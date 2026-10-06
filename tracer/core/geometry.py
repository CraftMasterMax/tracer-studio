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


def round_corners(pts, radius: float = 0.0, chamfer: float = 0.0) -> np.ndarray:
    """Cut the convex corners of a closed 2D loop with arcs (``radius``) or
    straight legs (``chamfer``, equal legs).  Concave corners and near-
    straight vertices (arc tessellation, e.g. circles) are left untouched,
    so the op is safe on any profile: it rounds the *design* corners.
    Used by ExtrudeFeature to fillet/chamfer its vertical edges without a
    B-rep kernel — the profile is filleted in 2D, then swept as usual.
    """
    pts = np.asarray(pts, float)
    if len(pts) > 1 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]                       # implicit close
    n = len(pts)
    if n < 3 or (radius <= 0 and chamfer <= 0):
        return pts
    area2 = float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1)
                         - np.roll(pts[:, 0], -1) * pts[:, 1]))
    orient = 1.0 if area2 > 0 else -1.0
    out: list[np.ndarray] = []
    for i in range(n):
        p, a, b = pts[i], pts[i - 1], pts[(i + 1) % n]
        va, vb = a - p, b - p
        na, nb = np.linalg.norm(va), np.linalg.norm(vb)
        if na < 1e-9 or nb < 1e-9:
            out.append(p)
            continue
        ua, ub = va / na, vb / nb
        cross = float(ua[0] * ub[1] - ua[1] * ub[0]) * orient
        theta = math.acos(float(np.clip(np.dot(ua, ub), -1.0, 1.0)))
        if cross >= -1e-9 or theta > math.radians(165) or theta < 1e-6:
            out.append(p)                    # concave / straight / spike: keep
            continue
        half = theta / 2.0
        if chamfer > 0:
            t = min(chamfer, 0.45 * na, 0.45 * nb)
            out.append(p + ua * t)
            out.append(p + ub * t)
        else:
            t = min(radius / math.tan(half), 0.45 * na, 0.45 * nb)
            r_eff = t * math.tan(half)
            entry, exit_ = p + ua * t, p + ub * t
            bis = ua + ub
            bis = bis / np.linalg.norm(bis)
            c = p + bis * (r_eff / math.sin(half))
            a0 = math.atan2(*(entry - c)[::-1])
            a1 = math.atan2(*(exit_ - c)[::-1])
            sweep = a1 - a0
            while sweep > math.pi:
                sweep -= 2 * math.pi
            while sweep < -math.pi:
                sweep += 2 * math.pi
            steps = max(2, math.ceil(abs(sweep) / math.radians(6)))
            for k in range(steps + 1):
                ang = a0 + sweep * k / steps
                out.append(c + r_eff * np.array([math.cos(ang), math.sin(ang)]))
    return np.asarray(out, float)


def rotation_about(center, axis, rad: float) -> np.ndarray:
    """4x4 rigid rotation of `rad` radians around the axis through
    `center` (right-hand rule) — Rodrigues' formula, no dependencies."""
    e = np.asarray(axis, float)
    e = e / np.linalg.norm(e)
    c = np.asarray(center, float)
    K = np.array([[0.0, -e[2], e[1]],
                  [e[2], 0.0, -e[0]],
                  [-e[1], e[0], 0.0]])
    R = np.eye(3) + np.sin(rad) * K \
        + (1.0 - np.cos(rad)) * (K @ K)
    m = np.eye(4)
    m[:3, :3] = R
    m[:3, 3] = c - R @ c
    return m


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
    def revolve(cls, outer, holes=(), angle: float = 360.0) -> "Solid":
        """Sweep a 2D profile about the local z-axis: point (u, v) maps to
        (u·cosθ, u·sinθ, v).  Kernel handles full and partial angles."""
        cs = _cross_section(outer, holes)
        return cls(m3.Manifold.revolve(cs, revolve_degrees=float(angle)))

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
    def surface_area(self) -> float:
        return float(self._m.surface_area())

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

    def mirror(self, normal) -> "Solid":
        """Reflect across the plane through the origin perpendicular to
        ``normal`` (the kernel welds the two halves when they touch)."""
        n = np.asarray(normal, dtype=np.float64)
        if not np.any(n):
            raise ValueError("mirror needs a non-zero plane normal")
        return Solid(self._m.mirror(n))

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
        """Interleaved-free arrays for the GPU: positions, unit normals, faces.

        Boolean welds leave two display artefacts behind: zero-area needle
        triangles that poison smooth normals, and vertex duplicates a few
        microns apart which stop normals from smoothing *across* a
        cylinder's columns (banded, patchwork shading). Both are fixed for
        display only: needles are dropped (they cover no pixels), remaining
        positions are welded on a 10-micron grid before computing vertex
        normals. The mesh itself — volume, watertightness, STL/STEP export,
        rim detection — is untouched. Real creases stay crisp because the
        feature-edge overlay is computed from face geometry, not normals.
        """
        mesh = self.to_trimesh()
        tri = mesh.triangles
        e2 = (((tri[:, 1] - tri[:, 0]) ** 2).sum(1)
              + ((tri[:, 2] - tri[:, 1]) ** 2).sum(1)
              + ((tri[:, 0] - tri[:, 2]) ** 2).sum(1))
        q = 4.0 * math.sqrt(3.0) * mesh.area_faces / np.maximum(e2, 1e-30)
        fn = np.asarray(mesh.face_normals)
        adj = np.asarray(mesh.face_adjacency)
        worst = np.zeros(len(fn))
        has_nb = np.zeros(len(fn), bool)
        if len(adj):
            d = np.abs(np.einsum("ij,ij->i", fn[adj[:, 0]], fn[adj[:, 1]]))
            np.maximum.at(worst, adj[:, 0], d)
            np.maximum.at(worst, adj[:, 1], d)
            has_nb[adj[:, 0]] = has_nb[adj[:, 1]] = True
        # Drop only faces that are both degenerate-slender AND disagree with
        # every neighbour (garbage normals). Legitimate thin triangles — the
        # fillet band near its tangent rings — match neighbours and stay.
        remove = (q < 1e-4) & has_nb & (worst < 0.5)
        if remove.any() and not remove.all():
            mesh.update_faces(~remove)
        try:
            mesh.merge_vertices(digits_vertex=2)     # weld ~micron duplicates
        except Exception:
            pass
        # welding can collapse a near-duplicate triangle to zero area with
        # a NaN normal (which would poison the vertex normals it shares)
        a2 = np.asarray(mesh.area_faces)
        dead = ~np.isfinite(a2) | (a2 <= 0.0)
        if dead.any() and not dead.all():
            mesh.update_faces(~dead)
        return (
            np.asarray(mesh.vertices, dtype=np.float32),
            np.asarray(mesh.vertex_normals, dtype=np.float32),
            np.asarray(mesh.faces, dtype=np.int32),
        )
