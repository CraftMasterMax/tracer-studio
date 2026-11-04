"""M193 rung 1 - THE ARC HIDING IN THE LINE TOOL.

SKT-CREATE-LINES, verbatim: "pause over an end point, then click and
drag to create an arc segment that is TANGENT to the previous line
segment."  The Line tool's chain already walks end-to-end (M176/M177);
what it never had was the BEND.  This rung grafts the vendor's half-arc
onto the chain's free end:

- A PRESS that lands on the live free end, when a previous leg exists
  to be tangent to, ARMS a tangent-arc drag.  Travel past a click's
  worth of pixels turns it into a DRAG: the release mints an Arc whose
  start welds to the free end (shared Point, C0) and whose start
  tangent matches the previous leg's direction (C1, exact by
  construction: the centre rides the normal at the start).
- Which SIDE the cursor lands on is which way the arc bends - the
  vendor's own flip, solved here by choosing the normal on the drag's
  side so the arc bulges TOWARD the cursor.
- The chain walks ON: the arc's exit tangent becomes the next bend's
  rule, so a second drag keeps flowing (a chain of arcs).
- A release that NEVER travelled is still M176/M177's back-click that
  CLOSES the chain - byte-for-byte.  A drag aimed dead straight along
  the tangent is not an arc at all: it commits as a straight LEG
  (the solver keeps the maker's intent, not a radius of infinity).
- L25 (M177 R3) travels with the drag: landing the arc's far end on
  EXISTING geometry ENDS the chain, the tool re-arms.
- The tangent is a guest of the chain anchor: wherever the free end
  dies (tool switch, model swap, history jump, finish, Enter, Esc,
  typed placement) the tangent and every armed drag die with it.

Rung 2 is the vendor's NEXT sentence - "Move the mouse to the OPPOSITE
SIDE of the line segment to FLIP the DIRECTION of the arc" - and the
honest verdict is that R1's ONE mouth already speaks it: the normal is
chosen on the drag's side at every aim update, so the flip is LIVE
inside the single held gesture, the release commits the LAST side the
cursor promised, and the corridor exactly ON the tangent degrades
continuously to the straight-leg law (no dead zone, no re-press). R2
therefore PINS that behavior as law: mid-drag crossing with tangency
surviving the flip, the corridor handoff, and the flip off an ARC's own
exit tangent (not an x/y trick - the cross product decides everywhere).
"""
import math

import pytest

# ---- pure geometry (no Qt at all) --------------------------------------
from tracer.core.sketch.entities import (Arc, Point, tangent_arc_mid,
                                         tangent_arc_sample)


def _circ(s, t, e):
    """The Arc through (s, mid, e) and its circumcircle."""
    got = tangent_arc_mid(s, t, e)
    assert got is not None
    (mx, my), exit_t = got
    ar = Arc(Point(*s), Point(mx, my), Point(*e))
    (cx, cy), r = ar.circle()
    return ar, (cx, cy), r, (mx, my), exit_t


def test_tangency_and_circle_exact():
    for s, t, e in [((0.0, 0.0), (1.0, 0.0), (0.0, 10.0)),    # semicircle
                    ((0.0, 0.0), (1.0, 0.0), (10.0, 10.0)),   # quarter up
                    ((3.0, 4.0), (0.0, 1.0), (-6.0, 4.0)),    # offset
                    ((0.0, 0.0), (0.7071, 0.7071), (5.0, 0.0))]:  # diagonal
        ar, (cx, cy), r, (mx, my), _exit = _circ(s, t, e)
        # C0: all three points lie on the circle...
        for p in (s, e, (mx, my)):
            assert abs(math.hypot(p[0] - cx, p[1] - cy) - r) < 1e-9 * max(r, 1)
        # C1: the radius vector at the start is perpendicular to the tangent
        rx, ry = s[0] - cx, s[1] - cy
        assert abs(rx * t[0] + ry * t[1]) < 1e-9 * max(r, 1)


