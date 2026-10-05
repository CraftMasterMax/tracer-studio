"""M42 — ribbon anatomy, 1:1 with the Fusion Design workspace.

Three things Fusion's top chrome has that ours lacked: the "Design ▾"
workspace chip (with the other workspaces listed but disabled), the
document title chip centered in the same row, and the Solid tab's exact
group layout — Sketch · Create · Pattern · Modify · Construct, with the
Pattern operations as three real buttons instead of one dropdown.
The ribbon title stays live: it follows the same name/dirty logic as
the window title.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (QApplication, QToolButton)         # noqa: E402

from tracer.ui.mainwindow import MainWindow                       # noqa: E402
from tracer.ui.renderer import SceneRenderer                      # noqa: E402
from tracer.ui.ribbon import RibbonBar                            # noqa: E402


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
    r.ctx.release()


def _toolbutton(win, tip_start):
    for b in win.findChildren(QToolButton):
        if b.toolTip().startswith(tip_start):
            return b
    raise AssertionError(f"no ribbon button {tip_start!r}")


# ---- workspace chip -----------------------------------------------------------

def test_workspace_chip_is_the_design_picker(win):
    chip = win.ribbon.workspace
    assert chip.text().startswith("Design")
    acts = chip.menu().actions()
    design = next(a for a in acts if a.text() == "Design")
    assert design.isCheckable() and design.isChecked()
    others = [a for a in acts if a.text() and a.text() != "Design"
              and not a.isSeparator()]
    assert {"Render", "Animation", "Simulation", "Manufacture",
            "Drawing", "Mesh"} <= {a.text() for a in others}
    assert all(not a.isEnabled() for a in others)


# ---- live title chip ----------------------------------------------------------

def test_ribbon_title_follows_doc_name_and_dirty_flag(win):
    win.new_document()
    win.doc.title = "Bracket"
    win._update_title()
    assert win.ribbon._title.text() == "Bracket"
    win.doc.dirty = True
    win._update_title()
    assert win.ribbon._title.text() == "Bracket \u2022"      # •
    win.doc.dirty = False
    win._update_title()
    assert win.ribbon._title.text() == "Bracket"


# ---- Solid-tab group layout ----------------------------------------------------

def test_design_panel_groups_follow_fusion_order(win):
    tips = []
    lay = win.ribbon.dl
    for i in range(lay.count()):
        it = lay.itemAt(i).widget()
        if isinstance(it, QToolButton):
            tip = it.toolTip().split(" \u2014 ")[0].split(" (")[0]
            tips.append(tip)
    want = ["New sketch", "Extrude", "Sweep", "Loft", "Hole",
            "Rectangular pattern", "Circular pattern", "Mirror",
            "Fillet", "Shell", "Construction plane"]
    assert tips == want


def test_pattern_operations_are_three_dispatching_buttons(win, monkeypatch):
    fired = []
    for name in ("action_linear_pattern", "action_circular_pattern",
                 "action_mirror"):
        monkeypatch.setattr(win, name,
                            lambda checked=False, n=name: fired.append(n))
    for tip in ("Rectangular pattern", "Circular pattern", "Mirror"):
        _toolbutton(win, tip).click()
    assert fired == ["action_linear_pattern", "action_circular_pattern",
                     "action_mirror"]


def test_pattern_buttons_carry_no_stale_dropdown(win):
    assert _toolbutton(win, "Rectangular pattern").menu() is None
    assert _toolbutton(win, "Circular pattern").menu() is None
    assert _toolbutton(win, "Mirror").menu() is None


def test_extrude_and_fillet_headlines_unchanged_for_m20(win):
    assert win.ribbon is not None
    extr = _toolbutton(win, "Extrude")
    assert extr.menu().actions()[0].text() == "E&xtrude profile… (X)"
    fil = _toolbutton(win, "Fillet")
    assert fil.menu() is not None


# ---- proof of life --------------------------------------------------------------

def test_screenshot_proof(win, qapp):
    import os
    win.new_document()
    win.doc.title = "Clone anatomy"
    win._update_title()
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m42_ribbon.png")
