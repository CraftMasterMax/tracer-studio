"""Constraint equations, each producing one scalar residual.

Every constraint knows which entities it touches so the solver can build
sparse Jacobian columns. Residuals are written scale-free (÷ a nominal
length) so Newton steps behave for both 0.5 mm and 500 mm sketches.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .entities import Point, Line, Circle, curve_center, curve_radius

_LEN_SCALE = 100.0  # mm; keeps residuals dimensionless-ish for solving


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else np.array([1.0, 0.0])


@dataclass
class Constraint:
    def entities(self) -> list: ...
    def residual(self, pos: dict) -> float: ...


@dataclass
class Coincident(Constraint):
    p: Point
    q: Point
    axis: int = 0  # solver expands this into x and y rows

    def entities(self): return [self.p, self.q]

    def residual(self, pos):
        return (self.p.x - self.q.x) if self.axis == 0 else (self.p.y - self.q.y)


@dataclass
class Fixed(Constraint):
    p: Point
    x: float | None = None
    y: float | None = None
    axis: int = 0

    def entities(self): return [self.p]

    def residual(self, pos):
        target = self.x if self.axis == 0 else self.y
        current = self.p.x if self.axis == 0 else self.p.y
        return current - target


@dataclass
class Horizontal(Constraint):
    line: Line

    def entities(self): return [self.line]

    def residual(self, pos): return (self.line.b.y - self.line.a.y) / _LEN_SCALE


@dataclass
class Vertical(Constraint):
    line: Line

    def entities(self): return [self.line]

    def residual(self, pos): return (self.line.b.x - self.line.a.x) / _LEN_SCALE


@dataclass
class Distance(Constraint):
    """Distance between two points (works for line endpoints too)."""
    p: Point
    q: Point
    value: float

    def entities(self): return [self.p, self.q]

    def residual(self, pos):
        return (math.hypot(self.q.x - self.p.x, self.q.y - self.p.y)
                - self.value) / _LEN_SCALE


@dataclass
class Radius(Constraint):
    """Dimensioned radius on a Circle or a three-point Arc. For arcs the
    radius is the circumradius of the shared points, so the constraint
    adds no solver DOF — the numerical Jacobian differentiates through
    the points. Field name ``curve`` covers both entity types."""
    curve: "Circle"          # Circle | Arc
    value: float

    def entities(self): return [self.curve]

    def residual(self, pos):
        e = self.curve
        r = e.r if hasattr(e, "r") else e.circle()[1]   # arc: circumradius
        return (r - self.value) / _LEN_SCALE


@dataclass
class PointOnLine(Constraint):
    p: Point
    line: Line

    def entities(self): return [self.p, self.line]

    def residual(self, pos):
        d = _unit(np.array([self.line.b.x - self.line.a.x,
                            self.line.b.y - self.line.a.y]))
        v = np.array([self.p.x - self.line.a.x, self.p.y - self.line.a.y])
        return float(d[0] * v[1] - d[1] * v[0]) / _LEN_SCALE


@dataclass
class Parallel(Constraint):
    l1: Line
    l2: Line

    def entities(self): return [self.l1, self.l2]

    def residual(self, pos):
        d1 = _unit(np.array([self.l1.b.x - self.l1.a.x, self.l1.b.y - self.l1.a.y]))
        d2 = _unit(np.array([self.l2.b.x - self.l2.a.x, self.l2.b.y - self.l2.a.y]))
        return float(d1[0] * d2[1] - d1[1] * d2[0])


@dataclass
class Perpendicular(Constraint):
    l1: Line
    l2: Line

    def entities(self): return [self.l1, self.l2]

    def residual(self, pos):
        d1 = np.array([self.l1.b.x - self.l1.a.x, self.l1.b.y - self.l1.a.y])
        d2 = np.array([self.l2.b.x - self.l2.a.x, self.l2.b.y - self.l2.a.y])
        n = np.linalg.norm(d1) * np.linalg.norm(d2)
        return float(d1 @ d2 / n) if n > 1e-12 else 0.0


@dataclass
class Equal(Constraint):
    """Same length for two lines, or same radius for two circles/arcs
    (mixed pairs are meaningless — length vs radius — and refused in the
    UI). Arcs differentiate through their three shared points."""
    l1: object          # Line | Circle | Arc
    l2: object          # Line | Circle | Arc

    def entities(self): return [self.l1, self.l2]

    def residual(self, pos):
        a, b = self.l1, self.l2
        if isinstance(a, Line) or isinstance(b, Line):
            d1 = np.linalg.norm([a.b.x - a.a.x, a.b.y - a.a.y])
            d2 = np.linalg.norm([b.b.x - b.a.x, b.b.y - b.a.y])
            return (d1 - d2) / _LEN_SCALE
        return (curve_radius(a) - curve_radius(b)) / _LEN_SCALE


@dataclass
class Concentric(Constraint):
    """Two circles/arcs share their centre. Curve centres are not Point
    entities (an arc's centre is derived), so this is its own constraint;
    expand() splits it into x and y rows, exactly like Coincident."""
    c1: object               # Circle | Arc
    c2: object
    axis: int = 0

    def entities(self): return [self.c1, self.c2]

    def residual(self, pos):
        x1, y1 = curve_center(self.c1)
        x2, y2 = curve_center(self.c2)
        return ((x1 - x2) if self.axis == 0 else (y1 - y2)) / _LEN_SCALE


@dataclass
class PointOnCircle(Constraint):
    """A point lies ON a circle's (or arc's) circumference — the natural
    curve twin of PointOnLine, and the per-vertex lock of the polygon
    tool: n points on a ring + equal chords ⇒ a regular n-gon. Editing
    the ring's Radius grows the whole polygon."""
    p: Point
    curve: object               # Circle | Arc

    def entities(self): return [self.p, self.curve]

    def residual(self, pos):
        cx, cy = curve_center(self.curve)
        d = math.hypot(self.p.x - cx, self.p.y - cy)
        return (d - curve_radius(self.curve)) / _LEN_SCALE


