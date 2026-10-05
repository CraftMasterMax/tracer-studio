"""Loft command dialog — pick the two sketches whose profiles blend.

Fusion's Loft asks for sections in order; this is the same question with
fewer clicks: every loftable sketch in the document (exactly one closed
outline, nothing inside it) lands in both dropdowns, base defaults to the
first, top to the second.  ``LoftDialog.ask`` returns (sid_base, sid_top)
or None.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QLabel, QVBoxLayout)


class LoftDialog(QDialog):
    def __init__(self, parent=None, candidates=()):
        super().__init__(parent)
        self.setWindowTitle("Loft between sketches")
        lay = QVBoxLayout(self)
        head = QLabel("Blend the closed profile of one sketch into "
                      "another's — base to top.")
        head.setObjectName("dim")
        lay.addWidget(head)

        form = QFormLayout()
        form.setSpacing(6)
        self.base = QComboBox()
        self.top = QComboBox()
        for sid, label in candidates:
            self.base.addItem(label, sid)
            self.top.addItem(label, sid)
        if self.top.count() > 1:
            self.top.setCurrentIndex(1)
        form.addRow("Base profile", self.base)
        form.addRow("Top profile", self.top)
        lay.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self) -> tuple:
        return (self.base.currentData(), self.top.currentData())

    @staticmethod
    def ask(parent, candidates) -> tuple | None:
        if len(candidates) < 2:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                parent, "Loft",
                "A loft blends two sketches. Draw a closed profile in two "
                "different sketches — sketching on a face gives the second "
                "one its offset for free.")
            return None
        dlg = LoftDialog(parent, candidates)
        return dlg.values() if dlg.exec() == QDialog.Accepted else None
