"""Fusion-style ribbon: quick-access strip + workspace tabs + tabbed panels.

Three zones, mirroring the Fusion toolbar's visual anatomy:

    [new open save undo redo]   [ Design | Sketch ]      <- row 1
    ─────────────────────────────────────────────────
    ▢ Sketch | ▣ Extrude ▦ Sweep △ Loft ⌀ Hole │ ⊞
    Pattern │ ◠ Fillet ◺ Chamfer ⬚ Shell                <- row 2 (panel)

All controls are QToolButtons built by the host window through
``add_tool`` so the ribbon itself knows no app logic — it only owns
layout, styling and the tab ⇄ page sync signal.  Glyphs come from
icons.py (generic geometry, identity-safe).
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QMenu, QSizePolicy,
                               QStackedWidget, QTabBar, QToolButton,
                               QVBoxLayout, QWidget)

from . import icons
from .theme import DARK


def _place(layout, widget) -> None:
    """Insert before the layout's trailing stretch so the group hugs the
    left edge, Fusion-style."""
    i = layout.count()
    if i and layout.itemAt(i - 1).spacerItem() is not None:
        i -= 1
    layout.insertWidget(i, widget)


class RibbonBar(QWidget):
    tab_clicked = Signal(int)          # 0 Design · 1 Sketch

    def __init__(self, parent=None):
        super().__init__(parent)
        t = DARK
        self.setStyleSheet(f"""
            RibbonBar {{ background: {t['bg0']};
                         border-bottom: 1px solid {t['line']}; }}
            QToolButton {{ border: none; border-radius: 5px; padding: 3px;
                           background: transparent; }}
            QToolButton:hover {{ background: {t['bg2']}; }}
            QToolButton:pressed {{ background: {t['line']}; }}
            QToolButton::menu-indicator {{ subcontrol-position: right;
                                           right: 2px; }}
            QTabBar::tab {{ background: transparent; color: {t['fg_dim']};
                            padding: 5px 14px; border: none;
                            border-bottom: 2px solid transparent; }}
            QTabBar::tab:selected {{ color: {t['fg']};
                                     border-bottom: 2px solid
                                     {t['accent']}; }}
            QTabBar::tab:hover {{ color: {t['fg']}; }}
            QMenu {{ background: {t['bg1']}; border: 1px solid {t['line']};
                     border-radius: 8px; padding: 4px; }}
            QMenu::item:selected {{ background: {t['bg2']};
                                    color: {t['accent']}; }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 2, 6, 2)
        root.setSpacing(2)

        row1 = QHBoxLayout()
        row1.setSpacing(1)
        self.quick = QWidget()
        q = QHBoxLayout(self.quick)
        q.setContentsMargins(0, 0, 0, 0)
        q.setSpacing(1)
        row1.addWidget(self.quick)
        row1.addSpacing(14)
        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.addTab("Design")
        self.tabs.addTab("Sketch")
        self.tabs.currentChanged.connect(lambda i: self.tab_clicked.emit(i))
        row1.addWidget(self.tabs)
        row1.addStretch(1)
        root.addLayout(row1)

        self.panels = QStackedWidget()
        self.panels.setFixedHeight(42)
        self.design_panel = QWidget()
        self.dl = QHBoxLayout(self.design_panel)
        self.sketch_panel = QWidget()
        self.sl = QHBoxLayout(self.sketch_panel)
        for lay in (self.dl, self.sl):
            lay.setContentsMargins(2, 1, 2, 1)
            lay.setSpacing(2)
            lay.addStretch(1)
        self.panels.addWidget(self.design_panel)
        self.panels.addWidget(self.sketch_panel)
        root.addWidget(self.panels)

    # -- tab ⇄ page ----------------------------------------------------------
    def set_current(self, index: int):
        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(index)
        self.tabs.blockSignals(False)
        self.panels.setCurrentIndex(index)

    # -- building blocks -------------------------------------------------------
    def quick_button(self, icon: str, tip: str, slot) -> QToolButton:
        return add_tool(self.quick.layout(), icon, tip, slot, size=16,
                        trailing=False)

    def design_tool(self, *a, **k) -> QToolButton:
        return add_tool(self.dl, *a, **k)

    def sketch_tool(self, *a, **k) -> QToolButton:
        return add_tool(self.sl, *a, **k)

    def design_sep(self) -> QFrame:
        return _sep(self.dl)

    def sketch_sep(self) -> QFrame:
        return _sep(self.sl)


def _sep(layout) -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.VLine)
    line.setStyleSheet(f"color: {DARK['line']};")
    _place(layout, line)
    return line


def add_tool(layout, icon: str, tip: str, slot=None, size: int = 26,
             menu_actions=None, checkable: bool = False,
             trailing: bool = True) -> QToolButton:
    """One ribbon button: glyph + tooltip, optional dropdown menu (whose
    first entry mirrors what a plain click fires — matches how Fusion's
    group buttons and our M20 tooltip-menu tests both behave)."""
    b = QToolButton()
    b.setIcon(icons.icon(icon))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.setCheckable(checkable)
    b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
    if menu_actions:
        m = QMenu(b)
        for item in menu_actions:
            if isinstance(item, QAction):
                m.addAction(item)
            else:
                text, fn = item
                m.addAction(text, fn)
        b.setMenu(m)
        b.setPopupMode(QToolButton.InstantPopup if slot is None
                       else QToolButton.MenuButtonPopup)
    if slot is not None:
        b.clicked.connect(slot)
    if trailing:
        _place(layout, b)
    else:
        layout.addWidget(b)
    return b