@dataclass
class Symmetry(Constraint):
    """p1 and p2 mirror across the (infinite) axis line: the chord's
    midpoint lies ON the axis (row 0) and the chord is PERPENDICULAR to
    it (row 1). expand() supplies both scalar rows, like Coincident.
    Circles stand in for their centre point at the UI layer."""
    p1: Point
    p2: Point
    axis: Line
    row: int = 0

    def entities(self): return [self.p1, self.p2, self.axis]

    def residual(self, pos):
        d = _unit(np.array([self.axis.b.x - self.axis.a.x,
                            self.axis.b.y - self.axis.a.y]))
        if self.row == 0:
            mx = (self.p1.x + self.p2.x) / 2 - self.axis.a.x
            my = (self.p1.y + self.p2.y) / 2 - self.axis.a.y
            return (d[0] * my - d[1] * mx) / _LEN_SCALE
        chord = np.array([self.p2.x - self.p1.x, self.p2.y - self.p1.y])
        n = float(np.linalg.norm(chord))
        if n < 1e-9:
            return 0.0
        return float(chord[0] * d[0] + chord[1] * d[1]) / n


def _split_line_curve(e1, e2):
    """Return (line, curve) if the pair is line+curve, else (None, None)."""
    if isinstance(e1, Line):
        return e1, e2
    if isinstance(e2, Line):
        return e2, e1
    return None, None


def _unit_normal(line):
    t = _unit(np.array([line.b.x - line.a.x, line.b.y - line.a.y]))
    return np.array([-t[1], t[0]])


@dataclass
class Tangent(Constraint):
    """One-point contact: a line touching a Circle/Arc, or two curves
    touching each other (the round-tip slot and the touching-bolt-circle
    are the maker classics).

    The configuration is frozen at creation — which side of the line the
    centre sits on, external vs internal for two curves — so the solver
    can never jump the contact through to the mirror branch mid-relax.
    For arcs the centre/radius are derived from the shared points, so no
    extra DOF exists; the numerical Jacobian differentiates through them.
    """
    e1: object               # Line | Circle | Arc
    e2: object               # Circle | Arc (Line only as e1 via make below)
    side: float = 1.0        # line-curve: sign of the centre off the line
    internal: bool = False   # curve-curve: one curve inside the other

    def entities(self): return [self.e1, self.e2]

    def residual(self, pos):
        l, cv = _split_line_curve(self.e1, self.e2)
        if l is not None:
            n = _unit_normal(l)
            cx, cy = curve_center(cv)
            g = n[0] * (cx - l.a.x) + n[1] * (cy - l.a.y)
            return (g - self.side * curve_radius(cv)) / _LEN_SCALE
        c1x, c1y = curve_center(self.e1)
        c2x, c2y = curve_center(self.e2)
        r1, r2 = curve_radius(self.e1), curve_radius(self.e2)
        target = abs(r1 - r2) if self.internal else r1 + r2
        return (math.hypot(c2x - c1x, c2y - c1y) - target) / _LEN_SCALE


