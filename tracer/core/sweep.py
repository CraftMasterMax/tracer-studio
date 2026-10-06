"""Sweep: a circular profile along a drawn path (pipes, handles, rods).

v1 keeps the profile a circle — the one shape that sweeps with ZERO frame
ambiguity: every path station just gets a ring normal to the local tangent,
built on the sketch normal + in-plane normal (a rotation-minimising frame
for planar paths, so nothing rolls).  The path is the sketch's loose chain
of connected lines/arcs: open (capped tube) or a closed loop (endless
ring).  Stations land every ~15 degrees on arcs and at every corner, and
the rings stitch through the loft engine — exact volumes follow (a quarter
arc R sweeping radius r gives the Pappus result (theta/2)*2*pi*R*pi*r^2).
"""
from __future__ import annotations

import math

import numpy as np

from .geometry import Solid
from .loft import loft


def _wrap(a: float) -> float:
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


def _arc_samples(a, m, b, step_deg: float = 15.0) -> list:
    """2D points from a to b along the arc through bulge point m
    (~every step_deg degrees, both ends included)."""
    ax, ay = a
    mx, my = m
    bx, by = b
    d = 2.0 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    if abs(d) < 1e-9:                              # collinear: straight run
        return [a, b]
    a2, m2, b2 = ax * ax + ay * ay, mx * mx + my * my, bx * bx + by * by
    cx = (a2 * (my - by) + m2 * (by - ay) + b2 * (ay - my)) / d
    cy = (a2 * (bx - mx) + m2 * (ax - bx) + b2 * (mx - ax)) / d
    r = math.hypot(ax - cx, ay - cy)
    a0 = math.atan2(ay - cy, ax - cx)
    am = math.atan2(my - cy, mx - cx)
    a1 = math.atan2(by - cy, bx - cx)
    total = _wrap(am - a0) + _wrap(a1 - am)        # signed sweep through m
    n = max(2, int(math.ceil(abs(math.degrees(total)) / step_deg)))
    return [(cx + r * math.cos(a0 + total * k / n),
             cy + r * math.sin(a0 + total * k / n)) for k in range(n + 1)]


def path_chain(model, need_circle: bool = True) -> tuple[list, bool]:
    """Order a sketch's loose line/arc chain into one polyline:
    returns ([(x, y), ...], closed).  With need_circle (sweep) it
    requires exactly one construction-free circle (the profile);
    without (pattern-on-path) a circle in the sketch is an error.
    One connected non-branching chain of lines and arcs; every
    neighbour must share an endpoint.  Raises ValueError with a
    maker-readable reason."""
    from .sketch.entities import Arc
    circles = [c for c in model.sketch.circles
               if not getattr(c, "construction", False)]
    if need_circle and len(circles) != 1:
        raise ValueError("Sweep needs exactly one circle as the profile — "
                         f"the sketch has {len(circles)}")
    if not need_circle and circles:
        raise ValueError("Pattern-on-path wants only the path — delete the "
                         f"circle ({len(circles)}) and pick the feature in "
                         "the dialog instead")
    ents = [e for e in list(model.sketch.lines) + list(model.sketch.arcs)
            if not e.construction]
    if not ents:
        raise ValueError("Sweep needs a path: connected lines and/or arcs")
    adj: dict[int, list] = {}
    pt: dict[int, object] = {}
    for e in ents:
        for p, q in ((e.a, e.b), (e.b, e.a)):
            adj.setdefault(id(p), []).append((e, q))
            pt[id(p)] = p
    seed = next(iter(pt))
    seen, stack = {seed}, [seed]
    while stack:
        for _, q in adj[stack.pop()]:
            if id(q) not in seen:
                seen.add(id(q))
                stack.append(id(q))
    if len(seen) != len(pt):
        raise ValueError("the path must be ONE connected chain of lines/arcs")
    deg = {k: len(v) for k, v in adj.items()}
    if any(d > 2 for d in deg.values()):
        raise ValueError("the path cannot branch (an endpoint joins 3+ parts)")
    odd = [k for k, d in deg.items() if d == 1]
    closed = not odd
    if not closed and len(odd) != 2:
        raise ValueError("the path needs two free ends or must close on "
                         "itself")
    start = odd[0] if odd else seed
    pts = [(pt[start].x, pt[start].y)]
    used: set[int] = set()
    cur = start
    while True:
        nxt = next(((e, q) for e, q in adj[cur] if id(e) not in used), None)
        if nxt is None:
            break
        e, q = nxt
        used.add(id(e))
        if isinstance(e, Arc):
            samp = _arc_samples((e.a.x, e.a.y), (e.m.x, e.m.y), (e.b.x, e.b.y))
            if cur == id(e.b):
                samp = samp[::-1]
            pts.extend(samp[1:])
        else:
            pts.append((q.x, q.y))
        cur = id(q)
        if closed and cur == start:
            break
    if len(used) != len(ents):
        raise ValueError("the path is not a single walkable chain — every "
                         "line/arc must share an endpoint with its neighbour")
    return pts, closed