def test_side_is_the_bend():
    _ar, (c1x, c1y), _r1, m1, exit1 = _circ((0.0, 0.0), (1.0, 0.0), (8.0, 6.0))
    _ar, (c2x, c2y), _r2, m2, exit2 = _circ((0.0, 0.0), (1.0, 0.0), (8.0, -6.0))
    assert c1y > 0.0 and c2y < 0.0          # centre follows the drag's side
    assert m1[1] > 0.0 > m2[1]              # the bulge faces the cursor
    assert exit1[1] > 0.0 > exit2[1]        # and so does where it leaves


def test_degenerate_drags_have_no_arc():
    assert tangent_arc_mid((1.0, 2.0), (1.0, 0.0), (1.0, 2.0)) is None
    assert tangent_arc_mid((0.0, 0.0), (1.0, 0.0), (17.0, 0.0)) is None
    assert tangent_arc_mid((0.0, 0.0), (0.0, 0.0), (5.0, 5.0)) is None


def test_exit_tangent_chains_and_sample_endpoints():
    _ar, _c, _r, _m, exit_t = _circ((0.0, 0.0), (1.0, 0.0), (0.0, 10.0))
    assert math.isclose(exit_t[0], -1.0, abs_tol=1e-12)   # half turn: back
    assert math.isclose(exit_t[1], 0.0, abs_tol=1e-12)
    poly = tangent_arc_sample((0.0, 0.0), (1.0, 0.0), (0.0, 10.0), n=24)
    assert poly is not None and len(poly) == 25
    assert math.dist(poly[0], (0.0, 0.0)) < 1e-12
    assert math.dist(poly[-1], (0.0, 10.0)) < 1e-12
    assert tangent_arc_sample((0.0, 0.0), (1.0, 0.0), (9.0, 0.0)) is None


# ---- the canvas choreography --------------------------------------------
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                              # noqa
from PySide6.QtTest import QTest                                   # noqa
from PySide6.QtWidgets import QApplication                         # noqa

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
    c._scale = 8.0                       # generous px/unit: the 9px magnet
    #                                     tolerance must never STEAL a
    #                                     drag's endpoints from this gate
    c._snap_grid = False                 # free mints: the drag decides
    yield c
    c.deleteLater()


def _sp(cv, x, y):
    return cv.w2s(x, y).toPoint()


def _click(cv, x, y):
    pt = _sp(cv, x, y)
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    QApplication.instance().processEvents()


def _press(cv, x, y):
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                     _sp(cv, x, y))
    QApplication.instance().processEvents()


def _drag_to(cv, x, y):
    QTest.mouseMove(cv, _sp(cv, x, y))          # this binding carries no
    #                                            button mask; the ARMED
    #                                            press (not held bits)
    #                                            drives the drag branch
    QApplication.instance().processEvents()


def _release(cv, x, y):
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                       _sp(cv, x, y))
    QApplication.instance().processEvents()


def _leg(cv, ax, ay, bx, by):
    """Two clicks: a committed chain leg, the chain now free at b."""
    _click(cv, ax, ay)
    _click(cv, bx, by)


def _arc_drag(cv, bx, by, ex, ey):
    """The vendor's gesture: press the free end, drag, release."""
    _press(cv, bx, by)
    _drag_to(cv, ex, ey)
    _release(cv, ex, ey)


def _sk(cv):
    return cv.model.sketch


