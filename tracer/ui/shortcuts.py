"""Keyboard/mouse reference: one table feeds the tour, the tab and the tests.

Every binding the app actually implements is listed here (and a unit test
asserts the menu shortcuts stay in sync).  ``seq=None`` marks mouse/gesture
rows; keyboard rows store the *display* string, which doubles as the
canonical ``QKeySequence`` text used for the consistency check.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel,
                               QScrollArea, QVBoxLayout, QWidget)

# (group title, [(keys, what, is_keyboard), ...])
SHORTCUTS: list[tuple[str, list[tuple[str, str, bool]]]] = [
    ("Look around (3D viewport)", [
        ("LMB click a face", "Select / deselect the whole face", False),
        ("LMB click two faces", "Measure: gap, angle or area (status bar)",
         False),
        ("LMB drag a flat face", "Press-Pull: push or pull material", False),
        ("Esc", "Cancel the drag / clear the face selection", False),
        ("MMB drag", "Orbit the model", False),
        ("Shift + MMB drag", "Pan the view", False),
        ("Mouse wheel", "Zoom in / out", False),
        ("MMB click", "Home view (fit + isometric)", False),
        ("Double-click a face", "Start a sketch on that face", False),
        ("F", "Fit model to screen", True),
        ("0", "Isometric view", True),
        ("1", "Front view", True),
        ("2", "Top view", True),
        ("3", "Right view", True),
        ("G", "Toggle grid", True),
        ("E", "Toggle shaded edges", True),
        ("?", "Open this shortcut sheet", True),
    ]),
    ("Sketching", [
        ("N", "New sketch (on origin plane or browser plane)", True),
        ("R", "Rectangle tool — click-click or drag", True),
        ("L", "Line tool — click-move-click chains", True),
        ("C", "Circle tool", True),
        ("A", "Arc tool — start · end · bulge, chained", True),
        ("O", "Slot tool — centre · centre · width, tangent-locked", True),
        ("Y", "Polygon tool — centre · vertex · number keys 3-9 set sides",
         True),
        ("S", "Select / drag tool", True),
        ("Esc", "Cancel chain, switch to select", True),
        ("Enter", "Finish the line chain", True),
        ("X", "Finish sketch → extrude profile", True),
        ("Shift + R", "Finish sketch → revolve about sketch's vertical axis", True),
        ("Ctrl + H", "Hole — drill every sketch circle (counterbore/countersink)",
         True),
        ("W", "Sweep — pipe the sketch's circle along its line/arc path",
         True),
        ("Ctrl + Z", "Undo last sketch step", True),
        ("Ctrl + Shift + Z", "Redo (or Ctrl + Y)", True),
        ("Double-click a badge", "Type a new dimension value", False),
        ("Drag a point", "Move geometry (snaps + auto H/V)", False),
    ]),
    ("Sketch constraints & dimensions", [
        ("H", "Horizontal constraint on selected lines", True),
        ("V", "Vertical constraint", True),
        ("P", "Perpendicular constraint (two lines)", True),
        ("Q", "Equal constraint (lines → same length · curves → radius)", True),
        ("2", "Concentric constraint (two circles/arcs)", True),
        ("M", "Symmetry constraint (point · point · line axis)", True),
        ("T", "Tangent constraint (line↔circle/arc, or two curves)", True),
        ("I", "Angular dimension (one line: from +X · two lines: between)", True),
        ("F", "Fix a point · fillet a corner with two lines selected", True),
        ("G", "Chamfer corner (two lines sharing a corner)", True),
        ("/", "Trim / extend two loose lines into a shared corner", True),
        (".", "On-curve constraint (point + line/circle/arc)", True),
        ("U", "Offset outline — parallel mitred copy (− = inward)", True),
        ("D", "Distance dimension (1 line, 2 points, or pick)", True),
        ("K", "Toggle construction geometry", True),
        ("Delete", "Delete selected entities", True),
    ]),
    ("Document & features", [
        ("Ctrl + N", "New document", True),
        ("Ctrl + O", "Open document…", True),
        ("Ctrl + S", "Save", True),
        ("Ctrl + Shift + S", "Save as…", True),
        ("Ctrl + Q", "Quit", True),
        ("Double-click a timeline chip", "Edit that sketch", False),
        ("Delete", "Delete selected feature (timeline focused)", True),
        ("Right-click a chip / browser row", "Feature menu: edit, suppress, rename, delete", False),
    ]),
]

TOUR_HIGHLIGHTS = [
    ("N", "sketch · R/L/C/O/Y/A to draw"),
    ("X", "finish → extrude"),
    ("MMB / wheel", "orbit · zoom (Shift pans)"),
    ("Double-click face", "sketch on it"),
    ("Drag a flat face", "press-pull material"),
    ("D + double-click", "dimension, then edit it"),
    ("T · F · G · /", "tangent · fillet · chamfer · trim"),
    ("Ctrl + Z", "undo inside the sketch"),
    ("1 2 3 0", "front / top / right / iso"),
    ("?", "the full cheat sheet"),
]


def shortcut_tokens() -> set[str]:
    """All keyboard key strings, split on spaces — for consistency tests."""
    out: set[str] = set()
    for _, rows in SHORTCUTS:
        for keys, _, is_kb in rows:
            if is_kb:
                out.add(keys)
    return out


class ShortcutsPage(QScrollArea):
    """Permanent cheat sheet — opened from the tab bar or the ? key."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("shortcutsPage")
        self.setWidgetResizable(True)
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(24, 16, 24, 24)
        col.setSpacing(14)
        title = QLabel("⌨  Keyboard &amp; mouse reference")
        tf = QFont()
        tf.setPointSize(15)
        tf.setBold(True)
        title.setFont(tf)
        col.addWidget(title)
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        for group, rows in SHORTCUTS:
            head = QLabel(group)
            hf = QFont()
            hf.setPointSize(10)
            hf.setBold(True)
            head.setFont(hf)
            head.setStyleSheet("color:#8ab4f8; padding-top:6px;")
            col.addWidget(head)
            for keys, what, _kb in rows:
                row = QHBoxLayout()
                row.setSpacing(10)
                k = QLabel(keys)
                k.setFont(mono)
                k.setStyleSheet("color:#f0c674;")
                k.setMinimumWidth(190)
                row.addWidget(k)
                row.addWidget(QLabel(what))
                row.addStretch(1)
                col.addLayout(row)
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("color:#3a3f4b;")
            col.addWidget(line)
        col.addStretch(1)
        self.setWidget(body)


