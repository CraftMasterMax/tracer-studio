"""Glyph outlines for embossed / engraved text (M76).

System-font outlines tessellated by Qt's own path engine, sorted into
closed 2D profiles: every outer contour (a glyph island) plus its
counters — the eye of an 'A', the middle of a '0' — found by containment,
not by winding (the kernel's cross-sections fill EvenOdd anyway).  The
line is scaled so its cap-to-baseline bbox height is the requested mm
and centred on the origin, so a command can drop it at any placement.

Extrude the regions and you have Fusion's Sketch Text + Extrude, without
the sketch.  Requires a live QApplication (the font engine insists).
"""
from __future__ import annotations

import numpy as np


def _signed_area(pts: np.ndarray) -> float:
    return 0.5 * float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1)
                              - np.roll(pts[:, 0], -1) * pts[:, 1]))


def glyph_regions(text: str, height_mm: float,
                  family: str | None = None) -> list[dict]:
    """[{"outer": Nx2 float, "holes": [Mx2 float, …]}, …] — one region
    per glyph island, y-up, centred, bbox height == height_mm.
    Returns [] for whitespace-only text or a font that drew nothing."""
    if not text or not text.strip():
        return []
    from PySide6.QtGui import QFont, QFontDatabase, QPainterPath
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        raise RuntimeError("glyph_regions needs a running QApplication")
    # Asking the database FIRST populates it — before that, Windows
    # resolves unknown families (like the alias "Sans") to .notdef and
    # every glyph tessellates as one tofu rectangle.  Then we pick a
    # family that actually EXISTS on this machine.
    fams = {f.lower(): f for f in QFontDatabase.families()}
    exact = None
    for cand in ([family] if family else
                 ["DejaVu Sans", "Liberation Sans", "Arial", "Segoe UI",
                  "Verdana", "Helvetica Neue", "Helvetica", "Noto Sans"]):
        if cand.lower() in fams:
            exact = fams[cand.lower()]
            break
    font = QFont(exact or family or "Sans")
    font.setPixelSize(100)
    path = QPainterPath()
    path.addText(0, 0, font, text)

    from shapely.geometry import Polygon as _Poly

    polys: list[np.ndarray] = []
    for sp in path.toSubpathPolygons():
        pts = np.array([(p.x(), -p.y()) for p in sp], float)   # y-up
        if len(pts) < 3 or abs(_signed_area(pts)) < 1e-9:
            continue
        g = _Poly(pts)
        if g.is_valid:
            polys.append(pts)
            continue
        # DirectWrite (Windows) hands one glyph's outer AND its counter as
        # ONE concatenated ring — self-crossing where the jump edge cuts
        # across.  buffer(0) untangles it back into filled parts; their
        # exterior rings and interior rings fall out as separate loops,
        # and the containment tree below does the rest.
        g = g.buffer(0)
        for part in getattr(g, "geoms", [g]):
            if part.is_empty or not isinstance(part, _Poly):
                continue
            polys.append(np.asarray(part.exterior.coords[:-1], float))
            for hole in part.interiors:
                polys.append(np.asarray(hole.coords[:-1], float))
    if not polys:
        return []

    # containment decides: an island is outer; anything inside another
    # polygon is its counter (nested deeper than one level: rare in text,
    # treated as a hole of its container either way)
    from shapely.geometry import Point, Polygon
    shapes = [Polygon(p) for p in polys]
    parent = [None] * len(polys)
    for i, si in enumerate(shapes):
        for j, sj in enumerate(shapes):
            # a parent must ENCLOSE and OUTRANK: an O's own centroid sits
            # in its counter, and the counter 'contains' the outer's rep
            # point as a plain polygon — area order breaks the tie-up
            if (i == j or abs(sj.area) <= abs(si.area)
                    or not sj.contains(Point(si.representative_point()))):
                continue
            if parent[i] is None or shapes[parent[i]].area > sj.area:
                parent[i] = j
    roots = [i for i in range(len(polys)) if parent[i] is None]
    holes_of = {r: [k for k in range(len(polys))
                    if k != r and _inside_root(k, r, parent)]
                for r in roots}
    # EvenOdd fill means every deeper nesting flips back to material, so
    # a whole containment tree folds to root + its holes at any depth

    allp = np.vstack([polys[r] for r in roots])
    lo, hi = allp.min(0), allp.max(0)
    s = float(height_mm) / max(float(hi[1] - lo[1]), 1e-9)
    c = (lo + hi) / 2.0
    out = []
    for r in roots:
        outer = (polys[r] - c) * s
        holes = [(polys[k] - c) * s for k in holes_of[r]]
        # font tessellation can repeat the seam vertex
        if len(outer) > 1 and np.allclose(outer[0], outer[-1]):
            outer = outer[:-1]
        holes = [h[:-1] if len(h) > 1 and np.allclose(h[0], h[-1]) else h
                 for h in holes]
        out.append(dict(outer=outer, holes=holes))
    out.sort(key=lambda reg: float(np.asarray(reg["outer"])[:, 0].mean()))
    return out


def _inside_root(idx, root, parent) -> bool:
    p = parent[idx]
    while p is not None:
        if p == root:
            return True
        p = parent[p]
    return False