def test_drag_from_free_end_commits_tangent_arc(ed):
    cv = ed
    cv.set_tool("line")
    _leg(cv, 2, 6, 9, 6)                       # a horizontal leg, free at B
    assert len(_sk(cv).lines) == 1 and not _sk(cv).arcs
    assert cv._line_dir == pytest.approx((1.0, 0.0))   # the recorded tangent
    _arc_drag(cv, 9, 6, 9, 12)                 # perpendicular drag: semicircle
    sk = _sk(cv)
    assert len(sk.lines) == 1                   # no stray leg minted
    assert len(sk.arcs) == 1
    ar = sk.arcs[-1]
    assert ar.a is sk.lines[-1].b               # welded at the free end (C0)
    (cx, cy), r = ar.circle()
    assert cx == pytest.approx(9.0, abs=1e-6)   # centre on the normal at B
    assert cy == pytest.approx(9.0, abs=1e-6)
    assert r == pytest.approx(3.0, abs=1e-6)
    assert (ar.m.x, ar.m.y) == pytest.approx((12.0, 9.0), abs=1e-6)
    assert not ar.construction
    assert (ar.b.x, ar.b.y) == pytest.approx((9.0, 12.0), abs=1e-6)
    # the chain WALKS ON: the free end is the arc's, the tangent its exit
    assert cv._line_start is ar.b
    assert cv._line_dir == pytest.approx((-1.0, 0.0), abs=1e-9)


def test_no_travel_back_click_still_closes(ed):
    """M176/M177's law, byte-for-byte: press the free end, never move,
    release - the chain CLOSES and NOTHING is minted."""
    cv = ed
    cv.set_tool("line")
    _leg(cv, 2, 6, 9, 6)
    _click(cv, 9, 6)                            # zero travel: the close
    sk = _sk(cv)
    assert len(sk.lines) == 1 and not sk.arcs
    assert cv._line_start is None and cv._line_dir is None


def test_straight_drag_adds_leg_not_arc(ed):
    cv = ed
    cv.set_tool("line")
    _leg(cv, 2, 6, 9, 6)
    _arc_drag(cv, 9, 6, 16, 6)                  # dead along the tangent
    sk = _sk(cv)
    assert len(sk.lines) == 2 and not sk.arcs   # a LEG, not radius infinity
    assert (sk.lines[-1].b.x, sk.lines[-1].b.y) == pytest.approx((16.0, 6.0))
    assert cv._line_start is sk.lines[-1].b     # and it still chains
    assert cv._line_dir == pytest.approx((1.0, 0.0))


def test_arcs_chain_tangent_after_tangent(ed):
    cv = ed
    cv.set_tool("line")
    _leg(cv, 2, 6, 9, 6)
    _arc_drag(cv, 9, 6, 9, 12)                  # first bend: exits at (-1,0)
    exit1 = cv._line_dir
    _arc_drag(cv, 9, 12, 5, 8)                  # press the ARC's free end
    sk = _sk(cv)
    assert len(sk.arcs) == 2
    ar1, ar2 = sk.arcs
    assert ar2.a is ar1.b                       # the chain welds arc to arc
    (cx, cy), _r = ar2.circle()
    rx, ry = ar1.b.x - cx, ar1.b.y - cy         # C1 at the shared end:
    assert abs(rx * exit1[0] + ry * exit1[1]) < 1e-6   #  radius ⟵ perp to
    #                                            the tangent arc 1 handed over


def test_arc_land_on_existing_ends_chain(ed):
    """L25 (M177 R3) travels with the drag: the far end landing on
    EXISTING geometry ENDS the chain, the tool re-arms."""
    cv = ed
    cv.set_tool("line")
    _leg(cv, 9, 12, 5, 12)                      # an island to land on
    _click(cv, 5, 12)                            # close it
    _leg(cv, 2, 6, 9, 6)                         # fresh chain, free at B
    _arc_drag(cv, 9, 6, 9, 12)                   # the far end welds onto P
    sk = _sk(cv)
    assert len(sk.arcs) == 1
    assert sk.arcs[-1].a is sk.lines[1].b       # tangent weld at B
    assert sk.arcs[-1].b is sk.lines[0].a       # the far end REUSED existing
    #                                          P (identity = coincidence)
    assert cv._line_start is None               # L25: the chain ENDS
    assert cv._line_dir is None
    assert cv._tool == "line"                   # the tool lives, re-armed


