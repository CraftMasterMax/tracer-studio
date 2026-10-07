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

from . import params
from .geometry import Solid, circle_contour, round_corners
from .rimfillet import rim_fillet
from .sketch.model import frame_matrix, plane_matrix, revolve_matrix

CombineOp = Literal["union", "subtract", "intersect"]


def _rodrigues(axis, theta):
    """Rotation matrix about an axis by theta (radians) — Rodrigues'
    formula. Frame algebra for datum creation; no scipy needed."""
    k = np.asarray(axis, float)
    k = k / np.linalg.norm(k)
    c, s = math.cos(theta), math.sin(theta)
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]],
                  [-k[1], k[0], 0.0]])
    return np.eye(3) * c + s * K + (1.0 - c) * np.outer(k, k)


def _rot_about_line(origin, direction, theta) -> np.ndarray:
    """4x4 homogeneous rotation by theta about an arbitrary line —
    the matrix form of p ↦ o + R(p − o)."""
    R = _rodrigues(direction, theta)
    m = np.eye(4)
    m[:3, :3] = R
    o = np.asarray(origin, float)
    m[:3, 3] = o - R @ o
    return m


def _trans(vec) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = np.asarray(vec, float)
    return m


def _scale_about(origin, factors) -> np.ndarray:
    """4x4 anisotropic scale about a base point; a scalar factor
    broadcasts to all three axes."""
    k = np.asarray(factors, float)
    if k.shape == ():
        k = np.repeat(float(k), 3)
    o = np.asarray(origin, float)
    m = np.eye(4)
    m[0, 0], m[1, 1], m[2, 2] = k
    m[:3, 3] = o - k * o
    return m


def _lattice_step(feat, doc, idx) -> np.ndarray:
    """Copy transform of a geometric-pattern lattice at grid index
    (i, j): the step (T·R·S) of direction 1 raised to i, composed with
    direction 2's raised to j — a true spiral once rotation or per-step
    scale is nonzero, an oblique grid when they are not."""
    ao, ad = doc.axis_frame(feat.axis or "Z")

    def one(dref, t, r, k):
        return (_trans(doc._dir(dref) * float(t))
                @ _rot_about_line(ao, ad, math.radians(float(r)))
                @ _scale_about(feat.base, [float(k)] * 3))

    i, j = idx
    return (np.linalg.matrix_power(one(feat.d1, feat.t1, feat.r1, feat.k1), i)
            @ np.linalg.matrix_power(one(feat.d2, feat.t2, feat.r2,
                                         feat.k2), j))


@dataclass
class Feature:
    name: str
    op: CombineOp = "union"
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    suppressed: bool = False
    bindings: dict = field(default_factory=dict)  # lever key -> formula
    body: str | None = None    # M104: which body this feature builds in
                               # (None reads as the implicit Body 1)

    def _lever(self, key: str):
        """Where a Change Parameters lever key lives: an entry in the
        dims dict (primitives) or a plain attribute (everything else)."""
        dims = getattr(self, "dims", None)
        if isinstance(dims, dict) and key in dims:
            return dims, key, float(dims[key])
        if hasattr(self, key) and not callable(getattr(self, key)):
            return None, key, getattr(self, key)
        raise params.ParamError(f"{self.name}: no parameter {key!r}")

    def apply_bindings(self, values: dict, scale: float = 1.0) -> None:
        """Write user-parameter formulas into the numeric levers (the
        fx column).  Formulas speak the document's measures, so the
        result scales to stored millimetres; integer levers (pattern
        counts) round to a usable whole."""
        for key, expr in self.bindings.items():
            v = params.eval_expr(expr, values) * scale
            holder, k, cur = self._lever(key)
            if isinstance(cur, int) and not isinstance(cur, bool):
                v = max(1, int(round(v)))
            else:
                v = float(v)
            if holder is None:
                setattr(self, k, v)
            else:
                holder[k] = v


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
    """Copies of the source solid rotated CCW about +Z through `center`
    — or about any NAMED datum axis (M125: `axis` carries "X"/"Y"/"Z" or
    a work axis from the browser; when set, the axis line itself is the
    pivot and `center` steps aside). angle=360 spaces copies evenly
    without a wrap duplicate; a partial angle spans its copies inclusive
    (Fusion's circular pattern)."""
    source_uid: str = ""
    center: tuple = (0.0, 0.0)
    angle: float = 360.0
    count: int = 6
    axis: str = ""


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
class GeometricPatternFeature(Feature):
    """Copies of the source solid on a T·R·S lattice (M126): two
    independent step transforms — each translate + rotate about a named
    axis + scale about the base point — raised to the copy's index, so
    Fusion's geometric pattern (the spiral of shrinking copies) needs
    no face identity, only frames. Directions and pivot accept NAMED
    datums (an axis name resolves to its line) or raw vectors.
    n2=1 gives the single-direction lattice."""
    source_uid: str = ""
    axis: str = "Z"                  # rotation/scale pivot (named datum)
    base: tuple = (0.0, 0.0, 0.0)    # translate/scale anchor ("base point")
    d1: object = (1.0, 0.0, 0.0)     # vector or named axis
    n1: int = 3
    t1: float = 10.0                 # mm per step along d1
    r1: float = 0.0                  # degrees per step about `axis`
    k1: float = 1.0                  # scale factor per step (> 0)
    d2: object = (0.0, 1.0, 0.0)
    n2: int = 1
    t2: float = 0.0
    r2: float = 0.0
    k2: float = 1.0
    MAX_COPIES = 4096


@dataclass
class ScaleFeature(Feature):
    """Resize one solid about a base point (M126) — the N=1 degenerate
    of the geometric-pattern lattice: uniform k or per-axis (kx,ky,kz).
    A negative factor mirrors too; the mesh round-trip fixes winding.
    Inherits the source's op, like mirror."""
    source_uid: str = ""
    base: tuple = (0.0, 0.0, 0.0)
    factors: tuple = (1.0, 1.0, 1.0)


