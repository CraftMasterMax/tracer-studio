"""Loft: a watertight solid through stacked cross-section loops.

Shared engine for Sweep (M35) and Loft (M36).  Every section — any closed
polygon floating anywhere in 3D — is resampled to the same vertex count
(spaced by arc length, so square-to-circle blends stay even), its seam is
rotated to face the previous section's nearest point (no twisting), and
consecutive rings are stitched with quads.  End faces are fan-capped from
each section's centroid; winding is corrected so the solid always points
outward.  Star-shaped profiles cap exactly; manifold3d rejects anything
else rather than producing a broken body.
"""
from __future__ import annotations

import numpy as np

from .geometry import Solid


def _poly_len(pts: np.ndarray) -> np.ndarray:
    d = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(d)])


def resample(pts: np.ndarray, n: int) -> np.ndarray:
    """n points equally spaced by arc length along a closed polyline."""
    pts = np.asarray(pts, float)
    L = _poly_len(pts)
    total = L[-1]
    if total <= 1e-12:
        raise ValueError("cross-section loop is degenerate")
    s = np.linspace(0.0, total, n, endpoint=False)
    out = np.empty((n, pts.shape[1]))
    seg = np.clip(np.searchsorted(L, s, side="right") - 1, 0, len(pts) - 2)
    t = (s - L[seg]) / np.maximum(L[seg + 1] - L[seg], 1e-12)
    t = np.clip(t, 0.0, 1.0)
    for axis in range(pts.shape[1]):
        out[:, axis] = pts[seg, axis] + t * (
            np.roll(pts[:, axis], -1)[seg] - pts[seg, axis])
    return out


def _align_seam(prev: np.ndarray, nxt: np.ndarray) -> np.ndarray:
    """Rotate nxt's start vertex to minimise total distance to prev —
    the twist-prevention trick every mesh loft needs."""
    n = len(nxt)
    d = ((prev[:, None, :] - nxt[None, :, :]) ** 2).sum(-1)
    # cost of rotating nxt by k: pair prev[i] with nxt[(i+k)%n]
    costs = [np.roll(d, -k, axis=1).diagonal().sum() for k in range(n)]
    return np.roll(nxt, -int(np.argmin(costs)), axis=0)


def loft(sections: list[np.ndarray], n: int = 64, caps: bool = True,
         loop: bool = False) -> Solid:
    """sections: closed polygon loops (M x 3) in world space, in order.
    loop=True stitches the last section back to the first (endless ring,
    no caps); otherwise the ends are capped."""
    if len(sections) < 2:
        raise ValueError("a loft needs at least two cross-sections")
    rings = [resample(np.asarray(s, float)[:, :3], n) for s in sections]
    for i in range(1, len(rings)):
        rings[i] = _align_seam(rings[i - 1], rings[i])
    V = np.vstack(rings)
    F = []

    def stitch(r0, r1):
        o0, o1 = r0 * n, r1 * n
        for i in range(n):
            a, b = o0 + i, o0 + (i + 1) % n
            c, d = o1 + i, o1 + (i + 1) % n
            F.append((a, b, c))
            F.append((b, d, c))

    for r in range(len(rings) - 1):
        stitch(r, r + 1)
    if loop:
        stitch(len(rings) - 1, 0)         # endless ring: stitch back to 0
    if caps and not loop:
        for r, flip in ((0, True), (len(rings) - 1, False)):
            cen = len(V)
            V = np.vstack([V, rings[r].mean(0)])
            for i in range(n):
                a, b = r * n + i, r * n + (i + 1) % n
                F.append((cen, b, a) if flip else (cen, a, b))
    F = np.asarray(F, np.uint32)
    m = Solid.from_mesh(V, F)._m
    if int(getattr(m.status(), "value", 0)) != 0 or m.is_empty():
        raise ValueError("these cross-sections do not form a valid solid "
                         "(try simpler convex profiles or more spacing)")
    if m.volume() < 0:                    # inward winding: flip every face
        m = Solid.from_mesh(V, F[:, ::-1].copy())._m
    if m.is_empty() or m.volume() <= 1e-9:
        raise ValueError("these cross-sections do not form a valid solid "
                         "(try simpler convex profiles or more spacing)")
    return Solid(m)
