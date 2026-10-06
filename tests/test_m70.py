"""M70 — Symmetric extent: extrude straddles its sketch plane.

Fusion's extent option, and a one-line truth in the kernel: the solid
grows −h/2..+h/2 about the profile plane.  An XY box sits z −5..+5, a
face-sketch wall centres on ITS plane (not the world's), symmetric +
taper composes (a double frustum), JSON and Change Parameters speak it,
and switching back restores the one-sided box exactly.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from conftest import script_cmd                                        # noqa: E402
from tracer.core.document import Document, ExtrudeFeature              # noqa: E402


def _rect(dx=40.0, dy=20.0):
    return np.array([[0, 0], [dx, 0], [dx, dy], [0, dy]], float)


def _box(s):
    lo, hi = s.bounding_box
    return np.asarray(lo, float), np.asarray(hi, float)


def test_symmetric_straddles_the_sketch_plane():
    d = Document("s1")
    d.add(ExtrudeFeature(name="w", outer=_rect(), height=10.0,
                         symmetric=True))
    s = d.recompute()
    lo, hi = _box(s)
    assert s.volume == pytest.approx(8000, rel=1e-6)
    assert lo[2] == pytest.approx(-5.0, abs=1e-6)
    assert hi[2] == pytest.approx(5.0, abs=1e-6)


def test_symmetric_respects_placement_and_face_planes():
    d = Document("s2")
    d.add(ExtrudeFeature(name="w", outer=_rect(), height=10.0,
                         plane="XZ", placement=(5.0, 2.0, 7.0),
                         symmetric=True))
    s = d.recompute()
    lo, hi = _box(s)
    cy = 0.5 * (lo[1] + hi[1])          # XZ plane's normal is Y
    assert cy == pytest.approx(2.0, abs=1e-4)
    assert s.volume == pytest.approx(8000, rel=1e-6)


def test_symmetric_and_taper_compose_into_a_double_frustum():
    d = Document("s3")
    d.add(ExtrudeFeature(name="w", outer=_rect(20.0, 20.0), height=10.0,
                         taper=45.0, symmetric=True))
    s = d.recompute()
    lo, hi = _box(s)
    assert lo[2] == pytest.approx(-5.0, abs=0.05)
    assert hi[2] == pytest.approx(5.0, abs=0.05)
    # widest at the +z end: 20 + 10 per edge = 40 across
    assert hi[0] - lo[0] == pytest.approx(40.0, abs=0.5)   # -10..+30
    assert s.to_trimesh().is_watertight
    want = 10 / 6 * (400 + 4 * 900 + 1600)   # 20² -> 30² -> 40²
    assert s.volume == pytest.approx(want, rel=1e-2)


def test_symmetric_json_round_trip():
    d = Document("s4")
    d.add(ExtrudeFeature(name="w", outer=_rect(), height=10.0,
                         symmetric=True))
    d.recompute()
    d2 = Document.from_dict(d.to_dict())
    ef = [f for f in d2.features if isinstance(f, ExtrudeFeature)][0]
    assert ef.symmetric is True
    lo, _ = _box(d2.recompute())
    assert lo[2] == pytest.approx(-5.0, abs=1e-6)


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
    r.ctx.release()


def _wall(win, qapp):
    win.new_document()
    ef = ExtrudeFeature(name="wall", outer=_rect(), height=10.0)
    win.doc.add(ef)
    win.recompute()
    qapp.processEvents()
    return ef


def test_change_parameters_makes_it_symmetric(win, qapp, monkeypatch):
    ef = _wall(win, qapp)
    lo0, hi0 = _box(win.doc.result)
    assert lo0[2] == pytest.approx(0.0, abs=1e-6)
    script_cmd(monkeypatch, {"height": 10.0, "fillet": 0.0,
                             "chamfer": 0.0, "taper": 0.0,
                             "symmetric": True})
    win.action_change_params(ef)
    qapp.processEvents()
    lo, hi = _box(win.doc.result)
    assert lo[2] == pytest.approx(-5.0, abs=1e-6)
    assert hi[2] == pytest.approx(5.0, abs=1e-6)
    win.rail.props.show_feature(ef)
    assert "extent: symmetric" in win.rail.props._body.text()


def test_symmetry_switches_back_exactly(win, qapp, monkeypatch):
    ef = _wall(win, qapp)
    script_cmd(monkeypatch, {"height": 10.0, "fillet": 0.0,
                             "chamfer": 0.0, "taper": 0.0,
                             "symmetric": True})
    win.action_change_params(ef)
    script_cmd(monkeypatch, {"height": 10.0, "fillet": 0.0,
                             "chamfer": 0.0, "taper": 0.0,
                             "symmetric": False})
    win.action_change_params(ef)
    qapp.processEvents()
    lo, hi = _box(win.doc.result)
    assert lo[2] == pytest.approx(0.0, abs=1e-6)
    assert hi[2] == pytest.approx(10.0, abs=1e-6)
