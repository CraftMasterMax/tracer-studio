"""M46 — app launcher menu: the mark at the ribbon's far-left corner
opens Fusion's primary file surface (New/Open/Save · Import · Export ▸ ·
Keyboard shortcuts · Exit), sharing the menu bar's exact QActions."""
import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QToolButton                 # noqa: E402

from tracer.ui.mainwindow import MainWindow                              # noqa: E402
from tracer.ui.renderer import SceneRenderer                             # noqa: E402


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
    w.new_document()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


def _launcher(w):
    return w.ribbon.findChild(QToolButton, "appLauncher")


def _top_texts(menu):
    return [a.text().replace("&", "") for a in menu.actions()
            if not a.isSeparator()]


# ---- the button -----------------------------------------------------------------

def test_launcher_button_leads_the_ribbon(win):
    b = _launcher(win)
    assert b is not None and not b.icon().isNull()
    assert b.mapTo(win.ribbon, b.geometry().topLeft()).x() < \
        win.ribbon.quick.geometry().left()     # left of quick-access
    assert "menu" in b.toolTip().lower()


def test_launcher_menu_is_shared_not_duplicated(win):
    menu = _launcher(win).menu()
    assert menu is not None and menu.objectName() == "launcherMenu"
    tops = {a.text().replace("&", ""): a
            for a in menu.actions() if not a.isSeparator()}
    assert tops["New"] is win.act_new          # identical QAction objects
    assert tops["Open…"] is win.act_open
    assert tops["Exit"] is win.act_exit
    assert not win.act_new.shortcut().isEmpty()   # shortcuts ride along


def test_launcher_menu_layout(win):
    menu = _launcher(win).menu()
    assert _top_texts(menu) == [
        "New", "Open…", "Save", "Save As…", "Import body…", "Export",
        "Keyboard shortcuts", "Exit"]


def test_export_submenu_carries_every_format(win):
    menu = _launcher(win).menu()
    exp = next(a.menu() for a in menu.actions()
               if a.text().replace("&", "") == "Export")
    texts = _top_texts(exp)
    for want in ("STL", "3MF", "OBJ", "PLY"):
        assert want in texts, texts
    assert "Export STEP (.step)…" in texts
    assert "Export render (PNG)…" in texts


# ---- dispatch ---------------------------------------------------------------------

def test_new_from_the_launcher(win, monkeypatch):
    fired = []
    monkeypatch.setattr(win, "action_new",
                        lambda *a, **k: fired.append(True))
    tops = {a.text().replace("&", ""): a
            for a in _launcher(win).menu().actions() if not a.isSeparator()}
    tops["New"].trigger()
    assert fired


def test_keyboard_shortcuts_item_jumps_the_rail(win):
    tops = {a.text().replace("&", ""): a
            for a in _launcher(win).menu().actions() if not a.isSeparator()}
    tops["Keyboard shortcuts"].trigger()
    assert win.rail.tabText(win.rail.currentIndex()) == "Shortcuts"


def test_file_menu_unchanged_for_old_contracts(win):
    """The M15 File-menu contract survives the refactor untouched."""
    texts = _top_texts(win.menuBar().actions()[0].menu())
    assert texts[:4] == ["New", "Open…", "Save", "Save As…"]
    assert "Export mesh" in texts and "Exit" in texts


# ---- proof of life ------------------------------------------------------------------

def test_screenshot_proof(win, qapp):
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m46_launcher.png")
    menu = _launcher(win).menu()
    b = _launcher(win)
    menu.popup(b.mapToGlobal(b.geometry().bottomLeft()))
    qapp.processEvents()
    assert menu.grab().save(f"{out}/m46_launcher_menu.png")
    menu.hide()
