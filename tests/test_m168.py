"""M168 rung 1 — the CUT (split kernel + the re-home law).

Trim-to-click needs one new kernel verb: split_entity turns ONE entity into
TWO that share one new seam Point.  Because to_loops() joins geometry through
shared IDENTITY, a profile keeps closing across the seam exactly as before —
the cut is invisible downstream.

Constraints re-home by a v1 law of two clauses, verified against an audit of
every constraint class's entities():
  * POINT-named facts (Coincident, Fixed, Distance, Symmetry's points) never
    name the eaten line at all — they ride through untouched;
  * SHA kind-facts (Horizontal, Vertical, Angle, Parallel, Perpendicular,
    Collinear, Radius, Symmetry's axis) are TRUE of every piece: copied to
    BOTH halves, and the structural src stamp rides the copy (a split is
    structural, its constraints are never removable);
  * METRIC/positional facts (Equal length, Midpoint, ArcMiddle, PointOnLine,
    Tangent contact) are AMBIGUOUS across a cut and DROP with the original —
    consumption rides delete_entity, so fx bindings follow the drop.

Arc halves are minted with exact sub-span midpoints: both halves' derived
circle matches the original to floating-point dust (< 1e-13 observed).
Circles, ellipses and points refuse the cut (v1), and every refusal lands
BEFORE any mutation — the model comes out byte-identical.

This rung is kernel-only: the editor does not wire it yet, no pixels move.
"""
import math

import pytest

pytest.importorskip("PySide6")

from tracer.core.sketch.constraints import (Distance, Equal, Horizontal,   # noqa: E402
                                            Parallel)
from tracer.core.sketch.entities import Circle, Ellipse, Line             # noqa: E402
from tracer.core.sketch.model import SketchModel                           # noqa: E402
from tracer.core.sketch.trim import split_entity, trim_piece   # noqa: E402
from tracer.core.snaps import _circumference                               # noqa: E402


def test_splitting_a_line_makes_two_halves_that_share_one_seam():
    m = SketchModel()
    a = m.point(0, 0); b = m.point(40, 0)
    l = m.add_line(a, b)
    n_pts = len(m.sketch.points)
    left, right = split_entity(m, l, 15.0, 0.0)
    assert len(m.sketch.lines) == 2                 # one in, two out
    assert left.b is right.a                        # ONE shared seam Point
    assert (left.b.x, left.b.y) == (15.0, 0.0)      # exact, where asked
    assert len(m.sketch.points) == n_pts + 1        # the seam is a point now
    assert (left.a.x, left.a.y, right.b.x, right.b.y) == (0.0, 0.0, 40.0, 0.0)
    assert math.dist((left.a.x, left.a.y), (left.b.x, left.b.y)) == 15.0
    assert math.dist((right.a.x, right.a.y), (right.b.x, right.b.y)) == 25.0
    assert m.sketch.lines == [left, right]          # halves eat the slot:
    #                                              the ORIGINAL ORDER holds
    c = m.point(0, 5)
    guide = Line(a, c, True)                        # a CONSTRUCTION line…
    m.sketch.lines.append(guide)
    gl, gr = split_entity(m, guide, 0, 2.5)
    assert gl.construction and gr.construction      # …copies its kind


def test_illegal_cuts_refuse_and_leave_the_model_byte_exact():
    m = SketchModel()
    u = m.point(0, 0); v = m.point(40, 0)
    l = m.add_line(u, v)
    before = ([(e.a.x, e.a.y, e.b.x, e.b.y) for e in m.sketch.lines],
              len(m.sketch.points), len(m.sketch.constraints))
    for call, why in ((lambda: split_entity(m, l, 40.0, 0.0), "end"),
                      (lambda: split_entity(m, l, 20.0, 3.0), "off-curve"),
                      (lambda: split_entity(m, u, 0.0, 0.0), "not splittable")):
        with pytest.raises(ValueError):
            call()                                   # refuse…
    after = ([(e.a.x, e.a.y, e.b.x, e.b.y) for e in m.sketch.lines],
             len(m.sketch.points), len(m.sketch.constraints))
    assert before == after                          # …BEFORE mutating: byte-exact


