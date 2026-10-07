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


def describe(a: dict, b: dict | None, unit: str = "mm") -> str:
    """One-line measurement, Fusion status-bar style, in document
    measures (M60)."""
    from . import units
    if b is None:
        return f"face area {units.A(a['area'], unit, sep=False)}" + (
            "" if a["planar"] else "  (curved)")
    ang = angle_between(a, b)
    dist = closest_distance(a, b)
    if abs(ang - 180.0) < 0.5 or ang < 0.5:
        kind = "parallel" if abs(ang - 180.0) < 0.5 else "parallel (same way)"
        return f"{kind}: gap {units.D(dist, unit)}"
    if abs(ang - 90.0) < 0.5:
        return (f"perpendicular, meeting at "
                f"{units.D(closest_distance(a, b), unit)}")
    return f"angle {ang:.1f}°, closest {units.D(dist, unit)}"


def mass_properties(solid, density_g_cm3: float = 1.0) -> dict:
    """Fusion's Inspect ▸ Mass Properties (M71): the body's volume and
    surface area, its mass at a material density (g/cm³ — 1 cm³ =
    1000 mm³), and the centre of mass, which for a watertight solid is
    the true volume centroid from the mesh kernel."""
    vol = float(solid.volume)
    com = np.asarray(
        solid.to_trimesh().mass_properties.center_mass, float)
    return dict(volume_mm3=vol,
                area_mm2=float(solid.surface_area),
                mass_g=vol / 1000.0 * float(density_g_cm3),
                com=com)


def extents(solid) -> dict:
    """Show-Extents (M117): the box the part lives in — Fusion has no
    overall-extents readout at all, so this is a beat, not a clone."""
    bb = np.asarray(solid.bounding_box, float)
    size = bb[1] - bb[0]
    return dict(size_mm=tuple(float(s) for s in size),
                diagonal_mm=float(np.linalg.norm(size)),
                min_mm=tuple(float(s) for s in bb[0]),
                max_mm=tuple(float(s) for s in bb[1]))


def principal_inertia(solid, density_g_cm3: float = 1.0) -> dict:
    """Mass moments and principal axes about the centre of mass (M117),
    in g·mm² — the numbers SolidWorks' Mass Properties dialog shows and
    Fusion's UI never does (its dialog page does not exist [—V]).

    Exact for a watertight mesh: every boundary triangle closes a
    signed tetrahedron against the origin, and the second-moment
    integral of a tetrahedron is a 20-line closed form; the kernel's
    outward winding carries the signs. Then the tensor is moved to the
    centre of mass and diagonalised."""
    tm = solid.to_trimesh()
    v = np.asarray(tm.vertices, float)
    f = np.asarray(tm.faces, int)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    det = np.einsum("ni,ni->n", a, np.cross(b, c))       # 6·V signed
    rho = float(density_g_cm3) / 1000.0                   # g/mm³
    mass = det.sum() / 6.0 * rho
    s = a + b + c
    # ∫ x dV = V·(a+b+c)/4 = det·s/24 per tetrahedron
    com = (det[:, None] * s).sum(0) / 24.0 / (det.sum() / 6.0)
    # ∫ x xᵀ dV over tetrahedron(0,a,b,c) = V/20·(Σ p pᵀ + s sᵀ)
    G = np.zeros((3, 3))
    for p in (a, b, c):
        G += (det[:, None] * p).T @ p            # Σ det·p pᵀ
    SS = (det[:, None] * s).T @ s                # Σ det·s sᵀ
    J = (G + SS) / 120.0 * rho                            # about origin
    I0 = np.trace(J) * np.eye(3) - J
    d = com
    I = I0 - mass * (float(d @ d) * np.eye(3) - np.outer(d, d))
    w, axes = np.linalg.eigh(I)
    w = np.maximum(w, 0.0)                                # float dust
    return dict(mass_g=float(mass), com=com,
                moments_g_mm2=tuple(float(x) for x in w),
                axes=axes)


def section_properties(loops) -> dict | None:
    """The readout Fusion's Section Analysis never had (no area, no
    perimeter, no centroid on a cut face [—V]) — shoelace integrals over
    the closed cut loops, holes subtracted by nesting depth (M117)."""
    polys = [np.asarray(l, float) for l in loops if len(l) >= 3]
    if not polys:
        return None
    areas, cents, perims = [], [], []
    for P in polys:
        x, y = P[:, 0], P[:, 1]
        x2, y2 = np.roll(x, -1), np.roll(y, -1)
        cross = x * y2 - x2 * y
        A2 = cross.sum() / 2.0                     # signed area
        areas.append(abs(A2))
        if abs(A2) < 1e-12:
            cents.append(P.mean(0))
        else:
            cents.append(np.column_stack([
                (x + x2) * cross, (y + y2) * cross]).sum(0) / (6.0 * A2))
        perims.append(float(np.hypot(*(P - np.roll(P, -1, 0)).T).sum()))

    def inside(pt, Q):                              # ray-cast, inclusive
        x, y = pt
        inside_ = False
        n = len(Q)
        for i in range(n):
            x1, y1 = Q[i]
            x2, y2 = Q[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                xt = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if xt > x:
                    inside_ = not inside_
        return inside_

    depth = [sum(inside(P[0], Q) for j, Q in enumerate(polys) if j != i
                 ) for i, P in enumerate(polys)]
    sign = np.array([1.0 if d % 2 == 0 else -1.0 for d in depth])
    area = float((sign * np.array(areas)).sum())
    if area <= 1e-12:
        return None
    cen = (sign * np.array(areas)[:, None]
           * np.array(cents)).sum(0) / area
    return dict(area_mm2=area,
                perimeter_mm=float(np.array(perims).sum()),
                centroid=(float(cen[0]), float(cen[1])),
                loops=len(polys),
                holes=int((np.array(depth) % 2 == 1).sum()))