def test_fresh_chain_arms_nothing(ed):
    """No previous segment, nothing to be tangent TO: the back-click on
    a ONE-CLICK chain closes on the press exactly as before - no drag
    ever arms and the tangent stays None."""
    cv = ed
    cv.set_tool("line")
    _click(cv, 2, 6)
    assert cv._line_dir is None
    _press(cv, 2, 6)
    assert cv._arc_drag is None                 # NOT armed - no tangent yet
    _release(cv, 2, 6)
    assert cv._line_start is None
    sk = _sk(cv)
    assert not sk.lines and not sk.arcs


def test_armed_drag_dies_with_a_tool_switch(ed):
    """M193 R1 wash law: the tangent is a GUEST of the anchor - walking
    to another tool while a drag is mid-flight kills the armed press,
    the live aim and the tangent, and commits NOTHING."""
    cv = ed
    cv.set_tool("line")
    _leg(cv, 2, 6, 9, 6)
    _press(cv, 9, 6)
    _drag_to(cv, 9, 12)                         # past the travel line
    assert cv._arc_drag is not None and cv._arc_drag_pushed
    assert cv._arc_drag_to is not None
    cv.grab()                                   # paint smoke: the dashed arc
    cv.set_tool("select")
    assert cv._arc_drag is None and cv._arc_drag_to is None
    assert cv._arc_drag_pushed is False and cv._line_dir is None
    _release(cv, 9, 12)                         # the orphaned release lands
    #                                            dead: the generic tail has
    sk = _sk(cv)                                #  no preview to answer
    assert len(sk.lines) == 1 and not sk.arcs


# ---- R2: the LIVE flip - one gesture, the OPPOSITE side, no re-press ---
def test_live_flip_across_the_tangent_mid_drag(ed):
    """SKT-CREATE-LINES, verbatim: "Move the mouse to the OPPOSITE SIDE
    of the line segment to FLIP the DIRECTION of the arc."  The flip is
    LIVE inside the ONE armed gesture - press, ride up, cross under,
    release - and the release commits what the LAST side promised.  No
    re-press, no second tool, and NOTHING is minted mid-flight: the
    preview is pure paint, the solve is the same mouth that answers the
    release."""
    cv = ed
    cv.set_tool("line")
    _leg(cv, 2, 6, 9, 6)
    _press(cv, 9, 6)
    _drag_to(cv, 9, 12)                         # ABOVE: the arc rides up
    assert cv._arc_drag_pushed and cv._arc_drag_to is not None
    up = tangent_arc_mid((9.0, 6.0), cv._line_dir, (9.0, 12.0))
    assert up is not None and up[0][1] > 6.0    #  the preview promises high
    _drag_to(cv, 11, 0)                         # ACROSS the tangent line
    assert cv._arc_drag_to is not None          # the gesture never DIED
    assert not _sk(cv).arcs                     # and never minted partials
    _release(cv, 11, 0)
    sk = _sk(cv)
    assert len(sk.lines) == 1 and len(sk.arcs) == 1
    ar = sk.arcs[-1]
    (cx, cy), r = ar.circle()
    assert cy < 6.0                             # the LOW side kept its word
    assert cx == pytest.approx(9.0, abs=1e-6)   # centre ON THE NORMAL still:
    #                                            tangency SURVIVED the flip
    want_mid, want_exit = tangent_arc_mid((9.0, 6.0), (1.0, 0.0), (11.0, 0.0))
    assert want_mid[1] < 6.0                    #  the solve agrees it went low
    assert (ar.m.x, ar.m.y) == pytest.approx(want_mid, abs=1e-6)
    #   ONE mouth: what the dashed preview promised, the release COMMITTED
    assert (ar.b.x, ar.b.y) == pytest.approx((11.0, 0.0), abs=1e-6)
    assert cv._line_start is ar.b               # and the chain walks on the
    assert cv._line_dir == pytest.approx(want_exit, abs=1e-9)  # flipped arc


