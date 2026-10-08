"""M144 — GD&T rung 1: the geometry the frame must obey (pure core).

Everything here was de-risked by the probe (research/gdt_glyphs.md)
from FETCHED standard text, not memory: ISO 1101:2012 (Table 1/2
per-control datum + zone doctrine, cl.6.1 frame compartments, cl.11
"hence TED shall ... be enclosed in a frame") and ASME Y14.5-2018
(6.4.1–6.4.3 compartment grammar, 6.3.2 datum letters). Three laws
shape the module:

GLYPHS ARE PAINTED, NEVER UNICODE. The machine checked the fonts
this product ships with: the entire U+2300 GD&T block is TOFU on
real paper fonts (Liberation, DejaVu: not one glyph). Six controls
are coordinate lists in a normalised unit box — the painter scales,
the paper receives. The diameter sign keeps the repo's printable
letter Ø (U+00D8): the ⌀ entered in a dialog normalises to it.

VALUES ARE STRINGS. A tolerance is the drafter's typed ink;
resolve_dims re-measures geometry, never a frame (wave-11a law —
same reason the fit callout stores its class as text).

ONE LETTER REGISTRY. Datum letters ARE the section letters: the
reserved family (I O Q S X Z — a superset of Y14.5's own I O Q,
safe under both standards) is imported from core.drawing, so the
object is literally shared, not re-spelled.
"""
from __future__ import annotations

from .drawing import RESERVED_LETTERS          # ONE registry (M136/M144)

# The six rung-1 controls, each a list of ops in the unit box:
#   ("poly", [(x, y), ...])          an open stroke
#   ("poly", [(x, y), ...], True)    a closed one
#   ("circle", (cx, cy), r)          a full circle
# Coordinates per the probe's §1 sourcing (ISO 1101 Table shapes;
# the Wikimedia PD SVGs confirmed numerically: straightness is
# (0.1,0.5)->(0.9,0.5), flatness the 2:1-slant parallelogram).
GLYPHS = {
    "straightness": [("poly", [(0.10, 0.50), (0.90, 0.50)])],
    "flatness": [("poly", [(0.90, 0.30), (0.30, 0.30),
                           (0.10, 0.70), (0.70, 0.70)], True)],
    "circularity": [("circle", (0.50, 0.50), 0.40)],
    "cylindricity": [("circle", (0.50, 0.55), 0.26),
                     ("poly", [(0.08, 0.80), (0.32, 0.28)]),
                     ("poly", [(0.68, 0.80), (0.92, 0.28)])],
    "perpendicularity": [("poly", [(0.15, 0.15), (0.15, 0.90)]),
                         ("poly", [(0.10, 0.90), (0.90, 0.90)])],
    "position": [("circle", (0.50, 0.50), 0.30),
                 ("poly", [(0.10, 0.50), (0.90, 0.50)]),
                 ("poly", [(0.50, 0.10), (0.50, 0.90)])],
    # rung 2 (M150): five new seats, ISO 1101 Table shapes via the
    # probe §1.3 unit-box specs (y-DOWN like the page)
    "parallelism": [("poly", [(0.14, 0.88), (0.44, 0.22)]),
                    ("poly", [(0.42, 0.88), (0.72, 0.22)])],
    "angularity": [("poly", [(0.14, 0.82), (0.80, 0.82)]),
                   ("poly", [(0.14, 0.82), (0.66, 0.22)])],
    "profile_line": [("arc", (0.50, 0.72), 0.36, 180, 0)],
    "profile_surface": [("arc", (0.50, 0.72), 0.36, 180, 0),
                        ("poly", [(0.14, 0.72), (0.86, 0.72)])],
    "circular_runout": [("arrow", (0.24, 0.76), (0.76, 0.24))],
}

# The controls rung 2 REFUSES by name, with the reason in the voice
# (a bare "unknown control" would hide the law):
DEFERRED = {
    "total_runout": "total runout is the circumferential-COMPOUND "
                    "readout (a 360-sweep of circular runout plus "
                    "element-line orientation) - no closed form, "
                    "queued behind circular runout",
    "concentricity": "concentricity was ELIMINATED by ASME "
                     "Y14.5-2018 - the honest check is a median-"
                     "element locus; do not draw it",
    "symmetry": "symmetry was ELIMINATED by ASME Y14.5-2018 - the "
                "honest check is a median-element locus; do not "
                "draw it",
}

