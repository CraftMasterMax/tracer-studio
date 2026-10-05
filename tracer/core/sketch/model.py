"""Qt-free sketch editing model: entities + constraints + interaction ops.

The canvas widget is a thin view over this. All behavior that tests care
about (snapping, dragging with live solve, toggling constraints, profile
extraction) lives here so it can run headless.
"""
from __future__ import annotations

from typing import Iterable

import math
import numpy as np

from .entities import Point, Line, Circle, Arc, curve_radius, curve_center
from .constraints import (Angle, AngleBetween, ArcMiddle, Coincident,
                          Concentric, Distance, Equal, Fixed, Horizontal,
                          Perpendicular, PointOnCircle, PointOnLine,
                          Parallel, Radius, Symmetry, Tangent, Vertical,
                          make_tangent)
from .solver import Sketch, SolveResult

# Sketch planes: (u_axis, v_axis) in world coords; extrude normal = u x v.
# Matches Fusion's origin planes: XY n=+Z, XZ n=-Y (front), YZ n=+X (right).
PLANES = {
    "XY": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "XZ": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "YZ": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
}


def plane_matrix(plane: str, origin=(0.0, 0.0, 0.0), axes=None) -> np.ndarray:
    """4x4 local->world: local x,y = sketch (u,v); extrude along local +z.

    For a face sketch the caller supplies axes=[u,v] (world unit vectors);
    origin-plane sketches look up the fixed basis by name."""
    if plane == "FACE" or axes is not None:
        if axes is None:
            raise ValueError("FACE plane requires axes")
        u, v = np.asarray(axes[0], float), np.asarray(axes[1], float)
    else:
        u, v = np.array(PLANES[plane][0]), np.array(PLANES[plane][1])
    return frame_matrix(u, v, origin)


def frame_matrix(u, v, origin=(0.0, 0.0, 0.0)) -> np.ndarray:
    """Local->world from an arbitrary right-handed in-plane basis (u, v, n)."""
    u, v = np.asarray(u, float), np.asarray(v, float)
    n = np.cross(u, v)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2] = u, v, n
    m[:3, 3] = np.array(origin, dtype=float)
    return m


def plane_uv(plane: str, axes=None) -> tuple:
    """Sketch in-plane unit axes (u, v) for a named plane or a face sketch."""
    if plane == "FACE" or axes is not None:
        if axes is None:
            raise ValueError("FACE plane requires axes")
        return np.asarray(axes[0], float), np.asarray(axes[1], float)
    return np.array(PLANES[plane][0], float), np.array(PLANES[plane][1], float)


def revolve_matrix(plane: str, origin=(0.0, 0.0, 0.0), axes=None) -> np.ndarray:
    """Local->world for a REVOLVED solid. The kernel sweeps the profile
    about ITS local z, mapping sketch (u, v) -> (u·cosθ, u·sinθ, v); so the
    world revolve axis is the sketch v-axis (the vertical line through the
    origin), and local columns become [u, v×u, v]."""
    u, v = plane_uv(plane, axes)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2] = u, np.cross(v, u), v
    m[:3, 3] = np.asarray(origin, float)
    return m


def face_basis(normal) -> tuple:
    """Stable (u, v) for a face normal: extrude dir = n, right-handed.
    Reference axis flips only for horizontal faces so X stays predictable."""
    n = np.asarray(normal, float)
    n = n / max(np.linalg.norm(n), 1e-12)
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[2]) > 0.999 else np.array([0.0, 0.0, 1.0])
    u = np.cross(n, ref)
    u /= max(np.linalg.norm(u), 1e-12)
    v = np.cross(n, u)
    return u, v


