"""Split Body (M51): trim a body with a plane, parametrically.

Fusion's most common split is "cut away one half" — Split ▸ plane ▸ keep
one side.  Multi-body splitting is out of v1 scope, so this is the maker
truth of it: subtract the half-space you don't want, leaving a flat
machined face exactly on the plane.  The tool is a slab big enough to
swallow any body, stood up on the plane along its normal; the side the
normal points at is the side that goes away (flip to choose).

The origin-plane presets and 'section' mapping share their vocabulary
with the viewport's Section Analysis, so the same pick menu drives both.
"""
from __future__ import annotations

import numpy as np

from .geometry import Solid
from .sketch.model import frame_matrix

# plane presets: normal points at the side a default split removes
PLANES = {"XY": (0.0, 0.0, 1.0),
          "XZ": (0.0, 1.0, 0.0),
          "YZ": (1.0, 0.0, 0.0)}


def half_space_tool(origin, normal, extent: float) -> Solid:
    """A slab covering the half-space the normal points INTO, from the
    plane out to `extent` (>= the body diagonal), 3x `extent` wide.
    Subtracting it from a body trims flush with the plane."""
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    e = float(extent)
    u = np.cross(n, np.eye(3)[int(np.abs(n).argmin())])
    u = u / np.linalg.norm(u)
    m = frame_matrix(u, np.cross(n, u), np.asarray(origin, float))
    slab = Solid.box(3.0 * e, 3.0 * e, e)
    return slab.translated((-1.5 * e, -1.5 * e, 0.0)).transformed(m)


def split_solid(solid: Solid, origin, normal, flip: bool = False) -> Solid:
    """Trim `solid` with the plane through `origin` (normal `normal`);
    keeps the side OPPOSITE the normal (flip reverses).  Raises
    ValueError if the plane misses the body on the kept side."""
    lo, hi = np.asarray(solid.bounding_box[0], float), \
        np.asarray(solid.bounding_box[1], float)
    extent = float(np.linalg.norm(hi - lo)) + 1e-3
    n = np.asarray(normal, float) * (-1.0 if flip else 1.0)
    out = solid.subtract(half_space_tool(origin, n, extent))
    if out.volume <= 1e-6:
        raise ValueError("the split plane misses the body — nothing left "
                         "on the kept side")
    return out
