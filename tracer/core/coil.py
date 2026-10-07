"""M127 coil-v1 — the helical ridge, honest on a mesh timeline.

A coil is a closed section (circular or square) riding a helix, lofted
through dense ring stations and capped abrupt: exactly what the
market-leader's Coil primitive builds when its type is Revolutions-And-
Pitch, and its abrupt ends match the vendor default too (runout needs
profile metadata we deliberately don't fake). Internal modeled threads
are NOT built here: standards tooling itself routes them through
decoration for performance (wave-5 research), and this kernel agrees.

The helix spins about a frame the caller resolves — so coil axes come
from the M125 named-datum store like everything else."""
from __future__ import annotations

import math

import numpy as np

from . import params
from .geometry import Solid


def _section_pts(section: str, size: float, k: int) -> np.ndarray:
    """Local (a, b) ring coordinates of the built-in sections; `size`
    is the circumscribed diameter, vendor-style."""
    r = float(size) / 2.0
    s = str(section).lower()
    if s == "circular":
        t = np.linspace(0.0, 2.0 * np.pi, k, endpoint=False)
        return np.column_stack([r * np.cos(t), r * np.sin(t)])
    if s == "square":
        h = r / math.sqrt(2.0)               # half-side of that diagonal
        corners = [(-h, -h), (h, -h), (h, h), (-h, h)]
        out = []
        for i in range(k):                    # walk edges so resampling
            u = 4.0 * i / k                   # sees a dense square
            e = int(u)
            f = u - e
            (a0, b0), (a1, b1) = corners[e], corners[(e + 1) % 4]
            out.append((a0 + (a1 - a0) * f, b0 + (b1 - b0) * f))
        return np.asarray(out)
    raise params.ParamError(f"unknown coil section {section!r} — "
                            "v1 builds circular and square")


def coil_solid(origin, axis_dir, radius: float, pitch: float, turns: float,
               section: str = "circular", size: float = 1.0,
               hand: str = "right", samples_per_turn: int = 36,
               ring: int = 24) -> Solid:
    """Lofted helical ridge about the line (origin, axis_dir). On-center
    positioning: the section centre rides the helix of `radius`
    (the centre diameter / 2). Height is turns x pitch — the classic
    two-of-three input solved forward."""
    r = float(radius)
    p = float(pitch)
    n_t = float(turns)
    d = float(size)
    if r <= 0.0:
        raise params.ParamError("coil centre diameter must be positive")
    if p <= 0.0:
        raise params.ParamError("coil pitch must be positive")
    if n_t < 0.5:
        raise params.ParamError("a coil needs at least half a turn")
    if d <= 0.0:
        raise params.ParamError("coil section size must be positive")
    if d > p:
        raise params.ParamError(
            f"section {d:g} mm rides a {p:g} mm pitch — neighbouring "
            "turns would swallow each other; choose a finer section "
            "or a coarser pitch")
    if str(hand).lower() not in ("right", "left"):
        raise params.ParamError("coil hand is right or left")
    sgn = 1.0 if str(hand).lower() == "right" else -1.0

    a = np.asarray(axis_dir, float)
    a = a / np.linalg.norm(a)
    helper = (np.array([0.0, 0.0, 1.0]) if abs(float(a[2])) < 0.9
              else np.array([1.0, 0.0, 0.0]))
    u0 = np.cross(a, helper)
    u0 = u0 / np.linalg.norm(u0)
    v0 = np.cross(a, u0)

    o = np.asarray(origin, float)
    steps = max(2, int(round(n_t * samples_per_turn))) + 1
    sec = _section_pts(section, d, ring)
    theta_max = sgn * 2.0 * math.pi * n_t
    sections = []
    for i in range(steps):
        th = theta_max * i / (steps - 1)
        z = p * abs(th) / (2.0 * math.pi)
        c = o + r * (math.cos(th) * u0 + math.sin(th) * v0) + z * a
        tvec = sgn * (-math.sin(th) * u0 + math.cos(th) * v0) * r \
            + (p / (2.0 * math.pi)) * a
        tvec = tvec / np.linalg.norm(tvec)
        e1 = np.cross(tvec, a)
        e1 = e1 / np.linalg.norm(e1)
        e2 = np.cross(tvec, e1)
        sections.append(c + np.outer(sec[:, 0], e1)
                          + np.outer(sec[:, 1], e2))
    from .loft import loft
    try:
        return loft(sections, n=ring, caps=True)
    except ValueError as exc:                 # loft speaks plain refuse
        raise params.ParamError(f"coil could not be built: {exc}")
