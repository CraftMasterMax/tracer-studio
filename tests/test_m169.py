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

M169 rung 2 adds THE SCRIBE KERNEL: trim_stroke(model, touches) eats a whole
gesture in stroke order - per touch the CONTAINING piece falls (trim_piece
is the only mutation), and ON-cut touches, Points and already-consumed
entities skip SILENTLY (a stroke is one verb and never warns mid-word).
The gap-rect of m28 has one PURE GAP corner - the scribe trims OVERHANGS,
it does not extend - so the clean-stroke gate rides an all-overhang rect;
the gap corner keeps m28's close-corner story.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QToolButton                # noqa: E402

from tracer.core.sketch.model import SketchModel, model_to_dict        # noqa: E402
from tracer.core.sketch.trim import trim_stroke                        # noqa: E402
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


# ---- M169 rung 2: THE SCRIBE KERNEL (trim_stroke) -----------------------------


def _scribble_rect():
    """Four strokes of a hand-drawn rectangle - every corner a pure
    OVERHANG (crossings at the exact corners (0,0), (40,0), (40,20),
    (0,20)); m28's _gap_rect keeps a gap corner, which is EXTEND work."""
    m = SketchModel()
    L0 = m.add_line(m.point(-0.3, 0.0), m.point(40.4, 0.0))
    L1 = m.add_line(m.point(40.0, -0.4), m.point(40.0, 20.4))
    L2 = m.add_line(m.point(40.3, 20.0), m.point(-0.4, 20.0))
    L3 = m.add_line(m.point(0.0, 20.3), m.point(0.0, -0.4))
    return m, [L0, L1, L2, L3]


def test_the_scribe_cleans_the_scribble_rect():
    """The scribe eats all EIGHT overshoot pieces in two circuits - the
    second circuit names the LIVE survivors, exactly what the canvas
    re-resolves between moves - and the loop CLOSES by identity."""
    m, (L0, L1, L2, L3) = _scribble_rect()
    corners = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0))

    def at_corner(p):                     # seams are COMPUTED crossings:
        return any(abs(p.x - cx) < 1e-6   #  compare with tolerance, never
                   and abs(p.y - cy) < 1e-6 for cx, cy in corners)
    first = trim_stroke(m, [(L0, -0.15, 0.0), (L1, 40.0, -0.3),
                            (L2, 40.15, 20.0), (L3, 0.0, 20.15)])
    assert len(first) == 4
    stubs = [e for e in m.sketch.lines if at_corner(e.a) ^ at_corner(e.b)]
    assert len(stubs) == 4                             # the far overshoots
    second = trim_stroke(m, [(e, (e.a.x + e.b.x) / 2, (e.a.y + e.b.y) / 2)
                             for e in stubs])
    assert len(second) == 4
    assert len(m.sketch.lines) == 4
    loops, warns = m.to_loops()
    assert len(loops) == 1 and not warns
    assert 799.0 < loops[0]["area"] < 801.0
    for cx, cy in ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)):
        seam = [p for p in m.sketch.points
                if abs(p.x - cx) < 1e-6 and abs(p.y - cy) < 1e-6]
        assert len(seam) == 1                          # ONE Point per corner
        assert len([e for e in m.sketch.lines
                    if seam[0] in (e.a, e.b)]) == 2    # it serves both sides


def test_on_cut_touches_skip_silently():
    """A stroke across nothing but crossings is a stroke that took nothing:
    no fall, no warning, and the model never learns it was considered."""
    m = SketchModel()
    l1 = m.add_line(m.point(0, 0), m.point(40, 40))
    l2 = m.add_line(m.point(0, 40), m.point(40, 0))
    before = model_to_dict(m)
    assert trim_stroke(m, [(l1, 20.0, 20.0), (l2, 20.0, 20.0)]) == []
    assert model_to_dict(m) == before


def test_dead_entities_and_points_skip_silently():
    """The first touch consumes; the stale echo names nothing - and a Point
    was never trimmable. The X under the strokes keeps every byte."""
    m = SketchModel()
    l1 = m.add_line(m.point(0, 0), m.point(40, 40))
    l2 = m.add_line(m.point(0, 40), m.point(40, 0))
    S = m.add_line(m.point(-5, 5), m.point(-5, -5))
    P = m.point(99, 99)
    x_bytes = model_to_dict(m)
    fallen = trim_stroke(m, [(S, -5.0, 0.0), (S, -5.0, 1.0), (P, 99.0, 99.0)])
    assert fallen == [S]                               # the echo took nothing
    assert len(m.sketch.lines) == 2
    cir = m.add_circle(m.point(10, 10), 2.0)
    assert trim_stroke(m, [(cir, 12.0, 10.0), (cir, 8.0, 10.0)]) == [cir]
    assert not m.sketch.circles
    after = model_to_dict(m)
    assert after["lines"] == x_bytes["lines"][:2]      # the X is byte-still


def test_order_matters_the_stale_half_touch_is_hushed():
    """First touch CONSUMES the original (split identity): a later touch
    naming the dead object skips - the live survivor is another name."""
    m = SketchModel()
    a = m.point(0, 0)
    m.add_line(a, m.point(40, 40))
    m.add_line(m.point(0, 40), m.point(40, 0))
    l1 = m.sketch.lines[0]
    fallen = trim_stroke(m, [(l1, 30.0, 30.0), (l1, 10.0, 10.0)])
    assert len(fallen) == 1                            # the echo hushed
    assert l1 not in m.sketch.lines                    # consumed by the cut
    assert len(m.sketch.lines) == 2                    # survivor + l2


def test_the_survivor_touched_again_loses_the_rest():
    """R3's promise at kernel level: resolving live each touch means the
    same geometric line touched twice loses BOTH pieces - the survivor
    crossed only at its own end is uncrossed, so it goes whole."""
    m = SketchModel()
    a = m.point(0, 0)
    m.add_line(a, m.point(40, 40))
    m.add_line(m.point(0, 40), m.point(40, 0))
    l1 = m.sketch.lines[0]
    trim_stroke(m, [(l1, 30.0, 30.0)])                 # the far piece falls
    survivor = [e for e in m.sketch.lines if e.a is a][0]
    fallen = trim_stroke(m, [(survivor, 10.0, 10.0)])
    assert len(fallen) == 1 and fallen[0] is survivor
    assert len(m.sketch.lines) == 1                    # only l2 remains


def test_neighbours_keep_their_bytes():
    """A stroke cuts what it touched - nothing else moves an atom."""
    m = SketchModel()
    l1 = m.add_line(m.point(0, 0), m.point(40, 40))
    l2 = m.add_line(m.point(0, 40), m.point(40, 0))
    cir = m.add_circle(m.point(-10, -10), 3.0)
    before = {
        "l2": (l2.a.x, l2.a.y, l2.b.x, l2.b.y),
        "cir": (cir.c.x, cir.c.y, cir.r),
        "dict": model_to_dict(m),
    }
    trim_stroke(m, [(l1, 30.0, 30.0)])
    assert (l2.a.x, l2.a.y, l2.b.x, l2.b.y) == before["l2"]
    assert (cir.c.x, cir.c.y, cir.r) == before["cir"]
    after = model_to_dict(m)
    for key in ("circles",):
        assert after[key] == before["dict"][key]


def test_the_scribe_is_pure_kernel():
    """No Qt in the scribe: the canvas owns gestures, history and paint -
    the kernel only knows pieces and silence."""
    import inspect

    import tracer.core.sketch.trim as tk
    assert "trim_stroke" in dir(tk)
    src = inspect.getsource(tk)
    assert "PySide6" not in src and "QtCore" not in src
