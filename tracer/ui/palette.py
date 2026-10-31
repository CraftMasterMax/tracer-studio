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

from PySide6.QtCore import Qt, QEvent, QRect, QSettings, Signal
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu,
                               QStyledItemDelegate, QVBoxLayout, QWidget)

from .commands import Command, plain, rank
from .theme import SP, TYPE, DARK

STAR = "\u2605"                       # ★ the promoted marker


class _PromoteDelegate(QStyledItemDelegate):
    """M183 R2: the row IS Fusion's result row - the command at left,
    the little PROMOTE button at its right ("select the Promote button
    next to a resulting command", LAW-36 verbatim).  A press inside the
    button CLAIMS the event: the row teaches, it never runs."""
    BW, BH = 72, 18                   # the button box

    def __init__(self, pal: "CommandPalette"):
        super().__init__(pal)
        self.pal = pal

    def _btn_rect(self, row_rect):
        return _btn(row_rect, self.BW, self.BH)

    def paint(self, p, opt, index):
        super().paint(p, opt, index)
        cmd = index.data(Qt.ItemDataRole.UserRole)
        if cmd is None:
            return
        r = self._btn_rect(opt.rect)
        p.save()
        col = QColor(DARK["fg_dim"])
        p.setPen(QPen(col, 1))
        p.setBrush(QColor(col.red(), col.green(), col.blue(), 26))
        p.drawRoundedRect(r, 4, 4)
        p.setPen(col)
        f = QFont(opt.font)
        f.setPointSize(max(7, f.pointSize() - 2))
        p.setFont(f)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.pal._btn_label(cmd))
        p.restore()

    def editorEvent(self, ev, model, opt, index):
        if (ev.type() == QEvent.Type.MouseButtonRelease
                and ev.button() == Qt.MouseButton.LeftButton
                and self._btn_rect(opt.rect).contains(ev.position().toPoint())):
            cmd = index.data(Qt.ItemDataRole.UserRole)
            if cmd is not None:
                self.pal.toggle_promote(cmd)
            return True               # the button ate it - the row sleeps
        return super().editorEvent(ev, model, opt, index)


def _btn(row_rect, bw, bh):
    return QRect(row_rect.right() - bw - 8,
                 row_rect.center().y() - bh // 2, bw, bh)


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
        # M183 R2: Fusion's button NEXT TO the command, painted on the
        # row itself - and the documented 'c' + Space SUMMON: the edit
        # field normally swallows Space, so the palette filters the key
        # before the field sees it.  Plain Space runs the current row;
        # with NOTHING matched Space stays a typing space (the multi-
        # word escape hatch - ours-said, subsequence search scores
        # spaceless queries just as well).
        self.delegate = _PromoteDelegate(self)
        self.list.setItemDelegate(self.delegate)
        self.edit.installEventFilter(self)

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

    def _btn_label(self, c: Command) -> str:
        """The row button's mouth: it SPEAKS the current state."""
        return "unpromote" if self._pid(c) in self._promoted else "promote"

    def eventFilter(self, obj, ev):
        """The law's sentence: 'c' + Spacebar/Enter invokes the tool.
        The edit field owns Space for typing, so this filter claims it
        for INVOKING - but only when there is a row to run (an empty
        result leaves Space as ordinary typing)."""
        if (obj is self.edit
                and ev.type() == QEvent.Type.KeyPress
                and ev.key() == Qt.Key.Key_Space
                and ev.modifiers() == Qt.KeyboardModifier.NoModifier
                and self.list.currentItem() is not None):
            self.run_current()
            return True
        return super().eventFilter(obj, ev)

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
