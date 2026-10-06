"""3D Print readiness checks — the brain behind Utilities ▸ 3D Print.

Fusion's 3D Print dialog inspects the model, warns what the slicer
will hate, and exports a bed-ready mesh.  The honest version here:
count triangles, weigh the part at the picked material, measure it
against a typical printer bed, count its floating islands and tell
the truth about watertightness.  Everything the report needs arrives
as a plain dict — the dialog is paint, this is the engineering.
"""
from __future__ import annotations


def print_report(solid, density_g_cm3: float = 1.24) -> dict:
    """Analyse a Solid for printing.  Sizes are millimetres (the stored
    truth); mass is grams at the given density.  Warnings are sentences
    for humans, in priority order."""
    from .measure import mass_properties
    tm = solid.to_trimesh()
    mp = mass_properties(solid, density_g_cm3)
    bounds = tm.bounds
    size = tuple(float(b) for b in bounds[1] - bounds[0])
    try:
        islands = len(tm.split(only_watertight=False))
    except Exception:
        islands = 1
    watertight = bool(tm.is_watertight)
    warns: list = []
    if not watertight:
        warns.append("Mesh is NOT watertight — the slicer will guess "
                     "what you meant")
    if islands > 1:
        warns.append(f"{islands} separate islands — every one prints")
    if size and max(size) > 250.0:
        warns.append(f"{max(size):.0f} mm across — larger than a typical "
                     "250 mm bed")
    if size and min(size) < 0.4:
        warns.append(f"Model is only {min(size):.2f} mm thick in one "
                     "axis — hair-thin features may not survive")
    return {"watertight": watertight,
            "triangles": int(len(tm.faces)),
            "volume_mm3": float(mp["volume_mm3"]),
            "mass_g": float(mp["mass_g"]),
            "size_mm": size,
            "islands": islands,
            "warnings": warns}


def drop_to_bed(solid):
    """Return a COPY of the solid's mesh resting on z=0 (the exported
    STL lies flat on the build plate, like Fusion's print prep)."""
    tm = solid.to_trimesh().copy()
    tm.apply_translation((0.0, 0.0, -float(tm.bounds[0][2])))
    return tm
