"""Fastener hole library (M107): the numbers a maker shouldn't look up.

Tracer's HoleFeature can already cut a tap-drilled, counterbored,
countersunk or threaded hole — the kernel is not the gap.  The gap is
DOMAIN KNOWLEDGE: that an M3 clearance hole is Ø3.4, an M3 tap drills
Ø2.5 on a 0.5 pitch, an M3 socket-head cap screw wants a Ø6 counterbore
about 3.2 deep, and an M3 heat-set insert presses into Ø4.  This module
turns a named fastener (M3, kind=clearance) into exactly the parameters
``HoleDialog`` / ``HoleFeature`` consume, so a single combo pick fills
the dialog and the sketch circle drops to being PLACEMENT ONLY.

Every table is plain, sourced data so it is trivially testable and
auditable.  Thread pitch + tap drill are reused verbatim from
``thread.ISO_COARSE`` (the tap path already trusts those figures).

Sources (nominal dimensions, mm) — re-keyed by hand, never copied:
  * Clearance holes — EN ISO 273 close/medium/coarse (H12/H13/H14).
    ✓✓ VERIFIED 2026-10-07 against the official ISO 273:1979 preview
    PDF plus three reprints; 7 shop-folklore cells corrected in the
    sweep (see the CLEARANCE table notes).
  * Tapped holes    — ISO 261 pitch (✓✓ verified), ISO 724 tap drill
    (✓✓ verified vs four charts) via ISO_COARSE.
  * Socket head cap screws (SHCS) — DIN 912 / ISO 4762 head Ø + height
    (✓✓ verified 14/14, 2026-10-07); the counterbore is the head Ø opened
    up ~0.5 mm, depth = head height +0.2 — a Tracer design margin, not a
    standards figure.
  * Heat-set inserts — brand-dependent; values re-swept 2026-10-07
    against reachable datasheets (see the INSERT table notes).
"""
from __future__ import annotations

from .thread import ISO_COARSE

# ISO metric coarse sizes the library speaks (matches ISO_COARSE).
SIZES = tuple(ISO_COARSE)                     # M3..M12

# ISO 273 clearance-hole diameters: size -> (close, medium, coarse)
CLEARANCE = {
    # EN ISO 273:1979 (fine/H12, medium/H13, coarse/H14) — verified
    # 2026-10-07 cell-by-cell against the official ISO preview PDF
    # (text layer + OCR) and three independent reprints
    # [iso273_washers_verify.md].  Seven cells were corrected: the old
    # M4/M5 close-medium pairs and coarse M6/M8 were shop-table
    # folklore (nominal+0.1 style), not the standard.
    "M3":  (3.2, 3.4, 3.6),
    "M4":  (4.3, 4.5, 4.8),      # was 4.1 / 4.3 / 4.6
    "M5":  (5.3, 5.5, 5.8),      # was 5.1 / 5.3 / 5.8
    "M6":  (6.4, 6.6, 7.0),      # was 6.4 / 6.6 / 7.1
    "M8":  (8.4, 9.0, 10.0),     # was 8.4 / 9.0 / 9.5
    "M10": (10.5, 11.0, 12.0),
    "M12": (13.0, 13.5, 14.5),
}
FIT = ("close", "medium", "coarse")           # index into a CLEARANCE row

# DIN 912 / ISO 4762 socket head cap screws: size -> (head Ø, head height).
# Counterbore = head Ø + 0.5 clearance, depth = head height + 0.2.
SHCS_HEAD = {
    "M3":  (5.5, 3.0),
    "M4":  (7.0, 4.0),
    "M5":  (8.5, 5.0),
    "M6":  (10.0, 6.0),
    "M8":  (13.0, 8.0),
    "M10": (16.0, 10.0),
    "M12": (18.0, 12.0),
}

# Common heat-set (brass) insert recommended drill Ø.  Brand-dependent —
# treat as a starting point and check the datasheet.  M5/M6 corrected
# 2026-10-07 after a source sweep: the old 7.0/8.5 were "large-barrel"
# folklore and exceed every reachable modern compact-series chart
# (CNC Kitchen 6.5/8.1, aggregators 6.0–6.8/8.2); 6.7/8.2 sit at the top
# of that band so a standard insert still seats without a loose bore.
INSERT = {
    "M3": 4.0,      # ✓✓ two brands agree (CNC Kitchen, Accu)
    "M4": 5.6,      # ✓? CNCK 5.7 — within one print step; series ambiguity
    "M5": 6.7,      # was 7.0 — above every reachable chart
    "M6": 8.2,      # was 8.5 — likewise large-barrel-only
}

# The kinds a preset can produce (drives the dialog's Fastener combo).
KINDS = ("clearance", "tapped", "socket head", "heat-set insert")


def nominal(size: str) -> float:
    return float(size[1:])


def pitch(size: str) -> float:
    return ISO_COARSE[size][0]


def tap_drill(size: str) -> float:
    return ISO_COARSE[size][1]


def clearance(size: str, fit: str = "medium") -> float:
    if size not in CLEARANCE:
        raise KeyError(f"no clearance data for {size!r}")
    return CLEARANCE[size][FIT.index(fit)]


def cbore(size: str) -> tuple[float, float]:
    """(counterbore Ø, depth) for a socket head cap screw, from DIN 912."""
    head, height = SHCS_HEAD[size]
    return round(head + 0.5, 2), round(height + 0.2, 2)


def hole_for(size: str, kind: str, fit: str = "medium") -> dict:
    """The HoleDialog parameter bundle for a named fastener.

    Returns keys ``drill`` (Ø mm, or None → keep the sketch circle),
    ``thread`` (an ISO_COARSE key or "None"), ``type``
    (simple|counterbore|countersink), ``cb_dia`` / ``cb_depth``
    (0 when unused).  ``drill`` overrides the sketch-circle diameter so
    the drawn circle only places the hole.
    """
    kind = kind.strip().lower()
    if kind == "clearance":
        return dict(drill=clearance(size, fit), thread="None",
                    type="simple", cb_dia=0.0, cb_depth=0.0)
    if kind == "tapped":
        return dict(drill=None, thread=size, type="simple",   # ISO tap drill
                    cb_dia=0.0, cb_depth=0.0)
    if kind == "socket head":
        dia, dep = cbore(size)
        return dict(drill=clearance(size, fit), thread="None",
                    type="counterbore", cb_dia=dia, cb_depth=dep)
    if kind == "heat-set insert":
        return dict(drill=INSERT[size], thread="None",
                    type="simple", cb_dia=0.0, cb_depth=0.0)
    raise ValueError(f"unknown fastener kind {kind!r}")
