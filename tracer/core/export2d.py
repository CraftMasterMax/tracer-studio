"""M92 — 2D profile export: DXF/SVG out of a sketch (M83 in reverse).

The maker loop's exit ramp: sketch in Tracer, send the profile to the
laser cutter / CNC / Inkscape.  Everything speaks the same op-tuple IR
M83 reads on the way in — DXF gets TRUE primitives (LINE, CIRCLE, ARC,
LWPOLYLINE via ezdxf), SVG gets polyline-approximated paths (every
consumer eats them; the DXF stays the exact one), millimetres, y up
(SVG's y-down is flipped on write, and M83's reader flips it back).
Construction geometry is scaffolding and stays home.
"""
from __future__ import annotations

import math


def sketch_ops(model) -> list:
    """A SketchModel -> the M83 IR. Arcs travel as their three defining
    points; ellipses flatten to closed polylines (64 segments)."""
    ops: list = []
    sk = model.sketch
    for l in sk.lines:
        if getattr(l, "construction", False):
            continue
        ops.append(("line", (float(l.a.x), float(l.a.y)),
                    (float(l.b.x), float(l.b.y))))
    for c in sk.circles:
        if getattr(c, "construction", False):
            continue
        ops.append(("circle", (float(c.c.x), float(c.c.y)), float(c.r)))
    for a in sk.arcs:
        if getattr(a, "construction", False):
            continue
        ops.append(("arc", (float(a.a.x), float(a.a.y)),
                    (float(a.m.x), float(a.m.y)),
                    (float(a.b.x), float(a.b.y))))
    for e in sk.ellipses:
        if getattr(e, "construction", False):
            continue
        pts = [(float(e.c.x + e.rx * math.cos(t)),
                float(e.c.y + e.ry * math.sin(t)))
               for t in (2 * math.pi * k / 64 for k in range(64))]
        ops.append(("poly", pts, True))
    return ops


def _circ3(p, q, r) -> tuple:
    """Circumcentre + radius through three points (never collinear:
    the arc tool refuses flat before minting)."""
    ax, ay = p
    bx, by = q
    cx, cy = r
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        mx, my = (ax + cx) / 2, (ay + cy) / 2
        rr = math.hypot(bx - mx, by - my)
        return (mx, my), max(rr, 1e-9)
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


def _arc_span(a0: float, am: float, a1: float) -> tuple:
    """ezdxf ARC is CCW start->end; pick the direction that passes the
    mid point (swapping endpoints is the same arc, just travel-free)."""
    ccw_mid = (am - a0) % (2 * math.pi)
    ccw_end = (a1 - a0) % (2 * math.pi)
    if ccw_mid < ccw_end:
        return a0, a1
    return a1, a0


def write_dxf(ops: list, path: str) -> int:
    """Exact primitives into a modelspace; returns the entity count,
    0 with no file minted for an empty profile."""
    if not ops:
        return 0
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for op in ops:
        t = op[0]
        if t == "line":
            msp.add_line(op[1], op[2])
        elif t == "circle":
            msp.add_circle(op[1], op[2])
        elif t == "arc":
            (c, r), (p, q, rr) = _circ3(op[1], op[2], op[3]), (op[1],
                                                          op[2], op[3])
            a0 = math.atan2(p[1] - c[1], p[0] - c[0])
            am = math.atan2(q[1] - c[1], q[0] - c[0])
            a1 = math.atan2(rr[1] - c[1], rr[0] - c[0])
            s, e = _arc_span(a0, am, a1)
            msp.add_arc(c, r, math.degrees(s) % 360.0,
                        math.degrees(e) % 360.0)
        elif t == "poly":
            msp.add_lwpolyline(op[1], format="xy", close=bool(op[2]))
        elif t == "text":
            # SM3: bend labels travel as TEXT entities — the shop
            # stamp rides the DXF like the dash lines do. (The one
            # word-op grammar point; PNG keeps painting its own.)
            msp.add_text(str(op[1]), dxfattribs={
                "insert": (float(op[2][0]), float(op[2][1])),
                "height": float(op[3])})
        else:
            continue
    doc.saveas(path)
    return len(ops)


def _flatten(op) -> list:
    """Sample any op to a point chain for the SVG path world."""
    t = op[0]
    if t == "line":
        return [op[1], op[2]]
    if t == "circle":
        (cx, cy), r = op[1], op[2]
        return [(cx + r * math.cos(2 * math.pi * k / 64),
                 cy + r * math.sin(2 * math.pi * k / 64))
                for k in range(65)]
    if t == "arc":
        (c, r), (p, q, rr) = _circ3(op[1], op[2], op[3]), (op[1],
                                                      op[2], op[3])
        a0 = math.atan2(p[1] - c[1], p[0] - c[0])
        am = math.atan2(q[1] - c[1], q[0] - c[0])
        a1 = math.atan2(rr[1] - c[1], rr[0] - c[0])
        ccw = ((am - a0) % (2 * math.pi)) < ((a1 - a0) % (2 * math.pi))
        sweep = ((a1 - a0) % (2 * math.pi)) if ccw else \
            -((a0 - a1) % (2 * math.pi))
        n = 32
        return [(c[0] + r * math.cos(a0 + sweep * k / n),
                 c[1] + r * math.sin(a0 + sweep * k / n))
                for k in range(n + 1)]
    if t == "poly":
        pts = list(op[1])
        if op[2] and pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        return pts
    return []


def write_svg(ops: list, path: str) -> int:
    """Polyline paths, mm units, y-up viewBox (we flip; M83 flips
    back).  Returns the entity count, 0 with no file for an empty
    profile."""
    if not ops:
        return 0
    chains = [_flatten(op) for op in ops]
    chains = [c for c in chains if len(c) >= 2]
    if not chains:
        return 0
    xs = [p[0] for c in chains for p in c]
    ys = [p[1] for c in chains for p in c]
    lo_x, hi_y = min(xs), max(ys)
    pad = 0.25 * max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    w = (max(xs) - min(xs)) + 2 * pad
    h = (max(ys) - min(ys)) + 2 * pad
    # M83's reader contract: a plain y-down file (viewBox "0 0 w h")
    # read back as (x, -y).  So we write a standard positive y-down
    # drawing: sx = x - minX + pad, sy = maxY - y + pad.  Re-import
    # through M83 then lands the shape translated + flipped exactly as
    # that importer treats ANY svg — spans and lengths preserved.
    # One user unit = one millimetre; DXF remains the exact-primitives
    # export with declared units.
    vb = f"0 0 {w:.4f} {h:.4f}"

    def pt(p):
        return f"{p[0] - lo_x + pad:.4f},{hi_y - p[1] + pad:.4f}"

    body = "\n".join(
        '  <path d="M ' + " L ".join(pt(p) for p in c) + '" '
        'fill="none" stroke="#000000" stroke-width="0.2"/>'
        for c in chains)
    svg = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
           f'width="{w:.4f}" height="{h:.4f}" '
           f'viewBox="{vb}">\n{body}\n</svg>\n')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    return len(chains)
