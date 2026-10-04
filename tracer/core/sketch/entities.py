"""Sketch entities: points are first-class and shared between lines.

Topology lives in the entity graph (a Line references two Point objects);
the solver only ever sees geometric DOFs. Two separate points that must
touch are joined with a `Coincident` constraint — the sketcher equivalent
of Fusion's snap-to-point.
"""
from __future__ import annotations

import itertools
import math

import numpy as np


class Entity:
    _ids = itertools.count(1)

    def __init__(self):
        self.id = next(Entity._ids)

    # parameters: flat float64 array
    def get_params(self) -> np.ndarray: ...
    def set_params(self, p: np.ndarray): ...
    @staticmethod
    def n_params() -> int: ...


class Point(Entity):
    def __init__(self, x: float = 0.0, y: float = 0.0):
        super().__init__()
        self.x, self.y = float(x), float(y)

    def get_params(self): return np.array([self.x, self.y])

    def set_params(self, p): self.x, self.y = float(p[0]), float(p[1])

    @staticmethod
    def n_params(): return 2

    def __repr__(self): return f"Point({self.x:.4g}, {self.y:.4g})"


class Line(Entity):
    def __init__(self, a: Point, b: Point, construction: bool = False):
        super().__init__()
        self.a, self.b = a, b
        self.construction = bool(construction)   # guide geometry: no profile

    def get_params(self): return np.array([self.a.x, self.a.y, self.b.x, self.b.y])

    def set_params(self, p):
        self.a.set_params(p[:2])
        self.b.set_params(p[2:])

    @staticmethod
    def n_params(): return 4

    def __repr__(self): return f"Line({self.a!r} -> {self.b!r})"


class Circle(Entity):
    def __init__(self, center: Point, radius: float):
        super().__init__()
        self.c, self.r = center, float(radius)

    def get_params(self): return np.array([self.c.x, self.c.y, self.r])

    def set_params(self, p):
        self.c.set_params(p[:2])
        self.r = float(p[2])

    @staticmethod
    def n_params(): return 3

    def __repr__(self): return f"Circle(c={self.c!r}, r={self.r:.4g})"


class Arc(Entity):
    """Circular arc through three shared points: start, end and a bulge
    point 'mid' on the curve.  Reusing Point objects means its endpoints
    snap, drag and take coincident constraints exactly like a Line, while
    the profile tessellates the curve into edges.  construction arcs are
    guide geometry (never bound a profile)."""

    def __init__(self, start: Point, mid: Point, end: Point,
                 construction: bool = False):
        super().__init__()
        self.a, self.m, self.b = start, mid, end
        self.construction = bool(construction)

    def get_params(self):
        return np.array([self.a.x, self.a.y, self.m.x, self.m.y,
                         self.b.x, self.b.y])

    def set_params(self, p):
        self.a.set_params(p[:2])
        self.m.set_params(p[2:4])
        self.b.set_params(p[4:])

    @staticmethod
    def n_params(): return 6

    # ---- derived circle --------------------------------------------------
    def circle(self) -> tuple[Point, float]:
        c = _circumcenter((self.a.x, self.a.y), (self.m.x, self.m.y),
                          (self.b.x, self.b.y))
        r = math.hypot(self.a.x - c[0], self.a.y - c[1])
        return c, r

    def angles(self):
        c, _r = self.circle()
        a0 = math.atan2(self.a.y - c[1], self.a.x - c[0])
        am = math.atan2(self.m.y - c[1], self.m.x - c[0])
        a1 = math.atan2(self.b.y - c[1], self.b.x - c[0])
        return c, a0, am, a1

    def sample(self, n: int = 48) -> np.ndarray:
        """Points along the swept arc from start -> mid -> end (n+1 rows)."""
        c, a0, am, a1 = self.angles()
        r = math.hypot(self.a.x - c[0], self.a.y - c[1])
        # sweep from a0 to a1 in the direction that passes through am
        cw = _sweep_through(a0, a1, am)
        ts = np.linspace(0.0, 1.0, n + 1)
        angs = a0 + cw * ts
        return np.column_stack([c[0] + r * np.cos(angs),
                                c[1] + r * np.sin(angs)])

    def __repr__(self):
        c, r = self.circle()
        return f"Arc(c={c[0]:.4g},{c[1]:.4g} r={r:.4g})"


def curve_radius(entity) -> float:
    """Radius of a Circle or of an Arc's circumcircle."""
    if isinstance(entity, Circle):
        return entity.r
    return entity.circle()[1]


def curve_center(entity) -> tuple[float, float]:
    """Centre of a Circle or of an Arc's circumcircle (x, y)."""
    if isinstance(entity, Circle):
        return entity.c.x, entity.c.y
    return entity.circle()[0]


def _circumcenter(p1, p2, p3):
    ax, ay = p1; bx, by = p2; cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:                       # collinear: return mid of p1,p3
        return ((ax + cx) / 2.0, (ay + cy) / 2.0)
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy)


def _sweep_through(a0, a1, am) -> float:
    """Signed sweep (radians) from a0 to a1; positive = CCW.  Chooses the
    direction whose arc actually passes through the mid angle am."""
    two = 2 * math.pi
    ccw = (a1 - a0) % two
    arc_ccw = (am - a0) % two
    if arc_ccw <= ccw:                       # am lies within CCW sweep
        return ccw
    return ccw - two                          # else the CW way round