@dataclass
class CoilFeature(Feature):
    """M127 coil-v1: a helical ridge (spring, boss thread) — circular
    or square section riding a helix about a NAMED axis (M125 store),
    lofted through dense ring stations with honest abrupt ends. Size
    schema is the vendor's classic two-of-three solved forward: height
    is turns x pitch. Internal modeled cut-threads are deliberately
    NOT offered: standards tooling itself recommends decoration there,
    and near-tangent helical booleans are how kernels die."""
    axis: str = "Z"                  # helix axis (named datum)
    base: tuple = (0.0, 0.0, 0.0)    # helix start point
    diameter: float = 8.0            # helix CENTER diameter (on-center)
    pitch: float = 1.25
    turns: float = 6.0
    hand: str = "right"              # or "left"
    section: str = "circular"        # or "square"
    size: float = 1.0                # section circumscribed diameter

    @property
    def height(self) -> float:
        return self.turns * self.pitch


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
    taper: float = 0.0       # draft angle in degrees; + widens as it goes
    symmetric: bool = False  # straddle the sketch plane (Fusion extent)

    def _profile(self):
        if self.fillet > 0 or self.chamfer > 0:
            outer = round_corners(self.outer, self.fillet, self.chamfer)
            holes = [round_corners(h, self.fillet, self.chamfer)
                     for h in self.holes]
            return outer, holes
        return self.outer, self.holes

    def _loft_taper(self, outer, holes) -> Solid:
        """Tapered wall (Fusion's draft): the outer skin lofts to the
        profile offset outward by h·tan(taper); each hole lofts to its
        shrunken self as a cutter extended past both caps.  Areas grow
        quadratically with z, so the lofted solid tracks the exact
        prismatoid to tessellation tolerance."""
        import math

        from shapely.geometry import Polygon

        from .loft import loft
        d = math.tan(math.radians(float(self.taper))) * self.height

        def sgn(a):
            return float(np.sum(a[:, 0] * np.roll(a[:, 1], -1)
                                - np.roll(a[:, 0], -1) * a[:, 1]))

        def off(p2, dist):
            poly = Polygon(np.asarray(p2, float))
            q = poly.buffer(dist, join_style=2, mitre_limit=50.0)
            if q.is_empty:                     # feature swallowed to a
                c = poly.representative_point()  # point — a stub cutter
                r = 0.05                       # still cuts cleanly
                stub = [(c.x - r, c.y - r), (c.x + r, c.y - r),
                        (c.x + r, c.y + r), (c.x - r, c.y + r)]
                if sgn(np.asarray(p2, float)) < 0:
                    stub = stub[::-1]
                return stub
            if q.geom_type == "MultiPolygon":
                q = max(q.geoms, key=lambda g: g.area)
            grown = np.asarray(q.exterior.coords[:-1], float)
            # GEOS may hand back the opposite winding — the loft engine
            # needs both rings turning the same way or it twists
            if sgn(grown) * sgn(np.asarray(p2, float)) < 0:
                grown = grown[::-1]
            return list(grown)

        def ring(p2, z):
            a = np.asarray(p2, float)
            return np.column_stack([a, np.full(len(a), z)])

        h = float(self.height)
        body = loft([ring(outer, 0.0), ring(off(outer, d), h)])
        step = d / h                            # radial drift per mm
        for hole in holes:
            # a +taper WIDENS material, so the hole shrinks going up:
            # buffer(-d) at the top; extended 1 mm past each cap along
            # the same slope for a clean through-cut
            cutter = loft([ring(off(hole, step), -1.0),
                           ring(off(hole, -(d + step)), h + 1.0)])
            body = body.subtract(cutter)
        return body

    def build(self) -> Solid:
        outer, holes = self._profile()
        if abs(float(self.taper)) < 1e-9:
            s = Solid.extrude(outer, holes, self.height)
        else:
            s = self._loft_taper(outer, holes)
        if self.symmetric:            # Fusion's symmetric extent: the
            s = s.translated((0.0, 0.0,   # profile grows evenly about
                              -float(self.height) / 2.0))  # its plane
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
    """Parametric primitive: box(dx,dy,dz), cylinder(radius,height),
    cone(radius_bottom,radius_top,height), torus(major,minor),
    sphere(radius)."""
    kind: str = "box"
    dims: dict = field(default_factory=dict)
    placement: tuple = (0.0, 0.0, 0.0)

    def build(self) -> Solid:
        if self.kind == "box":
            s = Solid.box(self.dims["dx"], self.dims["dy"], self.dims["dz"])
        elif self.kind == "cylinder":
            s = Solid.cylinder(self.dims["radius"], self.dims["height"])
        elif self.kind == "cone":
            s = Solid.cone(self.dims["radius_bottom"],
                           self.dims["radius_top"], self.dims["height"])
        elif self.kind == "torus":
            s = Solid.torus(self.dims["major"], self.dims["minor"])
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
class SplitFeature(Feature):
    """Split Body (M51): trim the accumulated body flush with a plane —
    Fusion's most common split, "cut away one half".  The plane runs
    through `origin` with `normal` pointing at the side that goes away
    (flip reverses which half survives).  A body op like Shell: it
    REPLACES the body, so `op` is unused; being a feature, the trim
    stays parametric — move `origin` and the cut follows."""
    origin: tuple = (0.0, 0.0, 0.0)
    normal: tuple = (0.0, 0.0, 1.0)
    flip: bool = False

    def apply(self, src: Solid) -> Solid:
        from .split import split_solid
        return split_solid(src, self.origin, self.normal, self.flip)


@dataclass
class MoveFeature(Feature):
    """Move Body (M53): shift the whole accumulated body by a vector —
    what dragging the triad commits.  A body op like Shell: it REPLACES
    the body, so `op` is unused; being a feature, the shift stays
    parametric — edit the vector and the body slides.  copy=True is
    Fusion's Copy (Ctrl-drag): the shifted twin JOINS the body."""
    vec: tuple = (0.0, 0.0, 0.0)
    copy: bool = False

    def apply(self, src: Solid) -> Solid:
        moved = src.translated(tuple(float(v) for v in self.vec))
        return moved.union(src) if self.copy else moved


@dataclass
class RotateFeature(Feature):
    """Rotate Body (M55): spin the whole accumulated body `angle_deg`
    around the axis (through `center`, direction `axis`) — what dragging
    a triad ring commits.  Body op like Move; right-hand rule, z-up
    like every other Tracer angle."""
    center: tuple = (0.0, 0.0, 0.0)
    axis: tuple = (0.0, 0.0, 1.0)
    angle_deg: float = 0.0
    copy: bool = False

    def apply(self, src: Solid) -> Solid:
        from .geometry import rotation_about
        turned = src.transformed(rotation_about(
            self.center, self.axis, np.deg2rad(float(self.angle_deg))))
        return turned.union(src) if self.copy else turned


@dataclass
class CombineFeature(Feature):
    """Combine (M64): Join / Cut / Intersect the whole body with a
    placed primitive tool — Fusion's Combine, tool built on the spot.
    `center` is the tool's bounding-box centre; the op picks the
    boolean.  Parametric: Change Parameters speaks for it too."""
    tool: str = "box"
    dims: dict = field(default_factory=dict)
    center: tuple = (0.0, 0.0, 0.0)

    def build_tool(self) -> Solid:
        d = self.dims
        if self.tool == "cylinder":
            s = Solid.cylinder(float(d.get("radius", 5.0)),
                               float(d.get("height", 10.0)))
        elif self.tool == "cone":
            s = Solid.cone(float(d.get("radius_bottom", 8.0)),
                           float(d.get("radius_top", 3.0)),
                           float(d.get("height", 15.0)))
        elif self.tool == "torus":
            s = Solid.torus(float(d.get("major", 15.0)),
                            float(d.get("minor", 4.0)))
        elif self.tool == "sphere":
            s = Solid.sphere(float(d.get("radius", 5.0)))
        else:
            s = Solid.box(float(d.get("dx", 10.0)),
                          float(d.get("dy", 10.0)),
                          float(d.get("dz", 10.0)))
        lo, hi = s.bounding_box
        c = (np.asarray(hi, float) + np.asarray(lo, float)) / 2.0
        return s.translated(np.asarray(self.center, float) - c)

    def apply(self, src: Solid) -> Solid:
        t = self.build_tool()
        if self.op == "subtract":
            return src.subtract(t)
        if self.op == "intersect":
            return src.intersect(t)
        return src.union(t)


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
class ThickenFeature(Feature):
    """M99: a sketch's open chains, thickened to a wall of `thickness`
    (butt caps, round joins) and extruded `depth` along the plane
    normal. `paths` carries the sampled polylines in sketch
    coordinates — frozen, sweep-style: re-run Thicken to re-extract."""
    thickness: float = 2.0
    depth: float = 5.0
    paths: list = field(default_factory=list)   # [[[x, y], ...], ...]
    plane: str = "XY"
    placement: tuple = (0.0, 0.0, 0.0)
    axes: list | None = None
    sketch: dict | None = None
    sid: int | None = None

    def build(self) -> Solid:
        from .thicken import thicken_solids
        parts = thicken_solids(self.paths, self.thickness, self.depth)
        if not parts:
            raise ValueError("Thicken: the sketch has no open chain left")
        s = parts[0]
        for p in parts[1:]:
            s = s.union(p)
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


