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


def project_view(solid, view: str = "top", eps: float = 1e-6) -> list:
    """Silhouette polylines of a Solid seen along a named view.
    Returns a list of point-lists; a closed chain repeats its start."""
    tm = solid.to_trimesh()
    if not len(tm.faces) or not len(tm.face_adjacency):
        return []
    d, X, Y = _basis(view)
    facing = tm.face_normals @ d
    v2 = np.stack([tm.vertices @ X, tm.vertices @ Y], axis=1)
    s = facing[tm.face_adjacency]
    a, b = s[:, 0], s[:, 1]
    sil = ((a > eps) & (b <= eps)) | ((b > eps) & (a <= eps))
    # ...plus crease edges: two front-facing faces that sharply bend
    # (a cube's corner seen in iso draws its Y — the draughtsman's
    # visible edge between lit faces). ~40 deg threshold: coplanar
    # triangulation crumbs stay invisible, smooth walls too.
    n = tm.face_normals[tm.face_adjacency]
    crease = (a > eps) & (b > eps) & \
        ((n[:, 0] * n[:, 1]).sum(axis=1) < math.cos(math.radians(40.0)))
    sil = sil | crease
    segs = v2[tm.face_adjacency_edges[sil]]
    return _chain(segs)


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


def _front_region(chains: list):
    """The draughting 'paper' the visible faces cover: closed rings
    unioned, inner rings subtracted (a bore is a hole in the region).
    None when the view has no closed loop at all."""
    from shapely.geometry import MultiPoint, Polygon
    from shapely.ops import unary_union
    rings = []
    for c in chains:
        P = np.asarray(c, float)
        if len(P) > 3 and np.allclose(P[0], P[-1], atol=1e-6):
            try:
                poly = Polygon(P)
            except Exception:
                continue
            if poly.is_valid and poly.area > 1e-9:
                rings.append(poly)
    if not rings:
        # the chain walk can weave creases INTO the silhouette ring
        # (a box's iso hexagon arrives as open trails): fall back to
        # the convex hull of everything visible — the safe outer
        pts = np.vstack([np.asarray(c, float) for c in chains
                         if len(c) > 1])
        if len(pts) < 3:
            return None
        hull = MultiPoint(pts).convex_hull
        return hull if hull.area > 1e-9 else None
    rings.sort(key=lambda q: -q.area)
    outers, region = [], None
    for i, p in enumerate(rings):
        rp = p.representative_point()
        if any(j != i and q.area > p.area and q.contains(rp)
               for j, q in enumerate(rings)):
            continue                       # nested: it's a hole, not an outer
        holes = [q for q in rings
                 if q is not p and q.area < p.area
                 and p.contains(q.representative_point())]
        piece = p.difference(unary_union(holes)) if holes else p
        outers.append(piece)
        region = piece if region is None else region.union(piece)
    return region


def project_hidden(solid, view: str = "top", eps: float = 1e-6,
                   visible: list | None = None) -> list:
    """M97: the dashed chains. An edge hides when NEITHER adjacent
    face looks at the viewer (both face away) AND the fold is sharp
    (>40° — a smooth wall never dashes into a mesh wireframe) AND the
    segment midpoint falls strictly INSIDE the front-facing silhouette
    region, so rim-on-rim coincidences (through holes, convex
    outlines) clip away exactly as the draughting standard expects.
    `visible` may carry a precomputed project_view to skip rework."""
    tm = solid.to_trimesh()
    if not len(tm.faces) or not len(tm.face_adjacency):
        return []
    d, X, Y = _basis(view)
    facing = tm.face_normals @ d
    v2 = np.stack([tm.vertices @ X, tm.vertices @ Y], axis=1)
    s = facing[tm.face_adjacency]
    a, b = s[:, 0], s[:, 1]
    n = tm.face_normals[tm.face_adjacency]
    back = (a <= -eps) & (b <= -eps) & \
        ((n[:, 0] * n[:, 1]).sum(axis=1) < math.cos(math.radians(40.0)))
    if not back.any():
        return []
    vis = (project_view(solid, view=view, eps=eps)
           if visible is None else visible)
    region = _front_region(vis)
    if region is None:
        return []
    from shapely.geometry import Point
    segs = v2[tm.face_adjacency_edges[back]]
    keep = [seg for seg in segs
            if region.contains(Point((seg[0] + seg[1]) * 0.5))]
    if not keep:
        return []
    chains = _chain(np.asarray(keep))
    # a hidden chain that merely re-traces visible ink is noise
    vpts = {(round(float(p[0]), 6), round(float(p[1]), 6))
            for c in vis for p in c}
    out = []
    for c in chains:
        pts = [(round(float(p[0]), 6), round(float(p[1]), 6)) for p in c]
        if all(p in vpts for p in pts):
            continue
        out.append([(float(p[0]), float(p[1])) for p in c])
    return out


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


def place(views: dict, page: str = "A3", margin: float = 10.0,
          moves: dict | None = None) -> dict:
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
    sc = fit_scale(views, page, margin)
    W, H = PAGES.get(page, PAGES["A3"])
    out: dict = {}
    for name, chains in views.items():
        if not chains:
            continue
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
