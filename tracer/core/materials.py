"""M110 — material densities for the parts list (BOM) masses.

A parts list earns its keep when it says what a body is MADE of and
what it WEIGHS. The geometry already knows its volume (Solid.volume,
mm³); mass is one published constant away: grams = volume/1000 × ρ
(g/cm³). These ρ values are typical engineering figures (the printed
set matches what filament spools and metal guides quote) — accurate to
a few percent, which is exactly the honesty level the BOM promises:
masses are labelled typical, not certified.

Like units (M60), this module SPEAKS about the model; it never changes
it. A body carries an optional "material" name; unknown names yield
None and the BOM prints "—" rather than inventing mass.
"""
from __future__ import annotations

#: published typical densities in g/cm³ (filaments first — this is a
#: maker CAD; see research/material_density_db.md for the source set).
MATERIALS = {
    "PLA": 1.24, "PLA-CF": 1.30, "PETG": 1.27, "ABS": 1.04,
    "ASA": 1.07, "TPU": 1.21, "Nylon PA12": 1.01, "Nylon PA6": 1.13,
    "PC": 1.20, "PP": 0.91, "PVA": 1.23, "Tough resin": 1.10,
    "Aluminium": 2.70, "Brass": 8.50, "Bronze": 8.80, "Copper": 8.96,
    "Steel": 7.85, "Stainless 304": 7.90, "Titanium Ti-6Al-4V": 4.43,
    "Magnesium": 1.74, "Acrylic": 1.18,
}

DEFAULT = "ABS"                    # Fusion's own starter default [H]
NAMES = sorted(MATERIALS)          # UI combo order


def mass_g(volume_mm3: float, material: str | None) -> float | None:
    """Grams for a volume at a material's density; None if unknown."""
    rho = MATERIALS.get(material or "")
    if rho is None:
        return None
    return float(volume_mm3) / 1000.0 * rho


def mass_str(g: float | None, unit: str = "g") -> str:
    """Speak a mass the way the drawing speaks lengths: '12.3 g',
    '1.24 kg'. Unknown yields the em dash so a column never lies."""
    if g is None:
        return "—"
    if unit == "kg" or g >= 1000.0:
        return f"{g / 1000.0:.2f} kg"
    return f"{g:.1f} g"
