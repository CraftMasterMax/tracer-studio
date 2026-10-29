"""M170 rung 1 — THE WELD (weld_points: two Points, ONE identity).

The drag magnet catches today and forgets tomorrow: two distinct Points
merely share coordinates, and the next drag drifts them apart. The join
law of this product is IDENTITY (close_corner merges, split_entity
reuses its seam, extend_end drives one Point through stub+joint+halves),
so the weld is the generic form of all three: every entity and EVERY
constraint naming the loser names the survivor after the merge.

The re-home law differs from the CUT's on purpose: a cut splits one
thing into two and a metric on it becomes AMBIGUOUS (drop); a weld fuses
two things into one, so re-homing every fact is never ambiguous - the
Distance the user pinned to that corner FOLLOWS the corner. The one
cleanup: a Coincident whose two sides just became the same Point is
vacuous and dies. keep's coordinates WIN (the magnet target is what the
user aimed at); gone leaves sk.points exactly as close_corner's loser
does. Refusals land BEFORE mutation; no hist push (the caller's gesture
owns the one snapshot the drag already paid).

This rung is kernel-only: the canvas wires the drop in rung 2.
"""
import pytest

pytest.importorskip("PySide6")

from tracer.core.sketch.constraints import Coincident, Distance      # noqa: E402
from tracer.core.sketch.entities import Point                        # noqa: E402
from tracer.core.sketch.model import SketchModel                      # noqa: E402
from tracer.core.sketch.trim import weld_points                       # noqa: E402


def _snap_state(m):
    sk = m.sketch
    return (len(sk.points), len(sk.lines), len(sk.arcs), len(sk.circles),
            len(sk.ellipses), len(sk.constraints),
            [(l.a.x, l.a.y, l.b.x, l.b.y) for l in sk.lines])


def test_two_ends_one_identity():
    """The magnet-caught corner (two Points, one coordinate) becomes ONE
    Point serving both lines; the loser leaves sk.points."""
    m = SketchModel()
    pa, pb, pc, pd = (m.point(0, 0), m.point(5, 5),
                      m.point(10, 0), m.point(5, 5))       # pd rides pb
    l1 = m.add_line(pa, pb)
    l2 = m.add_line(pc, pd)
    out = weld_points(m, pb, pd)
    sk = m.sketch
    assert out is pb and l1.b is pb and l2.b is pb         # ONE identity
    assert pd not in sk.points and len(sk.points) == 3
    assert (l2.b.x, l2.b.y) == (5.0, 5.0)


def test_metric_follows_the_corner():
    """The weld law vs the cut law: fusing is never ambiguous, so the
    Distance that named the loser now names the survivor - re-homed,
    not dropped."""
    m = SketchModel()
    o, p, gone = m.point(0, 0), m.point(8, 0), m.point(8, 0)
    m.add_line(o, p)
    m.constrain(Distance(o, gone, 8.0))
    weld_points(m, p, gone)
    (d,) = [c for c in m.sketch.constraints]
    assert d.q is p and abs(d.value - 8.0) < 1e-12


def test_tautological_coincident_dies_sibling_survives():
    """Coincident(gone, keep) welded itself shut - vacuous, deleted. The
    Coincident onto a THIRD point is a real join: re-homed, alive."""
    m = SketchModel()
    keep, gone, third = m.point(1, 1), m.point(1, 1), m.point(4, 4)
    m.sketch.constraints.append(Coincident(gone, keep))
    m.sketch.constraints.append(Coincident(gone, third))
    weld_points(m, keep, gone)
    (c,) = [c for c in m.sketch.constraints if isinstance(c, Coincident)]
    assert c.p is keep and c.q is third                    # one real join


def test_refusals_land_before_mutation():
    """Self-weld and a stranger Point refuse with the scene byte-kept."""
    m = SketchModel()
    a, b = m.point(0, 0), m.point(3, 4)
    m.add_line(a, b)
    state = _snap_state(m)
    with pytest.raises(ValueError):
        weld_points(m, a, a)                               # self-weld
    with pytest.raises(ValueError):
        weld_points(m, a, Point(9, 9))                     # off-scene twin
    assert _snap_state(m) == state


def test_every_carrier_field_rewires():
    """Line.a, Arc.m, Circle.c, Ellipse.c - the flat identity scan sees
    every Point slot there is (audit: no constraint or entity hides a
    Point inside a composite)."""
    m = SketchModel()
    gone = m.point(2, 2)
    keep = m.point(2, 2)
    s = m.sketch
    s.line(m.point(0, 0), gone)
    s.arc(gone, m.point(1, 4), m.point(3, 1))
    s.circle(gone, 1.5)
    s.ellipse(gone, 2.0, 1.0)
    weld_points(m, keep, gone)
    assert s.lines[0].b is keep and s.arcs[0].a is keep
    assert s.circles[0].c is keep and s.ellipses[0].c is keep
    assert gone not in s.points


def test_the_weld_closes_the_loop_and_the_target_coords_win():
    """The user story in kernel form: two legs fell SHORT of the corner
    (0.5 apart - no eps-weld saves that); the weld lands both on keep's
    coordinates and the profile suddenly has a loop."""
    m = SketchModel()
    pa = m.point(0, 0)
    pb = m.point(10, 10)                                   # magnet target
    pc = m.point(10, 10.5)                                 # the drifted end
    pd = m.point(20, 0)
    m.add_line(pa, pb)
    m.add_line(pd, pc)
    m.add_line(pd, pa)                                     # the base
    loops0, _ = m.to_loops()
    assert loops0 == []                                    # gap: no loop
    weld_points(m, pb, pc)
    assert m.sketch.lines[1].b is pb and pb.y == 10.0      # keep's coords
    loops, _warns = m.to_loops()
    assert len(loops) == 1
