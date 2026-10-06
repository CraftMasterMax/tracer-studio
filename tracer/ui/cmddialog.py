"""The unified command-dialog shell — Fusion's command-dialog anatomy:
a header strip, grouped fields, Remember Values, OK/Cancel.

Commands declare their fields declaratively through :func:`ask`, which
replaces Fusion-unlike chains of QInputDialog prompts with ONE dialog
holding every input (Circular Pattern's five prompts become one form,
exactly like Fusion's).  Remember Values persists a command's numbers
per session when the user opts in — Fusion's behaviour to the letter.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit,
                               QSpinBox, QVBoxLayout, QWidget)

from .theme import DARK

_REMEMBERED: dict[str, dict] = {}       # remember_key -> last values
_REMEMBER_ON: dict[str, bool] = {}      # remember_key -> checkbox state


class Shell:
    """Drop-in replacements for the four QInputDialog statics, same
    signatures — but rendered with the Fusion command chrome (header
    strip, spin-box with suffix, single focusable field).  One class so
    tests can retarget every prompt patch in one place.
    """

    @staticmethod
    def _vals(parent, title, label, kind, spec):
        return ask(parent, title, [dict(key="v", label=label, kind=kind,
                                        **spec)],
                   remember_key=f"{title}\u0000{label}")

    @staticmethod
    def getText(parent, title, label, text=""):
        vals = Shell._vals(parent, title, label, "text",
                           dict(default=str(text)))
        return (vals["v"], True) if vals else ("", False)

    @staticmethod
    def getDouble(parent, title, label, value=0.0, mn=-1e6, mx=1e6,
                  decimals=2, suffix=""):
        vals = Shell._vals(parent, title, label, "double",
                           dict(default=float(value), min=mn, max=mx,
                                decimals=decimals, suffix=suffix))
        return (vals["v"], True) if vals else (0.0, False)

    @staticmethod
    def getInt(parent, title, label, value=0, mn=-1e6, mx=1e6, step=1):
        vals = Shell._vals(parent, title, label, "int",
                           dict(default=int(value), min=mn, max=mx))
        return (vals["v"], True) if vals else (0, False)

    @staticmethod
    def getItem(parent, title, label, items, current=0, editable=False):
        items = list(items)
        vals = Shell._vals(parent, title, label, "combo",
                           dict(choices=items))
        return (vals["v"], True) if vals else \
            ((items[current] if items else ""), False)


class CommandDialog(QDialog):
    def __init__(self, title: str, parent=None,
                 remember_key: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._key = remember_key
        self._fields: dict[str, QWidget] = {}
        self._groups: dict[str, QFormLayout] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        bar = QWidget()
        bar.setFixedSize(4, 28)
        bar.setStyleSheet(f"background: {DARK['accent']}; border-radius: 2px;")
        head.addWidget(bar)
        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel(title)
        name.setStyleSheet(f"font-weight: 600; font-size: 14px;"
                           f" color: {DARK['fg']};")
        col.addWidget(name)
        sub = QLabel("Tracer Studio command")
        sub.setStyleSheet(f"color: {DARK['fg_faint']};")
        col.addWidget(sub)
        head.addLayout(col)
        head.addStretch(1)
        root.addLayout(head)

        self._body = QVBoxLayout()
        self._body.setSpacing(8)
        root.addLayout(self._body)

        foot = QHBoxLayout()
        self._remember = QCheckBox("Remember Values")
        if remember_key:
            self._remember.setChecked(_REMEMBER_ON.get(remember_key, False))
        else:
            self._remember.setEnabled(False)
        foot.addWidget(self._remember)
        foot.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        foot.addWidget(bb)
        root.addLayout(foot)

    # ---- fields ----------------------------------------------------------
    def _form(self, group: str) -> QFormLayout:
        if group not in self._groups:
            if group:
                box = QGroupBox(group)
                f = QFormLayout(box)
                f.setSpacing(6)
                box.setLayout(f)
                self._body.addWidget(box)
            else:
                f = QFormLayout()
                f.setSpacing(6)
                self._body.addLayout(f)
            self._groups[group] = f
        return self._groups[group]

    def add_combo(self, key, label, choices, group=""):
        w = QComboBox()
        w.addItems([str(c) for c in choices])
        self._form(group).addRow(label, w)
        self._fields[key] = w
        return self

    def add_double(self, key, label, default, mn=-1e6, mx=1e6,
                   decimals=2, suffix=" mm", group=""):
        w = QDoubleSpinBox()
        w.setRange(mn, mx)
        w.setDecimals(decimals)
        w.setSuffix(suffix)
        w.setValue(default)
        w.setFocusPolicy(w.focusPolicy() | w.focusPolicy().ClickFocus)
        w.lineEdit().selectAll()
        self._form(group).addRow(label, w)
        self._fields[key] = w
        return self

    def add_int(self, key, label, default, mn=1, mx=100000, group=""):
        w = QSpinBox()
        w.setRange(mn, mx)
        w.setValue(default)
        self._form(group).addRow(label, w)
        self._fields[key] = w
        return self

    def add_check(self, key, label, default=False, group=""):
        w = QCheckBox(label)
        w.setChecked(default)
        self._form(group).addRow(w)
        self._fields[key] = w
        return self

    def add_text(self, key, label, default="", group=""):
        w = QLineEdit(str(default))
        w.selectAll()
        self._form(group).addRow(label, w)
        self._fields[key] = w
        return self

    def add_multiline(self, key, label, default="", group=""):
        w = QPlainTextEdit(str(default))
        w.setFixedHeight(150)
        w.setTabChangesFocus(True)
        self._form(group).addRow(label, w)
        self._fields[key] = w
        return self

    def value(self, key):
        w = self._fields[key]
        if isinstance(w, QComboBox):
            return w.currentText()
        if isinstance(w, QPlainTextEdit):
            return w.toPlainText()
        if isinstance(w, QSpinBox):
            return int(w.value())
        if isinstance(w, QDoubleSpinBox):
            return float(w.value())
        if isinstance(w, QCheckBox):
            return w.isChecked()
        return w.text()

    def values(self) -> dict:
        return {k: self.value(k) for k in self._fields}

    # ---- Remember Values ---------------------------------------------------
    def _prefill(self):
        if not self._key or not self._remember.isChecked():
            return
        vals = _REMEMBERED.get(self._key, {})
        for k, v in vals.items():
            if k not in self._fields:
                continue
            w = self._fields[k]
            if isinstance(w, (QDoubleSpinBox, QSpinBox)):
                w.setValue(v)
            elif isinstance(w, QCheckBox):
                w.setChecked(v)
            elif isinstance(w, QComboBox) and str(v) in (
                    w.itemText(i) for i in range(w.count())):
                w.setCurrentText(str(v))

    def accept(self):
        if self._key and self._remember.isChecked():
            _REMEMBERED[self._key] = self.values()
        elif self._key:
            _REMEMBERED.pop(self._key, None)
        if self._key:
            _REMEMBER_ON[self._key] = self._remember.isChecked()
        super().accept()


def ask(parent, title, fields, remember_key=None) -> dict | None:
    """One Fusion-style dialog for a whole command.

    fields: list of dicts {key, label, kind, group?, default?, choices?,
    min?, max?, decimals?, suffix?} with kind in
    {"combo","double","int","check"}; returns {key: value} or None on
    Cancel.
    """
    d = CommandDialog(title, parent, remember_key)
    combo_keys = [f["key"] for f in fields if f["kind"] == "combo"]
    for f in fields:
        kind, g = f["kind"], f.get("group", "")
        if kind == "combo":
            d.add_combo(f["key"], f["label"], f["choices"], g)
            if len(combo_keys) == 1:      # convenience: single choice list
                d._fields[f["key"]].setCurrentIndex(0)
        elif kind == "double":
            d.add_double(f["key"], f["label"], f.get("default", 0.0),
                         f.get("min", -1e6), f.get("max", 1e6),
                         f.get("decimals", 2),
                         f.get("suffix", " mm"), g)
        elif kind == "int":
            d.add_int(f["key"], f["label"], f.get("default", 1),
                      f.get("min", 1), f.get("max", 100000), g)
        elif kind == "check":
            d.add_check(f["key"], f["label"], f.get("default", False), g)
        elif kind == "text":
            d.add_text(f["key"], f["label"], f.get("default", ""), g)
        elif kind == "multiline":
            d.add_multiline(f["key"], f["label"], f.get("default", ""), g)
        else:
            raise ValueError(f"unknown field kind {kind!r}")
    d._prefill()
    if d.exec_() != QDialog.DialogCode.Accepted:
        return None
    return d.values()