# The validator's rows — every field sourced in the probe §2.
#   mods:    material-condition modifiers the control may carry
#   datums:  (min, max) datum-reference arity (Table 2 doctrine)
#   diam:    "forbidden" | "optional" | "normal" — a zone that is
#            never / may be / usually IS diametral (cl.6.1: the
#            value is then preceded by the diameter symbol)
#   forces_TE: ISO cl.11 — basic (boxed) dims belong to orientation/
#            location/profile tolerances; rung 1 warns, never blocks
CONTROL_TABLE = {
    "straightness": dict(
        name="Straightness", mods=("M",), datums=(0, 0),
        diam="optional", forces_TE=False,
        zone="two parallel lines/planes; a cylinder iff ⌀ (18.1)"),
    "flatness": dict(
        name="Flatness", mods=(), datums=(0, 0),
        diam="forbidden", forces_TE=False,
        zone="two parallel planes t apart (18.2)"),
    "circularity": dict(
        name="Circularity", mods=(), datums=(0, 0),
        diam="forbidden", forces_TE=False,
        zone="two concentric circles, radial band (18.3)"),
    "cylindricity": dict(
        name="Cylindricity", mods=(), datums=(0, 0),
        diam="forbidden", forces_TE=False,
        zone="two coaxial cylinders, radial band (18.4)"),
    "perpendicularity": dict(
        name="Perpendicularity", mods=("M",), datums=(1, 3),
        diam="optional", forces_TE=True,
        zone="two parallel planes/lines (a cylinder iff ⌀) (18.6)"),
    "position": dict(
        name="Position", mods=("M", "L"), datums=(0, 3),
        diam="normal", forces_TE=True,
        zone="cylinder iff ⌀; two planes or sphere otherwise (18.8)"),
    # ---- rung 2 (M150) ----
    "parallelism": dict(
        name="Parallelism", mods=("M",), datums=(1, 3),
        diam="optional", forces_TE=True,
        zone="two parallel planes/lines (a cylinder iff ⌀)"),
    "angularity": dict(
        name="Angularity", mods=("M",), datums=(1, 3),
        diam="optional", forces_TE=True,
        zone="two parallel planes/lines at the STATED angle"),
    "profile_line": dict(
        name="Profile of a line", mods=("M",), datums=(0, 3),
        diam="forbidden", forces_TE=True,
        zone="two envelope lines t apart, t/2 each side of the "
             "true profile"),
    "profile_surface": dict(
        name="Profile of a surface", mods=("M",), datums=(0, 3),
        diam="forbidden", forces_TE=True,
        zone="two envelope surfaces t apart, t/2 each side of "
             "the true profile"),
    "circular_runout": dict(
        name="Circular runout", mods=(), datums=(1, 1),
        diam="forbidden", forces_TE=False,
        zone="two concentric circles in one view plane, radial "
             "band t"),
}

_NAMES = {row["name"]: key for key, row in CONTROL_TABLE.items()}

# diameter-sign spellings: the entered TOFU (U+2300) and the paper
# LETTER the product actually owns (U+00D8) — both parse, only the
# letter paints.
_DIAM = ("\u2300", "\u00d8")


