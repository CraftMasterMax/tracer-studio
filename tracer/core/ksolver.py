"""SM3 (M149): the K-factor sidecar — a DEFAULT PROVIDER, not a rule
subsystem. Fusion keeps K on a body-level Sheet Metal Rule; Tracer v1
keeps the numbers on the FlangeFeature and consults this table only to
FILL the default (k_factor=None → the table answers by material and
r/t; an unknown material answers None and the caller keeps K_DEFAULT
out loud, never a silent average).

Provenance is shop air-bend folklore (SM1's own line: K = 0.44 is
folklore, not a standard — and the phantom standard number lives
only in the research notes, never in product text). r/t keyed
lookup is prior art from FreeCAD's SheetMetalKfactor, read as
structure — no data copied.
"""
from __future__ import annotations

import json
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "ksheet.json"

MATERIALS: list[str] = []            # ordered, for the dialog combo
_ROWS: list[dict] = []
_loaded = False


def _load() -> None:
    global _loaded, MATERIALS, _ROWS
    if _loaded:
        return
    doc = json.loads(_DATA.read_text(encoding="utf-8"))
    _ROWS = list(doc["rows"])
    seen: set[str] = set()
    for r in _ROWS:
        if r["material"] not in seen:
            seen.add(r["material"])
            MATERIALS.append(r["material"])
    _loaded = True


def reload() -> None:
    """Re-read the JSON (edit-table-row → dialog-reflects-live)."""
    global _loaded
    _loaded = False
    _load()


def materials() -> list[str]:
    _load()
    return list(MATERIALS)


def k_for(material: str, ri: float, t: float) -> float | None:
    """Bin lookup: r/t lands in a material's row, or None (the caller
    keeps K_DEFAULT and says so). Edge is half-open [lo, hi) so an
    exact r/t boundary is deterministic, never two matching rows."""
    _load()
    if t <= 0:
        raise ValueError("a sheet needs positive thickness to find a K")
    rt = ri / t
    for r in _ROWS:
        lo, hi = r["r_over_t"]
        if r["material"] == material and lo <= rt < hi:
            return float(r["K"])
    return None


def k_or_default(material: str, ri: float, t: float, default: float):
    """(K, from_table: bool) — None from the table falls back to the
    caller's default and flags it so the UI can say '0.44 (default,
    no table row for this material)' rather than printing a number
    that pretends to be sourced."""
    k = k_for(material, ri, t)
    if k is None:
        return float(default), False
    return k, True
