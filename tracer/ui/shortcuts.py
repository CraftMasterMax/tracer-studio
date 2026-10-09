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

from .theme import DARK

# (group title, [(keys, what, is_keyboard), ...])
SHORTCUTS: list[tuple[str, list[tuple[str, str, bool]]]] = [
    ("Look around (3D viewport)", [
        ("LMB click a face", "Select / deselect the whole face", False),
        ("LMB click two faces", "Measure: gap, angle or area (status bar)",
         False),
        ("LMB drag a flat face", "Press-Pull: push or pull material", False),
        ("LMB drag on empty space", "Selection box: left→right window, "
         "right→left crossing", False),
        ("Esc", "Yield the gesture ladder: ring · zoom-window · "
         "section cut · selection · isolation level", False),
        ("MMB drag", "Orbit the model (RMB drag too)", False),
        ("Shift + MMB press on geometry", "Orbit around the pointed-at "
         "point: view centres on it, a pivot dot rides the centre", False),
        ("Shift + MMB drag on empty space", "Pan the view", False),
        ("RMB tap", "Context menu: Sketch on Face · views · styles", False),
        ("RMB hold still", "Marking wheel: Undo · Extrude · Sketch · "
         "Move — release on a wedge to fire it, on the hub to dismiss",
         False),
        ("Plane row ▸ Section: cut here", "Cut the display on the "
         "plane — capped, accent-shaded; picking sleeps while cut",
         False),
        ("Mouse wheel", "Zoom toward the cursor", False),
        ("MMB click", "Home view (fit + isometric)", False),
        ("Double-click a face", "Sketch on it — frame + outline land",
         False),
        ("F6", "Fit model to screen", True),
        ("0", "Isometric view", True),
        ("1", "Front view", True),
        ("2", "Top view", True),
        ("3", "Right view", True),
        ("G", "Toggle grid", True),
        ("Z", "Zoom to selection", True),
        ("S", "Command search (Fusion's toolbox) — type to run", True),
        ("/", "Command search (command-line voice)", True),
        ("?", "Open this shortcut sheet", True),
    ]),
    ("Modeling commands (any solid context)", [
        ("E", "Extrude the active sketch profile (asks for one if absent)",
         True),
        ("H", "Hole — drill every sketch circle (counterbore/countersink)",
         True),
        ("F", "Fillet body edges…", True),
        ("M", "Move body (triad; Ctrl during drag = copy)", True),
        ("A", "Appearance / material…", True),
        ("V", "Hide / show the active body", True),
        ("N", "New sketch (on origin plane or browser plane)", True),
        ("W", "Sweep — pipe the sketch's circle along its line/arc path",
         True),
        ("Ctrl + L", "Loft — blend one sketch's profile into another's",
         True),
        ("Ctrl + Shift + P",
         "Construction plane — offset / at-angle / 3-point / midplane",
         True),
        ("Ctrl + Shift + O",
         "Work axis — two points or the join of two planes", True),
        ("Press-pull", "drag a flat face with the left button", False),
    ]),
    ("Panels, styles & compute", [
        ("Ctrl + B", "Compute All", True),
        ("Ctrl + 4", "Visual style: Shaded", True),
        ("Ctrl + 5", "Visual style: Shaded with edges", True),
        ("Ctrl + 6", "Visual style: Ghosted", True),
        ("Ctrl + 7", "Visual style: Wireframe", True),
        ("Ctrl + Alt + V", "Show / hide the ViewCube", True),
        ("Ctrl + Alt + B", "Show / hide the browser", True),
        ("Ctrl + Alt + N", "Show / hide the navigation stack", True),
        ("Ctrl + Alt + D", "Show / hide datum letters in the viewport",
         True),
        ("Ctrl + Alt + R", "Reset panel layout", True),
    ]),
    ("Sketching", [
        ("L", "Line tool — click-move-click chains · Collinear (2 lines)",
         True),
        ("R", "Rectangle tool — click-click or drag", True),
        ("C", "Circle tool", True),
        ("Shift + C", "Ellipse tool", True),
        ("A", "Arc tool — start · end · bulge, chained", True),
        ("Y", "Polygon tool — centre · vertex · number keys 3-9 set sides",
         True),
        ("K", "Slot tool — centre · centre · width, tangent-locked", True),
        ("O", "Offset outline — parallel mitred copy (U = classic alias)",
         True),
        ("T", "Trim / extend two loose lines into a shared corner", True),
        ("X", "Toggle construction geometry (with entities selected)", True),
        ("Esc", "Cancel tool / clear selection", True),
        ("Enter", "Finish sketch → extrude profile (ends line chains)",
         True),
        ("Shift + R", "Finish sketch → revolve about sketch's vertical axis",
         True),
        ("Ctrl + Z", "Undo last sketch step", True),
        ("Ctrl + Shift + Z", "Redo (or Ctrl + Y)", True),
        ("Double-click a badge", "Type a new dimension value", False),
        ("Drag a point", "Move geometry (snaps + auto H/V)", False),
    ]),
    ("Sketch constraints & dimensions", [
        ("H", "Horizontal constraint on selected lines", True),
        ("V", "Vertical constraint", True),
        ("P", "Project model edges into this sketch (Fusion's Project)",
         True),
        ("Shift + P", "Perpendicular constraint (two lines)", True),
        ("Q", "Equal constraint (lines → same length · curves → radius)",
         True),
        ("2", "Concentric constraint (two circles/arcs)", True),
        ("M", "Symmetry constraint (point · point · line axis)", True),
        ("Shift + M", "Mirror entities about a selected line", True),
        ("J", "Midpoint constraint (point + line → pin to center)", True),
        ("Shift + T", "Tangent constraint (line↔circle/arc, or two curves)",
         True),
        ("I", "Angular dimension (one line: from +X · two lines: between)",
         True),
        ("F", "Fix a point · fillet a corner with two lines selected", True),
        ("G", "Chamfer corner (two lines sharing a corner)", True),
        (".", "On-curve constraint (point + line/circle/arc)", True),
        ("D", "Distance dimension (1 line, 2 points, or pick)", True),
        ("Delete", "Delete selected entities", True),
    ]),
    ("Drawing sheet (while the sheet is focused)", [
        ("D", "Toggle the dimension tool — click two view points", True),
        ("B", "Toggle balloons — one click pins the next item number",
         True),
        ("F", "Fit callout (ISO 286): click a dimension bubble, pick H7, "
              "g6, H7/g6… — paper carries the fit, model stays nominal",
         True),
        ("S", "Cut-line tool: two clicks on the top, front or right "
              "view stand a lettered section (A-A…) there; Shift "
              "flips the kept half; Alt sets a corner and a "
              "double-click finishes a JOGGED line", True),
        ("Double-click a section view", "Its props: depth (full / "
         "slice / distance slab), kept side, hidden lines, scale",
         False),
        ("G", "GD&T frame: click a dimension bubble to pin a feature "
              "control frame — painted symbols, ISO-checked cells, "
              "separate datums |A|B|C; tick Basic to box the dim",
         True),
        ("Esc", "Stand every sheet tool down", True),
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
    ("S", "command search — every command, two keys"),
    ("N", "sketch · L/R/C/Shift+C/A/Y/K to draw"),
    ("E or Enter", "finish → extrude"),
    ("MMB / wheel", "orbit · zoom to cursor (Shift+MMB pans, RMB "
     "orbits, hold RMB for the marking wheel)"),
    ("Double-click face", "sketch on it"),
    ("Drag a flat face", "press-pull material"),
    ("D + double-click", "dimension, then edit it"),
    ("T · F · Shift+T", "trim · fillet · tangent"),
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
            head.setStyleSheet(f"color:{DARK['accent_soft']}; padding-top:6px;")
            col.addWidget(head)
            for keys, what, _kb in rows:
                row = QHBoxLayout()
                row.setSpacing(10)
                k = QLabel(keys)
                k.setFont(mono)
                k.setStyleSheet(f"color:{DARK['hover']};")
                k.setMinimumWidth(190)
                row.addWidget(k)
                row.addWidget(QLabel(what))
                row.addStretch(1)
                col.addLayout(row)
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet(f"color:{DARK['line']};")
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
            k.setStyleSheet(f"color:{DARK['hover']};")
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
