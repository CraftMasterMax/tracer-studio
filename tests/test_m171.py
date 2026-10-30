"""M171 rung 1 - THE ARROW KEYS: empty hands SCROLL the view.

The key grammar claims ~30 verbs and not ONE arrow: selected geometry
never nudged, empty-handed keys never scrolled. Fusion answers both;
today the view starts answering. The law of this rung: empty selection +
an arrow = the VIEW steps by a screen-CONSTANT 10 px of world (Shift
x5), the sketch and the history byte-identical - a scroll is not an
edit and must not leave an undo row. While the M90 type-in is armed the
arrows STILL scroll and neither eat nor lose the digit buffer (today any
other key drops the pending - arrows must not). A non-empty selection
in SELECT mode used to PARK the arrows - rung 2 (below) took them.

Arrows are NON-PRINTABLE: like F2 before them they stay out of
SKETCH_KEYS - a claim there would be inert dead code.

Rung 2 takes the parked keys: SELECT mode + a selection + an arrow NUDGES
every movable Point of the selection (the crowd's grab + dof law) by a
screen-constant 5 px of world (Shift x5), then solves with the nudged
points pinned - chains flex like a drag, a welded corner carries every
rider, and a locked scene pays NOTHING: no undo row is born for a no-op.
One press, one undo step. Outside SELECT mode the arrows stay PARKED.

Rung 3: Ctrl+D photocopies the selection WITHOUT a hand - the Ctrl-drag's
kernel (copy_geometry, identity survives, copies arrive FREE and BORN
FREE), landing one nudge step beside the source with the pick re-homed
to the copy for exactly one undo row. Empty hands and other tools pay
the key nothing, and it is never the plain D's dim.
"""
import math
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, QPoint, Qt              # noqa
from PySide6.QtGui import QMouseEvent                                # noqa
from PySide6.QtTest import QTest                                    # noqa
from PySide6.QtWidgets import QApplication                          # noqa

from tracer.core.sketch.constraints import Distance, Fixed          # noqa
from tracer.core.sketch.model import SketchModel                    # noqa
from tracer.ui.sketcheditor import SketchCanvas                     # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    c = SketchCanvas()
    c.set_model(SketchModel())        # empty once: scale 4 / centre 0 stay
    c.resize(600, 400)
    c._snap_grid = False
    yield c
    c.deleteLater()


def _scr(x, y):
    return QPoint(int(round(300 + 4.0 * x)), int(round(200 - 4.0 * y)))


def _key(ed, k, mods=Qt.NoModifier):
    QTest.keyClick(ed, k, mods)


def _click(ed, x, y):
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(x, y))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(x, y))


def _move(ed, x, y):
    #  QTest.mouseMove cannot hold button state (m37 law) - send a real
    p = QPointF(300.0 + 4.0 * x, 200.0 - 4.0 * y)                  #  event
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))


def _state(m):
    sk = m.sketch
    return (len(sk.points), len(sk.lines), len(sk.constraints),
            [(l.a.x, l.a.y, l.b.x, l.b.y) for l in sk.lines])


def test_empty_handed_arrows_scroll_the_view(ed):
    m = ed.model
    a = m.point(-5, -5); b = m.point(5, 5)
    m.add_line(a, b)
    ed._solve()
    st = _state(m)
    n0 = len(ed._hist)
    c = ed._center.copy()
    _key(ed, Qt.Key_Left)                          # the VIEW shows more
    assert ed._center[0] == pytest.approx(c[0] - 2.5)   #  left: 10px/4
    _key(ed, Qt.Key_Right)                         #   Right brings it back
    assert ed._center[0] == pytest.approx(c[0])
    _key(ed, Qt.Key_Up)
    assert ed._center[1] == pytest.approx(c[1] + 2.5)   #  world y is UP
    _key(ed, Qt.Key_Down)
    assert ed._center[1] == pytest.approx(c[1])
    assert _state(m) == st                         # a scroll is NOT edit...
    assert len(ed._hist) == n0                     #  ...and pays no undo


