"""Constraint equations, each producing one scalar residual.

Every constraint knows which entities it touches so the solver can build
sparse Jacobian columns. Residuals are written scale-free (÷ a nominal
length) so Newton steps behave for both 0.5 mm and 500 mm sketches.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .entities import Point, Line, Circle

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
    circle: Circle
    value: float

    def entities(self): return [self.circle]

    def residual(self, pos): return (self.circle.r - self.value) / _LEN_SCALE


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


def expand(constraints: list[Constraint]) -> list[Constraint]:
    """Coincident carries two DOFs; split into per-axis rows."""
    out = []
    for c in constraints:
        if isinstance(c, Coincident):
            out.append(Coincident(c.p, c.q, axis=0))
            out.append(Coincident(c.p, c.q, axis=1))
        elif isinstance(c, Fixed):
            if c.x is not None:
                out.append(Fixed(c.p, x=c.x, y=c.y, axis=0))
            if c.y is not None:
                out.append(Fixed(c.p, x=c.x, y=c.y, axis=1))
        else:
            out.append(c)
    return out
