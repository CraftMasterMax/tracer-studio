"""M93 — drawing views from the mesh: silhouettes, chained.

A B-rep CAD harvests NURBS edges for its drawings; we have a triangle
soup, so views are VIEW-DEPENDENT SILHOUETTES: an edge is drawn where
one adjacent face turns toward the viewer and the other does not
(turns away, or grazes).  That single rule lands the box outline, the
bore's facing-wall boundaries, hole rims on top views — everything a
first-angle draughtsman expects from visible lines.

Boolean tessellations scatter Steiner points along rims, so raw
segments would paint 260 crumbs where 5 lines belong: chains are
built by welding shared endpoints and walking, then collinear runs
merge.  What comes out is a dict of polylines (closed chains repeat
their first point), in a view's own 2D basis (y = page-up).
"""
from __future__ import annotations

import math

import numpy as np

VIEWS = {
    "top":   {"dir": (0.0, 0.0, 1.0), "up": (0.0, 1.0, 0.0)},
    "front": {"dir": (0.0, -1.0, 0.0), "up": (0.0, 0.0, 1.0)},
    "right": {"dir": (1.0, 0.0, 0.0), "up": (0.0, 0.0, 1.0)},
    "iso":   {"dir": (1.0, -1.0, 1.0), "up": (0.0, 0.0, 1.0)},
}
STANDARD = ["top", "front", "right", "iso"]
# [DWG-REF-SHEET-SIZE, verbatim] ISO {A4 (297mm x 210mm) | A3 (420mm x
# 297mm) | A2 (594mm x 420mm) | A1 (841mm x 594mm) | A0 (1189mm x
# 841mm) | Custom}; ASME {A (11in x 8.5in) | B (17in x 11in) | C (22in
# x 17in) | D (34in x 22in) | E (44in x 34in) | Custom}.  The inch
# members arrive in millimetres through the R16 CONVERT law (1 in =
# 25.4 mm EXACTLY - the arithmetic, never a rounded copy of the
# vendor's picture).  Orientation {Landscape | Portrait} is the
# page's own pair: every stored number below is the page's landscape
# shape; sheet_size() swaps for a portrait key.
IN_MM = 25.4
PAGES = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0),
         "A1": (841.0, 594.0), "A0": (1189.0, 841.0),
         "A": (11 * IN_MM, 8.5 * IN_MM), "B": (17 * IN_MM, 11 * IN_MM),
         "C": (22 * IN_MM, 17 * IN_MM), "D": (34 * IN_MM, 22 * IN_MM),
         "E": (44 * IN_MM, 34 * IN_MM)}          # all landscape, mm
SHEET_FAMILIES = {"ISO": ["A4", "A3", "A2", "A1", "A0"],
                  "ASME": ["A", "B", "C", "D", "E"]}
ORIENTATIONS = ("Landscape", "Portrait")
# [DWG-REF-SHEET-SIZE, verbatim] the Custom cap: "The maximum value is
# 200in or 5000mm."  VENDOR DEFECT, flagged: the two heights of the
# pair are NOT equal (200 in = 5080 mm) - we honour the millimetre
# member of the pair, the unit the cap's own table is drawn in.
SHEET_MAX_MM = 5000.0


def sheet_size(page) -> tuple:
    """Resolve a drawing's PAGE KEY to (W, H) millimetres.  The key
    grammar is the file's own voice: a family member is "A3", a
    portrait sheet appends the printed Orientation word ("A3
    Portrait"), and a custom sheet is "Custom 500x350".  Unknown keys
    keep the pre-R20 fallback (A3) - a file written by a newer door
    still draws.  A Custom sheet that breaks the page's cap or
    grammar raises ValueError and names the rule."""
    key = str(page)
    if key in PAGES:
        return PAGES[key]
    parts = key.split()
    orient = "Landscape"
    if len(parts) > 1 and parts[-1] in ORIENTATIONS:
        orient, key = parts[-1], " ".join(parts[:-1])
    if key in PAGES:
        W, H = PAGES[key]
    elif key.startswith("Custom"):
        try:                                    # "Custom WxH" (mm)
            wh = key.split(None, 1)[1].lower().replace(" ", "")
            w, h = wh.split("x")
            W, H = float(w), float(h)
        except (IndexError, ValueError):
            raise ValueError('custom sheets wear the words '
                             '"Custom <W>x<H>" in millimetres - '
                             f'not {key!r}')
        for name, v in (("width", W), ("height", H)):
            if not 0.0 < v <= SHEET_MAX_MM:
                raise ValueError(
                    f"custom {name} {v:g} mm is outside the sheet-size "
                    f"page: it prints a maximum value of {SHEET_MAX_MM:g}"
                    " mm")
    else:
        return PAGES["A3"] if orient == "Landscape" \
            else tuple(reversed(PAGES["A3"]))
    return (W, H) if orient == "Landscape" else (H, W)


# [DWG-REF-SHEET-SIZE, verbatim] the zone rows: "To specify horizontal
# zones, type in a positive even number. The maximum value is 1000."
# (and the Vertical twin).  The cap prints ONLY on this reference page;
# the same rows on DWG-REF-CREATE-DRAWING drift without it (vendor
# defect, lane D ledger) - we honour the cap.  HOW zones look is proven
# absent from the whole Fusion-Drawing book (164/164 crawl,
# cache/size31/live.md): the tick placement, letters-on-top, numbers-
# on-the-left, bottom-up numbering and the standards' letter exclusions
# are OURS-declared (M27 + the silence-stamp law), riding the same
# reserved-letter pool M136/M144 already keep for sections and datums.
ZONE_CAP = 1000


def zone_count(v, name):
    """Validate one zone count in the page's own voice; 0 (or None)
    means NO zones - our declared reading of a row the page never
    prints a default for.  Returns int."""
    if v is None:
        return 0
    n = int(v)
    if n == 0:
        return 0
    if n < 0:
        raise ValueError(f"{name} zones: the page prints 'type in a "
                         "positive even number' - {n} is not positive")
    if n % 2:
        raise ValueError(f"{name} zones: the page prints 'type in a "
                         f"positive even number' - {n} is odd")
    if n > ZONE_CAP:
        raise ValueError(f"{name} zones: the page prints 'The maximum "
                         f"value is 1000.' - {n} exceeds it")
    return n


def zone_grid(W, H, hz, vz):
    """The sheet zone ruler, OURS-drawn (the book proves no vendor
    appearance is documented): hz COLUMNS labelled from
    RESERVED_LETTERS-excluded A,B,C... left to right along the TOP,
    vz ROWS labelled 1,2,3... bottom to top along the LEFT.  Returns
    {"xs","ys","top","left"} in sheet-mm: xs/ys the interior tick
    positions, top/left [(centre, label)] the printed cells."""
    hz, vz = zone_count(hz, "Horizontal"), zone_count(vz, "Vertical")
    letters = [c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               if c not in RESERVED_LETTERS]
    if hz > len(letters):
        raise ValueError(f"horizontal zones: {hz} columns want more "
                         f"labels than the {len(letters)} letters this "
                         "kernel's standards exclude (I O Q S X Z)")
    out = {"xs": [], "ys": [], "top": [], "left": []}
    if hz:
        cw = W / hz
        out["xs"] = [i * cw for i in range(1, hz)]
        out["top"] = [((i + 0.5) * cw, letters[i]) for i in range(hz)]
    if vz:
        ch = H / vz
        out["ys"] = [i * ch for i in range(1, vz)]
        out["left"] = [((i + 0.5) * ch, str(i + 1)) for i in range(vz)]
    return out

RESERVED_LETTERS = "IOQSXZ"   # the standards' exclusions (M136/M144):
#                              sections AND datums letter from here

# The editable title-block fields (M108): what a draughtsman types.  Scale,
# page size and sheet number are DERIVED at draw time, never stored here.
TITLE_FIELDS = ("number", "title", "author", "date", "material")


