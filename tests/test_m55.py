"""M55 — Rotate Body: drag an RGB ring, the solid spins, release commits.

Core: rotation_about is a right-hand-rule rigid matrix; RotateFeature
swaps a 40x20 box to 20x40 with a +90° Z spin and survives JSON.
Viewport: the cursor ray's polar angle in the ring plane recovers the
dragged degrees (test presses a projected world 45° point).  UI: a
45°→135° ring drag leaves the body rotated a quarter turn, ✳ in the
timeline, and an empty click cancels.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                             # noqa: E402
from PySide6.QtTest import QTest                                   # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox            # noqa: E402

from conftest import feature_rows                                  # noqa: E402
from tracer.core.document import (Document, PrimitiveFeature,      # noqa: E402
                                  RotateFeature)
from tracer.core.geometry import Solid, rotation_about             # noqa: E402


# ---- core ------------------------------------------------------------------------

def test_rotation_about_right_hand_rule():
    m = rotation_about((0, 0, 0), (0, 0, 1), np.deg2rad(90.0))
    p = m @ np.array([1.0, 0.0, 0.0, 1.0])
    assert np.allclose(p[:3], (0.0, 1.0, 0.0), atol=1e-9)
    m2 = rotation_about((10, 0, 0), (0, 0, 1), np.deg2rad(90.0))
    q = m2 @ np.array([11.0, 0.0, 5.0, 1.0])
    assert np.allclose(q[:3], (10.0, 1.0, 5.0), atol=1e-9)


def test_rotate_feature_quarter_turn():
    d = Document("spin")
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 20, "dz": 10}))
    d.add(RotateFeature(name="Rotate Z +90.0\u00b0", center=(20, 10, 5),
                        axis=(0, 0, 1), angle_deg=90.0))
    s = d.recompute()
    lo, hi = s.bounding_box
    assert (hi[0] - lo[0]) == pytest.approx(20, abs=1e-3)
    assert (hi[1] - lo[1]) == pytest.approx(40, abs=1e-3)
    assert s.volume == pytest.approx(8000, rel=1e-6)
    assert s.to_trimesh().is_watertight


def test_rotate_feature_json_round_trip():
    d = Document("spin")
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 30, "dy": 30, "dz": 6}))
    d.add(RotateFeature(name="r", center=(15, 15, 3), axis=(0, 1, 0),
                        angle_deg=33.5))
    vol = d.recompute().volume
    d2 = Document.from_dict(d.to_dict())
    rf = [f for f in d2.features if isinstance(f, RotateFeature)][0]
    assert rf.angle_deg == pytest.approx(33.5)
    assert np.allclose(rf.axis, (0, 1, 0))
    assert d2.recompute().volume == pytest.approx(vol, abs=1)


# ---- UI ----------------------------------------------------------------------------

from tracer.ui.mainwindow import MainWindow                        # noqa: E402
from tracer.ui.renderer import SceneRenderer                        # noqa: E402


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


def _plate(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 20, "dz": 10}))
    win.recompute()
    win.viewport.refresh(fit=True)
    qapp.processEvents()


def test_ring_param_recovers_world_angle(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    cam = vp.camera()
    win.action_rotate_body()
    rot = vp._rot
    assert rot is not None
    c, R = rot["center"], rot["radius"]
    p = c + np.array([np.cos(np.pi / 4) * R, np.sin(np.pi / 4) * R, 0.0])
    px, py = cam.project(p, vp.width(), vp.height())
    rot["axis"] = 2
    assert vp._ring_param(rot, px, py) == pytest.approx(np.pi / 4,
                                                        abs=0.02)


def _drag_ring(win, qapp, axis, th0, th1):
    vp = win.viewport
    cam = vp.camera()
    c, R = vp._rot["center"], vp._rot["radius"]
    u, v = np.eye(3)[(axis + 1) % 3], np.eye(3)[(axis + 2) % 3]

    def sp(th):
        p = c + (np.cos(th) * u + np.sin(th) * v) * R
        return QPoint(*[int(round(x)) for x in
                        cam.project(p, vp.width(), vp.height())])
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, sp(th0), 10)
    qapp.processEvents()
    QTest.mouseMove(vp, sp(th1))
    qapp.processEvents()
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, sp(th1), 10)
    qapp.processEvents()


def test_drag_z_ring_quarter_turn(win, qapp):
    _plate(win, qapp)
    win.action_rotate_body()
    _drag_ring(win, qapp, axis=2, th0=np.pi / 4, th1=3 * np.pi / 4)
    rf = [f for f in win.doc.features if isinstance(f, RotateFeature)]
    assert len(rf) == 1
    assert rf[0].angle_deg == pytest.approx(90.0, abs=2.0)
    assert rf[0].name.startswith("Rotate z")
    lo, hi = win.doc.result.bounding_box
    assert (hi[0] - lo[0]) == pytest.approx(20, abs=1.0)
    assert (hi[1] - lo[1]) == pytest.approx(40, abs=1.0)
    assert "rotated" in win.status.currentMessage()
    rows = [r.text(0) for r in feature_rows(win)]
    assert any("\u27f3" in r for r in rows)


def test_empty_click_cancels_rotate(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    win.action_rotate_body()
    assert vp._rot is not None
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(15, 15), 10)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(15, 15), 10)
    qapp.processEvents()
    assert vp._rot is None
    assert not [f for f in win.doc.features
                if isinstance(f, RotateFeature)]
    assert "cancelled" in win.status.currentMessage()


def test_rotate_warning_without_body(win, qapp):
    win.new_document()
    seen = []
    orig = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **k: seen.append(a[2]))
    try:
        win.action_rotate_body()
    finally:
        QMessageBox.warning = orig
    assert seen and "Nothing to rotate" in seen[0]
