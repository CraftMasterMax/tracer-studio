"""Circular rim fillets/chamfers computed straight from the mesh.

The OCCT bridge deliberately skips tessellated circle rims (a hole wall
is hundreds of short straight facets, none of which can host a fillet).
But a rim is where makers most want rounding, and its geometry is pure
revolution: in the (radius, height) cross-section the wall is a vertical
line, the cap a horizontal one, and the fillet a quarter circle. So the
round-over is just a revolved 2D profile:

    convex rim  -> subtract  square minus quarter-disk   (cut the corner)
    concave rim -> union     quarter-disk                 (add the bead)

Fully kernel-side (manifold3d), so it also works on stock Windows where
OpenCascade is absent. No surface fitting, no OCCT, no guessing.
"""
from __future__ import annotations

import numpy as np

from .geometry import Solid

_SHARP_DEG = 25.0     # fold angle between faces that counts as a crease
_CIRCLE_TOL = 0.03    # circle-fit residual, fraction of radius
_ARC_SEG = 24         # quarter-circle resolution
_MIN_EDGES = 8        # a rim loop below this is noise


def _loops(edge_pairs) -> list[tuple[np.ndarray, list[int]]]:
    """Chain sharp edges into closed loops; returns (ordered verts,
    edge row indices) per loop. Loops touching a degree-3 vertex are
    dropped (ambiguous routing)."""
    adj: dict[int, list[tuple[int, int]]] = {}
    for i, (a, b) in enumerate(edge_pairs):
        adj.setdefault(int(a), []).append((int(b), i))
        adj.setdefault(int(b), []).append((int(a), i))
    used = [False] * len(edge_pairs)
    out = []
    for s in adj:
        if all(used[e] for _, e in adj[s]):
            continue
        verts, erows, prev_e, cur = [s], [], None, s
        while True:
            nxt = None
            for v, e in adj[cur]:
                if e != prev_e and not used[e]:
                    nxt = (v, e)
                    break
            if nxt is None:
                break
            v, e = nxt
            used[e] = True
            erows.append(e)
            verts.append(v)
            prev_e, cur = e, v
            if cur == s:
                break
        if len(erows) < _MIN_EDGES or cur != s or verts[-1] != s:
            continue
        ring = verts[:-1]
        if any(len(adj[v]) != 2 for v in ring):
            continue
        out.append((np.asarray(ring), erows))
    return out


def _fit_circle(pts: np.ndarray):
    """Least-squares 3D circle: (center, unit axis, radius) or None."""
    c = pts.mean(0)
    _, s, vt = np.linalg.svd(pts - c)
    if s[2] > 1e-4 * max(s[0], 1e-12):              # must be planar
        return None
    w = vt[2]
    x = (pts - c) @ vt[0]
    y = (pts - c) @ vt[1]
    A = np.column_stack([x, y, np.ones_like(x)])
    D, E, F = np.linalg.lstsq(A, -(x * x + y * y), rcond=None)[0]
    r2 = D * D / 4 + E * E / 4 - F
    if r2 <= 0:
        return None
    r = float(np.sqrt(r2))
    cx, cy = -D / 2, -E / 2
    if np.abs(np.hypot(x - cx, y - cy) - r).max() > _CIRCLE_TOL * r:
        return None
    ctr = c + cx * vt[0] + cy * vt[1]
    return ctr, w / np.linalg.norm(w), r


