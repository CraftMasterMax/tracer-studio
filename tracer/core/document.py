"""Document model: an ordered feature list that recomputes to a Solid.

Feature history is a *linear* stack for now (each op applies to the
accumulated result). This is deliberately the same serialization shape a
true history tree will replace later — files written today stay readable.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from .geometry import Solid, circle_contour, round_corners
from .rimfillet import rim_fillet
from .sketch.model import frame_matrix, plane_matrix, revolve_matrix

CombineOp = Literal["union", "subtract", "intersect"]


@dataclass
class Feature:
    name: str
    op: CombineOp = "union"
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    suppressed: bool = False


@dataclass
class ImportedFeature(Feature):
    """A solid imported from a mesh/STEP file, stored as triangles.

    Imported bodies are first-class history: they participate in
    Join/Cut/Intersect like sketched features, and they save with the
    document (arrays are JSON — fine for maker-scale meshes)."""
    verts: list = field(default_factory=list)
    faces: list = field(default_factory=list)
    placement: tuple = (0.0, 0.0, 0.0)

    def build(self) -> Solid:
        s = Solid.from_mesh(np.asarray(self.verts, float),
                            np.asarray(self.faces, np.int32))
        return s.translated(self.placement)


@dataclass
class LinearPatternFeature(Feature):
    """Count copies of the source feature's solid offset by a vector —
    Fusion's linear pattern, and the maker's fastest route to hole arrays.
    Inherits the source's op unless overridden."""
    source_uid: str = ""
    vector: tuple = (0.0, 0.0, 0.0)
    count: int = 2


@dataclass
class CircularPatternFeature(Feature):
    """Copies of the source solid rotated CCW about +Z through `center`.
    angle=360 spaces copies evenly without a wrap duplicate; a partial
    angle spans its copies inclusive (Fusion's circular pattern)."""
    source_uid: str = ""
    center: tuple = (0.0, 0.0)
    angle: float = 360.0
    count: int = 6


@dataclass
class PathPatternFeature(Feature):
    """Copies of the source feature walking a drawn sketch path —
    Fusion's pattern-on-path.  `path` is the sampled 2D polyline in
    sketch coordinates, placed into 3D by `plane`/`placement`/`axes`
    exactly like a sweep.  `count` equally spaced stations ride the
    path; copy 0 stays where the source is, the rest follow the path's
    spacing (translation-only, v1).  Start the path at the source."""
    source_uid: str = ""
    path: list = field(default_factory=list)      # [[x, y], ...]
    count: int = 3
    plane: str = "XY"
    placement: tuple = (0.0, 0.0, 0.0)
    axes: list | None = None


@dataclass
class MirrorFeature(Feature):
    """Mirror twin of the source solid across a datum plane: the coordinate
    plane XY/XZ/YZ shifted `offset` mm along its normal. Inherits the
    source's op, so mirroring a Cut gives a matching second Cut — the
    maker's symmetric-lug trick."""
    NORMALS = {"XY": (0.0, 0.0, 1.0), "XZ": (0.0, 1.0, 0.0),
               "YZ": (1.0, 0.0, 0.0)}
    source_uid: str = ""
    plane: str = "YZ"
    offset: float = 0.0


