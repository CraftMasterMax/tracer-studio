"""Command search: Fusion's S-toolbox, cloned as a type-to-run popup.

S or / anywhere that isn't a text field opens it; typing filters
(fuzzy subsequence over the whole command index); Enter runs the top
hit — two keys to any command in the app.  The list is rebuilt from
the live menu tree on every open, so enabled state and coverage can
never drift.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QVBoxLayout,
                               QWidget)

from .commands import Command, plain, rank
from .theme import SP, TYPE, DARK


class CommandPalette(QFrame):
    picked = Signal()                       # a command ran: close me

    def __init__(self, parent: QWidget):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setWindowTitle("Command search")
        self.setFixedWidth(620)
        self._commands: list[Command] = []
        self._live: list[Command] = []

        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText(
            "Search commands — type to filter, Enter to run…")
        self.edit.setClearButtonEnabled(True)
        self.edit.textChanged.connect(self._refilter)

        self.list = QListWidget(self)
        self.list.setMaximumHeight(360)
        self.list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemActivated.connect(lambda _i: self.run_current())
        self.list.itemClicked.connect(lambda _i: self.run_current())
        self.list.currentRowChanged.connect(lambda _r: self.update())

        row = QHBoxLayout()
        row.setContentsMargins(SP * 2, SP * 2, SP * 2, SP)
        ic = QLabel("⌕", self)
        row.addWidget(ic)
        row.addWidget(self.edit, 1)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addLayout(row)
        col.addWidget(self.list)
        self.setStyleSheet(
            f"CommandPalette {{ background: {DARK['bg1']};"
            f" border: 1px solid {DARK['line_hi']};"
            f" border-radius: {SP * 2}px; }}"
            f" QLineEdit {{ border: none; background: transparent;"
            f" font-size: {TYPE['title']}px; padding: {SP}px; }}"
            f" QListWidget {{ border: none; background: transparent; }}"
            f" QListWidget::item {{ padding: {SP}px {SP * 2}px;"
            f" border-radius: {SP}px; }}")

    # ---- population -----------------------------------------------------------
    def set_commands(self, commands: list[Command]):
        self._commands = list(commands)
        self._refilter("")

    # ---- behaviour --------------------------------------------------------------
    def open_at(self, center_x: int, top_y: int):
        self.edit.setText("")
        self._refilter("")
        self.move(max(0, center_x - self.width() // 2), max(0, top_y))
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()

    def _refilter(self, query: str):
        self._live = [c for c in rank(query, self._commands) if c.enabled()]
        self.list.clear()
        f = QFont(self.list.font())
        f.setPointSize(TYPE["ui"])
        for c in self._live[:60]:
            it = QListWidgetItem(self._render(c))
            it.setFont(f)
            it.setData(Qt.ItemDataRole.UserRole, c)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    @staticmethod
    def _render(c: Command) -> str:
        key = f'\t{c.key}' if c.key else ""
        return f"{plain(c.label)}  ·  {c.category}{key}"

    def run_current(self):
        it = self.list.currentItem()
        if it is None:
            return
        cmd: Command = it.data(Qt.ItemDataRole.UserRole)
        if cmd is None or not cmd.enabled():
            return
        self.hide()
        self.picked.emit()
        cmd.run()

    def keyPressEvent(self, ev):
        k = ev.key()
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self.run_current()
            return
        if k == Qt.Key_Down:
            self.list.setCurrentRow(
                min(self.list.count() - 1, self.list.currentRow() + 1))
            return
        if k == Qt.Key_Up:
            self.list.setCurrentRow(max(0, self.list.currentRow() - 1))
            return
        if k == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(ev)
