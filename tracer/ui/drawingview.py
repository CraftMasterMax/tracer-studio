"""M93 — the drawing sheet canvas: white paper, live views, zoom & pan.

Views are never stored: every paint re-derives silhouettes from the
model in front of it, so the sheet can't rot while the solid changes —
the same honesty Fusion's views buy by rebuilding.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from PySide6.QtWidgets import QWidget

from ..core import drawing


class DrawingCanvas(QWidget):
    dim_added = Signal(str, tuple, tuple, dict)  # view, a, b, opts (M94/95)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.page = "A3"
        self._zoom = 1.6                       # screen px per sheet mm
        self._center = QPointF(0.0, 0.0)       # sheet mm coords at centre
        self._drag = None
        self._dim_mode = False                 # M94: bubble tool armed?
        self._dim_first = None                 # first endpoint (view, xy)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)

    def set_document(self, doc):
        self.doc = doc
        if doc is not None and doc.drawings:
            self.page = doc.drawings[-1].get("page", "A3")
        self._center = QPointF(*[v / 2 for v in drawing.PAGES.get(
            self.page, drawing.PAGES["A3"])])
        self._dim_first = None
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

    def placed(self) -> dict:
        """Per view: {sc, off, min, max, chains} — the shared M94
        placement (page = model * sc + off, y-up sheet mm)."""
        return drawing.place(self.views(), page=self.page)

    def layout(self) -> dict:
        """Page-coordinate chains (mm, y-up, origin lower-left)."""
        return {v: p["chains"] for v, p in self.placed().items()}

    def frames(self) -> dict:
        """view -> (scale, off): the page point of model (0, 0) is off,
        so page_to_model is the exact inverse (M94 dim tool)."""
        return {v: (p["sc"], p["off"]) for v, p in self.placed().items()}

    def page_to_model(self, view: str, page_pt) -> tuple:
        sc, off = self.frames()[view]
        return ((page_pt[0] - off[0]) / sc, (page_pt[1] - off[1]) / sc)

    def model_to_page(self, view: str, model_pt) -> tuple:
        sc, off = self.frames()[view]
        return (model_pt[0] * sc + off[0], model_pt[1] * sc + off[1])

    # ---- dimensions (M94) -------------------------------------------------
    def set_dim_mode(self, on: bool):
        self._dim_mode = bool(on)
        self._dim_first = None
        self.update()

    def _view_at(self, page_pt, placed, slack=3.0):
        """Which view's frame (with draughting slack) holds this click?"""
        best = None
        for name, p in placed.items():
            lo = np.asarray(p["min"]) - slack
            hi = np.asarray(p["max"]) + slack
            q = np.asarray(page_pt) - np.asarray(p["off"])
            if np.all(q >= lo) and np.all(q <= hi):
                # nearest frame centre wins if two overlap in the slack
                d = np.linalg.norm(q - 0.5 * (np.asarray(p["min"])
                                              + np.asarray(p["max"])))
                if best is None or d < best[1]:
                    best = (name, d)
        return best[0] if best else None

    def _snap(self, view, page_pt, placed, radius=3.0):
        """Grab the nearest projected chain endpoint (model space)."""
        p = placed[view]
        sc, off = p["sc"], np.asarray(p["off"])
        q = np.asarray(page_pt)
        best, bd = page_pt, radius
        for c in p["chains"]:
            for pt in c:
                d = float(np.linalg.norm(np.asarray(pt) - q))
                if d < bd:
                    best, bd = pt, d
        return self.page_to_model(view, best) if bd < radius \
            else self.page_to_model(view, page_pt)

    def rel_anchor(self, view: str, model_pt) -> list | None:
        """The endpoint as a fraction of the view's model-space extent
        (M94): (0, 0)..(1, 1) over the silhouette bbox. Fractions are
        what let a bubble FOLLOW a stretch — a raw (40, 0) can't know
        it was the RIGHT corner."""
        pv = self.placed().get(view)
        if pv is None:
            return None
        sc = pv["sc"]
        lo = (pv["min"][0] / sc, pv["min"][1] / sc)
        hi = (pv["max"][0] / sc, pv["max"][1] / sc)
        sx, sy = hi[0] - lo[0], hi[1] - lo[1]
        if sx < 1e-9 or sy < 1e-9:
            return None
        return [(model_pt[0] - lo[0]) / sx, (model_pt[1] - lo[1]) / sy]

    def resolve_dims(self, placed: dict | None = None):
        """The number can't lie and the arrow can't dangle: re-solve
        every bubble against the LIVE model (M94/M95). Linear bubbles
        re-derive endpoints from their view-fraction anchors; diameter
        bubbles re-FIND the projected circle nearest their centre and
        adopt its true radius (redrill 4->7 and the bubble reads
        Ø 14.00 by itself)."""
        if self.doc is None or not self.doc.drawings:
            return
        placed = placed if placed is not None else self.placed()
        views_cache: dict = {}
        for g in self.doc.drawings:
            for d in g.get("dims", []):
                pv = placed.get(d["view"])
                if pv is None:
                    continue
                if d.get("diameter"):
                    key = d["view"]
                    if key not in views_cache:
                        chains = self.views().get(key, [])
                        views_cache[key] = [
                            fit for fit in (drawing.fit_circle(L)
                                            for L in chains)
                            if fit is not None]
                    want = d.get("center", d.get("a"))
                    best = None
                    for (cx, cy), r in views_cache[key]:
                        dd = math.dist((cx, cy), want)
                        if dd <= max(4.0, 0.6 * r) and (
                                best is None or dd < best[2]):
                            best = ((cx, cy), r, dd)
                    if best is not None:
                        (cx, cy), r, _ = best
                        d["center"] = [cx, cy]
                        d["r"] = r
                        ux, uy = d.get("dir", (1.0, 0.0))
                        d["a"] = [cx, cy]
                        d["b"] = [cx + ux * r, cy + uy * r]
                    d["text"] = "\u00d8 %.2f" % float(d.get("r", 0.0) * 2)
                    continue
                sc = pv["sc"]
                lo = (pv["min"][0] / sc, pv["min"][1] / sc)
                hi = (pv["max"][0] / sc, pv["max"][1] / sc)
                for k in ("a", "b"):
                    r = d.get(k + "_rel")
                    if r is not None:
                        d[k] = [lo[0] + r[0] * (hi[0] - lo[0]),
                                lo[1] + r[1] * (hi[1] - lo[1])]
                d["text"] = f"{math.dist(d['a'], d['b']):.2f}"

    def _dim_click(self, ev):
        """Two endpoint clicks lay a linear bubble; ONE click on a
        projected circle lays a diameter (M95). Endpoints live in
        model space so the solid moving takes the dimension with it."""
        placed = self.placed()
        if not placed:
            return
        sheet = self.p2s(ev.position())
        view = self._view_at(sheet, placed)
        if view is None:
            self._dim_first = None
            self.update()
            return
        raw = self.page_to_model(view, sheet)
        for L in self.views().get(view, []):        # M95: a circle?
            fit = drawing.fit_circle(L)
            if fit is None:
                continue
            (cx, cy), r = fit
            if abs(math.dist(raw, (cx, cy)) - r) <= max(2.0, 0.35 * r):
                dx, dy = raw[0] - cx, raw[1] - cy
                dd = math.hypot(dx, dy) or 1.0
                self._dim_first = None
                self.dim_added.emit(
                    view, (cx, cy), (cx + dx / dd * r, cy + dy / dd * r),
                    {"diameter": True, "center": (cx, cy),
                     "dir": (dx / dd, dy / dd), "r": r})
                self.update()
                return
        pt = self._snap(view, sheet, placed)
        if self._dim_first is None or self._dim_first[0] != view:
            self._dim_first = (view, pt)
            self.update()
            return
        _v, a = self._dim_first
        self._dim_first = None
        if math.dist(a, pt) < 1e-9:
            self.update()
            return
        self.dim_added.emit(view, tuple(a), tuple(pt), {})
        self.update()

    # ---- paint ----------------------------------------------------------
    def s2p(self, x: float, y: float) -> QPointF:
        """Sheet mm -> widget px: centred, y flipped (sheet y is up)."""
        w, h = self.width(), self.height()
        return QPointF(w / 2 + (x - self._center.x()) * self._zoom,
                       h / 2 - (y - self._center.y()) * self._zoom)

    def p2s(self, pos) -> tuple:
        """Widget px -> sheet mm (the exact inverse of s2p)."""
        w, h = self.width(), self.height()
        return ((pos.x() - w / 2) / self._zoom + self._center.x(),
                (h / 2 - pos.y()) / self._zoom + self._center.y())

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
        # views + bubbles (one placement pass for both)
        placed = self.placed()
        p.setPen(QPen(QColor(28, 30, 34), max(1.0, 0.35 * self._zoom)))
        for view in placed.values():
            for c in view["chains"]:
                if len(c) < 2:
                    continue
                pts = [self.s2p(x, y) for x, y in c]
                for i in range(len(pts) - 1):
                    p.drawLine(pts[i], pts[i + 1])
        self._draw_dims(p, placed)

    def _draw_dims(self, p: QPainter, placed: dict):
        """Draughtsman bubbles: extension lines, arrowed dimension line
        offset away from the view, and the live millimetre text in a
        knocked-out gap.  Endpoints live in MODEL space, so the solid
        moving carries the dimension with it (M94)."""
        if self.doc is None or not self.doc.drawings:
            return
        g = self.doc.drawings[-1]
        dims = g.get("dims", [])
        self.resolve_dims(placed)
        ink = QPen(QColor(195, 60, 60), max(1.0, 0.5 * self._zoom))
        f = p.font()
        f.setPointSizeF(max(6.5, 9 * min(self._zoom, 2.0)))
        if self._dim_first is not None:                   # pending pick
            view = placed.get(self._dim_first[0])
            if view is not None:
                sc, off = view["sc"], view["off"]
                q = self.s2p(self._dim_first[1][0] * sc + off[0],
                             self._dim_first[1][1] * sc + off[1])
                p.setPen(QPen(QColor(78, 161, 255), 1.6))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(q, 5, 5)
        for d in dims:
            view = placed.get(d["view"])
            if view is None:
                continue
            sc, off = view["sc"], view["off"]
            if d.get("diameter"):                          # M95 Ø style
                self._draw_diameter(p, f, ink, d, sc, off)
                continue
            A = self.s2p(d["a"][0] * sc + off[0],
                         d["a"][1] * sc + off[1])
            B = self.s2p(d["b"][0] * sc + off[0],
                         d["b"][1] * sc + off[1])
            v = B - A
            L = math.hypot(v.x(), v.y())
            if L < 1e-6:
                continue
            u = QPointF(v.x() / L, v.y() / L)             # along the dim
            n = QPointF(-u.y(), u.x())                    # perpendicular
            # offset the dim line AWAY from the view's centre, draughting-
            # like, then lay extension lines and arrows along it
            ctr = self.s2p(off[0] + 0.5 * (view["min"][0] + view["max"][0]),
                           off[1] + 0.5 * (view["min"][1] + view["max"][1]))
            mid = QPointF(0.5 * (A.x() + B.x()), 0.5 * (A.y() + B.y()))
            if ((mid.x() - ctr.x()) * n.x()
                    + (mid.y() - ctr.y()) * n.y()) < 0:     # side test
                n = QPointF(-n.x(), -n.y())
            od = max(12.0, 4.0 * self._zoom)              # dim-line offset
            A2 = QPointF(A.x() + n.x() * od, A.y() + n.y() * od)
            B2 = QPointF(B.x() + n.x() * od, B.y() + n.y() * od)
            p.setPen(ink)
            p.drawLine(A, QPointF(A2.x() + n.x() * 3,
                                  A2.y() + n.y() * 3))    # ext lines
            p.drawLine(B, QPointF(B2.x() + n.x() * 3,
                                  B2.y() + n.y() * 3))
            p.drawLine(A2, B2)
            for tip, sgn in ((A2, 1.0), (B2, -1.0)):      # arrowheads
                base = QPointF(tip.x() + u.x() * 7 * sgn,
                               tip.y() + u.y() * 7 * sgn)
                w1 = QPointF(base.x() + n.x() * 1.8, base.y() + n.y() * 1.8)
                w2 = QPointF(base.x() - n.x() * 1.8, base.y() - n.y() * 1.8)
                path = QPainterPath()
                path.moveTo(tip)
                path.lineTo(w1)
                path.lineTo(w2)
                path.closeSubpath()
                p.setBrush(QColor(195, 60, 60))
                p.setPen(Qt.NoPen)
                p.drawPath(path)
                p.setPen(ink)
                p.setBrush(Qt.NoBrush)
            fm = p.fontMetrics()
            br = fm.boundingRect(d["text"])
            gap = QRectF(mid.x() + n.x() * od - br.width() / 2 - 3,
                         mid.y() + n.y() * od - br.height() / 2 - 2,
                         br.width() + 6, br.height() + 4)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#f5f5f2"))                 # knockout gap
            p.drawRect(gap)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(195, 60, 60)))
            p.setFont(f)
            p.drawText(gap, Qt.AlignCenter, d["text"])

    def _draw_diameter(self, p: QPainter, f, ink, d, sc, off):
        """A Ø bubble spans the whole circle: from the far rim through
        the centre to the near rim, arrowheads at both, text in the
        middle. Endpoints come from centre + dir*r, so the span follows
        the live circle resolve_dims just re-found."""
        cx, cy = d["a"]
        ux, uy = d.get("dir", (1.0, 0.0))
        r = float(d.get("r", math.dist(d["a"], d["b"])))
        if r < 1e-9:
            return
        far = self.s2p((cx - ux * r) * sc + off[0],
                       (cy - uy * r) * sc + off[1])
        near = self.s2p((cx + ux * r) * sc + off[0],
                        (cy + uy * r) * sc + off[1])
        p.setPen(ink)
        p.drawLine(far, near)
        v = near - far
        L = math.hypot(v.x(), v.y())
        if L < 1e-6:
            return
        u = QPointF(v.x() / L, v.y() / L)
        n = QPointF(-u.y(), u.x())
        for tip, sgn in ((far, 1.0), (near, -1.0)):
            base = QPointF(tip.x() + u.x() * 7 * sgn,
                           tip.y() + u.y() * 7 * sgn)
            path = QPainterPath()
            path.moveTo(tip)
            path.lineTo(QPointF(base.x() + n.x() * 1.8,
                                base.y() + n.y() * 1.8))
            path.lineTo(QPointF(base.x() - n.x() * 1.8,
                                base.y() - n.y() * 1.8))
            path.closeSubpath()
            p.setBrush(QColor(195, 60, 60))
            p.setPen(Qt.NoPen)
            p.drawPath(path)
            p.setPen(ink)
            p.setBrush(Qt.NoBrush)
        fm = p.fontMetrics()
        br = fm.boundingRect(d["text"])
        mid = QPointF(0.5 * (far.x() + near.x()),
                      0.5 * (far.y() + near.y()))
        gap = QRectF(mid.x() - br.width() / 2 - 3,
                     mid.y() - br.height() / 2 - 2,
                     br.width() + 6, br.height() + 4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f5f5f2"))
        p.drawRect(gap)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(195, 60, 60)))
        p.setFont(f)
        p.drawText(gap, Qt.AlignCenter, d["text"])

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
        if self._dim_mode and ev.button() == Qt.LeftButton:
            self._dim_click(ev)          # M94: bubbles, not panning
            return
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
