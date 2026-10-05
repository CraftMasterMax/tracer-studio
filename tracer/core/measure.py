"""Measure: distances, angles and areas from the picked mesh (Inspect).

Fusion's Measure gives instant answers between faces/edges/points. On the
mesh kernel we group triangles into logical faces (the viewport already
does this for highlighting) and answer with plane fits: area, centroid,
normal, planarity — and between two faces the angle plus the closest
distance, which covers the maker classics (wall gap, deck thickness,
chamfer angle)."""
from __future__ import annotations

import numpy as np


def face_stats(tm, tris) -> dict:
    """Summarise a group of mesh triangles as one logical face."""
    tris = np.asarray(sorted(tris), int)
    fn = np.asarray(tm.face_normals, float)[tris]
    n = fn.sum(0)
    n /= max(float(np.linalg.norm(n)), 1e-12)
    tri_pts = np.asarray(tm.vertices, float)[np.asarray(tm.faces, int)[tris]]
    pts = np.unique(tri_pts.reshape(-1, 3), axis=0)
    area = float(np.asarray(tm.area_faces, float)[tris].sum())
    c = pts.mean(0)
    off = float(np.abs((pts - c) @ n).max())        # off-plane corner reach
    return dict(tris=tris, area=area, center=c, normal=n, pts=pts,
                planar=off < 1e-4 * max(1.0, float(np.linalg.norm(tm.extents))))


def angle_between(a: dict, b: dict) -> float:
    """Degrees between the two faces' normals (0 = parallel same way,
    180 = opposed).  Coplanar-facing pairs read as 180."""
    d = float(np.clip(np.dot(a["normal"], b["normal"]), -1.0, 1.0))
    return float(np.degrees(np.arccos(d)))


def closest_distance(a: dict, b: dict) -> float:
    """Closest vertex-to-vertex distance between the two face groups —
    exact on this kernel's grid-aligned tessellations."""
    va, vb = a["pts"], b["pts"]
    va = va[:: max(1, len(va) // 2000)]             # bound the work
    vb = vb[:: max(1, len(vb) // 2000)]
    d2 = ((va[:, None, :] - vb[None, :, :]) ** 2).sum(-1)
    return float(np.sqrt(d2.min()))


def describe(a: dict, b: dict | None) -> str:
    """One-line measurement, Fusion status-bar style."""
    if b is None:
        return f"face area {a['area']:.1f} mm²" + (
            "" if a["planar"] else "  (curved)")
    ang = angle_between(a, b)
    dist = closest_distance(a, b)
    if abs(ang - 180.0) < 0.5 or ang < 0.5:
        kind = "parallel" if abs(ang - 180.0) < 0.5 else "parallel (same way)"
        return f"{kind}: gap {dist:.2f} mm"
    if abs(ang - 90.0) < 0.5:
        return f"perpendicular, meeting at {closest_distance(a, b):.2f} mm"
    return f"angle {ang:.1f}°, closest {dist:.2f} mm"
