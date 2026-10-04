"""Sketch entities: points are first-class and shared between lines.

Topology lives in the entity graph (a Line references two Point objects);
the solver only ever sees geometric DOFs. Two separate points that must
touch are joined with a `Coincident` constraint — the sketcher equivalent
of Fusion's snap-to-point.
"""
from __future__ import annotations

import itertools
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
    def __init__(self, a: Point, b: Point):
        super().__init__()
        self.a, self.b = a, b

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
