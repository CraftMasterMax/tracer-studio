"""Fusion-style timeline: icon-only chips (one per feature) on a dark
strip, playhead arrow at the head of the strip, hover shows the feature
name, click selects, double-click edits, right-click opens the menu.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QScrollArea, QToolTip, QWidget

from ..core.document import (BodyFilletFeature, Document, LoftFeature,
                             ShellFeature, SweepFeature)
from . import theme

OP_COLOR = {"union": theme.DARK["accent"], "subtract": theme.DARK["danger"],
            "intersect": theme.DARK["fg_dim"]}


class TimelineBar(QWidget):
    feature_clicked = Signal(object)        # Feature
    feature_activated = Signal(object)      # double-click = edit
    feature_menu = Signal(object, object)   # Feature, global QPoint
    feature_delete = Signal(object)         # Delete key on selected chip
    home_clicked = Signal()                 # playhead: view home
    rollback_changed = Signal(object)       # M88: index or None (end)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Document | None = None
        self._chips: list[tuple[int, int, object]] = []   # x, w, feature
        self._home = QRectF(6, 7, 22, 22)
        self._marker: QRectF | None = None   # M88 rubber band hit rect
        self._sel: int = -1
        self.setMinimumHeight(38)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._font = self.font()
        self._glyph_font = QFont(self._font)
        self._glyph_font.setPointSizeF(self._font.pointSizeF() * 1.25)

    def keyPressEvent(self, ev):
        if (ev.key() in (Qt.Key_Delete, Qt.Key_Backspace)
                and self.doc is not None and 0 <= self._sel < len(self.doc.features)):
            self.feature_delete.emit(self.doc.features[self._sel])
            self._sel = -1
            self.update()
            return
        super().keyPressEvent(ev)

    def select_feature(self, f) -> None:
        """M118: select a chip from outside — the Message Log's answer
        to the question Fusion never let you ask ('which feature broke?')."""
        if self.doc is None or f not in self.doc.features:
            return
        self._sel = self.doc.features.index(f)
        self.update()

    def set_document(self, doc: Document):
        self.doc = doc
        self._sel = -1
        self.update()

    def _label(self, f) -> str:
        if getattr(f, "suppressed", False):
            return f"\u25cb {f.name}"
        if isinstance(f, BodyFilletFeature):          # body op: ⌒ not +
            return f"\u2312 {f.name}"
        glyph = {"union": "+", "subtract": "\u2212", "intersect": "\u2229"}[f.op]
        return f"{glyph} {f.name}"

    def _glyph(self, f) -> str:
        if getattr(f, "suppressed", False):
            return "\u25cb"
        if isinstance(f, SweepFeature):
            return "\u2933"
        if isinstance(f, LoftFeature):
            return "\u25b3"
        if isinstance(f, ShellFeature):
            return "\u25a4"
        if isinstance(f, BodyFilletFeature):
            return "\u25d0" if f.chamfer else "\u2312"
        return {"union": "+", "subtract": "\u2212", "intersect": "\u2229"}[f.op]

    def paintEvent(self, ev):
        D = theme.DARK
        with QPainter(self) as p:
            p.setRenderHint(QPainter.Antialiasing)
            p.fillRect(self.rect(), QColor(D["bg0"]))
            p.setPen(QPen(QColor(D["line"])))
            p.drawLine(0, 0, self.width(), 0)
            self._chips = []
            # playhead: history position marker (click = home view)
            h = self.height() - 14
            self._home = QRectF(6, 7, 22, h)
            p.setBrush(QColor(D["bg1"]))
            p.setPen(QPen(QColor(D["line"]), 1))
            p.drawRoundedRect(self._home, 4, 4)
            mid = self._home.center()
            tri = QPolygonF([QPointF(mid.x() - 3, mid.y() - 5),
                             QPointF(mid.x() - 3, mid.y() + 5),
                             QPointF(mid.x() + 5, mid.y())])
            p.setBrush(QColor(D["fg"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(tri)
            if not self.doc:
                return        # safe now: context manager closes painter
            x = 34
            last = len(self.doc.features) - 1
            rb = getattr(self.doc, "rollback_to", None)   # M88 rubber band
            self._marker = None
            if rb == 0:
                self._marker = QRectF(31, 5, 6, h + 4)
                p.setPen(QPen(QColor(D["accent"]), 2.2))
                p.drawLine(34, 6, 34, 6 + int(h))
            for i, f in enumerate(self.doc.features):
                r = QRectF(x, 7, 30, h)
                dim = (getattr(f, "suppressed", False)
                       or (rb is not None and i >= rb))    # hidden by band
                sel = i == self._sel
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(D["bg1"] if dim
                                 else (D["accent_deep"] if sel
                                       else D["bg2"])))
                p.drawRoundedRect(r, 4, 4)
                pen = QPen(QColor(D["fg_faint"]) if dim
                           else (QColor(D["accent"]) if i == last or sel
                                 else QColor(OP_COLOR[f.op])))
                pen.setWidthF(1.6 if (sel or i == last) else 1.0)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r, 4, 4)
                p.setFont(self._glyph_font)
                p.setPen(QColor(D["fg_faint"]) if dim else QColor(D["fg"]))
                p.drawText(r, Qt.AlignCenter, self._glyph(f))
                if getattr(f, "error", None):        # M118: red badge —
                    p.setPen(Qt.PenStyle.NoPen)      # the feature that
                    p.setBrush(QColor(D["danger"]))  # broke the last
                    p.drawEllipse(r.topRight() - QPointF(7, 7), 3, 3)
                self._chips.append((x, 30, f))
                if rb is not None and i + 1 == rb:
                    mx = x + 32                # rubber band after this chip
                    self._marker = QRectF(mx - 3, 5, 7, h + 4)
                    p.setPen(QPen(QColor(D["accent"]), 2.2))
                    p.drawLine(int(mx), 6, int(mx), 6 + int(h))
                x += 34

    # ---- hit tests ---------------------------------------------------------
    def _feature_at(self, pos) -> object | None:
        for x, w, f in self._chips:
            if x <= pos.x() <= x + w and 4 <= pos.y() <= self.height() - 4:
                return f
        return None

    def mouseMoveEvent(self, ev):
        f = self._feature_at(ev.position())
        QToolTip.showText(ev.globalPosition().toPoint(),
                          getattr(f, "name", "") if f else "", self)
        if f is None and not self._home.contains(ev.position()):
            QToolTip.hideText()

    def mousePressEvent(self, ev):
        if (self._marker is not None
                and self._marker.contains(ev.position())):
            self.rollback_changed.emit(None)          # M88: end rollback
            return
        if self._home.contains(ev.position()):
            self.home_clicked.emit()
            return
        f = self._feature_at(ev.position())
        if f is not None:
            if ev.button() == Qt.RightButton:
                self.feature_menu.emit(f, ev.globalPosition().toPoint())
                return
            self._sel = self.doc.features.index(f)
            self.setFocus()
            self.feature_clicked.emit(f)
            self.update()
            return
        self._sel = -1
        self.update()

    def mouseDoubleClickEvent(self, ev):
        f = self._feature_at(ev.position())
        if f is not None:
            self.feature_activated.emit(f)

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
