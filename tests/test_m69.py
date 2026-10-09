"""M69 — Taper (draft): extrude walls that lean, Fusion's draft angle.

The outer skin lofts to the profile offset outward by h·tan(taper);
holes shrink on the same slope through cutters that run past both caps.
Ground truths are prismatoids (Simpson, exact for quadratic area growth)
and a cone frustum for circles, all to loft-tessellation tolerance:
a 45° rectangle widens 40x20 -> 60x40 (15333 mm^3), a 45° circle goes
R20 -> R30 (the frustum), a drafted through-hole keeps its channel clean
and watertight, and taper 0 stays byte-identical to a plain extrude.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from conftest import feature_rows, script_cmd                          # noqa: E402
from tracer.core.document import (Document,                            # noqa: E402
                                  ExtrudeFeature)


def _rect(dx, dy):
    return np.array([[0, 0], [dx, 0], [dx, dy], [0, dy]], float)


def _circ(r, n=64, c=(0.0, 0.0)):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)])


def _prismatoid(ab, am, at, h):
    return h / 6.0 * (ab + 4 * am + at)


# ---- core -------------------------------------------------------------------------

def test_taper_zero_is_a_plain_extrude():
    d = Document("t0")
    d.add(ExtrudeFeature(name="wall", outer=_rect(40, 20), height=10.0))
    s = d.recompute()
    assert s.volume == pytest.approx(8000, rel=1e-6)


def test_positive_draft_lofts_to_the_prismatoid():
    d = Document("t1")
    d.add(ExtrudeFeature(name="wall", outer=_rect(40, 20), height=10.0,
                         taper=45.0))          # grows 10 mm/edge
    s = d.recompute()
    want = _prismatoid(800, 50 * 30, 60 * 40, 10)
    assert s.volume == pytest.approx(want, rel=1e-2)
    assert s.to_trimesh().is_watertight


def test_draft_circle_is_a_cone_frustum():
    d = Document("t2")
    d.add(ExtrudeFeature(name="boss", outer=_circ(20, c=(30, 30)),
                         height=10.0, taper=45.0))   # R20 -> R30
    s = d.recompute()
    want = math.pi * 10 / 3 * (400 + 600 + 900)
    assert s.volume == pytest.approx(want, rel=2e-3)
    assert s.to_trimesh().is_watertight


def test_draft_through_hole_keeps_a_clean_channel():
    d = Document("t3")
    d.add(ExtrudeFeature(name="wall", outer=_rect(40, 20),
                         holes=[_circ(4, c=(20, 10))], height=10.0,
                         taper=15.0))          # hole survives 4 -> 1.32
    s = d.recompute()
    g = math.tan(math.radians(15)) * 10
    wall = _prismatoid(800, (40 + g) * (20 + g),
                       (40 + 2 * g) * (20 + 2 * g), 10)
    removed = math.pi * 12 / 3 * ((4 + g / 10) ** 2
                                  + (4 + g / 10) * (4 - g - g / 10)
                                  + (4 - g - g / 10) ** 2)
    assert s.volume == pytest.approx(wall - removed, rel=2e-2)
    tm = s.to_trimesh()
    assert tm.is_watertight
    assert tm.euler_number == 0              # one through channel


def test_negative_draft_necks_in():
    d = Document("t4")
    d.add(ExtrudeFeature(name="wall", outer=_rect(40, 20), height=10.0,
                         taper=-22.5))         # shrinks 4.142 mm/edge
    s = d.recompute()
    g = math.tan(math.radians(22.5)) * 10
    want = _prismatoid(800, (40 - g) * (20 - g), (40 - 2 * g) * (20 - 2 * g),
                       10)
    assert s.volume == pytest.approx(want, rel=2e-2)
    assert s.to_trimesh().is_watertight


def test_draft_json_round_trip():
    d = Document("t5")
    d.add(ExtrudeFeature(name="boss", outer=_circ(20, c=(30, 30)),
                         height=10.0, taper=45.0))
    v1 = d.recompute().volume
    d2 = Document.from_dict(d.to_dict())
    ef = [f for f in d2.features if isinstance(f, ExtrudeFeature)][0]
    assert ef.taper == pytest.approx(45.0)
    assert d2.recompute().volume == pytest.approx(v1, abs=1)


# ---- UI ---------------------------------------------------------------------------

from tracer.ui.mainwindow import MainWindow                            # noqa: E402
from tracer.ui.renderer import SceneRenderer                           # noqa: E402


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
    r.close()


def _wall(win, qapp):
    win.new_document()
    ef = ExtrudeFeature(name="wall", outer=_rect(40, 20), height=10.0)
    win.doc.add(ef)
    win.recompute()
    qapp.processEvents()
    return ef


def test_change_parameters_leans_the_wall(win, qapp, monkeypatch):
    ef = _wall(win, qapp)
    assert win.doc.result.volume == pytest.approx(8000, rel=1e-6)
    script_cmd(monkeypatch, {"height": 10.0, "fillet": 0.0,
                             "chamfer": 0.0, "taper": 45.0, "symmetric": False})
    win.action_change_params(ef)
    qapp.processEvents()
    assert ef.taper == pytest.approx(45.0)
    want = _prismatoid(800, 50 * 30, 60 * 40, 10)
    assert win.doc.result.volume == pytest.approx(want, rel=1e-2)
    win.rail.props.show_feature(ef)
    assert "taper: +45.0\u00b0" in win.rail.props._body.text()


def test_taper_back_to_zero_restores_the_box(win, qapp, monkeypatch):
    ef = _wall(win, qapp)
    script_cmd(monkeypatch, {"height": 10.0, "fillet": 0.0,
                             "chamfer": 0.0, "taper": 30.0, "symmetric": False})
    win.action_change_params(ef)
    qapp.processEvents()
    v30 = win.doc.result.volume
    assert v30 > 8000
    script_cmd(monkeypatch, {"height": 10.0, "fillet": 0.0,
                             "chamfer": 0.0, "taper": 0.0, "symmetric": False})
    win.action_change_params(ef)
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(8000, rel=1e-6)
