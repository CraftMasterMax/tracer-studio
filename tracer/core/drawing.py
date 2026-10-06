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


def layout(views: dict, page: str = "A3", margin: float = 10.0) -> dict:
    """Scale each view and centre it in its sheet slot (page mm, y up,
    origin at the sheet's lower-left):

        top   | iso
        ------+------
        front | right
    """
    sc = fit_scale(views, page, margin)
    W, H = PAGES.get(page, PAGES["A3"])
    slots = {"top": (0.28 * W, 0.72 * H), "iso": (0.72 * W, 0.72 * H),
             "front": (0.28 * W, 0.28 * H), "right": (0.72 * W, 0.28 * H)}
    out: dict = {}
    for name, chains in views.items():
        if not chains:
            continue
        P = np.vstack([np.asarray(c, float) * sc for c in chains])
        cx = 0.5 * (P[:, 0].max() + P[:, 0].min())
        cy = 0.5 * (P[:, 1].max() + P[:, 1].min())
        sx, sy = slots.get(name, (0.5 * W, 0.5 * H))
        out[name] = [[(float(p[0] * sc + sx - cx),
                       float(p[1] * sc + sy - cy)) for p in c]
                     for c in chains]
    return out
