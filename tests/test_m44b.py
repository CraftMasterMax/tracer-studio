"""M44b — viewport furniture: the Fusion nav widget under the ViewCube
(Home · Zoom In · Zoom Out) with hover feedback and working actions."""
import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QPointF, Qt                      # noqa: E402
from PySide6.QtGui import QMouseEvent                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from tracer.ui.mainwindow import MainWindow                          # noqa: E402
from tracer.ui.renderer import SceneRenderer                         # noqa: E402
from tracer.ui.viewcube import NavWidget                             # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


# ---- pure geometry -------------------------------------------------------------

def test_nav_geometry_and_hit():
    n = NavWidget()
    n.place(800, 70)
    assert set(n.rects) == {"home", "in", "out"}
    assert n.rects["in"].top() > n.rects["home"].bottom()      # stacked
    cx = n.rects["home"].center()
    assert n.hit(cx) == "home"
    assert n.hit(QPointF(5, 5)) is None


# ---- wired into the viewport ------------------------------------------------------

def _click_at(vp, pos: QPointF):
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, pos,
                     vp.mapToGlobal(pos.toPoint()),
                     Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, ev)
    up = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, pos,
                     vp.mapToGlobal(pos.toPoint()),
                     Qt.MouseButton.LeftButton,
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, up)


def test_nav_sits_under_the_cube(win):
    vp = win.viewport
    vp.resize(900, 600)
    vp._nav.place(vp.width(), vp._cube.rect.bottom() + 8)
    assert vp._nav.rects["home"].top() > vp._cube.rect.bottom()
    assert vp._nav.rects["home"].right() <= vp.width()


def test_zoom_buttons_dive_and_pull(win):
    vp = win.viewport
    d0 = vp._cam.distance
    _click_at(vp, vp._nav.rects["in"].center())
    assert vp._cam.distance < d0              # zoom in shortens the dive
    _click_at(vp, vp._nav.rects["out"].center())
    assert vp._cam.distance == pytest.approx(d0)


def test_home_button_refits(win):
    vp = win.viewport
    vp._cam.zoom(3.0)
    away = vp._cam.distance
    _click_at(vp, vp._nav.rects["home"].center())
    assert vp._cam.distance < away            # back to the framed distance


def test_hover_state_follows_the_pointer(win):
    vp = win.viewport
    moved = QMouseEvent(QMouseEvent.Type.MouseMove,
                        vp._nav.rects["out"].center(),
                        vp.mapToGlobal(QPoint(400, 400)),
                        Qt.MouseButton.NoButton,
                        Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, moved)
    assert vp._nav.hover == "out"
    away = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(30, 300),
                       vp.mapToGlobal(QPoint(30, 300)),
                       Qt.MouseButton.NoButton,
                       Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, away)
    assert vp._nav.hover is None


# ---- proof of life -----------------------------------------------------------------

def test_screenshot_proof(win, qapp):
    win._show_page(win.viewport)
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    img = win.viewport.grab()
    assert img.save(f"{out}/m44b_navwidget.png")
    # the widget must actually be inked: nav column has lighter pixels
    import numpy as np
    from PySide6.QtGui import QImage
    qimg = img.toImage().convertToFormat(QImage.Format.Format_RGB32)
    buf = np.frombuffer(qimg.constBits(), np.uint8,
                        qimg.sizeInBytes()).reshape(
        qimg.height(), qimg.width(), 4)[:, :, :3]
    w = qimg.width()
    col = buf[80:220, w - 40:w]
    assert (col.max(axis=2) > 200).sum() > 40     # home roof + glyphs
