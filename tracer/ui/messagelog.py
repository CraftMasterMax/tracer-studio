"""M118 — the Message Log panel.

Fusion's shape (a bottom table of time/severity/message, filter,
Copy/Save/Clear) with the one thing Fusion never shipped [V —
ui_message_log Finding 6]: double-click an entry and the timeline
selects the feature that wrote it. The panel is pure listener — it
reads the core logservice bus, never the other way round, so the
whole feature is testable headless save for the table itself.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import logservice
from . import theme

_SEV_COLOR = {logservice.ERROR: "danger",
              logservice.WARN: "warn",
              logservice.INFO: "fg"}

VIEW_CAP = 500                   # rows painted at most; the bus keeps all


class MessageLog(QWidget):
    """The bottom-docked log; parent toggles visibility."""

    goto_feature = Signal(int)                 # feature index (BEAT)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Message Log")
        self._dirty = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(QLabel("Message Log"))
        self._filter = QComboBox()
        self._filter.addItems(["All", "Errors", "Warnings", "Info"])
        self._filter.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self._filter)
        for label, fn in (("Copy Selected", self._copy_selected),
                          ("Copy All", self._copy_all),
                          ("Save As\u2026", self._save_as),
                          ("Clear", logservice.clear)):
            b = QPushButton(label)
            b.setProperty("tb", True)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)
        self._hint = QLabel("double-click an entry to select its "
                            "feature")
        self._hint.setObjectName("dim")
        bar.addWidget(self._hint)
        lay.addLayout(bar)

        D = theme.DARK
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Time", "Severity", "Source", "Message"])
        for col, w in ((0, 70), (1, 70), (2, 90), (3, 520)):
            self._table.setColumnWidth(col, w)
        self._table.setSelectionBehavior(
            QTableWidget.SelectRows)
        self._table.setSelectionMode(
            QTableWidget.ExtendedSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setHighlightSections(False)
        self._table.itemDoubleClicked.connect(self._double)
        lay.addWidget(self._table, 1)
        self.setMinimumHeight(120)

        # the bus outlives windows — a torn-down panel must stop
        # hearing it, or the next log write touches deleted C++
        logservice.subscribe(self._changed)
        self.destroyed.connect(
            lambda: logservice.unsubscribe(self._changed))

    # ------------------------------------------------------------------
    def _changed(self) -> None:
        # a log nobody looks at must not cost anything: a hidden panel
        # catches up when it is shown, not on every single write
        if not self.isVisible():
            self._dirty = True
            return
        self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._dirty:
            self.refresh()

    def _want(self, sev: str) -> bool:
        f = self._filter.currentText()
        return (f == "All" or (f == "Errors" and sev == logservice.ERROR)
                or (f == "Warnings" and sev == logservice.WARN)
                or (f == "Info" and sev == logservice.INFO))

    def refresh(self) -> None:
        D = theme.DARK
        self._dirty = False
        rows = [e for e in logservice.entries() if self._want(e.severity)]
        shown = rows[-VIEW_CAP:] if len(rows) > VIEW_CAP else rows
        self._hint.setText(
            f"showing latest {VIEW_CAP} of {len(rows)}" if shown is not rows
            else "double-click an entry to select its feature")
        at_bottom = (self._table.verticalScrollBar().value()
                     >= self._table.verticalScrollBar().maximum() - 2)
        self._table.setRowCount(len(shown))
        for r, e in enumerate(shown):
            rep = f"  \u00d7{e.count}" if e.count > 1 else ""
            cells = (e.ts, e.severity, e.source, e.text + rep)
            for c, val in enumerate(cells):
                it = QTableWidgetItem(val)
                if c == 1:
                    it.setForeground(QColor(D[_SEV_COLOR[e.severity]]))
                if c == 3 and e.feature:
                    it.setData(Qt.UserRole, e.feature_pos)
                    it.setToolTip(f"feature: {e.feature} — double-click")
                self._table.setItem(r, c, it)
        if at_bottom:
            self._table.scrollToBottom()

    def _double(self, item: QTableWidgetItem) -> None:
        row = self._table.item(item.row(), 3)
        pos = row.data(Qt.UserRole) if row is not None else None
        if pos is not None:
            self.goto_feature.emit(int(pos))

    # ---- clipboard & disk ------------------------------------------------
    def _copy_selected(self):
        rows = sorted({i.row() for i in self._table.selectedItems()})
        text = "\n".join(
            "  ".join(self._table.item(r, c).text()
                      for c in range(4) if self._table.item(r, c))
            for r in rows)
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def _copy_all(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(logservice.dump_text())

    def _save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Message Log", "tracer-log.txt",
            "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(logservice.dump_text() + "\n")
