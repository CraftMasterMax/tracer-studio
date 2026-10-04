"""M10: click-move-click rect/circle + shortcut tour & dedicated tab."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtGui import QKeySequence                       # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import (QApplication, QScrollArea,    # noqa: E402
                               QTabWidget, QTextEdit, QWidget)

from tracer.ui.shortcuts import SHORTCUTS, shortcut_tokens    # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
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


def _click(cv, x, y):
    p = cv.w2s(x, y).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, p, 10)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, p, 10)


# ---- click-move-click rect/circle -----------------------------------------
def test_click_move_click_rect(win, qapp):
    win.new_document()
    win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("rect")
    qapp.processEvents()
    _click(cv, 0, 0)                       # first corner
    assert cv._rect_corner is not None, "corner not armed after click"
    # moving to the second corner keeps it armed (just a rubber band)
    QTest.mouseMove(cv, cv.w2s(30, 20).toPoint())
    assert cv._rect_corner is not None, "moving cancelled the pending rect"
    assert len(cv.model.sketch.lines) == 0
    _click(cv, 30, 20)                     # second corner commits
    qapp.processEvents()
    assert len(cv.model.sketch.lines) == 4, "click-move-click drew no rect"
    assert cv._rect_corner is None
    xs = sorted({round(p.x) for l in cv.model.sketch.lines for p in (l.a, l.b)})
    ys = sorted({round(p.y) for l in cv.model.sketch.lines for p in (l.a, l.b)})
    assert xs == [0, 30] and ys == [0, 20]


def test_drag_rect_still_works(win, qapp):
    win.new_document()
    win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("rect")
    qapp.processEvents()
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, cv.w2s(0, 0).toPoint(), 10)
    QTest.mouseMove(cv, cv.w2s(12, 8).toPoint())
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, cv.w2s(12, 8).toPoint(), 10)
    qapp.processEvents()
    assert len(cv.model.sketch.lines) == 4, "drag rect regressed"
    assert cv._rect_corner is None, "drag left a corner armed"


def test_click_move_click_circle(win, qapp):
    win.new_document()
    win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("circle")
    qapp.processEvents()
    _click(cv, 0, 0)                       # centre
    _click(cv, 10, 0)                      # radius point
    qapp.processEvents()
    assert len(cv.model.sketch.circles) == 1, "click-move-click made no circle"
    c = cv.model.sketch.circles[0]
    assert c.r == pytest.approx(10, abs=0.3)
    assert cv._rect_corner is None


def test_rect_corner_cleared_by_tool_switch_and_escape(win, qapp):
    win.new_document()
    win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("rect")
    _click(cv, 0, 0)
    assert cv._rect_corner is not None
    cv.set_tool("line")
    assert cv._rect_corner is None, "tool switch kept a stale corner"
    cv.set_tool("rect")
    _click(cv, 0, 0)
    QTest.keyPress(cv, Qt.Key_Escape)
    assert cv._rect_corner is None, "escape kept a stale corner"


# ---- tour + shortcut sheet -------------------------------------------------
def test_shortcuts_are_a_dedicated_tab(win):
    assert isinstance(win.rail, QTabWidget)
    tabs = [win.rail.tabText(i) for i in range(win.rail.count())]
    assert "Shortcuts" in tabs
    page = win.rail.widget(tabs.index("Shortcuts"))
    assert isinstance(page, QScrollArea)


def test_shortcut_page_lists_keys(win, qapp):
    from PySide6.QtWidgets import QLabel
    tabs = [win.rail.tabText(i) for i in range(win.rail.count())]
    page = win.rail.widget(tabs.index("Shortcuts"))
    blob = " ".join(t.text() for t in page.findChildren(QLabel))
    for k in ("N", "X", "Ctrl + Z", "F"):
        assert k in blob, f"shortcut page missing {k!r}"


def test_show_shortcuts_activates_the_tab(win):
    win.rail.show_browser()
    assert win.rail.currentIndex() == 0
    win.show_shortcuts()
    assert win.rail.tabText(win.rail.currentIndex()) == "Shortcuts"


def test_tour_dialog_exec_when_shown(win, monkeypatch):
    # Replace the real (blocking) dialog with a recording stub that mirrors
    # the TourDialog surface show_tour() uses: ctor, btn_sheet.clicked, exec().
    from PySide6.QtCore import QObject
    from tracer.ui import mainwindow
    seen = {"ctor": 0, "connected": 0, "exec": 0}

    class Sig:
        def connect(self, fn):
            seen["connected"] += 1

    class Sheet:
        clicked = Sig()

    class FakeTour:
        def __init__(self, parent=None):
            seen["ctor"] += 1
            self.btn_sheet = Sheet()
        def accept(self):
            pass
        def exec(self):
            seen["exec"] += 1
            return 0

    monkeypatch.setattr(mainwindow, "TourDialog", FakeTour)
    win.show_tour()
    assert seen == {"ctor": 1, "connected": 2, "exec": 1}


def test_maybe_show_tour_shows_once(win, monkeypatch):
    from PySide6.QtCore import QSettings
    calls = []
    monkeypatch.setattr(win, "show_tour", lambda: calls.append(1))
    QSettings().remove("ui/tour_shown")
    assert win.maybe_show_tour() is True
    assert win.maybe_show_tour() is False
    assert calls == [1]            # only the first call opens the tour


# ---- single source of truth: table covers every real QAction shortcut ------
def test_table_covers_every_action_shortcut(win):
    listed = {t.replace(" ", "") for t in shortcut_tokens()}
    seqs = set()

    def walk(actions):
        for a in actions:
            s = a.shortcut()
            if not s.isEmpty():
                seqs.add(s.toString())
            if a.menu():
                walk(a.menu().actions())

    walk(win.menuBar().actions())
    assert seqs, "expected the menu bar to carry shortcuts"
    for s in seqs:
        assert s.replace(" ", "") in listed, f"{s} is bound but not in the sheet"

