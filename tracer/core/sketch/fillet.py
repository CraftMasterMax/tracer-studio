"""Corner fillet & chamfer: trim two adjacent lines and stitch an arc
or a flat cut in between.

Pure construction math + constraint bookkeeping. A fillet's arc carries
Tangent to both lines, Radius r, and ArcMiddle to pin its bulge point,
so the solver keeps it tangent through any drag. A chamfer is the
structural trim Fusion performs — topologically locked by its shared
endpoints, dimensioned later by the user if they care.

    P•────────E1                    P=T1•╲        ╱•T2────E1        ╲
     ╲          ╲   ─────────►        (l1) ╲  __╳__  ╱ (l2)          ╲
      ╲          ╲                          ╲──C──╱   r = arc radius   ╲
       ╲                                     (bulge)
        E2                                  tan = r/tan(θ/2) along each leg

Constraints on the original corner point P survive by construction: P
IS REUSED as the first tangent point, so dimensions/fixes that referred
to the corner keep referring to the (new) trim end of line 1 — exactly
what Fusion's fillet does to the trimmed leg.
"""
from __future__ import annotations

import math

from .entities import Line
from .constraints import Radius, ArcMiddle, make_tangent


def corner_fillet(model, l1: Line, l2: Line, r: float):
    """Apply a radius-r fillet to the shared corner of l1 and l2.
    Returns the new Arc. Raises ValueError with a user-facing reason."""
    if r <= 0:
        raise ValueError("Fillet radius must be positive")
    P, o1, o2, u1, u2, len1, len2, theta = _corner(model, l1, l2, "fillet")
    tan_len = r / math.tan(theta / 2.0)
    if tan_len > len1 - 1e-6 or tan_len > len2 - 1e-6:
        raise ValueError(f"Radius too large — the legs are {len1:.1f} and "
                         f"{len2:.1f} mm")
    half = (u1[0] + u2[0], u1[1] + u2[1])
    hl = math.hypot(*half)
    bis = (half[0] / hl, half[1] / hl)          # interior bisector

    t1 = (P.x + u1[0] * tan_len, P.y + u1[1] * tan_len)
    t2 = (P.x + u2[0] * tan_len, P.y + u2[1] * tan_len)
    cd = r / math.sin(theta / 2.0)              # |PC|
    cen = (P.x + bis[0] * cd, P.y + bis[1] * cd)
    bulge = (cen[0] - bis[0] * r, cen[1] - bis[1] * r)   # near-corner point

    Q = _trim(model, l1, l2, P, t1, t2)
    M = model.point(*bulge)
    arc = model.sketch.arc(P, M, Q)
    model.constrain(make_tangent(l1, arc), make_tangent(l2, arc),
                    Radius(arc, r), ArcMiddle(arc))
    return arc


def corner_chamfer(model, l1: Line, l2: Line, d: float):
    """Cut the shared corner flat: both legs trim by d, a new line joins
    the trim points. Returns the chamfer Line."""
    if d <= 0:
        raise ValueError("Chamfer distance must be positive")
    P, o1, o2, u1, u2, len1, len2, theta = _corner(model, l1, l2, "chamfer")
    if d > len1 - 1e-6 or d > len2 - 1e-6:
        raise ValueError(f"Chamfer too large — the legs are {len1:.1f} and "
                         f"{len2:.1f} mm")
    t1 = (P.x + u1[0] * d, P.y + u1[1] * d)
    t2 = (P.x + u2[0] * d, P.y + u2[1] * d)
    Q = _trim(model, l1, l2, P, t1, t2)
    return model.sketch.line(P, Q)


# ---- shared plumbing ---------------------------------------------------------

def _corner(model, l1, l2, verb):
    """Validate the corner exists and is fillet/chamfer-able, returning
    (P, o1, o2, u1, u2, len1, len2, theta). All raises happen here, BEFORE
    any mutation, so a refusal never leaves half-cut geometry."""
    shared = [p for p in (l1.a, l1.b) if p is l2.a or p is l2.b]
    if len(shared) != 1:
        raise ValueError(
            f"Fillet/chamfer needs two lines sharing exactly one corner "
            f"(extend them to meet first)")
    P = shared[0]
    users = sum(1 for e in (model.sketch.lines + model.sketch.arcs)
                if any(p is P for p in _endpoints(e)))
    if users != 2:
        raise ValueError("That corner is shared by more geometry — "
                         f"{verb} only joins two lines")
    o1 = l1.b if l1.a is P else l1.a            # far ends
    o2 = l2.b if l2.a is P else l2.a
    d1x, d1y = o1.x - P.x, o1.y - P.y
    d2x, d2y = o2.x - P.x, o2.y - P.y
    len1 = math.hypot(d1x, d1y)
    len2 = math.hypot(d2x, d2y)
    if len1 < 1e-9 or len2 < 1e-9:
        raise ValueError("Degenerate line at that corner")
    u1 = (d1x / len1, d1y / len1)
    u2 = (d2x / len2, d2y / len2)
    cos_t = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
    theta = math.acos(cos_t)
    if theta < math.radians(2) or math.pi - theta < math.radians(2):
        raise ValueError("Lines are (near-)parallel — no corner to " + verb)
    return P, o1, o2, u1, u2, len1, len2, theta


def _trim(model, l1, l2, P, t1, t2):
    """P slides to tangent point 1 (keeping every constraint that
    referenced the corner attached to leg 1), leg 2 gets a fresh shared
    endpoint at t2. Returns the new point Q."""
    P.x, P.y = t1
    Q = model.point(*t2)
    if l2.a is P:
        l2.a = Q
    else:
        l2.b = Q
    return Q


def _endpoints(e):
    return (e.a, e.m, e.b) if hasattr(e, "m") else (e.a, e.b)
