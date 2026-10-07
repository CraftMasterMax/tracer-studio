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

from ..core.thread import ISO_COARSE, designation
from ..core import fasteners as _F

TYPES = ("Simple", "Counterbore", "Countersink")
THREADS = ("None",) + tuple(ISO_COARSE)      # None + ISO metric coarse
# The Fastener presets: "Custom" keeps today's hand-typed behaviour (the
# sketch circle sets Ø); the rest look a named fastener up in the library
# (M107), at which point the circle only PLACES the hole.
STDS = ("Custom (Ø from sketch)", "Clearance", "Tapped",
        "Socket head (cbore)", "Heat-set insert")
_STD_KIND = {STDS[1]: "clearance", STDS[2]: "tapped",
             STDS[3]: "socket head", STDS[4]: "heat-set insert"}


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
        self._drill = None                 # fastener preset Ø override (M107)
        self.size = QComboBox()
        self.size.addItems(_F.SIZES)
        self.size.setCurrentText("M4")
        self.std = QComboBox()
        self.std.addItems(STDS)
        self.std.setCurrentIndex(0)        # Custom → identical to today
        self.type = QComboBox()
        self.type.addItems(TYPES)
        self.thread = QComboBox()
        self.thread.addItems(THREADS)
        self.t_class = QComboBox()          # M128: common ISO internal
        self.t_class.addItems(("6H", "6F", "7H"))    # classes (codes,
        self.t_mode = QComboBox()           # not tables — no M123 law)
        self.t_mode.addItems(("Modeled — real groove",
                              "Cosmetic — decal ring"))
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
        form.addRow("Fastener", self.std)
        form.addRow("Size", self.size)
        form.addRow("Type", self.type)
        form.addRow("Thread", self.thread)
        tr = form.rowCount()
        form.addRow("Class", self.t_class)
        form.addRow("Thread form", self.t_mode)
        self._thread_rows = (tr, tr + 1)        # M128: hidden unless tapped
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

        self._prov = QLabel("")                 # M123: where numbers come from
        self._prov.setObjectName("dim")
        self._prov.setWordWrap(True)
        lay.addWidget(self._prov)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.type.currentIndexChanged.connect(self._sync_rows)
        self.through.toggled.connect(self.depth.setDisabled)
        self.thread.currentIndexChanged.connect(self._sync_head)
        self.thread.currentIndexChanged.connect(self._sync_rows)
        self.t_class.currentIndexChanged.connect(self._sync_head)
        self.t_mode.currentIndexChanged.connect(self._sync_head)
        self.std.currentIndexChanged.connect(self._apply_std)
        self.size.currentIndexChanged.connect(self._apply_std)
        self._sync_rows()

    def _provenance_line(self, kind: str) -> str:
        """M123: name the standard behind the auto-filled numbers, so a
        preset is never an unsourced magic Ø. Empty for Custom."""
        key = {"clearance": "clearance", "socket head": "shcs_head",
               "heat-set insert": "insert"}.get(kind)
        if key is None:
            return ""
        p = _F.provenance(key)
        std = p["standard"]
        if kind == "socket head":
            c = _F.provenance("clearance")
            std += f" head + {c['standard']} hole"
        return f"{std} ({p['edition']}) · verified {p['verified']}"

    def _apply_std(self):
        """M107: a named fastener fills the dialog from the library.  "Custom"
        clears the Ø override and leaves every field to the user, so the
        pre-library behaviour (and its tests) is untouched."""
        if self.std.currentIndex() == 0:
            self._drill = None
            self._prov.setText("")
            self._sync_head()
            return
        size = self.size.currentText()
        kind = _STD_KIND[self.std.currentText()]
        self._prov.setText(self._provenance_line(kind))
        try:
            p = _F.hole_for(size, kind)
        except KeyError:
            self._drill = None
            self.head.setText(f"{size} {kind}: no library data — "
                              "check a datasheet, or pick another size")
            return
        self.thread.setCurrentText(p["thread"])   # → _sync_head, then we win
        self.type.setCurrentText(p["type"].capitalize())
        if p["type"] == "counterbore":
            self.cb_dia.setValue(p["cb_dia"])
            self.cb_depth.setValue(p["cb_depth"])
        self._drill = p["drill"]
        if kind == "tapped":
            return                               # head already shows tap drill
        dia = f"Ø {self._drill:g}" if self._drill else "Ø from sketch"
        note = (f"cbore Ø {p['cb_dia']:g} × {p['cb_depth']:g}"
                if p["type"] == "counterbore" else "")
        self.head.setText(f"{len(self._diam)} circle(s) place — {size} "
                          f"{kind}: drill {dia} {note}".rstrip())

    def _sync_head(self):
        """Show what a tapped hole will actually drill: the full ISO
        designation (M128: "M6-6H [modeled]"), tap-drill Ø and pitch,
        so the sketch circle is understood as placement only."""
        t = self.thread.currentText()
        if t == "None":
            self.head.setText(self._head0)
        else:
            pitch, tap = ISO_COARSE[t]
            desig = designation(t, pitch, internal=True,
                                cls=self.t_class.currentText())
            mode = "cosmetic" if self.t_mode.currentIndex() == 1 \
                else "modeled"
            self.head.setText(f"{len(self._diam)} circle(s) — {desig} "
                              f"[{mode}]: tap-drill Ø {tap:g}, pitch "
                              f"{pitch:g} mm")

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
        for i in self._thread_rows:          # M128: class + form only
            self._set_row(i, self.thread.currentText() != "None")

    def values(self) -> dict:
        ang = self.cs_angle.currentData()
        if ang is None:
            try:
                ang = float(self.cs_angle.currentText().rstrip("°"))
            except ValueError:
                ang = 90.0
        threaded = self.thread.currentText() != "None"
        return {"type": self.type.currentText().lower(),
                "thread": self.thread.currentText(),
                "thread_size": self.thread.currentText() if threaded
                else "",
                "thread_class": self.t_class.currentText() if threaded
                else "",
                "thread_mode": ("cosmetic" if self.t_mode.currentIndex()
                                == 1 else "modeled") if threaded
                else "modeled",
                "drill": self._drill,
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