def test_split_arc_halves_stay_on_the_original_circle():
    m = SketchModel()
    A = m.point(20, -30); M = m.point(35, -20); B = m.point(50, -30)
    ar = m.sketch.arc(A, M, B)
    geo0 = _circumference(A, M, B)
    cx, cy, r = geo0
    Sx = cx + r * math.cos(math.radians(135))        # a point ON the arc,
    Sy = cy + r * math.sin(math.radians(135))        #  well inside the span
    left, right = split_entity(m, ar, Sx, Sy)
    assert len(m.sketch.arcs) == 2                   # the pool got the halves
    assert left.b is right.a                         # shared seam again
    assert m.sketch.arcs == [left, right]            # in the eaten slot
    for half in (left, right):                       # every half re-derives
        g = _circumference(half.a, half.m, half.b)   #  THE SAME circle:
        assert max(abs(p - q) for p, q in zip(g, geo0)) < 1e-9
    assert math.dist((left.b.x, left.b.y), (cx, cy)) == pytest.approx(r,
                                                                      abs=1e-9)


def test_kind_facts_ride_both_halves():
    m = SketchModel()
    p1 = m.point(0, 0); p2 = m.point(40, 0)
    l1 = m.add_line(p1, p2)
    q1 = m.point(0, 10); q2 = m.point(40, 10)
    l2 = m.add_line(q1, q2)
    m.constrain(Horizontal(l1), Parallel(l1, l2), src="rect")
    left, right = split_entity(m, l1, 20.0, 0.0)
    hs = [c for c in m.sketch.constraints if isinstance(c, Horizontal)]
    ps = [c for c in m.sketch.constraints if isinstance(c, Parallel)]
    assert [c.line for c in hs] == [left, right]     # BOTH halves horizontal…
    assert {id(c.l1) for c in ps} == {id(left), id(right)}
    assert all(c.l2 is l2 for c in ps)               #  …and still parallel to l2
    assert all(getattr(c, "src", "") == "rect"      # structural stamp RIDES
               for c in hs + ps)                     #  the copies


def test_metric_facts_die_with_the_eaten_entity():
    m = SketchModel()
    p1 = m.point(0, 0); p2 = m.point(40, 0)
    l1 = m.add_line(p1, p2)
    q1 = m.point(0, 10); q2 = m.point(40, 10)
    l2 = m.add_line(q1, q2)
    d = Distance(p1, p2, value=40.0)
    m.constrain(Equal(l1, l2))
    m.constrain(d)                                   # point-named: no src
    split_entity(m, l1, 20.0, 0.0)
    kinds = [type(c).__name__ for c in m.sketch.constraints]
    assert "Equal" not in kinds                      # ambiguous across a cut…
    assert d in m.sketch.constraints                 # …but point Distance is
    assert (d.p.x, d.q.x) == (0.0, 40.0)             #  UNTOUCHED geometry


def test_a_seam_split_never_opens_a_profile():
    m = SketchModel()
    m.add_rect(m.point(0, 0), m.point(30, 20))
    loops0, warns0 = m.to_loops()
    assert len(loops0) == 1 and not warns0
    top = next(e for e in m.sketch.lines
               if abs(e.a.y - 20) < 1e-9 and abs(e.b.y - 20) < 1e-9)
    split_entity(m, top, 15.0, 20.0)
    loops1, warns1 = m.to_loops()                    # to_loops joins by IDENTITY:
    assert len(loops1) == 1 and not warns1           #  the seam keeps the loop
    assert abs(loops1[0]["area"] - loops0[0]["area"]) < 1e-12  #  closed, exact


def test_the_seam_is_free_and_the_split_solves():
    m = SketchModel()
    a = m.point(0, 0); b = m.point(40, 0)
    l = m.add_line(a, b)
    m.constrain(Horizontal(l))                       # the line is constrained…
    left, right = split_entity(m, l, 15.0, 0.0)
    res = m.solve()
    assert res.converged                             # solver absorbs the +1 pt…
    S = left.b
    assert (S.x, S.y) == (15.0, 0.0)                 #  …and the FREE seam holds
    S.y = 3.0                                        # only the ends are pinned
    res = m.solve()                                  #  by nothing here: the
    assert res.converged and right.a is S            #  seam is genuinely free


def test_circles_and_ellipses_refuse_the_cut_v1():
    m = SketchModel()
    c = m.sketch.circle(m.point(0, 0), 10.0)
    e = m.sketch.ellipse(m.point(50, 0), 8.0, 4.0)
    n_l, n_c = len(m.sketch.circles), len(m.sketch.ellipses)
    for ent, xy in ((c, (10.0, 0.0)), (e, (58.0, 0.0))):   # points ON each
        with pytest.raises(ValueError):
            split_entity(m, ent, *xy)                # closed curves refuse…
    assert len(m.sketch.circles) == n_l              #  …and leave everything
    assert len(m.sketch.ellipses) == n_c             #   exactly as it was


