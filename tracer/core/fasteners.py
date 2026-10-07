"""Fastener hole library (M107 tables, M123 provenance layer).

Tracer's HoleFeature can already cut a tap-drilled, counterbored,
countersunk or threaded hole — the kernel is not the gap.  The gap is
DOMAIN KNOWLEDGE: that an M3 clearance hole is Ø3.4, an M3 tap drills
Ø2.5 on a 0.5 pitch, an M3 socket-head cap screw wants a Ø6 counterbore
about 3.2 deep, and an M3 heat-set insert presses into Ø4.  This module
turns a named fastener (M3, kind=clearance) into exactly the parameters
``HoleDialog`` / ``HoleFeature`` consume, so a single combo pick fills
the dialog and the sketch circle drops to being PLACEMENT ONLY.

M123 moved the numbers out of Python literals and into `data/*.json`:
every table now carries its own PROVENANCE (standard + edition, what
verified it and when, and a licensing note) beside the values, so no
figure ships uncited.  ``provenance(key)`` hands that record to the UI
(a tooltip, an audit view); a CI validator (test_m123) fails the build
if any table is missing provenance or breaks an internal cross-check
with a neighbouring standard.  The numbers are facts — re-keyed by hand
from public sources, never scraped, with no source layout reproduced.

The public API is unchanged from M107: the same SIZES/FIT/KINDS, the
same ``hole_for`` bundles, and washers newly alongside them.
"""
from __future__ import annotations

import json
from pathlib import Path

from .thread import ISO_COARSE

_DATA_DIR = Path(__file__).parent / "data"

# table key -> data file. The validator walks this; nothing loads without
# a registered, provenance-carrying file.
TABLES = {
    "clearance":     "iso273_clearance.json",
    "shcs_head":     "iso4762_din912_shcs_head.json",
    "insert":        "heatset_inserts.json",
    "washer_normal": "iso7089_washer_normal.json",
    "washer_small":  "iso7092_washer_small.json",
}

_PROV: dict[str, dict] = {}
_TABLE: dict[str, dict[str, list[float]]] = {}


def _load(key: str) -> dict[str, list[float]]:
    if key not in _TABLE:
        raw = json.loads((_DATA_DIR / TABLES[key]).read_text(encoding="utf-8"))
        _PROV[key] = raw
        _TABLE[key] = {s: [float(x) for x in vals]
                       for s, vals in raw["data"].items()}
    return _TABLE[key]


def provenance(key: str) -> dict:
    """The full source record for a table (standard/edition/provenance/
    verified/license/notes) — data the UI can show so a value is never
    an unsourced magic number."""
    if key not in TABLES:
        raise KeyError(f"no such fastener table {key!r}")
    _load(key)
    return _PROV[key]


# ISO metric coarse sizes the library speaks (matches ISO_COARSE).
SIZES = tuple(ISO_COARSE)                     # M3..M12

# ISO 273 clearance-hole diameters: size -> (close, medium, coarse).
# Corrected 2026-10-07 against the official ISO 273:1979 preview + 3
# reprints; seven cells had drifted into nominal+0.1 shop folklore.
CLEARANCE = {s: tuple(v) for s, v in _load("clearance").items()}
FIT = tuple(_PROV["clearance"]["columns"])    # ("close","medium","coarse")

# DIN 912 / ISO 4762 socket head cap screws: size -> (head Ø, head h).
# Counterbore = head Ø + 0.5 clearance, depth = head height + 0.2 — a
# Tracer design margin on top of the standard head, not a standards figure.
SHCS_HEAD = {s: tuple(v) for s, v in _load("shcs_head").items()}

# Common heat-set (brass) insert recommended drill Ø (single column).
# Brand-dependent — a starting point, not gospel; see provenance notes.
INSERT = {s: v[0] for s, v in _load("insert").items()}

# Plain washers, size -> (ID, OD, thickness). "normal" = ISO 7089
# (= DIN 125A); "small" = ISO 7092 (= DIN 433) — the low-profile washer
# that clears an SHCS head recess.
WASHERS = {"normal": {s: tuple(v) for s, v in _load("washer_normal").items()},
           "small": {s: tuple(v) for s, v in _load("washer_small").items()}}

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


def washer(size: str, series: str = "normal") -> tuple[float, float, float]:
    """(ID, OD, thickness) for a plain washer, ISO 7089 (normal) or
    ISO 7092 (small)."""
    if series not in WASHERS:
        raise KeyError(f"no washer series {series!r} (normal|small)")
    if size not in WASHERS[series]:
        raise KeyError(f"no washer data for {size!r}")
    return WASHERS[series][size]


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
