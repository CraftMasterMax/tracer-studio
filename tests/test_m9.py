"""M9: sketch-level undo/redo + sketch-page shortcut conflict fix."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                        # noqa: E402
from PySide6.QtTest import QTest                     # noqa: E402
from PySide6.QtWidgets import (QApplication, QMessageBox)  # noqa: E402

from forma.core.sketch.constraints import Horizontal  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from forma.ui.mainwindow import MainWindow
    from forma.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


def _draw_rect(cv, qapp, x1=30, y1=20):
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, cv.w2s(0, 0).toPoint(), 10)
    QTest.mouseMove(cv, cv.w2s(x1, y1).toPoint())
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier,
                       cv.w2s(x1, y1).toPoint(), 10)
    qapp.processEvents()


def test_rect_undo_redo(win, qapp):
    win.new_document()
    win.action_new_sketch()
    cv = win.sketch
    _draw_rect(cv, qapp)
    assert len(cv.model.sketch.lines) == 4
    QTest.keyPress(cv, Qt.Key_Z, Qt.ControlModifier)
    qapp.processEvents()
    assert len(cv.model.sketch.lines) == 0, "undo did not remove the rectangle"
    QTest.keyPress(cv, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
    qapp.processEvents()
    assert len(cv.model.sketch.lines) == 4, "redo did not restore it"


def test_constraint_toggle_undo(win, qapp):
    win.new_document()
    win.action_new_sketch()
    cv = win.sketch
    m = cv.model
    l = m.add_line(m.point(0, 0), m.point(30, 0))
    qapp.processEvents()
    cv._sel = [l]
    QTest.keyPress(cv, Qt.Key_H)
    qapp.processEvents()
    assert any(isinstance(c, Horizontal) for c in m.sketch.constraints)
    QTest.keyPress(cv, Qt.Key_Z, Qt.ControlModifier)
    qapp.processEvents()
    assert not any(isinstance(c, Horizontal) for c in m.sketch.constraints)


def test_point_drag_undo_restores_position(win, qapp):
    win.new_document()
    win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("select")
    m = cv.model
    a, b = m.point(0, 0), m.point(40, 0)
    m.add_line(a, b)
    qapp.processEvents()
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, cv.w2s(40, 0).toPoint(), 10)
    QTest.mouseMove(cv, cv.w2s(70, 5).toPoint())
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier,
                       cv.w2s(70, 5).toPoint(), 10)
    qapp.processEvents()
    # NB: undo rebuilds the sketch graph, so read entities via the live
    # model — entity objects captured before an undo become stale refs.
    live = cv.model.sketch.lines[0].b
    assert live.x == pytest.approx(70, abs=0.5)
    QTest.keyPress(cv, Qt.Key_Z, Qt.ControlModifier)
    qapp.processEvents()
    assert cv.model.sketch.lines[0].b.x == pytest.approx(40, abs=0.5), \
        "undo did not restore drag"
    QTest.keyPress(cv, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
    assert cv.model.sketch.lines[0].b.x == pytest.approx(70, abs=0.5)


def test_sketch_page_disables_conflicting_shortcuts(win, qapp):
    assert win.act_grid.isEnabled() and win.act_undo.isEnabled()
    win.action_new_sketch()
    assert not win.act_grid.isEnabled(), "G shortcut would eat sketch keys"
    assert not win.act_undo.isEnabled()
    assert not win.act_edges.isEnabled()
    win._show_page(win.viewport)
    assert win.act_grid.isEnabled() and win.act_undo.isEnabled()


def test_back_button_and_discard_guard(win, qapp, monkeypatch):
    win.new_document()
    win.action_new_sketch()
    cv = win.sketch
    _draw_rect(cv, qapp)
    win._show_page(win.viewport)
    assert win.stack.currentWidget() is win.viewport
    assert len(win.doc.features) == 0          # nothing baked yet

    # un-extruded sketch survives Back, and guards any new sketch...
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.No))
    win.action_new_sketch()
    assert win.stack.currentWidget() is win.viewport   # refused to discard

    # ...until the user confirms
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    win.action_new_sketch()
    assert win.stack.currentWidget() is win._sketch_page
    assert not win.sketch.model.sketch.lines
