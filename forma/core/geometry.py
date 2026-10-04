"""Geometry kernel layer.

All quantities are in millimetres, Z-up. The concrete kernel behind
``Solid`` is ``manifold3d`` — an exact, guarantee-watertight mesh CSG
engine. A B-rep kernel (OpenCascade, via a small native bridge) will
slot in behind this same interface later without touching UI code.
"""
from __future__ import annotations

import math

import manifold3d as m3
import numpy as np
import trimesh

# Manifold auto-tessellates circles from a global curvature budget; the
# default leaves ~0.6% volume error on small cylinders. 256 segments gets
# us under 1e-4 while staying fast.
m3.set_circular_segments(256)


def circle_contour(radius: float, center: tuple[float, float] = (0.0, 0.0),
                   segments: int = 128) -> np.ndarray:
    """Closed polyline approximating a circle, as an (N,2) float64 array.

    manifold3d re-triangulates adaptively, so ``segments`` controls shape
    fidelity, not final triangle count.
    """
    t = np.linspace(0.0, 2.0 * math.pi, segments, endpoint=False)
    return np.column_stack(
        [center[0] + radius * np.cos(t), center[1] + radius * np.sin(t)]
    ).astype(np.float64)


def _cross_section(outer, holes) -> m3.CrossSection:
    contours = [np.asarray(outer, dtype=np.float64)]
    contours += [np.asarray(h, dtype=np.float64) for h in holes]
    return m3.CrossSection(contours, fillrule=m3.FillRule.EvenOdd)


class Solid:
    """An immutable watertight solid. Booleans return new Solids."""

    def __init__(self, manifold: m3.Manifold):
        self._m = manifold

    # ---- constructors -------------------------------------------------
    @classmethod
    def box(cls, dx: float, dy: float, dz: float) -> "Solid":
        m = m3.Manifold.cube((float(dx), float(dy), float(dz)), center=True)
        m = m.translate(np.array([dx / 2, dy / 2, dz / 2], np.float32))
        return cls(m)

    @classmethod
    def cylinder(cls, radius: float, height: float,
                 center: tuple[float, float] = (0.0, 0.0)) -> "Solid":
        m = m3.Manifold.cylinder(height, radius, radius)
        m = m.translate(np.array([center[0], center[1], 0.0], np.float32))
        return cls(m)

    @classmethod
    def sphere(cls, radius: float) -> "Solid":
        return cls(m3.Manifold.sphere(radius))

    @classmethod
    def extrude(cls, outer, holes=(), height: float = 1.0) -> "Solid":
        cs = _cross_section(outer, holes)
        return cls(m3.Manifold.extrude(cs, height))

    @classmethod
    def from_mesh(cls, vertices, faces) -> "Solid":
        verts = np.ascontiguousarray(vertices, dtype=np.float32)[:, :3]
        tris = np.ascontiguousarray(faces, dtype=np.uint32)
        return cls(m3.Manifold(m3.Mesh(verts, tris)))

    # ---- queries ------------------------------------------------------
    @property
    def volume(self) -> float:
        return float(self._m.volume())

    @property
    def bounding_box(self) -> np.ndarray:
        """Returns [[minx, miny, minz], [maxx, maxy, maxz]] as float64."""
        return np.asarray(self._m.bounding_box(), dtype=np.float64).reshape(2, 3)

    # ---- booleans & placement ----------------------------------------
    def union(self, other: "Solid") -> "Solid":
        return Solid(self._m + other._m)

    def subtract(self, other: "Solid") -> "Solid":
        return Solid(self._m - other._m)

    def intersect(self, other: "Solid") -> "Solid":
        # no * operator in the bindings; batch boolean intersect works
        return Solid(m3.Manifold.batch_boolean([self._m, other._m],
                                               m3.OpType.Intersect))

    def translated(self, offset) -> "Solid":
        off = np.asarray(offset, dtype=np.float32)
        return Solid(self._m.translate(off))

    # ---- mesh conversion (rendering & export) --------------------------
    def transformed(self, m4) -> "Solid":
        """Apply a 4x4 homogeneous transform via mesh round-trip through the
        kernel (re-manifolded, stays watertight)."""
        tm = self.to_trimesh()
        tm.apply_transform(np.asarray(m4, dtype=np.float64))
        return Solid.from_mesh(tm.vertices, tm.faces)

    def to_trimesh(self) -> trimesh.Trimesh:
        tm = self._m.to_mesh()
        verts = np.asarray(tm.vert_properties, dtype=np.float64)[:, :3]
        faces = np.asarray(tm.tri_verts, dtype=np.int64)
        return trimesh.Trimesh(vertices=verts, faces=faces, process=False)

    def to_render_arrays(self):
        """Interleaved-free arrays for the GPU: positions, unit normals, faces."""
        mesh = self.to_trimesh()
        return (
            np.asarray(mesh.vertices, dtype=np.float32),
            np.asarray(mesh.vertex_normals, dtype=np.float32),
            np.asarray(mesh.faces, dtype=np.int32),
        )