class SketchModel:
    def __init__(self, plane: str = "XY"):
        self.sketch = Sketch()
        self.name = "Sketch1"
        self.plane = plane
        self.axes: list | None = None      # FACE plane: [u, v] as 3-lists
        self.origin: tuple = (0.0, 0.0, 0.0)
        self.sid = id(self)          # association key while in memory

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

    def add_slot(self, p1: Point, p2: Point, r: float) -> list:
        """Centerline slot: two tangent lines closing two 180° caps,
        stitched through shared points and locked by Radius×2 + Tangent×4
        — the shape stays a true slot under any drag (the endpoints are
        the tangent points, so tangency-at-endpoint follows for free,
        same trick as the corner fillet)."""
        sk = self.sketch
        dx, dy = p2.x - p1.x, p2.y - p1.y
        L = math.hypot(dx, dy)
        if L < 1e-9 or r <= 1e-9:
            return []
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        A1 = sk.point(p1.x + nx * r, p1.y + ny * r)      # cap1 top
        A2 = sk.point(p2.x + nx * r, p2.y + ny * r)      # cap2 top
        A3 = sk.point(p2.x - nx * r, p2.y - ny * r)      # cap2 bottom
        A4 = sk.point(p1.x - nx * r, p1.y - ny * r)      # cap1 bottom
        M1 = sk.point(p2.x + ux * r, p2.y + uy * r)      # cap2 bulge
        M2 = sk.point(p1.x - ux * r, p1.y - uy * r)      # cap1 bulge
        top = sk.line(A1, A2)
        bot = sk.line(A3, A4)
        cap2 = sk.arc(A2, M1, A3)
        cap1 = sk.arc(A4, M2, A1)
        self.constrain(Radius(cap1, r), Radius(cap2, r),
                       make_tangent(top, cap1), make_tangent(top, cap2),
                       make_tangent(bot, cap1), make_tangent(bot, cap2))
        return [top, bot, cap1, cap2]

    def add_polygon(self, cx: float, cy: float, r: float,
                    rot: float = 0.0, n: int = 6) -> list:
        """Regular n-gon on a circumcircle (the hex-nut primitive):
        n shared-endpoint lines around a CONSTRUCTION circle, regularity
        locked by PointOnCircle×n + Equal×(n-1) + one Radius. That's
        2n-1 equations on 2n vertex coords — leaving exactly rotation,
        so dragging spins a true regular polygon, and editing the R
        badge resizes it. The ring is guide geometry: the profile is
        the polygon itself."""
        sk = self.sketch
        if n < 3 or r <= 1e-9:
            return []
        C = sk.point(cx, cy)
        ring = sk.circle(C, r, construction=True)
        pts = [sk.point(cx + r * math.cos(rot + 2 * math.pi * i / n),
                        cy + r * math.sin(rot + 2 * math.pi * i / n))
               for i in range(n)]
        edges = [sk.line(pts[i], pts[(i + 1) % n]) for i in range(n)]
        self.constrain(Radius(ring, r),
                       *[PointOnCircle(p, ring) for p in pts],
                       *[Equal(edges[0], e) for e in edges[1:]])
        return edges

    def add_offset(self, dist: float) -> list:
        """Fusion's Offset Entities (mitre variant): a parallel copy of
        the sketch's single closed line loop at signed distance `dist`
        (outward positive).  Each edge shifts along its own outward
        normal; neighbours meet where the shifted edges cross, so convex
        corners stretch and concave corners close in exactly like the
        original.  Guarded against offsets that collapse or flip the
        outline; refuses arc/circle geometry (v1) and holed outlines."""
        if self.sketch.circles or self.sketch.arcs:
            raise ValueError("Offset works on straight-edge sketches "
                             "for now")
        loops, warns = self.to_loops()
        if len(loops) != 1:
            raise ValueError("Offset needs exactly one closed outline "
                             "to copy")
        if loops[0].get("holes"):
            raise ValueError("Offset of outlines with holes is not "
                             "supported yet")
        pts = np.asarray(loops[0]["points"], float)
        n = len(pts)
        d = float(dist)
        if n < 3 or abs(d) < 1e-9:
            return []

        def cr2(u, v):                       # numpy 2 has no 2-D np.cross
            return u[0] * v[1] - u[1] * v[0]

        # work CCW so the right-hand edge normal points outward
        shoelace = 0.5 * sum(cr2(pts[i], pts[(i + 1) % n])
                             for i in range(n))
        if shoelace < 0:
            pts = pts[::-1]
        offs = []
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            e = b - a
            L = float(np.hypot(*e))
            if L < 1e-9:
                continue
            nu = np.array([e[1], -e[0]]) / L        # outward (right) normal
            offs.append((a + d * nu, b + d * nu))
        m = len(offs)
        if m < 3:
            return []
        corners = []
        for i in range(m):                          # mitre = edge crossings
            (a0, b0), (a1, b1) = offs[i - 1], offs[i]
            e0, e1 = b0 - a0, b1 - a1
            cr = cr2(e0, e1)
            if abs(cr) < 1e-9:                      # collinear neighbours
                corners.append(a1)
                continue
            t = float(cr2(a1 - a0, e1) / cr)
            corners.append(a0 + t * e0)
        area = 0.5 * sum(cr2(corners[i], corners[(i + 1) % m])
                         for i in range(m))
        if area <= 1e-9:
            raise ValueError("this offset collapses or flips the outline "
                             "— choose a smaller distance")
        for i in range(m):
            if np.hypot(*(corners[i] - corners[(i + 1) % m])) < 1e-9:
                raise ValueError("this offset pinches an edge shut — "
                                 "choose a smaller distance")
        sk = self.sketch
        ps = [sk.point(float(p[0]), float(p[1])) for p in corners]
        return [sk.line(ps[i], ps[(i + 1) % m]) for i in range(m)]

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
            self.constrain(Radius(ents[0], curve_radius(ents[0])))
        elif ctype is Distance:
            a, b = (ents[0].a, ents[0].b) if isinstance(ents[0], Line) else ents[:2]
            self.constrain(Distance(a, b, math_dist(a, b)))
        elif ctype in (Parallel, Perpendicular, Equal):
            self.constrain(ctype(ents[0], ents[1]))
        elif ctype is Tangent:
            self.constrain(make_tangent(ents[0], ents[1]))
        elif ctype is Concentric:
            self.constrain(Concentric(ents[0], ents[1]))
        elif ctype is Symmetry:
            self.constrain(Symmetry(ents[0], ents[1], ents[2]))
        elif ctype is PointOnLine:
            self.constrain(PointOnLine(ents[0], ents[1]))
        elif ctype is PointOnCircle:
            self.constrain(PointOnCircle(ents[0], ents[1]))
        else:
            raise ValueError(f"toggle cannot construct {ctype.__name__}")
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
        elif sk.arcs and any(ent is a for a in sk.arcs):
            sk.arcs = [a for a in sk.arcs if a is not ent]
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
        Construction lines are guide geometry and never bound a profile.
        Non-closed dangling edges are ignored (with a warning tuple).
        """
        from .profile import loops_from_lines_and_circles
        return loops_from_lines_and_circles(
            [l for l in self.sketch.lines if not l.construction],
            [c for c in self.sketch.circles
             if not getattr(c, "construction", False)],
            [a for a in self.sketch.arcs if not a.construction])


def math_dist(a: Point, b: Point) -> float:
    return float(np.hypot(b.x - a.x, b.y - a.y))


# ---- serialization (associative sketches depend on this) ----------------

def _point_index(model: SketchModel):
    pts = []
    index = {}
    def touch(p):
        if p.id not in index:
            index[p.id] = len(pts)
            pts.append(p)
    for l in model.sketch.lines:
        touch(l.a); touch(l.b)
    for c in model.sketch.circles:
        touch(c.c)
    for a in model.sketch.arcs:
        touch(a.a); touch(a.m); touch(a.b)
    for p in model.sketch.points:
        touch(p)
    return pts, index


def model_to_dict(m: SketchModel) -> dict:
    pts, idx = _point_index(m)
    cons = []
    for c in m.sketch.constraints:
        if isinstance(c, Horizontal):
            cons.append({"t": "H", "line": m.sketch.lines.index(c.line)})
        elif isinstance(c, Vertical):
            cons.append({"t": "V", "line": m.sketch.lines.index(c.line)})
        elif isinstance(c, Fixed):
            cons.append({"t": "F", "p": _add_pt(pts, idx, c.p),
                         "x": c.p.x, "y": c.p.y})
        elif isinstance(c, Distance):
            cons.append({"t": "D", "p": _add_pt(pts, idx, c.p),
                         "q": _add_pt(pts, idx, c.q), "v": c.value})
        elif isinstance(c, Radius):
            ent = c.curve
            if isinstance(ent, Arc):
                cons.append({"t": "R", "a": m.sketch.arcs.index(ent),
                             "v": c.value})
            else:
                cons.append({"t": "R", "c": m.sketch.circles.index(ent),
                             "v": c.value})
        elif isinstance(c, Coincident):
            cons.append({"t": "==",
                         "p": _add_pt(pts, idx, c.p), "q": _add_pt(pts, idx, c.q)})
        elif isinstance(c, PointOnLine):
            cons.append({"t": "on", "p": _add_pt(pts, idx, c.p),
                         "line": m.sketch.lines.index(c.line)})
        elif isinstance(c, PointOnCircle):
            cons.append({"t": "oc", "p": _add_pt(pts, idx, c.p),
                         "e": _ent_ref(m, c.curve)})
        elif isinstance(c, Parallel):
            cons.append({"t": "//", "l1": m.sketch.lines.index(c.l1),
                         "l2": m.sketch.lines.index(c.l2)})
        elif isinstance(c, Perpendicular):
            cons.append({"t": "perp", "l1": m.sketch.lines.index(c.l1),
                         "l2": m.sketch.lines.index(c.l2)})
        elif isinstance(c, Equal):
            if isinstance(c.l1, Line) and isinstance(c.l2, Line):
                cons.append({"t": "eq", "l1": m.sketch.lines.index(c.l1),
                             "l2": m.sketch.lines.index(c.l2)})
            else:
                cons.append({"t": "eq", "a": _ent_ref(m, c.l1),
                             "b": _ent_ref(m, c.l2)})
        elif isinstance(c, Tangent):
            cons.append({"t": "tan", "a": _ent_ref(m, c.e1),
                         "b": _ent_ref(m, c.e2), "side": c.side,
                         "internal": bool(c.internal)})
        elif isinstance(c, Angle):
            cons.append({"t": "ang", "line": m.sketch.lines.index(c.line),
                         "v": c.value})
        elif isinstance(c, AngleBetween):
            cons.append({"t": "angb", "l1": m.sketch.lines.index(c.l1),
                         "l2": m.sketch.lines.index(c.l2), "v": c.value})
        elif isinstance(c, ArcMiddle):
            cons.append({"t": "am", "arc": m.sketch.arcs.index(c.arc)})
        elif isinstance(c, Concentric):
            cons.append({"t": "cc", "a": _ent_ref(m, c.c1),
                         "b": _ent_ref(m, c.c2)})
        elif isinstance(c, Symmetry):
            cons.append({"t": "sym", "p": _add_pt(pts, idx, c.p1),
                         "q": _add_pt(pts, idx, c.p2),
                         "l": m.sketch.lines.index(c.axis)})
    d = {"name": m.name, "plane": m.plane,
         "points": [[p.x, p.y] for p in pts],
         "lines": [[idx[l.a.id], idx[l.b.id], int(l.construction)]
                   for l in m.sketch.lines],
         "circles": [[idx[c.c.id], c.r, int(c.construction)]
                     for c in m.sketch.circles],
         "arcs": [[idx[a.a.id], idx[a.m.id], idx[a.b.id], int(a.construction)]
                  for a in m.sketch.arcs],
         "constraints": cons}
    if m.plane == "FACE":
        d["axes"] = [[float(t) for t in a] for a in m.axes]
        d["origin"] = [float(t) for t in m.origin]
    return d


def _ent_ref(m, e) -> list:
    """Tagged index reference for Tangent's polymorphic endpoints."""
    if isinstance(e, Line):
        return ["l", m.sketch.lines.index(e)]
    if isinstance(e, Arc):
        return ["a", m.sketch.arcs.index(e)]
    return ["c", m.sketch.circles.index(e)]


