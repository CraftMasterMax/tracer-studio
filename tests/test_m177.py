"""M177 rung 1 - THE ENTER THAT ENDS (FD5-L24: Enter commits AND ends).

Fusion's confirmation grammar for draw commands, the sibling of M176's
exit grammar: ENTER = commit AND end. Two mouths wore it wrong:

- Enter over a live type-in buffer committed the number and left the
  command ARMED. L24: the number is filed and the hand comes BACK to
  select - "commit AND end" - with one reconciliation: the END lands
  at the end of the ENTRY SEQUENCE. A staged rectangle's width-Enter
  keeps commanding (m90's two-number grammar, FD5-L29's mid-command
  W/H entry); the commit that CLEARS the lock is the one that ends.
  (M90's own stage stays inert: its commit-in-select-mode has no
  command to end.)
- Only the LINE honoured bare Enter (end chain, back to select); rect,
  circle, arc, ellipse, slot and poly fell THROUGH into Finish-Sketch
  - Enter mid-rectangle closed the whole sketch edit. Now every chain
  verb ends its COMMAND on Enter, and only a NEUTRAL hand (select)
  lets Enter reach finish() - the old Fusion law m113's key table
  pins stays standing, and its side effect is gated live: an unclosed
  sketch under select-mode Enter still walks into finish()'s "close
  your profile" warning.

Tab, the commit-AND-CONTINUE twin, landed as rung 2: over a live lock
Tab FILES the number and the command SURVIVES - a staged rect stays
mid-walk, even the final commit keeps the tool (the whole contrast
with Enter), and swallowing Tab while a lock lives saves the canvas
from focus traversals mid-gesture (Tab was unclaimed before: the
editor could hand itself the boot). FD5-L23's length+angle field
cycling is the [observed] sibling - deferred. L25's free-point chain
exception is rung 3: the line chain now ENDS when a segment LANDS on
existing geometry (an identity-reused Point, or a mint the autolink
BINDS to a curve) - the tool re-arms for a fresh start - while FREE
mints (empty space, origin, grid, an ortho leash that MOVED the
magnet's answer) keep the chain walking. Back-clicking the chain's
own free end is M176 R1's close law and stays untouched.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                              # noqa
from PySide6.QtTest import QTest                                   # noqa
from PySide6.QtWidgets import QApplication                         # noqa

from tracer.core.sketch.constraints import Distance, Radius        # noqa
from tracer.core.sketch.model import SketchModel                   # noqa
from tracer.ui.sketcheditor import SketchCanvas                    # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    c = SketchCanvas()
    c.set_model(SketchModel())
    c.resize(600, 400)
    c._snap_grid = False
    yield c
    c.deleteLater()


def _click(cv, x, y):
    sx, sy = cv.w2s(x, y).toPoint().x(), cv.w2s(x, y).toPoint().y()
    pt = QPoint(sx, sy)
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    QApplication.instance().processEvents()


def _key(cv, k):
    QTest.keyClick(cv, k)
    QApplication.instance().processEvents()


def _dims(cv):
    return [c for c in cv.model.sketch.constraints
            if isinstance(c, Distance)]


def test_enter_after_a_typed_number_commits_AND_ends_the_command(ed, qapp):
    m = ed.model
    ed.set_tool("line")
    _click(ed, 0, 0)
    _click(ed, 10, 0)
    QTest.keyClicks(ed, "7")
    _key(ed, Qt.Key_Return)                        # L24: COMMIT AND END
    dims = _dims(ed)
    assert len(dims) == 1 and dims[0].value == pytest.approx(7.0)
    assert ed._tool == "select"                    # the hand came BACK
    assert ed._line_start is None                  # no chain left armed
    assert ed._pending is None                     # lock filed, not live


def test_enter_on_an_unarmed_line_ends_the_command_keeping_the_work(ed):
    m = ed.model
    ed.set_tool("line")
    _click(ed, 0, 0)
    _click(ed, 5, 0)                               # one segment stands
    _key(ed, Qt.Key_Return)                        # Enter, no buffer
    assert len(m.sketch.lines) == 1                # work SURVIVES...
    assert ed._tool == "select"                    #  ...command ENDS
    assert _dims(ed) == []                         # no number invented


def test_enter_ends_the_rect_COMMAND_not_the_sketch(ed):
    ed.set_tool("rect")
    _click(ed, 0, 0)
    _click(ed, 12, 8)                              # rect drawn, armed
    _key(ed, Qt.Key_Return)                        # used to fall
    #                                               through into
    #                                               FINISH-SKETCH (and
    #                                               warn "no closed
    #                                               profile"!)
    assert ed._tool == "select"                    # the COMMAND ended...
    assert getattr(ed, "_warn_text", "") == ""                     #  ...finish() NEVER


def test_enter_ends_the_circle_and_poly_commands_too(ed):
    ed.set_tool("circle")
    _click(ed, 0, 0)
    _click(ed, 6, 0)                               # circle born, armed
    _key(ed, Qt.Key_Return)
    assert ed._tool == "select"
    assert getattr(ed, "_warn_text", "") == ""                     # no sketch finish
    ed.set_tool("poly")
    _key(ed, Qt.Key_5)                             # a pentagon
    _click(ed, 20, 0)                              # centre down
    _key(ed, Qt.Key_Return)                        # Enter ENDS the tool
    assert ed._tool == "select"                    #  (no poly born yet -
    assert getattr(ed, "_warn_text", "") == ""                     #   the aim survives?)


def test_select_mode_enter_still_reaches_finish_sketch(ed):
    m = ed.model
    ed.set_tool("line")
    _click(ed, 0, 0)
    _click(ed, 9, 0)
    _key(ed, Qt.Key_Escape)                        # Esc(1): M176 R3's
    assert ed._tool == "line"                      #  cascade drops the
    _key(ed, Qt.Key_Escape)                        #  lock; Esc(2) ENDS
    assert ed._tool == "select"                    #  the command
    _key(ed, Qt.Key_Return)                        # NOW Enter is the
    #                                               Finish-Sketch key:
    #                                               an open sketch walks
    #                                               into its warning
    assert "closed" in ed._warn_text.lower() or "profile" in ed._warn_text


def test_a_rect_walks_both_numbers_and_the_last_enter_ends(ed, qapp):
    m = ed.model
    ed.set_tool("rect")
    _click(ed, 0, 0)
    _click(ed, 6, 4)                               # width+height lock
    QTest.keyClicks(ed, "10")                      # live...
    _key(ed, Qt.Key_Return)                        # width commits BUT
    dims = _dims(ed)                               #  the staged rect
    assert len(dims) == 1 and dims[0].value == pytest.approx(10.0)
    assert ed._tool == "rect"                      #   STAYS in command
    assert ed._pending is not None                 #  height lock live
    QTest.keyClicks(ed, "5")
    _key(ed, Qt.Key_Return)                        # the LAST commit
    dims = _dims(ed)                               #  ENDS the command
    assert len(dims) == 2
    assert ed._pending is None
    assert ed._tool == "select"


# ---- RUNG 2: TAB, the commit-AND-CONTINUE twin (FD5-L24) ------------------

def _type(ed, text):
    QTest.keyClicks(ed, text)                      # digits into the chip


def test_tab_files_the_number_and_the_command_lives(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0, 0)
    _click(ed, 10, 0)
    _type(ed, "7")
    _key(ed, Qt.Key_Tab)                           # COMMIT...
    dims = _dims(ed)
    assert len(dims) == 1 and dims[0].value == pytest.approx(7.0)
    assert ed._pending is None and ed._num_buf == ""   # lock filed...
    assert ed._tool == "line"                      #  ...command LIVES
    assert ed._line_start is not None              #   chain still armed


def test_tab_then_click_keeps_the_tool_armed_with_the_typed_value(ed, qapp):
    # L24's OWN words: "Tab then click = keep the tool armed with the
    # typed value." The chain walks on off the FILED segment.
    m = ed.model
    ed.set_tool("line")
    _click(ed, 0, 0)
    _click(ed, 10, 0)
    _type(ed, "7")
    _key(ed, Qt.Key_Tab)                           # file the 7
    _click(ed, 7, 5)                               # then CLICK: chain on
    assert len(m.sketch.lines) == 2
    assert m.sketch.lines[1].a is m.sketch.lines[0].b   # shared anchor
    assert ed._tool == "line"                      #  still commanding
    assert ed._pending is not None                 #  fresh lock live


def test_tab_files_a_rect_width_and_stays_for_the_height(ed, qapp):
    m = ed.model
    ed.set_tool("rect")
    _click(ed, 0, 0)
    _click(ed, 6, 4)
    _type(ed, "10")
    _key(ed, Qt.Key_Tab)                           # width files, STAYS
    dims = _dims(ed)
    assert len(dims) == 1 and dims[0].value == pytest.approx(10.0)
    assert ed._tool == "rect"                      #   rect commanding
    assert ed._pending is not None                 #  height lock live
    _type(ed, "5")
    _key(ed, Qt.Key_Tab)                           # EVEN THE FINAL Tab
    dims = _dims(ed)                               #  does not end: that
    assert len(dims) == 2                          #  is Enter's law,
    assert ed._pending is None                     #   not Tab's
    assert ed._tool == "rect"


def test_tab_on_an_empty_lock_is_a_lock_preserving_no_op(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0, 0)
    _click(ed, 10, 0)                              # lock armed, empty
    _key(ed, Qt.Key_Tab)
    assert ed._pending is not None                 # lock SURVIVES...
    assert _dims(ed) == []                         #  nothing filed...
    assert ed._tool == "line"                      #   nothing ended
    _type(ed, "4")                                 # the mouth STILL
    assert ed._num_buf == "4"                      #  owns its digits


def test_tab_honors_a_circle_diameter_and_stays_armed(ed, qapp):
    m = ed.model
    ed.set_tool("circle")
    _click(ed, 0, 0)
    _click(ed, 5, 0)
    _type(ed, "6")
    _key(ed, Qt.Key_Tab)
    rds = [c for c in m.sketch.constraints if isinstance(c, Radius)]
    assert len(rds) == 1 and rds[0].value == pytest.approx(3.0)
    assert m.sketch.circles[0].r == pytest.approx(3.0, rel=1e-6)
    assert ed._pending is None
    assert ed._tool == "circle"                    # continue, not exit


# ---- RUNG 3: L25 - THE FREE-POINT CHAIN EXCEPTION --------------------------
# "Clicking empty space chains from the last endpoint; ending ON AN EXISTING
# curve/point ENDS the chain (the tool re-arms for a new start)." The magnet
# hands over the truth for free: an identity-reused Point IS an existing
# point, and a drop whose autolink BINDS the mint (on-entity, midpoint,
# intersection...) lands on an existing curve. Empty space, the origin and
# the grid mint NOTHING-bound - free. The ortho leash that MOVES the magnet's
# answer mints a fresh end too: nothing exists where the leash put it.


def test_landing_on_an_existing_point_ends_the_chain(ed, qapp):
    m = ed.model
    ed.set_tool("rect")
    _click(ed, 0, 0)
    _click(ed, 10, 6)                    # a rect STANDS: corners EXIST
    ed.set_tool("line")
    _click(ed, 16, 10)                   # a FREE start (chain armed)
    _click(ed, 10, 6)                    # the segment LANDS on a corner
    assert len(m.sketch.lines) == 5      #  the segment is DRAWN...
    assert ed._tool == "line"            #  ...the TOOL lives...
    assert ed._line_start is None        #   ...the CHAIN ended
    assert not ed._chain_armed()         #    the check went OUT
    assert ed._pending is not None       #     the M90 lock still owns it


def test_a_free_end_keeps_the_chain_walking(ed, qapp):
    m = ed.model
    ed.set_tool("line")
    _click(ed, 2, 2)
    _click(ed, 8, 2)                     # a FREE commit...
    assert ed._line_start is not None    #  ...the chain CONTINUES
    _click(ed, 8, 9)                     # another FREE commit
    assert len(m.sketch.lines) == 2
    assert ed._line_start is not None    #  still walking
    assert ed._chain_armed()             #   the check stays LIT


def test_the_next_click_after_a_landing_starts_fresh(ed, qapp):
    m = ed.model
    ed.set_tool("rect")
    _click(ed, 0, 0)
    _click(ed, 10, 6)
    ed.set_tool("line")
    _click(ed, 16, 10)
    _click(ed, 10, 6)                    # lands: chain ENDED
    _click(ed, 16, 16)                   # the NEXT click...
    assert len(m.sketch.lines) == 5      #  ...is a FRESH START...
    start = ed._line_start
    assert start is not None             #   ...the tool RE-ARMED
    _click(ed, 22, 20)                   # and the new chain WALKS
    assert len(m.sketch.lines) == 6
    assert m.sketch.lines[5].a is start  #  off the NEW anchor, not the
    #                                     rect corner the last one died on


def test_closing_back_onto_the_chains_own_start_lands_too(ed, qapp):
    m = ed.model
    ed.set_tool("line")
    _click(ed, 2, 2)                     # A: free
    _click(ed, 8, 2)                     # B: free - chain walks
    _click(ed, 2, 6)                     # C: free - chain walks
    _click(ed, 2, 2)                     # back onto A: by now EXISTING
    assert len(m.sketch.lines) == 3      #  the closing segment DREW...
    assert ed._line_start is None        #   ...and the chain LANDED
    assert ed._tool == "line"            #    tool RE-ARMS for a start


def test_back_click_on_the_free_end_still_closes_untouched(ed, qapp):
    m = ed.model
    ed.set_tool("line")
    _click(ed, 0, 0)
    _click(ed, 9, 0)                     # free commit, chain walks
    end = ed._line_start
    _click(ed, 9, 0)                     # back-click ON the free end
    assert len(m.sketch.lines) == 1      #  NO zero-length segment...
    assert ed._line_start is None        #   M176 R1's CLOSE law...
    assert ed._tool == "line"            #    ...UNTOUCHED by L25
    assert end is m.sketch.lines[0].b    #     (the identity snap proved
    #                                     it WAS the free end)


def test_the_ortho_leash_mint_rides_free_and_keeps_chaining(ed, qapp):
    m = ed.model
    ed.set_tool("rect")
    _click(ed, 0, 0)
    _click(ed, 20, 10)                   # a rect STANDS
    ed.set_tool("line")
    _click(ed, 6, 5)                     # free start INSIDE... far enough
    q = ed.w2s(20, 10).toPoint()         # shift-click ON the far corner:
    QTest.mousePress(ed, Qt.LeftButton, Qt.ShiftModifier, q)      # magnet
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.ShiftModifier, q)    # says
    qapp.processEvents()                 # EXISTING - the leash says NO
    assert len(m.sketch.lines) == 5      #  the leashed segment DREW...
    assert ed._line_start is not None    #   to a FRESH minted end...
    ln = m.sketch.lines[4]
    assert ln.b.y == pytest.approx(5.0)  #    (20,5), NOT the corner:
    assert ln.b.x == pytest.approx(20.0) #     nothing exists where the
    #                                     leash put it - the chain rides on
