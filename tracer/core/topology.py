"""M116 — the crowned module: face groups and semantic edges.

A mesh pick only ever answers "(body, triangle)". Everything above it
— hover a face, click an edge, let the fillet dialog speak "the rim of
this hole", re-bind a fillet after the model moves, classify crossing
windows — needs ONE classifier that turns triangles into the things
designers name. This is it, run once per body and cached on the Solid:

* crease test: two adjacent faces fold more than SHARP_DEG apart;
* face groups: union-find (connected components) over NON-crease
  adjacency — a box leaves with six, a cylinder with three;
* semantic edges: the crease graph walked between CORNERS (a vertex
  where three or more creases meet, or where two meet at a sharp
  turn), so the twelve triangles of a box side yield one rectangle
  per side edge, and the round rim of a hole returns as ONE closed
  loop;
* groups carry area, best-fit plane and a planarity verdict.

The mesh kernel guarantees the input is manifold with outward
triangles, so no repair and no degenerate chase — just read the shape
that is actually there. Pure numpy/scipy; nothing here knows Qt.

Research: selection_filter.md action 1 (one classifier, three
consumers: drawing lines, 3D selection kinds, fillet identity).
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

SHARP_DEG = 25.0      # fold between faces that makes an edge "creased"
TURN_DEG = 30.0       # turn along a crease path that makes a corner
PLANAR_DEG = 0.5      # spread of face normals still called a plane


def _fold_degrees(normals, pairs) -> np.ndarray:
    dots = np.einsum("ij,ij->i", normals[pairs[:, 0]], normals[pairs[:, 1]])
    return np.degrees(np.arccos(np.clip(dots, -1.0, 1.0)))


class Topology:
    """The face/edge/corner reading of one Solid's triangulation."""

    def __init__(self, tm):
        self._tm = tm
        fn = np.asarray(tm.face_normals, float)
        self._pairs = np.asarray(tm.face_adjacency, int)
        self._all_edges = np.asarray(tm.face_adjacency_edges, int)
        if len(self._pairs):
            # cone/apex slivers from the kernel carry float-noise normals;
            # a fold only counts as a crease when BOTH faces have area
            fa = np.asarray(tm.area_faces, float)
            honest = fa[self._pairs].min(axis=1) > 1e-9
            self._crease = ((_fold_degrees(fn, self._pairs) > SHARP_DEG)
                            & honest)
        else:
            self._crease = np.zeros(0, bool)

        # ---- face groups: union-find over the SMOOTH adjacency ------
        n = len(tm.faces)
        if len(self._pairs):
            smooth = self._pairs[~self._crease]
            graph = coo_matrix((np.ones(len(smooth)),
                                (smooth[:, 0], smooth[:, 1])), shape=(n, n))
            self.n_groups, self.face_groups = connected_components(
                graph, directed=False)
        else:
            self.n_groups, self.face_groups = (n, np.arange(n)) \
                if n else (0, np.zeros(0, int))
        self._groups = self._read_groups(fn)

        # ---- crease graph → corners → semantic edges -----------------
        rows = np.flatnonzero(self._crease)
        c_edges = self._all_edges[rows]
        self.edges, self.corners, self._pair_edge = self._walk(
            np.asarray(tm.vertices, float), c_edges, rows)

    # ------------------------------------------------------------------
    def _read_groups(self, fn) -> list[dict]:
        faces = np.asarray(self._tm.faces, int)
        verts = np.asarray(self._tm.vertices, float)
        areas = np.asarray(self._tm.area_faces, float)
        out = []
        for g in range(self.n_groups):
            idx = np.flatnonzero(self.face_groups == g)
            a = float(areas[idx].sum())
            w = areas[idx] / a if a > 0 else np.full(len(idx), 1.0 / len(idx))
            n_mean = (fn[idx] * w[:, None]).sum(0)
            len_n = float(np.linalg.norm(n_mean))
            if len_n < 1e-12:               # dust group: borrow any face
                n_mean = fn[idx][0]
                len_n = float(np.linalg.norm(n_mean)) or 1.0
            n_mean = n_mean / len_n
            spread = float(np.degrees(np.arccos(
                np.clip(fn[idx] @ n_mean, -1.0, 1.0))).max())
            ctr = verts[faces[idx]].mean((0, 1))
            out.append({"tris": idx, "area": a, "normal": n_mean,
                        "center": ctr, "planar": bool(spread < PLANAR_DEG),
                        "spread_deg": spread})
        return out

    def _walk(self, verts, c_edges, rows):
        """Chain crease edges between corners into semantic edges; a
        cornerless cycle returns as ONE closed loop. Also maps each
        crease FACE-PAIR to its semantic edge index (pick → token)."""
        adj: dict[int, list[tuple[int, int]]] = {}
        for i, (a, b) in enumerate(c_edges):
            adj.setdefault(int(a), []).append((int(b), i))
            adj.setdefault(int(b), []).append((int(a), i))

        corner: set[int] = set()
        for v, lst in adj.items():
            if len(lst) >= 3:
                corner.add(v)
                continue
            if len(lst) == 2:                       # sharp turn?
                (a, _), (b, _) = lst
                d1, d2 = verts[a] - verts[v], verts[b] - verts[v]
                n1, n2 = np.linalg.norm(d1), np.linalg.norm(d2)
                if n1 <= 0 or n2 <= 0:
                    corner.add(v)
                    continue
                ang = float(np.degrees(np.arccos(
                    np.clip(d1 @ d2 / (n1 * n2), -1.0, 1.0))))
                if ang < 180.0 - TURN_DEG:          # straight is ~180
                    corner.add(v)

        used = [False] * len(c_edges)
        out: list[dict] = []

        def take(start, first):
            """Walk from corner `start` along unused creases."""
            nxt, e0 = first
            used[e0] = True
            path, eids, prev, cur = [start, nxt], [e0], e0, nxt
            while cur != start and cur not in corner:
                step = None
                for v, e in adj[cur]:
                    if e != prev and not used[e]:
                        step = (v, e)
                        break
                if step is None:
                    break
                v, e = step
                used[e] = True
                path.append(v)
                eids.append(e)
                prev, cur = e, v
            return path, eids, cur

        for s in sorted(corner):
            for first in list(adj.get(s, [])):
                if used[first[1]]:
                    continue
                path, eids, cur = take(s, first)
                out.append(self._record(path, eids,
                                        cur == s and len(eids) > 2))
        # cornerless cycles (a full circle has no corners at all)
        for e0 in range(len(c_edges)):
            if used[e0]:
                continue
            a, b = int(c_edges[e0][0]), int(c_edges[e0][1])
            used[e0] = True
            path, eids, prev, cur = [a, b], [e0], e0, b
            while cur != a:
                step = None
                for v, e in adj[cur]:
                    if e != prev and not used[e]:
                        step = (v, e)
                        break
                if step is None:
                    break
                v, e = step
                used[e] = True
                path.append(v)
                eids.append(e)
                prev, cur = e, v
            out.append(self._record(path, eids,
                                    cur == a and len(eids) > 2))

        pair_edge: dict[tuple[int, int], int] = {}
        for i, se in enumerate(out):
            for e in se["edge_ids"]:
                f1, f2 = self._pairs[rows[e]]
                pair_edge[(min(int(f1), int(f2)), max(int(f1), int(f2)))] = i
        return out, np.array(sorted(corner), int), pair_edge

    def _record(self, path, eids, closed) -> dict:
        pts = np.asarray(self._tm.vertices, float)[path]
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        length = float(seg.sum())
        if closed:
            length += float(np.linalg.norm(pts[-1] - pts[0]))
        return {"verts": [int(v) for v in path], "edge_ids": list(eids),
                "closed": bool(closed), "length": length}

    # ---- queries ------------------------------------------------------
    def group_of_face(self, tri: int) -> int:
        return int(self.face_groups[tri])

    def group(self, g: int) -> dict:
        return self._groups[g]

    @property
    def groups(self) -> list[dict]:
        return self._groups

    def flat_groups(self) -> list[int]:
        """Group ids that are planes — what Shell eats, what a datum
        snaps to."""
        return [g for g, d in enumerate(self._groups) if d["planar"]]

    def closed_loops(self) -> list[dict]:
        return [e for e in self.edges if e["closed"]]

    def edge_of_faces(self, f1: int, f2: int) -> dict | None:
        """The semantic edge two faces fold along — the triangle-pick
        to edge-token answer the fillet dialog waits for."""
        key = (min(int(f1), int(f2)), max(int(f1), int(f2)))
        i = self._pair_edge.get(key)
        return self.edges[i] if i is not None else None


def topology(solid) -> Topology:
    """The cached Topology of a Solid (Solids are value-typed, so the
    cache can never go stale under their feet)."""
    return solid.topology()