@dataclass
class InterlockFeature(Feature):
    """M121 — one side of an interlock pair: Fusion's Plastic-extension
    family (Boss · Snap Fit · Rest · Lip) shipped free.  `role` 'carry'
    unions the feature into the body that CARRIES it, below the
    interface plane; 'mate' subtracts the mating tool from the partner
    body above it (Rest is one-sided: a stepped seat only).  The
    interface plane is local z=0 raised to `plane_z` at (x, y);
    `flip` mirrors it across that plane — Fusion's Flip checkbox, and
    the two bodies' roles are exchanged with it.  `params` is the
    kind's analytic vocabulary, the same keywords core/interlock.py
    takes (shaft_d, length, outer_w … plus clearance)."""
    kind: str = "boss"
    role: str = "carry"
    center: tuple = (0.0, 0.0)
    plane_z: float = 0.0
    flip: bool = False
    params: dict = field(default_factory=dict)

    def build(self) -> Solid:
        from . import interlock
        tool = interlock.tools(self.kind, **self.params)[self.role]
        if tool is None:
            raise ValueError(f"{self.name}: {self.kind} has no "
                             f"{self.role} tool")
        if self.flip:
            tool = tool.mirror((0.0, 0.0, 1.0))
        return tool.translated((float(self.center[0]),
                                float(self.center[1]),
                                float(self.plane_z)))


