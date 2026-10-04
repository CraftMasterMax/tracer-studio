"""Fusion-style timeline: horizontal feature chips, double-click to edit.

Chips render as small blocks with the operation color (union accent,
subtract red) + name; wheel scrolls horizontally; context menu gets
Edit/Delete later (M+1).
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QScrollArea, QWidget

from ..core.document import Document

OP_COLOR = {"union": "#4ea1ff", "subtract": "#e06c75", "intersect": "#9aa1ac"}


class TimelineBar(QWidget):
    feature_clicked = Signal(object)        # Feature
    feature_activated = Signal(object)      # double-click = edit
    feature_menu = Signal(object, object)   # Feature, global QPoint

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Document | None = None
        self._chips: list[tuple[int, int, object]] = []   # x, w, feature
        self._sel: int = -1
        self.setMinimumHeight(38)
        self.setMouseTracking(True)
        self._font = self.font()

    def set_document(self, doc: Document):
        self.doc = doc
        self._sel = -1
        self.update()

    def _label(self, f) -> str:
        if getattr(f, "suppressed", False):
            return f"\u25cb {f.name}"
        glyph = {"union": "+", "subtract": "\u2212", "intersect": "\u2229"}[f.op]
        return f"{glyph} {f.name}"

    def paintEvent(self, ev):
        with QPainter(self) as p:
            p.setRenderHint(QPainter.Antialiasing)
            p.fillRect(self.rect(), QColor("#141518"))
            p.setPen(QPen(QColor("#2d313a")))
            p.drawLine(0, 0, self.width(), 0)
            self._chips = []
            if not self.doc:
                return            # safe now: context manager closes painter
            fm = QFontMetrics(self._font)
            x = 8
            for i, f in enumerate(self.doc.features):
                label = self._label(f)
                w = fm.horizontalAdvance(label) + 22
                y, h = 6, self.height() - 14
                r = QRectF(x, y, w, h)
                dim = getattr(f, "suppressed", False)
                p.setBrush(QColor("#1b1d22" if dim else
                                 ("#23262c" if i != self._sel else "#2c313b")))
                pen = QPen(QColor("#5f6672") if dim else QColor(OP_COLOR[f.op]))
                pen.setWidthF(1.0 if i != self._sel else 1.8)
                p.setPen(pen)
                p.drawRoundedRect(r, 4, 4)
                p.setPen(QColor("#5f6672") if dim else QColor("#e8eaed"))
                p.drawText(r, Qt.AlignCenter, label)
                self._chips.append((x, w, f))
                x += w + 6

    def mousePressEvent(self, ev):
        for x, w, f in self._chips:
            if x <= ev.position().x() <= x + w:
                if ev.button() == Qt.RightButton:
                    self.feature_menu.emit(f, ev.globalPosition().toPoint())
                    return
                self._sel = self.doc.features.index(f)
                self.feature_clicked.emit(f)
                self.update()
                return
        self._sel = -1
        self.update()

    def mouseDoubleClickEvent(self, ev):
        for x, w, f in self._chips:
            if x <= ev.position().x() <= x + w:
                self.feature_activated.emit(f)
                return

    def wheelEvent(self, ev):
        bar = self.parent()
        if isinstance(bar, QScrollArea):
            bar.horizontalScrollBar().setValue(
                bar.horizontalScrollBar().value() - ev.angleDelta().y())


class TimelineHost(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bar = TimelineBar()
        self.setWidget(self.bar)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(42)
        self.frame = None

    def set_document(self, doc):
        self.bar.set_document(doc)
