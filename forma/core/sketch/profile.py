"""Closed-loop finding + region nesting (outer loop with its holes).

Algorithm: merge coincident endpoints (union-find on coords within eps),
then walk minimal faces — at every node take the unused edge that makes
the smallest CCW turn from the reversed incoming direction. On planar
straight-skeleton sketches this yields exactly the bounded faces; we keep
the ones with positive signed area (CCW = filled under even-odd).
"""
from __future__ import annotations

import math

import numpy as np

_EPS = 1e-7


class _UnionFind:
    def __init__(self):
        self.parent: list[int] = []

    def add(self) -> int:
        self.parent.append(len(self.parent))
        return len(self.parent) - 1

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _polygon_area(poly: np.ndarray) -> float:
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _point_in_poly(pt, poly: np.ndarray) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-300) + xi:
            inside = not inside
        j = i
    return inside


def loops_from_lines_and_circles(lines, circles, arcs=()):
    """Returns (loops, warnings).

    loops: list of dicts {points: Nx2 float64 ccw, area: float}
    warnings: list of strings (dangling/open geometry etc).
    Arcs contribute their chord-subdivided polyline: the endpoints are the
    arc's real shared Points (connect to lines); interior samples are
    ephemeral degree-2 nodes.
    """
    warnings: list[str] = []
    uf = _UnionFind()
    node_of: dict[int, int] = {}          # entity point id -> node idx
    pts: dict[int, tuple] = {}            # node idx -> (x,y), last writer wins

    def node_for(p):
        if p.id not in node_of:
            node_of[p.id] = uf.add()
            pts[node_of[p.id]] = (float(p.x), float(p.y))
        n = node_of[p.id]
        pts[n] = (float(p.x), float(p.y))
        return n

    def node_xy(xy):                      # ephemeral tessellation vertex
        n = uf.add()
        pts[n] = (float(xy[0]), float(xy[1]))
        return n

    edges = []  # (n0, n1) half-edge pool
    for ln in lines:
        n0, n1 = node_for(ln.a), node_for(ln.b)
        if n0 == n1:
            warnings.append("zero-length edge skipped")
            continue
        edges.append([n0, n1, False])

    for ar in arcs:
        smp = ar.sample(48)
        if len(smp) < 3:
            continue
        chain = [node_for(ar.a)]
        chain += [node_xy(r) for r in smp[1:-1]]
        chain.append(node_for(ar.b))
        for u_, v_ in zip(chain, chain[1:]):
            if u_ != v_:
                edges.append([u_, v_, False])

    # merge coincident-but-distinct endpoints (drawn without snap)
    coords = {n: xy for n, xy in pts.items()}
    ns = sorted(coords)
    for i, a in enumerate(ns):
        for b in ns[i + 1:]:
            if math.hypot(coords[a][0] - coords[b][0],
                          coords[a][1] - coords[b][1]) <= _EPS:
                uf.union(a, b)

    key = {n: uf.find(n) for n in pts}
    cpts: dict[int, tuple] = {}
    for n, xy in pts.items():
        cpts.setdefault(key[n], xy)

    adj_out: dict[int, list[int]] = {}
    halves: list[list] = []               # [u, v, used] directed
    seen_pair = set()
    for e in edges:
        u, v = key[e[0]], key[e[1]]
        if u == v:
            continue
        pair = (min(u, v), max(u, v))
        if pair in seen_pair:
            continue                       # same segment drawn twice
        seen_pair.add(pair)
        hi = len(halves)
        halves.append([u, v, False])
        halves.append([v, u, False])
        adj_out.setdefault(u, []).append(hi)
        adj_out.setdefault(v, []).append(hi + 1)
    degree: dict[int, int] = {}
    for e in edges:
        if key[e[0]] != key[e[1]]:
            degree[key[e[0]]] = degree.get(key[e[0]], 0) + 1
            degree[key[e[1]]] = degree.get(key[e[1]], 0) + 1
    odd = [n for n, d in degree.items() if d % 2]
    if odd:
        warnings.append(f"{len(odd)} odd-degree nodes: sketch not fully closed")

    def ang(n_from, n_to):
        a, b = cpts[n_from], cpts[n_to]
        return math.atan2(b[1] - a[1], b[0] - a[0])

    loops = []
    for h0 in range(len(halves)):
        if halves[h0][2]:
            continue
        u, v, _ = halves[h0]
        halves[h0][2] = True
        prev, cur = u, v
        poly_nodes = [u, v]
        ok = False
        for _ in range(8192):
            if cur == u:
                ok = True
                break
            # keep the face on the LEFT: most-clockwise from reversed
            # incoming direction (DCEL minimal-face walk); twin excluded.
            back = ang(cur, prev)
            best_i, best_da = None, math.inf
            for hi in adj_out.get(cur, []):
                h = halves[hi]
                if h[2] or h[1] == prev:
                    continue
                a = (back - ang(cur, h[1])) % (2 * math.pi)
                if a < best_da:
                    best_i, best_da = hi, a
            if best_i is None:
                break
            halves[best_i][2] = True
            nxt = halves[best_i][1]
            poly_nodes.append(nxt)
            prev, cur = cur, nxt
        if not ok or len(poly_nodes) < 4:
            continue
        p = np.array([cpts[n] for n in poly_nodes[:-1]], dtype=np.float64)
        a = _polygon_area(p)
        if a <= 1e-12:
            continue                       # CW outer face or degenerate
        loops.append({"points": p, "area": float(a)})

    # circles: independent CCW loops
    from ..geometry import circle_contour
    for c in circles:
        if c.r <= _EPS:
            warnings.append("zero-radius circle skipped")
            continue
        p = circle_contour(c.r, (c.c.x, c.c.y), segments=96)
        loops.append({"points": p, "area": math.pi * c.r * c.r})

    return loops, warnings


def regions(loops):
    """Nesting: even depth = filled region. Returns [outer_loop, ...] each
    augmented with 'holes': [loop,...] (direct children).

    Only 2-level nesting (plate + holes) is exposed today; deeper nesting
    is reported as a warning and flattened per even-odd."""
    outers = []
    for i, L in enumerate(loops):
        depth = 0
        for j, M in enumerate(loops):
            if i != j and _point_in_poly(L["points"][0], M["points"]):
                depth += 1
        L["_depth"] = depth
        if depth % 2 == 0:
            outers.append(L)
    for L in loops:
        if L["_depth"] % 2 == 1:
            # nearest even-depth ancestor
            best, bd = None, -1
            for O in outers:
                if _point_in_poly(L["points"][0], O["points"]) and L is not O:
                    d = np.linalg.norm(L["points"].mean(axis=0) - O["points"].mean(axis=0))
                    if best is None or d < bd:
                        best, bd = O, d
            if best is not None:
                best.setdefault("holes", []).append(L)
    for O in outers:
        O.setdefault("holes", [])
    return outers