def title_block(sheet: dict, meta: dict | None = None,
                page: str = "A3") -> dict:
    """Resolve a sheet's title block into sheet-mm geometry + text (M108).

    Coordinates are the sheet's own space (y-up, origin lower-left) so the
    canvas maps them through the same s2p as every view, and the DXF writer
    can emit the frame as plain line art (text stays the PNG's job, exactly
    as with dimension bubbles).  ``meta`` carries the derived strings the
    caller knows: ``scale`` (e.g. "1:2"), ``page`` and ``sheet`` ("1 / 1").
    Every field degrades to a sane default — an untouched sheet still shows
    a populated, honest block.
    """
    block = dict(sheet.get("block") or {})
    meta = meta or {}
    W, H = sheet_size(page)
    margin = 10.0
    wblk = min(180.0, W - 2 * margin)
    hblk = min(40.0, H - 2 * margin)
    x0, y0 = W - margin - wblk, margin
    r1, r2 = y0 + hblk / 3.0, y0 + 2 * hblk / 3.0        # row boundaries
    cx, dx = x0 + wblk / 2.0, x0 + wblk / 3.0
    ex = x0 + 2 * wblk / 3.0
    lines = [((x0, y0), (x0 + wblk, y0)),
             ((x0 + wblk, y0), (x0 + wblk, y0 + hblk)),
             ((x0 + wblk, y0 + hblk), (x0, y0 + hblk)),
             ((x0, y0 + hblk), (x0, y0)),
             ((x0, r1), (x0 + wblk, r1)), ((x0, r2), (x0 + wblk, r2)),
             ((cx, r1), (cx, r2)), ((dx, y0), (dx, r1)), ((ex, y0), (ex, r1))]
    title = block.get("title") or sheet.get("name", "")
    num = block.get("number", "")
    yt, ym, yb = (r2 + y0 + hblk) / 2, (r1 + r2) / 2, (y0 + r1) / 2
    xL, xR = x0, x0 + wblk
    # each cell carries the column box [xa,xb] it lives in + a y centre, so
    # the painter aligns/clips text inside its own box (never bleeding into
    # the neighbour across a divider).
    cells = [
        {"text": title, "xa": x0, "xb": cx, "y": yt,
         "size": hblk / 3 * 0.5, "align": "l"},
        {"text": num, "xa": cx, "xb": xR, "y": yt,
         "size": hblk / 3 * 0.5, "align": "r"},
        {"text": f"Drawn: {block.get('author', '')}" if block.get("author")
         else "Drawn:", "xa": x0, "xb": cx, "y": ym,
         "size": hblk / 3 * 0.38, "align": "l"},
        {"text": f"Date: {block.get('date', '')}" if block.get("date")
         else "Date:", "xa": cx, "xb": xR, "y": ym,
         "size": hblk / 3 * 0.38, "align": "l"},
        {"text": f"Scale {meta.get('scale', '')}".strip(), "xa": x0, "xb": dx,
         "y": yb, "size": hblk / 3 * 0.38, "align": "l"},
        {"text": (block.get("material") if block.get("material")
                  else "—"), "xa": dx, "xb": ex, "y": yb,
         "size": hblk / 3 * 0.38, "align": "c"},
        {"text": f"Sheet {meta.get('sheet', '')}".strip(), "xa": ex, "xb": xR,
         "y": yb, "size": hblk / 3 * 0.38, "align": "r"},
    ]
    return {"rect": (x0, y0, wblk, hblk), "lines": lines, "cells": cells,
            "page": page}


def _basis(view) -> tuple:
    """View key -> (eye, page-x, page-y). A named standard view reads
    VIEWS; a 3-tuple of vectors (d, X, Y) is a section child's own
    basis and passes straight through — the whole projection pipeline
    is matrix maths over this triple, so arbitrary-direction sections
    reuse every consumer unchanged (M136)."""
    if isinstance(view, (tuple, list)):
        d, X, Y = (np.asarray(a, float) for a in view)
        d = d / np.linalg.norm(d)
        X = X / np.linalg.norm(X)
        Y = Y / np.linalg.norm(Y)
        return d, X, Y
    d = np.asarray(VIEWS[view]["dir"], float)
    d = d / np.linalg.norm(d)
    up = np.asarray(VIEWS[view]["up"], float)
    x = np.cross(up, d)
    x = x / np.linalg.norm(x)
    y = np.cross(d, x)
    return d, x, y


def _covered(m2: np.ndarray, mdep: float, tri2: np.ndarray,
             triD: np.ndarray) -> bool:
    """M101: is the 2D point m2 (view basis), sitting at depth mdep,
    hidden behind some front-facing surface? True when a front-facing
    triangle STRICTLY contains m2 and its interpolated depth lies in
    front of the point. The strictness is the whole art: shared edges
    (rim on hole, crease riding its own surface, outline boundary) are
    never "inside" either neighbour, so coincident ink keeps its class
    instead of drowning in float noise."""
    if not len(tri2):
        return False
    v0 = tri2[:, 1] - tri2[:, 0]
    v1 = tri2[:, 2] - tri2[:, 0]
    vp = m2 - tri2[:, 0]
    den = v0[:, 0] * v1[:, 1] - v0[:, 1] * v1[:, 0]
    ok = np.abs(den) > 1e-12
    one = np.where(ok, den, 1.0)
    u = (vp[:, 0] * v1[:, 1] - vp[:, 1] * v1[:, 0]) / one
    v = (v0[:, 0] * vp[:, 1] - v0[:, 1] * vp[:, 0]) / one
    # boundary-INCLUSIVE containment, and here is why it is honest: a
    # point sitting on a triangle's edge interpolates to the depth of
    # THAT EDGE — never closer than the edge being tested, so the dtol
    # below refuses self-coverage (rim on its own hole, a crease on
    # its own faces). But when some OTHER surface's boundary crosses
    # in FRONT (the classic symmetric iso case: a far edge's ray
    # grazing a near silhouette), the interpolated depth is genuinely
    # nearer and the edge hides. Strict tests missed exactly that.
    inside = ok & (u > -1e-7) & (v > -1e-7) & (u + v < 1.0 + 1e-7)
    if not inside.any():
        return False
    t0, t1, t2 = triD[inside, 0], triD[inside, 1], triD[inside, 2]
    depth = t0 + u[inside] * (t1 - t0) + v[inside] * (t2 - t0)
    return bool((depth > mdep + 1e-4).any())


def project_edges(solid, view: str = "top", eps: float = 1e-6) -> dict:
    """M101: TRUE hidden-line removal in one pass — {"visible": [...],
    "hidden": [...]} chains in the view's 2D basis (a closed chain
    repeats its start). Candidate edges come from the orientation
    rules: turn edges (one face front, the other not), sharp creases
    (two faces front, fold > 40°), and back creases (neither face
    front, at least one strictly away — grazing counts, so a pocket
    floor meeting a fleeing wall hides; the sharp fold keeps smooth
    walls — spheres, bore seams — silent). Then DEPTH decides: a
    candidate whose midpoint lies strictly UNDER a nearer front-facing
    triangle is occluded, so a visible candidate demotes to dashed
    (a bore behind an intact wall) and a back candidate standing in
    front of every surface promotes to solid (a far rim SEEN THROUGH
    an open hole — the answer the orientation-only rule could never
    give). Coincident 2D segments merge, visible winning: rims that
    repeat rims draw one line."""
    cache = getattr(solid, "_edge_cache", None)
    if cache is None:
        cache = solid._edge_cache = {}
    key = (view, eps)
    if key in cache:
        return cache[key]
    out = {"visible": [], "hidden": []}
    tm = solid.to_trimesh()
    if len(tm.faces) and len(tm.face_adjacency):
        d, X, Y = _basis(view)
        facing = tm.face_normals @ d
        dep = tm.vertices @ d
        v2 = np.stack([tm.vertices @ X, tm.vertices @ Y], axis=1)
        s = facing[tm.face_adjacency]
        a, b = s[:, 0], s[:, 1]
        n = tm.face_normals[tm.face_adjacency]
        fold = ((n[:, 0] * n[:, 1]).sum(axis=1)
                < math.cos(math.radians(40.0)))
        cand_vis = (((a > eps) & (b <= eps)) | ((b > eps) & (a <= eps))
                    | ((a > eps) & (b > eps) & fold))
        graze = 0.2
        cand_hid = ((a <= graze) & (b <= graze)
                    & ((a <= -eps) | (b <= -eps)) & fold) & ~cand_vis
        idx = np.nonzero(cand_vis | cand_hid)[0]
        if len(idx):
            fm = facing > eps
            tri2 = v2[tm.faces[fm]]
            triD = dep[tm.faces[fm]]
            # M139a: 2D spatial binning. The _covered maths is law (its
            # boundary strictness decides the class of every coincident
            # line), but interrogating every front-facing triangle about
            # every midpoint is O(E x T): the modelled M8 threads of a
            # small plate's drawing pushed one view to ~20 s (41k
            # triangles) and made the suite gate itself a coin flip. A
            # triangle can only cover a point INSIDE its 2D bbox, so
            # register each triangle with the grid cells its bbox
            # touches — a midpoint then talks to its own cell's handful.
            # Identical answers, one to two orders of magnitude cheaper.
            lo2 = tri2.min(axis=(0, 1))
            cell = max(float(np.hypot(*np.ptp(tri2, axis=(0, 1))))
                       / 32.0, 1e-9)
            glo = np.floor((tri2.min(axis=1) - lo2) / cell).astype(int)
            ghi = np.floor((tri2.max(axis=1) - lo2) / cell).astype(int)
            grid: dict = {}
            for t in range(len(tri2)):
                for gx in range(glo[t, 0], ghi[t, 0] + 1):
                    for gy in range(glo[t, 1], ghi[t, 1] + 1):
                        grid.setdefault((gx, gy), []).append(t)
            ee = tm.face_adjacency_edges[idx]
            segs = v2[ee]
            mids = segs.mean(axis=1)
            mdeps = dep[ee].mean(axis=1)
            vis: dict = {}
            hid: dict = {}
            for i in range(len(idx)):
                p, q = segs[i]
                k = tuple(sorted((tuple(np.round(p, 6)),
                                  tuple(np.round(q, 6)))))
                if k in vis:
                    continue                       # one visible copy is ink
                cc = tuple(np.floor((mids[i] - lo2) / cell).astype(int))
                cand = grid.get(cc)                # bbox law: a triangle
                if cand is None:                   #  outside this cell
                    hit = False                    #  cannot cover it
                else:
                    sel = np.fromiter(cand, int)
                    hit = _covered(mids[i], float(mdeps[i]),
                                   tri2[sel], triD[sel])
                if hit:
                    hid.setdefault(k, (p, q))      # occluded: dashed
                else:
                    # In front of every surface: solid ink — this is how
                    # a far rim seen THROUGH an open hole (or a back edge
                    # riding the silhouette boundary) is drawn honestly.
                    vis[k] = (p, q)
                    hid.pop(k, None)
            out = {
                "visible": [[(float(x), float(y)) for x, y in c]
                            for c in _chain(np.array(list(vis.values())))]
                if vis else [],
                "hidden": [[(float(x), float(y)) for x, y in c]
                           for c in _chain(np.array(list(hid.values())))]
                if hid else [],
            }
    cache[key] = out
    return out


