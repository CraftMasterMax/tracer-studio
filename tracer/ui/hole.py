"""Hole command dialog — Fusion's Hole panel condensed for maker CAD.

The drilled diameter comes from the sketch circle; this dialog sets the
depth and the optional counterbore / countersink, exactly the three hole
types a maker reaches for (clearance holes, socket-head cap screws, flat
wood-screw seats).  ``HoleDialog.ask`` returns a values dict or None.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QLabel, QVBoxLayout)

TYPES = ("Simple", "Counterbore", "Countersink")


def _spin(value: float, lo: float = 0.01, hi: float = 1e5,
          suffix: str = " mm") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(2)
    s.setSuffix(suffix)
    s.setValue(value)
    return s


class HoleDialog(QDialog):
    def __init__(self, parent=None, diameters=(6.0,)):
        super().__init__(parent)
        self.setWindowTitle("Hole")
        lay = QVBoxLayout(self)
        di = ", ".join(f"{d:g}" for d in diameters)
        head = QLabel(f"{len(diameters)} circle(s) — hole Ø {di}")
        head.setObjectName("dim")
        lay.addWidget(head)

        form = QFormLayout()
        form.setSpacing(6)
        self._form = form
        self.type = QComboBox()
        self.type.addItems(TYPES)
        self.depth = _spin(5.0)
        self.through = QCheckBox("Through all")
        self.cb_dia = _spin(max(diameters) + 4.0)
        self.cb_depth = _spin(4.0)
        self.cs_dia = _spin(max(diameters) + 5.0)
        self.cs_angle = QComboBox()
        self.cs_angle.setEditable(True)
        for a in (82.0, 90.0, 120.0):
            self.cs_angle.addItem(f"{a:g}°", a)
        self.cs_angle.setCurrentIndex(1)          # 90° default
        form.addRow("Type", self.type)
        form.addRow("Depth", self.depth)
        form.addRow(" ", self.through)
        r = form.rowCount()
        form.addRow("Cbore Ø", self.cb_dia)
        form.addRow("Cbore depth", self.cb_depth)
        self._cb_rows = (r, r + 1)
        r = form.rowCount()
        form.addRow("Csink Ø", self.cs_dia)
        form.addRow("Csink angle", self.cs_angle)
        self._cs_rows = (r, r + 1)
        lay.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.type.currentIndexChanged.connect(self._sync_rows)
        self.through.toggled.connect(self.depth.setDisabled)
        self._sync_rows()

    def _set_row(self, index, visible):
        lab = self._form.itemAt(index * 2).label()
        wid = self._form.itemAt(index * 2 + 1).widget()
        lab.setVisible(visible)
        wid.setVisible(visible)

    def _sync_rows(self):
        t = self.type.currentText()
        for i in self._cb_rows:
            self._set_row(i, t == "Counterbore")
        for i in self._cs_rows:
            self._set_row(i, t == "Countersink")

    def values(self) -> dict:
        ang = self.cs_angle.currentData()
        if ang is None:
            try:
                ang = float(self.cs_angle.currentText().rstrip("°"))
            except ValueError:
                ang = 90.0
        return {"type": self.type.currentText().lower(),
                "depth": float(self.depth.value()),
                "through": bool(self.through.isChecked()),
                "cb_dia": float(self.cb_dia.value()),
                "cb_depth": float(self.cb_depth.value()),
                "cs_dia": float(self.cs_dia.value()),
                "cs_angle": float(ang)}

    @staticmethod
    def ask(parent, diameters) -> dict | None:
        dlg = HoleDialog(parent, diameters)
        return dlg.values() if dlg.exec() == QDialog.Accepted else None
