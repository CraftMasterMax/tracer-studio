"""Document Measures (M60): one unit setting drives every readout.

The geometry's internal truth stays millimetres — this module is only
about SPEAKING the numbers: the status bar, the inspector, the measure
card.  Fusion's Tools ▸ Document Measures changes the vocabulary, never
the model, and so do we: files stay pure millimetre, unit ships as
metadata (doc.units).

Formatting keeps the old voice exactly: mm output is byte-identical to
the pre-M60 f-strings that the test suite pins.
"""
from __future__ import annotations

LABEL = {"mm": "mm", "cm": "cm", "inch": "in"}
PER_MM = {"mm": 1.0, "cm": 10.0, "inch": 25.4}   # millimetres per unit


def val(v_mm: float, unit: str = "mm") -> float:
    return float(v_mm) / PER_MM[unit]


def L(v_mm: float, unit: str = "mm") -> str:
    """A length: '12 mm', '1.2 cm', '0.472441 in' (:g voice)."""
    return f"{val(v_mm, unit):g} {LABEL[unit]}"


def D(v_mm: float, unit: str = "mm", prec: int = 2) -> str:
    """A length with fixed precision (measure gaps: '0.4724 in')."""
    return f"{val(v_mm, unit):.{prec}f} {LABEL[unit]}"


def A(v_mm2: float, unit: str = "mm", prec: int = 1,
      sep: bool = True) -> str:
    f = PER_MM[unit]
    g = "," if sep else ""
    return f"{float(v_mm2) / (f * f):{g}.{prec}f} {LABEL[unit]}²"


def V(v_mm3: float, unit: str = "mm", prec: int = 1) -> str:
    f = PER_MM[unit]
    return f"{float(v_mm3) / (f ** 3):,.{prec}f} {LABEL[unit]}³"