@dataclass
class BodyFilletFeature(Feature):
    """Round (or bevel) every sharp edge of the body built so far.  Two
    engines: circular rims (hole openings, boss tops/bases) are revolved
    quarter-round tools computed purely in the mesh kernel, so they work
    everywhere including stock Windows; straight edges go through the
    OpenCascade bridge when it is available.  It REPLACES the accumulated
    body instead of booleaning with it, so its `op` is unused.  The
    processed mesh is cached (and saved) so recomputes with an unchanged
    source never re-run OCCT, and documents stay readable on machines
    without OpenCascade."""
    radius: float = 2.0
    chamfer: bool = False
    n_rims: int = 0                                   # rims done last run
    src_key: list = field(default_factory=list)     # see apply()
    res_verts: list = field(default_factory=list)
    res_faces: list = field(default_factory=list)

    def _key(self, src: Solid) -> list:
        # trailing 2: M19 added the rim pass; old caches recompute once
        return [round(src.volume, 3), len(src.to_trimesh().faces),
                float(self.radius), bool(self.chamfer), 2]

    def _baked(self) -> Solid:
        return Solid.from_mesh(np.asarray(self.res_verts, float),
                               np.asarray(self.res_faces, np.int32))

    def apply(self, src: Solid) -> Solid:
        key = self._key(src)
        if self.res_faces and self.src_key == key:
            return self._baked()
        from . import step          # lazy: only fillet features touch OCCT
        base, ran_occt, occt_err = src, False, None
        if step.available():
            try:
                base = step.fillet_mesh(src, self.radius,
                                        chamfer=self.chamfer)
                ran_occt = True
            except Exception as exc:
                occt_err = exc      # geometry rejection: rims may still work
        out, n_rims = rim_fillet(base, self.radius, chamfer=self.chamfer)
        self.n_rims = n_rims
        if not ran_occt and n_rims == 0:
            if self.res_faces and not step.available():
                # OCCT vanished (e.g. file moved to a bare machine):
                # keep the baked result. A *geometry* rejection with
                # OCCT present must surface, not silently show stale.
                return self._baked()
            if occt_err is not None:
                raise occt_err
            raise RuntimeError("nothing to round: no circular rims, and "
                               "solid-edge fillets need OpenCascade")
        tm = out.to_trimesh()
        self.src_key = key
        self.res_verts = np.asarray(tm.vertices).tolist()
        self.res_faces = np.asarray(tm.faces).tolist()
        return out


@dataclass
class ExtrudeFeature(Feature):
    """Profile (outer contour + holes) on a sketch plane extruded along
    the plane normal. `sketch` is the serialized SketchModel payload that
    makes this feature re-editable (associative)."""
    outer: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    holes: list = field(default_factory=list)
    height: float = 1.0
    placement: tuple = (0.0, 0.0, 0.0)
    plane: str = "XY"
    axes: list | None = None
    sketch: dict | None = None
    sid: int | None = None
    region: int = 0
    fillet: float = 0.0      # round vertical edges (2D corner fillet, mm)
    chamfer: float = 0.0     # cut vertical edges (2D corner chamfer, mm)

    def _profile(self):
        if self.fillet > 0 or self.chamfer > 0:
            outer = round_corners(self.outer, self.fillet, self.chamfer)
            holes = [round_corners(h, self.fillet, self.chamfer)
                     for h in self.holes]
            return outer, holes
        return self.outer, self.holes

    def build(self) -> Solid:
        outer, holes = self._profile()
        s = Solid.extrude(outer, holes, self.height)
        if self.plane == "XY":
            return s.translated(self.placement)
        m = plane_matrix(self.plane, self.placement, self.axes)
        return s.transformed(m)


@dataclass
class RevolveFeature(Feature):
    """Sketch profile revolved about the sketch's V-axis (the vertical line
    through the sketch origin) — Fusion's Revolve. angle in degrees.
    A profile entirely behind the axis is mirrored; one crossing it is an
    error (Fusion rejects it too)."""
    outer: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    holes: list = field(default_factory=list)
    angle: float = 360.0
    placement: tuple = (0.0, 0.0, 0.0)
    plane: str = "XY"
    axes: list | None = None
    sketch: dict | None = None
    sid: int | None = None
    region: int = 0

    def build(self) -> Solid:
        outer = np.asarray(self.outer, float)
        if outer.size == 0:
            raise ValueError(f"{self.name}: empty profile")
        umin, umax = outer[:, 0].min(), outer[:, 0].max()
        if umin < -1e-6 < umax:
            raise ValueError(
                f"{self.name}: profile crosses the revolve axis "
                "(the sketch's vertical origin line) — move it aside")
        neg = umax <= 1e-6                 # entirely behind the axis: mirror

        def adj(pts):
            pts = np.asarray(pts, float)
            return pts * [[-1.0, 1.0]] if neg else pts.copy()

        s = Solid.revolve(adj(outer), [adj(h) for h in self.holes], self.angle)
        return s.transformed(revolve_matrix(self.plane, self.placement,
                                            self.axes))