def _smooth_poly(pts, blend: float, closed: bool) -> np.ndarray:
    """Replace sharp corners with a quadratic-Bezier round (bends, not
    lobsters): a swept tube physically rounds a corner over a distance
    comparable to its diameter, and smooth stations keep every ring
    perpendicular to a real local tangent. Near-straight joints — and
    the dense 15-degree samples of arc paths — pass through untouched."""
    pts = np.asarray(pts, float)
    n = len(pts)
    if n < 3:
        return pts

    def corner(p0, p1, p2, out):
        v1, v2 = p1 - p0, p2 - p1
        L1, L2 = float(np.linalg.norm(v1)), float(np.linalg.norm(v2))
        u1, u2 = v1 / L1, v2 / L2
        theta = float(np.arccos(np.clip(float(np.dot(-u1, u2)), -1.0, 1.0)))
        if theta < math.radians(12):                  # nearly straight
            out.append(p1)
            return
        t = min(blend, 0.45 * L1, 0.45 * L2)
        a, b = p1 - u1 * t, p1 + u2 * t
        k = max(2, int(math.ceil(math.degrees(theta) / 15.0)))
        s = np.linspace(0.0, 1.0, k + 1)[:, None]
        bez = (1 - s) ** 2 * a + 2 * (1 - s) * s * p1 + s ** 2 * b
        out.extend(bez[1:])                           # a already present

    out: list = []
    if closed:
        for i in range(n):
            corner(pts[i - 1], pts[i], pts[(i + 1) % n], out)
    else:
        out.append(pts[0])
        for i in range(1, n - 1):
            corner(pts[i - 1], pts[i], pts[i + 1], out)
        out.append(pts[-1])
    return np.asarray(out, float)


def sample_polyline(pts, count: int) -> list:
    """`count` points equally spaced by arc length over a 2D polyline,
    first and last included (pattern-on-path stations).  Degenerate
    (zero-length) paths return the single point repeated.  Rigid
    placement later preserves these spacings into 3D."""
    pts = np.asarray(pts, float)
    if pts.shape[0] < 2:
        raise ValueError("the path is too short to pattern along")
    n = max(2, int(count))
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    total = float(seg.sum())
    if total < 1e-9:
        return [tuple(float(t) for t in pts[0])] * n
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    targets = np.linspace(0.0, total, n)
    out = []
    for t in targets:
        k = int(np.clip(np.searchsorted(cum, t, side="right") - 1,
                        0, len(seg) - 1))
        f = 0.0 if seg[k] < 1e-12 else (t - cum[k]) / seg[k]
        p = pts[k] + (pts[k + 1] - pts[k]) * f
        out.append((float(p[0]), float(p[1])))
    return out


def sweep_tube(path, radius: float, closed: bool, ring: int = 32) -> Solid:
    """Solid tube of `radius` around a 2D polyline (sketch-plane coords):
    circular stations normal to the local tangent, stitched by the loft
    engine.  Closed paths become endless rings."""
    r = float(radius)
    pts = np.asarray(path, float)[:, :2]
    if pts.shape[0] < 2:
        raise ValueError("the path is too short to sweep")
    if closed and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    if closed and pts.shape[0] < 3:
        raise ValueError("a closed path needs at least three stations")
    pts = _smooth_poly(pts, 2.5 * r, closed)
    if closed:
        pts = np.vstack([pts, pts[:1]])            # wrap for the tangents
    t = np.zeros((len(pts), 2))
    t[1:-1] = pts[2:] - pts[:-2]
    t[0], t[-1] = pts[1] - pts[0], pts[-1] - pts[-2]
    ln = np.linalg.norm(t, axis=1)
    if float(ln.min()) < 1e-9:
        raise ValueError("the path has repeated points")
    t /= ln[:, None]
    if closed:
        pts, t = pts[:-1], t[:-1]            # wrap existed only for tangents
    th = np.linspace(0.0, 2.0 * np.pi, ring, endpoint=False)
    Z = np.array([0.0, 0.0, 1.0])                  # sketch normal: constant
    secs = []
    for p, tt in zip(pts, t):
        u = np.array([-tt[1], tt[0], 0.0])         # in-plane normal
        c = np.array([p[0], p[1], 0.0])
        secs.append(c + float(radius) * (np.cos(th)[:, None] * Z
                                         + np.sin(th)[:, None] * u))
    return loft(secs, n=48, caps=not closed, loop=closed)
