"""M121 — the interlock family: Boss · Snap Fit · Rest · Lip.

Fusion ships all four behind the paid Plastic extension (every help
page — SLD-BOSS, SLD-SNAP-FIT, SLD-REST, SLD-LIP — carries the "This
feature is part of an extension" banner, verified 2026-10-07). They are
pure 2D-profile + boolean work, exactly where our mesh kernel has no
B-rep disadvantage — so they ship here free, as first-class parametric
features, the way M120 shipped AutoConstrain free.

One grammar for all four kinds (mirroring the dialogs' shared shape:
Side 1 / Side 2, Flip, Offset Position, transparency-while-editing):

* the INTERFACE PLANE is local z = 0 (Fusion's sketch / rest plane);
* SIDE 1 is the body that CARRIES the feature and sits BELOW (−z);
  SIDE 2 is its mating partner ABOVE (+z);
* every kind returns up to two TOOLS: ``carry`` unions into side 1 and
  ``mate`` subtracts from side 2 (Rest is one-sided: mate only — it
  "forms a flat area" for a component to sit in);
* ``clearance`` is the maker's honest gap: printed parts are not
  injection mouldings, so mating faces carry a printable δ (0.2 mm is
  the classic FDM line-fit) — Fusion's dialogs expose the same idea as
  a clearance/offset per type.

Everything here is analytic: the tests pin tool volumes against
shoelace and cylinder arithmetic, and — the promise the family exists
for — every pair assembles with (side1 ∩ side2).volume ≈ 0.
"""
from __future__ import annotations

import math

from .geometry import Solid, rotation_about

KINDS = ("boss", "snapfit", "rest", "lip")
ROLES = ("carry", "mate")


def _frame(*, L, h, c):
    """Cantilever hook cross-section in (x, up): a block L×h with the
    leading-top corner chamfered by `c` — the slope the mating part
    rides up before the hook snaps past it."""
    pts = [(0.0, 0.0), (L, 0.0), (L, h - c), (L - c, h), (0.0, h)]
    return pts


def _ring(dx, dy, t, z0, dz):
    """Rectangular frame: outer dx×dy minus inner (dx−2t)×(dy−2t),
    spanning z ∈ [z0, z0+dz]. Centred on the origin in plan."""
    outer = Solid.box(dx, dy, dz).translated(
        (-dx / 2.0, -dy / 2.0, z0))
    inner_dz = dz + 2.0
    inner = Solid.box(dx - 2 * t, dy - 2 * t, inner_dz).translated(
        (-(dx - 2 * t) / 2.0, -(dy - 2 * t) / 2.0, z0 - 1.0))
    return outer.subtract(inner)


def _hook(*, L, w, h, c) -> Solid:
    """The extruded cross-section stood up so the profile lives in
    (x, z) and the width runs across y, centred: rotate +90° about X
    maps (x, u, s) → (x, −s, u)."""
    s = Solid.extrude(_frame(L=L, h=h, c=c), height=w)
    s = s.transformed(rotation_about((0, 0, 0), (1, 0, 0), math.pi / 2))
    return s.translated((0.0, w / 2.0, 0.0))


def tools(kind: str, *, clearance: float = 0.2, **p) -> dict:
    """Build the interlock tools for one kind; returns {"carry": Solid
    | None, "mate": Solid | None} in local coordinates (interface
    plane z = 0). Raises ValueError on an unknown kind or a nonsense
    parameter — a lip thinner than its clearance would promise an
    assembly that cannot exist, so we refuse instead of printing a
    collision."""
    if kind not in KINDS:
        raise ValueError(f"unknown interlock kind: {kind!r}")
    if clearance < 0:
        raise ValueError("clearance cannot be negative")

    if kind == "boss":
        d, h1, h2 = float(p["shaft_d"]), float(p["height1"]), \
            float(p["height2"])
        if d <= 0 or h1 <= 0 or h2 <= 0:
            raise ValueError("boss needs positive shaft_d, height1, "
                             "height2")
        r = d / 2.0
        if r <= clearance:
            raise ValueError("boss shaft thinner than its own clearance")
        carry = Solid.cylinder(r, h1 + h2).translated((0, 0, -h1))
        mate = Solid.cylinder(r + clearance, h2)
        return {"carry": carry, "mate": mate}

    if kind == "snapfit":
        L, w, h = float(p["length"]), float(p["width"]), \
            float(p["height"])
        c, e = float(p["lead"]), float(p["depth"])
        if min(L, w, h, e) <= 0 or c < 0 or c >= min(L, h):
            raise ValueError("snap fit needs L, w, h, depth > 0 and "
                             "0 <= lead < min(L, h)")
        carry = _hook(L=L, w=w, h=h, c=c)
        mate = Solid.box(L + 2 * clearance, w + 2 * clearance, e) \
            .translated((-clearance, -(w + 2 * clearance) / 2.0, 0.0))
        return {"carry": carry, "mate": mate}

    if kind == "rest":
        sd, hd, dep = float(p["seat_d"]), float(p["hole_d"]), \
            float(p["depth"])
        reach = float(p["reach"])
        if sd <= 0 or dep <= 0 or reach <= 0 or not 0 < hd < sd:
            raise ValueError("rest needs seat > hole > 0 and positive "
                             "depth / reach")
        # Stepped cutter: a seat pocket `dep` deep with a through-ish
        # pilot below it; what remains in the body is the flat annular
        # shelf the component rests on.
        seat = Solid.cylinder(sd / 2.0, dep).translated((0, 0, -dep))
        pilot = Solid.cylinder(hd / 2.0, reach).translated(
            (0, 0, -dep - reach))
        return {"carry": None, "mate": seat.union(pilot)}

    # kind == "lip" — the enclosure wedge: a rim bead on one body
    # riding inside an open channel on its partner.
    W, D, t = float(p["outer_w"]), float(p["outer_d"]), \
        float(p["thickness"])
    h, e = float(p["height"]), float(p["depth"])
    if min(W, D, h, e) <= 0 or t <= 0:
        raise ValueError("lip needs positive outline, thickness, "
                         "height, depth")
    gap = min(W, D) - 2 * t
    if gap <= 2 * clearance:
        raise ValueError("lip wall thinner than its own clearance")
    carry = _ring(W, D, t, 0.0, h)
    mate = _ring(W + 2 * clearance, D + 2 * clearance,
                 t + 2 * clearance, 0.0, e)
    return {"carry": carry, "mate": mate}
