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

from ..core.thread import ISO_COARSE

TYPES = ("Simple", "Counterbore", "Countersink")
THREADS = ("None",) + tuple(ISO_COARSE)      # None + ISO metric coarse


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
        self._diam = list(diameters)
        self._head0 = f"{len(diameters)} circle(s) — hole Ø {di}"
        head = QLabel(self._head0)
        head.setObjectName("dim")
        self.head = head
        lay.addWidget(head)

        form = QFormLayout()
        form.setSpacing(6)
        self._form = form
        self.type = QComboBox()
        self.type.addItems(TYPES)
        self.thread = QComboBox()
        self.thread.addItems(THREADS)
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
        form.addRow("Thread", self.thread)
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
        self.thread.currentIndexChanged.connect(self._sync_head)
        self._sync_rows()

    def _sync_head(self):
        """Show what a tapped hole will actually drill: tap-drill Ø and
        pitch, so the sketch circle is understood as placement only."""
        t = self.thread.currentText()
        if t == "None":
            self.head.setText(self._head0)
        else:
            pitch, tap = ISO_COARSE[t]
            self.head.setText(f"{len(self._diam)} circle(s) — {t}: tap-drill "
                              f"Ø {tap:g}, pitch {pitch:g} mm")

    def _set_row(self, index, visible):
        """Toggle a form row's label + field.  Uses QFormLayout's
        (row, role) lookup — robust across PySide versions, unlike flat
        itemAt() arithmetic which depends on how labels are stored."""
        lab = self._form.itemAt(index, QFormLayout.LabelRole)
        fld = self._form.itemAt(index, QFormLayout.FieldRole)
        if lab is not None and lab.widget() is not None:
            lab.widget().setVisible(visible)
        if fld is not None and fld.widget() is not None:
            fld.widget().setVisible(visible)

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
                "thread": self.thread.currentText(),
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
