"""M39 — Fusion ribbon GUI.

The chrome now wears the Fusion uniform: a quick-access strip (new/open/
save/undo/redo), Design ⇄ Sketch workspace tabs that stay in sync with
the visible page, and icon-grouped command panels per tab.  Buttons are
found by tooltip prefix (the M20 contract), menus' first entry is the
headline operation, and the tab bar is context-aware: clicking Sketch
starts one, clicking Design steps back to the model.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (QApplication, QFileDialog,               # noqa: E402
                               QToolButton)

from tracer.ui.mainwindow import MainWindow                             # noqa: E402
from tracer.ui.renderer import SceneRenderer                            # noqa: E402
from tracer.ui.ribbon import RibbonBar                                  # noqa: E402


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
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _toolbutton(win, tip_start):
    for b in win.findChildren(QToolButton):
        if b.toolTip().startswith(tip_start):
            return b
    raise AssertionError(f"no ribbon button {tip_start!r}")


# ---- anatomy ------------------------------------------------------------------

def test_ribbon_replaces_the_flat_toolbar(win):
    ribbons = [c for c in win.findChildren(RibbonBar)]
    assert len(ribbons) == 1
    assert win.ribbon.tabs.count() == 2
    assert [win.ribbon.tabs.tabText(i) for i in range(2)] == \
        ["Design", "Sketch"]


def test_quick_access_holds_the_five_file_actions(win):
    tips = [b.toolTip().split(" (")[0]
            for b in win.ribbon.quick.findChildren(QToolButton)]
    assert tips == ["New", "Open…", "Save", "Undo", "Redo"]


# ---- tab ⇄ page sync -----------------------------------------------------------

def test_pages_light_the_matching_tab(win, qapp):
    assert win.ribbon.tabs.currentIndex() == 0
    win._show_page(win._sketch_page)
    qapp.processEvents()
    assert win.ribbon.tabs.currentIndex() == 1
    assert win.ribbon.panels.currentIndex() == 1      # tool panel follows
    win._show_page(win.viewport)
    qapp.processEvents()
    assert win.ribbon.tabs.currentIndex() == 0
    assert win.ribbon.panels.currentIndex() == 0


def test_sketch_tab_opens_a_sketch_then_design_tab_leaves_it(win, qapp):
    win.ribbon.tabs.setCurrentIndex(1)                # like a real click
    qapp.processEvents()
    assert win.stack.currentWidget() is win._sketch_page
    win.ribbon.tabs.setCurrentIndex(0)
    qapp.processEvents()
    assert win.stack.currentWidget() is win.viewport


# ---- dispatch through the panels ------------------------------------------------

def test_design_buttons_dispatch(win, monkeypatch):
    fired = []
    for name in ("action_sweep", "action_loft", "action_hole",
                 "action_shell"):
        monkeypatch.setattr(win, name,
                            lambda checked=False, n=name: fired.append(n))
    for tip in ("Sweep — pipe", "Loft — blend", "Hole — drill", "Shell —"):
        _toolbutton(win, tip).click()
    assert fired == ["action_sweep", "action_loft", "action_hole",
                     "action_shell"]


def test_extrude_button_headline_stays_first_in_its_menu(win):
    b = _toolbutton(win, "Extrude")
    acts = b.menu().actions()
    assert acts and acts[0].text() == "E&xtrude profile… (X)"


def test_sketch_panel_tools_drive_the_canvas(win, qapp):
    win._show_page(win._sketch_page)
    qapp.processEvents()
    _toolbutton(win, "Rectangle").click()
    assert win.sketch._tool == "rect"
    _toolbutton(win, "Arc").click()
    assert win.sketch._tool == "arc"


def test_quick_save_prompts_for_a_path_when_unsaved(win, qapp, monkeypatch):
    calls = []

    def fake(*a, **k):
        calls.append(True)
        return "", ""
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(fake))
    win._unsaved = True
    _toolbutton(win, "Save").click()
    qapp.processEvents()
    assert calls                                  # dialog was raised


# ---- proof of life ---------------------------------------------------------------

def test_screenshot_proofs(win, qapp):
    import os
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    win._show_page(win.viewport)
    qapp.processEvents()
    assert win.grab().save(f"{out}/m39_design.png")
    win._show_page(win._sketch_page)
    qapp.processEvents()
    assert win.grab().save(f"{out}/m39_sketch.png")
