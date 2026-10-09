"""M59 — Fusion's selection grammar on real faces.

Plain click REPLACES (the picked face group, whole), Ctrl+click
TOGGLES in and out of the set, Ctrl+click on empty ground changes
nothing, plain click on empty ground clears.  A Ctrl+drag rubber band
ADDS to the set; a plain one replaces it.
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


def _cube(win, qapp):
    from tracer.core.document import PrimitiveFeature
    win.new_document()
    win.doc.add(PrimitiveFeature(name="cube", kind="box",
                                 dims={"dx": 30, "dy": 30, "dz": 30}))
    win.recompute()
    win.viewport.refresh(fit=True)
    qapp.processEvents()


def _click(win, qapp, world=None, spot=None, ctrl=False):
    vp = win.viewport
    if world is not None:
        spot = vp.camera().project(np.asarray(world, float),
                                   vp.width(), vp.height())
    mods = Qt.KeyboardModifier.ControlModifier if ctrl \
        else Qt.KeyboardModifier.NoModifier
    p = QPoint(int(spot[0]), int(spot[1]))
    QTest.mousePress(vp, Qt.LeftButton, mods, p, 10)
    QTest.mouseRelease(vp, Qt.LeftButton, mods, p, 10)
    qapp.processEvents()


TOP = (15, 15, 30)        # centre of the top face
FRONT = (15, 0, 15)       # centre of a side face (may or may not face
                          # the iso camera — the test just needs a
                          # DIFFERENT visible face)


def test_plain_click_replaces_selection(win, qapp):
    _cube(win, qapp)
    _click(win, qapp, TOP)
    assert len(win.viewport.selected_groups()) == 1
    n_top = np.asarray(win.viewport.selected_face()["normal"], float)
    _click(win, qapp, FRONT)
    g = win.viewport.selected_groups()
    assert len(g) == 1, "plain click must REPLACE, not accumulate"
    n_front = np.asarray(win.viewport.selected_face()["normal"], float)
    assert np.linalg.norm(n_top - n_front) > 0.3    # a different face


def test_ctrl_click_toggles_into_and_out(win, qapp):
    _cube(win, qapp)
    _click(win, qapp, TOP)
    _click(win, qapp, FRONT, ctrl=True)
    assert len(win.viewport.selected_groups()) == 2
    _click(win, qapp, FRONT, ctrl=True)           # toggle back out
    assert len(win.viewport.selected_groups()) == 1
    _click(win, qapp, spot=(2000, 500), ctrl=True)   # empty: no change
    assert len(win.viewport.selected_groups()) == 1


def test_plain_click_empty_clears(win, qapp):
    _cube(win, qapp)
    _click(win, qapp, TOP)
    _click(win, qapp, spot=(2000, 500))
    assert len(win.viewport.selected_groups()) == 0


def test_ctrl_box_adds_plain_box_replaces(win, qapp):
    _cube(win, qapp)
    _click(win, qapp, TOP)
    assert len(win.viewport.selected_groups()) == 1
    vp = win.viewport
    big = [QPoint(40, 40), QPoint(vp.width() - 40, vp.height() - 40)]

    def drag(ctrl):
        QTest.mousePress(vp, Qt.LeftButton,
                         Qt.KeyboardModifier.ControlModifier if ctrl
                         else Qt.KeyboardModifier.NoModifier, big[0], 10)
        QTest.mouseMove(vp, big[1])
        QTest.mouseRelease(vp, Qt.LeftButton,
                           Qt.KeyboardModifier.NoModifier, big[1], 10)
        qapp.processEvents()
    drag(ctrl=True)                               # add everything else
    assert len(vp.selected_groups()) == 6, "ctrl box must ADD"
    drag(ctrl=False)                              # replace: still all
    assert len(vp.selected_groups()) == 6
