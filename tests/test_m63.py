"""M63 — viewport polish: cube hover glow + Fusion's two rubber colours.

Fusion's ViewCube lights the face under the cursor and offers a hand;
our rubber band speaks Fusion's language: left→right is a WINDOW
(blue, must contain), right→left is CROSSING (green, just touches).
The hover hit uses the same projected polygons that were painted, and
a pixel grab proves the hovered face actually renders different.
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
    r.ctx.release()


def _plate(win, qapp):
    from tracer.core.document import PrimitiveFeature
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 20, "dz": 10}))
    win.recompute()
    win.viewport.refresh(fit=True)
    win.viewport.camera().set_view("iso")
    qapp.processEvents()


def _cube_point(win, label):
    vp = win.viewport
    vp.grab()                                   # paints -> fills _screen
    path, _k = vp._cube._screen[label]          # "T"/"F"/"R"/"B"/"L"/"D"
    c = path.boundingRect().center()
    return QPoint(int(c.x()), int(c.y()))


def test_cube_hover_tracks_cursor_and_sets_hand(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    p = _cube_point(win, "T")
    QTest.mouseMove(vp, p)
    qapp.processEvents()
    assert vp._cube_hover == "top"
    assert vp.cursor().shape() == Qt.PointingHandCursor
    QTest.mouseMove(vp, QPoint(10, vp.height() - 10))
    qapp.processEvents()
    assert vp._cube_hover is None


def test_hovered_cube_face_renders_different(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    vp._cube_hover = None
    vp.update()
    qapp.processEvents()
    before = np.asarray(vp.grab().toImage().convertToFormat(
        __import__("PySide6.QtGui", fromlist=["QImage"]).QImage
        .Format_RGB888).bits(), dtype=np.uint8).copy()
    vp._cube_hover = "top"          # hit() path proven by the test above
    vp.update()
    qapp.processEvents()
    after = np.asarray(vp.grab().toImage().convertToFormat(
        __import__("PySide6.QtGui", fromlist=["QImage"]).QImage
        .Format_RGB888).bits(), dtype=np.uint8).copy()
    assert before.shape == after.shape
    assert int(np.count_nonzero(before != after)) > 8   # the face glowed
    vp._cube_hover = None


def test_rubber_window_is_blue_crossing_is_green(win, qapp):
    from PySide6.QtGui import QColor
    vp = win.viewport
    w_pen, _ = vp.rubber_style(True)
    c_pen, _ = vp.rubber_style(False)
    assert w_pen != c_pen
    assert QColor(w_pen).blue() > QColor(w_pen).red()
    assert QColor(c_pen).green() > QColor(c_pen).blue()
    vp._box = [QPoint(100, 100), QPoint(300, 300)]
    assert vp._box_is_window() is True          # left→right
    vp._box = [QPoint(300, 300), QPoint(100, 100)]
    assert vp._box_is_window() is False         # right→left
    vp._box = None
