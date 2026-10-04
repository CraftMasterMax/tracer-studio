"""Press-Pull support: extract a planar face region from the result mesh.

Fusion's Press-Pull lets you grab a face and drag it: material is added
along the outward normal or removed against it. On this mesh kernel a
"face" is the coplanar triangle group the viewport already uses for
hover/select. This module validates that the group really tiles one flat
region and returns its boundary as 2D polygons in the face's own (u, v)
basis, so the UI can express the edit as a regular ExtrudeFeature —
parametric, suppressible, serialized, undoable, for free.

Curved or ragged selections are rejected (None) rather than approximated;
the UI then says so instead of silently making junk geometry.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

import numpy as np

from .sketch.model import face_basis

NORMAL_TOL_DEG = 1.5      # whole-patch normal spread allowed for "flat"
PLANAR_TOL = 1e-4         # vertex off-plane slack, fraction of patch size
HOLE_MIN_AREA = 1e-3      # holes smaller than this share of the outer loop
MAX_SLIMNESS = 30.0       # diagonal² / area cap: kills wall-column slivers


def _loops(bnd: list[tuple[int, int]]) -> list[list[int]] | None:
    """Order undirected boundary edges into closed loops (None if the
    edge graph is not a disjoint set of cycles)."""
    graph = defaultdict(list)
    for a, b in bnd:
        graph[a].append(b)
        graph[b].append(a)
    if any(len(nb) != 2 for nb in graph.values()):
        return None
    done: set[int] = set()
    loops: list[list[int]] = []
    for start in graph:
        if start in done:
            continue
        loop = [start]
        done.add(start)
        prev, cur = None, start
        while True:
            nxts = [x for x in graph[cur] if x != prev] or graph[cur]
            nxt = nxts[0]
            if nxt == start:
                break
            if nxt in done:
                return None                      # figure-eight / reuse
            loop.append(nxt)
            done.add(nxt)
            prev, cur = cur, nxt
        if len(loop) >= 3:
            loops.append(loop)
        else:
            return None
    return loops if loops else None


def _area2(pts: np.ndarray) -> float:
    return float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1)
                        - np.roll(pts[:, 0], -1) * pts[:, 1])) / 2.0


def face_region(mesh, faces) -> dict | None:
    """Validate a triangle group as one flat face and extract it.

    Returns {'point', 'normal', 'u', 'v', 'outer' (N,2), 'holes' [M,2]}
    or None when the set is curved, non-planar, empty or not a proper
    disc-with-holes patch.
    """
    faces = np.asarray(faces, int)
    if faces.size == 0:
        return None
    fn = np.asarray(mesh.face_normals, float)[faces]
    finite = np.isfinite(fn).all(1)
    if not finite.all():                         # leftover degenerate faces
        if not finite.any():
            return None
        faces, fn = faces[finite], fn[finite]
    n0 = fn.sum(0)
    n0 /= max(np.linalg.norm(n0), 1e-12)
    if float((fn @ n0).min()) < math.cos(math.radians(NORMAL_TOL_DEG)):
        return None                              # curved (cylinder/cone)
    tris = np.asarray(mesh.faces, int)[faces]
    vid = np.unique(tris)
    pos = np.asarray(mesh.vertices, float)[vid]
    c = pos.mean(0)
    diag = float(np.linalg.norm(pos.max(0) - pos.min(0))) or 1.0
    if float(np.abs((pos - c) @ n0).max()) > PLANAR_TOL * diag:
        return None                              # not one plane
    cnt: Counter = Counter()
    for t in tris:
        for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            cnt[(int(min(e)), int(max(e)))] += 1
    if any(k > 2 for k in cnt.values()):
        return None                              # non-manifold seam
    bnd = [e for e, k in cnt.items() if k == 1]
    if not bnd:
        return None
    loops = _loops(bnd)
    if loops is None:
        return None
    u, v = face_basis(n0)
    where = {int(g): i for i, g in enumerate(vid.tolist())}
    rings = []
    for lp in loops:
        p = pos[[where[int(g)] for g in lp]]
        rings.append(np.stack([(p - c) @ u, (p - c) @ v], 1))
    rings.sort(key=lambda r: -abs(_area2(r)))
    outer = rings[0]
    holes = [r for r in rings[1:]
             if abs(_area2(r)) > HOLE_MIN_AREA * abs(_area2(outer))]
    # A tessellated curved wall marches on in sliver-thin columns, each
    # locally flat: they can't be told apart from a real planar face by
    # normals alone, but they ARE pathological in shape — one column of
    # the demo boss wall is 12 mm tall against a 0.17 mm chord (diagonal²
    # / area ~ 70). A genuine CAD planar face (plate top, box side,
    # filleted cap, even a slim 2x20 rib) stays compact. For every solid
    # this kernel can build (boxes, prisms, extrusions, cylinders,
    # revolves) curved-surface columns always blow the slenderness bound.
    area = abs(_area2(outer)) - sum(abs(_area2(r)) for r in holes)
    span = float(np.linalg.norm(outer.max(0) - outer.min(0)))
    if area <= 1e-9 or span * span > MAX_SLIMNESS * area:
        return None                              # a curved-surface column
    return dict(point=c, normal=n0, u=u, v=v, outer=outer, holes=holes)
