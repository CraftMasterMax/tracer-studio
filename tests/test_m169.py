"""M169 rung 1 — SURFACE HONESTY (every surface speaks what T now is).

M168 R3 moved T from a one-shot corner act to the trim TOOL, and three
surfaces kept lying about it: the HUD answered "Tool: ?" while the tool was
armed (its dict never learned the new member), the palette row still sold
"T" as "Trim corner (two lines)" - so the palette's T and the canvas's T
did different things under one badge - and the ribbon tooltip cited "/",
a key dead since the last migration. Rung 1's law: a key means ONE thing
everywhere.

  T is the trim TOOL in the palette (retargeted row, key KEPT - m113 owns
  the membership), the ribbon (the button picks the tool, Fusion-style),
  the HUD (names it), and the claim set (still swallows the letter).
  The corner act survives behind honest doors: the canvas context menu
  (built in _build_menu - m164's testable split) and direct act_trim().
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QToolButton                # noqa: E402

from tracer.core.sketch.model import SketchModel                       # noqa: E402
from tracer.ui.commands import SKETCH_KEYS, _sketch_runner             # noqa: E402
from tracer.ui.mainwindow import MainWindow                            # noqa: E402
from tracer.ui.renderer import SceneRenderer                           # noqa: E402
from tracer.ui.sketcheditor import TOOL_HINTS, _CLAIM_TEXT,            \
    SketchCanvas                                                       # noqa: E402


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
    r.close()


# ---- what the surfaces SAY ----------------------------------------------------

def test_hud_speaks_the_trim_tool():
    """No more 'Tool: ?' while trim is armed - and the select hint no
    longer sells T as a constraint key."""
    assert "trim" in TOOL_HINTS
    assert TOOL_HINTS["trim"].startswith("Trim")
    assert "Q/T" not in TOOL_HINTS["select"]           # the old citation died


def test_palette_T_row_names_the_tool():
    """One key, one meaning: the T row runs the TOOL, not the corner act."""
    label, target = SKETCH_KEYS["T"]
    assert target == "tool:trim_mode"
    assert "Trim" in label and "corner" not in label.lower()
    assert not any(t == "tool:trim" for _l, t in SKETCH_KEYS.values())


def test_palette_row_count_is_kept():
    """Retarget, never inflate: the table is exactly as wide as before."""
    assert len(SKETCH_KEYS) == 29                    # M169 R1 census


def test_canvas_still_claims_lowercase_t():
    """The claim set is key-derived (not target-derived): the retarget
    must not hand the letter T back to the global shortcut layer."""
    assert "t" in _CLAIM_TEXT


# ---- what the surfaces DO ------------------------------------------------------

def test_running_the_palette_row_arms_the_tool(win):
    """The palette command and the canvas key converge on the SAME state."""
    _sketch_runner(win, "tool:trim_mode")()
    assert win.sketch._tool == "trim"
    win.sketch.set_tool("select")


def test_toolbar_button_picks_the_trim_tool(win):
    """Fusion's ribbon Trim button CHOOSES the tool; the tooltip cites the
    live key and no longer the '/' era (the 'Trim' prefix is m45's order
    pin and stays)."""
    btns = [b for b in win.ribbon.sketch_panel.findChildren(QToolButton)
            if b.toolTip().startswith("Trim")]
    assert len(btns) == 1, [b.toolTip() for b in btns]
    tip = btns[0].toolTip()
    assert "/" not in tip and "T" in tip
    btns[0].click()
    assert win.sketch._tool == "trim"


def test_the_corner_act_still_lives_in_the_menu(qapp):
    """The act lost its key and its toolbar door but kept the right-click
    on a two-line selection: _build_menu still carries the corner verb."""
    cv = SketchCanvas()
    cv.set_model(SketchModel())
    cv.resize(600, 400)
    m = cv.model
    LA = m.add_line(m.point(0, 0), m.point(10, 0.3))
    LB = m.add_line(m.point(9.6, 6), m.point(10.1, 0.1))
    cv._sel = [LA, LB]
    act = [a for a in cv._build_menu().actions()
           if a.text() == "Trim / extend to corner"]
    assert len(act) == 1
    act[0].trigger()                                   # the real door, fired
    qapp.processEvents()
    assert any(pa is pb for pa in (LA.a, LA.b) for pb in (LB.a, LB.b))
    assert len(m.sketch.points) == 3                   # orphan dropped
    cv.deleteLater()
