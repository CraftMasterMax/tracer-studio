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
                    Radius(arc, r), ArcMiddle(arc),
                    src="fillet")            # M164 R1: structural witness
    return arc


def corner_chamfer(model, l1: Line, l2: Line, d: float):
    """EQUAL DISTANCE Chamfer (the page's first door, M201 R24): both
    legs trim by the SAME d - "The second distance dimension is driven
    by the first distance dimension. If you update the first dimension,
    the second dimension will update as well, so that the two distances
    remain equal." Delegates the one truth to the Two Distance mouth.
    """
    return corner_chamfer_sides(model, l1, l2, d, d)


def corner_chamfer_sides(model, l1: Line, l2: Line, d1: float,
                         d2: float):
    """TWO DISTANCE Chamfer (the page's third door, M201 R24): "Bevels
    ... based on a different distance to each side" - leg 1 trims by
    d1, leg 2 by d2, and a new line joins the trim points. The side
    naming is OURS, declared (the page has no dialog to name legs
    with; the house law, mirroring the vendor's own pick-order sentence
    "The first distance value you specify applies to both sides...
    Any additional adjustments only apply to the side of the chamfer
    you are modifying"): d1 measures along the FIRST selection, d2
    along the second. A distance is a LENGTH here - both must be
    positive (unlike the offset rung's signed One Side law, this page
    puts the side in the geometry, not in the sign). All validation
    happens in _corner BEFORE any mutation: a refusal never leaves
    half-cut geometry. Returns the chamfer Line."""
    a, b = float(d1), float(d2)
    if a <= 0 or b <= 0:
        raise ValueError("Chamfer distances must be positive")
    P, o1, o2, u1, u2, len1, len2, theta = _corner(model, l1, l2, "chamfer")
    if a > len1 - 1e-6 or b > len2 - 1e-6:
        raise ValueError(f"Chamfer too large — the legs are {len1:.1f} and "
                         f"{len2:.1f} mm")
    t1 = (P.x + u1[0] * a, P.y + u1[1] * a)
    t2 = (P.x + u2[0] * b, P.y + u2[1] * b)
    Q = _trim(model, l1, l2, P, t1, t2)
    return model.sketch.line(P, Q)


def corner_chamfer_angle(model, l1: Line, l2: Line, d1: float,
                         angle_deg: float):
    """DISTANCE AND ANGLE Chamfer (the page's second door, M201 R24):
    "Bevels ... based on a single distance and an angle." The angle's
    meaning is OURS, declared (the page never glosses its manipulator):
    angle_deg is the angle the CHAMFER LINE makes with leg 1 AT THE
    FIRST TRIM POINT - so on a square corner 45 degrees is the ISOSCELES
    case (equal trims) and 90 would send the cut parallel to leg 2
    (never lands). In triangle P-T1-T2 the angles are phi at T1 and
    (pi - theta - phi) at T2, so the law of sines fixes the second
    leg's trim: d2 = d1 * sin(phi) / sin(theta + phi). The distance
    rides leg 1 under the SAME first-selection naming as
    corner_chamfer_sides. Validates BEFORE any mutation through
    _corner's own door."""
    a = float(d1)
    phi = math.radians(float(angle_deg))
    if a <= 0:
        raise ValueError("Chamfer distance must be positive")
    if not 0.0 < phi < math.pi:
        raise ValueError("The chamfer angle must be between 0 and 180 "
                         "degrees")
    P, o1, o2, u1, u2, len1, len2, theta = _corner(model, l1, l2, "chamfer")
    if theta + phi >= math.pi - 1e-9:
        raise ValueError("That angle leaves the chamfer no corner to cut "
                         "(the cut would run parallel to a leg)")
    b = a * math.sin(phi) / math.sin(theta + phi)
    return corner_chamfer_sides(model, l1, l2, a, b)


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