def test_shift_multiplies_the_step(ed):
    c = ed._center.copy()
    _key(ed, Qt.Key_Right, Qt.ShiftModifier)
    assert ed._center[0] == pytest.approx(c[0] + 12.5)
    c = ed._center.copy()
    _key(ed, Qt.Key_Up, Qt.ShiftModifier)
    assert ed._center[1] == pytest.approx(c[1] + 12.5)


def test_scroll_survives_the_digit_gate(ed):
    m = ed.model
    _key(ed, Qt.Key_R)                             # R arms the rect tool
    assert ed._tool == "rect"
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(-10, 8))
    QTest.mouseMove(ed, _scr(2, -2))               # a rect drag commits...
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(2, -2))
    assert ed._pending is not None                 #  ...and arms type-in
    QTest.keyClick(ed, Qt.Key_5)                   # "5" rides the buffer
    assert ed._num_buf == "5"
    c = ed._center.copy()
    _key(ed, Qt.Key_Left)                          # an arrow scrolls...
    assert ed._center[0] == pytest.approx(c[0] - 10.0 / ed._scale)
    assert ed._num_buf == "5"                      #   ...keeps the digit
    assert ed._pending is not None                 #   ...and the pending


def test_a_non_select_tool_parks_the_arrows(ed):
    m = ed.model
    sk = m.sketch
    p = sk.point(30, 30)
    ed._solve()
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(30, 30))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(30, 30))
    assert ed._sel == [p]
    _key(ed, Qt.Key_T)                                 # trim takes the
    assert ed._tool == "trim" and ed._sel == [p]       #  hands but not the
    c = ed._center.copy()                              #   selection
    n0 = len(ed._hist)
    _key(ed, Qt.Key_Right)                             # NUDGE is SELECT
    assert ed._center[0] == pytest.approx(c[0])        #  mode only; the
    assert (p.x, p.y) == (30.0, 30.0)                  #  arrows park with
    assert len(ed._hist) == n0                         #  someone else's tool


def test_trim_mode_empty_hands_scroll_too(ed):
    _key(ed, Qt.Key_Escape)                        # lay down the trim
    _key(ed, Qt.Key_T)                             #  tool, empty select
    assert ed._tool == "trim"
    c = ed._center.copy()
    n0 = len(ed._hist)
    _key(ed, Qt.Key_Down)
    assert ed._center[1] == pytest.approx(c[1] - 2.5)
    assert ed._tool == "trim"                      # scroll keeps the tool
    assert len(ed._hist) == n0


# ---- RUNG 2: the NUDGE - a selection steps through the solver -----------

def test_a_lone_point_steps_exactly_one_world_per_press(ed):
    m = ed.model
    p = m.point(20, 15)
    ed._solve()
    _click(ed, 20, 15)
    assert ed._sel == [p]
    n0 = len(ed._hist)
    _key(ed, Qt.Key_Right)                         # 5 px of world at scale 4
    assert p.x == pytest.approx(21.25) and p.y == pytest.approx(15.0)
    assert len(ed._hist) == n0 + 1                 # one press, one undo step
    _key(ed, Qt.Key_Up)
    assert p.x == pytest.approx(21.25) and p.y == pytest.approx(16.25)
    _key(ed, Qt.Key_Right, Qt.ShiftModifier)       # Shift x5: 6.25 mm
    assert p.x == pytest.approx(27.5)
    assert len(ed._hist) == n0 + 3


def test_a_line_body_nudge_moves_both_ends_rigidly(ed):
    m = ed.model
    a = m.point(0, 0); b = m.point(8, 0)
    m.add_line(a, b)
    ln = m.sketch.lines[0]
    ed._solve()
    _click(ed, 4, 0)                               # press the BODY, no end
    assert ed._sel == [ln]
    n0 = len(ed._hist)
    _key(ed, Qt.Key_Down, Qt.ShiftModifier)
    assert (a.x, a.y) == pytest.approx((0.0, -6.25))
    assert (b.x, b.y) == pytest.approx((8.0, -6.25))
    assert math.hypot(b.x - a.x, b.y - a.y) == pytest.approx(8.0)
    assert len(ed._hist) == n0 + 1                 # the body pays ONE push