@dataclass
class PrimitiveFeature(Feature):
    """Parametric primitive: box(dx,dy,dz), cylinder(radius,height), sphere(radius)."""
    kind: str = "box"
    dims: dict = field(default_factory=dict)
    placement: tuple = (0.0, 0.0, 0.0)

    def build(self) -> Solid:
        if self.kind == "box":
            s = Solid.box(self.dims["dx"], self.dims["dy"], self.dims["dz"])
        elif self.kind == "cylinder":
            s = Solid.cylinder(self.dims["radius"], self.dims["height"])
        elif self.kind == "sphere":
            s = Solid.sphere(self.dims["radius"])
        else:
            raise ValueError(f"unknown primitive kind: {self.kind!r}")
        return s.translated(self.placement)


@dataclass
class HoleFeature(Feature):
    """Parametric hole drilled into the body at a sketch-circle placement.

    Composed entirely of kernel primitives, subtracted as one tool:
    the main cylinder, an optional counterbore cylinder, and an optional
    countersink ring (a triangular wedge revolved 360 degrees about the
    hole axis).  When `thread_pitch` is set the tool also carries a
    helical groove (M49): the drilled cylinder is the tap-drill core and
    the groove opens outward to the ISO crest, giving a real internal
    thread.  `normal` points INTO the material — the command layer
    probes both sides at creation so the cut always bites.  `cidx` is the
    index of the source circle in the sketch so re-editing the sketch
    relocates the hole."""
    center: tuple = (0.0, 0.0, 0.0)
    normal: tuple = (0.0, 0.0, -1.0)
    radius: float = 1.0
    depth: float = 5.0
    through: bool = False
    cut_length: float = 0.0       # actual tool length (through = oversized)
    cb_radius: float = 0.0        # counterbore outer radius (0 = none)
    cb_depth: float = 0.0
    cs_radius: float = 0.0        # countersink outer radius (0 = none)
    cs_angle: float = 90.0        # cone included angle, degrees
    thread_pitch: float = 0.0     # ISO pitch (0 = plain drilled hole)
    thread_len: float = 0.0       # threaded length from the opening
    sketch: dict | None = None
    sid: int | None = None
    cidx: int = 0

    def build(self) -> Solid:
        n = np.asarray(self.normal, float)
        n = n / np.linalg.norm(n)
        # stable in-plane pair: the world axis least parallel to n
        u = np.cross(n, np.eye(3)[int(np.abs(n).argmin())])
        u = u / np.linalg.norm(u)
        m = frame_matrix(u, np.cross(n, u), self.center)   # local +z = INTO material
        L = self.cut_length if self.through else self.depth
        parts = [Solid.cylinder(self.radius, L)]           # 0..L along normal
        if self.cb_radius > self.radius + 1e-9 and self.cb_depth > 0:
            d = min(self.cb_depth, L)
            parts.append(Solid.cylinder(self.cb_radius, d))
        if self.cs_radius > self.radius + 1e-9:
            beta = math.radians(self.cs_angle) / 2.0
            k = min((self.cs_radius - self.radius) / math.tan(beta), L)
            if k > 1e-9:
                parts.append(Solid.revolve(np.array([
                    [self.radius, 0.0], [self.cs_radius, 0.0],
                    [self.radius, k]])))
        if self.thread_pitch > 0 and self.thread_len > 1.2 * self.thread_pitch:
            from .thread import helix_groove
            tl = min(self.thread_len, L)
            if tl > 1.2 * self.thread_pitch:
                parts.append(helix_groove(self.radius, self.thread_pitch, tl))
        tool = parts[0]
        for p in parts[1:]:
            tool = tool.union(p)
        return tool.transformed(m)