def _ent_at(m, ref):
    kind, i = ref
    if kind == "l":
        return m.sketch.lines[i]
    if kind == "a":
        return m.sketch.arcs[i]
    return m.sketch.circles[i]


def _add_pt(pts, idx, p) -> int:
    if p.id in idx:
        return idx[p.id]
    idx[p.id] = len(pts)
    pts.append(p)
    return idx[p.id]


def model_from_dict(d: dict) -> SketchModel:
    m = SketchModel(plane=d.get("plane", "XY"))
    m.name = d.get("name", "Sketch")
    if m.plane == "FACE":
        m.axes = d["axes"]
        m.origin = tuple(d["origin"])
    pts = [m.point(x, y) for x, y in d.get("points", [])]
    for e in d.get("lines", []):
        ln = m.add_line(pts[e[0]], pts[e[1]])
        ln.construction = bool(e[2]) if len(e) > 2 else False
    for e in d.get("circles", []):
        c = m.add_circle(pts[e[0]], e[1])
        c.construction = bool(e[2]) if len(e) > 2 else False
    for e in d.get("arcs", []):
        ar = m.sketch.arc(pts[e[0]], pts[e[1]], pts[e[2]])
        ar.construction = bool(e[3]) if len(e) > 3 else False
    for c in d.get("constraints", []):
        t = c["t"]
        if t == "H":
            m.constrain(Horizontal(m.sketch.lines[c["line"]]))
        elif t == "V":
            m.constrain(Vertical(m.sketch.lines[c["line"]]))
        elif t == "F":
            p = pts[c["p"]]
            m.constrain(Fixed(p, x=c["x"], y=c["y"]))
        elif t == "D":
            m.constrain(Distance(pts[c["p"]], pts[c["q"]], c["v"]))
        elif t == "R":
            ent = (m.sketch.arcs[c["a"]] if "a" in c
                   else m.sketch.circles[c["c"]])
            m.constrain(Radius(ent, c["v"]))
        elif t == "==":
            m.constrain(Coincident(pts[c["p"]], pts[c["q"]]))
        elif t == "on":
            m.constrain(PointOnLine(pts[c["p"]], m.sketch.lines[c["line"]]))
        elif t == "oc":
            m.constrain(PointOnCircle(pts[c["p"]], _ent_at(m, c["e"])))
        elif t == "//":
            m.constrain(Parallel(m.sketch.lines[c["l1"]], m.sketch.lines[c["l2"]]))
        elif t == "perp":
            m.constrain(Perpendicular(m.sketch.lines[c["l1"]],
                                      m.sketch.lines[c["l2"]]))
        elif t == "eq":
            if "l1" in c:                              # legacy line-line form
                m.constrain(Equal(m.sketch.lines[c["l1"]],
                                  m.sketch.lines[c["l2"]]))
            else:
                m.constrain(Equal(_ent_at(m, c["a"]), _ent_at(m, c["b"])))
        elif t == "tan":
            m.constrain(Tangent(_ent_at(m, c["a"]), _ent_at(m, c["b"]),
                                side=c.get("side", 1.0),
                                internal=bool(c.get("internal", False))))
        elif t == "ang":
            m.constrain(Angle(m.sketch.lines[c["line"]], c["v"]))
        elif t == "angb":
            m.constrain(AngleBetween(m.sketch.lines[c["l1"]],
                                     m.sketch.lines[c["l2"]], c["v"]))
        elif t == "am":
            m.constrain(ArcMiddle(m.sketch.arcs[c["arc"]]))
        elif t == "cc":
            m.constrain(Concentric(_ent_at(m, c["a"]), _ent_at(m, c["b"])))
        elif t == "sym":
            m.constrain(Symmetry(pts[c["p"]], pts[c["q"]],
                                 m.sketch.lines[c["l"]]))
    return m
