"""Small monochrome line icons for the quick toolbar.

Glyphs are plain geometry (cube, revolve arc, arrays, rounded corner...)
drawn with QPainter, so they carry no third-party artwork and stay
crisp at any DPI.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

_COL = QColor("#cfd4da")


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
         "fillet": _fillet, "chamfer": _chamfer}


def icon(name: str) -> QIcon:
    if name not in _DRAW:
        raise KeyError(f"no icon named {name!r}")
    return QIcon(_pm(_DRAW[name]))