# ---- Rung 2: piece deletion (the trim verb) --------------------------------

def test_trimming_an_X_deletes_just_the_clicked_piece():
    m = SketchModel()
    a = m.point(0, 0); b = m.point(40, 40)
    c = m.point(0, 40); d = m.point(40, 0)
    l1 = m.add_line(a, b)                             # X crossing at (20, 20)
    l2 = m.add_line(c, d)
    victim = trim_piece(m, l1, 30, 30)                # the (20..40) spoke…
    assert (victim.a.x, victim.a.y) == pytest.approx((20.0, 20.0), abs=1e-9)
    assert (victim.b.x, victim.b.y) == pytest.approx((40.0, 40.0), abs=1e-9)
    kept = m.sketch.lines
    assert len(kept) == 2                             # spoke half + l2
    survivor = next(l for l in kept if l is not l2)
    assert (survivor.a.x, survivor.a.y) == (0.0, 0.0)
    assert (survivor.b.x, survivor.b.y) == pytest.approx((20.0, 20.0),
                                                         abs=1e-9)
    assert (c.x, c.y, d.x, d.y) == (0.0, 40.0, 40.0, 0.0)   # neighbour byte


def test_a_lonely_line_is_one_piece_and_goes_whole():
    m = SketchModel()
    u = m.point(0, 0); v = m.point(40, 0)
    l = m.add_line(u, v)
    assert trim_piece(m, l, 20, 0) is l               # Fusion: trim on a
    assert m.sketch.lines == []                       #  lonely line erases it


def test_the_middle_piece_falls_and_the_facts_ride_the_survivors():
    m = SketchModel()
    h = m.add_line(m.point(0, 0), m.point(60, 0))
    m.add_line(m.point(20, -10), m.point(20, 10))
    m.add_line(m.point(40, -10), m.point(40, 10))
    m.constrain(Horizontal(h), src="test")
    assert trim_piece(m, h, 30, 0) is not None        # cut twice, middle out
    hor = sorted((round(l.a.x, 9), round(l.b.x, 9)) for l in m.sketch.lines
                 if abs(l.a.y) < 1e-9 and abs(l.b.y) < 1e-9)
    assert hor == [(0.0, 20.0), (40.0, 60.0)]         # the two outer pieces
    hs = [c for c in m.sketch.constraints if isinstance(c, Horizontal)]
    assert len(hs) == 2                               # SHA facts survived…
    assert all(getattr(c, "src", "") == "test" for c in hs)   # …structurally


def test_a_click_on_a_cut_refuses_before_any_split():
    m = SketchModel()
    h = m.add_line(m.point(0, 0), m.point(60, 0))
    m.add_line(m.point(20, -10), m.point(20, 10))
    m.add_line(m.point(40, -10), m.point(40, 10))
    before = sorted((l.a.x, l.a.y, l.b.x, l.b.y) for l in m.sketch.lines)
    assert trim_piece(m, h, 20, 0) is None            # ambiguous boundary:
    after = sorted((l.a.x, l.a.y, l.b.x, l.b.y) for l in m.sketch.lines)
    assert before == after                            #  nothing deleted…
    assert len(m.sketch.lines) == 3                   #  and NOTHING SPLIT


def test_a_T_junction_cut_reuses_the_stems_own_point():
    m = SketchModel()
    hh = m.add_line(m.point(0, 0), m.point(60, 0))
    stem_pt = m.point(20, 0)                          # the stem ENDS ON hh:
    stem = m.add_line(stem_pt, m.point(20, 20))       #  a classic T
    trim_piece(m, hh, 40, 0)                          # trim (20..60) away
    left = next(l for l in m.sketch.lines if l not in (stem,))
    assert (left.a.x, left.a.y) == (0.0, 0.0)
    assert left.b is stem_pt                          # the seam IS the stem's
    #                                               end: identity, not contact


def test_an_arc_piece_between_crossing_and_end_disappears():
    m = SketchModel()
    A = m.point(-10, 0); M = m.point(0, 10); B = m.point(10, 0)
    ar = m.sketch.arc(A, M, B)                        # upper semicircle r 10
    m.add_line(m.point(5, -5), m.point(5, 9))         # crosses it at (5, 8.66)
    trim_piece(m, ar, 8, 6)                           # the (cross..B) piece
    assert len(m.sketch.arcs) == 1
    kept = m.sketch.arcs[0]
    assert (kept.a.x, kept.a.y) == (-10.0, 0.0)       # the far piece survives…
    assert math.dist((kept.b.x, kept.b.y), (5.0, math.sqrt(75))) < 1e-9
    #                                            …still EXACTLY on the circle
    assert math.hypot(kept.b.x, kept.b.y) == pytest.approx(10.0, abs=1e-9)


