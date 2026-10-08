"""Qt-free sketch editing model: entities + constraints + interaction ops.

The canvas widget is a thin view over this. All behavior that tests care
about (snapping, dragging with live solve, toggling constraints, profile
extraction) lives here so it can run headless.
"""
from __future__ import annotations

from typing import Iterable

import math
import numpy as np

from .entities import (Point, Line, Circle, Arc, Ellipse, curve_radius,
                       curve_center)
from .constraints import (Angle, AngleBetween, ArcMiddle, Coincident,
                          Collinear, Concentric, Distance, Equal, Fixed,
                          Horizontal, Midpoint, Perpendicular,
                          PointOnCircle, PointOnLine, Parallel, Radius,
                          Symmetry, Tangent, Vertical, make_tangent)
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


def face_axes(normal, owner_u=(1.0, 0.0, 0.0)) -> tuple:
    """M140 rung A: the DERIVED sketch axes of a face — nearest-axis
    law.  U is the candidate axis lying MOST IN the plane (smallest
    |dot| against the normal), projected in and normalised; an owner
    seed may break an exact tie, and world X/Y/Z break every
    remaining one, so the frame is a pure function of the face and
    never of where the cursor landed.  v = n x u keeps the frame
    right-handed (extrude dir = n).  face_basis stays the press-
    pull convention; this one serves the sketch-on-face path."""
    n = np.asarray(normal, float)
    n = n / max(np.linalg.norm(n), 1e-12)
    best = None
    for cand in (np.asarray(owner_u, float), np.array([1.0, 0.0, 0.0]),
                 np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])):
        score = abs(float(cand @ n)) / max(np.linalg.norm(cand), 1e-12)
        u = cand - float(cand @ n) * n
        if np.linalg.norm(u) < 1e-9:
            continue                       # candidate rides the normal
        if best is None or score < best[0] - 1e-9:
            best = (score, u / np.linalg.norm(u))
    u = best[1] if best else np.array([1.0, 0.0, 0.0])
    return u, np.cross(n, u)


def _dim_tag(c) -> str:
    """Type fingerprint for a dimension binding (M89): a binding only
    drives a constraint whose serialized type still matches."""
    return ("D" if isinstance(c, Distance) else
            "DIA" if isinstance(c, Radius) and isinstance(c.curve, Circle)
            else                       # M98: circles speak diameter
            "R" if isinstance(c, Radius) else
            "ang" if isinstance(c, Angle) else
            "angb" if isinstance(c, AngleBetween) else "?")


