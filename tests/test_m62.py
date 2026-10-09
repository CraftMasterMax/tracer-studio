"""M62 — Zoom Window: drag a rectangle, the view fills with what's in it.

Fusion's zoom marking menu: Fit / Zoom to selection / Zoom window.
Arming Zoom window (marking menu or Modify is not Fusion's home — the
viewport owns the gesture) changes the cursor; the next LMB drag draws
the same rubber band and, on release, refits the camera to the world
bbox of the mesh that fell inside; a plain click or Esc aborts without
moving the camera.  The marking menu gains the entry in Fusion's place:
right after Zoom to selection.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                             # noqa: E402
from PySide6.QtTest import QTest                                   # noqa: E402
from PySide6.QtWidgets import QApplication                         # noqa: E402

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
    r.close()


def _plate(win, qapp):
    from tracer.core.document import PrimitiveFeature
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 20, "dz": 10}))
    win.recompute()
    win.viewport.refresh(fit=True)
    qapp.processEvents()


def test_marking_menu_gains_zoom_window(win, qapp):
    _plate(win, qapp)
    menu = win._marking_menu()
    labels = [a.text().replace("&", "") for a in menu.actions()
              if not a.isSeparator()]
    assert labels[:3] == ["Fit", "Zoom to selection", "Zoom window"]


def test_zoom_window_drag_refits_camera(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    cam = vp.camera()
    d0 = cam.distance
    t0 = cam.target.copy()
    win.action_zoom_window()
    assert vp._zoom_win is not None                # armed
    # window around the left half of the projected body only
    lo, hi = win.doc.result.bounding_box
    p_lo = cam.project(np.asarray(lo, float), vp.width(), vp.height())
    p_hi = cam.project(np.asarray(hi, float), vp.width(), vp.height())
    x0 = int(min(p_lo[0], p_hi[0])) - 8
    x1 = int((min(p_lo[0], p_hi[0]) + max(p_lo[0], p_hi[0])) / 2)
    y0 = int(min(p_lo[1], p_hi[1])) - 8
    y1 = int(max(p_lo[1], p_hi[1])) + 8
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(x0, y0), 10)
    QTest.mouseMove(vp, QPoint(x1, y1))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(x1, y1),
                       10)
    qapp.processEvents()
    assert vp._zoom_win is None                    # gesture spent
    assert cam.distance < d0 * 0.95                # zoomed IN
    assert np.linalg.norm(cam.target - t0) > 1.0   # and re-centred
    assert "Zoom window" in win.status.currentMessage()


def test_zoom_window_plain_click_aborts(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    cam = vp.camera()
    d0, t0 = cam.distance, cam.target.copy()
    win.action_zoom_window()
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(120, 480),
                     10)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier,
                       QPoint(120, 480), 10)
    qapp.processEvents()
    assert vp._zoom_win is None
    assert cam.distance == pytest.approx(d0)
    assert np.allclose(cam.target, t0)
    assert "cancelled" in win.status.currentMessage().lower()


def test_zoom_window_esc_aborts(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    win.action_zoom_window()
    assert vp._zoom_win is not None
    from PySide6.QtGui import QKeyEvent
    vp.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape,
                               Qt.KeyboardModifier.NoModifier, 0, 0, 0))
    qapp.processEvents()
    assert vp._zoom_win is None