def test_across_the_straight_corridor_the_band_answers(ed):
    """Exactly ON the tangent there is no arc to bend: the solve says
    None and the same held gesture aims a STRAIGHT LEG (the band, not a
    curve). A hair off the line and the ONE gesture is an arc again -
    the flip mouth is CONTINUOUS with the leg law: no dead zone where
    the maker would have to let go and re-press."""
    cv = ed
    cv.set_tool("line")
    _leg(cv, 2, 6, 9, 6)
    _press(cv, 9, 6)
    _drag_to(cv, 16, 6)                         # dead ON the tangent
    assert cv._arc_drag_pushed
    assert tangent_arc_mid((9.0, 6.0), cv._line_dir, (16.0, 6.0)) is None
    _drag_to(cv, 16, 0.5)                       # a hair BELOW: arc again
    _release(cv, 16, 0.5)
    sk = _sk(cv)
    assert len(sk.arcs) == 1 and len(sk.lines) == 1
    (cx, cy), _r = sk.arcs[-1].circle()
    assert cy < 6.0                             # and it bends to the NEW
    #                                              side the corridor opened
    assert cv._arc_drag is None                 # the gesture settled whole


def test_flip_survives_off_the_axis_and_after_an_arc(ed):
    """The flip is not a x/y trick: with a DIAGONAL incoming leg the
    cross product decides, and pressing the free end of an ALREADY-BENT
    chain flips the SECOND arc about ITS OWN exit tangent (the one
    mouth, everywhere)."""
    cv = ed
    cv.set_tool("line")
    _leg(cv, 2, 6, 8, 12)                       # diagonal leg, dir (6,6)/L
    d = math.hypot(6.0, 6.0)
    assert cv._line_dir == pytest.approx((6 / d, 6 / d))
    _press(cv, 8, 12)
    _drag_to(cv, 4, 18)                         # LEFT of the climb: arc up
    _drag_to(cv, 14, 10)                        # ACROSS to the right
    _release(cv, 14, 10)
    sk = _sk(cv)
    assert len(sk.arcs) == 1
    ar = sk.arcs[-1]
    (cx, cy), r = ar.circle()
    rx, ry = ar.a.x - cx, ar.a.y - cy
    assert abs(rx * (6 / d) + ry * (6 / d)) < 1e-9 * max(r, 1)   # still C1
    cross = (6 / d) * (ar.b.y - ar.a.y) - (6 / d) * (ar.b.x - ar.a.x)
    assert cross < 0.0                          # and it bent the NEW way
    # now flip a SECOND arc hung off that arc's own exit tangent
    exit1 = cv._line_dir
    px, py = -exit1[1], exit1[0]                # perpendicular to the way
    _press(cv, ar.b.x, ar.b.y)                  #  the chain LEAVES
    _drag_to(cv, ar.b.x + 10 * px, ar.b.y + 10 * py)    # promise one side...
    _drag_to(cv, ar.b.x - 10 * px, ar.b.y - 10 * py)    # ...CROSS to the other
    ex, ey = ar.b.x - 10 * px, ar.b.y - 10 * py
    _release(cv, ex, ey)
    sk = _sk(cv)
    assert len(sk.arcs) == 2
    a2 = sk.arcs[-1]
    assert a2.a is ar.b                                   # welded end to end
    (c2x, c2y), _r2 = a2.circle()
    r2x, r2y = a2.a.x - c2x, a2.a.y - c2y
    assert abs(r2x * exit1[0] + r2y * exit1[1]) < 1e-9    # C1 off the ARC
    def side(qx, qy):                                     # which side of the
        return exit1[0] * (qy - ar.b.y) - exit1[1] * (qx - ar.b.x)
    assert side(c2x, c2y) * side(ex, ey) > 0              # exit line, and the
    #                                                     bulge faced the LAST
    #                                                     side the cursor held