def project_view(solid, view: str = "top", eps: float = 1e-6) -> list:
    """Visible-line chains of a Solid along a named view (M101: the
    occluded ones now live in project_hidden)."""
    return project_edges(solid, view, eps)["visible"]


def _merge_collinear(pts: list) -> list:
    out = [pts[0]]
    for p in pts[1:]:
        if len(out) >= 2:
            p0, p1 = out[-2], out[-1]
            d1 = p1 - p0
            d2 = p - p1
            cr = abs(d1[0] * d2[1] - d1[1] * d2[0])
            sc = np.linalg.norm(d1) * np.linalg.norm(d2) + 1e-12
            if cr / sc < 1e-6 and not np.allclose(p, out[0]):
                out[-1] = p                       # p1 was a crumb
                continue
        out.append(p)
    return out


def _chain(segs) -> list:
    """Weld segment ends, walk unused edges into chains, merge crumbs."""
    if len(segs) == 0:
        return []
    def key(p):
        return (round(float(p[0]), 6), round(float(p[1]), 6))
    adj: dict = {}
    for i, (p, q) in enumerate(segs):
        ka, kb = key(p), key(q)
        if ka == kb:
            continue
        adj.setdefault(ka, []).append([kb, i])
        adj.setdefault(kb, []).append([ka, i])
    used = set()
    chains: list = []
    for node in list(adj):
        for nxt, ei in adj[node]:
            if ei in used:
                continue
            used.add(ei)
            chain = [node, nxt]                   # tuple keys all the walk
            cur, guard = nxt, 0
            while True:
                guard += 1
                if guard > 100000:
                    break
                step = None
                for cand, e2 in adj.get(cur, []):
                    if e2 not in used:
                        step = (cand, e2)
                        break
                if step is None:
                    break
                cand, e2 = step
                used.add(e2)
                chain.append(cand)
                cur = cand
                if cur == chain[0] or cur == chain[1]:
                    break            # closed loop, or ping-pong guard
            if len(chain) >= 2:
                chains.append(_merge_collinear(
                    [np.array(p, float) for p in chain]))
    return chains


def fit_scale(views: dict, page: str = "A3", margin: float = 10.0) -> float:
    """One scale for every view so the STANDARD layout fits the sheet
    with margins. The layout packs two view columns and two rows, so
    each view gets half the sheet; 1.0 caps at full size."""
    W, H = sheet_size(page)
    pts = [p for chains in views.values() for c in chains for p in c]
    if not pts:
        return 1.0
    P = np.asarray(pts)
    w = float(P[:, 0].max() - P[:, 0].min())
    h = float(P[:, 1].max() - P[:, 1].min())
    return float(min((W - 2 * margin) / 2.2 / max(w, 1e-9),
                     (H - 2 * margin) / 2.2 / max(h, 1e-9), 1.0))


SLOTS = {"top": (0.28, 0.72), "iso": (0.72, 0.72),
         "front": (0.28, 0.28), "right": (0.72, 0.28)}


def project_hidden(solid, view: str = "top", eps: float = 1e-6,
                   visible: list | None = None) -> list:
    """M97/M101: the dashed chains — candidate edges the DEPTH test
    occludes behind nearer front surface (see project_edges). The
    `visible` argument is a compatibility shim for older callers; the
    unified pass no longer needs it."""
    return project_edges(solid, view, eps)["hidden"]


def _poly_self_intersects(pts) -> bool:
    """True when a closed polyline crosses itself (non-adjacent edges
    meet). A breakout profile must bound a simple region: the page draws
    a closed loop the material is removed within, and a figure-eight has
    no honest inside to cut."""
    P = np.asarray(pts, float)
    n = len(P)
    if n < 3:
        return False                       # caller's <3 check owns that
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue                   # skip shared-endpoint edges
            c, d = P[j], P[(j + 1) % n]
            r = b - a
            s = d - c
            denom = r[0] * s[1] - r[1] * s[0]
            if abs(denom) < 1e-12:
                continue                   # parallel (collinear overlap
            t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / denom
            u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / denom
            if 1e-9 < t < 1 - 1e-9 and 1e-9 < u < 1 - 1e-9:
                return True
    return False


_breakout_cache: dict = {}      # M201 R37: a breakout is TWO solid ops
#   (the column probe and the cut) and _sources() re-derives on every
#   repaint - the _section_on_cache precedent, same identity law: a hit
#   counts only while the SAME Solid object answers, so a recompute
#   (which mints a new one) misses and the cut follows the model live.


def breakout_solid(solid, view, loop, depth=None):
    """M201 R37 [Create breakout section views] a breakout section "is
    part of an existing drawing view, that is used to remove material to
    a specified depth in order to expose inner details of a design";
    [verbatim] "A closed profile defines the breakout section" and "The
    depth is set to half of your design's depth by default, but you can
    type in any depth value."  So the cut lives in 3D, never on paper:
    extrude the CLOSED PROFILE loop (drawn in the parent's own model-page
    (u,v) coords, the same dot-with-(X,Y) convention hole_marks and every
    chain speak) into a prism and SUBTRACT it from the parent solid. The
    prism rides the parent view's (d, X, Y) triple - identical to the
    detail cookie, so an iso parent cuts as honestly as an axis-aligned
    one - but where the cookie INTERSECTS (keep the crop) the breakout
    SUBTRACTS (remove the slab) and it sinks to a DEPTH instead of
    swallowing all sight-depth. depth=None means the page's own default,
    half the design's extent along the sight, measured from the FRONT of
    the design [reference dialog: "move the start point to the front of
    the design for depth calculation"]. Returns (solid, info) where info
    carries the RESOLVED depth and the floor plane's sight-depth so the
    caller stores them (deviations only) and the film prints a measured
    number; a solid that touches no material under the loop is HONEST
    (nothing removed) - the caller shows the uncut parent, never a lie."""
    from .geometry import Solid
    P = np.asarray(loop, float)
    if P.shape[0] < 3:
        raise ValueError("a breakout profile needs at least three points")
    if _poly_self_intersects(P):
        raise ValueError("the breakout profile crosses itself - draw a "
                         "simple closed loop")
    d, X, Y = _basis(view)
    vkey = view if isinstance(view, str) else tuple(
        tuple(np.round(np.asarray(a, float), 9)) for a in (d, X, Y))
    key = (vkey, tuple(np.round(P.ravel(), 9)),
           None if depth is None else round(float(depth), 9))
    hit = _breakout_cache.get(key)
    if hit is not None and hit[0] is solid:
        return hit[1], hit[2]
    # The page measures depth "from the front of the design" UNDER the
    # profile, not off a far bounding-box corner - so for an iso parent the
    # near surface that matters is the material actually inside the loop's
    # sight-column, which we find by intersecting with an infinite prism.
    lo, hi = np.asarray(solid.bounding_box, float)
    corners = np.array([[a, b, c] for a in (lo[0], hi[0])
                        for b in (lo[1], hi[1]) for c in (lo[2], hi[2])])
    sd = corners @ d
    L = float(sd.max() - sd.min())                 # design sight-extent
    if L <= 0.0:
        raise ValueError("the parent has no depth to break out along")

    def prism(z0, h):
        m = np.eye(4)
        m[:3, :3] = np.column_stack([X, Y, d])     # +z -> toward the eye
        m[:3, 3] = z0 * d                          # local (u,v) ride X,Y
        return Solid.extrude(P, height=h).transformed(m)

    column = solid.intersect(prism(sd.min() - L, 3.0 * L))   # the sight-column
    if column.volume <= 1e-6:
        # a profile on bare paper cuts nothing - honest, paint the uncut
        # parent; the REFUSALS still speak (a refusal that depends on
        # where material happens to sit is not a refusal).
        dep = float(depth) if depth is not None else 0.5 * L
        if depth is not None:
            if dep <= 0.0:
                raise ValueError("breakout depth must be positive")
            if dep >= L:
                raise ValueError("a breakout depth of the whole design "
                                 "is a section, not a breakout - choose "
                                 "a shallower cut")
        info = {"depth_used": dep, "floor": float(sd.max()) - dep,
                "front": float(sd.max()), "default": depth is None}
        if len(_breakout_cache) > 128:
            _breakout_cache.clear()
        _breakout_cache[key] = (solid, solid, info)
        return solid, info
    # THE column's own vertices, not its world AABB: an iso column is a
    # rotated wedge whose bounding box reaches sight-depth far BEYOND any
    # real material, and sinking from that phantom front shaves nothing.
    tm = column.to_trimesh()
    csd = np.asarray(tm.vertices, float) @ d
    front, cbottom = float(csd.max()), float(csd.min())
    extent = front - cbottom                       # the column's own depth
    dep = float(depth) if depth is not None else 0.5 * extent
    if dep <= 0.0:
        raise ValueError("breakout depth must be positive")
    if dep >= extent:
        raise ValueError("a breakout depth of the whole design is a "
                         "section, not a breakout - choose a shallower cut")
    cut = solid.subtract(prism(front - dep, dep + L))   # sink dep from front
    info = {"depth_used": dep, "floor": front - dep, "front": front,
            "default": depth is None}
    if len(_breakout_cache) > 128:
        _breakout_cache.clear()
    _breakout_cache[key] = (solid, cut, info)
    return cut, info


