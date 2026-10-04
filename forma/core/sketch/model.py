"""Qt-free sketch editing model: entities + constraints + interaction ops.

The canvas widget is a thin view over this. All behavior that tests care
about (snapping, dragging with live solve, toggling constraints, profile
extraction) lives here so it can run headless.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np

from .entities import Point, Line, Circle
from .constraints import (Coincident, Distance, Fixed, Horizontal, Vertical,
                          Radius)
from .solver import Sketch, SolveResult


class SketchModel:
    def __init__(self):
        self.sketch = Sketch()
        self.name = "Sketch1"

    # ---- entity factory --------------------------------------------------
    def point(self, x: float, y: float) -> Point:
        return self.sketch.point(x, y)

    def add_line(self, a: Point, b: Point) -> Line:
        return self.sketch.line(a, b)

    def add_rect(self, p0: Point, p1: Point) -> list[Line]:
        """Corner-to-corner rectangle with shared points + H/V constraints.
        The workhorse tool: most maker sketches are 80% rectangles."""
        x0, y0 = p0.x, p0.y
        x1, y1 = p1.x, p1.y
        if abs(x1 - x0) < 1e-9 or abs(y1 - y0) < 1e-9:
            return []
        c = self.sketch
        a = c.point(x0, y0)
        b = c.point(x1, y0)
        d = c.point(x1, y1)
        e = c.point(x0, y1)
        lines = [c.line(a, b), c.line(b, d), c.line(d, e), c.line(e, a)]
        self.constrain(Horizontal(lines[0]), Horizontal(lines[2]),
                       Vertical(lines[1]), Vertical(lines[3]))
        return lines

    def add_circle(self, center: Point, radius: float) -> Circle:
        return self.sketch.circle(center, radius)

    # ---- constraints ------------------------------------------------------
    def constrain(self, *cs: object):
        self.sketch.constrain(*cs)

    def has(self, ctype: type, ents: tuple) -> bool:
        def touch(c):
            ids = tuple(sorted(getattr(e, "id", None) for e in c.entities()))
            return ids == tuple(sorted(e.id for e in ents))
        return any(isinstance(c, ctype) and touch(c)
                   for c in self.sketch.constraints)

    def toggle(self, ctype: type, ents: tuple):
        """Add or remove a constraint of ctype over ents (Fusion-style toggle)."""
        if self.has(ctype, ents):
            self.sketch.constraints = [
                c for c in self.sketch.constraints
                if not (isinstance(c, ctype) and self._same_entities(c, ents))]
            # re-adding mutates through the shared Sketch list
            return False
        if ctype is Horizontal:
            self.constrain(Horizontal(ents[0]))
        elif ctype is Vertical:
            self.constrain(Vertical(ents[0]))
        elif ctype is Fixed:
            p = ents[0]
            self.constrain(Fixed(p, x=p.x, y=p.y))
        elif ctype is Radius:
            self.constrain(Radius(ents[0], ents[0].r))
        elif ctype is Distance:
            a, b = (ents[0].a, ents[0].b) if isinstance(ents[0], Line) else ents[:2]
            self.constrain(Distance(a, b, math_dist(a, b)))
        return True

    @staticmethod
    def _same_entities(c, ents) -> bool:
        ids = tuple(sorted(e.id for e in c.entities()))
        return ids == tuple(sorted(e.id for e in ents))

    def remove_last(self, ctype: type, ents: tuple):
        self.sketch.constraints = [
            c for c in self.sketch.constraints
            if not (isinstance(c, ctype) and self._same_entities(c, ents))]

    def delete_entity(self, ent) -> None:
        sk = self.sketch
        sk.constraints = [c for c in sk.constraints
                          if all(e is not ent for e in c.entities())]
        if isinstance(ent, Line):
            sk.lines.remove(ent)
        elif isinstance(ent, Circle):
            sk.circles.remove(ent)
        elif isinstance(ent, Point):
            sk.points = [p for p in sk.points if p is not ent]

    # ---- solving -------------------------------------------------------------
    def solve(self, pins: Iterable[Point] = ()) -> SolveResult:
        """Solve; optionally pin points to their CURRENT position (drag keeps
        the grabbed point under the cursor while the rest relaxes)."""
        pins = list(pins)
        temp = [Fixed(p, x=p.x, y=p.y) for p in pins]
        temp_ids = {id(c) for c in temp}      # identity, not dataclass __eq__:
        self.sketch.constraints.extend(temp)  # a user constraint that happens
        try:                                  # to compare equal must survive
            res = self.sketch.solve()
        finally:
            self.sketch.constraints = [c for c in self.sketch.constraints
                                       if id(c) not in temp_ids]
        return res

    # ---- profile extraction ----------------------------------------------------
    def to_loops(self):
        """Return [(outer Nx2 array, area, ccw), ...] from closed loops.

        Shared points define connectivity; circles become 96-gons.
        Non-closed dangling edges are ignored (with a warning tuple).
        """
        from .profile import loops_from_lines_and_circles
        return loops_from_lines_and_circles(self.sketch.lines,
                                            self.sketch.circles)


def math_dist(a: Point, b: Point) -> float:
    return float(np.hypot(b.x - a.x, b.y - a.y))
