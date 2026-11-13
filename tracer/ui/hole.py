"""Hole command dialog — Fusion's Hole panel condensed for maker CAD.

The drilled diameter comes from the sketch circle; this dialog sets the
depth and the optional counterbore / countersink, exactly the three hole
types a maker reaches for (clearance holes, socket-head cap screws, flat
wood-screw seats).  ``HoleDialog.ask`` returns a values dict or None.

M201 R25 [Hole reference, GUID-3A76B269-8C8D-437B-8F4A-85D0B2BBA492,
verbatim] the door wears the page's row words at the rows it owns:
"Placement: Select At Point (Single Hole) or From Sketch (Multiple
Holes)." - our mouth drills at the EDITOR'S circles, so it wears the
one member it can bake; "Extents: Select Distance, To, or All." -
Distance and All land (the born "Through all" check was All in
under-dressed clothes), "To" is unoffered (no terminate-on-face
kernel); "Hole Type: Select Simple, Counterbore, or Countersink." -
the page's word for the born "Type" row; "Tip Angle: Specifies the
angle of the drill point for the hole."; "Counterbore Depth",
"Counterbore Diameter", "Countersink Diameter", "Countersink Angle"
- in the page's printed order (Depth BEFORE Diameter on the bore).
[Thread reference, GUID-C37E8172-DE94-4EB0-AFE3-9D3172328441] lends
its rows to the tapped path: "Modeled" and "Class" (verbatim gloss
"Specify whether the threads a cosmetic or modeled on the geometry."
- DEFECT H2, the vendor dropped a word; flagged not cloned, our
members say what the kernel does: a real groove or a decal.  DEFECT
H6: the HOLE reference prints no Modeled row at all, though its own
task page says "Check the Modeled checkbox to preview the thread." -
the door wears the Thread reference's word rather than an incomplete
enum).
Unoffered, declared: References ("Available when At Point is
active." - no At Point here), Flip Direction, "Objects to cut"
(casing drift H5: the task prints "Objects to Cut"; a single-body
doc has nothing to choose), Taper Tapped (gate "(Only available for
Simple and Countersink hole types.)" rides only the TASK page, H8,
and no kernel tapers a tap anyway). The task page's "To edit a hole,
use the Press Pull comment" is DEFECT H3 - "comment" for "command" -
flagged, not cloned.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QLabel,
                               QVBoxLayout)

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
        self.placement = QComboBox()
        # M201 R25 [Hole reference, verbatim] "Placement: Select At
        # Point (Single Hole) or From Sketch (Multiple Holes)." - this
        # mouth drills at the SKETCH EDITOR's circles (the door's own
        # sentence since birth: "each circle becomes one drilled
        # hole"), which IS the page's second member.  At Point wants a
        # face/point picker on the canvas ("References: Available when
        # At Point is active.") - no such picker feeds this dialog, so
        # the row carries ONE member and the kernel never promises a
        # placement it cannot see.
        self.placement.addItems(("From Sketch (Multiple Holes)",))
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
        # M201 R25 [Hole reference, verbatim] "Extents: Select
        # Distance, To, or All." - the born "Through all" checkbox was
        # the page's All in under-dressed clothes; the row now wears
        # the page's word.  "To" stays UNOFFERED: it terminates a hole
        # on a picked face and no kernel here computes a termination.
        # The VALUES KEY stays "through" (label is UI law, key is file
        # law: every scripted era answer and every HoleFeature field
        # speaks through=True/False; zero migration).
        self.extents = QComboBox()
        self.extents.addItems(("Distance", "All"))
        # M201 R7 [SLD-REF-HOLE-DIALOG, verbatim] "Drill Point: Select
        # Flat, or Angle." + "Tip Angle: Specifies the angle of the
        # drill point for the hole." THE NUMBER ENCODES THE ROW (R4's
        # law): 0.00° IS the page's "Flat" - what this tool has always
        # cut - and no second widget re-asks the choice. The page
        # names NO default ("default" appears zero times): 0.0 rests
        # because it is the LEGACY voice, not a quoted vendor fiat.
        # The page words no bounds; the spin's 0..179.99 is the house
        # coin (the kernel refuses what it cannot sweep, and the door
        # prechecks the same set before the capture). Page order: the
        # Tip Angle row sits with the Depth rows (no Diameter row is
        # ours to place: the sketch circle is our diameter).
        self.tip_angle = _spin(0.0, 0.0, 179.99, "°")
        self.cb_dia = _spin(max(diameters) + 4.0)
        self.cb_depth = _spin(4.0)
        self.cs_dia = _spin(max(diameters) + 5.0)
        self.cs_angle = QComboBox()
        self.cs_angle.setEditable(True)
        for a in (82.0, 90.0, 120.0):
            self.cs_angle.addItem(f"{a:g}°", a)
        self.cs_angle.setCurrentIndex(1)          # 90° default
        # M201 R25 [Hole reference, verbatim row words in printed
        # order]: "Placement", "Extents", "Hole Type", ..., "Depth",
        # "Tip Angle", "Counterbore Depth" BEFORE "Counterbore
        # Diameter" (the born dialog had the bore pair reversed),
        # "Countersink Diameter", "Countersink Angle".  Fastener/Size/
        # Thread/Class/Modeled are OUR rows and the tapped path's:
        # Class and Modeled are the Thread reference's own words
        # (verbatim "Class: Select the thread class." / "Modeled");
        # "Hole Tap Type" (Simple|Clearance|Tapped|Taper Tapped) is
        # the page's row we DO have, worn by the Fastener preset +
        # Thread machinery rather than cloned as a fourth combo: the
        # vendor's four members split across our two honest doors
        # (Custom Ø = Simple, the presets = Clearance/Tapped; Taper
        # Tapped unoffered - no kernel tapers a tap, H8).
        form.addRow("Placement", self.placement)
        form.addRow("Fastener", self.std)
        form.addRow("Size", self.size)
        form.addRow("Extents", self.extents)
        form.addRow("Hole Type", self.type)
        form.addRow("Thread", self.thread)
        tr = form.rowCount()
        form.addRow("Class", self.t_class)
        form.addRow("Modeled", self.t_mode)
        self._thread_rows = (tr, tr + 1)        # M128: hidden unless tapped
        form.addRow("Depth", self.depth)
        form.addRow("Tip Angle", self.tip_angle)
        r = form.rowCount()
        form.addRow("Counterbore Depth", self.cb_depth)
        form.addRow("Counterbore Diameter", self.cb_dia)
        self._cb_rows = (r, r + 1)
        r = form.rowCount()
        form.addRow("Countersink Diameter", self.cs_dia)
        form.addRow("Countersink Angle", self.cs_angle)
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
        # the page's Extents row keeps the born law: All disables the
        # Depth number (one voice in the record - the distance row
        # falls silent when the hole runs through everything).
        self.extents.currentTextChanged.connect(
            lambda t: self.depth.setDisabled(t == "All"))
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
                # label is UI law, key is file law: the page's word is
                # Extents {Distance | All}, the FILE's word stays
                # through - every scripted era answer and HoleFeature
                # field speaks it, zero migration.
                "through": self.extents.currentText() == "All",
                "tip_angle": float(self.tip_angle.value()),   # M201 R7
                "cb_dia": float(self.cb_dia.value()),
                "cb_depth": float(self.cb_depth.value()),
                "cs_dia": float(self.cs_dia.value()),
                "cs_angle": float(ang)}

    @staticmethod
    def ask(parent, diameters) -> dict | None:
        dlg = HoleDialog(parent, diameters)
        return dlg.values() if dlg.exec() == QDialog.Accepted else None
