"""M163 rung 1 - the live command panel engine: the panel IS the command.

Fusion's command dialogs make you commit to numbers you could not see in
the model.  The lane-C machinery report (fleet specs/m163_param_
transaction_internals.md) mined how KiCad, FreeCAD and Inkscape ship the
alternative - apply-without-modal - and this module is the PySide6
translation of exactly that trio's laws:

* commit boundary = the moment a DISCRETE INTENTION completes (Enter /
  focus-out / slider release / the checkbox click itself), never a
  keystroke  (KiCad's wxEVT_PG_CHANGED split);
* undo granularity = ONE journal step per field-commit session; repeat
  round-trips on the same (field) fold into the step already open, and
  a session that mutated nothing leaves NO trace - here expressed on
  MainWindow's snapshot journal via capture()/rollback, the house
  idiom at mw:2091 ("rejected: no edit happened");
* the coalescing key RESETS on selection change, panel close and every
  explicit confirmation, so a deliberate step never merges with the
  next incidental round-trip  (Inkscape maybeDone + swapUndoLabel);
* preview reads pending values and renders only - it must NEVER write
  the model  (the SKIP_UNDO / PNS private-world rule).

The engine ships inert: no command migrates in this rung.  Field kinds,
Remember Values and cmddialog.ask() all stay as the headless seam until
carriers migrate rung by rung.
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent, QWheelEvent
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..core import params, units
from .theme import DARK

# units.py has no parser (recon HOOK 4) - this is it, law-blessed: a unit
# may only sit at the END ("2mm + 4" is not a number, and we say why).
_UNIT_RE = re.compile(r"^(?P<expr>.+?)\s*(?P<unit>mm|cm|inch)?$", re.I)


def parse_scalar(text: str, values: dict | None = None) -> float:
    """Number | arithmetic | named-parameter reference | trailing unit,
    evaluated to MILLIMETRES.  Raises params.ParamError on anything else
    (the same error family the parameter sheet already speaks)."""
    m = _UNIT_RE.match(str(text).strip())
    if not m:
        raise params.ParamError(f"can't read {text!r} as a number")
    unit = (m.group("unit") or "mm").lower()
    mm = params.eval_expr(m.group("expr"), values)      # ParamError passes
    return mm * units.PER_MM[unit]


class ExprField(QWidget):
    """One numeric input that speaks numbers, formulas and parameters.

    Text is the raw entry; the VALUE is evaluated millimetres.  Invalid
    input paints the field with the danger token (never a hex literal -
    the M112 law) and refuses to commit; Escape rewinds to the last
    accepted text; the wheel scrubs ONLY while focused (FreeCAD 1.0's
    fix), Ctrl fine, Shift coarse.
    """

    committed = Signal(float)          # a discrete intention completed
    invalid = Signal(bool)             # red-on / red-off (Commit gates)

    def __init__(self, value: float = 0.0, step: float = 0.1,
                 suffix: str = " mm", parent=None):
        super().__init__(parent)
        self._mm = float(value)
        self._step = float(step)
        self.values: dict | None = None      # carrier injects param sheet
        self.edit = QLineEdit(self._fmt(self._mm) + suffix)
        self.edit.setAlignment(Qt.AlignRight)
        self._base = self.edit.text()        # what Esc rewinds to
        self._bad = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit)
        self.edit.editingFinished.connect(self._finish)
        self.edit.installEventFilter(self)      # Esc + wheel ride the filter

    # ---- value ---------------------------------------------------------
    def value_mm(self) -> float:
        return self._mm

    def set_value_mm(self, mm: float):
        self._mm = float(mm)
        self._base = self._fmt(self._mm) + " mm"
        self.edit.setText(self._base)

    @staticmethod
    def _fmt(v: float) -> str:
        return f"{v:.2f}".rstrip("0").rstrip(".") or "0"

    def _eval(self, text: str) -> float:
        return parse_scalar(text, self.values)

    # ---- boundaries ------------------------------------------------------
    def _finish(self):                      # Enter or focus-out
        try:
            mm = self._eval(self.edit.text())
        except params.ParamError as e:
            self._set_bad(True, str(e))
            self.edit.setText(self._base)   # red, then honest rewind
            return
        self._set_bad(False)
        changed = mm != self._mm
        self._mm, self._base = mm, self.edit.text()
        if changed:                         # no-change emits NOTHING
            self.committed.emit(mm)

    def _escape(self):
        self._set_bad(False)
        self.edit.setText(self._base)       # focus-out==Esc; never silent
        if self.hasFocus():                 # commit nothing, leave cleanly
            self.edit.clearFocus()

    def _set_bad(self, bad: bool, why: str = ""):
        if bad == self._bad and not why:
            return
        self._bad = bad
        self.edit.setStyleSheet(
            f"border: 1px solid {DARK['danger']};" if bad else "")
        self.edit.setToolTip(why if bad else "")
        self.invalid.emit(bad)

    def is_invalid(self) -> bool:
        return self._bad

    # ---- focus-gated wheel scrub + Esc (no escapePressed in PySide6) ----
    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() in (ev.Type.KeyPress,
                                              ev.Type.ShortcutOverride):
            if ev.key() == Qt.Key.Key_Escape:
                self._escape()
                ev.accept()
                return True
        if obj is self.edit and ev.type() == ev.Type.Wheel:
            if not self.edit.hasFocus():
                return False                # passes through, FreeCAD law
            step = self._step
            mods = ev.modifiers()
            if mods & Qt.ControlModifier:
                step /= 10.0
            elif mods & Qt.ShiftModifier:
                step *= 10.0
            dy = 1 if ev.angleDelta().y() > 0 else -1
            mm = round(self._mm + dy * step, 6)
            self.set_value_mm(mm)
            self.committed.emit(mm)         # a wheel notch IS an intention
            ev.accept()
            return True
        return super().eventFilter(obj, ev)


class ParamTransaction:
    """One field-commit session == one undo step; noise leaves no trace.

    Wraps MainWindow's snapshot journal's ``capture(desc)``: the capture
    is LAZY - pushed at the first MUTATED commit of a session, never at
    panel-open, never for a no-op (FreeCAD's openTransaction "only
    created if there are actual changes").  Same key folds into the
    step already open; rotate() ends the session.
    """

    def __init__(self, capture):
        self._capture = capture
        self._open_key: str | None = None

    def apply(self, key: str, desc: str, mutated: bool = True):
        if not mutated:
            return                       # no-change emits NOTHING
        if key == self._open_key:
            return                       # folded into the open step
        self._capture(desc)
        self._open_key = key

    def rotate(self):
        """Selection changed / panel closed / explicit confirmation:
        the next edit MUST open a fresh undo step (swapUndoLabel law)."""
        self._open_key = None


class CmdPanel(QWidget):
    """The modeless command surface.  Declared with the SAME field
    language as cmddialog.ask(), plus a command id for value memory.
    Header = accent bar, command name, green Commit / red Abort - the
    press-pull command-header anatomy, not an OK/Cancel dialog (the
    structural anti-modal test asserts exactly that there is no
    QDialogButtonBox in here).

    Signals:
      values_committed(dict, key)   one boundary crossed (preview+apply)
      finished(dict | None)         Commit -> values, Abort/Esc -> None
    """

    values_committed = Signal(dict, str)
    finished = Signal(object)

    def __init__(self, title: str, fields: list[dict],
                 command_id: str = "", parent=None):
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle(title)
        self.command_id = command_id
        self._specs = {f["key"]: f for f in fields}
        self._edits: dict[str, QWidget] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        bar = QWidget()
        bar.setFixedSize(4, 28)
        bar.setStyleSheet(f"background: {DARK['accent']};"
                          f" border-radius: 2px;")
        head.addWidget(bar)
        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel(title)
        name.setStyleSheet(f"font-weight: 600; font-size: 14px;"
                           f" color: {DARK['fg']};")
        col.addWidget(name)
        sub = QLabel("Live command - edits apply as you commit")
        sub.setStyleSheet(f"color: {DARK['fg_faint']};")
        col.addWidget(sub)
        head.addLayout(col)
        head.addStretch(1)
        self.btn_abort = QPushButton("Abort")
        self.btn_commit = QPushButton("Commit")
        for b in (self.btn_abort, self.btn_commit):
            b.setFixedHeight(26)
        self.btn_commit.setStyleSheet(
            f"background: {DARK['success']}; color: {DARK['bg0']};")
        self.btn_abort.setStyleSheet(
            f"background: {DARK['danger']}; color: {DARK['bg0']};")
        head.addWidget(self.btn_abort)
        head.addWidget(self.btn_commit)
        root.addLayout(head)

        body = QVBoxLayout()
        body.setSpacing(6)
        root.addLayout(body)
        for f in fields:
            body.addWidget(self._make(f))

        self.btn_commit.clicked.connect(self._commit)
        self.btn_abort.clicked.connect(lambda: self.finished.emit(None))
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

    # ---- fields -----------------------------------------------------------
    def _make(self, f: dict) -> QWidget:
        key, kind, label = f["key"], f["kind"], f["label"]
        if kind == "double":
            w = ExprField(f.get("default", 0.0),
                          step=f.get("step", 0.1),
                          suffix=f.get("suffix", " mm"))
            w.committed.connect(
                lambda v, k=key: self.values_committed.emit(
                    self.values(), f"{self.command_id}:{k}"))
            w.invalid.connect(self._gate)
            self._edits[key] = w
            return self._row(label, w)
        if kind == "combo":
            w = QComboBox()
            w.addItems([str(c) for c in f["choices"]])
            if f.get("default") is not None:
                i = w.findText(str(f["default"]))
                if i >= 0:
                    w.setCurrentIndex(i)
            w.activated.connect(                 # one click IS the step
                lambda _i, k=key: self.values_committed.emit(
                    self.values(), f"{self.command_id}:{k}"))
            self._edits[key] = w
            return self._row(label, w)
        if kind == "check":
            w = QCheckBox(label)
            w.setChecked(bool(f.get("default", False)))
            w.toggled.connect(
                lambda _c, k=key: self.values_committed.emit(
                    self.values(), f"{self.command_id}:{k}"))
            self._edits[key] = w
            return w
        raise ValueError(f"cmdpanel: field kind {kind!r} not in rung 1")

    @staticmethod
    def _row(label: str, w: QWidget) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(label)
        lab.setMinimumWidth(96)
        lay.addWidget(lab)
        lay.addWidget(w, 1)
        return row

    def value(self, key: str):
        w = self._edits[key]
        if isinstance(w, ExprField):
            return w.value_mm()
        if isinstance(w, QComboBox):
            return w.currentText()
        if isinstance(w, QCheckBox):
            return w.isChecked()
        raise KeyError(key)

    def values(self) -> dict:
        return {k: self.value(k) for k in self._edits}

    def set_param_values(self, values: dict):
        """The carrier injects the document's resolved parameter sheet so
        dimension fields can say wall*2 (feature#6, expression-in-field)."""
        for w in self._edits.values():
            if isinstance(w, ExprField):
                w.values = values

    # ---- commit / abort ----------------------------------------------------
    def _gate(self, bad: bool):
        self.btn_commit.setEnabled(not bad)

    def _commit(self):
        self.finished.emit(self.values())

    def keyPressEvent(self, ev: QKeyEvent):
        if ev.key() == Qt.Key.Key_Escape:
            self.finished.emit(None)          # Esc aborts the whole verb
            return
        super().keyPressEvent(ev)
