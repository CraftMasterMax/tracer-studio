"""M53 — Move Body: grab a triad arrow and slide the body, Fusion-style.

Core: MoveFeature is a body op that translates everything and survives
JSON.  Viewport math: the cursor-ray-to-axis parameter recovers the
world offset along the grabbed axis.  UI: pressing the +X arrow and
dragging to a projected world point commits exactly that translation;
an empty click cancels without touching history.  (Mouse grammar —
MMB orbit / Shift+MMB pan — lives in test_fusion_parity.)
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                             # noqa: E402
from PySide6.QtTest import QTest                                   # noqa: E402
from PySide6.QtWidgets import QApplication                         # noqa: E402

from conftest import feature_rows                                  # noqa: E402
from tracer.core.document import (Document, MoveFeature,           # noqa: E402
                                  PrimitiveFeature)
from tracer.core.geometry import Solid                             # noqa: E402


# ---- core ------------------------------------------------------------------------

def test_move_feature_translates_everything():
    d = Document("slide")
    d.add(PrimitiveFeature(name="block", kind="box",
                           dims={"dx": 40, "dy": 40, "dz": 20}))
    d.add(MoveFeature(name="Move", vec=(10.0, -5.0, 2.0)))
    s = d.recompute()
    lo, hi = s.bounding_box
    assert lo[0] == pytest.approx(10) and lo[1] == pytest.approx(-5)
    assert lo[2] == pytest.approx(2)
    assert s.volume == pytest.approx(32000, rel=1e-6)


def test_move_feature_json_round_trip():
    d = Document("slide")
    d.add(PrimitiveFeature(name="block", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10}))
    d.add(MoveFeature(name="Move", vec=(1.5, 2.5, -3.5)))
    d.recompute()
    d2 = Document.from_dict(d.to_dict())
    mf = [f for f in d2.features if isinstance(f, MoveFeature)][0]
    assert np.allclose(mf.vec, (1.5, 2.5, -3.5))
    lo = d2.recompute().bounding_box[0]
    assert np.allclose(lo, (1.5, 2.5, -3.5))


def test_solid_translated_moves_bbox():
    s = Solid.box(10, 10, 10).translated((4.0, 0.0, -2.0))
    assert np.allclose(s.bounding_box[0], (4.0, 0.0, -2.0))


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


def _block(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="block", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 20}))
    win.recompute()
    win.viewport.refresh(fit=True)
    qapp.processEvents()


def test_axis_param_recovers_world_offset(win, qapp):
    """Pressing on a point of the grabbed axis reads that point's
    world parameter — the drag math with a known answer."""
    _block(win, qapp)
    vp = win.viewport
    cam = vp.camera()
    win.action_move_body()               # arms triad at bbox centre
    mv = vp._mv
    assert mv is not None
    o = mv["origin"]
    p = o + np.array([25.0, 0.0, 0.0])
    px, py = cam.project(p, vp.width(), vp.height())
    mv["axis"] = 0
    assert vp._axis_param(mv, px, py) == pytest.approx(25.0, abs=0.5)


def _drag_axis(win, qapp, axis, t0_mm, t1_mm):
    """Press the triad shaft at world parameter `t0_mm` along the axis
    and release at `t1_mm`; the handler commits the difference."""
    vp = win.viewport
    cam = vp.camera()
    o = vp._mv["origin"]
    e = np.eye(3)[axis]
    p0 = cam.project(o + e * t0_mm, vp.width(), vp.height())
    p1 = cam.project(o + e * t1_mm, vp.width(), vp.height())
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier,
                     QPoint(int(p0[0]), int(p0[1])), 10)
    qapp.processEvents()
    QTest.mouseMove(vp, QPoint(int(p1[0]), int(p1[1])))
    qapp.processEvents()
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier,
                       QPoint(int(p1[0]), int(p1[1])), 10)
    qapp.processEvents()


def test_drag_x_arrow_moves_body_x(win, qapp):
    _block(win, qapp)
    before = win.doc.result.bounding_box[0].copy()
    win.action_move_body()
    grab = win.viewport._mv["length"] * 0.8
    _drag_axis(win, qapp, axis=0, t0_mm=grab, t1_mm=40.0)
    mf = [f for f in win.doc.features if isinstance(f, MoveFeature)]
    assert len(mf) == 1 and mf[0].name == "Move"
    assert mf[0].vec[0] == pytest.approx(40.0 - grab, abs=1.5)
    assert mf[0].vec[1] == pytest.approx(0.0, abs=1e-9)
    after = win.doc.result.bounding_box[0]
    assert after[0] - before[0] == pytest.approx(40.0 - grab, abs=1.5)
    assert "moved" in win.status.currentMessage()
    rows = [r.text(0) for r in feature_rows(win)]
    assert any("\u2725" in r and r.endswith("Move") for r in rows)


def test_empty_click_cancels_without_history(win, qapp):
    _block(win, qapp)
    vp = win.viewport
    win.action_move_body()
    assert vp._mv is not None
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(15, 15), 10)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(15, 15), 10)
    qapp.processEvents()
    assert vp._mv is None
    assert not [f for f in win.doc.features
                if isinstance(f, MoveFeature)]
    assert "cancelled" in win.status.currentMessage()


def test_move_warning_without_body(win, qapp):
    from PySide6.QtWidgets import QMessageBox
    win.new_document()
    seen = []
    orig = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **k: seen.append(a[2]))
    try:
        win.action_move_body()
    finally:
        QMessageBox.warning = orig
    assert seen and "Nothing to move" in seen[0]
