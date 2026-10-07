"""ISO 286 limits & fits — the callout brain behind 'Ø30 H7 (+0.021/0)'.

Fusion's drawing dimensions carry fit classes with live tolerance
stack-up; this is Tracer's honest first step: the maker-common slice
of ISO 286 as pure data, exactly as the standard intends it — the
nominal geometry stays nominal (a dimension carries truth; the model
carries shape), and the class decorates the paper.

Scope v1 (the rows the fleet could verify end to end):
  * IT5..IT9 grades, nominal sizes > 0 to 120 mm
  * hole basis H; shafts h, g, k, n, p  — the five classes a maker
    actually reaches for (sliding, location, light drive, press)
  * clearance / transition / interference arithmetic for a fit pair

The IT column is [V] (transcribed from ISO 286-2-compiled tables,
cross-checked cell-for-cell against two OSS datasets); fundamental
deviations for g/n/p are [H]-anchored transcriptions — every one
reproduces published limit tables (25 g6 = −8/−21, 30 n6 = +8/+21,
10 p6 = +15/+24, 110-class sanity via IT9 = 87). Hole counterparts
K/N/P and shafts j/m/r/s/t/u need grade-dependent Δ rules and are
deliberately absent: raise rather than guess.

Units: inputs mm, tables µm (ISO 286's own unit); public API returns
mm limits and µm deviations as named. All values valid at 20 °C.
"""
from __future__ import annotations

# ---- the tables ---------------------------------------------------------------
# Coarse size bands (ISO 286-1 Table 1): upper bounds, inclusive, mm.
_IT_BOUNDS = (3, 6, 10, 18, 30, 50, 80, 120)
# IT grade -> µm per band above. Index 0 = smallest size.
_IT = {
    5: (4, 5, 6, 8, 9, 13, 15, 18),
    6: (6, 8, 9, 11, 13, 16, 19, 22),
    7: (10, 12, 15, 18, 21, 25, 30, 35),
    8: (14, 18, 22, 27, 33, 39, 46, 54),
    9: (25, 30, 36, 43, 52, 62, 74, 87),
}
# Fundamental deviations use FINER bands >10 mm (Ø20 and Ø25 g6 differ).
_DEV_BOUNDS = (3, 6, 10, 14, 18, 24, 30, 40, 50, 65, 80, 100, 120)
_G_ES = (-4, -5, -6, -7, -7, -7, -8, -9, -9, -10, -11, -13, -15)
_N_EI = (4, 5, 6, 7, 7, 8, 8, 10, 10, 12, 13, 15, 15)
_P_EI = (12, 12, 15, 18, 18, 22, 22, 26, 26, 32, 32, 38, 38)

MAX_SIZE = _IT_BOUNDS[-1]          # mm, the table's reach in v1


def _band(bounds: tuple[int, ...], nominal: float) -> int:
    if not nominal > 0:
        raise ValueError(f"nominal size must be > 0, got {nominal}")
    for i, hi in enumerate(bounds):
        if nominal <= hi:
            return i
    raise ValueError(f"Ø{nominal:g} mm is beyond the v1 table "
                     f"(> {bounds[-1]} mm)")


def it(nominal: float, grade: int) -> int:
    """Standard tolerance IT(grade) in µm for this nominal size."""
    try:
        col = _IT[grade]
    except KeyError:
        raise ValueError(f"grade IT{grade} unsupported (v1: "
                         f"IT{min(_IT)}-IT{max(_IT)})") from None
    return col[_band(_IT_BOUNDS, nominal)]


def parse(cls: str) -> tuple[bool, str, int]:
    """'H7' -> (is_hole=True, 'H', 7); 'g6' -> (False, 'g', 6)."""
    s = cls.strip()
    if len(s) < 2 or not s[-1].isdigit():
        raise ValueError(f"{cls!r} is not an ISO 286 class like 'H7'")
    letter, grade = s[:-1], int(s[-1])
    is_hole = letter.isupper()
    if (is_hole and letter != "H") or (not is_hole and letter not in "hgknp"):
        raise ValueError(f"class {letter!r} not in v1 "
                         f"(holes H; shafts h g k n p)")
    if grade not in _IT:
        raise ValueError(f"grade {grade} unsupported (v1: IT"
                         f"{min(_IT)}-IT{max(_IT)})")
    return is_hole, letter, grade


def deviation(nominal: float, cls: str) -> tuple[int, int]:
    """(lower, upper) fundamental limits in µm relative to nominal:
    holes (EI, ES), shafts (ei, es)."""
    is_hole, letter, grade = parse(cls)
    tol = it(nominal, grade)
    if is_hole:                                   # H: EI = 0, ES = +IT
        return 0, tol
    if letter == "h":                             # h: es = 0, ei = -IT
        return -tol, 0
    i = _band(_DEV_BOUNDS, nominal)
    if letter == "g":
        es = _G_ES[i]
        return es - tol, es
    if letter == "k":                             # k: ei = 0 (≤500)
        return 0, tol
    if letter == "n":
        ei = _N_EI[i]
        return ei, ei + tol
    ei = _P_EI[i]                                 # p
    return ei, ei + tol


def limits(nominal: float, cls: str) -> tuple[float, float]:
    """(min, max) size in millimetres for Ø`nominal` wearing `cls`."""
    lo, hi = deviation(nominal, cls)
    return round(nominal + lo / 1000.0, 4), round(nominal + hi / 1000.0, 4)


def fit(nominal: float, pair: str) -> dict:
    """Analyse a hole/shaft pair like 'H7/g6' at this nominal size.

    Returns clearance extremes in µm (positive = gap, negative =
    interference) and the taxonomy:
      Xmin = EI − es   (tightest assembly)
      Xmax = ES − ei   (loosest assembly)
    """
    parts = pair.split("/")
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise ValueError(f"{pair!r} is not a pair like 'H7/g6'")
    hole_cls, shaft_cls = (p.strip() for p in parts)
    h_lo, h_hi = deviation(nominal, hole_cls)
    s_lo, s_hi = deviation(nominal, shaft_cls)
    if not (hole_cls.isupper() and shaft_cls.islower()):
        raise ValueError(f"{pair!r}: hole first (CAPS), shaft second "
                         f"(lower)")
    xmin, xmax = h_lo - s_hi, h_hi - s_lo
    kind = ("clearance" if xmin >= 0 else
            "interference" if xmax <= 0 else "transition")
    return {"hole": (h_lo, h_hi), "shaft": (s_lo, s_hi),
            "xmin_um": xmin, "xmax_um": xmax, "kind": kind}


def fmt_um(um: int) -> str:
    """µm offset as ISO 129 decimal mm text: +21 -> '+0.021', 0 -> '0'."""
    return "0" if um == 0 else f"{um / 1000.0:+.3f}"


def callout(nominal: float, cls: str) -> str:
    """The paper furniture for one dimension: 'Ø30 H7 (+0.021/0)'.
    Fit PAIRS carry no inline limits — draughtsmen write 'Ø30 H7/g6'
    and the limits belong to each mating part's own drawing."""
    if "/" in cls:
        return cls
    lo, hi = deviation(nominal, cls)
    return f"{cls} ({fmt_um(hi)}/{fmt_um(lo)})"
