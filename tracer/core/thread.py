"""Threads as real geometry (M49/M49b): the helical groove a tap or a
die cuts.

A thread groove is a round-bottom wire swept along a helix — the same
loft engine the sweep pipe uses, but the path is 3D so the ring frame is
analytic: for a helix of constant lead the radial direction, the tangent
and their cross product form a continuous (roll-free) frame with no
number-marching.  The wire straddles the wall: it bites a little into
the material so the groove joins the surface cleanly, and reaches to
pitch/2 deep — the practical thread depth a maker taps or dies by hand.
Internal grooves cut outward from a drilled core to the ISO major
radius; external ridges cut inward from a turned boss to its minor.

The table is ISO metric coarse with the maker's standard tap-drill rule
(major - pitch), the sizes a printed fastener or a tapped aluminium
bracket actually uses.

fit_cylinder closes the loop on the external side: it recognises a
cylindrical patch of the pick mesh (axis, centre, radius, height) so
picking a boss face and choosing M-size is all a bolt needs.
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


def coarse_size(pitch: float) -> str:
    """Which M size carries this ISO coarse pitch (pitches are unique
    across the table). Lets a legacy hole that stores only its pitch
    still answer with a designation; '' when nothing matches
    (fine pitches the coarse dialog never offered)."""
    for name, (p, _) in ISO_COARSE.items():
        if abs(p - float(pitch)) < 1e-9:
            return name
    return ""


def designation(size: str, pitch: float, internal: bool = True,
                cls: str = "") -> str:
    """ISO metric thread designation (M128): the coarse pitch is
    omitted ("M8-6H"), a fine one is written out ("M8x1-6H"); the
    tolerance class defaults to 6H internal / 6g external. Classes
    are CODES, not measured numbers — the fastener-data citation law
    (M123) is about tables, so formatting lives right here."""
    size = size or coarse_size(pitch)
    if not size:
        return ""
    coarse = ISO_COARSE[size][0]
    shown = "" if abs(float(pitch) - coarse) < 1e-9 else f"x{float(pitch):g}"
    return f"{size}{shown}-{cls or ('6H' if internal else '6g')}"

H_RATIO = 0.61343           # ISO fundamental thread depth / pitch (ref)


def _helix_wire(rc: float, rw: float, pitch: float, z0: float, z1: float,
                ring: int, per_turn: int) -> Solid:
    """A wire of circular section (radius rw) whose centre traces a
    helix of radius rc and lead `pitch` about the +Z axis, z from z0 to
    z1.  Watertight, origin-axis aligned."""
    p = float(pitch)
    turns = (z1 - z0) / p
    n_st = max(32, int(per_turn * turns) + 1)
    zs = np.linspace(z0, z1, n_st)
    th = np.linspace(0.0, 2.0 * np.pi * turns, n_st)
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


def helix_groove(core_radius: float, pitch: float, length: float,
                 ring: int = 24, per_turn: int = 48,
                 z_from: float = 0.0) -> Solid:
    """Cutter for an INTERNAL thread: cuts from `core_radius` outward to
    the ISO major radius (core + pitch/2 for a tap-drilled hole).  Runs
    from `z_from` up to `z_from + length`; the opening end sticks out a
    pitch so the boolean leaves no stub seam."""
    p = float(pitch)
    if p <= 0 or length <= 1.2 * p:
        raise ValueError("thread too short for its pitch")
    r_core = float(core_radius)
    outer = r_core + 0.5 * p             # groove root lands on the crest
    inner = r_core - 0.10 * p            # bite in so the groove joins the wall
    rw = (outer - inner) / 2.0           # wire radius  = 0.30 pitch
    rc = (outer + inner) / 2.0           # wire-centre radius = core + 0.2 pitch
    return _helix_wire(rc, rw, p, float(z_from) - 1.5 * p,
                       float(z_from) + length, ring, per_turn)


def helix_ridge(major_radius: float, pitch: float, length: float,
                ring: int = 24, per_turn: int = 48,
                z_from: float = 0.0) -> Solid:
    """Cutter for an EXTERNAL thread (a bolt): cuts a helical groove
    inward from `major_radius` (the turned boss surface) down to the
    minor (major - pitch/2), both ends sticking out so the thread runs
    cleanly off the top and bottom of the threaded length."""
    p = float(pitch)
    if p <= 0 or length <= 1.2 * p:
        raise ValueError("thread too short for its pitch")
    r_maj = float(major_radius)
    outer = r_maj + 0.10 * p             # embed past the crest
    inner = r_maj - 0.5 * p              # groove floor = minor radius
    if inner <= 0.1:
        raise ValueError("boss too thin: the thread would cut the core away")
    rw = (outer - inner) / 2.0
    rc = (outer + inner) / 2.0
    return _helix_wire(rc, rw, p, float(z_from) - 1.5 * p,
                       float(z_from) + length + 1.5 * p, ring, per_turn)


def fit_cylinder(points, normals) -> dict | None:
    """Recognise a cylindrical patch: least-squares axis from the normal
    spread (normals of a cylinder are all perpendicular to its axis),
    then a Kasa circle fit to the points projected onto the plane normal
    to it.  Returns {'axis','point','radius','zmin','zmax'} — z0/z are
    measured from 'point' along 'axis' — or None when the patch reads
    flat, conical or sphere-ish (residual over 4 % of the radius)."""
    pts = np.asarray(points, float).reshape(-1, 3)
    nrm = np.asarray(normals, float).reshape(-1, 3)
    if len(pts) < 12 or len(nrm) < 12:
        return None
    nrm = nrm / np.linalg.norm(nrm, axis=1, keepdims=True)
    # the axis direction carries the LEAST normal variance
    _, sv, vt = np.linalg.svd(nrm, full_matrices=False)
    axis = vt[2]
    if sv[1] < 0.25 * sv[0]:             # normals collapsed to one way: flat
        return None
    if sv[2] > 0.25 * sv[1]:             # normals not a flat fan: no axis
        return None
    # ON-basis of the plane normal to the axis
    e1 = np.cross(axis, np.eye(3)[int(np.abs(axis).argmin())])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(axis, e1)
    q = pts - pts.mean(0)
    x, y = q @ e1, q @ e2
    A = np.column_stack([x, y, np.ones_like(x)])
    sol, *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    cx, cy = sol[0] / 2.0, sol[1] / 2.0
    r2 = sol[2] + cx * cx + cy * cy
    if r2 <= 0:
        return None
    r = float(np.sqrt(r2))
    perp = np.hypot(x - cx, y - cy)
    if float(np.std(perp)) > 0.04 * r:   # flat (r explodes), cone, sphere
        return None
    centre = pts.mean(0) + e1 * cx + e2 * cy
    h = q @ axis                          # height along the axis
    return dict(axis=tuple(float(t) for t in axis),
                point=tuple(float(t) for t in centre),
                radius=r, zmin=float(h.min()), zmax=float(h.max()))