def test_a_circle_cuts_a_line_into_three_and_the_cap_goes():
    m = SketchModel()
    ln = m.add_line(m.point(-20, 0), m.point(20, 0))
    m.sketch.circle(m.point(0, 0), 10.0)              # crossings at ±10
    trim_piece(m, ln, 15, 0)                          # the right cap is under
    segs = sorted((round(l.a.x, 9), round(l.b.x, 9)) for l in m.sketch.lines)
    assert segs == [(-20.0, -10.0), (-10.0, 10.0)]    #  the click: two left
    assert len(m.sketch.circles) == 1                 # the cutter survives


def test_trimming_opens_a_closed_profile_honestly():
    m = SketchModel()
    m.add_rect(m.point(0, 0), m.point(30, 20))
    m.add_line(m.point(15, 20), m.point(15, 30))      # a T-stem on the top
    top = next(e for e in m.sketch.lines
               if abs(e.a.y - 20) < 1e-9 and abs(e.b.y - 20) < 1e-9)
    loops0, _ = m.to_loops()
    assert len(loops0) == 1
    trim_piece(m, top, 25, 20)                        # (stem..corner) piece
    loops1, warns1 = m.to_loops()
    assert loops1 == [] and warns1                    # the profile OPENED:
    #                                               to_loops says so, out loud


def test_a_lonely_circle_is_one_piece_too():
    m = SketchModel()
    c = m.sketch.circle(m.point(0, 0), 5.0)
    assert trim_piece(m, c, 5, 0) is c                # un-splittable means
    assert m.sketch.circles == []                     #  one whole piece


# ---- Rung 3: the trim TOOL (T mode + hover piece + junction extend) ---------

import pytest as _pt                                              # noqa: E402

_qt = _pt.importorskip("PySide6")
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt            # noqa: E402
from PySide6.QtGui import QMouseEvent                             # noqa: E402
from PySide6.QtTest import QTest                                  # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402
from tracer.ui.sketcheditor import SketchCanvas                   # noqa: E402


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


def scr(x, y):                    # world mm -> widget px (scale 4, centre 0)
    return (int(round(300 + 4.0 * x)), int(round(200 - 4.0 * y)))


def _press(c, x, y):
    QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, QPoint(*scr(x, y)))


def _move(c, x, y):
    # the m167 law: this PySide6's QTest.mouseMove never reaches an
    # unshown canvas — the move branch must ride a REAL event.
    p = QPointF(*scr(x, y))
    QApplication.sendEvent(
        c, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                       Qt.NoButton, Qt.NoButton, Qt.NoModifier))


def _release(c, x, y):
    QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, QPoint(*scr(x, y)))


def _key(c, key, mods=Qt.NoModifier):
    QTest.keyClick(c, key, mods)
    qapp = QApplication.instance()
    qapp.processEvents()


def _crossed(m):
    """X crossing at (20, 20): spoke l1, bar l2 — built on the CANVAS'S OWN
    model, NEVER a fresh one: ed.set_model(geom) AUTO-FITS the view
    (scale 4 -> 6.67, centre 0 -> (20,20)) and shatters the scr() map — the
    m167 law: gates speak world mm against the fixture's scale-4 view."""
    a = m.point(0, 0); b = m.point(40, 40)
    c = m.point(0, 40); d = m.point(40, 0)
    l1 = m.add_line(a, b); l2 = m.add_line(c, d)
    return l1, l2, (a, b, c, d)


def test_T_arms_the_trim_tool_and_T_again_lays_it_down(ed):
    _key(ed, Qt.Key_T)
    assert ed._tool == "trim"                     # the key is the TOOL now
    _key(ed, Qt.Key_T)
    assert ed._tool == "select"
    _key(ed, Qt.Key_T)
    assert ed._tool == "trim"
    _key(ed, Qt.Key_Escape)                       # the generic tool exit
    assert ed._tool == "select"


def test_shift_T_still_bites_as_tangent(ed):
    from tracer.core.sketch.constraints import Tangent
    m = ed.model
    ln = m.add_line(m.point(0, 0), m.point(10, 0))
    cir = m.add_circle(m.point(5, 6), 2.0)
    m.solve()
    ed._sel = [ln, cir]
    _key(ed, Qt.Key_T, Qt.ShiftModifier)          # the m23 law, untouched
    assert any(isinstance(c, Tangent) for c in m.sketch.constraints)
    assert ed._tool == "select"                   # tangent never arms trim


