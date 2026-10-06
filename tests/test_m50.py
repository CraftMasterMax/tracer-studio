"""M50 — pattern on path: a sketch chain becomes the walk.

sample_polyline pins the stations (equally spaced by arc length, ends
included), path_chain(need_circle=False) wants a bare open chain, and
PathPatternFeature places the source at each station (translation
first, v1).  End-to-end: plate + boss, a fresh sketch draws the walk,
the command dialog picks the boss -> three watertight bumps down the
line, JSON-safe.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox                # noqa: E402

from conftest import feature_rows, script_cmd                          # noqa: E402
from tracer.core.document import (Document, PathPatternFeature,        # noqa: E402
                                  PrimitiveFeature)
from tracer.core.sweep import path_chain, sample_polyline              # noqa: E402
from tracer.core.sketch.model import SketchModel                       # noqa: E402


# ---- core: stations --------------------------------------------------------------

def test_station_spacing_is_even_by_arc_length():
    assert sample_polyline([(0, 0), (30, 0)], 4) == \
        [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)]
    # an L of two equal legs: the mid station lands on the corner
    got = sample_polyline([(0, 0), (10, 0), (10, 10)], 3)
    assert np.allclose(got, [(0, 0), (10, 0), (10, 10)])


def test_station_count_clamps_and_ends_are_kept():
    got = sample_polyline([(0, 0), (5, 0)], 1)      # < 2 clamps to 2
    assert len(got) == 2 and got[0] == (0.0, 0.0) and got[-1] == (5.0, 0.0)


def test_chain_without_profile_circle():
    m = SketchModel()
    a, b, c = m.point(0, 0), m.point(10, 0), m.point(10, 8)
    m.add_line(a, b)
    m.add_line(b, c)
    pts, closed = path_chain(m, need_circle=False)
    assert not closed and len(pts) >= 3
    m.add_circle(m.point(3, -6), 2.0)               # a stray circle is an error
    with pytest.raises(ValueError):
        path_chain(m, need_circle=False)


# ---- core: the feature ------------------------------------------------------------

def _plate_boss():
    d = Document("walk")
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 80, "dy": 20, "dz": 5}))
    d.add(PrimitiveFeature(name="boss", kind="cylinder",
                           dims={"radius": 4.0, "height": 6},
                           placement=(10, 10, 5.0), op="union"))
    d.recompute()
    return d


def test_three_stations_place_three_bumps():
    d = _plate_boss()
    boss = d.features[1]
    d.add(PathPatternFeature(name="Path of boss", op="union",
                             source_uid=boss.uid,
                             path=[[10, 10], [30, 10], [50, 10]], count=3))
    s = d.recompute()
    assert s.to_trimesh().is_watertight
    want = 80 * 20 * 5 + 3 * math.pi * 16 * 6
    assert s.volume == pytest.approx(want, rel=0.01)


def test_path_pattern_json_round_trip():
    d = _plate_boss()
    boss = d.features[1]
    d.add(PathPatternFeature(name="Path of boss", op="union",
                             source_uid=boss.uid,
                             path=[[10, 10], [30, 10], [50, 10]], count=4))
    vol = d.recompute().volume
    d2 = Document.from_dict(d.to_dict())
    pf = [f for f in d2.features if isinstance(f, PathPatternFeature)][0]
    assert pf.count == 4 and len(pf.path) == 3
    assert d2.recompute().volume == pytest.approx(vol, abs=1)


# ---- UI -----------------------------------------------------------------------------

from tracer.ui.mainwindow import MainWindow                             # noqa: E402
from tracer.ui.renderer import SceneRenderer                            # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:                     # CI windows runners: no GL
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


def _plate_boss_ui(win, qapp):
    """plate + boss on the model, then drop into a fresh empty sketch."""
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 80, "dy": 20, "dz": 5}))
    win.doc.add(PrimitiveFeature(name="boss", kind="cylinder",
                                 dims={"radius": 4.0, "height": 6},
                                 placement=(10, 10, 5.0), op="union"))
    win.recompute()
    win.action_new_sketch()
    qapp.processEvents()
    return win.sketch.model


def _walk_sketch(win, qapp, coords=((10, 10), (30, 10), (50, 10))):
    m = _plate_boss_ui(win, qapp)
    pts = [m.point(*c) for c in coords]
    for i in range(len(pts) - 1):
        m.add_line(pts[i], pts[i + 1])
    qapp.processEvents()
    return m


def test_command_walks_the_boss_down_the_path(win, qapp, monkeypatch):
    _walk_sketch(win, qapp)
    script_cmd(monkeypatch, {"src": "boss", "count": 3})
    before = win.doc.result.volume
    win.action_path_pattern()
    qapp.processEvents()
    pf = [f for f in win.doc.features if isinstance(f, PathPatternFeature)]
    assert len(pf) == 1 and pf[0].name == "Path of boss"
    assert pf[0].count == 3 and len(pf[0].path) == 3
    s = win.doc.result
    assert s.to_trimesh().is_watertight
    want = 80 * 20 * 5 + 3 * math.pi * 16 * 6
    assert s.volume == pytest.approx(want, rel=0.01)
    assert s.volume > before
    assert "along the path" in win.status.currentMessage()
    rows = [r.text(0) for r in feature_rows(win)]
    assert any(r.endswith("Path of boss") and "\u2935" in r for r in rows)


def test_closed_loop_is_refused(win, qapp, monkeypatch):
    m = _plate_boss_ui(win, qapp)
    p0, p1, p2 = m.point(10, 10), m.point(30, 10), m.point(20, 18)
    m.add_line(p0, p1)
    m.add_line(p1, p2)
    m.add_line(p2, p0)                             # closed triangle (shared pts)
    qapp.processEvents()
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(a[2])))
    win.action_path_pattern()
    qapp.processEvents()
    assert seen and "OPEN" in seen[-1]
    assert not [f for f in win.doc.features
                if isinstance(f, PathPatternFeature)]


def test_inspector_counts_copies_along_length(win, qapp, monkeypatch):
    _walk_sketch(win, qapp)
    script_cmd(monkeypatch, {"src": "boss", "count": 3})
    win.action_path_pattern()
    pf = [f for f in win.doc.features
          if isinstance(f, PathPatternFeature)][0]
    win.rail.props.show_feature(pf)
    html = win.rail.props._body.text()
    assert "3 copies walking" in html and "40 mm path" in html
