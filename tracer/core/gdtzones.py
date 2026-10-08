"""M150 prototype (LAB ONLY) — the first computed frames (pure core).

Zone arithmetic for GD&T rung 2: every law CLOSED-FORM on stored or
parametric quantities (contract gdt_rung2.md §2.2); association order
IS LAW — each expression written ONCE, parens pinned, goldens re-
derive in the test's written order.
"""
from __future__ import annotations

import math


def orientation_dev(extent: float, delta_deg: float) -> float:
    """Width between the parallel planes about the datum normal for a
    face tilted delta_deg off its nominal angle, over extent L:
    dev = L * sin(radians(|true - nominal|))."""
    return extent * math.sin(math.radians(abs(float(delta_deg))))


def true_position(dx: float, dy: float) -> float:
    """Diametral deviation of an axis from its true location: the
    factor 2 is the DIAMETRAL law (zone is Ø), never a rounding."""
    return 2.0 * math.sqrt(dx * dx + dy * dy)


def runout(offset: float) -> float:
    """Circular runout of a circle parallel-offset e from the datum
    axis: the radial readout sweeps the full annulus, 2e."""
    return 2.0 * abs(offset)


def profile_plane_dev(offset: float) -> float:
    """Distance of a point to the TE plane — the envelope is equal-
    bilateral t/2 each side; PASS iff dev <= t/2."""
    return abs(offset)


def profile_cyl_dev(dist_perp: float, radius: float) -> float:
    """Radial distance of a point to the TE cylinder (axis at o)."""
    return abs(dist_perp - radius)


def bonus_internal(d_act: float, d_mms: float) -> float:
    """Bonus tolerance of an INTERNAL feature (hole): the most-
    material size is the SMALLEST hole."""
    return d_act - d_mms


def bonus_external(d_act: float, d_mms: float) -> float:
    """Bonus of an EXTERNAL feature (pin): most material is the
    LARGEST pin."""
    return d_mms - d_act


def bonus_lmc_internal(d_act: float, d_lms: float) -> float:
    """LMC mirror of the internal bonus: tolerance GROWS as the
    hole shrinks toward least material."""
    return d_lms - d_act


def bonus_lmc_external(d_act: float, d_lms: float) -> float:
    """LMC mirror for an external feature."""
    return d_act - d_lms


def allowed(t: float, d_act: float, d_mms: float) -> float:
    """The pinned association order — float + is NOT associative:
    allowed = t + (d_act - d_mms)."""
    return t + (d_act - d_mms)


def virtual_internal(d_mms: float, t: float) -> float:
    """Gage (virtual condition) of an internal feature: VC = MMS - t."""
    return d_mms - t


def virtual_external(d_mms: float, t: float) -> float:
    """VC of an external feature: MMS + t."""
    return d_mms + t


def projected_dev(e: float, h: float, phi_deg: float) -> float:
    """Diametral deviation at the TOP of a projected zone of height h
    for an axis already offset e at the face and tilted phi_deg:
    dev(h) = 2.0 * (e + h * tan(radians(phi))). v1 ships the untilted
    law (phi = 0) — the tilt term rides the SAME expression."""
    return 2.0 * (e + h * math.tan(math.radians(phi_deg)))
