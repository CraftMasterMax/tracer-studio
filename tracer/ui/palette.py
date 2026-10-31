"""Command search: Fusion's S-toolbox, cloned as a type-to-run popup.

S or / anywhere that isn't a text field opens it; typing filters
(fuzzy subsequence over the whole command index); Enter runs the top
hit — two keys to any command in the app.  The list is rebuilt from
the live menu tree on every open, so enabled state and coverage can
never drift.  M183 added the HAND: promoted commands (FD8 LAW-36)
persist across restarts, wear a star, and ride the top of every list
their letters match — the pin is an ORDER, never a resurrection.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu,
                               QVBoxLayout, QWidget)

from .commands import Command, plain, rank
from .theme import SP, TYPE, DARK

STAR = "\u2605"                       # ★ the promoted marker


class CommandPalette(QFrame):
    picked = Signal()                       # a command ran: close me

    def __init__(self, parent: QWidget):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setWindowTitle("Command search")
        self.setFixedWidth(620)
        self._commands: list[Command] = []
        self._live: list[Command] = []
        self._promoted: set[str] = self._load_promoted()

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
        # M183 R1: the row itself is the promote button (FD8-36's mouth)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._row_menu)

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
        self._promoted = self._load_promoted()   # M183 R1: the store is
        self.edit.setText("")                    #  re-read every open,
        self._refilter("")                       #   never cached-stale
        self.move(max(0, center_x - self.width() // 2), max(0, top_y))
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()

    # ---- M183 R1: the PROMOTE MOUTH (FD8 LAW-36) ------------------------------
    # "select the Promote button... the tool appears at the top each time
    # the character is keyed in".  Identity = category + plain(label), so
    # "Cham&fer" and "Chamfer" are one tool (the plain() mouth again).
    @staticmethod
    def _pid(c: Command) -> str:
        return f"{c.category}\u0001{plain(c.label)}"

    @staticmethod
    def _load_promoted() -> set[str]:
        v = QSettings().value("palette/promoted", [])
        if isinstance(v, str):
            v = [v] if v else []
        return set(v)

    def toggle_promote(self, c: Command) -> bool:
        """Returns the state AFTER the flip (True = promoted now)."""
        pid = self._pid(c)
        if pid in self._promoted:
            self._promoted.discard(pid)
        else:
            self._promoted.add(pid)
        s = QSettings()
        s.setValue("palette/promoted", sorted(self._promoted))
        s.sync()
        self._refilter(self.edit.text())
        return pid in self._promoted

    def _promote_menu(self, c: Command) -> QMenu:
        on = self._pid(c) in self._promoted
        m = QMenu(self)
        verb = "Unpromote" if on else "Promote"
        m.addAction(f"{verb}  {plain(c.label)}",
                    lambda: self.toggle_promote(c))
        return m

    def _row_menu(self, pos):
        it = self.list.itemAt(pos)
        if it is None:
            return
        self.list.setCurrentRow(self.list.row(it))
        cmd = it.data(Qt.ItemDataRole.UserRole)
        if cmd is not None:
            self._promote_menu(cmd).exec(self.list.mapToGlobal(pos))

    def _refilter(self, query: str):
        live = [c for c in rank(query, self._commands) if c.enabled()]
        # the PIN: promoted hits keep the TOP, in rank order among
        # themselves; a promoted-but-disabled hit is already gone (the
        # enabled law outranks the pin - the pin is an ORDER, not a
        # resurrection).
        top = [c for c in live if self._pid(c) in self._promoted]
        self._live = top + [c for c in live if self._pid(c)
                            not in self._promoted]
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

    def _render(self, c: Command) -> str:
        key = f'\t{c.key}' if c.key else ""
        mark = f"{STAR} " if self._pid(c) in self._promoted else ""
        return f"{mark}{plain(c.label)}  ·  {c.category}{key}"

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
