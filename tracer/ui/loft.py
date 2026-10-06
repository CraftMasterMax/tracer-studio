"""Loft command dialog — pick the sketches whose profiles blend, in order.

Fusion's Loft asks for sections in sequence (base → middles → top) and so
do we now: every loftable sketch in the document (exactly one closed
outline, nothing inside it) can be added to an ordered section list; two
arrive preloaded (the old base/top defaults), and ▲▼ fixes any mis-click.
``LoftDialog.ask`` returns the ordered sid tuple (length ≥ 2) or None.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout)


class LoftDialog(QDialog):
    def __init__(self, parent=None, candidates=()):
        super().__init__(parent)
        self.setWindowTitle("Loft through sketches")
        self.resize(360, 380)
        lay = QVBoxLayout(self)
        head = QLabel("Blend closed profiles in order — base to top.")
        head.setObjectName("dim")
        head.setWordWrap(True)
        lay.addWidget(head)

        row = QHBoxLayout()
        self.pick = QComboBox()
        for sid, label in candidates:
            self.pick.addItem(label, sid)
        add = QPushButton("Add")
        add.clicked.connect(self._add_current)
        row.addWidget(self.pick, 1)
        row.addWidget(add)
        lay.addLayout(row)

        lab = QLabel("Sections (in order):")
        lab.setObjectName("dim")
        lay.addWidget(lab)
        self.listw = QListWidget()
        lay.addWidget(self.listw, 1)

        mv = QHBoxLayout()
        up = QPushButton("\u25b2")
        up.setToolTip("Move section earlier")
        up.clicked.connect(lambda: self._move(-1))
        down = QPushButton("\u25bc")
        down.setToolTip("Move section later")
        down.clicked.connect(lambda: self._move(1))
        rem = QPushButton("Remove")
        rem.clicked.connect(self._remove)
        for b in (up, down, rem):
            mv.addWidget(b)
        mv.addStretch(1)
        lay.addLayout(mv)

        self.closed = QCheckBox("Closed loop — last section blends back "
                                "to the first")
        lay.addWidget(self.closed)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        # the old defaults: first two candidates, base then top
        for sid, label in list(candidates)[:2]:
            self._insert(sid, label)

    # ---- ordered list plumbing ---------------------------------------------
    def _insert(self, sid, label):
        it = QListWidgetItem(label)
        it.setData(Qt.UserRole, sid)
        self.listw.addItem(it)

    def _add_current(self):
        if self.pick.currentData() is None:
            return
        self._insert(self.pick.currentData(), self.pick.currentText())

    def _move(self, delta):
        r = self.listw.currentRow()
        t = r + delta
        if r < 0 or not (0 <= t < self.listw.count()):
            return
        it = self.listw.takeItem(r)
        self.listw.insertItem(t, it)
        self.listw.setCurrentRow(t)

    def _remove(self):
        r = self.listw.currentRow()
        if r >= 0 and self.listw.count() > 2:   # a loft needs two
            self.listw.takeItem(r)

    def values(self) -> tuple:
        return tuple(self.listw.item(i).data(Qt.UserRole)
                     for i in range(self.listw.count()))

    @staticmethod
    def ask(parent, candidates) -> dict | None:
        if len(candidates) < 2:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                parent, "Loft",
                "A loft blends two sketches — or more. Draw a closed "
                "profile in two different sketches — sketching on a face "
                "gives the second one its offset for free.")
            return None
        dlg = LoftDialog(parent, candidates)
        if dlg.exec() != QDialog.Accepted:
            return None
        return {"sids": dlg.values(), "closed": dlg.closed.isChecked()}
