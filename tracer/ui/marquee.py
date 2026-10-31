"""M184: the ONE dress mouth for rubber-band selection (FD8 LAW-49).

"Crossing = DASHED, window = solid... SELECTIONAREAOPACITY = 25"
[documented appearance, AutoCAD-family law]. Both canvases (sketch and
3D viewport) ask HERE - so the dress can never drift between them.
Keep this module pure: no widget, no painter - a decision, not a draw.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

FILL_ALPHA = 64          # SELECTIONAREAOPACITY = 25 -> 0.25 * 255


def marquee_paint(crossing: bool, color: str):
    """(pen style, fill) for a selection band: a left-to-right WINDOW
    rides a SOLID edge, a right-to-left CROSSING is DASHED; both fill
    at 25% of their own color so geometry stays readable THROUGH the
    law (LAW-49 - the dress is meaning, not decoration)."""
    style = (Qt.PenStyle.DashLine if crossing
             else Qt.PenStyle.SolidLine)
    c = QColor(color)
    return style, QColor(c.red(), c.green(), c.blue(), FILL_ALPHA)