def test_a_welded_corner_carries_every_rider(ed):
    m = ed.model
    sk = m.sketch
    a = m.point(0, 0); c = m.point(5, 5); b = m.point(10, 0)
    m.add_line(a, c)
    m.add_line(c, b)                               # ONE Point serves both
    ed._solve()
    assert sk.lines[0].b is c and sk.lines[1].a is c
    _click(ed, 5, 5)
    assert ed._sel == [c]
    n0 = len(ed._hist)
    _key(ed, Qt.Key_Left)
    assert sk.lines[0].b.x == pytest.approx(3.75)  # both lines rode ONE
    assert sk.lines[1].a.x == pytest.approx(3.75)  #  corner step: identity
    assert sk.lines[0].b is sk.lines[1].a          #  is still ONE Point
    assert len(ed._hist) == n0 + 1


def test_a_locked_scene_refuses_with_zero_ambient(ed):
    m = ed.model
    a = m.point(2, 6); b = m.point(8, 6)
    m.add_line(a, b)
    ln = m.sketch.lines[0]
    m.toggle(Fixed, (a,))
    m.toggle(Fixed, (b,))
    ed._solve()
    assert ed._dof_of(a) == 0 and ed._dof_of(b) == 0
    _click(ed, 5, 6)
    assert ed._sel == [ln]
    c = ed._center.copy()
    n0 = len(ed._hist)
    _key(ed, Qt.Key_Up)
    assert (a.x, a.y, b.x, b.y) == pytest.approx((2.0, 6.0, 8.0, 6.0))
    assert len(ed._hist) == n0                     # a no-op pays NO undo row
    assert ed._center[1] == pytest.approx(c[1])    #  ...and is not a scroll


def test_the_chain_flexes_and_the_distance_holds(ed):
    m = ed.model
    a = m.point(0, 0); b = m.point(10, 0)
    m.add_line(a, b)
    m.constrain(Distance(a, b, 10.0))
    ed._solve()
    _click(ed, 10, 0)
    assert ed._sel == [b]
    n0 = len(ed._hist)
    _key(ed, Qt.Key_Right)
    assert b.x == pytest.approx(11.25)             # the HAND stays (pinned)
    assert abs(math.hypot(b.x - a.x, b.y - a.y) - 10.0) < 1e-6
    assert a.x == pytest.approx(1.25)              # chain RODE toward b
    assert len(ed._hist) == n0 + 1


def test_auto_repeat_is_two_steps_and_one_undo_is_one_step(ed):
    m = ed.model
    p = m.point(12, -4)
    ed._solve()
    _click(ed, 12, -4)
    n0 = len(ed._hist)
    _key(ed, Qt.Key_Right)
    _key(ed, Qt.Key_Right)                         # auto-repeat: TWO presses
    assert m.sketch.points[0].x == pytest.approx(14.5)   # TWO undo steps
    assert len(ed._hist) == n0 + 2
    assert ed.undo_op()
    assert m.sketch.points[0].x == pytest.approx(13.25)  # one undo = ONE step
    assert len(ed._hist) == n0 + 1


def test_a_dragged_point_can_be_dragged_again(ed):
    # The MOUSE twin of the auto-repeat law: a pinned solve truthfully
    # reports the pinned point had 0 dof - but that witness is about the
    # GESTURE, not the geometry. The release now settles clean, so the
    # next press finds the point mobile again (broken since M167's dof
    # filter until rung 2 asked for it; the expose-and-fix is the ledger
    # way).
    m = ed.model
    p = m.point(20, 15)
    ed._solve()
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(20, 15))
    _move(ed, 22, 15)
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(22, 15))
    assert p.x == pytest.approx(22.0)              # drag 1 lands
    assert ed._dof_of(p) == 2                      #  the witness speaks
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(22, 15))
    assert ed._drag_pt is not None                 # press 2 GRABS again
    _move(ed, 24, 15)
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(24, 15))
    assert p.x == pytest.approx(24.0)              # drag 2 lands too


# ---- RUNG 3: CTRL+D - the photocopy WITHOUT a hand -----------------------

def _clickc(ed, x, y):                             # Ctrl+click: a stranger
    QTest.mousePress(ed, Qt.LeftButton, Qt.ControlModifier, _scr(x, y))     # joins
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.ControlModifier, _scr(x, y))