@dataclass
class InterferenceFeature(Feature):
    """M122 (assembly phase 1) — a BODY made of a clash: the exact
    intersection of two other bodies.  Fusion reports interference and
    discards the geometry; here the clash is a first-class stream, so
    it recomputes while the parts move (kinematic placement included)
    and prints as a red 3D "where do I hurt" map.  Both source bodies
    must build before this feature in the stream (add_interference
    guarantees it).  An empty clash is an EMPTY body, never an
    error — the part audit lives in core/interference.pairs()."""
    body_a: str = ""
    body_b: str = ""

    def build(self) -> Solid:                 # recompute special-cases it
        raise RuntimeError("InterferenceFeature builds from its sources")


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
        self.axes: list[dict] = []        # work axes (M125 datum store)
        self.appearance: dict | None = None   # Appearance ▸ material paint
        self.params: dict = {}                # user parameters (M81)
        self.configs: dict = {}               # M91: name -> {param: raw}
        self.active_config: str | None = None # M91: the one overlaying
        self.drawings: list = []              # M93: [{name, page}]
        self.rollback_to: int | None = None   # M88 rubber band (view state)
        self.bodies: list[dict] = []          # M104: [{name, visible}]
        self.active_body: str | None = None   # M104: new features land here
        self._result: Solid | None = None
        self._body_solids: dict[str, Solid] | None = None
        self.dirty = False

    # ---- bodies (M104) ---------------------------------------------------
    def add_body(self, name: str | None = None) -> dict:
        """Fusion's New Body: a fresh named stream becomes the active
        one, and every feature added from now on lands inside it."""
        if name is None:
            taken = {b["name"] for b in self.bodies}
            k = 1
            while f"Body {k}" in taken:
                k += 1
            name = f"Body {k}"
        b = {"name": name, "visible": True,
             "placement": [0.0, 0.0, 0.0],   # kinematic STATE, not a
             "rot": None}                    # feature (Placement≠Feature)
        self.bodies.append(b)
        self.active_body = name
        self.dirty = True
        return b

    def body_list(self) -> list:
        """The bodies the browser and viewport show.  A history built
        before M104 (features appended without bodies) materializes the
        implicit Body 1 the moment anyone asks — the browser never lies."""
        if not self.bodies and self.features:
            self.bodies = [{"name": "Body 1", "visible": True,
                            "placement": [0.0, 0.0, 0.0], "rot": None}]
            if self.active_body is None:
                self.active_body = "Body 1"
        return self.bodies

    # ---- kinematic body placement (Placement ≠ Feature) -------------------
    @staticmethod
    def _apply_placement(body: dict | None, solid):
        """Rotate (state matrix) then translate (state vector): pure
        kinematic transforms applied outside the feature timeline."""
        if body is None:
            return solid
        rot = body.get("rot")
        if rot is not None:
            solid = solid.transformed(np.asarray(rot, float).reshape(4, 4))
        pos = body.get("placement") or (0.0, 0.0, 0.0)
        if any(pos):
            solid = solid.translated(tuple(float(v) for v in pos))
        return solid

    def _body(self, name: str) -> dict:
        for b in self.body_list():
            if b["name"] == name:
                return b
        raise KeyError(f"no body {name!r}")

    def move_body(self, name: str, dx: float, dy: float, dz: float) -> dict:
        """Slide a body WITHOUT a timeline feature — Fusion's kinematic
        component move, as data model.  Accumulates."""
        b = self._body(name)
        p = b.setdefault("placement", [0.0, 0.0, 0.0])
        b["placement"] = [p[0] + dx, p[1] + dy, p[2] + dz]
        self.dirty = True
        return b

    def rotate_body(self, name: str, angle_deg: float,
                    axis=(0.0, 0.0, 1.0), center=(0.0, 0.0, 0.0)) -> dict:
        """Spin a body without a feature; composes onto the state matrix
        (world-space rotation_about the given centre)."""
        from .geometry import rotation_about
        b = self._body(name)
        m = rotation_about(tuple(float(c) for c in center),
                           tuple(float(a) for a in axis),
                           np.deg2rad(float(angle_deg)))
        prev = (np.asarray(b.get("rot"), float).reshape(4, 4)
                if b.get("rot") is not None else np.eye(4))
        b["rot"] = (m @ prev).ravel().tolist()
        self.dirty = True
        return b

    def reset_body_placement(self, name: str) -> dict:
        b = self._body(name)
        b["placement"] = [0.0, 0.0, 0.0]
        b["rot"] = None
        self.dirty = True
        return b

    def capture_body_placement(self, name: str):
        """Capture Position: bake the kinematic state into real timeline
        features (Rotate then Move — same order state applies in) and
        zero the state.  After capture the placement is parametric and
        survives anything that reads features, not body dicts."""
        b = self._body(name)
        pos = list(b.get("placement") or (0.0, 0.0, 0.0))
        made = []
        if b.get("rot") is not None:
            r3 = np.asarray(b["rot"], float).reshape(4, 4)[:3, :3]
            from scipy.spatial.transform import Rotation
            rv = Rotation.from_matrix(r3).as_rotvec()
            ang = float(np.linalg.norm(rv))
            if ang > 1e-12:
                ax = (rv / ang).tolist()
                rf = RotateFeature(name="Capture Rot",
                                   center=(0.0, 0.0, 0.0),
                                   axis=tuple(ax),
                                   angle_deg=float(np.rad2deg(ang)))
                rf.body = name                   # NOT the active body!
                made.append(self.add(rf))
        if any(abs(v) > 1e-12 for v in pos):
            mf = MoveFeature(name="Capture Move", vec=tuple(pos))
            mf.body = name
            made.append(self.add(mf))
        self.reset_body_placement(name)
        return made

    def set_active_body(self, name: str) -> bool:
        for b in self.body_list():
            if b["name"] == name:
                if self.active_body != name:
                    self.active_body = name
                    self.dirty = True
                return True
        return False

    def set_body_visible(self, name: str, flag: bool) -> bool:
        """The per-body bulb.  This is a VIEWPORT fact: the part
        (result) keeps every body — paper and measurement never lie
        because a browser row happens to be collapsed."""
        for b in self.body_list():
            if b["name"] == name:
                if bool(b.get("visible", True)) != bool(flag):
                    b["visible"] = bool(flag)
                    self.dirty = True
                return True
        return False

    def body_solids(self) -> dict:
        """body name -> its Solid, live (rebuilds when dirty)."""
        self.result                        # refresh both caches
        return dict(self._body_solids or {})

    def export_solids(self) -> list:
        """The part as SEPARATE bodies for per-body export (M105): every
        body that has a solid, in browser order.  The whole part goes —
        the viewport bulb is a view fact and does not gate the file
        (Fusion exports every body, visible or not)."""
        self.result
        out = []
        for b in self.body_list():
            s = (self._body_solids or {}).get(b["name"])
            if s is not None:
                out.append((b["name"], s))
        return out

    def set_body_appearance(self, name: str, app) -> bool:
        """Paint ONE body (M106): ``app`` is an appearance record
        ({"name", "color", "opacity"}) or None to unpaint.  This rides in
        the body dict, so it saves, round-trips and undoes for free.  The
        whole-part doc.appearance (M52) stays the default for bodies that
        carry none of their own."""
        for b in self.body_list():
            if b["name"] == name:
                if app:
                    b["appearance"] = dict(app)
                else:
                    b.pop("appearance", None)
                self.dirty = True
                return True
        return False

    def painted_bodies(self) -> bool:
        """True when any body carries its own colour (M106) — the signal
        that the viewport should shade per-body instead of by the uniform."""
        return any((b.get("appearance") or {}).get("color")
                   for b in self.body_list())

    def export_appearances(self) -> dict:
        """M115: body name → print-appearance record for the 3MF writer,
        resolving the same chain the viewport honours — the body's own
        paint (M106), else the whole-part uniform (M52).  A body's BOM
        material name rides along; bodies with neither yield nothing."""
        out = {}
        for b in self.body_list():
            app = b.get("appearance") or self.appearance
            rec = {}
            if app and app.get("color"):
                rec["appearance"] = dict(app)
            if b.get("material"):
                rec["material"] = b["material"]
            if rec:
                out[b["name"]] = rec
        return out

    def _visible_solids(self) -> list:
        """[(body, Solid)] that are visible and built, browser order."""
        self.result
        out = []
        for b in self.body_list():
            if not b.get("visible", True):
                continue
            s = (self._body_solids or {}).get(b["name"])
            if s is not None:
                out.append((b, s))
        return out

    def _stitch(self, colours: bool, default_color):
        """Concatenate visible bodies into (v, n, f[, face_colors])."""
        parts = self._visible_solids()
        if not parts:
            return None
        vs, ns, fs, cs = [], [], [], []
        painted = any((b.get("appearance") or {}).get("color")
                      for b, _ in parts)
        off = 0
        for b, s in parts:
            v, n, f = s.to_render_arrays()
            vs.append(v)
            ns.append(n)
            fs.append(f + off if off else f)
            off += len(v)
            if colours and painted:
                col = (b.get("appearance") or {}).get("color")
                col = col if col is not None else (
                    default_color if default_color is not None
                    else (0.70, 0.70, 0.72))
                cs.append(np.tile(np.asarray(col, np.float32), (len(f), 1)))
        if len(vs) == 1:
            v, n, f = vs[0], ns[0], fs[0]
        else:
            v, n, f = np.vstack(vs), np.vstack(ns), np.vstack(fs)
        if not colours:
            return v, n, f
        return v, n, f, (np.vstack(cs) if painted else None)

    def display_arrays(self):
        """The viewport mesh: visible bodies STITCHED (concatenated,
        never booleaned), so hiding a body lifts exactly its triangles
        and a wall shared by two touching bodies stays drawn — Fusion.
        One visible body returns that solid's own arrays: the exact
        pixels the single-body world drew before M104."""
        return self._stitch(colours=False, default_color=None)

    def display_stitched(self, default_color=None):
        """As display_arrays, but a 4-tuple ``(v, n, f, face_colors)``
        where face_colors is per-face sRGB when any body is painted
        (M106), else None so the renderer keeps its uniform base colour."""
        return self._stitch(colours=True, default_color=default_color)

    # ---- construction geometry (M125) — named datum planes & work axes ------
    # A datum is a frame, nothing more: planes carry (origin, u, v, n),
    # axes carry (origin, dir). Creation methods are pure frame algebra —
    # no face identity is required anywhere, which is exactly what a
    # mesh-timeline kernel can honour forever. Names are the handle:
    # sketches host on planes, patterns spin about axes, mirrors across
    # planes, all by name resolved at recompute.

    def _next_name(self, prefix: str) -> str:
        taken = {p["name"] for p in self.planes} | \
                {a["name"] for a in self.axes}
        k = 1
        while f"{prefix} {k}" in taken:
            k += 1
        return f"{prefix} {k}"

    @staticmethod
    def _frame(p1, p2, p3):
        """Orthonormal frame through three points (Fusion's Plane ▸
        Through Three Points); raises rather than accept a collapsed
        pick triangle."""
        p1, p2, p3 = (np.asarray(q, float) for q in (p1, p2, p3))
        n = np.cross(p2 - p1, p3 - p1)
        if np.linalg.norm(n) < 1e-9:
            raise params.ParamError(
                "three points must not be collinear — no plane to fit")
        n /= np.linalg.norm(n)
        u = p2 - p1
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        return (p1 + p2 + p3) / 3.0, u, v, n

    def add_plane(self, base: str, offset: float) -> dict:
        """Offset copy of an origin plane (Fusion's Construct ▸ Plane)."""
        n, u, v = self._PLANE_BASES[base]
        p = {"name": self._next_name("Plane"), "base": base, "method": "offset",
             "offset": float(offset),
             "origin": [c * float(offset) for c in n],
             "u": list(u), "v": list(v), "n": list(n)}
        self.planes.append(p)
        self.dirty = True
        return p

    def add_plane_angle(self, base: str, angle: float,
                        hinge: str = "u", through=(0.0, 0.0, 0.0)) -> dict:
        """Base frame rotated `angle`° about an in-plane hinge line
        through `through` (Fusion's Plane ▸ At Angle; our hinge is the
        base plane's u or v axis — the pick-a-real-line version wants
        face identity we don't have yet)."""
        if hinge not in ("u", "v"):
            raise params.ParamError("hinge must be 'u' or 'v'")
        n, u, v = self._PLANE_BASES[base]
        o = np.zeros(3)                        # origin-plane frame sits at 0
        ax = np.asarray({"u": u, "v": v}[hinge], float)
        t = np.asarray(through, float)
        th = math.radians(float(angle))
        R = _rodrigues(ax, th)
        origin = t + R @ (o - t)               # rotate the base origin
        p = {"name": self._next_name("Plane"), "base": base,
             "method": "angle", "angle": float(angle), "hinge": hinge,
             "through": list(map(float, t)),
             "origin": list(map(float, origin)),
             "u": list(map(float, R @ np.asarray(u))),
             "v": list(map(float, R @ np.asarray(v))),
             "n": list(map(float, R @ np.asarray(n)))}
        self.planes.append(p)
        self.dirty = True
        return p

    def add_plane_3pt(self, p1, p2, p3) -> dict:
        o, u, v, n = self._frame(p1, p2, p3)
        p = {"name": self._next_name("Plane"), "method": "three-points",
             "points": [list(map(float, q)) for q in (p1, p2, p3)],
             "origin": list(map(float, o)), "u": list(map(float, u)),
             "v": list(map(float, v)), "n": list(map(float, n))}
        self.planes.append(p)
        self.dirty = True
        return p

    def add_plane_mid(self, a: str, b: str) -> dict:
        """Midplane between two named planes (origin or custom). The
        honest refusal when they aren't parallel is the whole point:
        no silent best-fit lie."""
        oa, ua, va, na = self.plane_frame(a)
        ob, ub, vb, nb = self.plane_frame(b)
        na, nb = np.asarray(na), np.asarray(nb)
        if abs(abs(float(np.dot(na, nb))) - 1.0) > 1e-6:
            raise params.ParamError(
                f"midplane needs parallel planes — {a!r} and {b!r} "
                "are not")
        n = na if float(np.dot(na, nb)) > 0 else -na
        u = np.asarray(ua, float)             # keep A's in-plane x; rebuild
        v = np.cross(n, u)                    # a right-handed v either way
        d = float(np.dot(np.asarray(ob, float) - np.asarray(oa, float), n))
        origin = np.asarray(oa, float) + n * (d / 2.0)
        p = {"name": self._next_name("Plane"), "method": "midplane",
             "between": [a, b],
             "origin": list(map(float, origin)),
             "u": list(map(float, u)), "v": list(map(float, v)),
             "n": list(map(float, n))}
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

    def plane_frame(self, ref: str):
        """(origin, u, v, n) for an origin plane name or a stored one."""
        if ref in self._PLANE_BASES:
            n, u, v = self._PLANE_BASES[ref]
            return [0.0, 0.0, 0.0], list(u), list(v), list(n)
        for p in self.planes:
            if p["name"] == ref:
                return p["origin"], p["u"], p["v"], p["n"]
        raise params.ParamError(
            f"no plane named {ref!r} — it may have been deleted; recreate "
            "it with Construction Plane (Ctrl+Shift+P) or point the "
            "feature at a surviving datum")

    def add_axis_2pt(self, p1, p2) -> dict:
        p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
        d = p2 - p1
        if np.linalg.norm(d) < 1e-9:
            raise params.ParamError("two points must differ to define "
                                    "an axis")
        d /= np.linalg.norm(d)
        a = {"name": self._next_name("Axis"), "method": "two-points",
             "points": [list(p1), list(p2)],
             "origin": list(p1), "dir": list(d)}
        self.axes.append(a)
        self.dirty = True
        return a

    def add_axis_2planes(self, a: str, b: str) -> dict:
        """Intersection axis of two planes; origin is the intersection
        line's point closest to the world origin."""
        oa, _, _, na = self.plane_frame(a)
        ob, _, _, nb = self.plane_frame(b)
        na, nb = np.asarray(na, float), np.asarray(nb, float)
        d = np.cross(na, nb)
        if np.linalg.norm(d) < 1e-9:
            raise params.ParamError(
                f"{a!r} and {b!r} do not intersect in an axis (parallel)")
        d /= np.linalg.norm(d)
        try:
            o = np.linalg.solve(np.vstack([na, nb, d]),
                                [float(na @ np.asarray(oa, float)),
                                 float(nb @ np.asarray(ob, float)), 0.0])
        except np.linalg.LinAlgError:
            raise params.ParamError("no intersection axis for those planes")
        ax = {"name": self._next_name("Axis"), "method": "two-planes",
              "between": [a, b],
              "origin": list(map(float, o)), "dir": list(map(float, d))}
        self.axes.append(ax)
        self.dirty = True
        return ax

    def remove_axis(self, name: str) -> bool:
        before = len(self.axes)
        self.axes = [x for x in self.axes if x["name"] != name]
        if len(self.axes) != before:
            self.dirty = True
            return True
        return False

    def datum_references(self, name: str) -> list[str]:
        """M125 part 3: names of features that bind to datum `name` BY
        NAME at recompute — mirrors (plane) and named-axis circular
        patterns (axis).  Sketches and derived planes store a frozen
        frame copy, so they survive deletion of the datum that seeded
        them; these two do not, which is exactly why the UI warns."""
        out: list[str] = []
        for f in self.features:
            if isinstance(f, MirrorFeature) and f.plane == name:
                out.append(f.name)
            elif isinstance(f, CircularPatternFeature) and f.axis == name:
                out.append(f.name)
            elif isinstance(f, GeometricPatternFeature) and \
                    name in (f.axis, f.d1, f.d2):
                out.append(f.name)      # pivot or either lattice rail
            elif isinstance(f, CoilFeature) and f.axis == name:
                out.append(f.name)      # the helix spins on this line
        return out

    def _dir(self, ref) -> np.ndarray:
        """Lattice direction (M126): a string resolves through the axis
        store ("X"/"Y"/"Z" or a work axis); anything else must be a
        non-zero literal vector."""
        if isinstance(ref, str):
            return np.asarray(self.axis_frame(ref)[1], float)
        v = np.asarray(ref, float)
        n = float(np.linalg.norm(v))
        if n < 1e-12:
            raise params.ParamError("pattern direction cannot be zero")
        return v / n

    def axis_frame(self, ref: str):
        """(origin, dir) for X/Y/Z or a stored work axis."""
        w = {"X": [1.0, 0.0, 0.0], "Y": [0.0, 1.0, 0.0],
             "Z": [0.0, 0.0, 1.0]}.get(ref)
        if w:
            return [0.0, 0.0, 0.0], w
        for a in self.axes:
            if a["name"] == ref:
                return a["origin"], a["dir"]
        raise params.ParamError(
            f"no axis named {ref!r} — it may have been deleted; recreate "
            "it with Work Axis (Ctrl+Shift+O) or point the feature at a "
            "surviving datum")

    # ---- editing -------------------------------------------------------
    def add(self, feature: Feature) -> Feature:
        if not self.bodies:
            self.add_body()                 # the implicit Body 1, Fusion-style
        if getattr(feature, "body", None) is None:
            feature.body = self.active_body or self.bodies[0]["name"]
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

    def add_interference(self, body_a: str, body_b: str,
                         name: str | None = None):
        """M122 (assembly phase 1): make the clash between two bodies a
        BODY of its own — the interference solid, live in the timeline
        (this is what Fusion's Interference command cannot do).  Both
        streams must already exist.  Returns (body dict, feature)."""
        self._body(body_a)                    # honest KeyError early
        self._body(body_b)
        label = name or f"Interference {body_a} ∩ {body_b}"
        taken = {b["name"] for b in self.body_list()}
        k = 2
        final = label
        while final in taken:
            final = f"{label} {k}"
            k += 1
        b = self.add_body(final)
        f = self.add(InterferenceFeature(name=final, body=final,
                                         body_a=body_a, body_b=body_b))
        return b, f

    _INTERLOCK_NAMES = {                   # M121, per role
        "boss": {"carry": "Boss post", "mate": "Boss clearance"},
        "snapfit": {"carry": "Snap-fit hook", "mate": "Snap-fit window"},
        "rest": {"carry": None, "mate": "Rest seat"},
        "lip": {"carry": "Lip bead", "mate": "Lip channel"},
    }

    def add_interlock(self, kind, body_carry, body_mate=None, *, x=0.0,
                      y=0.0, z0=0.0, clearance=0.2, flip=False, **geometry):
        """M121 interlock family: append the feature pair that mates two
        bodies across the interface plane z = z0 at (x, y).  body_carry
        gets the joining feature below the plane; body_mate receives the
        matching clearance cut above it — None for the one-sided Rest,
        which simply cuts its body's flat shelf.  flip mirrors the pair
        across the plane and exchanges the bodies (Fusion's Flip
        checkbox).  Every parameter is validated BEFORE anything
        changes: a nonsense geometry touches no stream.  Returns the
        appended features."""
        from . import interlock
        if kind not in interlock.KINDS:
            raise ValueError(f"unknown interlock kind: {kind!r}")
        params = dict(geometry, clearance=float(clearance))
        built = interlock.tools(kind, **params)   # fail before mutating
        carry_body, mate_body = body_carry, body_mate
        if flip:
            carry_body, mate_body = mate_body, carry_body
        out = []
        names = self._INTERLOCK_NAMES[kind]
        if built["carry"] is not None:
            if carry_body is None:
                raise ValueError(f"{kind} mates two bodies — name both")
            out.append(self.add(InterlockFeature(
                name=names["carry"], op="union", kind=kind,
                role="carry", center=(float(x), float(y)),
                plane_z=float(z0), flip=bool(flip), params=params,
                body=carry_body)))
        if built["mate"] is not None:
            target = mate_body if kind != "rest" else body_carry
            if target is None:
                raise ValueError(f"{kind} mates two bodies — name both")
            out.append(self.add(InterlockFeature(
                name=names["mate"], op="subtract", kind=kind, role="mate",
                center=(float(x), float(y)), plane_z=float(z0),
                flip=bool(flip), params=params, body=target)))
        return out

    def add_linear_pattern(self, name, source: Feature, vector, count, op=None):
        return self.add(LinearPatternFeature(
            name=name, op=op or source.op, source_uid=source.uid,
            vector=tuple(float(v) for v in vector), count=int(count)))

    def add_circular_pattern(self, name, source: Feature, center=(0, 0),
                             angle=360.0, count=6, op=None, axis=""):
        return self.add(CircularPatternFeature(
            name=name, op=op or source.op, source_uid=source.uid,
            center=(float(center[0]), float(center[1])),
            angle=float(angle), count=int(count), axis=axis))

    def add_mirror(self, name, source: Feature, plane="YZ", offset=0.0,
                   op=None):
        return self.add(MirrorFeature(
            name=name, op=op or source.op, source_uid=source.uid,
            plane=plane, offset=float(offset)))

    def add_geometric_pattern(self, name, source: Feature, *, axis="Z",
                              base=(0.0, 0.0, 0.0), d1=(1.0, 0.0, 0.0),
                              n1=3, t1=10.0, r1=0.0, k1=1.0,
                              d2=(0.0, 1.0, 0.0), n2=1, t2=0.0, r2=0.0,
                              k2=1.0, op=None):
        return self.add(GeometricPatternFeature(
            name=name, op=op or source.op, source_uid=source.uid,
            axis=axis, base=tuple(float(v) for v in base),
            d1=d1 if isinstance(d1, str) else
            tuple(float(v) for v in d1),
            n1=int(n1), t1=float(t1), r1=float(r1), k1=float(k1),
            d2=d2 if isinstance(d2, str) else
            tuple(float(v) for v in d2),
            n2=int(n2), t2=float(t2), r2=float(r2), k2=float(k2)))

    def add_scale(self, name, source: Feature, base=(0.0, 0.0, 0.0),
                  factors=1.0, op=None):
        k = np.asarray(factors, float)
        if k.shape == ():
            k = np.repeat(float(k), 3)
        return self.add(ScaleFeature(
            name=name, op=op or source.op, source_uid=source.uid,
            base=tuple(float(v) for v in base),
            factors=tuple(float(v) for v in k)))

    def add_coil(self, name, *, axis="Z", base=(0.0, 0.0, 0.0),
                 diameter=8.0, pitch=1.25, turns=6.0, hand="right",
                 section="circular", size=1.0, op="union"):
        return self.add(CoilFeature(
            name=name, op=op, axis=axis,
            base=tuple(float(v) for v in base),
            diameter=float(diameter), pitch=float(pitch),
            turns=float(turns), hand=str(hand), section=str(section),
            size=float(size)))

    @staticmethod
    def _rotz_about(cx, cy, t) -> "np.ndarray":
        c, s = np.cos(t), np.sin(t)
        m = np.eye(4)
        m[:2, :2] = [[c, -s], [s, c]]
        m[0, 3] = cx - (c * cx - s * cy)        # T(p) R T(-p)
        m[1, 3] = cy - (s * cx + c * cy)
        return m

    # ---- evaluation ------------------------------------------------------
    def _refresh_sketch_feature(self, f, values, scale):
        """M89: re-derive an extrude/revolve profile from its sketch
        payload with parameter-driven dimension formulas applied —
        a sheet edit moves the solid.  The payload itself is rewritten
        from the solved model, so reopening the editor sees the truth."""
        from .sketch.model import model_from_dict, model_to_dict
        from .sketch.profile import regions
        m = model_from_dict(f.sketch)
        m.apply_dim_params(values, scale)
        m.solve()
        loops, _w = m.to_loops()
        regs = regions(loops)
        if not regs:
            raise ValueError(f"{f.name}: sketch lost its closed profile "
                             "after the parameter change")
        i = min(max(int(getattr(f, "region", 0) or 0), 0), len(regs) - 1)
        r = regs[i]
        f.outer = np.asarray(r["points"], float)
        f.holes = [np.asarray(h["points"], float)
                   for h in r.get("holes", [])]
        f.sketch = dict(f.sketch, **model_to_dict(m))

    def merged_sheet(self) -> dict:
        """M91: the base parameters with the active configuration's
        overrides laid on top — the sheet the rebuild resolves.
        An unknown active name simply isn't here (honest ignore)."""
        over = self.configs.get(self.active_config or "")
        if not over:
            return self.params
        return {**self.params,
                **{k: str(v) for k, v in over.items()}}

    def recompute(self) -> Solid | None:
        if self.params:                   # M81: the sheet drives levers
            from . import units
            vals = params.resolve(self.merged_sheet())   # M91 overlay
            sc = units.PER_MM[self.units]        # stored truth is mm
            for f in self.features:
                if f.bindings:
                    f.apply_bindings(vals, sc)
                sk = getattr(f, "sketch", None)
                if sk and sk.get("dim_exprs"):        # M89 fx dimensions
                    self._refresh_sketch_feature(f, vals, sc)
        # M104: one stream PER BODY.  A feature reads and writes only its
        # own body's accumulator — a cut in Body 2 leaves Body 1 standing.
        # Legacy history (f.body is None) streams into the implicit
        # "Body 1", exactly the single accumulator the world ran on.
        buckets: dict[str, Solid | None] = {}
        by_uid: dict[str, Solid] = {}
        for pos, f in enumerate(self.features):
            # M118: the log bridge's "who broke" — whichever feature the
            # loop was building when an exception escapes is the guilty
            # one. No try/except needed inside the loop itself.
            self._in_feature = (pos, f)
            if self.rollback_to is not None and pos >= self.rollback_to:
                continue                      # M88: past the rubber band
            if f.suppressed:
                continue
            key = getattr(f, "body", None) or "Body 1"
            acc = buckets.get(key)
            if isinstance(f, LinearPatternFeature):
                src = by_uid.get(f.source_uid)
                if src is None:          # source deleted/suppressed: no-op
                    continue
                solid = Solid.batch_union(
                    [src.translated(tuple(v * k for v in f.vector))
                     for k in range(max(1, int(f.count)))])
            elif isinstance(f, PathPatternFeature):
                src = by_uid.get(f.source_uid)
                if src is None:
                    continue
                from .sweep import sample_polyline
                M = plane_matrix(f.plane, f.placement, f.axes)
                ws = [M[:3, :3] @ np.array([x, y, 0.0]) + M[:3, 3]
                      for x, y in sample_polyline(f.path, f.count)]
                solid = Solid.batch_union(
                    [src.translated(tuple(w - ws[0])) for w in ws])
            elif isinstance(f, CircularPatternFeature):
                src = by_uid.get(f.source_uid)
                if src is None:
                    continue
                n = max(1, int(f.count))
                ang = float(f.angle)
                full = abs(abs(ang) - 360.0) < 1e-9
                step = ang / (n if full else max(n - 1, 1))
                if f.axis:                      # M125: named datum pivot
                    ao, ad = self.axis_frame(f.axis)
                    xf = [_rot_about_line(ao, ad, math.radians(step * k))
                          for k in range(n)]
                else:                           # legacy: +Z through center
                    xf = [self._rotz_about(f.center[0], f.center[1],
                                           math.radians(step * k))
                          for k in range(n)]
                solid = Solid.batch_union([src.transformed(m) for m in xf])
            elif isinstance(f, MirrorFeature):
                src = by_uid.get(f.source_uid)
                if src is None:
                    continue
                n = MirrorFeature.NORMALS.get(f.plane)
                p0 = (0.0, 0.0, 0.0)
                if n is None:                   # M125: custom datum plane
                    p0, _, _, nf = self.plane_frame(f.plane)
                    n = tuple(float(v) for v in nf)
                shift = tuple(p0[i] + n[i] * f.offset for i in range(3))
                solid = src.translated((-shift[0], -shift[1], -shift[2])) \
                            .mirror(n).translated(shift)
            elif isinstance(f, GeometricPatternFeature):
                src = by_uid.get(f.source_uid)
                if src is None:
                    continue
                n1, n2 = int(f.n1), int(f.n2)
                if n1 < 1 or n2 < 1:
                    raise params.ParamError("lattice counts must be >= 1")
                if n1 * n2 > f.MAX_COPIES:
                    raise params.ParamError(
                        f"lattice of {n1}x{n2} exceeds {f.MAX_COPIES} "
                        "copies")
                if float(f.k1) <= 0 or float(f.k2) <= 0:
                    raise params.ParamError(
                        "lattice step factors must be positive")
                solid = Solid.batch_union(
                    [src.transformed(_lattice_step(f, self, m))
                     for m in ((i, j) for i in range(n1)
                               for j in range(n2))])
            elif isinstance(f, ScaleFeature):
                src = by_uid.get(f.source_uid)
                if src is None:
                    continue
                k = np.asarray(f.factors, float)
                if k.shape == ():
                    k = np.repeat(float(k), 3)
                if k.size != 3:
                    raise params.ParamError("scale wants 1 or 3 factors")
                if not np.all(k):
                    raise params.ParamError("scale factors cannot be zero")
                solid = src.transformed(_scale_about(f.base, k))
            elif isinstance(f, CoilFeature):
                ao, ad = self.axis_frame(f.axis or "Z")
                from .coil import coil_solid
                solid = coil_solid(ao, ad, float(f.diameter) / 2.0,
                                   f.pitch, f.turns, f.section, f.size,
                                   f.hand)
            elif isinstance(f, InterferenceFeature):
                # a clash AS A BODY: intersect two source streams exactly
                # as their users see them — placement state included.
                sides = []
                for want in (f.body_a, f.body_b):
                    s = buckets.get(want)
                    if s is None:
                        raise ValueError(
                            f"{f.name!r}: source body {want!r} has "
                            "nothing to interfere with yet")
                    b = next((x for x in self.bodies
                              if x["name"] == want), None)
                    sides.append(self._apply_placement(b, s))
                solid = sides[0].intersect(sides[1])
            elif isinstance(f, (BodyFilletFeature, ShellFeature,
                                SplitFeature, MoveFeature, RotateFeature,
                                CombineFeature)):
                if acc is None:
                    verb = ("fillet" if isinstance(f, BodyFilletFeature)
                            else "shell" if isinstance(f, ShellFeature)
                            else "split" if isinstance(f, SplitFeature)
                            else "move" if isinstance(f, MoveFeature)
                            else "rotate" if isinstance(f, RotateFeature)
                            else "combine")
                    raise ValueError(f"{f.name!r} has no body to {verb} yet")
                buckets[key] = f.apply(acc)
                by_uid[f.uid] = buckets[key]
                continue          # replaces the body; not a boolean operand
            else:
                solid = f.build()
            by_uid[f.uid] = solid
            if acc is None:
                if f.op == "subtract":
                    raise ValueError(f"first feature {f.name!r} cannot be a subtract")
                buckets[key] = solid
            elif f.op == "union":
                buckets[key] = acc.union(solid)
            elif f.op == "subtract":
                buckets[key] = acc.subtract(solid)
            else:
                buckets[key] = acc.intersect(solid)
        # Placement ≠ Feature (architecture [S]; kernel report actionable,
        # joint report §1 by name): a body's placement is KINEMATIC STATE,
        # applied AFTER its feature stream — moving a body creates no
        # timeline feature and no recompute dependency, exactly as Fusion
        # documents for components. Capture bakes it into features.
        placed = {}
        for k, v in buckets.items():
            if v is None:
                continue
            b = next((x for x in self.bodies if x["name"] == k), None)
            placed[k] = self._apply_placement(b, v)
        self._body_solids = placed
        solids = list(self._body_solids.values())
        if not solids:
            self._result = None
        elif len(solids) == 1:
            self._result = solids[0]          # the single-body world:
        else:                                 # the very solid it always was
            self._result = Solid.batch_union(solids)   # the PART is the union
        # M118: a clean pass wipes every failure badge and pointer
        self._in_feature = None
        self.failed_feature = None
        for f in self.features:
            if getattr(f, "error", None):
                f.error = None
        self.dirty = False
        return self._result

    def record_failure(self, message: str) -> tuple[int, str] | None:
        """Called by the recompute bridge after an exception escaped
        recompute(): stamps the feature that was mid-build with the
        error badge and remembers it for the log's click-to-select.
        Returns (pos, name) — or None if no feature was in flight."""
        info = getattr(self, "_in_feature", None)
        for f in self.features:
            f.error = None
        if info is None:
            self.failed_feature = None
            return None
        pos, f = info
        f.error = str(message)
        self.failed_feature = (pos, f.name)
        self._in_feature = None
        return pos, f.name

    @property
    def result(self) -> Solid | None:
        if self._result is None or self.dirty:
            return self.recompute()
        return self._result

    # ---- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        def _feat(f: Feature) -> dict:
            d = {"type": type(f).__name__, "name": f.name, "op": f.op,
                 "uid": f.uid, "suppressed": bool(f.suppressed),
                 "body": getattr(f, "body", None)}
            if isinstance(f, ExtrudeFeature):
                d.update(outer=np.asarray(f.outer).tolist(),
                         holes=[np.asarray(h).tolist() for h in f.holes],
                         height=float(f.height),
                         fillet=float(f.fillet), chamfer=float(f.chamfer),
                         taper=float(f.taper),
                         symmetric=bool(f.symmetric),
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
                         angle=float(f.angle), count=int(f.count),
                         axis=f.axis)
            elif isinstance(f, MirrorFeature):
                d.update(source_uid=f.source_uid, plane=f.plane,
                         offset=float(f.offset))
            elif isinstance(f, GeometricPatternFeature):
                d.update(source_uid=f.source_uid, axis=f.axis,
                         base=list(map(float, f.base)),
                         d1=f.d1 if isinstance(f.d1, str)
                         else list(map(float, f.d1)),
                         n1=int(f.n1), t1=float(f.t1), r1=float(f.r1),
                         k1=float(f.k1),
                         d2=f.d2 if isinstance(f.d2, str)
                         else list(map(float, f.d2)),
                         n2=int(f.n2), t2=float(f.t2), r2=float(f.r2),
                         k2=float(f.k2))
            elif isinstance(f, ScaleFeature):
                d.update(source_uid=f.source_uid,
                         base=list(map(float, f.base)),
                         factors=list(map(float, f.factors)))
            elif isinstance(f, CoilFeature):
                d.update(axis=f.axis, base=list(map(float, f.base)),
                         diameter=float(f.diameter),
                         pitch=float(f.pitch), turns=float(f.turns),
                         hand=f.hand, section=f.section,
                         size=float(f.size))
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
            elif isinstance(f, ThickenFeature):
                d.update(thickness=float(f.thickness),
                         depth=float(f.depth),
                         paths=[[[float(x), float(y)] for x, y in p]
                                for p in f.paths],
                         plane=f.plane,
                         placement=list(map(float, f.placement)),
                         axes=f.axes, sketch=f.sketch, sid=f.sid)
            elif isinstance(f, ShellFeature):
                d.update(thickness=float(f.thickness),
                         openings=[[[float(x) for x in o[0]],
                                    [float(x) for x in o[1]]]
                                   for o in f.openings])
            elif isinstance(f, SplitFeature):
                d.update(origin=list(map(float, f.origin)),
                         normal=list(map(float, f.normal)),
                         flip=bool(f.flip))
            elif isinstance(f, MoveFeature):
                d.update(vec=list(map(float, f.vec)),
                         copy=bool(f.copy))
            elif isinstance(f, RotateFeature):
                d.update(center=list(map(float, f.center)),
                         axis=list(map(float, f.axis)),
                         angle_deg=float(f.angle_deg),
                         copy=bool(f.copy))
            elif isinstance(f, CombineFeature):
                d.update(tool=str(f.tool), dims=dict(f.dims),
                         center=list(map(float, f.center)))
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
            elif isinstance(f, InterlockFeature):
                d.update(kind=f.kind, role=f.role,
                         center=list(map(float, f.center)),
                         plane_z=float(f.plane_z), flip=bool(f.flip),
                         params={k: float(v) for k, v in f.params.items()})
            elif isinstance(f, InterferenceFeature):
                d.update(body_a=str(f.body_a), body_b=str(f.body_b))
            d["bindings"] = dict(f.bindings)     # every lever, one line
            return d
        return {"format": "tracer/document", "version": 2,
                "title": self.title, "units": self.units,
                "params": dict(self.params),
                "configs": {k: dict(v) for k, v in self.configs.items()},
                "active_config": self.active_config,
                "drawings": [dict(g) for g in self.drawings],   # M93
                "bodies": [dict(b) for b in self.bodies],       # M104
                "active_body": self.active_body,
                "features": [_feat(f) for f in self.features],
                "planes": [dict(p) for p in self.planes],
                "axes": [dict(a) for a in self.axes],   # M125
                "appearance": (dict(self.appearance)
                               if self.appearance else None)}

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        if data.get("format") not in ("tracer/document",
                                      "forma/document") or data.get("version", 0) > 2:
            raise ValueError("not a readable Tracer Studio document")
        doc = cls(title=data.get("title", "Untitled"))
        doc.units = data.get("units", "mm")
        doc.params = dict(data.get("params", {}))   # pre-M81 files: empty
        doc.configs = {k: dict(v) for k, v
                       in (data.get("configs") or {}).items()}  # M91
        doc.active_config = data.get("active_config")
        doc.drawings = [dict(g) for g in (data.get("drawings") or [])]
        # M104: bodies travel with the file; a bodyless (pre-M104) file
        # simply reads as one implicit Body 1 (body_list materializes it).
        doc.bodies = [dict(b) for b in (data.get("bodies") or [])]
        doc.active_body = data.get("active_body")
        for fd in data.get("features", []):
            t = fd["type"]
            base = dict(op=fd["op"], uid=fd.get("uid") or uuid.uuid4().hex[:8],
                        suppressed=bool(fd.get("suppressed", False)),
                        body=fd.get("body"))
            if t == "ExtrudeFeature":
                doc.features.append(ExtrudeFeature(
                    name=fd["name"],
                    outer=np.array(fd["outer"], float),
                    holes=[np.array(h, float) for h in fd["holes"]],
                    height=fd["height"],
                    fillet=float(fd.get("fillet", 0.0)),
                    chamfer=float(fd.get("chamfer", 0.0)),
                    taper=float(fd.get("taper", 0.0)),
                    symmetric=bool(fd.get("symmetric", False)),
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
                    count=int(fd["count"]), axis=fd.get("axis", ""),
                    **base))
            elif t == "MirrorFeature":
                doc.features.append(MirrorFeature(
                    name=fd["name"], source_uid=fd["source_uid"],
                    plane=fd["plane"], offset=float(fd["offset"]), **base))
            elif t == "GeometricPatternFeature":
                doc.features.append(GeometricPatternFeature(
                    name=fd["name"], source_uid=fd["source_uid"],
                    axis=fd.get("axis", "Z"),
                    base=tuple(fd.get("base", (0.0, 0.0, 0.0))),
                    d1=fd["d1"] if isinstance(fd["d1"], str)
                    else tuple(map(float, fd["d1"])),
                    n1=int(fd["n1"]), t1=float(fd["t1"]),
                    r1=float(fd["r1"]), k1=float(fd["k1"]),
                    d2=fd["d2"] if isinstance(fd["d2"], str)
                    else tuple(map(float, fd["d2"])),
                    n2=int(fd["n2"]), t2=float(fd["t2"]),
                    r2=float(fd["r2"]), k2=float(fd["k2"]), **base))
            elif t == "ScaleFeature":
                doc.features.append(ScaleFeature(
                    name=fd["name"], source_uid=fd["source_uid"],
                    base=tuple(fd.get("base", (0.0, 0.0, 0.0))),
                    factors=tuple(fd["factors"]), **base))
            elif t == "CoilFeature":
                doc.features.append(CoilFeature(
                    name=fd["name"], axis=fd.get("axis", "Z"),
                    base=tuple(fd.get("base", (0.0, 0.0, 0.0))),
                    diameter=float(fd["diameter"]),
                    pitch=float(fd["pitch"]), turns=float(fd["turns"]),
                    hand=fd.get("hand", "right"),
                    section=fd.get("section", "circular"),
                    size=float(fd["size"]), **base))
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
            elif t == "ThickenFeature":
                doc.features.append(ThickenFeature(
                    name=fd["name"], thickness=float(fd["thickness"]),
                    depth=float(fd["depth"]),
                    paths=[[list(map(float, p)) for p in chain]
                           for chain in fd["paths"]],
                    plane=fd.get("plane", "XY"),
                    placement=tuple(fd.get("placement", (0.0, 0.0, 0.0))),
                    axes=fd.get("axes"), sketch=fd.get("sketch"),
                    sid=fd.get("sid"), **base))
            elif t == "ShellFeature":
                doc.features.append(ShellFeature(
                    name=fd["name"], thickness=float(fd["thickness"]),
                    openings=[(list(map(float, o[0])), list(map(float, o[1])))
                              for o in fd["openings"]], **base))
            elif t == "SplitFeature":
                doc.features.append(SplitFeature(
                    name=fd["name"],
                    origin=tuple(fd["origin"]), normal=tuple(fd["normal"]),
                    flip=bool(fd.get("flip", False)), **base))
            elif t == "MoveFeature":
                doc.features.append(MoveFeature(
                    name=fd["name"], vec=tuple(fd["vec"]),
                    copy=bool(fd.get("copy", False)), **base))
            elif t == "RotateFeature":
                doc.features.append(RotateFeature(
                    name=fd["name"], center=tuple(fd["center"]),
                    axis=tuple(fd["axis"]),
                    angle_deg=float(fd["angle_deg"]),
                    copy=bool(fd.get("copy", False)), **base))
            elif t == "CombineFeature":
                doc.features.append(CombineFeature(
                    name=fd["name"], tool=str(fd.get("tool", "box")),
                    dims=dict(fd.get("dims", {})),
                    center=tuple(fd.get("center", (0.0, 0.0, 0.0))),
                    **base))
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
            elif t == "InterlockFeature":
                doc.features.append(InterlockFeature(
                    name=fd["name"], kind=fd["kind"], role=fd["role"],
                    center=tuple(fd["center"]),
                    plane_z=float(fd["plane_z"]),
                    flip=bool(fd.get("flip", False)),
                    params={k: float(v) for k, v in fd["params"].items()},
                    **base))
            elif t == "InterferenceFeature":
                doc.features.append(InterferenceFeature(
                    name=fd["name"], body_a=str(fd["body_a"]),
                    body_b=str(fd["body_b"]), **base))
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
        if not doc.bodies:
            # legacy (pre-M104) file: adopt the whole history into the
            # implicit Body 1 now, so the reopened doc is explicit forever
            doc.body_list()
            for f in doc.features:
                if f.body is None:
                    f.body = doc.active_body or "Body 1"
        for p in data.get("planes", []):          # pre-M40 files have none
            if p.get("name") and p.get("origin"):
                doc.planes.append(dict(p))   # M125: every key survives —
        for a in data.get("axes", []):            # methods carry payloads
            if a.get("name") and a.get("origin") and a.get("dir"):
                doc.axes.append(dict(a))
        app = data.get("appearance")              # pre-M52 files have none
        doc.appearance = dict(app) if app else None
        for f, fd in zip(doc.features, data.get("features", [])):
            f.bindings = dict(fd.get("bindings", {}))   # pre-M81: empty
        doc.dirty = True
        return doc