def make_tangent(e1, e2) -> Tangent:
    """Build Tangent(e1, e2) in whichever branch the current geometry
    lives in. Raises ValueError for pairs tangent cannot relate."""
    from .entities import Arc
    if not isinstance(e1, (Line, Circle, Arc)) or not isinstance(e2, (Line, Circle, Arc)):
        raise ValueError("Tangent applies to lines and circles/arcs")
    if isinstance(e1, Line) and isinstance(e2, Line):
        raise ValueError("Two lines take parallel/perpendicular, not tangent")
    l, cv = _split_line_curve(e1, e2)
    if l is not None:
        n = _unit_normal(l)
        cx, cy = curve_center(cv)
        g = n[0] * (cx - l.a.x) + n[1] * (cy - l.a.y)
        return Tangent(e1, e2, side=1.0 if g >= 0 else -1.0)
    c1x, c1y = curve_center(e1)
    c2x, c2y = curve_center(e2)
    r1, r2 = curve_radius(e1), curve_radius(e2)
    d = math.hypot(c2x - c1x, c2y - c1y)
    internal = abs(d - abs(r1 - r2)) < abs(d - (r1 + r2))
    return Tangent(e1, e2, internal=bool(internal))


@dataclass
class Angle(Constraint):
    """Inclination of a line, radians from +X. Residual is the wrapped
    signed angle error: gradient ±1 everywhere, so — unlike a sin form —
    it never stalls when the line starts exactly 90° from the target.
    make_angle/snapped pick the branch the geometry already occupies, so
    a segment that reads 20° while pointing at 200° never flips."""
    line: Line
    value: float

    def entities(self): return [self.line]

    def measured(self) -> float:
        return math.atan2(self.line.b.y - self.line.a.y,
                          self.line.b.x - self.line.a.x)

    def residual(self, pos):
        return _wrap(self.measured() - self.value)


@dataclass
class AngleBetween(Constraint):
    """Directed angle from l1 to l2, radians; wrapped-error residual."""
    l1: Line
    l2: Line
    value: float

    def entities(self): return [self.l1, self.l2]

    def measured(self) -> float:
        t1 = math.atan2(self.l1.b.y - self.l1.a.y, self.l1.b.x - self.l1.a.x)
        t2 = math.atan2(self.l2.b.y - self.l2.a.y, self.l2.b.x - self.l2.a.x)
        return t2 - t1

    def residual(self, pos):
        return _wrap(self.measured() - self.value)


def _wrap(a: float) -> float:
    """Angle error into (−π, π] — continuous mod 2π, crest at the seam."""
    return (a + math.pi) % (2 * math.pi) - math.pi


def snapped(current: float, want: float) -> float:
    """Pick want or want+π — whichever branch current already lies on, so
    a fresh constraint never drags geometry across a flip and editing a
    value on a flipped line doesn't flip it back."""
    return want if math.cos(current - want) >= 0 else want + math.pi


def make_angle(line, deg: float) -> Angle:
    c = Angle(line, None)
    c.value = snapped(c.measured(), math.radians(deg))
    return c


def make_angle_between(l1, l2, deg: float) -> AngleBetween:
    c = AngleBetween(l1, l2, None)
    c.value = snapped(c.measured(), math.radians(deg))
    return c


@dataclass
class ArcMiddle(Constraint):
    """Pin the arc's bulge point to the middle of its own span (equal
    half-chords). After a corner fillet the circle is fully determined by
    the two tangencies + radius, but the 3rd defining point could still
    slide along it and stretch the drawn arc — this nails it to the
    corner-facing midpoint. (The mirrored far-side solution exists but is
    never reached from a correctly seeded start.)"""
    arc: object                     # Arc

    def entities(self): return [self.arc]

    def residual(self, pos):
        a, m, b = self.arc.a, self.arc.m, self.arc.b
        d1 = math.hypot(m.x - a.x, m.y - a.y)
        d2 = math.hypot(b.x - m.x, b.y - m.y)
        return (d1 - d2) / _LEN_SCALE


def expand(constraints: list[Constraint]) -> list[Constraint]:
    """Coincident carries two DOFs; split into per-axis rows."""
    out = []
    for c in constraints:
        if isinstance(c, Coincident):
            out.append(Coincident(c.p, c.q, axis=0))
            out.append(Coincident(c.p, c.q, axis=1))
        elif isinstance(c, Concentric):
            out.append(Concentric(c.c1, c.c2, axis=0))
            out.append(Concentric(c.c1, c.c2, axis=1))
        elif isinstance(c, Symmetry):
            out.append(Symmetry(c.p1, c.p2, c.axis, row=0))
            out.append(Symmetry(c.p1, c.p2, c.axis, row=1))
        elif isinstance(c, Fixed):
            if c.x is not None:
                out.append(Fixed(c.p, x=c.x, y=c.y, axis=0))
            if c.y is not None:
                out.append(Fixed(c.p, x=c.x, y=c.y, axis=1))
        else:
            out.append(c)
    return out
