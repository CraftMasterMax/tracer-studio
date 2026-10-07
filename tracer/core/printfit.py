"""M124 print fit-mode — an honest δ at the export boundary.

FDM prints drift, and they drift asymmetrically: holes print small
(faceting + ooze), first layers squash outward, heights are nearly
true (`print_fit_mode.md`, sourced from measurement studies and the
slicers' own factory profiles).  Slicers fudge this per-layer behind
your back — Cura `hole_xy_offset`, PrusaSlicer `xy_size_compensation`,
Bambu `xy_hole_compensation` — and SuperSlicer even INVERTS the hole
sign.  Tracer's answer is a document-level knob at the ONE boundary
that matters: export.

v1 compensates the feature the literature agrees is worst — drilled
holes — by rewriting the parametric radius (hole +δ) inside a
context manager: the document's own numbers are never touched, the
mesh is never morphed (a ball offset provably cannot move a wall
larger than the ball — it only rounds rims), and every change is
logged with the face it came from.  Threads, pins and planar faces
stay nominal in v1 and SAY SO in the plan; the label-only mode just
annotates expected deviation without touching geometry, which is what
δ = 0 (the default) always does.
"""
from __future__ import annotations

import contextlib

from .document import HoleFeature, ThreadFeature

#: Sourced expected deviations for a dialed-in consumer FDM machine at
#: 0.4 mm nozzle (print_fit_mode.md §1: Popescu 2022, Sukindar 2024,
#: HydraRaptor faceting analysis, PrusaSlicer factory profiles).
EXPECTED_DEVIATION = (
    "holes Ø: print SMALL ~0.1–0.2 mm (faceting + ooze)",
    "XY widths: print LARGE by up to ~0.3 mm",
    "Z heights: nearly true (studies: < 0.1 mm)",
    "first layer: elephant-foot squish +0.15–0.2 mm at the bed",
)


def plan(doc, delta: float) -> dict:
    """Decide what a δ would change — WITHOUT touching the document.

    Returns {"delta", "edits": [{feature, name, r, new_r}], "skipped":
    [{name, reason}], "expected": (label-only notes)}.  A hole smaller
    than 2δ is refused, not risked: the offset could break through the
    wall it lives in."""
    delta = float(delta)
    edits, skipped = [], []
    for f in getattr(doc, "features", []):
        if isinstance(f, HoleFeature) and f.op == "subtract":
            r = float(f.radius)
            if delta <= 0.0:
                continue
            if r < 2.0 * delta:
                skipped.append({"name": f.name, "reason":
                                f"r {r:g} mm below 2δ (feature would break)"})
                continue
            edits.append({"feature": f, "name": f.name,
                          "r": r, "new_r": round(r + delta, 4)})
        elif isinstance(f, ThreadFeature) and delta > 0.0:
            skipped.append({"name": f.name,
                            "reason": "printed threads stay nominal in v1"})
    return {"delta": delta, "edits": edits, "skipped": skipped,
            "expected": () if delta <= 0.0 else EXPECTED_DEVIATION}


@contextlib.contextmanager
def compensated(doc, delta: float):
    """Yield (plan, doc) with the planned hole radii enlarged by δ;
    restore the document byte-for-byte on exit.  The recompute happens
    inside, so whatever reads doc.result during the block sees the
    print-compensated solid and nothing else ever does."""
    pl = plan(doc, delta)
    for e in pl["edits"]:
        e["feature"].radius = e["new_r"]
    if pl["edits"]:
        doc.recompute()
    try:
        yield pl, doc
    finally:
        for e in pl["edits"]:
            e["feature"].radius = e["r"]
        if pl["edits"]:
            doc.recompute()


def describe(pl: dict) -> str:
    """One honest line: what the plan did or would do."""
    if pl["delta"] <= 0.0:
        return "as-modelled (δ 0 — geometry unchanged)"
    moved = ", ".join(f"{e['name']} Ø {2 * e['r']:g}→{2 * e['new_r']:g}"
                      for e in pl["edits"]) or "no holes moved"
    warn = "" if not pl["skipped"] else f" — {len(pl['skipped'])} skipped"
    return f"δ {pl['delta']:g} mm: {moved}{warn}"