def detail_cookie(solid, view, centre, radius: float):
    """M201 R36 [Create a detail view, verbatim] "Click a point on
    the parent view to place the center point of the detail boundary"
    / "Drag the cursor away from the center point to adjust the size
    of the detail boundary" - the boundary is INTERACTIVE (the page
    prints no radius field, no circle-word), so the honest clip lives
    in 3D, not on paper: intersect the solid with a cylinder whose
    AXIS is the parent view's sight line through the boundary centre.
    `centre` is parent-view coordinates (the same (dot(c,X), dot(c,Y))
    convention hole_marks and every chain already speak); the view's
    own orthonormal (X, Y, d) triple is the column basis that turns
    the +z cylinder toward the sight - so an ISO parent clips exactly
    as well as an axis-aligned one (R34's lesson: grow the honest
    hop, refuse the dishonest one - and this hop is honest for every
    parent the projection pipeline can name).
    The 2000 mm depth is the section slab's own working number: parts
    are far smaller; the cookie must swallow all sight-depth, or the
    crop would show a lid. An empty cookie is HONEST (a boundary on
    bare paper clips nothing) - the caller paints nothing, never a
    lie."""
    from .geometry import Solid
    r = float(radius)
    if r <= 0.0:
        raise ValueError("detail boundary needs a positive radius")
    d, X, Y = _basis(view)
    u, v = float(centre[0]), float(centre[1])
    p0 = u * X + v * Y                       # any depth on the axis
    m4 = np.eye(4)
    m4[:3, :3] = np.column_stack([X, Y, d])  # maps +z -> sight
    m4[:3, 3] = p0 - 1000.0 * d
    return solid.intersect(
        Solid.cylinder(r, 2000.0).transformed(m4))


def fit_circle(chain):
    """M95: ((cx, cy), r) when a projected closed chain is (near) a
    circle — a face-on circular edge under an orthographic view:
    closed, square-ish bbox, uniform radius. Iso ellipses, rectangles
    and open chains honestly refuse."""
    P = np.asarray(chain, float)
    if P.shape[0] < 5 or not np.allclose(P[0], P[-1], atol=1e-6):
        return None
    lo, hi = P.min(axis=0), P.max(axis=0)
    w, h = hi[0] - lo[0], hi[1] - lo[1]
    if w <= 1e-9 or h <= 1e-9 or not 0.85 <= w / h <= 1.18:
        return None
    c = 0.5 * (lo + hi)
    rr = np.linalg.norm(P - c, axis=1)
    r = float(rr.mean())
    if r <= 1e-9 or float(np.abs(rr - r).max()) > 0.10 * r:
        return None
    return (float(c[0]), float(c[1])), r


def _kasa(Q):
    """Algebraic circle fit (Kåsa): solves D x + E y + F = -(x^2+y^2).
    Returns (cx, cy, r) or None when the system lies (collinear)."""
    A = np.column_stack([Q[:, 0], Q[:, 1], np.ones(len(Q))])
    b = -(Q ** 2).sum(axis=1)
    try:
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    D, E, F = (float(x) for x in sol)
    cx, cy = -D / 2.0, -E / 2.0
    rr = cx * cx + cy * cy - F
    if rr <= 0.0:
        return None
    return cx, cy, math.sqrt(rr)


def _circ3(a, b, c):
    """Circumcircle of three points; None when (nearly) collinear.
    Computed against A as origin: the absolute-coordinate form cancels
    catastrophically when the triple is tight and far from (0,0) —
    exactly the mesh case here (points 0.5 apart at radius 40) — and
    returns a spurious million-mm circle."""
    ax, ay = a
    bx, by = b[0] - ax, b[1] - ay
    cx, cy = c[0] - ax, c[1] - ay
    d = 2.0 * (bx * cy - by * cx)
    if abs(d) < 1e-9:
        return None
    bb, cc = bx * bx + by * by, cx * cx + cy * cy
    ux = (cy * bb - by * cc) / d
    uy = (bx * cc - cx * bb) / d
    return (ax + ux, ay + uy), math.hypot(ux, uy)


