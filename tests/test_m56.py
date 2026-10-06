"""M56 — Marking menu: the right-click shortcut menu in the viewport.

Fusion's marking menu is how veterans live: a right-click (no drag)
anywhere in the canvas brings up Fit / Zoom to selection / the four
standard views / the Visual Styles submenu / grid & edge toggles.
The viewport emits context_request on an RMB click that did NOT drag
(a right-DRAG still orbits); the window pops a QMenu with exactly the
Fusion-shaped content, and every entry drives the real command.
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
    qapp.processEvents()


def test_right_click_opens_the_marking_menu(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    QTest.mousePress(vp, Qt.RightButton, Qt.NoModifier,
                     QPoint(500, 300), 10)
    QTest.mouseRelease(vp, Qt.RightButton, Qt.NoModifier,
                       QPoint(500, 300), 10)
    qapp.processEvents()
    assert win._mark_menu is not None and win._mark_menu.isVisible()
    labels = [a.text().replace("&", "") for a in win._mark_menu.actions()
              if not a.isSeparator()]
    assert labels == ["Fit", "Zoom to selection", "Zoom window",
                      "Isometric", "Front",
                      "Top", "Right", "Visual Styles", "Toggle grid",
                      "Toggle edges"]
    win._mark_menu.close()
    qapp.processEvents()


def test_right_drag_orbits_without_menu(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    cam = vp.camera()
    yaw0 = cam.yaw
    win._mark_menu = None
    QTest.mousePress(vp, Qt.RightButton, Qt.NoModifier,
                     QPoint(500, 300), 10)
    QTest.mouseMove(vp, QPoint(560, 310))
    QTest.mouseRelease(vp, Qt.RightButton, Qt.NoModifier,
                       QPoint(560, 310), 10)
    qapp.processEvents()
    assert cam.yaw != pytest.approx(yaw0)      # orbited
    assert win._mark_menu is None              # ...no menu


def test_marking_menu_entries_act(win, qapp):
    _plate(win, qapp)
    win.action_view("iso")
    cam = win.viewport.camera()
    menu = win._marking_menu()
    acts = {a.text().replace("&", ""): a for a in menu.actions()
            if not a.isSeparator()}
    acts["Front"].trigger()
    qapp.processEvents()
    import math
    assert cam.pitch == pytest.approx(0.0, abs=1e-9)   # Front view
    g0 = win._renderer.show_grid
    acts["Toggle grid"].trigger()
    assert win._renderer.show_grid != g0
    vs = [a.text() for a in acts["Visual Styles"].menu().actions()]
    assert vs == ["Wireframe", "Ghosted", "Shaded", "Shaded with edges",
                  "X-ray"]
    acts["Visual Styles"].menu().actions()[0].trigger()   # Wireframe
    assert win._renderer._style == "wireframe"
    win.action_visual_style("Shaded with edges")          # restore
    win._renderer.show_grid = g0                          # restore


def test_marking_menu_zoom_to_selection(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    dist0 = float(np.linalg.norm(
        np.asarray(vp.camera().position)
        - np.asarray(vp.camera().target)))
    win._zoom_to_selection()
    qapp.processEvents()
    # nothing selected -> same as Fit (camera re-fits the body), which
    # for the already-fitted view keeps the distance in a sane band
    dist1 = float(np.linalg.norm(
        np.asarray(vp.camera().position)
        - np.asarray(vp.camera().target)))
    assert 0.2 * dist0 < dist1 < 5.0 * dist0
