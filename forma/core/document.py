"""Document model: an ordered feature list that recomputes to a Solid.

Feature history is a *linear* stack for now (each op applies to the
accumulated result). This is deliberately the same serialization shape a
true history tree will replace later — files written today stay readable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from .geometry import Solid, circle_contour

CombineOp = Literal["union", "subtract", "intersect"]


@dataclass
class Feature:
    name: str
    op: CombineOp = "union"


@dataclass
class ExtrudeFeature(Feature):
    """Profile (outer contour + holes) in the XY plane extruded by height."""
    outer: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    holes: list = field(default_factory=list)
    height: float = 1.0
    placement: tuple = (0.0, 0.0, 0.0)

    def build(self) -> Solid:
        s = Solid.extrude(self.outer, self.holes, self.height)
        return s.translated(self.placement)


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

    # ---- evaluation ------------------------------------------------------
    def recompute(self) -> Solid | None:
        acc: Solid | None = None
        for f in self.features:
            solid = f.build()
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
            d = {"type": type(f).__name__, "name": f.name, "op": f.op}
            if isinstance(f, ExtrudeFeature):
                d.update(outer=np.asarray(f.outer).tolist(),
                         holes=[np.asarray(h).tolist() for h in f.holes],
                         height=float(f.height),
                         placement=list(map(float, f.placement)))
            elif isinstance(f, PrimitiveFeature):
                d.update(kind=f.kind,
                         dims={k: float(v) for k, v in f.dims.items()},
                         placement=list(map(float, f.placement)))
            return d
        return {"format": "forma/document", "version": 1,
                "title": self.title, "units": self.units,
                "features": [_feat(f) for f in self.features]}

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        if data.get("format") != "forma/document" or data.get("version", 0) > 1:
            raise ValueError("not a readable Forma document")
        doc = cls(title=data.get("title", "Untitled"))
        doc.units = data.get("units", "mm")
        for fd in data.get("features", []):
            t = fd["type"]
            if t == "ExtrudeFeature":
                doc.features.append(ExtrudeFeature(
                    name=fd["name"], op=fd["op"],
                    outer=np.array(fd["outer"], float),
                    holes=[np.array(h, float) for h in fd["holes"]],
                    height=fd["height"], placement=tuple(fd["placement"])))
            elif t == "PrimitiveFeature":
                doc.features.append(PrimitiveFeature(
                    name=fd["name"], op=fd["op"], kind=fd["kind"],
                    dims=fd["dims"], placement=tuple(fd["placement"])))
            else:
                raise ValueError(f"unknown feature type {t!r}")
        doc.dirty = True
        return doc
