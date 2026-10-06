"""DXF / SVG → sketch ops: the reader side of profile import (M83).

Both formats land in one tiny intermediate representation — tuples a
sketch can speak directly:

    ("line",  (x0, y0), (x1, y1))
    ("circle",(cx, cy), radius)
    ("arc",   start, mid, end)              # three points, our grammar
    ("poly",  [(x, y), ...], closed)        # flattened chain
    ("ellipse",(cx, cy), rx, ry)

Straight lines, true circles and true circular arcs keep their exact
form.  Splines, elliptical arcs and beziers flatten to polylines —
honest approximations of what the file really contains.  Paper stuff
(text, hatches, dimension styles) is ignored: it is not profile.
SVG lives y-down; everything flips to sketch y-up on the way out.
"""
from __future__ import annotations

import math


def read(path: str) -> list:
    """Dispatch by extension; anything else is refused by name."""
    ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""
    if ext == "dxf":
        return read_dxf(path)
    if ext == "svg":
        return read_svg(path)
    raise ValueError(f"can't import {ext or 'that'} file — "
                     "sketch profiles come in as DXF or SVG")


# --------------------------------------------------------------------- DXF

def read_dxf(path: str) -> list:
    import ezdxf
    doc = ezdxf.readfile(path)
    ops: list = []
    for e in doc.modelspace():
        try:
            t = e.dxftype()
            if t == "LINE":
                s, g = e.dxf.start, e.dxf.end
                ops.append(("line", (s.x, s.y), (g.x, g.y)))
            elif t == "CIRCLE":
                ops.append(("circle", (e.dxf.center.x, e.dxf.center.y),
                            float(e.dxf.radius)))
            elif t == "ARC":
                a = _arc3(e.dxf.center.x, e.dxf.center.y,
                          float(e.dxf.radius), float(e.dxf.start_angle),
                          float(e.dxf.end_angle))
                ops.append(("arc", *a))
            elif t == "LWPOLYLINE":
                pts = [(float(x), float(y)) for x, y in e.get_points("xy")]
                if len(pts) >= 2:
                    ops.append(("poly", pts, bool(e.closed)))
            elif t == "POLYLINE":
                pts = [(float(v.dxf.location.x), float(v.dxf.location.y))
                       for v in e.vertices]
                if len(pts) >= 2:
                    ops.append(("poly", pts, bool(e.is_closed)))
            elif t == "SPLINE":
                pts = [(float(p[0]), float(p[1]))
                       for p in e.flattening(0.1)]
                if len(pts) >= 2:
                    ops.append(("poly", pts, bool(e.closed)))
            # TEXT / HATCH / DIMENSION / ... are paper, not profile
        except Exception:
            continue                          # one broken entity is not a
    return ops                                # reason to lose the drawing


def _arc3(cx, cy, r, a0, a1) -> tuple:
    """DXF centre/radius/angles (degrees CCW) → our three-point arc."""
    r0, r1 = math.radians(a0), math.radians(a1)
    if r1 <= r0:
        r1 += 2 * math.pi
    mid = (r0 + r1) / 2.0
    return ((cx + r * math.cos(r0), cy + r * math.sin(r0)),
            (cx + r * math.cos(mid), cy + r * math.sin(mid)),
            (cx + r * math.cos(r1), cy + r * math.sin(r1)))


# --------------------------------------------------------------------- SVG

def read_svg(path: str) -> list:
    from svgelements import (Circle as SvcCircle, CubicBezier, Ellipse as
                             SvcEllipse, Line as SvcLine, Move, Path, Rect,
                             SVG, Close, QuadraticBezier)
    from svgelements import Arc as SvcArc
    svg = SVG.parse(path)
    ops: list = []

    def flip(p):
        return (float(p.x), -float(p.y))

    def flatten(seg, floor=8):
        L = getattr(seg, "length", None)
        if callable(L):
            L = L()
        n = max(floor, min(256, int((L or 8.0) / 0.5)))
        return [flip(seg.point(i / n)) for i in range(n + 1)]

    def walk_path(p):
        start = last = None
        for s in p:
            try:
                if isinstance(s, Move):
                    start = last = s.end
                elif isinstance(s, SvcLine):
                    if s.start != s.end:
                        ops.append(("line", flip(s.start), flip(s.end)))
                    last = s.end
                elif isinstance(s, SvcCircle):
                    ops.append(("circle", (float(s.cx), -float(s.cy)),
                                float(s.rx)))
                elif isinstance(s, SvcArc) and \
                        abs(s.rx - s.ry) <= 1e-6 * max(s.rx, 1e-9):
                    a, m, b = (flip(s.point(t)) for t in (0.0, 0.5, 1.0))
                    ops.append(("arc", a, m, b))
                elif isinstance(s, (SvcArc, CubicBezier, QuadraticBezier)):
                    ops.append(("poly", flatten(s), False))
                elif isinstance(s, Close):
                    if start is not None and last is not None and \
                            start != last:
                        ops.append(("line", flip(last), flip(start)))
                    last = start
            except Exception:
                continue
    for el in svg.elements():
        try:
            if isinstance(el, SvcCircle):
                ops.append(("circle", (float(el.cx), -float(el.cy)),
                            float(el.rx)))
            elif isinstance(el, SvcEllipse):
                ops.append(("poly",
                            [flip(el.point(i / 64)) for i in range(64)],
                            True))
            elif isinstance(el, (Path, Rect)):
                walk_path(el if isinstance(el, Path) else Path(el))
        except Exception:
            continue
    return ops
