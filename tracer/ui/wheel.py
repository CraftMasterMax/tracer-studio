"""The marking wheel (M132) — Fusion's signature canvas command surface.

Structure cloned, identity never: hold the right button still and a
four-wedge ring blooms centred on the cursor — north/east/south/west
commands, hover highlights its wedge, release inside a wedge runs it,
release over the hub or the void (or Esc) dismisses. A quick tap leaves
the ring unopened and the plain context menu answers; a drag before the
ring opens was an orbit all along.

The wheel is NOT a window — it is state plus a paint routine the host
viewport draws in its own overlay pass and drives with a mouse grab.
That is both how the vendor's ring feels (it paints over the model, it
does not occlude it with a dialog) and what makes it deterministic to
test and to screenshot: no top-level popup, no grab that varies per
platform. All of the radial geometry is one pure function, wedge_at,
so the whole grammar is checkable without a mouse or a clock.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen

from . import theme

HOLD_MS = 200             # hold-to-open; below it, a tap = menu
R_IN, R_OUT = 26.0, 92.0  # hub radius and ring radius, px


def wedge_at(dx: float, dy: float,
             r_in: float = R_IN, r_out: float = R_OUT) -> int | None:
    """Compass sector of an offset from the wheel centre: 0=N, 1=E,
    2=S, 3=W; None on the hub, the void, or dead-centre. Widget y
    grows downward, hence atan2(dx, -dy) for clockwise-from-north."""
    r = math.hypot(dx, dy)
    if r < r_in or r > r_out:
        return None
    ang = math.degrees(math.atan2(dx, -dy)) % 360.0
    return int(((ang + 45.0) % 360.0) // 90.0)


class MarkingWheel:
    """Radial-menu state anchored at a point in the host's widget
    space.  `commands` is four (label, callable) pairs, N/E/S/W."""

    def __init__(self, center, commands):
        cx, cy = (center.x(), center.y()) if hasattr(center, "x") else center
        self.center = QPointF(cx, cy)
        self._cmds = list(commands)[:4]
        self.hover: int | None = None

    # -- pure: which wedge, and what it runs -----------------------------
    def pick(self, pos) -> int | None:
        px, py = (pos.x(), pos.y()) if hasattr(pos, "x") else pos
        return wedge_at(px - self.center.x(), py - self.center.y())

    def set_hover(self, pos) -> bool:
        """Track the cursor; True if the highlight moved (repaint)."""
        h = self.pick(pos)
        if h == self.hover:
            return False
        self.hover = h
        return True

    def commands(self):
        return list(self._cmds)

    def run(self, idx: int):
        self._cmds[idx][1]()

    # -- the look: painted onto the host's QPainter ------------------------
    def paint(self, p: QPainter, font):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        c = self.center
        dark = theme.DARK
        base = QColor(dark["bg2"])
        hot = QColor(dark["accent_soft"])
        outer = (c.x() - R_OUT, c.y() - R_OUT, 2 * R_OUT, 2 * R_OUT)
        inner = (c.x() - R_IN, c.y() - R_IN, 2 * R_IN, 2 * R_IN)
        p.setFont(font)
        fm = QFontMetrics(font)
        for i in range(len(self._cmds)):
            # Wedge i's compass centre is 90*i clockwise from north; Qt
            # angles run CCW from east (0°), so the sector's leading
            # edge sits at 135 - 90*i. (45 would rotate every fill one
            # quadrant off its label — the proof shot caught it.)
            start = 135 - 90 * i
            path = QPainterPath()
            path.arcMoveTo(*outer, start)
            path.arcTo(*outer, start, -90)
            path.arcTo(*inner, start - 90, 90)
            path.closeSubpath()
            fill = hot if i == self.hover else base
            fill.setAlpha(238 if i == self.hover else 222)
            p.fillPath(path, fill)
            p.setPen(QPen(QColor(dark["line"]), 1))
            p.drawPath(path)
            a = math.radians(90 * i)       # wedge centre bearing
            lp = QPointF(c.x() + 0.63 * R_OUT * math.sin(a),
                         c.y() - 0.63 * R_OUT * math.cos(a))
            p.setPen(QPen(QColor(dark["fg"])))
            box = QRectF(lp.x() - R_OUT * 0.5, lp.y() - fm.height() / 2,
                         R_OUT, fm.height())
            p.drawText(box, Qt.AlignCenter, self._cmds[i][0])
        p.setPen(QPen(QColor(dark["line"]), 1))
        p.setBrush(QColor(dark["bg1"]))
        p.drawEllipse(c, int(R_IN), int(R_IN))
        p.restore()
