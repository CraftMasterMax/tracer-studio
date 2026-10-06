"""M99 — Thicken: an open sketch chain becomes a solid wall.

Fusion's Patch/Thicken speaks surfaces; on the mesh kernel the honest
twin is a buffer. Each OPEN chain of the sketch (lines and arcs,
construction geometry excluded) is thickened to `thickness` with
BUTT caps — a straight wall is exactly length x thickness, no
semicircular ears — and ROUND joins, so corners bend like sheet metal
instead of mitre-spiking. Overlapping chains union into one wall
before extrusion, and the strip extrudes `depth` along the plane
normal in the feature's own transform. Closed loops are refused with
directions: a closed profile is Extrude's job, and a maker who means
Extrude deserves to hear it, not a surprise sliver.
"""
from __future__ import annotations

import numpy as np

from .drawing import _chain
from .geometry import Solid


def open_chains(model) -> list:
    """The sketch's open (non-closed) chains as sampled polylines in
    sketch coordinates. Raises ValueError with a maker-readable reason
    when the sketch has nothing open to thicken."""
    from .sketch.entities import Arc
    from .sweep import _arc_samples
    segs = []
    for e in list(model.sketch.lines) + list(model.sketch.arcs):
        if getattr(e, "construction", False):
            continue
        if isinstance(e, Arc):
            pts = _arc_samples((e.a.x, e.a.y), (e.m.x, e.m.y),
                               (e.b.x, e.b.y))
        else:
            pts = [(e.a.x, e.a.y), (e.b.x, e.b.y)]
        for p, q in zip(pts, pts[1:]):
            if float(np.hypot(q[0] - p[0], q[1] - p[1])) > 1e-9:
                segs.append([p, q])
    if not segs:
        raise ValueError("Thicken wants open edges: draw a line or an arc.")
    chains = [[tuple(map(float, p)) for p in c]
              for c in _chain(np.asarray(segs, float))]
    # the M93 walker extends from one tip only, so a trail that starts
    # mid-path leaves its two halves apart — stitch what meets at an end
    merged = True
    while merged:
        merged = False
        for i in range(len(chains)):
            for j in range(i + 1, len(chains)):
                a, b = chains[i], chains[j]
                if a[-1] == b[0]:
                    chains[i] = a + b[1:]
                elif a[-1] == b[-1]:
                    chains[i] = a + b[-2::-1]
                elif a[0] == b[-1]:
                    chains[i] = b + a[1:]
                elif a[0] == b[0]:
                    chains[i] = b[::-1] + a[1:]
                else:
                    continue
                del chains[j]
                merged = True
                break
            if merged:
                break
    out = [[(float(p[0]), float(p[1])) for p in c] for c in chains
           if not (len(c) > 3 and np.allclose(c[0], c[-1], atol=1e-9))]
    if not out:
        raise ValueError("Thicken wants OPEN edges — every chain here is "
                         "closed; use Extrude for closed profiles.")
    return out


def thicken_solids(chains, thickness: float, depth: float) -> list:
    """Buffer every chain to the thickness, union, extrude the depth.
    Returns the Solid(s) — one per disjoint wall polygon."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    polys = []
    for c in chains:
        if len(c) < 2:
            continue
        b = LineString(c).buffer(thickness / 2.0, cap_style="flat",
                                 join_style="round")
        if b.is_empty or b.area <= 1e-9:
            continue
        if b.geom_type == "Polygon":
            polys.append(b)
        else:                              # GeometryCollection leftovers
            polys.extend(g for g in b.geoms
                         if g.geom_type == "Polygon" and g.area > 1e-9)
    if not polys:
        return []
    u = polys[0] if len(polys) == 1 else unary_union(polys)
    faces = [u] if u.geom_type == "Polygon" else \
        [g for g in u.geoms if g.geom_type == "Polygon"]
    out = []
    for f in faces:
        if f.area <= 1e-9:
            continue
        outer = [[float(x), float(y)] for x, y in f.exterior.coords[:-1]]
        holes = [[[float(x), float(y)] for x, y in h.coords[:-1]]
                 for h in f.interiors]
        out.append(Solid.extrude(outer, holes, depth))
    return out
