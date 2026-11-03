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
    def __init__(self, a: Point, b: Point, construction: bool = False,
                 centerline: bool = False):
        super().__init__()
        self.a, self.b = a, b
        self._construction = bool(construction)  # guide geometry: no profile
        # M191 R5 [SKT-CENTERLINE-GEOMETRY]: a DECLARED centerline is the
        # sketch's own sentence about symmetry - the vendor's Centerline
        # paints long-dash-dot, carries no profile, AUTO-AXES a later
        # revolve, and a span mirrored across it speaks DIAMETER. The
        # flag rides the line object (like construction), the FILE and
        # undo; a centerline is construction BY LAW - enforced HERE, at
        # every door (constructor, act, file wake), so no mouth can
        # raise the flag and forget the steel.
        self._centerline = False
        if centerline:
            self.centerline = True

    @property
    def construction(self) -> bool:
        return self._construction

    @construction.setter
    def construction(self, v: bool):
        self._construction = bool(v)
        if self._centerline:                 # the law never sleeps: an
            self._construction = True        #   axis stays steel-less

    @property
    def centerline(self) -> bool:
        return self._centerline

    @centerline.setter
    def centerline(self, v: bool):
        self._centerline = bool(v)
        if self._centerline:
            self._construction = True

    def get_params(self): return np.array([self.a.x, self.a.y, self.b.x, self.b.y])

    def set_params(self, p):
        self.a.set_params(p[:2])
        self.b.set_params(p[2:])

    @staticmethod
    def n_params(): return 4

    def __repr__(self): return f"Line({self.a!r} -> {self.b!r})"


class Circle(Entity):
    def __init__(self, center: Point, radius: float,
                 construction: bool = False):
        super().__init__()
        self.c, self.r = center, float(radius)
        self.construction = bool(construction)   # guide geometry: no profile

    def get_params(self): return np.array([self.c.x, self.c.y, self.r])

    def set_params(self, p):
        self.c.set_params(p[:2])
        self.r = float(p[2])

    @staticmethod
    def n_params(): return 3

    def __repr__(self): return f"Circle(c={self.c!r}, r={self.r:.4g})"


class Ellipse(Entity):
    """Axis-aligned ellipse: a shared centre Point plus two radii along
    the sketch's own axes — Fusion's ellipse, drawn centre-first exactly
    like the circle, rx and ry set by where the second click lands."""

    def __init__(self, center: Point, rx: float, ry: float,
                 construction: bool = False):
        super().__init__()
        self.c, self.rx, self.ry = center, float(rx), float(ry)
        self.construction = bool(construction)

    def get_params(self):
        return np.array([self.c.x, self.c.y, self.rx, self.ry])

    def set_params(self, p):
        self.c.set_params(p[:2])
        self.rx, self.ry = float(p[2]), float(p[3])

    @staticmethod
    def n_params(): return 4

    def sample(self, n: int = 96) -> np.ndarray:
        t = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
        return np.column_stack([self.c.x + self.rx * np.cos(t),
                                self.c.y + self.ry * np.sin(t)])

    def __repr__(self):
        return f"Ellipse(c={self.c!r}, rx={self.rx:.4g}, ry={self.ry:.4g})"


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


def _tangent_circle(s, t, e):
    """Solve the unique circle that starts at s heading along unit t and
    passes through e.  Centre on the normal to t at s; |C - e| = |C - s|
    fixes it.  Returns (cx, cy, sweep) - sweep signed CCW from s to e - or
    None when s==e or the drag is (near-)straight along t.  The normal is
    chosen on e's side so the arc BULGES toward the drag: which side the
    cursor lands on is which way the arc bends (the vendor's flip)."""
    sx, sy = s
    vx, vy = e[0] - sx, e[1] - sy
    chord2 = vx * vx + vy * vy
    if chord2 < 1e-18:
        return None
    tl = math.hypot(t[0], t[1])
    if tl < 1e-12:
        return None
    tx, ty = t[0] / tl, t[1] / tl
    nx, ny = -ty, tx                       # unit normal to the entry tangent
    along = vx * nx + vy * ny              # signed off-tangent reach of e
    if abs(along) < 1e-9 * math.sqrt(chord2):   # straight along t -> no arc
        return None
    if along < 0:                          # bend toward e: flip the normal
        nx, ny, along = -nx, -ny, -along
    rho = chord2 / (2.0 * along)           # > 0: centre on e's side
    cx, cy = sx + rho * nx, sy + rho * ny
    ux, uy = sx - cx, sy - cy              # radius vector at s
    wx, wy = e[0] - cx, e[1] - cy          # radius vector at e
    sweep = math.atan2(ux * wy - uy * wx, ux * wx + uy * wy)
    return cx, cy, sweep


def tangent_arc_mid(s, t, e):
    """M193 R1 [SKT-CREATE-LINES, verbatim]: "pause over an end point,
    then click and drag to create an arc segment that is TANGENT to the
    previous line segment."  The arc from s that LEAVES along unit t (so
    it is C1-continuous with the segment before it) and lands on the drag
    end e.  Returns (mid, exit_tangent): mid is the point ON the curve at
    half the signed sweep (the Arc's bulge point) and exit_tangent is the
    unit tangent AT e - t rotated by the sweep - so a following segment
    stays tangent (a chain of arcs flows).  None => keep the straight law."""
    solved = _tangent_circle(s, t, e)
    if solved is None:
        return None
    cx, cy, sweep = solved
    ux, uy = s[0] - cx, s[1] - cy
    hs, hc = math.sin(sweep / 2.0), math.cos(sweep / 2.0)
    mid = (cx + (ux * hc - uy * hs), cy + (ux * hs + uy * hc))
    es, ec = math.sin(sweep), math.cos(sweep)
    return mid, (t[0] * ec - t[1] * es, t[0] * es + t[1] * ec)


def tangent_arc_sample(s, t, e, n: int = 24):
    """The swept tangent arc as an (n+1)-point polyline (start ... end) -
    the DRAG PREVIEW's curve.  None when there is no arc (see the helpers)."""
    solved = _tangent_circle(s, t, e)
    if solved is None:
        return None
    cx, cy, sweep = solved
    r = math.hypot(s[0] - cx, s[1] - cy)
    a0 = math.atan2(s[1] - cy, s[0] - cx)
    out = []
    for i in range(n + 1):
        a = a0 + sweep * (i / n)
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def _sweep_through(a0, a1, am) -> float:
    """Signed sweep (radians) from a0 to a1; positive = CCW.  Chooses the
    direction whose arc actually passes through the mid angle am."""
    two = 2 * math.pi
    ccw = (a1 - a0) % two
    arc_ccw = (am - a0) % two
    if arc_ccw <= ccw:                       # am lies within CCW sweep
        return ccw
    return ccw - two                          # else the CW way round
