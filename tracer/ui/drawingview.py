"""M93 — the drawing sheet canvas: white paper, live views, zoom & pan.

Views are never stored: every paint re-derives silhouettes from the
model in front of it, so the sheet can't rot while the solid changes —
the same honesty Fusion's views buy by rebuilding.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from PySide6.QtWidgets import QWidget

from ..core import drawing


class DrawingCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.page = "A3"
        self._zoom = 1.6                       # screen px per sheet mm
        self._center = QPointF(0.0, 0.0)       # sheet mm coords at centre
        self._drag = None
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)

    def set_document(self, doc):
        self.doc = doc
        if doc is not None and doc.drawings:
            self.page = doc.drawings[-1].get("page", "A3")
        self._center = QPointF(*[v / 2 for v in drawing.PAGES.get(
            self.page, drawing.PAGES["A3"])])
        self.update()

    # ---- data -----------------------------------------------------------
    def views(self) -> dict:
        """Live silhouette views of the current result (model space)."""
        if self.doc is None or self.doc.result is None:
            return {}
        return {v: drawing.project_view(self.doc.result, view=v)
                for v in drawing.STANDARD}

    def chains(self, view: str = "top") -> list:
        return self.views().get(view, [])

    def layout(self) -> dict:
        """Page-coordinate chains (mm, y-up, origin lower-left)."""
        return drawing.layout(self.views(), page=self.page)

    # ---- paint ----------------------------------------------------------
    def s2p(self, x: float, y: float) -> QPointF:
        """Sheet mm -> widget px: centred, y flipped (sheet y is up)."""
        w, h = self.width(), self.height()
        return QPointF(w / 2 + (x - self._center.x()) * self._zoom,
                       h / 2 - (y - self._center.y()) * self._zoom)

    def paintEvent(self, ev):
        p = QPainter(self)
        self.paintPage(p)
        p.end()

    def paintPage(self, p: QPainter):
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(52, 56, 62))          # desk grey
        W, H = drawing.PAGES.get(self.page, drawing.PAGES["A3"])
        a = self.s2p(0, 0)
        b = self.s2p(W, H)
        sheet = QRectF(min(a.x(), b.x()), min(a.y(), b.y()),
                       abs(b.x() - a.x()), abs(b.y() - a.y()))
        p.setPen(QPen(QColor(20, 22, 26), 1))
        p.setBrush(QColor("#f5f5f2"))                        # the paper
        p.drawRect(sheet)
        p.setBrush(Qt.NoBrush)
        # title block bottom-right, Fusion-sheet style
        tb = QRectF(sheet.right() - 150 * self._zoom,
                    sheet.bottom() - 24 * self._zoom,
                    150 * self._zoom, 24 * self._zoom)
        p.setPen(QPen(QColor(90, 94, 100), 1))
        p.drawRect(tb)
        name = ""
        if self.doc is not None and self.doc.drawings:
            name = self.doc.drawings[-1].get("name", "")
        p.setPen(QPen(QColor(40, 42, 46)))
        f = p.font()
        f.setPointSizeF(max(6.0, 9 * min(self._zoom, 2.0)))
        p.setFont(f)
        p.drawText(tb.adjusted(6, 2, -6, -2),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   f"{name}   {self.page}   1:{max(1, round(1 / self.page_scale()))}"
                   if self.views() else name)
        # views
        lay = self.layout()
        p.setPen(QPen(QColor(28, 30, 34), max(1.0, 0.35 * self._zoom)))
        for chains in lay.values():
            for c in chains:
                if len(c) < 2:
                    continue
                pts = [self.s2p(x, y) for x, y in c]
                for i in range(len(pts) - 1):
                    p.drawLine(pts[i], pts[i + 1])

    def page_scale(self) -> float:
        views = self.views()
        if not views:
            return 1.0
        return drawing.fit_scale(views, page=self.page)

    # ---- navigation -----------------------------------------------------
    def wheelEvent(self, ev):
        self._zoom = min(8.0, max(0.25, self._zoom *
                                  (1.15 if ev.angleDelta().y() > 0
                                   else 1 / 1.15)))
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() in (Qt.MiddleButton, Qt.LeftButton):
            self._drag = ev.position()

    def mouseMoveEvent(self, ev):
        if self._drag is not None:
            d = ev.position() - self._drag
            self._center += QPointF(-d.x() / self._zoom, d.y() / self._zoom)
            self._drag = ev.position()
            self.update()

    def mouseReleaseEvent(self, ev):
        self._drag = None
