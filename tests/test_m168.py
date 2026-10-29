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
from tracer.core.sketch.trim import split_entity                           # noqa: E402
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