class SketchModel:
    def __init__(self, plane: str = "XY"):
        self.sketch = Sketch()
        self.name = "Sketch1"
        self.plane = plane
        self.axes: list | None = None      # FACE plane: [u, v] as 3-lists
        self.origin: tuple = (0.0, 0.0, 0.0)
        self.refs: list = []         # projected model edges (M82 refs)
        self.handle: dict | None = None   # M142: live face attachment
        #   {"feature","part"} — captured beside the frozen frame; None
        #   is (and always was) a pure snapshot
        self.host: str = ""          # M152: the CONSTRUCTION-PLANE name
        #   a datum-hosted sketch was opened on ("" everywhere else).
        #   DISPLAY + RELINK + WARN material — NEVER a resolver: the
        #   frame stays the frozen copy (M125 law); the letter is
        #   looked up through the registry, one registry one truth.
        self.dim_exprs: dict = {}    # M89: constraint idx -> {e, t}
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
        a = p0                                  # the given corners are USED,
        b = c.point(x1, y0)                     # so a snapped corner shares
        d = p1                                  # the point it snapped to
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

    def add_offset(self, dist: float, join: str = "mitre") -> list:
        """Fusion's Offset Entities: a parallel copy of the outline at
        signed distance `dist` (outward positive).

        A straight-edged single loop with a MITRE join keeps the
        classic shifted-edge construction — exact corners, no kernel,
        no approximation.  Everything richer rides the manifold
        kernel's CrossSection.offset (M84): rounded joins, sketches
        with arcs/circles/ellipses, outlines with holes and multiple
        loops at once — all with guaranteed-clean self-intersections.
        A lone circle offsets to a TRUE circle.  Curved outlines in a
        crowd offset as their tessellated truth, honestly."""
        d = float(dist)
        if abs(d) < 1e-9:
            return []
        round_join = str(join).lower() in ("round", "smooth")
        flat = (not self.sketch.circles and not self.sketch.arcs
                and not self.sketch.ellipses)

        # ---- the classic exact-mitre path for plain straight loops ----
        if not round_join and flat:
            probe, _pw = self.to_loops()
            if len(probe) == 1 and not probe[0].get("holes"):
                return self._add_offset_mitre(d)

        # ---- one lone circle stays an exact circle ----
        if (len(self.sketch.circles) == 1 and not self.sketch.lines
                and not self.sketch.arcs and not self.sketch.ellipses):
            c = self.sketch.circles[0]
            if c.r + d <= 1e-9:
                raise ValueError("that offset collapses or flips the "
                                 "circle")
            return [self.sketch.circle(c.c, c.r + d)]

        # ---- M84: the manifold kernel's robust offset does the rest ----
        import manifold3d as m3
        loops, _w = self.to_loops()
        rings = []
        for L in loops:
            pts = np.asarray(L["points"], float)
            if len(pts) >= 3:
                sh = 0.5 * float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1)
                                        - np.roll(pts[:, 0], -1)
                                        * pts[:, 1]))
                if sh < 0:                       # the kernel wants CCW
                    pts = pts[::-1]
                rings.append([(float(x), float(y)) for x, y in pts])
        if not rings:
            raise ValueError("Offset found no closed outline to copy")
        try:
            cs = m3.CrossSection(rings, m3.FillRule.EvenOdd)
            out = cs.offset(d, m3.JoinType.Round if round_join
                            else m3.JoinType.Miter, 2.0, 32)
        except Exception as e:
            raise ValueError(f"the offset kernel refused: {e}") from e
        polys = list(out.to_polygons())
        if not polys or out.area() <= 1e-9:
            raise ValueError("that offset collapses or flips the outline")
        made: list = []
        for ring in polys:
            pts = [(float(q[0]), float(q[1])) for q in ring]
            if (len(pts) > 2
                    and math.hypot(pts[0][0] - pts[-1][0],
                                   pts[0][1] - pts[-1][1]) < 1e-9):
                pts = pts[:-1]
            if len(pts) < 3:
                continue
            kp = [self.point(x, y) for x, y in pts]
            for a, b in zip(kp, kp[1:] + kp[:1]):
                if a is not b:
                    made.append(self.add_line(a, b))
        if not made:
            raise ValueError("that offset collapses or flips the outline")
        return made

    def _add_offset_mitre(self, dist: float) -> list:
        """Fusion's Offset Entities (mitre variant): a parallel copy of
        the sketch's single closed line loop at signed distance `dist`
        (outward positive).  Each edge shifts along its own outward
        normal; neighbours meet where the shifted edges cross, so convex
        corners stretch and concave corners close in exactly like the
        original.  Guarded against offsets that collapse or flip the
        outline."""
        d = float(dist)
        loops, warns = self.to_loops()
        if len(loops) != 1:
            raise ValueError("Offset needs exactly one closed outline "
                             "to copy")
        if loops[0].get("holes"):
            raise ValueError("Offset of outlines with holes is not "
                             "supported yet")
        pts = np.asarray(loops[0]["points"], float)
        n = len(pts)
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
        elif ctype in (Parallel, Perpendicular, Equal, Collinear, Midpoint):
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

    def mirror_about(self, axis, ents) -> list:
        """Fusion's Mirror entity tool: static mirrored COPIES of the
        given entities about a line.  Geometry lying ON the axis keeps
        its point — a mirrored wall butts the original through a shared
        Point — and geometry that mirrors onto itself is skipped, so the
        two halves stitch as one profile instead of doubling edges.
        An Ellipse mirrors only about axis-parallel lines: a slanted
        axis would need a rotated ellipse we do not model."""
        ax = np.array([axis.a.x, axis.a.y], dtype=float)
        dv = np.array([axis.b.x - axis.a.x, axis.b.y - axis.a.y],
                      dtype=float)
        L = float(np.hypot(*dv))
        if L < 1e-9:
            return []
        d = dv / L
        H = 2.0 * np.outer(d, d) - np.eye(2)          # Householder

        def mp(p):                                    # mirrored point
            v = np.array([p.x, p.y], dtype=float) - ax
            q = ax + H @ v
            if float(np.hypot(*(q - np.array([p.x, p.y])))) < 1e-9:
                return p                              # on the axis: SHARED
            return self.sketch.point(float(q[0]), float(q[1]))

        c = self.sketch
        made: list = []
        for e in ents:
            if isinstance(e, Line):
                a2, b2 = mp(e.a), mp(e.b)
                if a2 is e.a and b2 is e.b:
                    continue                          # mirrors onto itself
                made.append(c.line(a2, b2))
            elif isinstance(e, Circle):
                cc = mp(e.c)
                if cc is e.c:
                    continue
                made.append(c.circle(cc, e.r))
            elif isinstance(e, Ellipse):
                if abs(d[0]) >= 1e-9 and abs(d[1]) >= 1e-9:
                    continue                          # slanted: unsupported
                cc = mp(e.c)
                if cc is e.c:
                    continue
                made.append(c.ellipse(cc, e.rx, e.ry))
            elif any(e is a for a in c.arcs):
                a2, m2, b2 = mp(e.b), mp(e.m), mp(e.a)  # sweep flips
                if a2 is e.a and m2 is e.m and b2 is e.b:
                    continue
                made.append(c.arc(a2, m2, b2))
        return made

    def delete_entity(self, ent) -> None:
        sk = self.sketch
        sk.constraints = [c for c in sk.constraints
                          if all(e is not ent for e in c.entities())]
        if isinstance(ent, Line):
            sk.lines.remove(ent)
        elif isinstance(ent, Circle):
            sk.circles.remove(ent)
        elif isinstance(ent, Ellipse):
            sk.ellipses.remove(ent)
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

    def apply_dim_params(self, values: dict, scale: float = 1.0) -> list:
        """M89: write parameter-driven formulas into bound dimensions.
        Bindings are {constraint-index: {e: expr, t: type-tag}}; a gone
        constraint or a type that moved under the binding IDLES it (with
        a warning) instead of silently driving the wrong dimension.
        Linear dimensions speak the document's measures and scale to
        stored millimetres; angles never scale.  Returns warnings."""
        from ..params import eval_expr
        warns: list = []
        cons = self.sketch.constraints
        for k in sorted(self.dim_exprs, key=int):
            i = int(k)
            rec = self.dim_exprs[k]
            if not (0 <= i < len(cons)):
                warns.append(f"fx on dimension {i}: constraint is gone")
                continue
            c = cons[i]
            if _dim_tag(c) != rec.get("t"):
                warns.append(f"fx on dimension {i}: type changed — idle")
                continue
            v = float(eval_expr(rec["e"], values))
            if not isinstance(c, (Angle, AngleBetween)):
                v *= float(scale)
            if rec.get("t") == "DIA":
                v *= 0.5        # M98: the fx speaks diameter; the
            c.value = v         # constraint stays a radius
        return warns

    # ---- profile extraction ----------------------------------------------------
    def project(self, verts, faces) -> int:
        """Fusion's Project/Include, honest for a mesh kernel: slice the
        model with THIS sketch's plane and lay the contours under the
        cursor as REFERENCE geometry (refs, not entities — a projected
        circle really IS the 64-gon of the mesh, and minting solver
        points for it would explode the DOF count).  Refs never join
        loops or constraints, but the drawing magnet grabs their
        vertices, so new geometry snaps to real material edges.
        A plane that grazes a boundary falls back a hair (±1 µm) into
        the material — a coplanar cut is undefined.  Returns how many
        contours landed."""
        import trimesh
        M = plane_matrix(self.plane, tuple(self.origin), self.axes)
        o, u, v, n = M[:3, 3], M[:3, 0], M[:3, 1], M[:3, 2]
        mesh = trimesh.Trimesh(np.asarray(verts, float),
                               np.asarray(faces, np.int64), process=False)
        self.refs = []
        for off in (0.0, 1e-3, -1e-3):
            try:
                sec = mesh.section(plane_origin=o + n * off, plane_normal=n)
            except Exception:
                continue
            if sec is None or not len(sec.discrete):
                continue
            rings = []
            for pl in sec.discrete:
                p = np.asarray(pl, float)
                xy = np.column_stack([(p - o) @ u, (p - o) @ v])
                step = np.hypot(*(xy[1:] - xy[:-1]).T)
                xy = xy[np.r_[True, step > 1e-9]]      # weld consecutive
                if len(xy) > 3 and math.hypot(*(xy[0] - xy[-1])) < 1e-9:
                    rings.append({"pts": xy[:-1], "closed": True})
                elif len(xy) >= 2:
                    rings.append({"pts": xy, "closed": False})
            if rings:
                self.refs = rings
                return len(rings)
        return 0

    def import_ops(self, ops, weld: float = 1e-4) -> int:
        """M83: land imported DXF/SVG ops (see tracer.core.import2d) as
        real entities.  Imports arrive with a duplicated vertex at
        every seam — loops only stitch through IDENTITY, so each
        coincident point is welded onto one SHARED Point here.
        Returns the number of entities landed."""
        cache: dict = {}

        def pt(x, y):
            k = (round(x / weld), round(y / weld))
            p = cache.get(k)
            if p is None:
                p = self.point(float(x), float(y))
                cache[k] = p
            return p

        n = 0
        for op in ops:
            t = op[0]
            try:
                if t == "line":
                    self.add_line(pt(*op[1]), pt(*op[2]))
                    n += 1
                elif t == "circle":
                    self.add_circle(pt(*op[1]), float(op[2]))
                    n += 1
                elif t == "arc":
                    self.sketch.arc(pt(*op[1]), pt(*op[2]), pt(*op[3]))
                    n += 1
                elif t == "ellipse":
                    self.sketch.ellipse(pt(*op[1]), float(op[2]),
                                        float(op[3]))
                    n += 1
                elif t == "poly":
                    pts = [pt(x, y) for x, y in op[1]]
                    if op[2] and len(pts) >= 2:
                        if pts[0] is not pts[-1]:
                            pts.append(pts[0])
                    for a, b in zip(pts, pts[1:]):
                        if a is not b:
                            self.add_line(a, b)
                            n += 1
            except Exception:
                continue
        return n

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
            [a for a in self.sketch.arcs if not a.construction],
            [e for e in self.sketch.ellipses
             if not getattr(e, "construction", False)])


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
    for e in model.sketch.ellipses:
        touch(e.c)
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
        elif isinstance(c, Midpoint):
            cons.append({"t": "mid", "p": _add_pt(pts, idx, c.p),
                         "l": m.sketch.lines.index(c.line)})
        elif isinstance(c, Collinear):
            cons.append({"t": "col", "l1": m.sketch.lines.index(c.l1),
                         "l2": m.sketch.lines.index(c.l2)})
    d = {"name": m.name, "plane": m.plane,
         "points": [[p.x, p.y] for p in pts],
         "lines": [[idx[l.a.id], idx[l.b.id], int(l.construction)]
                   for l in m.sketch.lines],
         "circles": [[idx[c.c.id], c.r, int(c.construction)]
                     for c in m.sketch.circles],
         "arcs": [[idx[a.a.id], idx[a.m.id], idx[a.b.id], int(a.construction)]
                  for a in m.sketch.arcs],
         "ellipses": [[idx[e.c.id], e.rx, e.ry, int(e.construction)]
                      for e in m.sketch.ellipses],
         "constraints": cons}
    if m.plane == "FACE":
        d["axes"] = [[float(t) for t in a] for a in m.axes]
        d["origin"] = [float(t) for t in m.origin]
    d["refs"] = [{"pts": [[float(x), float(y)]
                          for x, y in np.asarray(r["pts"], float)],
                  "closed": bool(r["closed"])} for r in m.refs]
    d["handle"] = dict(m.handle) if m.handle else None   # M142
    d["host"] = str(m.host)                 # M152: datum-host witness
    d["dim_exprs"] = {str(int(k)): dict(rec)
                      for k, rec in m.dim_exprs.items()}   # M89 fx
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
    for e in d.get("ellipses", []):
        el = m.sketch.ellipse(pts[e[0]], e[1], e[2])
        el.construction = bool(e[3]) if len(e) > 3 else False
    m.refs = [{"pts": np.asarray(r["pts"], float),
               "closed": bool(r.get("closed", False))}
              for r in d.get("refs", [])]        # pre-M82 files: none
    m.handle = d.get("handle")                   # M142; pre-M142: None
    m.host = d.get("host", "")                   # M152; pre-M152: ""
    m.dim_exprs = {int(k): dict(rec) for k, rec
                   in d.get("dim_exprs", {}).items()}   # M89 fx
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
        elif t == "mid":
            m.constrain(Midpoint(pts[c["p"]], m.sketch.lines[c["l"]]))
        elif t == "col":
            m.constrain(Collinear(m.sketch.lines[c["l1"]],
                                  m.sketch.lines[c["l2"]]))
    return m