@dataclass
class ThreadFeature(Feature):
    """Bolt threads cut onto a cylindrical boss (M49b).  `radius` is the
    boss surface — the thread's major — and the helical groove bites
    pitch/2 deep to the minor, both ends running off the fitted patch so
    the thread starts and exits cleanly.  `center` sits on the boss axis
    at the thread start, `axis` runs along it into the threaded length;
    the command layer fills both in from a picked cylindrical face.
    A body op in spirit, but it IS a plain subtract of the ridge
    cutter, so `build()` + op='subtract' ride the generic path."""
    center: tuple = (0.0, 0.0, 0.0)
    axis: tuple = (0.0, 0.0, 1.0)
    radius: float = 4.0
    pitch: float = 1.0
    length: float = 10.0

    def build(self) -> Solid:
        from .thread import helix_ridge
        n = np.asarray(self.axis, float)
        n = n / np.linalg.norm(n)
        u = np.cross(n, np.eye(3)[int(np.abs(n).argmin())])
        u = u / np.linalg.norm(u)
        m = frame_matrix(u, np.cross(n, u), self.center)
        return helix_ridge(float(self.radius), float(self.pitch),
                           float(self.length)).transformed(m)


@dataclass
class ShellFeature(Feature):
    """Hollow the accumulated body to `thickness` walls, opened at the
    removed planar face(s).  `openings` stores each removed face as
    [point, outward normal] — enough to erode the body and punch a window
    through just that face, leaving higher features intact.  A body op
    (like BodyFilletFeature): it REPLACES the body, so `op` is unused."""
    thickness: float = 2.0
    openings: list = field(default_factory=list)

    def apply(self, src: Solid) -> Solid:
        from .shell import shell_open
        return shell_open(src, self.thickness,
                          [(o[0], o[1]) for o in self.openings])


@dataclass
class SweepFeature(Feature):
    """Sweep a circular profile along a drawn path (v1 profile: circle).
    `path` stores the sampled 2D polyline in sketch coordinates, `closed`
    turns it into an endless ring; stations are always circles so no
    profile orientation is stored."""
    radius: float = 3.0
    path: list = field(default_factory=list)      # [[x, y], ...]
    closed: bool = False
    plane: str = "XY"
    placement: tuple = (0.0, 0.0, 0.0)
    axes: list | None = None
    sketch: dict | None = None
    sid: int | None = None

    def build(self) -> Solid:
        from .sweep import sweep_tube
        s = sweep_tube(self.path, self.radius, self.closed)
        return s.transformed(plane_matrix(self.plane, self.placement,
                                          self.axes))


@dataclass
class LoftFeature(Feature):
    """Blend between closed profiles drawn in two sketches — Fusion Loft.
    Each section carries its own sketch placement (origin planes or
    sketch-on-face) plus its single closed outer loop; the blend runs
    through the resampled, seam-aligned loft engine. v1: two sections,
    no holes inside either profile."""
    sections: list = field(default_factory=list)
    closed: bool = False       # ring loft: last section blends back to first

    def build(self) -> Solid:
        from .loft import loft
        if len(self.sections) < 2:
            raise ValueError(f"{self.name}: a loft needs at least two "
                             "profiles")
        secs = []
        for s in self.sections:
            m4 = plane_matrix(s["plane"], s["placement"], s.get("axes"))
            pts = np.asarray(s["outer"], float)
            h = np.column_stack([pts, np.zeros(len(pts))])
            secs.append(h @ m4[:3, :3].T + m4[:3, 3])
        return loft(secs, n=96, caps=not self.closed, loop=self.closed)


