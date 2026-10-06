"""Small monochrome line icons for the quick toolbar.

Glyphs are plain geometry (cube, revolve arc, arrays, rounded corner...)
drawn with QPainter, so they carry no third-party artwork and stay
crisp at any DPI.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import (QColor, QIcon, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF)

_COL = QColor("#e4e8ee")


def _pm(draw) -> QPixmap:
    pm = QPixmap(QSize(32, 32))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(_COL)
    pen.setWidthF(1.9)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    draw(p)
    p.end()
    return pm


def _box(p: QPainter):
    """Extrusion: a small 3D block."""
    p.drawPolygon(QPolygonF([QPointF(7, 17), QPointF(12, 11),
                             QPointF(26, 11), QPointF(21, 17)]))
    p.drawRect(7, 17, 14, 9)
    p.drawLine(QPointF(21, 17), QPointF(26, 11))
    p.drawLine(QPointF(21, 26), QPointF(26, 20))
    p.drawLine(QPointF(26, 11), QPointF(26, 20))


def _sketch(p: QPainter):
    """A profile outline with a node point."""
    p.drawRoundedRect(QRectF(7, 9, 15, 15), 3, 3)
    p.setBrush(_COL)
    p.drawEllipse(QPointF(25, 8), 2.6, 2.6)


def _revolve(p: QPainter):
    """A body swung around a vertical axis."""
    pen = QPen(_COL)
    pen.setWidthF(1.9)
    pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawLine(QPointF(10, 5), QPointF(10, 27))
    p.setPen(QPen(_COL, 1.9))
    p.drawArc(QRectF(10, 9, 15, 15), 0, 90 * 16)
    p.drawArc(QRectF(10, 9, 15, 15), 180 * 16, 60 * 16)
    p.setBrush(_COL)
    p.drawPolygon(QPolygonF([QPointF(25, 14), QPointF(25, 20),
                             QPointF(28.5, 17)]))


def _pattern(p: QPainter):
    """Linear array of three blocks."""
    for x in (5, 13.5, 22):
        p.drawRect(QRectF(x, 12, 6, 9))


def _cpattern(p: QPainter):
    """Radial array around a centre."""
    c = QPointF(16, 16)
    p.drawEllipse(c, 2.0, 2.0)
    import math
    for k in range(3):
        a = math.radians(90 * k)
        x, y = c.x() + 8 * math.cos(a), c.y() - 8 * math.sin(a)
        p.drawRect(QRectF(x - 3, y - 3, 6, 6))
    p.drawEllipse(c, 11.5, 11.5)


def _ppattern(p: QPainter):
    """A block array walking a curved path: three copies on a dashed arc."""
    import math
    pen = QPen(_COL)
    pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawArc(QRectF(3, 7, 26, 26), 0, 90 * 16)
    pen.setStyle(Qt.PenStyle.SolidLine)
    p.setPen(pen)
    p.setBrush(_COL)
    for k in (0, 45, 90):
        a = math.radians(k)
        x, y = 16 + 13 * math.cos(a), 20 - 13 * math.sin(a)
        p.drawRect(QRectF(x - 2.5, y - 2.5, 5, 5))


def _mirror(p: QPainter):
    """Solid half, ghost half, plane between."""
    p.drawPolygon(QPolygonF([QPointF(6, 24), QPointF(6, 10),
                             QPointF(14, 24)]))
    pen = QPen(_COL)
    pen.setWidthF(1.4)
    pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawPolygon(QPolygonF([QPointF(26, 24), QPointF(26, 10),
                             QPointF(18, 24)]))
    pen.setStyle(Qt.PenStyle.SolidLine)
    p.setPen(pen)
    p.drawLine(QPointF(16, 5), QPointF(16, 28))


def _fillet(p: QPainter):
    """Right angle blended with a tangent arc."""
    p.drawLine(QPointF(7, 25), QPointF(7, 14))
    p.drawLine(QPointF(7, 25), QPointF(26, 25))
    p.drawArc(QRectF(7, 7, 18, 18), 0, 90 * 16)


def _chamfer(p: QPainter):
    """Right angle cut with a flat bevel."""
    p.drawLine(QPointF(7, 25), QPointF(7, 16))
    p.drawLine(QPointF(7, 25), QPointF(26, 25))
    p.drawLine(QPointF(7, 16), QPointF(16, 25))


_DRAW = {"sketch": _sketch, "extrude": _box, "revolve": _revolve,
         "pattern": _pattern, "cpattern": _cpattern, "mirror": _mirror,
         "ppattern": _ppattern,
         "fillet": _fillet, "chamfer": _chamfer}


# ---- ribbon glyphs: generic geometry only (identity-safe) --------------------

def _hole(p: QPainter):
    p.drawEllipse(QPointF(16, 16), 7.5, 7.5)
    p.drawLine(QPointF(5, 16), QPointF(27, 16))


def _sweep(p: QPainter):
    p.drawEllipse(QPointF(9, 16), 5, 5)
    p.drawEllipse(QPointF(24, 13), 4, 4)
    p.drawLine(QPointF(11, 12), QPointF(22, 10))
    p.drawLine(QPointF(12, 20), QPointF(25, 16))


def _loft(p: QPainter):
    p.drawRect(QRectF(12, 7, 8, 6))
    p.drawRect(QRectF(7, 20, 18, 6))
    p.drawLine(QPointF(12, 13), QPointF(7, 20))
    p.drawLine(QPointF(20, 13), QPointF(25, 20))


def _shell(p: QPainter):
    p.drawPolyline(QPolygonF([QPointF(8, 8), QPointF(8, 25),
                              QPointF(25, 25), QPointF(25, 8)]))
    p.drawRect(QRectF(13, 13, 7, 7))


def _new(p: QPainter):
    p.drawPolyline(QPolygonF([QPointF(9, 5), QPointF(19, 5),
                              QPointF(24, 10), QPointF(24, 27),
                              QPointF(9, 27), QPointF(9, 5)]))
    p.drawLine(QPointF(19, 5), QPointF(19, 10))
    p.drawLine(QPointF(19, 10), QPointF(24, 10))


def _open(p: QPainter):
    p.drawPolyline(QPolygonF([QPointF(5, 25), QPointF(5, 10),
                              QPointF(13, 10), QPointF(16, 13),
                              QPointF(27, 13), QPointF(27, 25),
                              QPointF(5, 25)]))
    p.drawLine(QPointF(5, 17), QPointF(27, 17))


def _save(p: QPainter):
    p.drawRect(QRectF(6, 6, 20, 20))
    p.drawRect(QRectF(11, 6, 10, 7))
    p.drawRect(QRectF(10, 16, 12, 10))


def _undo(p: QPainter):
    p.drawArc(QRectF(8, 9, 16, 14), 30 * 16, 230 * 16)
    p.drawPolyline(QPolygonF([QPointF(8, 14), QPointF(8, 20),
                              QPointF(14, 20)]))


def _redo(p: QPainter):
    p.drawArc(QRectF(8, 9, 16, 14), -80 * 16, 230 * 16)
    p.drawPolyline(QPolygonF([QPointF(24, 14), QPointF(24, 20),
                              QPointF(18, 20)]))


def _line(p: QPainter):
    p.drawLine(QPointF(8, 24), QPointF(24, 8))
    p.drawEllipse(QPointF(8, 24), 1.6, 1.6)
    p.drawEllipse(QPointF(24, 8), 1.6, 1.6)


def _rect(p: QPainter):
    p.drawRect(QRectF(7, 10, 18, 13))


def _circle(p: QPainter):
    p.drawEllipse(QPointF(16, 16), 8, 8)


def _slot(p: QPainter):
    p.drawRoundedRect(QRectF(6, 12, 20, 8), 4, 4)


def _poly(p: QPainter):
    p.drawPolyline(QPolygonF([QPointF(16, 6), QPointF(26, 13),
                              QPointF(22, 25), QPointF(10, 25),
                              QPointF(6, 13), QPointF(16, 6)]))


def _arc(p: QPainter):
    p.drawArc(QRectF(7, 7, 18, 18), 20 * 16, 120 * 16)
    p.drawEllipse(QPointF(23, 11), 1.6, 1.6)
    p.drawEllipse(QPointF(10, 22), 1.6, 1.6)


def _trim(p: QPainter):
    p.drawLine(QPointF(6, 20), QPointF(26, 10))
    p.drawLine(QPointF(26, 22), QPointF(6, 12))
    p.drawEllipse(QPointF(16, 16), 1.8, 1.8)


def _offset(p: QPainter):
    p.drawRect(QRectF(6, 8, 20, 16))
    pen = QPen(_COL)
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setWidthF(1.4)
    p.setPen(pen)
    p.drawRect(QRectF(11, 12, 10, 8))


def _construction(p: QPainter):
    pen = QPen(_COL)
    pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawRect(QRectF(7, 9, 18, 14))


def _plane(p: QPainter):
    p.drawPolyline(QPolygonF([QPointF(7, 22), QPointF(13, 10),
                              QPointF(26, 10), QPointF(20, 22),
                              QPointF(7, 22)]))
    p.setPen(QPen(_COL, 1.2))
    p.drawLine(QPointF(13, 10), QPointF(20, 22))


def _constrain(p: QPainter):
    """Two lines joined by a link pin: geometry tied together."""
    p.drawLine(QPointF(7, 7), QPointF(7, 25))
    p.drawLine(QPointF(18, 7), QPointF(18, 25))
    p.drawLine(QPointF(7, 16), QPointF(19, 16))
    p.drawEllipse(QPointF(22.5, 16), 3.0, 3.0)


def _launcher(p: QPainter):
    """App mark: a rounded plate with parametric nodes (generic,
    identity-safe — no third-party artwork)."""
    p.drawRoundedRect(QRectF(6, 6, 20, 20), 5, 5)
    p.setBrush(_COL)
    for x, y in ((6, 6), (26, 6), (6, 26)):
        p.drawEllipse(QPointF(x, y), 2.3, 2.3)


def _section(p: QPainter):
    """A block sliced by a dashed clip plane."""
    p.drawRect(QRectF(7, 9, 18, 16))
    pen = QPen(_COL)
    pen.setWidthF(1.5)
    pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawLine(QPointF(5, 17), QPointF(27, 17))


def _move(p: QPainter):
    """A ghost outline pushed into a solid arrow — the move sticker."""
    p.drawRect(QRectF(5, 17, 10, 10))
    pen = QPen(_COL)
    pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawRect(QRectF(9, 13, 10, 10))
    pen.setStyle(Qt.PenStyle.SolidLine)
    pen.setWidthF(2.2)
    p.setPen(pen)
    p.drawLine(QPointF(14, 18), QPointF(25, 7))
    p.setBrush(_COL)
    tri = QPolygonF([QPointF(26, 4), QPointF(26, 12), QPointF(18, 6)])
    p.drawPolygon(tri)


def _appearance(p: QPainter):
    """A paint drop landing on a brushed band."""
    path = QPainterPath()
    path.moveTo(16, 4)
    path.cubicTo(24, 13, 23, 20, 16, 20)
    path.cubicTo(9, 20, 8, 13, 16, 4)
    p.fillPath(path, _COL)
    p.setBrush(_COL)
    p.drawRect(QRectF(5, 23, 22, 5))


def _split(p: QPainter):
    """A solid sliced into two halves by a dashed plane."""
    p.drawRect(QRectF(6, 9, 20, 16))
    pen = QPen(_COL)
    pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawLine(QPointF(16, 6), QPointF(16, 27))


def _thread(p: QPainter):
    """A bolt shank with helical thread diagonals."""
    p.drawRect(QRectF(11, 5, 10, 22))
    for y in (9, 14, 19, 24):
        p.drawLine(QPointF(11, y + 3), QPointF(21, y))


def _dimension(p: QPainter):
    """Measured span: ticks, arrowheads, baseline."""
    p.drawLine(QPointF(5, 16), QPointF(27, 16))
    p.drawLine(QPointF(5, 11), QPointF(5, 21))
    p.drawLine(QPointF(27, 11), QPointF(27, 21))
    p.drawPolyline(QPolygonF([QPointF(9, 13), QPointF(5, 16),
                              QPointF(9, 19)]))
    p.drawPolyline(QPolygonF([QPointF(23, 13), QPointF(27, 16),
                              QPointF(23, 19)]))


_DRAW.update({"hole": _hole, "sweep": _sweep, "loft": _loft,
              "shell": _shell, "new": _new, "open": _open, "save": _save,
              "undo": _undo, "redo": _redo, "line": _line, "rect": _rect,
              "circle": _circle, "slot": _slot, "poly": _poly,
              "arc": _arc, "trim": _trim, "offset": _offset,
              "construction": _construction, "plane": _plane,
              "constrain": _constrain, "dimension": _dimension,
              "launcher": _launcher, "section": _section,
              "thread": _thread, "split": _split,
              "appearance": _appearance, "move": _move})


def icon(name: str) -> QIcon:
    if name not in _DRAW:
        raise KeyError(f"no icon named {name!r}")
    return QIcon(_pm(_DRAW[name]))
