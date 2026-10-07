"""M111 Versions dialog — the durable history that lives BESIDE the file.

Undo is RAM; this is disk. The list comes straight from the
``.tracer_versions`` sidecar (core/versions).  Restore loads a snapshot
as UNSAVED working state — nothing truncates: the chain only grows and
the next Save becomes the newest head ("history never lies", the state
machine every CAD user half-exists on).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QInputDialog, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout)

from ..core import versions


class VersionsDialog(QDialog):
    """``on_restore(doc_dict, detach)`` is the host's load hook; the
    dialog itself only ever touches the sidecar folder."""

    COLUMNS = ("", "v", "when", "named", "note")

    def __init__(self, doc_path, parent=None, on_restore=None):
        super().__init__(parent)
        self.doc_path = Path(doc_path)
        self.on_restore = on_restore
        self.setWindowTitle(f"Versions — {self.doc_path.name}")
        self.resize(580, 340)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.doubleClicked.connect(self._load_current)

        box = QVBoxLayout(self)
        box.addWidget(self.table)
        row = QHBoxLayout()
        for label, slot in (("Restore", self._load_current),
                            ("Open as Copy", self._load_copy),
                            ("Note…", self._note),
                            ("Name…", self._pin),
                            ("Delete", self._delete)):
            row.addWidget(QPushButton(label, self, clicked=slot))
        row.addStretch(1)
        row.addWidget(QPushButton("Close", self, clicked=self.reject))
        box.addLayout(row)
        box.addWidget(QLabel(
            "Every Save keeps an auto point (the last "
            f"{versions.AUTO_KEEP}); Named versions are kept forever. "
            "Restoring never deletes anything."))
        self._reload()

    # ---- model -----------------------------------------------------------
    def entries(self):
        return versions.list_versions(self.doc_path)

    def _reload(self):
        entries = self.entries()
        self.table.setRowCount(len(entries))
        for r, v in enumerate(entries):
            marker = "\u25cf" if r == len(entries) - 1 else ""
            for c, text in enumerate((marker, str(v.n), v.when,
                                      v.name or "", v.note)):
                it = QTableWidgetItem(text)
                if c <= 1:
                    it.setTextAlignment(Qt.AlignCenter)
                if c == 0 and marker:
                    it.setToolTip("Newest — the state the saved file holds")
                self.table.setItem(r, c, it)

    def selected(self):
        r = self.table.currentRow()
        entries = self.entries()
        return entries[r] if 0 <= r < len(entries) else None

    # ---- actions ----------------------------------------------------------
    def _load(self, detach: bool):
        v = self.selected()
        if v is None:
            return
        try:
            data = versions.read(v)
        except Exception as e:
            QMessageBox.warning(self, "Version unreadable", str(e))
            return
        if self.on_restore is not None and \
                self.on_restore(data, detach) is False:
            return
        self.accept()

    def _load_current(self):
        self._load(detach=False)

    def _load_copy(self):
        self._load(detach=True)

    def _note(self):
        v = self.selected()
        if v is None:
            return
        text, ok = QInputDialog.getText(self, "Version note",
                                        f"Note for v{v.n}:", text=v.note)
        if ok:
            versions.set_note(v, text)
            self._reload()

    def _pin(self):
        v = self.selected()
        if v is None:
            return
        text, ok = QInputDialog.getText(self, "Named version",
                                        "Label (kept forever):",
                                        text=v.name or "")
        if ok and text.strip():
            versions.name_version(v, text.strip())
            self._reload()

    def _delete(self):
        v = self.selected()
        if v is None:
            return
        if QMessageBox.question(
                self, "Delete version",
                f"Delete v{v.n} ({v.when}) forever?") \
                == QMessageBox.StandardButton.Yes:
            versions.delete(v)
            self._reload()