def gdt_validate(entry: dict) -> list[str]:
    """One choke for the frame grammar; raises ValueError NAMING the
    broken law (the dialog shows the message verbatim, fits.callout's
    voice). Returns the shop-law WARNINGS — legal ISO the drafter
    should hear about (position with no datum reference)."""
    row = CONTROL_TABLE.get(entry.get("sym", ""))
    if row is None:
        gone = DEFERRED.get(str(entry.get("sym", "")))
        if gone is not None:
            raise ValueError(gone)
        raise ValueError(
            f"'{entry.get('sym')}' is not one of: "
            + ", ".join(r["name"] for r in CONTROL_TABLE.values()))
    # the value: an optional (S)⌀ prefix + a positive number, kept
    # as WRITTEN (a tolerance is typed ink, never a re-measure)
    tol = str(entry.get("tol", "")).strip()
    prefix = ""
    for cand in ("S" + _DIAM[0], "S" + _DIAM[1],
                 _DIAM[0], _DIAM[1]):
        if tol.startswith(cand):
            prefix = "S" if cand.startswith("S") else "D"
            tol = tol[len(cand):].strip()
            break
    try:
        value = float(tol)
    except ValueError:
        raise ValueError(
            f"tolerance '{entry.get('tol')}' must be a number, "
            "optionally preceded by the diameter sign") from None
    if not value > 0:
        raise ValueError("a tolerance zone has a positive width")
    if prefix and row["diam"] == "forbidden":
        raise ValueError(
            f"{row['name']} zones are not diametral — the ⌀ sign "
            f"does not belong ({row['zone']})")
    if prefix == "SD" and row["diam"] != "normal":
        raise ValueError(
            f"a spherical (S⌀) zone belongs to location, not "
            f"{row['name'].lower()}")
    # the modifier: shares the value cell (Y14.5 6.4.1), after the
    # number — and ONLY the modifiers the control is modified by
    mod = str(entry.get("mod", "") or "").strip()
    if mod and mod not in row["mods"]:
        raise ValueError(
            f"{row['name']} is not modified by ({mod})"
            + (f" — only by {', '.join(row['mods'])}"
               if row["mods"] else " — no modifier applies"))
    # the datums: arity (Table 2) + ONE letter per compartment
    # (6.4.3); a shared compartment is the ISO COMMON datum, dashed
    datums = list(entry.get("datums", []))
    lo, hi = row["datums"]
    if len(datums) > hi:
        raise ValueError(f"{row['name']} takes at most {hi} datum "
                         "references, in precedence order")
    if len(datums) < lo:
        raise ValueError(
            f"{row['name']} is a RELATED control — it needs at "
            f"least {lo} datum reference")
    for cell in datums:
        cell = str(cell).strip()
        if not cell:
            raise ValueError("an empty datum compartment")
        if any(c.isspace() for c in cell):
            raise ValueError(
                f"datum '{cell}' mixes letters with spaces — every"
                " reference gets its OWN compartment (6.4.3), or "
                "A-B dashed for a common datum")
        for part in cell.split("-"):
            if len(part) != 1:
                raise ValueError(
                    f"datum '{cell}': two independent letters need "
                    "separate compartments (6.4.3) — one shared "
                    "cell is a COMMON datum, written A-B")
            if not ("A" <= part <= "Z"):
                raise ValueError(
                    f"datum '{cell}' must use capital letters")
            if part in RESERVED_LETTERS:
                raise ValueError(
                    f"datum letter {part} is reserved by the "
                    f"standards (reserved: {RESERVED_LETTERS})")
    # ---- rung 2 grammar: the angle, the projected zone ----
    angle = str(entry.get("angle", "") or "").strip()
    if entry["sym"] == "angularity":
        if not angle:
            raise ValueError(
                "angularity states its TRUE angle - the frame "
                "without it describes no zone")
        try:
            a_val = float(angle)
        except ValueError:
            raise ValueError(
                f"angle '{angle}' must be a number of degrees"
            ) from None
        if not 0.0 < a_val < 180.0:
            raise ValueError(
                "the stated angle lives between 0 and 180 "
                "degrees (0 is parallelism, 90 perpendicularity)")
    elif angle:
        raise ValueError(
            f"({angle}) belongs to angularity only - "
            f"{row['name']} rides its datum at right angles or "
            "parallel")
    proj = str(entry.get("proj", "") or "").strip()
    if proj:
        if entry["sym"] not in ("position", "perpendicularity",
                                "parallelism", "angularity"):
            raise ValueError(
                "a projected zone projects an AXIS - "
                f"{row['name']} has no axis story")
        try:
            h_val = float(proj)
        except ValueError:
            raise ValueError(
                f"projected height '{proj}' must be a number"
            ) from None
        if not h_val > 0:
            raise ValueError("the projected height is a positive "
                             "length (the drafter owns it: at "
                             "least the mating part's thickness)")
    warnings = []
    if mod in ("M", "L") and not entry.get("size") \
            and not entry.get("target"):
        warnings.append(
            f"({mod}) is painted, not evaluated, without size "
            "limits or a feature target - the frame is honest ink "
            "but the bonus stays in the shop's head")
    if not datums and row["datums"][0] == 0 and row["forces_TE"]:
        warnings.append(
            f"{row['name']} with no datum reference locates nothing"
            " relative to anything — legal ink, suspicious sheet")
    return warnings


def gdt_cells(entry: dict) -> list[dict]:
    """The frame as ORDERED CELLS for the painter (and its width
    math): [|glyph][value⌀+mod][A][B][C]. Value and modifiers SHARE
    the cell (6.4.1); every datum gets its OWN (6.4.3); the common
    datum A-B is the one legitimate shared cell (ISO cl.6.1)."""
    row = CONTROL_TABLE[entry["sym"]]
    tol = str(entry["tol"]).strip()
    for tofu in _DIAM:                          # entered ⌀ → paper Ø
        if tol.startswith(tofu):
            tol = "\u00d8 " + tol[len(tofu):].strip()
            break
    text = f"{tol} {entry['mod']}" if entry.get("mod") else tol
    cells = [dict(kind="glyph", key=entry["sym"]),
             dict(kind="text", s=text)]
    if entry.get("proj"):
        cells.append(dict(kind="proj", s="P " + str(entry["proj"]).strip()))
    cells += [dict(kind="datum", s=str(d))
              for d in entry.get("datums", [])]
    assert row                          # the key came from the table
    return cells


def key_for_name(label: str) -> str | None:
    """Dialog label -> table key (the combo speaks English, the
    entry speaks keys)."""
    return _NAMES.get(label.strip())