class TourDialog(QDialog):
    """First-run welcome tour — the 8 shortcuts you need on day one."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tourDialog")
        self.setWindowTitle("Welcome to Tracer Studio")
        self.setModal(False)
        col = QVBoxLayout(self)
        col.setContentsMargins(20, 16, 20, 16)
        head = QLabel("<b>Welcome to Tracer Studio</b> — parametric CAD for makers.")
        hf = QFont()
        hf.setPointSize(12)
        hf.setBold(True)
        head.setFont(hf)
        col.addWidget(head)
        col.addWidget(QLabel("Tracer Studio is keyboard-first. These are the keys you "
                             "will use every session:"))
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        for keys, what in TOUR_HIGHLIGHTS:
            row = QHBoxLayout()
            k = QLabel(keys)
            k.setFont(mono)
            k.setStyleSheet("color:#f0c674;")
            k.setMinimumWidth(170)
            row.addWidget(k)
            row.addWidget(QLabel(what))
            row.addStretch(1)
            col.addLayout(row)
        btns = QHBoxLayout()
        btns.addStretch(1)
        from PySide6.QtWidgets import QPushButton
        self.btn_sheet = QPushButton("Open full cheat sheet")
        self.btn_sheet.setObjectName("tourSheet")
        self.btn_go = QPushButton("Start modelling")
        self.btn_go.setObjectName("tourGo")
        self.btn_go.setDefault(True)
        btns.addWidget(self.btn_sheet)
        btns.addWidget(self.btn_go)
        col.addLayout(btns)
        self.btn_go.clicked.connect(self.accept)
        self.resize(430, 0)

    def keyPressEvent(self, ev):          # Esc closes without opening sheet
        if ev.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(ev)
