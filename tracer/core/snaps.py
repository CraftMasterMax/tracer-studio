"""Object snaps — the sketch magnet, as pure geometry (M120).

Fusion has no snap settings dialog [ui_sketchmode V]: the magnets are
implicit and typed.  This module is the same doctrine made explicit —
every candidate the cursor could mean, each with a kind, resolved by
nearest-wins with a documented tie-break.  Closed-form math only: our
sketch language is lines/circles/arcs/ellipses, so no library and no
approximations are needed [snap_geometry §2].  The editor owns
screen↔world and reuse of existing Points; this owns the candidates.

Resolution: semantic kinds (everything but on-entity) win as a class —
inside the class, nearest wins, and ties break by kind:
    endpoint > intersection > midpoint > quadrant > center >
    reference > origin > on-entity (the last-resort fallback)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .sketch.entities import Arc, Circle, Ellipse, Line, Point

KINDS = ("endpoint", "intersection", "midpoint", "quadrant", "center",
         "reference", "origin", "grid", "onentity")
PRIORITY = {k: i for i, k in enumerate(KINDS)}

_EPS = 1e-12


@dataclass
class Snap:
    x: float
    y: float
    kind: str
    pt: Point | None = None      # existing Point object safe to REUSE
    entity: object = None        # what it lies on (on-entity bindings)
    entity2: object = None       # second curve (line x line intersections)
    dist: float = 0.0            # world distance from the cursor

    def __post_init__(self):
        if not self.dist:
            self.dist = 0.0      # callers measure; tests may not care


def _circumference(a: Point, m: Point, b: Point):
    """Centre + radius of the circle through three points (arc data)."""
    ax, ay, bx, by, cx, cy = a.x, a.y, b.x, b.y, m.x, m.y
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < _EPS:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy, math.hypot(ax - ux, ay - uy)


def _arc_span(a: Point, m: Point, b: Point, cx: float, cy: float):
    """(start, sweep) radians, a -> b through m (always the m side)."""
    def ang(p):
        return math.atan2(p.y - cy, p.x - cx)
    a0, am, a1 = ang(a), ang(m), ang(b)
    ccw = ((am - a0) % (2 * math.pi)) < ((a1 - a0) % (2 * math.pi))
    if ccw:
        sweep = (a1 - a0) % (2 * math.pi)
    else:
        sweep = -((a0 - a1) % (2 * math.pi))
    return a0, sweep


def _in_arc(ang: float, a0: float, sweep: float) -> bool:
    rel = (ang - a0) % (2 * math.pi) if sweep > 0 else (a0 - ang) % (2 * math.pi)
    return rel <= abs(sweep) + 1e-9


def _on_segment(px, py, a: Point, b: Point):
    vx, vy = b.x - a.x, b.y - a.y
    L2 = vx * vx + vy * vy
    if L2 < _EPS:
        return a.x, a.y, 0.0
    t = max(0.0, min(1.0, ((px - a.x) * vx + (py - a.y) * vy) / L2))
    return a.x + t * vx, a.y + t * vy, t


# ---- per-kind candidate generators ------------------------------------------

def _endpoints(sk, out):
    # centres and arc-mids have their OWN kinds — do not label them
    # "endpoint" just because they are Points in sk.points
    special = set()
    for c in sk.circles:
        special.add(id(c.c))
    for e in sk.ellipses:
        special.add(id(e.c))
    for a in sk.arcs:
        special.add(id(a.m))
    for l in sk.lines:
        for p in (l.a, l.b):
            out.append(Snap(p.x, p.y, "endpoint", pt=p, entity=l))
    for a in sk.arcs:
        for p in (a.a, a.b):
            out.append(Snap(p.x, p.y, "endpoint", pt=p, entity=a))
    for p in sk.points:
        if id(p) not in special:
            out.append(Snap(p.x, p.y, "endpoint", pt=p))


def _centers(sk, out):
    for c in sk.circles:
        out.append(Snap(c.c.x, c.c.y, "center", pt=c.c, entity=c))
    for e in sk.ellipses:
        out.append(Snap(e.c.x, e.c.y, "center", pt=e.c, entity=e))
    for a in sk.arcs:
        geo = _circumference(a.a, a.m, a.b)
        if geo:
            # the centre is NOT a stored Point of an arc — mint it
            out.append(Snap(geo[0], geo[1], "center", entity=a))


def _midpoints(sk, out):
    for l in sk.lines:
        out.append(Snap((l.a.x + l.b.x) / 2, (l.a.y + l.b.y) / 2,
                        "midpoint", entity=l))
    for a in sk.arcs:                       # arc mid IS a Point — reuse
        out.append(Snap(a.m.x, a.m.y, "midpoint", pt=a.m, entity=a))


def _quadrants(sk, out):
    for c in sk.circles:
        for dx, dy in ((c.r, 0), (-c.r, 0), (0, c.r), (0, -c.r)):
            out.append(Snap(c.c.x + dx, c.c.y + dy, "quadrant", entity=c))
    for e in sk.ellipses:
        for dx, dy in ((e.rx, 0), (-e.rx, 0), (0, e.ry), (0, -e.ry)):
            out.append(Snap(e.c.x + dx, e.c.y + dy, "quadrant", entity=e))


def _intersections(sk, out):
    def near_arc(a, x, y):
        geo = _circumference(a.a, a.m, a.b)
        if not geo:
            return False
        cx, cy, _r = geo
        return _in_arc(math.atan2(y - cy, x - cx), *_arc_span(a.a, a.m, a.b,
                                                              cx, cy))

    curves = []                              # (entity, kind-for-math)
    for l in sk.lines:
        curves.append((l, "line"))
    for c in sk.circles:
        curves.append((c, "circle"))
    for a in sk.arcs:
        curves.append((a, "arc"))
    for i in range(len(curves)):
        for j in range(i + 1, len(curves)):
            (e1, k1), (e2, k2) = curves[i], curves[j]
            pts = []
            if k1 == "line" and k2 == "line":
                x1, y1, x2, y2 = e1.a.x, e1.a.y, e1.b.x, e1.b.y
                x3, y3, x4, y4 = e2.a.x, e2.a.y, e2.b.x, e2.b.y
                den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
                if abs(den) > _EPS:
                    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
                    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
                    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
                        pts.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
            elif (k1 == "line") != (k2 == "line"):     # line × circle/arc
                ln = e1 if k1 == "line" else e2
                cd = e2 if k1 == "line" else e1
                arc = cd if isinstance(cd, Arc) else None
                geo = _circumference(cd.a, cd.m, cd.b) if arc \
                    else (cd.c.x, cd.c.y, cd.r)
                if geo:
                    cx, cy, r = geo
                    dx, dy = ln.b.x - ln.a.x, ln.b.y - ln.a.y
                    fx, fy = ln.a.x - cx, ln.a.y - cy
                    A = dx * dx + dy * dy
                    if A > _EPS:
                        B = 2 * (fx * dx + fy * dy)
                        C = fx * fx + fy * fy - r * r
                        disc = B * B - 4 * A * C
                        if disc >= 0:
                            for sgn in ((1, -1) if disc > _EPS else (0,)):
                                t = (-B + sgn * math.sqrt(disc)) / (2 * A)
                                if -1e-9 <= t <= 1 + 1e-9:
                                    x, y = ln.a.x + t * dx, ln.a.y + t * dy
                                    if arc is None or near_arc(arc, x, y):
                                        pts.append((x, y))
            else:                            # circle/arc x circle/arc
                g1 = (e1.c.x, e1.c.y, e1.r) if isinstance(e1, Circle) \
                    else _circumference(e1.a, e1.m, e1.b)
                g2 = (e2.c.x, e2.c.y, e2.r) if isinstance(e2, Circle) \
                    else _circumference(e2.a, e2.m, e2.b)
                if g1 and g2:
                    (x1, y1, r1), (x2, y2, r2) = g1, g2
                    d = math.hypot(x2 - x1, y2 - y1)
                    if d > _EPS and d <= r1 + r2 + 1e-9 and \
                            d >= abs(r1 - r2) - 1e-9:
                        aa = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
                        h2 = r1 * r1 - aa * aa
                        h = math.sqrt(max(h2, 0.0))
                        xm, ym = x1 + aa * (x2 - x1) / d, \
                            y1 + aa * (y2 - y1) / d
                        rx, ry = (-(y2 - y1) / d * h, (x2 - x1) / d * h)
                        for x, y in ((xm + rx, ym + ry), (xm - rx, ym - ry)):
                            ok = True
                            for e, g in ((e1, g1), (e2, g2)):
                                if isinstance(e, Arc) and not _in_arc(
                                        math.atan2(y - g[1], x - g[0]),
                                        *_arc_span(e.a, e.m, e.b, g[0], g[1])):
                                    ok = False
                            pts.append((x, y))
                            if h < 1e-9:
                                break
                            if not ok:
                                pts.pop()
            for x, y in pts:
                out.append(Snap(x, y, "intersection", entity=e1, entity2=e2))


def _on_entity(sk, x, y, out):
    for l in sk.lines:
        px, py, _t = _on_segment(x, y, l.a, l.b)
        out.append(Snap(px, py, "onentity", entity=l))
    for c in sk.circles:
        d = math.hypot(x - c.c.x, y - c.c.y)
        k = (c.r / d) if d > _EPS else 0.0
        out.append(Snap(c.c.x + (x - c.c.x) * k, c.c.y + (y - c.c.y) * k,
                        "onentity", entity=c))
    for a in sk.arcs:
        geo = _circumference(a.a, a.m, a.b)
        if not geo:
            continue
        cx, cy, r = geo
        a0, sw = _arc_span(a.a, a.m, a.b, cx, cy)
        ang = math.atan2(y - cy, x - cx)
        if _in_arc(ang, a0, sw):
            out.append(Snap(cx + r * math.cos(ang), cy + r * math.sin(ang),
                            "onentity", entity=a))
        else:                                # nearest endpoint of the span
            for p in (a.a, a.b):
                out.append(Snap(p.x, p.y, "onentity", entity=a, pt=p))
    for e in sk.ellipses:                    # nearest by coarse + Newton
        best, bd = None, float("inf")
        for s in range(64):
            t = 2 * math.pi * s / 64
            px, py = e.c.x + e.rx * math.cos(t), e.c.y + e.ry * math.sin(t)
            d = (px - x) ** 2 + (py - y) ** 2
            if d < bd:
                best, bd = t, d
        t = best
        for _ in range(12):                  # Newton on f(t)=pos(t)-q · pos'
            px, py = e.c.x + e.rx * math.cos(t), e.c.y + e.ry * math.sin(t)
            dx, dy = px - x, py - y
            t1x, t1y = -e.rx * math.sin(t), e.ry * math.cos(t)
            t2x, t2y = -e.rx * math.cos(t), -e.ry * math.sin(t)
            num = dx * t1x + dy * t1y
            den = t1x * t1x + t1y * t1y + dx * t2x + dy * t2y
            if abs(den) < _EPS:
                break
            t -= num / den
        px, py = e.c.x + e.rx * math.cos(t), e.c.y + e.ry * math.sin(t)
        out.append(Snap(px, py, "onentity", entity=e))


def candidates(sk, x: float, y: float, tol: float, extra=(), skip=None):
    """All snaps within `tol` WORLD units of (x, y), nearest first.
    extra: (px, py, kind) tuples for origin/references/grid — minted.
    skip: a Point that must not magnetize (the drag's own endpoint)."""
    out: list[Snap] = []
    _endpoints(sk, out)
    _centers(sk, out)
    _midpoints(sk, out)
    _quadrants(sk, out)
    _intersections(sk, out)
    _on_entity(sk, x, y, out)
    for px, py, kind in extra:
        out.append(Snap(px, py, kind))
    if skip is not None:
        out = [s for s in out if s.pt is not skip]
    for s in out:
        s.dist = math.hypot(s.x - x, s.y - y)
    hits = [s for s in out if s.dist <= tol]
    # Typed magnets beat the on-entity fallback as a CLASS.  Plain
    # nearest-wins lets a curve point 0.07 away shadow an intersection
    # 0.3 away — found in M120 validation; every CAD gives semantic
    # snaps the larger capture.  [refines snap_geometry "nearest wins"]
    sem = [s for s in hits if s.kind != "onentity"]
    pool = sem or [s for s in hits if s.kind == "onentity"]
    seen, uniq = set(), []
    for s in pool:
        key = (id(s.pt), s.kind) if s.pt is not None \
            else (round(s.x, 6), round(s.y, 6), s.kind)
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    uniq.sort(key=lambda s: (round(s.dist * 1e9), PRIORITY[s.kind]))
    return uniq


def best(sk, x, y, tol, extra=(), skip=None):
    hits = candidates(sk, x, y, tol, extra=extra, skip=skip)
    return hits[0] if hits else None


def autolink(s: Snap, pt: Point) -> list:
    """The constraints the snap IMPLIES [snap_geometry §4]: the drop ON
    an entity binds the point so it survives a rebuild — the live, free
    twin of their premium batch AutoConstrain.  Reused Points (s.pt)
    need nothing: identity is already coincidence."""
    from .sketch.constraints import Fixed, Midpoint, PointOnCircle, PointOnLine

    def carrier(e):
        if isinstance(e, Line):
            return PointOnLine(pt, e)
        if isinstance(e, (Circle, Arc)):
            return PointOnCircle(pt, e)      # works for arcs too
        return None                           # ellipse: no carrier yet

    if s.kind == "onentity" and s.entity is not None:
        c = carrier(s.entity)
        return [c] if c else []
    if s.kind == "intersection":              # ride BOTH curves: pinned,
        out = []                              # and tracks either edit
        for e in (s.entity, s.entity2):
            c = carrier(e)
            if c is not None:
                out.append(c)
        return out
    if s.kind == "quadrant":
        c = carrier(s.entity)
        return [c] if c else []               # ellipse quadrant: free mint
    if s.kind == "midpoint" and isinstance(s.entity, Line):
        return [Midpoint(p=pt, line=s.entity)]
    if s.kind == "center" and isinstance(s.entity, Arc):
        return [Fixed(p=pt, x=s.x), Fixed(p=pt, y=s.y)]
    return []