def test_hover_previews_the_piece_and_the_click_takes_it(ed):
    m = ed.model
    l1, l2, pts = _crossed(m)
    a, b, c, d = pts
    _key(ed, Qt.Key_T)
    _move(ed, 30, 30)                             # over the (20..40) spoke
    assert ed._trim_hover is not None
    e, lo, hi = ed._trim_hover
    assert e is l1 and (lo, hi) == pytest.approx((0.5, 1.0))   # THE piece
    n_hist = len(ed._hist)
    _press(ed, 30, 30)
    _release(ed, 30, 30)                          # the release commits
    assert len(m.sketch.lines) == 2               # spoke half gone…
    assert l2 in m.sketch.lines                   #  bar byte-still
    assert (c.x, c.y, d.x, d.y) == (0.0, 40.0, 40.0, 0.0)
    assert len(ed._hist) == n_hist + 1            #  one push per click
    assert ed._trim_hover is None                 # preview dies after cut


def test_hovering_never_cuts_the_model(ed):
    """R3's central safety law: the hover preview is a PAINT-ONLY ghost -
    piece_bounds is read-only, so sweeping the cursor splits NOTHING and
    pushes NO history; the model leaves a hover byte-identical."""
    m = ed.model
    _crossed(m)

    def snap():
        return [(l.a.x, l.a.y, l.b.x, l.b.y) for l in m.sketch.lines], \
               [(p.x, p.y) for p in m.sketch.points]

    before, pbefore = snap()
    n_hist = len(ed._hist)
    _key(ed, Qt.Key_T)
    for x in (10, 30, 25):                        # sweep across the pieces…
        _move(ed, x, x)
    assert ed._trim_hover is not None             #  a piece is previewed
    after, pafter = snap()
    assert after == before                        #   every line byte-still…
    assert pafter == pbefore                      #   every point unmoved
    assert len(m.sketch.lines) == 2               #   nothing split
    assert len(ed._hist) == n_hist                #  no undo debt from a hover


def test_a_click_on_the_crossing_warns_and_splits_nothing(ed):
    m = ed.model
    _crossed(m)
    _key(ed, Qt.Key_T)
    n_hist = len(ed._hist)
    _press(ed, 20, 20)                            # EXACTLY on the X…
    _release(ed, 20, 20)
    assert "crossing" in (getattr(ed, "_warn_text", "") or "")
    assert len(m.sketch.lines) == 2               # nothing split, nothing
    assert len(ed._hist) == n_hist                #  deleted, no undo debt


def test_the_tool_extends_a_stub_into_a_true_T(ed):
    m = ed.model
    tip = m.point(10, 0)
    stub = m.add_line(m.point(0, 0), tip)
    m.add_line(m.point(14, -8), m.point(14, 8))
    _key(ed, Qt.Key_T)
    n_hist = len(ed._hist)
    _press(ed, 6, 0)          # mid-stub: clear of the 9px point-snap, yet
    _release(ed, 6, 0)        #  nearer the open tip than the far corner
    assert (tip.x, tip.y) == (14.0, 0.0)          # EXACT onto the wall
    assert len(m.sketch.lines) == 3               # the wall split in two…
    halves = [l for l in m.sketch.lines if l is not stub]
    assert all(tip in (h.a, h.b) for h in halves)  #  ONE Point serves all
    assert len(ed._hist) == n_hist + 1
    ed.undo_op()
    sk2 = ed.model.sketch                          # stale-ref law: re-read
    assert len(sk2.lines) == 2 and len(sk2.points) == 4


def test_a_lonely_line_under_the_tool_still_goes_whole(ed):
    m = ed.model
    l = m.add_line(m.point(0, 0), m.point(10, 0))
    m.add_line(m.point(0, 30), m.point(10, 30))    # far parallel: no future
    _key(ed, Qt.Key_T)
    _press(ed, 5, 0)
    _release(ed, 5, 0)                            # nothing ahead to extend…
    assert len(m.sketch.lines) == 1               #  …so the piece (all of
    assert m.sketch.lines[0] is not l             #   it) is trimmed away


def test_pressing_empty_space_arms_nothing(ed):
    m = ed.model
    _crossed(m)
    _key(ed, Qt.Key_T)
    n_hist = len(ed._hist)
    _press(ed, -25, -25)                          # far from every curve
    _release(ed, -25, -25)
    assert len(m.sketch.lines) == 2
    assert len(ed._hist) == n_hist                # no phantom history
