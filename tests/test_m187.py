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