def _ctrl_d(ed):
    QTest.keyClick(ed, Qt.Key_D, Qt.ControlModifier)


def test_ctrl_d_photocopies_a_point_beside_its_source(ed):
    m = ed.model
    p = m.point(4, 4)
    ed._solve()
    _click(ed, 4, 4)
    n0 = len(ed._hist)
    _ctrl_d(ed)
    sk = m.sketch
    assert len(sk.points) == 2                     # a twin is born...
    q = [pt for pt in sk.points if pt is not p][0]
    assert (p.x, p.y) == (4.0, 4.0)                #  the source never rode
    assert (q.x, q.y) == pytest.approx((5.25, 4.0))   # ONE nudge step over
    assert ed._sel == [q]                          # the pick re-homes
    assert len(ed._hist) == n0 + 1                 # one act, one undo row
    assert ed.undo_op()                            # and ONE undo erases it
    assert len(m.sketch.points) == 1


def test_the_copy_keeps_its_corner_and_carries_no_constraints(ed):
    m = ed.model
    sk = m.sketch
    a = m.point(-8.0, 0.0); c = m.point(6.0, 0.0); b = m.point(6.0, -8.0)
    m.add_line(a, c)
    m.add_line(c, b)
    m.constrain(Distance(a, c, 14.0))
    ed._solve()
    _click(ed, -1, 0)                              # L1 by its body...
    _clickc(ed, 6, -4)                             #  L2 joins via Ctrl
    assert ed._sel == [sk.lines[0], sk.lines[1]]
    _ctrl_d(ed)
    assert len(sk.points) == 6 and len(sk.lines) == 4
    assert len(sk.constraints) == 1                # copies arrive FREE
    assert sk.lines[2].b is sk.lines[3].a           # corner IDENTITY rode
    assert sk.lines[2].b is not c                   #  into the copy
    assert (sk.lines[2].b.x, sk.lines[2].b.y) == pytest.approx((7.25, 0.0))
    assert (a.x, a.y, b.x, b.y) == pytest.approx((-8.0, 0.0, 6.0, -8.0))


def test_the_copy_is_born_free_and_the_nudge_rides_it(ed):
    m = ed.model
    p = m.point(0, 0)
    m.toggle(Fixed, (p,))
    ed._solve()
    assert ed._dof_of(p) == 0
    _click(ed, 0, 0)                               # even locked points pick
    n0 = len(ed._hist)
    _ctrl_d(ed)                                    # a locked source still
    q = [pt for pt in m.sketch.points if pt is not p][0]    #  photocopies
    assert ed._dof_of(q) == 2                      # BORN FREE: no Fixed rides
    assert len(m.sketch.constraints) == 1          #  the copy has none
    _key(ed, Qt.Key_Right)                         # and the RUNG 2 nudge
    assert q.x == pytest.approx(2.5)               #  rides the COPY...
    assert p.x == 0.0                              #   the nailed source stays
    assert len(ed._hist) == n0 + 2                 # copy row + nudge row


def test_ctrl_d_is_silent_without_hands_and_obeys_the_tool(ed):
    m = ed.model
    a = m.point(2, 2); b = m.point(8, 5)
    m.add_line(a, b)
    ed._solve()
    st = (len(m.sketch.points), len(m.sketch.lines), len(m.sketch.constraints),
          len(ed._hist), a.x, a.y, b.x, b.y)
    assert ed._sel == []                           # EMPTY HANDS: the key
    _ctrl_d(ed)                                    #  pays NOTHING it cannot
    assert st == (len(m.sketch.points), len(m.sketch.lines),   # charge...
                  len(m.sketch.constraints), len(ed._hist),
                  a.x, a.y, b.x, b.y)
    _click(ed, 5, 3.5)                             # a pick exists...
    _key(ed, Qt.Key_T)                             #  but TRIM holds the hand
    st2 = (len(m.sketch.points), len(m.sketch.lines),
           len(m.sketch.constraints), len(ed._hist))
    _ctrl_d(ed)
    assert st2 == (len(m.sketch.points), len(m.sketch.lines),
                   len(m.sketch.constraints), len(ed._hist))
    assert ed._pending is None and ed._num_buf == ""    # never the D's dim
