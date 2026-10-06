"""Glyph outlines for embossed / engraved text (M76).

Qt's own path engine tessellates the glyphs; we sort the contours into
closed 2D profiles: every outer contour (a glyph island) plus its
counters — the eye of an 'A', the middle of a '0' — found by containment,
not by winding (the kernel's cross-sections fill EvenOdd anyway).  The
line is scaled so its cap-to-baseline bbox height is the requested mm
and centred on the origin, so a command can drop it at any placement.

Windows taught this module two hard lessons.  First, a glyph's outer and
its counter can arrive welded into one self-crossing ring — buffer(0)
untangles that.  Second, and worse: before the platform font engine is
fully awake, a QFont resolves to .notdef and EVERY letter tessellates as
one square tofu box — silently, validly, and with a perfectly plausible
area.  So we ship a font (Liberation Sans, SIL OFL — see
resources/fonts/) and register it with the application, we prefer it
above system families, and we VETO any tessellation that is nothing but
boxy rings: a rejected candidate falls through to the next; a total
failure returns [] and the command warns instead of embossing squares.

Requires a live QApplication (the font engine insists).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

_BUNDLED_TTF = (Path(__file__).resolve().parent.parent
                / "resources" / "fonts" / "LiberationSans-Regular.ttf")
_BUNDLED: str | None = None          # "" = tried and absent; None = not yet


def _signed_area(pts: np.ndarray) -> float:
    return 0.5 * float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1)
                              - np.roll(pts[:, 0], -1) * pts[:, 1]))


def _bundled_family() -> str | None:
    """Register the shipped Liberation Sans once; its family name then
    resolves without the OS font chain or a half-warm engine."""
    global _BUNDLED
    if _BUNDLED is not None:
        return _BUNDLED or None
    fam = ""
    try:
        from PySide6.QtGui import QFontDatabase
        if _BUNDLED_TTF.exists():
            fid = QFontDatabase.addApplicationFont(str(_BUNDLED_TTF))
            if fid != -1:
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    fam = fams[0]
    except Exception:
        fam = ""
    _BUNDLED = fam
    return fam or None


def _rings(path) -> list[np.ndarray]:
    """QPainterPath subpaths -> y-up rings, welded contours untangled."""
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
        # DirectWrite (Windows) can hand one glyph's outer AND its
        # counter as ONE concatenated ring — self-crossing where the
        # jump edge cuts across.  buffer(0) untangles it back into
        # filled parts; their exterior rings and interior rings fall out
        # as separate loops, and the containment tree does the rest.
        g = g.buffer(0)
        for part in getattr(g, "geoms", [g]):
            if part.is_empty or not isinstance(part, _Poly):
                continue
            polys.append(np.asarray(part.exterior.coords[:-1], float))
            for hole in part.interiors:
                polys.append(np.asarray(hole.coords[:-1], float))
    return polys


def _all_tofu(polys) -> bool:
    """True when every ring is a square, fully-filled rectangle — the
    .notdef box a cold Windows font engine draws for every letter.
    Real type never looks like this: an 'I' is a THIN bar, an 'O' is
    many points, and no letter fills its own bounding box."""
    def boxy(pts) -> bool:
        if len(pts) > 6:
            return False
        w = float(np.ptp(pts[:, 0]))
        h = float(np.ptp(pts[:, 1]))
        if w <= 0 or h <= 0:
            return True
        return (abs(w - h) <= 0.25 * max(w, h)
                and abs(_signed_area(pts)) >= 0.85 * w * h)
    return bool(polys) and all(boxy(p) for p in polys)


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
    # Querying the database populates it — the first half of the Windows
    # cold-engine lesson.  The second half is the bundled font plus the
    # tofu veto below: prefer what EXISTS, and refuse what is a box.
    db = {f.lower(): f for f in QFontDatabase.families()}
    cands: list[str] = []
    if family:
        cands.append(family)
    bundled = _bundled_family()
    if bundled:
        cands.append(bundled)
    for cand in ("DejaVu Sans", "Liberation Sans", "Arial", "Segoe UI",
                 "Verdana", "Helvetica Neue", "Helvetica", "Noto Sans",
                 "Sans"):
        real = db.get(cand.lower())
        if real and real not in cands:
            cands.append(real)
    polys: list[np.ndarray] = []
    for fam in cands:
        font = QFont(fam)
        font.setPixelSize(100)
        path = QPainterPath()
        path.addText(0, 0, font, text)
        polys = _rings(path)
        if polys and not _all_tofu(polys):
            break                        # a candidate that drew LETTERS
    else:
        polys = []                       # every candidate boxed: none
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
