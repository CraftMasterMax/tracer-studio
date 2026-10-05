"""Shell: hollow a solid and open it at a removed face (Fusion Shell).

Recipe in the mesh kernel.  The cavity is the body eroded by the wall
thickness (Minkowski difference with a ball — the inner parallel body:
an exact inset for prismatic parts, softly rounded inner corners for
organic ones, like a real moulded case).  Material removed is the cavity
PLUS a window punched through each opened face: copies of the cavity
lifted along the face normal in steps of t/4 — small enough that every
interior column under the face stays covered — and clipped to the slab
BELOW that face, so the window breaches the ceiling right under it but
never perforates a taller feature standing on the deck.  One final
subtract yields the shell; prismatic parts come out analytically exact.
"""
from __future__ import annotations

import math

import numpy as np
import manifold3d as m3

from .geometry import Solid
from .sketch.model import frame_matrix


def _slab(point: np.ndarray, n: np.ndarray, d: float) -> Solid:
    """Huge box spanning ±d in-plane and [−d, 0] along n from `point` —
    the half-space on the material side of the opened face plane."""
    a = np.abs(n)
    u = np.cross(n, np.eye(3)[int(a.argmin())])
    u /= np.linalg.norm(u)
    m = frame_matrix(u, np.cross(n, u), tuple(point))   # local +z = n
    return Solid.box(2 * d, 2 * d, d).translated((-d, -d, -d)).transformed(m)


def shell_open(solid: Solid, thickness: float,
               openings: list[tuple[tuple, tuple]]) -> Solid:
    """openings: list of (point on the face, outward unit normal)."""
    t = float(thickness)
    if t <= 0:
        raise ValueError("shell thickness must be positive")
    cav = Solid(solid._m.minkowski_difference(m3.Manifold.sphere(t, 32)))
    if cav._m.is_empty() or cav.volume <= 1e-9:
        raise ValueError(f"wall thickness {t:g} mm leaves no interior — "
                         "this body is too thin to shell")
    lo, hi = solid.bounding_box
    d = float(np.linalg.norm(hi - lo)) + 2 * t
    c_lo, c_hi = cav.bounding_box
    tool = cav
    for pt, nrm in openings:
        n = np.asarray(nrm, float)
        n = n / float(np.linalg.norm(n))
        p = np.asarray(pt, float)
        # cavity span along n, sign-aware (bbox corners follow the axis)
        pos = n > 0
        lo_n = float(n @ np.where(pos, c_lo, c_hi))
        hi_n = float(n @ np.where(pos, c_hi, c_lo))
        if hi_n - lo_n < t:
            raise ValueError(
                "not enough room under the opened face to carry a "
                f"{t:g} mm wall through the body")
        step = t / 4.0
        reach = max(float(p @ n) + t - lo_n, step)
        k_max = min(math.ceil(reach / step), 300)
        lifted = cav.translated(tuple(n * step))       # k = 1..k_max
        for k in range(2, k_max + 1):
            lifted = lifted.union(cav.translated(tuple(n * (k * step))))
        tool = tool.union(lifted.intersect(_slab(p + n * t, n, d)))
    out = solid.subtract(tool)
    if out.volume <= 1e-9:
        raise ValueError("shell removed the whole body")
    return out
