"""Fusion-style timeline: icon-only chips (one per feature) on a dark
strip, playhead arrow at the head of the strip, hover shows the feature
name, click selects, double-click edits, right-click opens the menu.

M161 THE TIMELINE GETS ITS TRANSPORT (research/fd4_timeline.md):
LAW-2 — the five permanent controls, exact order (Move to Beginning,
Previous Step, Play, Next Step, End of Timeline) docked at the strip's
LEFT; LAW-3 — the gear menu at the RIGHT edge; LAW-7 — the marker is
an integer slot 0..N, now DRAGGABLE (transport buttons just set it);
LAW-9 — the marker grew its triangular grab handle; LAW-13 — a
rolled-back chip is DIM WITH ITS OWN COLOR, never the suppressed gray;
LAW-14 — tooltips ride the transport too; LAW-4 — the wheel scrolls
the strip horizontally (fixed: the scroll area is found by walking
parents, and the viewport wrapper does not count). LAW-34: Play is
the ONLY sanctioned animation. The home triangle predates FD4 and
stays — LAW-6 files it as OUR OWN leading control, uncited.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
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
    gear_clicked = Signal(object)           # M161 LAW-3: Options menu
    #   (global QPoint — the MENU is the window's, the DOCK is the bar's)

    # LAW-2 (FD4): the five permanent controls, IN THIS ORDER, left
    # docked. The home triangle follows them — OUR own leading icon
    # (LAW-6 files it uncited; it predates FD4 and stays).
    TRANSPORT = ("begin", "prev", "play", "next", "end")
    TRANSPORT_TIPS = {"begin": "Move to Beginning",   # LAW-2 names,
                      "prev": "Previous Step",        #   LAW-14
                      "play": "Play",                 #   tooltips
                      "next": "Next Step",
                      "end": "End of Timeline"}
    TB = 24                                 # transport button pitch

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Document | None = None
        self._chips: list[tuple[int, int, object]] = []   # x, w, feature
        self._home = QRectF(6, 7, 22, 22)
        self._tb: list[tuple[str, QRectF]] = []   # M161 transport rects
        self._gear: QRectF | None = None          # LAW-3: gear, RIGHT
        self._playing = False                     # LAW-34: the ONLY
        #   sanctioned animation — a stepped timer, nothing else moves
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(260)         # step cadence (ours)
        self._play_timer.timeout.connect(self._play_step)
        self._drag_marker = False                 # LAW-7 draggable
        self._dragged = False
        self._drag_at = QPointF(0, 0)
        self._chip0 = 6 + self.TB * len(self.TRANSPORT) + 2 + 22 + 8
        self.hide_inactive = False                # LAW-3 menu item
        self._marker: QRectF | None = None   # M88 rubber band hit rect
        self._sel: int = -1
        self.setMinimumHeight(38)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._font = self.font()
        self._glyph_font = QFont(self._font)
        self._glyph_font.setPointSizeF(self._font.pointSizeF() * 1.25)

    # ---- transport (LAW-2/LAW-7/LAW-34) -----------------------------------
    def _slot(self) -> int:
        """LAW-7: the marker is an INTEGER SLOT 0..N between icons;
        rollback None means 'at the end' == N."""
        if self.doc is None:
            return 0
        n = len(self.doc.features)
        rb = getattr(self.doc, "rollback_to", None)
        return n if rb is None else max(0, min(n, int(rb)))

    def _emit_slot(self, slot: int):
        """Transport buttons just SET THE SLOT (LAW-7); end == None
        keeps the document's own vocabulary (M88)."""
        if self.doc is None:
            return
        self.rollback_changed.emit(None if slot >= len(self.doc.features)
                                   else max(0, int(slot)))

    def _tbutton(self, what: str):
        self._emit_slot({"begin": 0, "prev": self._slot() - 1,
                         "next": self._slot() + 1,
                         "end": 1 << 30}[what])

    def _play_step(self):
        """LAW-34: Play walks the slot forward one feature at a time —
        the filmstrip metaphor (LAW-25) — and stops at the end."""
        if self.doc is None:
            self._play_timer.stop()
            self._playing = False
            return
        s = self._slot()
        n = len(self.doc.features)
        if s >= n:
            self.stop_play()
            return
        self._emit_slot(s + 1)

    def start_play(self):
        if self.doc is None or not self.doc.features:
            return
        if self._slot() >= len(self.doc.features):
            # OURS-SAID: Play AT THE END rewinds first — the filmstrip
            # metaphor (LAW-25) replays; Fusion's API names play() but
            # the probe found no law for the at-end case.
            self._emit_slot(0)
        self._playing = True
        self._play_timer.start()
        self.update()

    def stop_play(self):
        self._playing = False
        self._play_timer.stop()
        self.update()

    def _draw_transport(self, p, D, h):
        """|◀ ◀ ▶ ▶ ▶| as POLYGONS — vector, not glyphs: deterministic
        pixels, no font-coverage roulette in headless CI (the transport
        IS a pixel-gated widget)."""
        self._tb = []
        x = 6.0
        for what in self.TRANSPORT:
            r = QRectF(x, 7, 20, h)
            mid = r.center()
            bar = QColor(D["fg_dim"] if self._slot_off(what)
                         else D["fg"])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bar)
            if what == "begin":
                p.drawRect(QRectF(mid.x() - 6, mid.y() - 5, 2, 10))
                self._tri_left(p, mid.x() + 4, mid.y())
            elif what == "prev":
                self._tri_left(p, mid.x() + 1, mid.y())
            elif what == "play":
                if self._playing:                    # pause = two bars
                    p.drawRect(QRectF(mid.x() - 5, mid.y() - 5, 3, 10))
                    p.drawRect(QRectF(mid.x() + 2, mid.y() - 5, 3, 10))
                else:
                    self._tri_right(p, mid.x() - 3, mid.y())
            elif what == "next":
                self._tri_right(p, mid.x() - 1, mid.y())
            else:                                    # end: ▶|
                self._tri_right(p, mid.x() - 4, mid.y())
                p.drawRect(QRectF(mid.x() + 4, mid.y() - 5, 2, 10))
            self._tb.append((what, r))
            x += self.TB

    @staticmethod
    def _tri_left(p, tipx, cy):
        p.drawPolygon(QPolygonF([QPointF(tipx - 7, cy),
                                 QPointF(tipx + 1, cy - 5),
                                 QPointF(tipx + 1, cy + 5)]))

    @staticmethod
    def _tri_right(p, tipx, cy):
        p.drawPolygon(QPolygonF([QPointF(tipx + 7, cy),
                                 QPointF(tipx - 1, cy - 5),
                                 QPointF(tipx - 1, cy + 5)]))

    def _slot_off(self, what: str) -> bool:
        """Disabled paint (LAW-20 selection-aware states, timeline
        edition): Begin at slot 0, End/Next at slot N."""
        s, n = self._slot(), (len(self.doc.features)
                              if self.doc is not None else 0)
        return ((what in ("begin", "prev") and s <= 0)
                or (what in ("end", "next") and s >= n))

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
            h = self.height() - 14
            # LAW-2: the five permanent controls, left docked, then our
            # own home triangle (LAW-6: uncited, pre-FD4, stays).
            self._draw_transport(p, D, h)
            self._home = QRectF(6 + self.TB * len(self.TRANSPORT) + 2,
                                7, 22, h)
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
            # LAW-3: the gear docks at the RIGHT edge (polygon teeth —
            # font roulette stays banned from pixel-gated ink)
            self._gear = QRectF(self.width() - 30, 7, 22, h)
            self._draw_gear(p, D)
            if not self.doc:
                return        # safe now: context manager closes painter
            x = self._home.right() + 8
            chip0 = x                  # slot arithmetic anchors here
            self._chip0 = x            #   (drag math reads it too)
            last = len(self.doc.features) - 1
            # rung D (M152): the feature names whose attachment state
            # is speaking this pass — document-side law keys every
            # sentence to a NAME, so the predicate is a name set
            warn_names = set()
            for line in getattr(self.doc, "attachment_warnings",
                                []) or []:
                if " \u2014 " in line:
                    warn_names.add(line.split(" \u2014 ")[0])
                if "'s datum" in line:
                    warn_names.add(line.split("'s datum")[0])
            rb = getattr(self.doc, "rollback_to", None)   # M88 rubber band
            # LAW-7/9: the marker rides a SLOT, drawn from arithmetic —
            # draggable truth, and it survives hidden chips. Vertical
            # line + triangular grab handle (LAW-9); blue is OURS.
            self._marker = None
            slot = self._slot() if rb is not None else None
            if rb is not None:
                mx = chip0 + slot * 34 - 2
                self._marker = QRectF(mx - 4, 5, 9, h + 4)
                p.setPen(QPen(QColor(D["accent"]), 2.2))
                p.drawLine(int(mx), 6, int(mx), 6 + int(h))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(D["accent"]))
                p.drawPolygon(QPolygonF([QPointF(mx - 5, 4),
                                         QPointF(mx + 5, 4),
                                         QPointF(mx, 12)]))
            for i, f in enumerate(self.doc.features):
                r = QRectF(x, 7, 30, h)
                sup = bool(getattr(f, "suppressed", False))
                rolled = rb is not None and i >= rb
                # LAW-3 gear menu: "hide all inactive" — the chip stops
                # painting but its SLOT stays (positions remain honest)
                hide = sup and self.hide_inactive
                if hide:
                    x += 34
                    continue
                # LAW-13 (M161 split): suppressed dims to the faint
                # gray with the ○ badge; a ROLLED-BACK chip dims WITH
                # ITS OWN COLOR at half ink — the two states never
                # wear the same face.
                dim = sup or rolled
                sel = i == self._sel
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(D["bg1"] if dim
                                 else (D["accent_deep"] if sel
                                       else D["bg2"])))
                p.drawRoundedRect(r, 4, 4)
                if sup:
                    pen = QPen(QColor(D["fg_faint"]))
                elif rolled:
                    pen = QPen(QColor(OP_COLOR[f.op]))
                    pen.setColor(QColor(pen.color().red(),
                                        pen.color().green(),
                                        pen.color().blue(), 110))
                else:
                    pen = QPen(QColor(D["accent"]) if i == last or sel
                               else QColor(OP_COLOR[f.op]))
                pen.setWidthF(1.6 if (sel or i == last) else 1.0)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r, 4, 4)
                p.setFont(self._glyph_font)
                if sup:
                    gcol = QColor(D["fg_faint"])
                elif rolled:
                    # LAW-13's face: the op's OWN hue dimmed, never the
                    # suppressed gray — first paint proved fg-at-alpha
                    # lands on the same gray, so the hue itself rides.
                    gcol = QColor(OP_COLOR[f.op])
                    gcol.setAlpha(150)
                else:
                    gcol = QColor(D["fg"])
                p.setPen(QPen(gcol))
                p.drawText(r, Qt.AlignCenter, self._glyph(f))
                if getattr(f, "error", None):        # M118: red badge —
                    p.setPen(Qt.PenStyle.NoPen)      # the feature that
                    p.setBrush(QColor(D["danger"]))  # broke the last
                    p.drawEllipse(r.topRight() - QPointF(7, 7), 3, 3)
                elif f.name in warn_names:           # M152 rung D: the
                    p.setPen(Qt.PenStyle.NoPen)      # amber sibling on
                    p.setBrush(QColor(D["warn"]))    # the SAME corner —
                    p.drawEllipse(r.topRight() - QPointF(7, 7), 3, 3)
                #                                      red outranks amber
                self._chips.append((x, 30, f))
                x += 34
            # LAW-4 (M161): the wheel can only scroll what the strip can
            # OUTGROW — the bar now sizes to its features (the scroll
            # area shows a real range; long timelines stopped clipping
            # silently at the viewport edge).
            self.setMinimumWidth(int(x) + 40)

    def _draw_gear(self, p, D):
        """LAW-3's Options button, drawn as ring + six teeth — vector,
        deterministic, no tofu."""
        import math
        cx, cy = self._gear.center().x(), self._gear.center().y()
        p.setPen(QPen(QColor(D["fg_dim"]), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 5.0, 5.0)
        for k in range(6):
            a = math.pi / 3 * k + math.pi / 6
            p.drawLine(QPointF(cx + 6.5 * math.cos(a),
                               cy + 6.5 * math.sin(a)),
                       QPointF(cx + 9.0 * math.cos(a),
                               cy + 9.0 * math.sin(a)))

    # ---- hit tests ---------------------------------------------------------
    def _feature_at(self, pos) -> object | None:
        for x, w, f in self._chips:
            if x <= pos.x() <= x + w and 4 <= pos.y() <= self.height() - 4:
                return f
        return None

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        if self._drag_marker:
            # LAW-7/8: dragging the marker between icons sets the slot
            # live — "the model rewinds in real time" (LAW-8), pure
            # evaluation cutoff, never a mutation of the stream.
            if (pos - self._drag_at).manhattanLength() > 3:
                self._dragged = True
            n = len(self.doc.features) if self.doc is not None else 0
            slot = max(0, min(n, round((pos.x() - self._chip0 + 2) / 34)))
            if slot != self._slot():
                self._emit_slot(slot)
            return
        f = self._feature_at(pos)
        if f is not None:
            QToolTip.showText(ev.globalPosition().toPoint(), f.name, self)
            return
        # LAW-14: the transport wears its name too
        for what, r in self._tb:
            if r.contains(pos):
                QToolTip.showText(ev.globalPosition().toPoint(),
                                  self.TRANSPORT_TIPS[what], self)
                return
        if self._gear is not None and self._gear.contains(pos):
            QToolTip.showText(ev.globalPosition().toPoint(), "Options",
                              self)
            return
        QToolTip.hideText()

    def mousePressEvent(self, ev):
        pos = ev.position()
        for what, r in self._tb:                 # LAW-2, exact order
            if r.contains(pos):
                if what == "play":
                    if self._playing:
                        self.stop_play()
                    else:
                        self.start_play()       # LAW-34: the only one
                else:
                    self.stop_play()            # any other press ends
                    self._tbutton(what)         #   the show
                return
        if (self._gear is not None
                and self._gear.contains(pos)):   # LAW-3: Options RIGHT
            self.gear_clicked.emit(ev.globalPosition().toPoint())
            return
        if (self._marker is not None
                and self._marker.contains(pos)):
            # M88 law stands: a CLICK (no drag) ends the rollback; a
            # DRAG rides the slots (mouseMoveEvent).
            self._drag_marker = True
            self._dragged = False
            self._drag_at = QPointF(pos)
            return
        if self._home.contains(pos):
            self.home_clicked.emit()
            return
        f = self._feature_at(pos)
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
        self.feature_clicked.emit(None)   # LAW-15: empty strip clears
        #   the model highlight the last click painted
        self.update()

    def mouseReleaseEvent(self, ev):
        if self._drag_marker:
            self._drag_marker = False
            if not self._dragged:
                self.rollback_changed.emit(None)   # M88 click-to-end
            self._dragged = False

    def mouseDoubleClickEvent(self, ev):
        f = self._feature_at(ev.position())
        if f is not None:
            self.feature_activated.emit(f)

    def _scroll_area(self) -> QScrollArea | None:
        """LAW-4 lives over THE STRIP: TimelineBar's Qt parent is the
        scroll area's VIEWPORT, not the QScrollArea — walk until one
        answers (the M20 wheel never scrolled because the direct
        parent check always failed)."""
        w = self.parent()
        while w is not None and not isinstance(w, QScrollArea):
            w = w.parent()
        return w

    def wheelEvent(self, ev):
        sa = self._scroll_area()
        if sa is not None:
            h = sa.horizontalScrollBar()
            h.setValue(h.value() - ev.angleDelta().y())


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
