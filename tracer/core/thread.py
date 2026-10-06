"""Threads as real geometry (M49): the helical groove a tap cuts.

A thread groove is a round-bottom wire swept along a helix — the same
loft engine the sweep pipe uses, but the path is 3D so the ring frame is
analytic: for a helix of constant lead the radial direction, the tangent
and their cross product form a continuous (roll-free) frame with no
number-marching.  The wire straddles the wall: it bites a little into the
drilled core so the groove joins the hole cleanly, and reaches out to the
ISO major radius.  A tap-drilled hole leaves a practical thread depth of
pitch/2 (major - tap-drill ~= pitch), the ~85% engagement a maker taps by
hand.

The table is ISO metric coarse with the maker's standard tap-drill rule
(major - pitch), the sizes a printed fastener or a tapped aluminium
bracket actually uses.
"""
from __future__ import annotations

import math

import numpy as np

from .geometry import Solid
from .loft import loft

# name -> (pitch mm, tap-drill diameter mm), ISO metric coarse
ISO_COARSE = {
    "M3": (0.50, 2.50),
    "M4": (0.70, 3.30),
    "M5": (0.80, 4.20),
    "M6": (1.00, 5.00),
    "M8": (1.25, 6.80),
    "M10": (1.50, 8.50),
    "M12": (1.75, 10.20),
}

H_RATIO = 0.61343           # ISO fundamental thread depth / pitch (ref)


def helix_groove(core_radius: float, pitch: float, length: float,
                 ring: int = 24, per_turn: int = 48,
                 z_from: float = 0.0) -> Solid:
    """Cutter for an internal thread: a helical wire around the +Z axis
    whose groove opens from `core_radius` out to the ISO major radius
    (core + pitch/2 for a tap-drilled hole).  Runs from `z_from` up to
    `z_from + length`; ends stick out one pitch on the far side so
    booleans never leave a stub seam.  Returns a watertight Solid,
    origin-axis aligned."""
    p = float(pitch)
    if p <= 0 or length <= 1.2 * p:
        raise ValueError("thread too short for its pitch")
    r_core = float(core_radius)
    outer = r_core + 0.5 * p             # groove root lands on the crest
    inner = r_core - 0.10 * p            # bite in so the groove joins the wall
    rw = (outer - inner) / 2.0           # wire radius  = 0.30 pitch
    rc = (outer + inner) / 2.0           # wire-centre radius = core + 0.2 pitch
    z0 = float(z_from) - 1.5 * p         # start below the surface
    z1 = float(z_from) + length
    turns = (z1 - z0) / p
    n_st = max(32, int(per_turn * turns) + 1)
    zs = np.linspace(z0, z1, n_st)
    th = np.linspace(0.0, 2.0 * np.pi * (z1 - z0) / p, n_st)
    phi = np.linspace(0.0, 2.0 * np.pi, ring, endpoint=False)
    cphi, sphi = np.cos(phi)[:, None], np.sin(phi)[:, None]
    secs = []
    for z, a in zip(zs, th):
        ca, sa = math.cos(a), math.sin(a)
        c = np.array([rc * ca, rc * sa, z])
        t = np.array([-rc * sa, rc * ca, p / (2.0 * math.pi)])
        t /= np.linalg.norm(t)
        rad = np.array([ca, sa, 0.0])
        u = rad - float(rad @ t) * t     # in-plane "outward" axis
        u /= np.linalg.norm(u)
        v = np.cross(t, u)
        secs.append(c + rw * (cphi * u + sphi * v))
    return loft(secs, n=max(ring, 24))