class Document:
    # Origin-plane normals with in-plane bases chosen so u × v = n:
    # a sketch drawn on such a plane extrudes along its own normal.
    _PLANE_BASES = {
        "XY": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        "XZ": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
        "YZ": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    }

    def __init__(self, title: str = "Untitled"):
        self.title = title
        self.units = "mm"
        self.features: list[Feature] = []
        self.planes: list[dict] = []      # construction planes (Construct ▸)
        self._result: Solid | None = None
        self.dirty = False

    # ---- construction planes --------------------------------------------------
    def add_plane(self, base: str, offset: float) -> dict:
        """Offset copy of an origin plane (Fusion's Construct ▸ Plane)."""
        n, u, v = self._PLANE_BASES[base]
        k, taken = 1, {p["name"] for p in self.planes}
        while f"Plane {k}" in taken:
            k += 1
        p = {"name": f"Plane {k}", "base": base, "offset": float(offset),
             "origin": [c * float(offset) for c in n],
             "u": list(u), "v": list(v), "n": list(n)}
        self.planes.append(p)
        self.dirty = True
        return p

    def remove_plane(self, name: str) -> bool:
        before = len(self.planes)
        self.planes = [p for p in self.planes if p["name"] != name]
        if len(self.planes) != before:
            self.dirty = True
            return True
        return False

    # ---- editing -------------------------------------------------------
    def add(self, feature: Feature) -> Feature:
        self.features.append(feature)
        self.dirty = True
        return feature

    def add_plate(self, name, dx, dy, thickness, holes=(), placement=(0, 0, 0)):
        outer = np.array([[0, 0], [dx, 0], [dx, dy], [0, dy]], dtype=float)
        hole_polys = [circle_contour(r, (cx, cy)) for cx, cy, r in holes]
        return self.add(ExtrudeFeature(name=name, outer=outer,
                                       holes=hole_polys, height=thickness,
                                       placement=placement))

    def add_cylinder(self, name, radius, height, center=(0, 0), z=0.0, op="union"):
        return self.add(PrimitiveFeature(
            name=name, op=op, kind="cylinder",
            dims={"radius": radius, "height": height},
            placement=(center[0], center[1], z)))

    def add_linear_pattern(self, name, source: Feature, vector, count, op=None):
        return self.add(LinearPatternFeature(
            name=name, op=op or source.op, source_uid=source.uid,
            vector=tuple(float(v) for v in vector), count=int(count)))

    def add_circular_pattern(self, name, source: Feature, center=(0, 0),
                             angle=360.0, count=6, op=None):
        return self.add(CircularPatternFeature(
            name=name, op=op or source.op, source_uid=source.uid,
            center=(float(center[0]), float(center[1])),
            angle=float(angle), count=int(count)))

    def add_mirror(self, name, source: Feature, plane="YZ", offset=0.0,
                   op=None):
        return self.add(MirrorFeature(
            name=name, op=op or source.op, source_uid=source.uid,
            plane=plane, offset=float(offset)))

    @staticmethod
    def _rotz_about(cx, cy, t) -> "np.ndarray":
        c, s = np.cos(t), np.sin(t)
        m = np.eye(4)
        m[:2, :2] = [[c, -s], [s, c]]
        m[0, 3] = cx - (c * cx - s * cy)        # T(p) R T(-p)
        m[1, 3] = cy - (s * cx + c * cy)
        return m

    # ---- evaluation ------------------------------------------------------
    def recompute(self) -> Solid | None:
        acc: Solid | None = None
        by_uid: dict[str, Solid] = {}
        for f in self.features:
            if f.suppressed:
                continue
            if isinstance(f, LinearPatternFeature):
                src = by_uid.get(f.source_uid)
                if src is None:          # source deleted/suppressed: no-op
                    continue
                solid = None
                for k in range(max(1, int(f.count))):
                    c = src.translated(tuple(v * k for v in f.vector))
                    solid = c if solid is None else solid.union(c)
            elif isinstance(f, PathPatternFeature):
                src = by_uid.get(f.source_uid)
                if src is None:
                    continue
                from .sweep import sample_polyline
                M = plane_matrix(f.plane, f.placement, f.axes)
                ws = [M[:3, :3] @ np.array([x, y, 0.0]) + M[:3, 3]
                      for x, y in sample_polyline(f.path, f.count)]
                solid = None
                for w in ws:
                    c = src.translated(tuple(w - ws[0]))
                    solid = c if solid is None else solid.union(c)
            elif isinstance(f, CircularPatternFeature):
                src = by_uid.get(f.source_uid)
                if src is None:
                    continue
                n = max(1, int(f.count))
                ang = float(f.angle)
                full = abs(abs(ang) - 360.0) < 1e-9
                step = ang / (n if full else max(n - 1, 1))
                solid = None
                for k in range(n):
                    m = self._rotz_about(f.center[0], f.center[1],
                                         math.radians(step * k))
                    c = src.transformed(m)
                    solid = c if solid is None else solid.union(c)
            elif isinstance(f, MirrorFeature):
                src = by_uid.get(f.source_uid)
                if src is None:
                    continue
                n = MirrorFeature.NORMALS.get(f.plane)
                if n is None:
                    raise ValueError(f"unknown mirror plane {f.plane!r}")
                shift = tuple(v * f.offset for v in n)
                solid = src.translated((-shift[0], -shift[1], -shift[2])) \
                            .mirror(n).translated(shift)
            elif isinstance(f, (BodyFilletFeature, ShellFeature)):
                if acc is None:
                    verb = ("fillet" if isinstance(f, BodyFilletFeature)
                            else "shell")
                    raise ValueError(f"{f.name!r} has no body to {verb} yet")
                acc = f.apply(acc)
                by_uid[f.uid] = acc
                continue          # replaces the body; not a boolean operand
            else:
                solid = f.build()
            by_uid[f.uid] = solid
            if acc is None:
                if f.op == "subtract":
                    raise ValueError(f"first feature {f.name!r} cannot be a subtract")
                acc = solid
            elif f.op == "union":
                acc = acc.union(solid)
            elif f.op == "subtract":
                acc = acc.subtract(solid)
            else:
                acc = acc.intersect(solid)
        self._result = acc
        self.dirty = False
        return acc

    @property
    def result(self) -> Solid | None:
        if self._result is None or self.dirty:
            return self.recompute()
        return self._result

    # ---- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        def _feat(f: Feature) -> dict:
            d = {"type": type(f).__name__, "name": f.name, "op": f.op,
                 "uid": f.uid, "suppressed": bool(f.suppressed)}
            if isinstance(f, ExtrudeFeature):
                d.update(outer=np.asarray(f.outer).tolist(),
                         holes=[np.asarray(h).tolist() for h in f.holes],
                         height=float(f.height),
                         fillet=float(f.fillet), chamfer=float(f.chamfer),
                         placement=list(map(float, f.placement)),
                         plane=f.plane, axes=f.axes, sketch=f.sketch,
                         sid=f.sid, region=f.region)
            elif isinstance(f, RevolveFeature):
                d.update(outer=np.asarray(f.outer).tolist(),
                         holes=[np.asarray(h).tolist() for h in f.holes],
                         angle=float(f.angle),
                         placement=list(map(float, f.placement)),
                         plane=f.plane, axes=f.axes, sketch=f.sketch,
                         sid=f.sid, region=f.region)
            elif isinstance(f, PrimitiveFeature):
                d.update(kind=f.kind,
                         dims={k: float(v) for k, v in f.dims.items()},
                         placement=list(map(float, f.placement)))
            elif isinstance(f, ImportedFeature):
                d.update(verts=np.asarray(f.verts).tolist(),
                         faces=np.asarray(f.faces).tolist(),
                         placement=list(map(float, f.placement)))
            elif isinstance(f, LinearPatternFeature):
                d.update(source_uid=f.source_uid,
                         vector=list(map(float, f.vector)),
                         count=int(f.count))
            elif isinstance(f, PathPatternFeature):
                d.update(source_uid=f.source_uid,
                         path=[list(map(float, p)) for p in f.path],
                         count=int(f.count), plane=f.plane,
                         placement=list(map(float, f.placement)),
                         axes=f.axes)
            elif isinstance(f, CircularPatternFeature):
                d.update(source_uid=f.source_uid,
                         center=list(map(float, f.center)),
                         angle=float(f.angle), count=int(f.count))
            elif isinstance(f, MirrorFeature):
                d.update(source_uid=f.source_uid, plane=f.plane,
                         offset=float(f.offset))
            elif isinstance(f, BodyFilletFeature):
                d.update(radius=float(f.radius), chamfer=bool(f.chamfer),
                         n_rims=int(f.n_rims), src_key=f.src_key,
                         res_verts=f.res_verts, res_faces=f.res_faces)
            elif isinstance(f, LoftFeature):
                d.update(closed=bool(f.closed),
                         sections=[{"sid": s.get("sid"), "plane": s["plane"],
                                    "placement": list(map(float,
                                                          s["placement"])),
                                    "axes": s.get("axes"),
                                    "outer": [[float(x), float(y)]
                                              for x, y in s["outer"]]}
                                   for s in f.sections])
            elif isinstance(f, SweepFeature):
                d.update(radius=float(f.radius),
                         path=[[float(x), float(y)] for x, y in f.path],
                         closed=bool(f.closed), plane=f.plane,
                         placement=list(map(float, f.placement)),
                         axes=f.axes, sketch=f.sketch, sid=f.sid)
            elif isinstance(f, ShellFeature):
                d.update(thickness=float(f.thickness),
                         openings=[[[float(x) for x in o[0]],
                                    [float(x) for x in o[1]]]
                                   for o in f.openings])
            elif isinstance(f, HoleFeature):
                d.update(center=list(map(float, f.center)),
                         normal=list(map(float, f.normal)),
                         radius=float(f.radius), depth=float(f.depth),
                         through=bool(f.through),
                         cut_length=float(f.cut_length),
                         cb_radius=float(f.cb_radius),
                         cb_depth=float(f.cb_depth),
                         cs_radius=float(f.cs_radius),
                         cs_angle=float(f.cs_angle),
                         thread_pitch=float(f.thread_pitch),
                         thread_len=float(f.thread_len),
                         sketch=f.sketch, sid=f.sid, cidx=int(f.cidx))
            elif isinstance(f, ThreadFeature):
                d.update(center=list(map(float, f.center)),
                         axis=list(map(float, f.axis)),
                         radius=float(f.radius),
                         pitch=float(f.pitch),
                         length=float(f.length))
            return d
        return {"format": "tracer/document", "version": 2,
                "title": self.title, "units": self.units,
                "features": [_feat(f) for f in self.features],
                "planes": [dict(p) for p in self.planes]}

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        if data.get("format") not in ("tracer/document",
                                      "forma/document") or data.get("version", 0) > 2:
            raise ValueError("not a readable Tracer Studio document")
        doc = cls(title=data.get("title", "Untitled"))
        doc.units = data.get("units", "mm")
        for fd in data.get("features", []):
            t = fd["type"]
            base = dict(op=fd["op"], uid=fd.get("uid") or uuid.uuid4().hex[:8],
                        suppressed=bool(fd.get("suppressed", False)))
            if t == "ExtrudeFeature":
                doc.features.append(ExtrudeFeature(
                    name=fd["name"],
                    outer=np.array(fd["outer"], float),
                    holes=[np.array(h, float) for h in fd["holes"]],
                    height=fd["height"],
                    fillet=float(fd.get("fillet", 0.0)),
                    chamfer=float(fd.get("chamfer", 0.0)),
                    placement=tuple(fd["placement"]),
                    plane=fd.get("plane", "XY"), axes=fd.get("axes"),
                    sketch=fd.get("sketch"),
                    sid=fd.get("sid"), region=fd.get("region", 0), **base))
            elif t == "RevolveFeature":
                doc.features.append(RevolveFeature(
                    name=fd["name"],
                    outer=np.array(fd["outer"], float),
                    holes=[np.array(h, float) for h in fd["holes"]],
                    angle=fd.get("angle", 360.0), placement=tuple(fd["placement"]),
                    plane=fd.get("plane", "XY"), axes=fd.get("axes"),
                    sketch=fd.get("sketch"),
                    sid=fd.get("sid"), region=fd.get("region", 0), **base))
            elif t == "PrimitiveFeature":
                doc.features.append(PrimitiveFeature(
                    name=fd["name"], kind=fd["kind"],
                    dims=fd["dims"], placement=tuple(fd["placement"]), **base))
            elif t == "ImportedFeature":
                doc.features.append(ImportedFeature(
                    name=fd["name"], verts=fd["verts"], faces=fd["faces"],
                    placement=tuple(fd["placement"]), **base))
            elif t == "LinearPatternFeature":
                doc.features.append(LinearPatternFeature(
                    name=fd["name"], source_uid=fd["source_uid"],
                    vector=tuple(fd["vector"]), count=int(fd["count"]), **base))
            elif t == "PathPatternFeature":
                doc.features.append(PathPatternFeature(
                    name=fd["name"], source_uid=fd["source_uid"],
                    path=[list(map(float, p)) for p in fd["path"]],
                    count=int(fd["count"]), plane=fd.get("plane", "XY"),
                    placement=tuple(fd.get("placement", (0., 0., 0.))),
                    axes=fd.get("axes"), **base))
            elif t == "CircularPatternFeature":
                doc.features.append(CircularPatternFeature(
                    name=fd["name"], source_uid=fd["source_uid"],
                    center=tuple(fd["center"]), angle=float(fd["angle"]),
                    count=int(fd["count"]), **base))
            elif t == "MirrorFeature":
                doc.features.append(MirrorFeature(
                    name=fd["name"], source_uid=fd["source_uid"],
                    plane=fd["plane"], offset=float(fd["offset"]), **base))
            elif t == "LoftFeature":
                doc.features.append(LoftFeature(
                    name=fd["name"], closed=bool(fd.get("closed", False)),
                    sections=[{"sid": s.get("sid"),
                               "plane": s.get("plane", "XY"),
                               "placement": list(map(
                                   float, s.get("placement", (0., 0., 0.)))),
                               "axes": s.get("axes"),
                               "outer": [list(map(float, p))
                                         for p in s["outer"]]}
                              for s in fd["sections"]], **base))
            elif t == "SweepFeature":
                doc.features.append(SweepFeature(
                    name=fd["name"], radius=float(fd["radius"]),
                    path=[list(map(float, p)) for p in fd["path"]],
                    closed=bool(fd.get("closed", False)),
                    plane=fd.get("plane", "XY"),
                    placement=tuple(fd.get("placement", (0.0, 0.0, 0.0))),
                    axes=fd.get("axes"), sketch=fd.get("sketch"),
                    sid=fd.get("sid"), **base))
            elif t == "ShellFeature":
                doc.features.append(ShellFeature(
                    name=fd["name"], thickness=float(fd["thickness"]),
                    openings=[(list(map(float, o[0])), list(map(float, o[1])))
                              for o in fd["openings"]], **base))
            elif t == "HoleFeature":
                doc.features.append(HoleFeature(
                    name=fd["name"],
                    center=tuple(fd["center"]), normal=tuple(fd["normal"]),
                    radius=float(fd["radius"]), depth=float(fd["depth"]),
                    through=bool(fd.get("through", False)),
                    cut_length=float(fd.get("cut_length", 0.0)),
                    cb_radius=float(fd.get("cb_radius", 0.0)),
                    cb_depth=float(fd.get("cb_depth", 0.0)),
                    cs_radius=float(fd.get("cs_radius", 0.0)),
                    cs_angle=float(fd.get("cs_angle", 90.0)),
                    thread_pitch=float(fd.get("thread_pitch", 0.0)),
                    thread_len=float(fd.get("thread_len", 0.0)),
                    sketch=fd.get("sketch"), sid=fd.get("sid"),
                    cidx=int(fd.get("cidx", 0)), **base))
            elif t == "ThreadFeature":
                doc.features.append(ThreadFeature(
                    name=fd["name"],
                    center=tuple(fd["center"]), axis=tuple(fd["axis"]),
                    radius=float(fd["radius"]), pitch=float(fd["pitch"]),
                    length=float(fd["length"]), **base))
            elif t == "BodyFilletFeature":
                doc.features.append(BodyFilletFeature(
                    name=fd["name"], radius=float(fd["radius"]),
                    chamfer=bool(fd.get("chamfer", False)),
                    n_rims=int(fd.get("n_rims", 0)),
                    src_key=fd.get("src_key", []),
                    res_verts=fd.get("res_verts", []),
                    res_faces=fd.get("res_faces", []), **base))
            else:
                raise ValueError(f"unknown feature type {t!r}")
        for p in data.get("planes", []):          # pre-M40 files have none
            if p.get("name") and p.get("origin"):
                doc.planes.append({k: p[k] for k in
                                   ("name", "base", "offset", "origin",
                                    "u", "v", "n") if k in p})
        doc.dirty = True
        return doc