def find_rims(solid: Solid) -> list[dict]:
    """Every sharp closed loop that is a true circle, classified."""
    import trimesh
    tm: trimesh.Trimesh = solid.to_trimesh()
    fn = tm.face_normals
    pairs, edges = tm.face_adjacency, tm.face_adjacency_edges
    dots = np.einsum("ij,ij->i", fn[pairs[:, 0]], fn[pairs[:, 1]])
    keep = np.degrees(np.arccos(np.clip(dots, -1.0, 1.0))) > _SHARP_DEG
    sharp, sharp_pairs = edges[keep], pairs[keep]
    out = []
    for verts, erows in _loops(sharp):
        fit = _fit_circle(tm.vertices[verts])
        if fit is None:
            continue
        ctr, w, r = fit
        if r < 0.05:
            continue
        pts = tm.vertices[verts]
        rel = pts - ctr
        rho = rel - np.outer(rel @ w, w)
        nrm = np.linalg.norm(rho, axis=1)
        if (nrm < 1e-9).any():
            continue
        rho = rho / nrm[:, None]
        dmat = []
        for k, e in enumerate(erows):
            f1, f2 = sharp_pairs[e]
            n1, n2 = fn[f1], fn[f2]
            a1, a2 = abs(n1 @ w), abs(n2 @ w)
            wall, cap = (n1, n2) if a1 <= a2 else (n2, n1)
            if max(a1, a2) < 0.7 or min(a1, a2) > 0.5:
                dmat = None                          # cone-ish: hands off
                break
            dmat.append((-np.sign(wall @ rho[k]), -np.sign(cap @ w)))
        if not dmat:
            continue
        dmat = np.asarray(dmat, float)
        if not (np.abs(dmat.mean(0)) >= 0.8).all():   # inconsistent loop
            continue
        dr_mat = float(np.sign(dmat[:, 0].mean()))
        dh_mat = float(np.sign(dmat[:, 1].mean()))
        # convex vs concave: what fraction around each rim point is solid?
        eps = 0.2 * r
        probe, stride = [], max(1, len(pts) // 16)
        for p, pr in zip(pts[::stride], rho[::stride]):
            for j in range(8):
                a = np.radians(45 * j + 22.5)
                probe.append(p + eps * (np.cos(a) * pr + np.sin(a) * w))
        inside = float(tm.contains(np.asarray(probe)).mean())
        if not (inside < 0.4 or inside > 0.6):
            continue                                 # ambiguous: hands off
        out.append(dict(center=ctr, axis=w, radius=r,
                        dr_mat=dr_mat, dh_mat=dh_mat,
                        concave=bool(inside > 0.55)))
    return out


def _tool(rim: dict, size: float, chamfer: bool) -> Solid | None:
    """The revolved cutter (convex) or bead (concave), placed in world.

    In normalized corner coords a=dr·(ρ−r), b=dh·(z−z0) both are the same
    polygon: the corner square [0,R]² minus the quarter-disk of radius R
    centered at (R,R). That arc is tangent to both faces, so the round-over
    blends in smoothly — a second pass finds no sharp rim there.

    The square is extended a hair past a=0: a tool face exactly coincident
    with the *curved* wall would force the boolean to weld two different
    tessellations of the same cylinder, fanning the whole wall with
    zero-area slivers. The overlap lands in void (cutter) or in existing
    material (bead), so it is invisible, while wall coincidence never
    happens. Coincidence with the planar cap is safe (manifold is exact
    on coplanar planes) and is kept flush.
    """
    r, R = rim["radius"], size
    dr, dh = (rim["dr_mat"], rim["dh_mat"])
    if rim["concave"]:
        dr, dh = -dr, -dh                            # bead fills the void
    if dr < 0 and r - R <= 1e-6:
        return None                                  # tool would cross axis
    d = min(0.005, 0.02 * R)                         # anti-coincidence skirt
    P = lambda a, b: (r + dr * a, dh * b)             # noqa: E731
    if chamfer:
        pts = [P(-d, 0.0), P(R, 0.0), P(0.0, R)]
    else:
        th = np.linspace(np.pi, 1.5 * np.pi, _ARC_SEG + 1)
        arc = [P(R + R * np.cos(t), R + R * np.sin(t)) for t in th]
        pts = [P(R, 0.0), P(-d, 0.0), P(-d, R), P(0.0, R)] + arc[1:-1]
    pts = np.asarray(pts, float)
    if pts[:, 0].min() <= 1e-9:
        return None
    cr = pts[:-1, 0] * pts[1:, 1] - pts[1:, 0] * pts[:-1, 1]
    cr = np.append(cr, pts[-1, 0] * pts[0, 1] - pts[0, 0] * pts[-1, 1])
    if cr.sum() < 0:
        pts = pts[::-1]
    tool = Solid.revolve(pts, angle=360.0)
    w = np.asarray(rim["axis"], float)
    ref = np.array([1.0, 0.0, 0.0]) if abs(w[0]) < 0.9 else \
        np.array([0.0, 1.0, 0.0])
    u = np.cross(ref, w)
    u /= np.linalg.norm(u)
    v = np.cross(w, u)
    m = np.eye(4)
    m[:3, :3] = np.column_stack([u, v, w])
    m[:3, 3] = rim["center"]
    return tool.transformed(m)


def rim_fillet(solid: Solid, size: float, chamfer: bool = False):
    """Round every circular rim; returns (solid, n_applied)."""
    out, applied = solid, 0
    for rim in find_rims(solid):
        tool = _tool(rim, size, chamfer)
        if tool is None:
            continue                                 # oversized: skip rim
        out = (out.union(tool) if rim["concave"] else out.subtract(tool))
        applied += 1
    return out, applied
