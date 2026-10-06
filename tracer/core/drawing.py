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
        fx, fy = SLOTS.get(name, (0.5, 0.5))
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
