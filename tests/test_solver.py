"""Solver must nail a fully-constrained rectangle from a perturbed start,
detect DOF correctly, and never crash on degenerate input."""
import numpy as np
import pytest

from tracer.core.sketch.solver import Sketch
from tracer.core.sketch.constraints import (Coincident, Distance, Fixed,
                                           Horizontal, Vertical, Radius,
                                           PointOnLine, Parallel)


def _rectangle(rng):
    s = Sketch()
    p0 = s.point(0, 0)
    p1 = s.point(50, 0)
    p2 = s.point(50, 30)
    p3 = s.point(0, 30)
    l0 = s.line(p0, p1)
    l1 = s.line(p1, p2)
    l2 = s.line(p2, p3)
    l3 = s.line(p3, p0)
    # jitter start (p0 stays fixed by constraint)
    for p in (p1, p2, p3):
        p.x += rng.uniform(-8, 8)
        p.y += rng.uniform(-8, 8)
    return s, (p0, p1, p2, p3), (l0, l1, l2, l3)


def test_fully_constrained_rectangle():
    rng = np.random.default_rng(7)
    s, pts, (l0, l1, l2, l3) = _rectangle(rng)
    p0, p1, p2, p3 = pts
    s.constrain(
        Fixed(p0, x=0.0, y=0.0),
        Horizontal(l0), Horizontal(l2),
        Vertical(l1), Vertical(l3),
        Distance(p0, p1, 50.0), Distance(p1, p2, 30.0),
        Distance(p2, p3, 50.0), Distance(p3, p0, 30.0),
    )
    res = s.solve()
    assert res.converged, f"residual {res.residual_norm}"
    assert res.dof == 0
    np.testing.assert_allclose([p0.x, p0.y], [0, 0], atol=1e-7)
    np.testing.assert_allclose([p1.x, p1.y], [50, 0], atol=1e-7)
    np.testing.assert_allclose([p2.x, p2.y], [50, 30], atol=1e-7)
    np.testing.assert_allclose([p3.x, p3.y], [0, 30], atol=1e-7)


def test_underconstrained_reports_dof():
    rng = np.random.default_rng(3)
    s, pts, lines = _rectangle(rng)
    p0, p1, p2, p3 = pts
    s.constrain(Fixed(p0, x=0.0, y=0.0), Horizontal(lines[0]))
    res = s.solve()
    assert res.dof > 0


def test_circle_radius_and_center():
    s = Sketch()
    c = s.point(9.7, 10.4)
    circ = s.circle(c, 5.31)
    s.constrain(Fixed(c, x=10.0, y=10.0), Radius(circ, 5.0))
    res = s.solve()
    assert res.converged
    assert circ.r == pytest.approx(5.0, abs=1e-8)
    assert (c.x, c.y) == pytest.approx((10.0, 10.0), abs=1e-8)


def test_point_on_line():
    s = Sketch()
    a = s.point(0, 0)
    b = s.point(10, 0)
    ln = s.line(a, b)
    p = s.point(3.0, 2.5)
    s.constrain(Fixed(a, x=0.0, y=0.0), Fixed(b, x=10.0, y=0.0),
                Fixed(p, x=3.0), PointOnLine(p, ln))
    res = s.solve()
    assert res.converged
    assert p.y == pytest.approx(0.0, abs=1e-8)


def test_coincident_merges_two_points():
    s = Sketch()
    a = s.point(0, 0)
    b = s.point(5, 5)
    s.constrain(Fixed(a, x=2.0, y=3.0), Coincident(b, a))
    res = s.solve()
    assert res.converged
    assert (b.x, b.y) == pytest.approx((2.0, 3.0), abs=1e-8)


def test_degenerate_zero_length_line_no_crash():
    s = Sketch()
    a = s.point(1, 1)
    b = s.point(1, 1)
    ln = s.line(a, b)
    s.constrain(Fixed(a, x=0.0, y=0.0), Horizontal(ln), Distance(a, b, 4.0))
    res = s.solve()          # must not raise; may or may not converge
    assert isinstance(res.dof, int)
