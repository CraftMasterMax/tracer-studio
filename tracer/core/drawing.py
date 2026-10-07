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
PAGES = {"A3": (420.0, 297.0), "A4": (297.0, 210.0)}     # landscape mm

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
    W, H = PAGES.get(page, PAGES["A3"])
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


def _basis(view: str) -> tuple:
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
                if _covered(mids[i], float(mdeps[i]), tri2, triD):
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
    W, H = PAGES.get(page, PAGES["A3"])
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
    import trimesh
    tm = solid.to_trimesh()
    nrm = np.zeros(3)
    nrm[i] = 1.0
    _, X, Y = _basis(view)
    loops: list = []
    for off in (0.0, 1e-3, -1e-3):
        try:
            sec = tm.section(plane_origin=nrm * (at + off),
                             plane_normal=nrm)
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
    res = {"half": half, "view": view, "cut": loops}
    if len(_section_cache) > 64:
        _section_cache.clear()
    _section_cache[key] = (solid, res)
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
    W, H = PAGES.get(page, PAGES["A3"])
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
    W, H = PAGES.get(page, PAGES["A3"])
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
    W, H = PAGES.get(page, PAGES["A3"])
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
