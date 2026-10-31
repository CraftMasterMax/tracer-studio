"""M172 rung 1 - THE ROUNDING HAND: F pulls the arc, the release files it.

Canvas F retires the dialog for corners: with two selected lines sharing
a corner, F AIMS the rounding hand (the kernel's OWN validator answers -
a corner three geometries share refuses with the kernel's own words and
the scene stays byte-identical: aiming is not editing). A press ON the
aimed corner starts the pull; the move SIZES the ghost (cursor distance
to the corner, clamped by the kernel's own leg max - a pull can never
outrun the legs); the release FILES it: corner_fillet at the pulled r,
ONE history row, the arc becomes the pick, and the aim is spent. A
click without a pull files the dialog's own default radius; a click
elsewhere voids the aim and carries on as an ordinary click; tool
switch and Escape kill the arm (the M168 graveyard law). A refused
commit pops its row - a no-op leaves no undo. The aim is not modal:
the rung-2 NUDGE moves the corner and the aim RIDES it (the state holds
LIVE entities, not coordinates). One undo erases the whole fillet: the
arc, the two minted points, all four structural constraints.

Rung 2: G arms the FLAT twin on the same machine (chord ghost, D
numeral, pull = distance, corner_chamfer files ZERO constraints).

Rung 3 gives the ghost a voice: while ARMED, digits feed the corner's
OWN buffer (M90's _num_buf stays the dimmer's mouth - the corner hook
only fires with nothing pending). Enter files the EXACT typed number
with no mouse; typed text OUTRANKS a pull in flight (the cursor
afterwards just rides); empty buffer + Enter commits the ghost's own
number; garbage warns and the ARM STAYS ALIVE; and the typed number
must still fit the legs - steel is steel for the mouth too.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, QPoint, Qt               # noqa
from PySide6.QtGui import QMouseEvent                                # noqa
from PySide6.QtTest import QTest                                    # noqa
from PySide6.QtWidgets import QApplication                          # noqa

from tracer.core.sketch.constraints import Radius                   # noqa
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


def _move(ed, x, y):
    #  QTest.mouseMove cannot hold button state (m37 law) - send a real
    p = QPointF(300.0 + 4.0 * x, 200.0 - 4.0 * y)                 # event
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))


def _click(ed, x, y):
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(x, y))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(x, y))


def _clickc(ed, x, y):
    QTest.mousePress(ed, Qt.LeftButton, Qt.ControlModifier, _scr(x, y))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.ControlModifier, _scr(x, y))


def _scene(ed):
    m = ed.model
    far1 = m.point(-2, 6)
    P = m.point(6, 6)
    far2 = m.point(6, -2)
    m.add_line(far1, P)
    m.add_line(P, far2)
    ed._solve()
    return m, far1, P, far2


def _pick2(ed):
    _click(ed, 2, 6)                               # l1 by its mid...
    _clickc(ed, 6, 2)                              #  l2 joins via Ctrl


def _sig(m):
    sk = m.sketch
    return (len(sk.points), len(sk.lines), len(sk.arcs),
            len(sk.constraints),
            tuple(sorted((round(p.x, 4), round(p.y, 4)) for p in sk.points)))


def test_f_arms_the_corner_and_touches_nothing(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    assert len(ed._sel) == 2
    st = _sig(m)
    n0 = len(ed._hist)
    _key(ed, Qt.Key_F)
    assert ed._corner is not None                  # the hand is aimed...
    assert ed._corner[4] == pytest.approx(2.0)     #  at the old default
    assert len(ed._hist) == n0 and _sig(m) == st   #   and THAT is all


def test_a_press_and_release_files_the_default_round(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    n0 = len(ed._hist)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    sk = m.sketch
    assert len(sk.arcs) == 1                       # no pull = the default
    rad = [c for c in sk.constraints if isinstance(c, Radius)]
    assert len(rad) == 1 and rad[0].value == pytest.approx(2.0)
    assert len(sk.points) == 5                     # tangent 2 + bulge born
    assert ed._sel == [sk.arcs[0]]                 # the arc is the pick
    assert len(ed._hist) == n0 + 1                 # one act, one undo row
    assert ed._corner is None                      # the aim is spent
    assert P.x == pytest.approx(4.0)               # P REUSED as tangent 1
    assert ed.undo_op()                            # one undo erases all
    assert len(m.sketch.arcs) == 0 and len(m.sketch.points) == 3
    assert len(ed._hist) == n0


def test_the_pull_sizes_the_arc(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    n0 = len(ed._hist)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    _move(ed, 2.5, 6)                              # pull 3.5 mm out...
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(2.5, 6))
    rad = [c for c in m.sketch.constraints if isinstance(c, Radius)]
    assert len(rad) == 1
    assert rad[0].value == pytest.approx(3.5, abs=1e-9)   # the pull IS r
    assert P.x == pytest.approx(2.5)               # tan(45): tan_len = r
    assert len(ed._hist) == n0 + 1


def test_refusals_pay_nothing(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    ed._corner[4] = 99.0                           # an impossible commit
    st = _sig(m)
    n0 = len(ed._hist)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    assert _sig(m) == st and len(ed._hist) == n0   # popped: zero ambient
    assert ed._corner is None and len(m.sketch.arcs) == 0
    far3 = m.point(12, 6)                          # a corner of THREE:
    m.add_line(P, far3)                            #  the ARM itself
    ed._solve()                                    #   refuses, kernel-
    st2 = _sig(m)                                  #    worded, silent
    n1 = len(ed._hist)
    _key(ed, Qt.Key_F)
    assert ed._corner is None
    assert "more geometry" in ed._warn_text
    assert _sig(m) == st2 and len(ed._hist) == n1


def test_a_click_elsewhere_voids_the_aim(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    st = _sig(m)
    n0 = len(ed._hist)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(-4, -4))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(-4, -4))
    assert ed._corner is None                      # the aim is void...
    assert ed._sel == []                           #  and the click went
    assert len(ed._hist) == n0                     #   through as a click
    assert _sig(m) == st


def test_the_aim_rides_the_nudge_and_dies_with_the_tool(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    _key(ed, Qt.Key_Right)                         # M171's nudge steps
    assert P.x == pytest.approx(7.25)              #  the whole corner -
    assert ed._corner is not None                  #   the aim RIDES it
    assert ed._corner[3] is P                      #    (live entities)
    _key(ed, Qt.Key_T)                             # tool switch KILLS it
    assert ed._corner is None                      #  (M168 graveyard)
    _key(ed, Qt.Key_Escape)                        # back to select: the
    _key(ed, Qt.Key_F)                             #  still-picked pair
    assert ed._corner is not None                  #  RE-ARMS the hand
    _key(ed, Qt.Key_Escape)                        # Esc kills the aim
    assert ed._corner is None


# ---- RUNG 3: THE NUMERAL AND THE TYPE-IN ----------------------------------

def test_typing_the_radius_files_it_with_no_mouse(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    n0 = len(ed._hist)
    QTest.keyClick(ed, Qt.Key_3)                   # NO MOUSE at all:
    assert ed._corner_buf == "3"                   #  the corner's mouth
    assert ed._corner[4] == pytest.approx(3.0)     #  the ghost rides it
    QTest.keyClick(ed, Qt.Key_Return)
    sk = m.sketch
    assert len(sk.arcs) == 1
    rad = [c for c in sk.constraints if isinstance(c, Radius)]
    assert len(rad) == 1 and rad[0].value == pytest.approx(3.0)  # EXACT
    assert ed._corner is None and ed._corner_buf == ""           # spent
    assert len(ed._hist) == n0 + 1                 # still ONE row
    assert ed._num_buf == ""                       # M90's mouth SHUT
    assert (P.x, P.y) == pytest.approx((3.0, 6.0)) # tan_len rides the word


def test_the_mouth_outruns_the_hand(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    _move(ed, 2.5, 6)                              # the hand asks 3.5...
    assert ed._corner[4] == pytest.approx(3.5)
    for k in (Qt.Key_2, Qt.Key_Period, Qt.Key_5):  # the mouth says 2.5
        QTest.keyClick(ed, k)
    assert ed._corner_buf == "2.5"
    assert ed._corner[4] == pytest.approx(2.5)
    _move(ed, 1.5, 6)                              # hand keeps moving...
    assert ed._corner[4] == pytest.approx(2.5)     #  the number HOLDS
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(1.5, 6))
    rad = [c for c in m.sketch.constraints if isinstance(c, Radius)]
    assert rad[0].value == pytest.approx(2.5, abs=1e-9)   # the mouth WON
    assert (P.x, P.y) == pytest.approx((3.5, 6.0))


def test_garbage_warns_the_arm_survives_and_empty_enter_files_the_ghost(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    n0 = len(ed._hist)
    QTest.keyClick(ed, Qt.Key_Period)              # "." alone: typed...
    assert ed._corner_buf == "."
    assert ed._corner[4] == pytest.approx(2.0)     #  ghost unmoved
    QTest.keyClick(ed, Qt.Key_Return)              # Enter on garbage:
    assert "." in ed._warn_text                    #  WARNS...
    assert ed._corner is not None                  #  ARM ALIVE...
    assert len(ed._hist) == n0                     #   zero rows born
    assert len(m.sketch.arcs) == 0
    QTest.keyClick(ed, Qt.Key_Backspace)           # erase the typo
    assert ed._corner_buf == ""
    QTest.keyClick(ed, Qt.Key_Return)              # EMPTY Enter:
    rad = [c for c in m.sketch.constraints if isinstance(c, Radius)]
    assert len(rad) == 1 and rad[0].value == pytest.approx(2.0)  # the
    assert len(ed._hist) == n0 + 1                 #  ghost's own number


def test_the_corner_mouth_is_a_separate_mouth(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    QTest.keyClick(ed, Qt.Key_7)                   # digits while ARMED
    assert ed._corner_buf == "7"                   #  feed the CORNER
    assert ed._num_buf == ""                       #  M90's mouth stays
    assert ed._pending is None                     #   SHUT...
    assert ed._tool == "select"                    #   and no tool stole
    assert len(m.sketch.arcs) == 0                 #    the keystroke
    QTest.keyClick(ed, Qt.Key_Backspace)
    assert ed._corner_buf == ""
    ed._pending = ("dim-witness", None)            # open the DIMMER'S
    QTest.keyClick(ed, Qt.Key_5)                   # mouth: the digit
    assert ed._num_buf == "5"                      #  belongs to M90...
    assert ed._corner_buf == ""                    #   corner hook slept
    _key(ed, Qt.Key_Escape)                        # M176 R3's EXPLICIT
    assert ed._pending is None and ed._num_buf == ""  #  cascade: Esc(1)
    assert ed._corner is not None                  #  honors the number &
    _key(ed, Qt.Key_Escape)                        #  drops the lock;
    assert ed._corner is None                      #  Esc(2) washes all


# ---- RUNG 2: G FLATS THE SAME HAND (chamfer) -----------------------------

def test_g_arms_the_flat_ghost_and_files_the_chamfer(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    st = _sig(m)
    n0 = len(ed._hist)
    _key(ed, Qt.Key_G)
    assert ed._corner is not None and ed._corner[0] == "chamfer"
    assert ed._corner[4] == pytest.approx(2.0)
    assert len(ed._hist) == n0 and _sig(m) == st      # aiming is not editing
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    sk = m.sketch
    assert len(sk.arcs) == 0                          # the cut is FLAT
    assert len(sk.lines) == 3                         #  the chord is born
    assert len(sk.constraints) == 0                   #   structural trim
    assert len(sk.points) == 4                        #    tangent 2's Q
    assert ed._sel == [sk.lines[2]]                   #     the cut's pick
    assert (P.x, P.y) == pytest.approx((4.0, 6.0))    # P REUSED tangent 1
    assert len(ed._hist) == n0 + 1


def test_the_pull_distances_the_flat(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_G)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    _move(ed, 2.5, 6)                                 # pull 3.5 mm out
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(2.5, 6))
    assert (P.x, P.y) == pytest.approx((2.5, 6.0))    # d = the pull, exact
    cut = m.sketch.lines[2]
    others = [p for p in (cut.a, cut.b) if p is not P]
    assert (others[0].x, others[0].y) == pytest.approx((6.0, 2.5))


def test_fillet_then_chamfer_share_one_session_without_inheritance(ed):
    m = ed.model
    m.add_rect(m.point(-10, -10), m.point(10, 10))
    ed._solve()
    sk = m.sketch
    n0 = len(ed._hist)

    def corner_at(x, y):
        return next(p for p in sk.points if (p.x, p.y) == (x, y))

    def pick_corner(pt):
        ed._sel = [l for l in sk.lines if pt in (l.a, l.b)][:2]

    A = corner_at(10, 10)
    pick_corner(A)
    _key(ed, Qt.Key_F)
    assert ed._corner[4] == pytest.approx(5.0)        # legs 20: default 5
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(10, 10))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(10, 10))
    assert len(m.sketch.arcs) == 1 and len(ed._hist) == n0 + 1
    assert ed._corner is None                         # the aim is spent
    B = corner_at(-10, 10)
    pick_corner(B)                                    # the NEXT corner
    _key(ed, Qt.Key_G)                                #  finds its OWN
    assert ed._corner[0] == "chamfer"                 #   default from
    assert ed._corner[4] == pytest.approx(3.8)        #   LIVE legs (the
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(-10, 10))  # top
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(-10, 10))  # was
    assert len(m.sketch.arcs) == 1                    #  fillet kept
    assert len(m.sketch.lines) == 5                   #  chamfer added one
    assert len(ed._hist) == n0 + 2                    # two acts, two rows
    assert ed.undo_op()                               # undo splits them
    # the UNDO swaps model.sketch for a NEW object - re-read through the
    # model (identity across undo is the M171 law this gate obeys).
    assert len(m.sketch.lines) == 4 and len(m.sketch.arcs) == 1
    assert len(m.sketch.points) == 6                  # Q gone, M kept


def test_the_flat_refuses_its_own_way(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_G)
    ed._corner[4] = 99.0                              # impossible flat
    st = _sig(m)
    n0 = len(ed._hist)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    assert _sig(m) == st and len(ed._hist) == n0      # popped: zero ambient
    far3 = m.point(12, 6)                             # a corner of THREE:
    m.add_line(P, far3)                               #  the kernel words
    ed._solve()                                       #   the KIND in its
    n1 = len(ed._hist)                                #    own refusal
    _key(ed, Qt.Key_G)
    assert ed._corner is None
    assert "chamfer" in ed._warn_text
    assert len(ed._hist) == n1
