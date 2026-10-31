"""M187 rung 1 - THE MEASURED GAP: a point keeps its distance to a LINE.

LAW-59 [documented OFFSET ASSOCIATION]: an offset copy carries an auto
distance dimension bound parent<->child - delete the dimension and the
distance UNLOCKS. Our offset mints parallel geometry but binds
nothing: drag the parent and the child is simply left behind, and no
number anywhere says how far apart they are. The bind needs a part we
don't own yet: a SIGNED point-to-line distance constraint - the gap
keeper. PointOnLine is its zero case; this rung adds the family.

The residual is the signed cross form (same geometry PointOnLine
already speaks) with the value subtracted; the numerical Jacobian the
M87 machinery already runs does the rest. The constraint round-trips
through the payload as tag "ld" and drops exactly one degree of
freedom - the rank analysis finds it for free.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from tracer.core.sketch.constraints import Fixed, LineDistance        # noqa
from tracer.core.sketch.model import (SketchModel, model_from_dict,     # noqa
                                      model_to_dict)


def _gap(value=2.0, p_y=7.0):
    """A pinned horizontal line and one free point asked to keep a
    signed gap. Only the gap row moves the point."""
    m = SketchModel()
    m.name = "G"
    a = m.point(0.0, 0.0)
    b = m.point(10.0, 0.0)
    ln = m.add_line(a, b)
    p = m.point(5.0, p_y)
    m.constrain(Fixed(a, x=0.0, y=0.0))
    m.constrain(Fixed(b, x=10.0, y=0.0))
    m.constrain(LineDistance(p, ln, value))
    return m, p, ln, a, b


def test_the_gap_pulls_the_point_to_its_signed_distance():
    m, p, ln, a, b = _gap(value=2.0, p_y=7.0)
    r = m.solve()
    assert r.converged and p.y == pytest.approx(2.0, abs=1e-6), \
        "the point lands at the demanded gap from the LINE"
    assert p.x == pytest.approx(5.0, abs=1e-6), \
        "and the gap rules only across the line - it never drags" \
        " along it"


def test_the_gap_survives_a_moved_parent():
    m, p, ln, a, b = _gap(value=2.0, p_y=7.0)
    m.solve()
    for c in m.sketch.constraints:            # the parent is DRAGGED:
        if isinstance(c, Fixed) and c.p is a:   #  its pins re-target to
            c.x, c.y = 0.0, 1.0                 #  y = 1 (an edit like
        if isinstance(c, Fixed) and c.p is b:   #  any dim edit)
            c.x, c.y = 10.0, 1.0
    r = m.solve()
    assert r.converged, "the gap row keeps the system honest"
    assert a.y == pytest.approx(1.0, abs=1e-6) \
        and b.y == pytest.approx(1.0, abs=1e-6)
    assert p.y == pytest.approx(3.0, abs=1e-6), \
        "the child RODE the parent: the gap is kept, not remembered"


def test_a_negative_value_means_the_other_side():
    m, p, ln, a, b = _gap(value=-3.0, p_y=7.0)
    r = m.solve()
    assert r.converged and p.y == pytest.approx(-3.0, abs=1e-6), \
        "signed is SIGNED: -3 lands below the line"


def test_the_gap_round_trips_through_the_payload():
    m, p, ln, a, b = _gap(value=2.0, p_y=7.0)
    m.solve()
    before = (p.x, p.y)
    d = model_to_dict(m)
    ld = [c for c in d["constraints"] if c["t"] == "ld"]
    assert len(ld) == 1 and ld[0]["v"] == 2.0, \
        "the demanded GAP rides the book, not the incident"
    back = model_from_dict(d)
    r = back.solve()
    assert r.converged
    bp = back.sketch.points[2]
    assert (bp.x, bp.y) == pytest.approx(before, abs=1e-6), \
        "and the saved sketch stands where the living one stood"


def test_the_gap_buys_back_exactly_one_dof():
    m = SketchModel()
    m.name = "G"
    a = m.point(0.0, 0.0)
    b = m.point(10.0, 10.0)
    p = m.point(5.0, 7.0)
    ln = m.add_line(a, b)
    m.constrain(Fixed(a, x=0.0, y=0.0))
    m.constrain(Fixed(b, x=10.0, y=10.0))
    r0 = m.solve()
    m.constrain(LineDistance(p, ln, 2.0))
    r1 = m.solve()
    assert r0.dof - r1.dof == 1, \
        "one gap row, one degree returned - the rank says so itself"


# ---- R2: THE OFFSET WELDS ITSELF TO ITS PARENT [LAW-59] ---------------------
# The mitre copy is no longer dumb paste: every child edge keeps its
# parent PARALLEL and holds the signed gap AS MINTED. Editing a parent
# dimension makes the child RIDE; deleting the gap rows UNLOCKS the
# distance (parallel stays - the two halves of the association are
# separate promises, exactly like the documented glyph/dimension pair).

from tracer.core.sketch.constraints import (Distance, Horizontal,        # noqa
                                            Parallel, Vertical)


def _bound(d=5.0):
    """A fully pinned 40x20 rectangle, offset by d, solved."""
    m = SketchModel()
    m.name = "B"
    p0 = m.point(0.0, 0.0)
    p1 = m.point(40.0, 0.0)
    p2 = m.point(40.0, 20.0)
    p3 = m.point(0.0, 20.0)
    ls = [m.add_line(p0, p1), m.add_line(p1, p2),
          m.add_line(p2, p3), m.add_line(p3, p0)]
    m.constrain(Horizontal(ls[0]), Vertical(ls[1]),
                Horizontal(ls[2]), Vertical(ls[3]))
    m.constrain(Fixed(p0, x=0.0, y=0.0))
    w = Distance(p0, p1, 40.0)
    h = Distance(p0, p3, 20.0)
    m.constrain(w, h)
    r0 = m.solve()
    assert r0.converged and r0.dof == 0
    made = m.add_offset(d)
    return m, made, w


def _cons(m, kind):
    return [c for c in m.sketch.constraints if isinstance(c, kind)]


def _signed_gap(p, ln):
    dx, dy = ln.b.x - ln.a.x, ln.b.y - ln.a.y
    L = math.hypot(dx, dy)
    return (dx * (p.y - ln.a.y) - dy * (p.x - ln.a.x)) / L


def test_the_mitre_copy_welds_every_edge():
    m, made, w = _bound()
    assert len(made) == 4
    par = [c for c in _cons(m, Parallel)]
    ld = _cons(m, LineDistance)
    assert len(par) == 4 and len(ld) == 4, \
        "one parallel promise and one gap promise per child edge"
    for c in ld:
        assert abs(abs(c.value) - 5.0) < 1e-6, \
            "the stamped gap is the distance AS MINTED"
    r = m.solve()
    assert r.dof == 0, "the copy adds zero freedom - it is BOUND"


def test_a_fresh_bind_stands_where_it_was_born():
    m, made, w = _bound()
    before = [(c.a.x, c.a.y, c.b.x, c.b.y) for c in made]
    r = m.solve()
    assert r.converged
    for c, (ax, ay, bx, by) in zip(made, before):
        assert (c.a.x, c.a.y, c.b.x, c.b.y) == pytest.approx(
            (ax, ay, bx, by), abs=1e-6), \
            "residuals are zero at birth - the bind changes NOTHING"


def test_the_child_rides_a_moved_parent_dimension():
    m, made, w = _bound()
    m.solve()
    right_before = max(c.a.x for c in made)
    w.value = 60.0                        # the width dimension EDITED
    r = m.solve()
    assert r.converged and r.dof == 0
    for c in _cons(m, LineDistance):      # every gap KEPT
        assert abs(_signed_gap(c.p, c.line) - c.value) < 1e-4
    assert max(c.a.x for c in made) == pytest.approx(
        right_before + 20.0, abs=1e-4), \
        "the copy FOLLOWED its parent - association, not coincidence"


def test_deleting_the_gap_rows_unlocks_the_distance():
    m, made, w = _bound()
    m.solve()
    kept = [c for c in m.sketch.constraints if not isinstance(c,
                                                              LineDistance)]
    m.sketch.constraints[:] = kept        # the dimension is DELETED
    w.value = 60.0
    r = m.solve()
    assert r.converged
    gaps = [abs(_signed_gap(c.a, made[0])) for c in made]
    assert any(abs(g - 5.0) > 1e-2 for g in gaps), \
        "without the gap rows the distance is FREE - unlocked"


def test_the_bind_round_trips_through_the_payload():
    m, made, w = _bound()
    m.solve()
    d = model_to_dict(m)
    assert len([c for c in d["constraints"] if c["t"] == "ld"]) == 4
    assert len([c for c in d["constraints"] if c["t"] == "//"]) == 4
    back = model_from_dict(d)
    r = back.solve()
    assert r.converged and r.dof == 0, \
        "the association rides the book and re-opens fully bound"
