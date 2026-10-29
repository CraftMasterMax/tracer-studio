"""M165 rung 1 - the value AT THE CURSOR: an inline chip editor.

ChipField is a canvas-child ExprField pixel-glued to a Distance/Radius/
Diameter chip rect (paint-derived: chip_rect is the SAME math the painter
runs, so seat and paint cannot drift).  Grammar: number | expression |
named-param | trailing-unit (cmdpanel.parse_scalar, native millimetres),
or "=expr" to bind the dimension to the parameter sheet - M89's law, the
"=" prefix IS the old fx row, and a plain number on a bound chip
releases it.  Enter/focus-out commits one boundary, Esc rewinds and
closes, invalid input paints the danger token and refuses.  Rung 2
brought the ANGLE chips in too: their field speaks BARE DEGREES - no
units, no expressions, no binding (M89's lengths-only law) - and the
live panel's last dim leg retired with it."""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt, Signal

from ..core import params
from ..core.sketch.constraints import Angle, AngleBetween, Radius
from ..core.sketch.entities import Circle
from .cmdpanel import ExprField, parse_scalar          # the ONE eval helper
from .theme import DARK

# chip metrics: cancel the global 24px QLineEdit floor (theme MIN_H) or
# the field is a panel row pasted over the chip, not the chip itself
_CHIP_QSS = "QLineEdit { min-height: 0px; padding: 0px 2px; }"


def is_dia(c) -> bool:
    """M98 probe: a Radius ON A CIRCLE is a diameter chip (se's dia law,
    was the panel's field-label branch)."""
    return isinstance(c, Radius) and isinstance(c.curve, Circle)


def is_angle(c) -> bool:
    return isinstance(c, (Angle, AngleBetween))


def parse_degrees(text: str) -> float:
    """Rung 2 grammar: an angle field wants a BARE number of degrees.
    No units, no expressions, no named params (the panel row was a plain
    double too - expressions are M89's LENGTH law, never angles), no
    binding; the chip speaks [0, 180), exactly what it displays."""
    t = str(text).strip()
    if t.startswith("="):
        raise params.ParamError("angles do not bind - fx is lengths-only")
    try:
        v = float(t)
    except ValueError:
        raise params.ParamError(
            f"angle wants bare degrees, not {text!r}") from None
    if not 0.0 <= v < 180.0:
        raise params.ParamError(f"angle out of range [0, 180): {text!r}")
    return v


def bare_value(c) -> float:
    """The number the chip shows minus its decoration: circles speak Ø
    (2x), angles speak their own degrees (the same % 180 the painter
    used), arcs and distances speak their own value."""
    if is_angle(c):
        return math.degrees(float(c.value)) % 180.0
    return 2 * float(c.value) if is_dia(c) else float(c.value)


def chip_rect(fm, pos, text: str) -> QRectF:
    """ONE rect math for painter and field - the painter builds its chip
    AND its hit entry from this, the field is seated from the same."""
    br = fm.boundingRect(text)
    return QRectF(pos.x() - br.width() / 2 - 5,
                  pos.y() - br.height() / 2 - 2,
                  br.width() + 10, br.height() + 4)


