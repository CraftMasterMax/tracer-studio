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
from .sketch.model import plane_matrix, revolve_matrix

CombineOp = Literal["union", "subtract", "intersect"]


@dataclass
class Feature:
    name: str
    op: CombineOp = "union"
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    suppressed: bool = False


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


class Document:
    def __init__(self, title: str = "Untitled"):
        self.title = title
        self.units = "mm"
        self.features: list[Feature] = []
        self._result: Solid | None = None
        self.dirty = False

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
            elif isinstance(f, LinearPatternFeature):
                d.update(source_uid=f.source_uid,
                         vector=list(map(float, f.vector)),
                         count=int(f.count))
            elif isinstance(f, CircularPatternFeature):
                d.update(source_uid=f.source_uid,
                         center=list(map(float, f.center)),
                         angle=float(f.angle), count=int(f.count))
            return d
        return {"format": "forma/document", "version": 2,
                "title": self.title, "units": self.units,
                "features": [_feat(f) for f in self.features]}

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        if data.get("format") != "forma/document" or data.get("version", 0) > 2:
            raise ValueError("not a readable Forma document")
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
            elif t == "LinearPatternFeature":
                doc.features.append(LinearPatternFeature(
                    name=fd["name"], source_uid=fd["source_uid"],
                    vector=tuple(fd["vector"]), count=int(fd["count"]), **base))
            elif t == "CircularPatternFeature":
                doc.features.append(CircularPatternFeature(
                    name=fd["name"], source_uid=fd["source_uid"],
                    center=tuple(fd["center"]), angle=float(fd["angle"]),
                    count=int(fd["count"]), **base))
            else:
                raise ValueError(f"unknown feature type {t!r}")
        doc.dirty = True
        return doc
