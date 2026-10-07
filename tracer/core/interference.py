"""Interference audit — the collision layer the assembly phase opens
with (joint report actionable #3, queue tail "collision first!").

Fusion's Interference command measures a clash and throws the geometry
away — the InterferenceResults API hands back volumes with no way to
make a solid of them in a parametric file. Our manifold booleans can:
every clash here is both a NUMBER and, if the user asks, a BODY — an
InterferenceFeature whose solid re-computes while the parts move.

Broad phase: axis-aligned bounding boxes (no boolean, pure numpy).
Narrow phase: the real (a & b) — manifold intersection, exact volume.
Touching is NOT clashing (the sane default Fusion also picked): two
bodies sharing only a face interfere zero and are not reported.
"""
from __future__ import annotations

import numpy as np


def pairs(solids: dict, *, tol: float = 1e-6) -> list[dict]:
    """All clashing pairs among {name: Solid}: [{a, b, volume}], biggest
    clash first. Bodies that merely touch never clear `tol`."""
    names = sorted(solids)
    boxes = {n: np.asarray(solids[n].bounding_box, float) for n in names}
    out = []
    for i, a in enumerate(names):
        ba = boxes[a]
        for b in names[i + 1:]:
            bb = boxes[b]
            if np.any(ba[0] > bb[1]) or np.any(bb[0] > ba[1]):
                continue                     # AABBs miss: no boolean
            v = float(solids[a].intersect(solids[b]).volume)
            if v > tol:
                out.append({"a": a, "b": b, "volume": v})
    out.sort(key=lambda r: -r["volume"])
    return out