class ChipField(ExprField):
    """The chip BECOMES the field: zero-margin ExprField sized to
    chip_rect, focus on the inner edit (the wrapper stays NoFocus, so
    ExprField's hasFocus law delegates through the child)."""

    closeRequested = Signal()          # Esc / unchanged Enter / focus-out

    def __init__(self, canvas, c):
        bare = bare_value(c)
        super().__init__(value=bare, step=0.1, suffix="", parent=canvas)
        self.constraint = c                        # re-seat identity (is)
        self._provider = canvas._params_provider
        self._angle = is_angle(c)                  # rung 2 grammar switch
        self.setFocusPolicy(Qt.NoFocus)
        self.edit.setAlignment(Qt.AlignCenter)
        pref = f"{bare:.2f}"                       # the chip's number,
        self.edit.setText(pref)                    #  selected on open so
        self._base = pref                          #  typing replaces it
        self.edit.setPlaceholderText(
            "\u00b0" if self._angle else           # context lives in the
            "\u00d8 mm" if is_dia(c) else          #  placeholder, never
            "R mm" if isinstance(c, Radius)        #  the editable text
            else "mm")
        self.edit.setStyleSheet(_CHIP_QSS)
        self.committed.connect(canvas._on_chip_commit)
        self.closeRequested.connect(canvas._on_chip_close)
        rect = next((r for r, cc in canvas._dim_hits if cc is c), None)
        if rect is not None:                       # seat: the SAME rect
            self.setGeometry(rect.toRect().adjusted(-2, -2, 2, 2))

    def set_value_mm(self, mm: float):             # wheel scrub: cp's
        self._mm = float(mm)                       #  version hard-codes
        self._base = self._fmt(self._mm)           #  " mm" - the chip is
        self.edit.setText(self._base)              #   unit-naked

    # ---- grammar: plain rides parse_scalar (mm); "=..." is M89's fx;
    # angles speak BARE DEGREES and nothing else (rung 2) ----
    def _eval(self, text):
        t = str(text).strip()
        if self._angle:
            return parse_degrees(t)
        vals, sc = self._provider()
        if t.startswith("="):                      # the old lstrip law
            expr = t.lstrip("=").strip()
            if not expr:
                raise params.ParamError(
                    'fx wants an expression after "="')
            return float(params.eval_expr(expr, vals)) * sc   # fx: doc
        return parse_scalar(t, vals)               #  units, no units

    # ---- boundaries: TEXT is the change truth (a same-number "=width"
    # re-bind must still land - cp's numeric check would eat it) ----
    def _finish(self):
        try:
            mm = self._eval(self.edit.text())
        except params.ParamError as e:
            self._set_bad(True, str(e))            # red + tooltip...
            self.edit.setText(self._base)          #  ...then honest rewind
            return                                 # stays OPEN to retry
        self._set_bad(False)
        changed = self.edit.text() != self._base
        self._mm, self._base = mm, self.edit.text()
        if changed:
            self.committed.emit(mm)                # commit reads RAW text
        else:
            self.closeRequested.emit()             # Enter on untouched:

    def _set_bad(self, bad, why=""):               #  close, no trace
        if bad == self._bad and not why:
            return
        self._bad = bad
        # cp's _set_bad REPLACES the sheet - that would resurrect the
        # 24px floor mid-edit and burst the chip; compose ONE rule
        # instead - and INSIDE the braces: a border dangling after a
        # closed selector does not parse (measured: never painted).
        self.edit.setStyleSheet(
            "QLineEdit { min-height: 0px; padding: 0px 2px;"
            + (f" border: 1px solid {DARK['danger']};" if bad else "")
            + " }")
        self.edit.setToolTip(why if bad else "")
        self.invalid.emit(bad)

    # ---- key claim: Esc closes (QTest sends KeyPress - answer both),
    # Ctrl|Meta chords die as SHORTCUTS only (KeyPress stays in the
    # field: QLineEdit's own undo lives) ----
    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() in (ev.Type.KeyPress,
                                              ev.Type.ShortcutOverride):
            if ev.key() == Qt.Key.Key_Escape:
                self._escape()                     # rewind (cp law)
                self.closeRequested.emit()         # ...and close
                ev.accept()
                return True
            if ev.type() == ev.Type.ShortcutOverride and \
                    ev.modifiers() & (Qt.ControlModifier | Qt.MetaModifier):
                ev.accept()
                return True
        return super().eventFilter(obj, ev)        # wheel scrub rides


def open(canvas, c):
    """The patchable seam - module-global ON PURPOSE, the twin of
    cmdpanel.run: conftest.script_dim_edit patches THIS, so headless
    pins re-target in one line.  Every real route comes through the
    canvas's _open_dim_editor (M90 drop + ring live there)."""
    ed = ChipField(canvas, c)
    canvas._dim_edit = ed
    ed.show()
    ed.raise_()
    ed.edit.setFocus()
    ed.edit.selectAll()                            # type immediately
    canvas.update()                                # first paint re-seats
    return ed