def find_arcs(chains: list) -> list:
    """M103: circular arcs BURIED IN silhouette chains — a scallop on
    an edge, a rounded corner, a boss breaking through a wall. Arcs
    never ride alone (chains trace whole boundary loops, and
    _merge_collinear leaves a straight run as ONE segment), so an arc
    is cut out by CURVATURE: a vertex turns by 1..60 degrees, the same
    way as its neighbours — a 64-gon wall turns 5.6 degrees per step,
    while true corners (90 deg) and tangent junctions (0 deg) break
    the run. Maximal same-signed runs get a circle by VOTE — three
    vantage triples (head, middle, tail of the run) each propose a
    circumcircle, the proposal with the most inliers wins, and Kåsa
    polishes the inlier set — because a run's last chord often already
    points down the straight that follows, and a least-squares fit
    without that outlier's pull lies prettier than it should. What
    still lies is refused:
    residuals past 10% of r, spans under 25 degrees or over 330
    (a whole ring is fit_circle's territory — and a closed chain whose
    run spans nearly the entire ring IS that ring), radii absurdly
    beyond the run's own extent (collinear dust). Deduped, because a
    circle split by a tangent vertex fits to itself twice.
    Returns [((cx, cy), r), ...] in the chains' own 2D basis."""
    found: list = []
    seen: set = set()
    for L in chains:
        P = np.asarray(L, float)
        if P.shape[0] < 6:
            continue
        closed = bool(np.allclose(P[0], P[-1], atol=1e-6))
        if closed:
            P = P[:-1]
        dd = np.hypot(*(np.diff(P, axis=0)).T)
        if not (dd > 1e-9).all():                 # weld repeated tips
            P = np.vstack([P[:-1][np.r_[dd[:-1], True] > 1e-9], P[-1:]])
        n = len(P)
        if n < 6:
            continue
        e = np.diff(P, axis=0)
        e = e / np.hypot(e[:, 0], e[:, 1])[:, None]
        T = np.zeros(n)
        cross = e[:-1, 0] * e[1:, 1] - e[:-1, 1] * e[1:, 0]
        dot = (e[:-1] * e[1:]).sum(axis=1)
        T[1:n - 1] = np.degrees(np.arctan2(cross, dot))
        if closed:                                 # the ring's closing edge
            w = P[0] - P[-1]
            w = w / math.hypot(w[0], w[1])
            T[0] = math.degrees(math.atan2(
                w[0] * e[0, 1] - w[1] * e[0, 0], float(w @ e[0])))
            T[n - 1] = math.degrees(math.atan2(
                e[-1, 0] * w[1] - e[-1, 1] * w[0], float(e[-1] @ w)))
            big = np.nonzero(np.abs(T) > 60.0)[0]
            if len(big):
                # open the ring AT a corner, never through an arc
                cut = int(big[np.abs(T[big]).argmax()])
                P, T = np.roll(P, -cut, axis=0), np.roll(T, -cut)
            elif len(np.nonzero(np.abs(T) < 1.0)[0]) == 0:
                continue          # a pure polygon ring: fit_circle's job
            T[0] = T[n - 1] = 0.0                  # linear ends break runs
        band = (np.abs(T) >= 1.0) & (np.abs(T) <= 60.0)
        sgn = np.sign(T)
        i = 1
        while i <= n - 2:
            if not band[i]:
                i += 1
                continue
            j = i
            while (j + 1 <= n - 2 and band[j + 1]
                   and sgn[j + 1] == sgn[j]):
                j += 1
            Q = P[i:j + 2]
            i = j + 1
            if len(Q) < 5:
                continue
            m = len(Q)
            diag = float(np.hypot(*(Q.max(axis=0) - Q.min(axis=0))))
            best = None
            for trip in ((0, 1, 2), (m // 2 - 1, m // 2, m // 2 + 1),
                         (m - 3, m - 2, m - 1)):  # three vantage triples
                c3 = _circ3(Q[trip[0]], Q[trip[1]], Q[trip[2]])
                if c3 is None:
                    continue
                (ux, uy), rr = c3
                if rr <= 1e-9 or rr > 25.0 * max(diag, 1e-9):
                    continue
                inl = np.abs(np.linalg.norm(Q - [ux, uy], axis=1)
                             - rr) <= 0.10 * rr
                if best is None or int(inl.sum()) > int(best.sum()):
                    best = inl
            if best is None or int(best.sum()) < 5 \
                    or int(best.sum()) * 2 < m:    # mostly junk
                continue
            Qi = Q[best]
            f = _kasa(Qi)                          # polish on the inliers
            if f is None:
                continue
            cx, cy, r = f
            if float(np.abs(np.linalg.norm(Qi - [cx, cy], axis=1)
                            - r).max()) > 0.10 * r:
                continue
            if r > 25.0 * max(diag, 1e-9):
                continue                           # dust fits a lie
            ang = np.unwrap(np.arctan2(Qi[:, 1] - cy, Qi[:, 0] - cx))
            span = math.degrees(abs(float(ang[-1] - ang[0])))
            if not 25.0 <= span <= 330.0:
                continue
            k = (round(cx, 3), round(cy, 3), round(r, 3))
            if k in seen:
                continue
            seen.add(k)
            found.append(((cx, cy), r))
    return found


def parse_scale(text: str):
    """M100: the Scale dialog's wording → a factor. "Fit (auto)"
    (anything starting with fit) means the layout assistant decides
    (None); "1:2" is 0.5, "2:1" is 2, and a bare number is itself.
    Garbage raises with the draughtsman's examples."""
    t = str(text).strip().lower()
    if not t or t.startswith("fit"):
        return None
    if ":" in t:
        try:
            a, b = t.split(":", 1)
            a, b = float(a), float(b)
        except ValueError:
            raise ValueError(f"scale {text!r} is not a ratio")
        if b == 0:
            raise ValueError("scale ratios need a non-zero second term")
        return a / b
    try:
        f = float(t)
    except ValueError:
        raise ValueError(f"scale {text!r} — try Fit, 1:2, 2:1 or 0.5")
    if f <= 0:
        raise ValueError("scales are positive")
    return f


# --------------------------------------------------------------------- M102
# Sections: cut the body open, keep the half BEHIND the plane, and the
# viewer reads the result in the standard view that looks AT that face.

SECTION_VIEWS = {"X": "right", "Y": "front", "Z": "top"}
# which side survives: material between the viewer and the plane is
# discarded — so for each axis, exactly one inequality keeps matter:
_SECTION_KEEP = {"X": -1, "Y": +1, "Z": -1}
_section_cache: dict = {}


def section(solid, axis: str = "Y", at: float = 0.0) -> dict:
    """M102: {"half": Solid beyond the plane (the kept side), "view":
    the standard view that reads it, "cut": closed loops of the cut
    face in that view's 2D basis}. The loops come from slicing the
    ORIGINAL solid — the plane crosses material there, and the M82
    lesson applies: jitter off coplanar degeneracy if a cut grazes a
    feature boundary. Booleans and slices are exact per (solid, axis,
    at): the immutable Solid caches the whole result, so repaints are
    free until the model changes."""
    key = (id(solid), axis, round(float(at), 9))
    hit = _section_cache.get(key)
    if hit is not None and hit[0] is solid:
        return hit[1]
    from .geometry import Solid
    i = "XYZ".index(axis)
    view = SECTION_VIEWS[axis]
    sgn = _SECTION_KEEP[axis]
    bb = np.asarray(solid.bounding_box, float)
    lo, hi = bb[0], bb[1]
    pad = 100.0
    box_lo = [lo[k] - pad for k in range(3)]
    box_hi = [hi[k] + pad for k in range(3)]
    if sgn > 0:                       # keep coord >= at (viewer side dies)
        box_lo[i] = float(at)
    else:                             # keep coord <= at
        box_hi[i] = float(at)
    M = np.eye(4)
    M[:3, 3] = box_lo
    halfspace = Solid.box(*[box_hi[k] - box_lo[k] for k in range(3)])
    half = solid.intersect(halfspace.transformed(M))
    tm = solid.to_trimesh()
    nrm = np.zeros(3)
    nrm[i] = 1.0
    X, Y = _basis(view)[1], _basis(view)[2]
    loops = _cut_loops(tm, nrm * at, nrm, X, Y)
    res = {"half": half, "view": view, "cut": loops}
    if len(_section_cache) > 64:
        _section_cache.clear()
    _section_cache[key] = (solid, res)
    return res


def _cut_loops(tm, o, n, X, Y) -> list:
    """Closed cut-face loops in the (X, Y) page basis, M102's honest
    recipe: try the exact plane, then jitter off coplanar degeneracy
    if the cut grazes a feature boundary; weld crumbs, close rings."""
    loops: list = []
    for off in (0.0, 1e-3, -1e-3):
        try:
            sec = tm.section(plane_origin=np.asarray(o, float)
                             + np.asarray(n, float) * off,
                             plane_normal=np.asarray(n, float))
        except Exception:
            continue
        if sec is None or not len(sec.discrete):
            continue
        for pl in sec.discrete:
            P = np.asarray(pl, float)
            xy = np.column_stack([P @ X, P @ Y])
            step = np.hypot(*(xy[1:] - xy[:-1]).T)
            xy = xy[np.r_[True, step > 1e-9]]          # weld crumbs
            if len(xy) > 3 and math.hypot(*(xy[0] - xy[-1])) < 1e-9:
                xy = xy[:-1]                           # closed: no repeat
            if len(xy) >= 3:
                loops.append([(float(x), float(y)) for x, y in xy])
        if loops:
            break
    return loops


def section_letter(n: int) -> str:
    """M136: the letter for the n-th section on a sheet. The
    drafting-alphabet law (Onshape spells it out [official]): I, O,
    Q, S, X and Z are reserved by the standards and never label a
    section — past the twenty usable letters the label doubles up
    (AA, BB) rather than repeat a single one. Both section makers
    (the M102 dialog and the M136 line) letter from here, so one
    registry, one alphabet, no collision. M144: datums read the
    SAME RESERVED_LETTERS object — one family, two users."""
    alphabet = [c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                if c not in RESERVED_LETTERS]
    if n < len(alphabet):
        return alphabet[n]
    return alphabet[n % len(alphabet)] * 2        # double up past 20


def plane_from_line(parent: str, p0, p1, flip: bool = False):
    """M136: the section plane a LINE ON A PARENT VIEW defines — the
    drafting rule: the plane contains the drawn line and stands
    perpendicular to the parent's projection plane. p0/p1 are points
    in the parent view's MODEL coordinates (page coords un-scaled and
    un-offset by the caller). Returns (origin, keep-normal, right):
    the keep-normal points at the EYE (the arrows' side; that half is
    what the section view looks at), RIGHT runs along the line and
    becomes the child's page-x. Default arrow: 90° CW of the drag —
    drag left→right across a TOP view and the arrow drops toward the
    FRONT, exactly the classic front-section; flip negates.
    Orthogonal parents only (top/front/right): an iso parent's page
    axes tilt depth into the line and the plane stops being a
    section-plane (v1 scope, banked in the queue doc)."""
    if parent not in ("top", "front", "right"):
        raise ValueError(f"section line needs an orthogonal parent "
                         f"view, not {parent!r}")
    _, X, Y = _basis(parent)
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    u2 = p1 - p0
    L = float(np.linalg.norm(u2))
    if L < 1e-9:
        raise ValueError("section line needs two distinct points")
    u2 = u2 / L
    dl3 = u2[0] * X + u2[1] * Y                 # along the line
    a2 = np.array([u2[1], -u2[0]])              # 90 deg CW in page
    if flip:
        a2 = -a2
    a3 = a2[0] * X + a2[1] * Y                  # unit: X,Y orthonormal
    o3 = p0[0] * X + p0[1] * Y                  # depth-0 point on plane
    return o3, a3, dl3


_section_on_cache: dict = {}


def section_on(solid, o, n, right=None, mode: str = "full",
               dist: float | None = None) -> dict:
    """M136: the arbitrary-plane sibling of section() — same shape
    ({"half", "view", "cut"}) but the plane is (origin o, keep-normal
    n pointing at the eye), and the child's view key is a BASIS
    TUPLE (eye, page-x, page-y) that _basis passes through, so
    project_view/hidden/HLR/place/paint/export all take a slanted
    section exactly like a named one. RIGHT (defaults to any
    perpendicular) lays the cut line flat on the child's page.
    M137 depth modes (the vendor's triad): FULL keeps the half the
    normal points into; DISTANCE keeps a slab of `dist` from the
    plane (the material near the wound, nothing deeper); SLICE
    shows the cut face ALONE — half=None, the cap loops are the
    whole view."""
    o = np.asarray(o, float)
    n = np.asarray(n, float) / max(float(np.linalg.norm(n)), 1e-12)
    if right is None:
        ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else \
            np.array([0.0, 1.0, 0.0])
        right = np.cross(ref, n)
    X = np.asarray(right, float)
    X = X - n * float(X @ n)
    X = X / max(float(np.linalg.norm(X)), 1e-12)
    Y = np.cross(n, X)                          # right-handed page
    mode = str(mode or "full").lower()
    dd = float(dist) if dist is not None else 0.0
    key = (id(solid), tuple(np.round(o, 9)), tuple(np.round(n, 9)),
           tuple(np.round(X, 9)), mode, round(dd, 9))
    hit = _section_on_cache.get(key)
    if hit is not None and hit[0] is solid:
        return hit[1]
    from .geometry import Solid
    bb = np.asarray(solid.bounding_box, float)
    L = float(np.linalg.norm(bb[1] - bb[0])) + 100.0
    # prism: a big square in the plane extruded from the plane into
    # the KEPT half-space — local +z rides n, so intersect keeps
    # {p : (p - o) . n >= 0}, the eye side (slice_plane's rule and
    # the draughtsman's: the near half is what you look at).
    # M137: FULL extrudes past any part; DISTANCE stops at `dist`.
    depth = L if mode != "distance" else max(dd, 1e-4)
    half = None                                 # SLICE: the cut IS all
    if mode != "slice":
        box = Solid.box(2 * L, 2 * L, depth)    # corner at local 000
        M = np.eye(4)
        M[:3, :3] = np.column_stack([X, Y, n])
        M[:3, 3] = o - (X + Y) * L              # centre square on o
        half = solid.intersect(box.transformed(M))
    tm = solid.to_trimesh()
    loops = _cut_loops(tm, o, n, X, Y)
    res = {"half": half, "view": (tuple(n), tuple(X), tuple(Y)),
           "cut": loops, "mode": mode}
    if len(_section_on_cache) > 64:
        _section_cache.clear()
        _section_on_cache.clear()
    _section_on_cache[key] = (solid, res)
    return res


def plane_from_polyline(parent: str, pts, flip: bool = False):
    """M138: the generalization of plane_from_line — a cutting
    POLYLINE whose bends are right angles, the only jogged family
    the standards admit (every drafting product enforces the square
    turn BY CONSTRUCTION). Returns (segs, basis): one SEG per
    maximal straight cut-run {"o","lo","hi"} — its plane through the
    run, lateral ownership lo..hi along the main direction (None =
    open toward the polyline end; hinge segments hand their shared
    d-coordinate to the neighbour runs) — and a single shared BASIS
    tuple (eye, page-x, page-y). The rotation the 'drawn as if the
    offsets were in one plane' law implies is the IDENTITY for this
    family: every cut plane is perpendicular to the parent and the
    orthographic child along the shared eye flattens the steps for
    free (live-verified on the stack, banked in the queue doc).
    Non-square bends raise — that is the angular/aligned rung,
    which does need the hinge rotation, and its open-source oracle
    still stitches by approximation."""
    if parent not in ("top", "front", "right"):
        raise ValueError(f"section line needs an orthogonal parent "
                         f"view, not {parent!r}")
    _, X, Y = _basis(parent)
    P = [np.asarray(p, float) for p in pts]
    d2 = None
    segs2 = []
    for i in range(len(P) - 1):
        v = P[i + 1] - P[i]
        L = float(np.linalg.norm(v))
        if L < 1e-9:
            continue                            # click noise
        u = v / L
        if d2 is None:
            d2 = u
        segs2.append((P[i], P[i + 1], u))
    if d2 is None or not segs2:
        raise ValueError("section line needs two distinct points")
    n2 = np.array([d2[1], -d2[0]])              # 90 deg CW: the eye
    if flip:
        n2 = -n2
    runs: list = []                             # cut-runs, left to right
    for (p0, p1, u) in segs2:
        a2 = abs(float(u @ d2))
        if a2 < 0.001:                          # square: a hinge
            if not runs or runs[-1]["hi"] is not None:
                raise ValueError("a jog must connect two cuts")
            runs[-1]["hi"] = float(p0 @ d2)
            continue
        if a2 < 0.999:
            raise ValueError("jogs must turn square: bend the "
                             "cutting line at right angles only")
        if runs and runs[-1]["hi"] is None:     # extend the open run
            off0 = float(runs[-1]["p1"] @ n2)
            if abs(float(p1 @ n2) - off0) > 1e-6:
                raise ValueError("two cuts in a row must stay on "
                                 "one line")
            runs[-1]["p1"] = p1
            continue
        if runs:
            prev_hi = runs[-1]["hi"]
            if float(p0 @ d2) < prev_hi - 1e-9 or \
                    float(p1 @ d2) < prev_hi - 1e-9:
                raise ValueError("jogged cuts must ADVANCE along "
                                 "the line — no doubling back")
        runs.append({"p0": p0, "p1": p1, "hi": None})
    if runs[-1]["hi"] is not None:
        raise ValueError("a cutting polyline must END on a cut, "
                         "not on a jog")
    d3 = d2[0] * X + d2[1] * Y
    n3 = n2[0] * X + n2[1] * Y
    y3 = np.cross(n3, d3)                       # child page-y
    basis = (tuple(n3), tuple(d3), tuple(y3))
    segs = []
    for i, r in enumerate(runs):
        segs.append({"o": r["p0"][0] * X + r["p0"][1] * Y,
                     "lo": None if i == 0 else runs[i - 1]["hi"],
                     "hi": r["hi"]})
    return segs, basis


_jog_cache: dict = {}


def section_jogged(solid, segs, basis, mode: str = "full",
                   dist: float | None = None) -> dict:
    """M138: the jogged child, assembled the way the standards read
    it: cut each run's OWN plane inside its lateral slab (the slabs
    are disjoint — no material is asked of two planes at once) and
    CONCATENATE the cap loops (a single plane-section of the joined
    halves would trace wrong loops where the steps land; the hatch
    and the page do not care which plane a loop was cut on). The
    kept halves union into ONE projectable solid, so every existing
    consumer — HLR, hidden ink, place, hatch, DXF, PNG — receives
    the jogged child exactly like a straight one. Depth modes ride
    per run (the slab's named depth is the same at every step)."""
    mode = str(mode or "full").lower()
    dd = float(dist) if dist is not None else 0.0
    key = (id(solid), mode, round(dd, 9),
           tuple((tuple(np.round(s["o"], 6)), s["lo"], s["hi"])
                 for s in segs))
    hit = _jog_cache.get(key)
    if hit is not None and hit[0] is solid:
        return hit[1]
    from .geometry import Solid
    n3 = np.asarray(basis[0], float)
    d3 = np.asarray(basis[1], float)
    y3 = np.asarray(basis[2], float)
    bb = np.asarray(solid.bounding_box, float)
    L = float(np.linalg.norm(bb[1] - bb[0])) + 100.0
    halves, cuts = [], []
    for s in segs:
        o = np.asarray(s["o"], float)
        base = float(o @ d3)
        lo = base - L if s["lo"] is None else float(s["lo"])
        hi = base + L if s["hi"] is None else float(s["hi"])
        if hi <= lo:
            continue
        M = np.eye(4)
        M[:3, :3] = np.column_stack([d3, n3, y3])
        M[:3, 3] = d3 * lo - n3 * L - y3 * L   # lo/hi are ABSOLUTE
        clip = solid.intersect(                # d coords — anchor
            Solid.box(hi - lo, 2 * L, 2 * L).transformed(M))
        sec = section_on(clip, o, n3, right=d3, mode=mode, dist=dd)
        if sec["half"] is not None:
            halves.append(sec["half"])
        cuts.extend(sec["cut"])
    half = None
    for h in halves:
        half = h if half is None else half.union(h)
    res = {"half": half, "view": tuple(basis), "cut": cuts,
           "mode": mode}
    if len(_jog_cache) > 24:
        _jog_cache.clear()
    _jog_cache[key] = (solid, res)
    return res


def _sweep_hatch(region, spacing: float) -> list:
    """Shared 45° sweep: the family x - y = c across a shapely region."""
    from shapely.geometry import LineString
    minx, miny, maxx, maxy = region.bounds
    step = spacing * math.sqrt(2.0)     # perpendicular spacing
    out: list = []
    c = minx - maxy - step              # x - y ranges over the bounds:
    while c <= maxx - miny + step:      # [minx-maxy, maxx-miny]
        cut = region.intersection(LineString([(minx - 1.0, minx - 1.0 - c),
                                              (maxx + 1.0, maxx + 1.0 - c)]))
        if not cut.is_empty:
            for g in getattr(cut, "geoms", [cut]):
                if g.geom_type != "LineString" or g.length < 1e-9:
                    continue
                cs = list(g.coords)
                out.append(((float(cs[0][0]), float(cs[0][1])),
                            (float(cs[-1][0]), float(cs[-1][1]))))
        c += step
    return out


def hatch_lines(loop, spacing: float = 3.5) -> list:
    """M102: the draughtsman's 45° section hatch, clipped to a closed
    2D loop (shapely does the honest clipping; multi-piece crossings
    become multiple segments)."""
    from shapely.geometry import Polygon
    P = Polygon(np.asarray(loop, float))
    if not P.is_valid:
        P = P.buffer(0)
    if P.is_empty or P.area <= 1e-9:
        return []
    return _sweep_hatch(P, spacing)


def hatch_region(loops, spacing: float = 3.5) -> list:
    """M102: hatch a WHOLE cut face at once — loops whose representative
    point sits inside a bigger loop are HOLES (the pocket is air, and
    air gets no hatching), subtracted before the sweep. This is what
    the sheet paints and the DXF writes; hatch_lines stays for a
    single ring."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = []
    for L in loops:
        P = Polygon(np.asarray(L, float))
        if not P.is_valid:
            P = P.buffer(0)
        if not P.is_empty and P.area > 1e-9:
            polys.append(P)
    if not polys:
        return []
    outers: list = []
    holes: list = []
    for i, p in enumerate(polys):
        rp = p.representative_point()
        if any(j != i and q.area > p.area and q.contains(rp)
               for j, q in enumerate(polys)):
            holes.append(p)
        else:
            outers.append(p)
    region = unary_union(outers)
    if holes:
        region = region.difference(unary_union(holes))
    if region.is_empty or region.area <= 1e-9:
        return []
    return _sweep_hatch(region, spacing)


def place(views: dict, page: str = "A3", margin: float = 10.0,
          moves: dict | None = None,
          scales: dict | None = None) -> dict:
    """M94: the placement math the sheet and the dim tool share.
    Scale every view once and centre it in its slot; return per view
    {\"sc\", \"off\", \"min\", \"max\", \"chains\"} where a model point
    (x, y) lands at page = (x, y) * sc + off — so the canvas can
    inverse-map a click back to model space (page_to_model), and page
    coords stay y-up, origin at the sheet's lower-left. M96: `moves`
    ({view: [dx, dy]} sheet mm) rides on top of the assistant's slots —
    the draughtsman's nudge, stored per view on the drawing.

        top   | iso
        ------+------
        front | right
    """
    base = fit_scale(views, page, margin)
    W, H = sheet_size(page)
    # M102: a sheet can carry more views than the standard four (sections
    # are named A-A, B-B...). The layout assistant parks them in the
    # middle band, staggered, and the draughtsman's drag has the rest.
    EXTRA = [(0.5, 0.5), (0.5, 0.64), (0.5, 0.36),
             (0.30, 0.5), (0.70, 0.5)]
    extra_i = 0
    out: dict = {}
    for name, chains in views.items():
        if not chains:
            continue
        sc = float((scales or {}).get(name) or base)   # M100 override
        P = np.vstack([np.asarray(c, float) * sc for c in chains])
        lo = P.min(axis=0)
        hi = P.max(axis=0)
        cx = 0.5 * (hi[0] + lo[0])
        cy = 0.5 * (hi[1] + lo[1])
        if name in SLOTS:
            fx, fy = SLOTS[name]
        else:
            fx, fy = EXTRA[min(extra_i, len(EXTRA) - 1)]
            extra_i += 1
        mx, my = (moves or {}).get(name, (0.0, 0.0))
        off = (fx * W - cx + mx, fy * H - cy + my)
        out[name] = {"sc": float(sc), "off": (float(off[0]),
                                              float(off[1])),
                     "min": (float(lo[0]), float(lo[1])),
                     "max": (float(hi[0]), float(hi[1])),
                     "chains": [[(float(p[0] + off[0]),
                                  float(p[1] + off[1]))
                                 for p in np.asarray(c, float) * sc]
                                for c in chains]}
    return out


def layout(views: dict, page: str = "A3", margin: float = 10.0) -> dict:
    """Page-coordinate chains per view (the draughting sheet)."""
    return {name: p["chains"] for name, p in
            place(views, page, margin).items()}


# ---------------------------------------------------------------------------
# M110 — parts list (BOM) and balloons, per ISO 7573 / ISO 6433.


def _stem(name: str) -> str:
    """'Bracket 2' → 'Bracket' — the auto-suffix our body naming adds.
    Two bodies sharing a stem AND identical volume are one part twice."""
    out = name.rstrip()
    i = len(out)
    while i and out[i - 1].isdigit():
        i -= 1
    if i < len(out) and i and out[i - 1] in " .-_":
        return out[:i].rstrip(" .-_")
    return name


def parts_list(bodies, solids, mass_unit: str = "g") -> list:
    """Rows for the sheet's parts list (ISO 7573 columns, trimmed to
    what a mesh document truly knows: item, description, qty, material,
    mass).  Hidden bodies stay off the list; a body whose solid is
    unknown still appears — with mass '—' — because the list must never
    silently drop a part.  Masses multiply by qty (row mass, not unit
    mass), the convention downstream spreadsheets expect."""
    from . import materials
    rows, order = {}, []
    for b in bodies or []:
        if not b.get("visible", True):
            continue
        name = b.get("name", "")
        s = solids.get(name) if solids else None
        vol = round(float(s.volume), 6) if s is not None else None
        mat = b.get("material") or ""
        key = (_stem(name), vol, mat)
        if key in rows:
            rows[key]["qty"] += 1
            continue
        g = materials.mass_g(vol, mat or None) \
            if vol is not None else None
        order.append(key)
        rows[key] = {"name": name, "stem": _stem(name), "qty": 1,
                     "material": mat or "—", "mass_g": g}
    out = []
    for i, key in enumerate(order, start=1):
        r = rows[key]
        q = r["qty"]
        g = r["mass_g"]
        out.append({"item": i,
                    "description": r["stem"] if q > 1 else r["name"],
                    "qty": q, "material": r["material"],
                    "mass": materials.mass_str(
                        None if g is None else g * q, mass_unit)})
    return out


BOM_COLUMNS = (("item", 0.12, "c"), ("description", 0.46, "l"),
               ("qty", 0.10, "r"), ("material", 0.18, "l"),
               ("mass", 0.14, "r"))


def parts_list_table(rows, block_rect, page: str = "A3",
                     margin: float = 10.0, hh: float = 5.0) -> dict:
    """Resolve parts-list rows into sheet-mm geometry, ready for the
    same cell-painter the title block uses (M108 contract: rect, lines,
    cells).  The table docks against the title block's top edge — ISO
    7573: when the list sits ON the drawing it reads bottom-to-top with
    the heading adjacent to the title block — sharing its 180 mm width
    so the sheet's right edge stays one clean line.  Rows that no
    longer fit are counted in ``overflow`` (the painter adds a note);
    the list never silently truncates."""
    W, H = sheet_size(page)
    bx, by, bw, bh = block_rect
    x0, ybot = bx, by + bh
    room = (H - margin) - ybot
    n = int(room // hh)
    overflow = max(0, len(rows) - n)
    shown = rows[:n]
    h_used = (len(shown) + 1) * hh                     # + heading row
    xs = [x0]
    for _, frac, _ in BOM_COLUMNS:
        xs.append(xs[-1] + bw * frac)
    lines = []
    for i in range(len(shown) + 2):                    # horizontals
        y = ybot + i * hh
        lines.append(((x0, y), (x0 + bw, y)))
    for xa in xs:                                      # verticals
        lines.append(((xa, ybot), (xa, ybot + h_used)))
    cells = []

    def put(col_i, text, y, bold=False):
        key, frac, align = BOM_COLUMNS[col_i]
        cells.append({"text": str(text), "xa": xs[col_i], "xb": xs[col_i + 1],
                      "y": y, "size": hh * (0.52 if bold else 0.62),
                      "align": align, "col": key,
                      "bold": bool(bold)})

    yh = ybot + (len(shown) + 0.5) * hh                # heading centre
    for ci, (key, _f, _a) in enumerate(BOM_COLUMNS):
        put(ci, {"item": "It.", "description": "Description",
                 "qty": "Qty", "material": "Material",
                 "mass": "Mass"}[key], yh, bold=True)
    for i, r in enumerate(shown):                      # bottom-to-top
        y = ybot + (i + 0.5) * hh
        for ci, (key, _f, _a) in enumerate(BOM_COLUMNS):
            put(ci, r.get(key, ""), y)
    return {"rect": (x0, ybot, bw, h_used), "lines": lines,
            "cells": cells, "overflow": overflow,
            "reversed": False}


# ---------------------------------------------------------------------------
# M129 — holes speak on the drawing: table + marks, from metadata.
#
# Rows and bubbles derive straight from HoleFeature fields (M123 sizes,
# M128 designations) — never measured off a mesh, because a 24-gon
# under-reads a diameter. A hole is marked in the view you look INTO
# the bore from (axis parallel to the view direction), anchored in
# model millimetres like balloons so a dragged view carries its holes.


HOLE_COLUMNS = (("item", 0.10, "c"), ("hole", 0.34, "l"),
                ("qty", 0.12, "r"), ("depth", 0.22, "r"),
                ("drill", 0.22, "r"))


def _hole_groups(doc):
    """(groups, per-feature item numbers) in first-appearance order.
    Suppressed holes stay silent; identical (label, note, depth, drill)
    holes group into one counted row — same thread, same depth, one
    line. A plain hole's own Ø is its drill line ('' — no second
    number to lie with)."""
    from .document import HoleFeature
    order: list = []
    seen: dict = {}
    items: list = []
    for f in doc.features:
        if not isinstance(f, HoleFeature) or f.suppressed:
            continue
        label = (f.designation or f"Ø {2 * f.radius:g}"
                 if f.thread_pitch > 0 else f"Ø {2 * f.radius:g}")
        if f.cb_radius > f.radius + 1e-9:
            note = f"cbore Ø {2 * f.cb_radius:g}×{f.cb_depth:g}"
        elif f.cs_radius > f.radius + 1e-9:
            note = f"csink Ø {2 * f.cs_radius:g}×{f.cs_angle:g}°"
        else:
            note = ""
        depth = "THRU" if f.through else f"{f.depth:g}"
        drill = f"Ø {2 * f.radius:g}" if f.thread_pitch > 0 else ""
        key = (label, note, depth, drill)
        if key not in seen:
            seen[key] = len(order)
            order.append({"label": label, "note": note, "depth": depth,
                          "drill": drill, "qty": 0})
        order[seen[key]]["qty"] += 1
        items.append((f, seen[key]))
    rows = [{"item": i + 1,
             "hole": g["label"] + (" " + g["note"] if g["note"] else ""),
             "qty": g["qty"], "depth": g["depth"], "drill": g["drill"]}
            for i, g in enumerate(order)]
    return rows, [(f, gi + 1) for f, gi in items]


def hole_rows(doc) -> list:
    """Sheet rows: It. | Hole | Qty | Depth | Drill."""
    return _hole_groups(doc)[0]


def hole_marks(doc) -> dict:
    """Per standard view: model-space centres to tag, keyed by view.
    Threaded holes tag at the ISO major (the cosmetic reference
    circle); plain holes at the drilled radius. Iso takes no marks —
    a bore seen at an angle shows no true circle."""
    _, items = _hole_groups(doc)
    out: dict = {}
    for f, item in items:
        n = np.asarray(f.normal, float)
        n = n / np.linalg.norm(n)
        c = np.asarray(f.center, float)
        if f.thread_pitch > 0:
            from .thread import major
            m = major(f.thread_size or "")
            r = m / 2.0 if m > 0 else \
                float(f.radius) + float(f.thread_pitch) / 2.0
        else:
            r = float(f.radius)
        for view in ("top", "front", "right"):
            d, x, y = _basis(view)
            if abs(float(np.dot(n, d))) < 0.99:
                continue                # across the sight: hidden
                #                       # lines territory, no circle
            out.setdefault(view, []).append(
                {"item": item, "x": float(np.dot(c, x)),
                 "y": float(np.dot(c, y)), "r": float(r)})
    return out


def hole_table(rows, page: str = "A3", margin: float = 10.0,
               hh: float = 5.0, width: float | None = None) -> dict:
    """The parts list's contract (rect/lines/cells, M108 painter) for
    the hole table — but reading TOP-to-bottom from the sheet's upper
    left, the corner the title block's BOM never claims. Overflow is
    counted, never silent."""
    W, H = sheet_size(page)
    bw = float(width) if width else min(0.40 * W, 150.0)
    x0 = margin
    ytop = H - margin
    n = max(0, int(((H - 2 * margin) * 0.5) // hh) - 1)
    overflow = max(0, len(rows) - n)
    shown = rows[:n]
    h_used = (len(shown) + 1) * hh
    ybot = ytop - h_used
    xs = [x0]
    for _, frac, _ in HOLE_COLUMNS:
        xs.append(xs[-1] + bw * frac)
    lines = [((x0, ybot + i * hh), (x0 + bw, ybot + i * hh))
             for i in range(len(shown) + 2)]
    lines += [((xa, ybot), (xa, ytop)) for xa in xs]
    cells = []

    def put(col_i, text, y, bold=False):
        key, frac, align = HOLE_COLUMNS[col_i]
        cells.append({"text": str(text), "xa": xs[col_i],
                      "xb": xs[col_i + 1], "y": y,
                      "size": hh * (0.52 if bold else 0.62),
                      "align": align, "col": key, "bold": bool(bold)})

    for ci, (key, _f, _a) in enumerate(HOLE_COLUMNS):
        put(ci, {"item": "It.", "hole": "Hole", "qty": "Qty",
                 "depth": "Depth", "drill": "Drill"}[key],
            ytop - 0.5 * hh, bold=True)
    for i, r in enumerate(shown):
        for ci, (key, _f, _a) in enumerate(HOLE_COLUMNS):
            put(ci, r.get(key, ""), ytop - (i + 1.5) * hh)
    return {"rect": (x0, ybot, bw, h_used), "lines": lines,
            "cells": cells, "overflow": overflow, "reversed": False}


# ---- M201 R38: the hole table's ORIGIN -------------------------------------
# [Create a hole table, verbatim] "In the canvas, select a drawing view to
# associate with the hole table and click to place the origin." / [Tables
# overview, verbatim] "Hole tables require an origin." / "Each view require
# its own origin." (the grammar error is the page's, printed exactly). The
# origin is the table's measuring stick: "[Origin] Specifies the origin used
# to measure hole X and Y coordinates." The page prints TWO arrange members
# and nothing else: "by Position: Holes are located and labeled according to
# their physical location to the origin" / "by Size: ... according to their
# size from the smallest to largest" (lower-case "by" is page-printed).
ARRANGE_MODES = ("by Position", "by Size")
# [verbatim, P1/P2 order] four styles - the help NEVER prints "ANSI".
ORIGIN_STYLES = ("Datum Target", "ISO Origin", "ASME Origin",
                 "Alternate Origin")


def require_origin(shop: dict, view: str) -> tuple:
    """The origin store is keyed BY VIEW and that keying IS the page's law
    - a table never measures from a NEIGHBOUR's origin ("Each view require
    its own origin.") and never silently from (0, 0) ("Hole tables require
    an origin."). A miss is a NAMED refusal carrying the page's own
    sentences; the refusal NAME is ours (the page prints no error text)."""
    try:
        return tuple(shop[view])
    except KeyError:
        raise ValueError(
            "HOLE_TABLE_NO_ORIGIN: Hole tables require an origin - and "
            "each view require its own origin (the page's two sentences, "
            "grammar verbatim; the refusal name is ours)") from None


def place_origin(shop: dict, view: str, pt) -> dict:
    """ONE origin per view, by CONSTRUCTION: the store is a mapping keyed
    by view, so a second placement REPLACES - it cannot leave a second
    origin to disagree with the first. That is our reading of the page's
    reuse sentence "Hole Table utilizes the Ordinate Dimensions origin if
    available, and vice versa.": with no second family of origins to
    share with (Tracer has no ordinate dimensions yet), reuse can only
    mean never-duplicate. OURS-STAMP, named."""
    shop[view] = (float(pt[0]), float(pt[1]))
    return shop


def require_style(style: str) -> str:
    """The four page-printed members, and ONLY those - a request for
    "ANSI Origin" (what the vendor's BLOG says while the help says ASME)
    is refused by name, never quietly mapped."""
    if style not in ORIGIN_STYLES:
        raise ValueError(f"ORIGIN_STYLE_UNKNOWN {style!r} - the help "
                         f"prints only {ORIGIN_STYLES}")
    return style


def view_hole_rows(doc, view: str, origin, arrange: str = "by Position"):
    """The table FOR ONE VIEW: "The hole table displays on the sheet and
    is populated with information about the holes in the view you
    selected." - a bore across the sight shows no true circle in that
    view (hole_marks already answers nothing for it) and so gets NO row;
    the iso answers nothing at all, and its table is EMPTY, not refused
    (page silence on host views: any view answers, like the breakout).
    Arrange re-labels the counted rows: "by Size" sorts "from smallest to
    largest"; "by Position" reads DOWN from the origin first, then right.
    THE READING ORDER AND EVERY TIE-BREAK ARE TRACER STAMPS - the page
    names the two orders but prints no detail beyond them. Returns
    (rows, xy): rows carry the renumbered "item"; xy is each row's first
    member measured FROM THE ORIGIN, the page's X and Y coordinates."""
    if arrange not in ARRANGE_MODES:
        raise ValueError(f"ARRANGE_UNKNOWN {arrange!r} - the page prints "
                         f"only {ARRANGE_MODES}")
    ox, oy = (float(origin[0]), float(origin[1]))
    rows_all, _items = _hole_groups(doc)
    marks = hole_marks(doc).get(view, [])
    pos: dict = {}                       # group -> reading-first (y, x)
    size: dict = {}                      # group -> smallest tagged radius
    for m in marks:
        g = m["item"]
        if (g not in pos or
                (m["y"], -m["x"]) > (pos[g][0], -pos[g][1])):
            pos[g] = (m["y"], m["x"])
        if g not in size or m["r"] < size[g]:
            size[g] = m["r"]

    def key(g):
        gx, gy = pos[g][1] - ox, pos[g][0] - oy
        return (size[g], -gy, gx) if arrange == "by Size" else (-gy, gx)

    rows, xy = [], []
    for i, g in enumerate(sorted(pos, key=key)):
        r = dict(rows_all[g - 1])
        r["item"] = i + 1                # renumbered by the page's order
        rows.append(r)
        xy.append({"item": i + 1, "x": pos[g][1] - ox,
                   "y": pos[g][0] - oy})
    return rows, xy
