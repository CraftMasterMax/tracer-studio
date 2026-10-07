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
from .theme import DRAWING

# the sheet is paper: its inks never follow the UI theme (a drawing
# prints the same in dark or light chrome); tokens live in theme.DRAWING
_DESK = QColor(DRAWING["desk"])
_DESK_EDGE = QColor(DRAWING["desk_edge"])
_PAPER = QColor(DRAWING["paper"])
_VIEW_EDGE = QColor(DRAWING["view_edge"])
_SHEET = QColor(DRAWING["sheet"])
_BORDER = QColor(DRAWING["border"])
_DETAIL = QColor(DRAWING["detail"])
_HATCH = QColor(DRAWING["hatch"])
_FAINT = QColor(DRAWING["faint"])
_RED = QColor(DRAWING["red"])
_SELECT = QColor(DRAWING["select"])


def scale_label(factor: float) -> str:
    """The caption under a scaled view, drawn the way drawings say it:
    0.5 -> "1:2", 2 -> "2:1", 1 -> "1:1"."""
    if abs(factor - 1.0) < 1e-9:
        return "1:1"
    if factor < 1.0:
        return f"1:{1.0 / factor:.6g}"
    return f"{factor:.6g}:1"


class DrawingCanvas(QWidget):
    dim_added = Signal(str, tuple, tuple, dict)  # view, a, b, opts (M94/95)
    balloon_added = Signal(str, tuple, int)      # view, model xy, item (M110)
    view_drag_begin = Signal()                   # M96: undo capture hook
    view_scale_requested = Signal(str)           # M100: Scale dialog ask

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.page = "A3"
        self.sheet_idx = -1                      # M96: which sheet shows
        self._zoom = 1.6                       # screen px per sheet mm
        self._center = QPointF(0.0, 0.0)       # sheet mm coords at centre
        self._drag = None
        self._dim_mode = False                 # M94: bubble tool armed?
        self._dim_first = None                 # first endpoint (view, xy)
        self._balloon_mode = False             # M110: balloon tool armed?
        self._view_drag = None                 # M96: (view, start, base)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)

    def set_document(self, doc, idx: int | None = None):
        """Show a sheet (M96: idx picks it; default = newest)."""
        self.doc = doc
        if doc is not None and doc.drawings:
            self.sheet_idx = (idx if idx is not None
                              else len(doc.drawings) - 1)
            self.sheet_idx = max(0, min(self.sheet_idx,
                                        len(doc.drawings) - 1))
            self.page = self.sheet().get("page", "A3")
        else:
            self.sheet_idx = -1
        self._center = QPointF(*[v / 2 for v in drawing.PAGES.get(
            self.page, drawing.PAGES["A3"])])
        self._dim_first = None
        self._view_drag = None
        self.update()

    def sheet(self) -> dict:
        """The sheet on the table right now (empty dict if none)."""
        if self.doc is None or not self.doc.drawings:
            return {}
        return self.doc.drawings[max(
            0, min(self.sheet_idx, len(self.doc.drawings) - 1))]

    # ---- data -----------------------------------------------------------
    def sections(self) -> list:
        """M102: the stored cuts on this sheet ({name, axis, at})."""
        return list(self.sheet().get("sections") or [])

    def _sources(self) -> dict:
        """view name -> (solid to project, standard view key), live.
        The four standards project the full result; a section projects
        its half through the standard basis that reads the cut face."""
        if self.doc is None or self.doc.result is None:
            return {}
        out = {v: (self.doc.result, v) for v in drawing.STANDARD}
        for sec in self.sections():
            try:
                d = drawing.section(self.doc.result, sec["axis"],
                                    float(sec["at"]))
            except Exception:
                continue
            out[sec["name"]] = (d["half"], d["view"])
        return out

    def views(self) -> dict:
        """Live silhouette views of the current result (model space),
        sections included."""
        return {name: drawing.project_view(sol, view=v)
                for name, (sol, v) in self._sources().items()}

    def chains(self, view: str = "top") -> list:
        return self.views().get(view, [])

    def hidden_views(self) -> dict:
        """M97: dashed back creases per view (model space, live)."""
        return {name: drawing.project_hidden(sol, view=v)
                for name, (sol, v) in self._sources().items()}

    def hidden_page(self, view: str) -> list:
        """Hidden chains in sheet-mm page coords — moves included,
        since the frame they ride on already carries the view's move."""
        src = self._sources().get(view)
        if src is None:
            return []
        sol, vkey = src
        sc, off = self.frames()[view]
        return [[(float(p[0] * sc + off[0]), float(p[1] * sc + off[1]))
                 for p in c]
                for c in drawing.project_hidden(sol, view=vkey)]

    def cuts_page(self) -> dict:
        """M102: section name -> closed cut-face loops in sheet-mm page
        coords (moves and per-view scales ride the frame). M109: a view
        rotated for display carries its hatch around with it."""
        srcs = self._sources()
        out: dict = {}
        placed = self.placed()
        for sec in self.sections():
            name = sec["name"]
            if name not in srcs or name not in placed:
                continue
            d = drawing.section(self.doc.result, sec["axis"],
                                float(sec["at"]))
            out[name] = [[self._m2p(placed[name], p) for p in L]
                         for L in d["cut"]]
        return out

    def placed(self, views: dict | None = None) -> dict:
        """Per view: {sc, off, min, max, chains, rot, ctr} — the shared
        M94 placement (page = model * sc + off, y-up sheet mm). M96: the
        draughtsman's per-view moves ride on the assistant's slots. M109:
        a per-view display rotation (deg, about the view's own centre) is
        attached as `rot` (radians) + `ctr` (its page centre); it is a
        PRESENTATION transform only — the model-space chains/dims the
        numbers are measured from are never touched, and rot = 0 makes
        every map below the exact identity it always was. Pass `views` to
        reuse a fresh projection instead of redoing it."""
        views = self.views() if views is None else views
        placed = drawing.place(views, page=self.page,
                               moves=self.sheet().get("move"),
                               scales=self.sheet().get("vscale"))
        rots = self.sheet().get("rot") or {}
        for name, p in placed.items():
            try:
                deg = float(rots.get(name, 0.0))
            except (TypeError, ValueError):
                deg = 0.0
            p["rot"] = math.radians(deg)
            p["ctr"] = (p["off"][0] + 0.5 * (p["min"][0] + p["max"][0]),
                        p["off"][1] + 0.5 * (p["min"][1] + p["max"][1]))
        return placed

    # ---- M109: per-view rotation (a page-space spin about the view ctr) --
    @staticmethod
    def _spin(fr: dict, pt, neg: bool = False):
        """Rotate a page point about the view's centre by +/- its rot.
        A no-op (identity) when the view is unrotated."""
        a = fr.get("rot", 0.0)
        if not a:
            return (float(pt[0]), float(pt[1]))
        if neg:
            a = -a
        cx, cy = fr["ctr"]
        ca, sa = math.cos(a), math.sin(a)
        dx, dy = pt[0] - cx, pt[1] - cy
        return (cx + dx * ca - dy * sa, cy + dx * sa + dy * ca)

    def model_to_page(self, view: str, model_pt) -> tuple:
        """model (view 2D mm) -> DISPLAYED page mm, rotation applied last."""
        p = self.placed().get(view)
        if p is None:
            return (float(model_pt[0]), float(model_pt[1]))
        return self._m2p(p, model_pt)

    def page_to_model(self, view: str, page_pt) -> tuple:
        """DISPLAYED page mm -> model, de-rotating the click first so the
        dim tool sees true model coordinates whatever the view's angle."""
        p = self.placed().get(view)
        if p is None:
            return (float(page_pt[0]), float(page_pt[1]))
        return self._p2m(p, page_pt)

    @classmethod
    def _m2p(cls, fr: dict, model_pt) -> tuple:
        """model -> displayed page, straight from a placed frame (the hot
        paint path holds frames already, so skip the name lookup)."""
        sc, off = fr["sc"], fr["off"]
        return cls._spin(fr, (model_pt[0] * sc + off[0],
                              model_pt[1] * sc + off[1]))

    @classmethod
    def _p2m(cls, fr: dict, page_pt) -> tuple:
        """displayed page -> model: un-rotate about ctr, then the plain
        inverse of page = model * sc + off."""
        sc, off = fr["sc"], fr["off"]
        cx, cy = cls._spin(fr, page_pt, neg=True)
        return ((cx - off[0]) / sc, (cy - off[1]) / sc)

    def _cm(self, fr: dict, canon_page) -> tuple:
        """CANONICAL page (place()'s own space, pre-rotation) -> model."""
        sc, off = fr["sc"], fr["off"]
        return ((canon_page[0] - off[0]) / sc, (canon_page[1] - off[1]) / sc)

    def layout(self) -> dict:
        """Page-coordinate chains (mm, y-up, origin lower-left)."""
        return {v: p["chains"] for v, p in self.placed().items()}

    def frames(self) -> dict:
        """view -> (scale, off): the page point of model (0, 0) is off,
        so the CANONICAL map is page_to_model's inverse before rotation."""
        return {v: (p["sc"], p["off"]) for v, p in self.placed().items()}

    # ---- dimensions (M94) -------------------------------------------------
    def set_dim_mode(self, on: bool):
        self._dim_mode = bool(on)
        self._dim_first = None
        if on:
            self._balloon_mode = False        # M110: one tool at a time
        self.update()

    def set_balloon_mode(self, on: bool):
        """M110: arm the balloon click — one click on a view pins the
        next item number there, in MODEL millimetres (the bubble
        travels with the body and survives a view spin, like a dim)."""
        self._balloon_mode = bool(on)
        if on:
            self._dim_mode = False
            self._dim_first = None
        self.update()

    def _view_at(self, page_pt, placed, slack=3.0):
        """Which view's frame (with draughting slack) holds this click?
        The click is in DISPLAYED sheet mm; un-rotate it into each view's
        canonical page space first (identity when that view is upright)."""
        best = None
        for name, p in placed.items():
            lo = np.asarray(p["min"]) - slack
            hi = np.asarray(p["max"]) + slack
            click = self._spin(p, page_pt, neg=True)
            q = np.asarray(click) - np.asarray(p["off"])
            if np.all(q >= lo) and np.all(q <= hi):
                # nearest frame centre wins if two overlap in the slack
                d = np.linalg.norm(q - 0.5 * (np.asarray(p["min"])
                                              + np.asarray(p["max"])))
                if best is None or d < best[1]:
                    best = (name, d)
        return best[0] if best else None

    def _snap(self, view, page_pt, placed, radius=3.0):
        """Grab the nearest projected chain endpoint (model space). Chains
        live in canonical page space, so the displayed click is un-rotated
        in and the answer mapped canonical -> model."""
        p = placed[view]
        q = np.asarray(self._spin(p, page_pt, neg=True))
        best, bd = q, radius
        for c in p["chains"]:
            for pt in c:
                d = float(np.linalg.norm(np.asarray(pt) - q))
                if d < bd:
                    best, bd = pt, d
        return self._cm(p, best) if bd < radius else self._cm(p, q)

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
        arcs_cache: dict = {}
        srcs = self._sources()
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
                if d.get("radius"):
                    key = d["view"]
                    if key not in arcs_cache:
                        src = srcs.get(key)
                        arcs_cache[key] = (
                            drawing.find_arcs(self.views().get(key, []))
                            if src is not None
                            and src[1] in ("top", "front", "right")
                            else [])
                    want = d.get("center", d.get("a"))
                    best = None
                    for (cx, cy), r in arcs_cache[key]:
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
                    d["text"] = "R %.2f" % float(d.get("r", 0.0))
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
        src = self._sources().get(view)             # M103: an arc?
        if src is not None and src[1] in ("top", "front", "right"):
            for (cx, cy), r in drawing.find_arcs(
                    self.views().get(view, [])):
                if abs(math.dist(raw, (cx, cy)) - r) <= max(2.0, 0.35 * r):
                    dx, dy = raw[0] - cx, raw[1] - cy
                    dd = math.hypot(dx, dy) or 1.0
                    self._dim_first = None
                    self.dim_added.emit(
                        view, (cx, cy),
                        (cx + dx / dd * r, cy + dy / dd * r),
                        {"radius": True, "center": (cx, cy),
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
        p.fillRect(self.rect(), _DESK)          # desk grey
        W, H = drawing.PAGES.get(self.page, drawing.PAGES["A3"])
        a = self.s2p(0, 0)
        b = self.s2p(W, H)
        sheet = QRectF(min(a.x(), b.x()), min(a.y(), b.y()),
                       abs(b.x() - a.x()), abs(b.y() - a.y()))
        p.setPen(QPen(_DESK_EDGE, 1))
        p.setBrush(_PAPER)                        # the paper
        p.drawRect(sheet)
        p.setBrush(Qt.NoBrush)
        self._paint_block(p)                                 # M108 title block
        self._paint_bom(p)                                   # M110 parts list
        # views + section hatch + hidden ink + bubbles (one pass)
        views = self.views()
        placed = self.placed(views)
        p.setPen(QPen(_VIEW_EDGE, max(1.0, 0.35 * self._zoom)))
        for view in placed.values():
            for c in view["chains"]:
                if len(c) < 2:
                    continue
                pts = [self.s2p(*self._spin(view, (x, y))) for x, y in c]
                for i in range(len(pts) - 1):
                    p.drawLine(pts[i], pts[i + 1])
        cuts = self.cuts_page()
        if cuts:                        # M102: 45° hatch fills the wound
            p.setPen(QPen(_DETAIL,
                          max(0.6, 0.22 * self._zoom)))
            for loops in cuts.values():
                for ha, hb in drawing.hatch_region(loops):
                    p.drawLine(self.s2p(*ha), self.s2p(*hb))
        if self.doc is not None and self.doc.result is not None:
            hp = QPen(_HATCH, max(0.8, 0.28 * self._zoom))
            hp.setStyle(Qt.DashLine)
            p.setPen(hp)                        # M101: depth-hidden ink
            srcs = self._sources()
            for name in placed:
                src = srcs.get(name)
                if src is None:
                    continue
                for c in drawing.project_hidden(src[0], view=src[1]):
                    pts = [self.s2p(*self._m2p(placed[name], p2))
                           for p2 in c]
                    for i in range(len(pts) - 1):
                        p.drawLine(pts[i], pts[i + 1])
        # M100: a view on an explicit scale wears its ratio as a caption;
        # M102: a section wears its letter (A-A · 1:2 when both)
        vs = self.sheet().get("vscale") or {}
        sec_names = {s["name"] for s in self.sections()}
        if vs or sec_names:
            f2 = p.font()
            f2.setPointSizeF(max(5.5, 7 * min(self._zoom, 2.0)))
            p.setFont(f2)
            for name, fr in placed.items():
                fac = vs.get(name)
                bits = []
                if name in sec_names:
                    bits.append(name)
                if fac:
                    bits.append(scale_label(float(fac)))
                if not bits:
                    continue
                # caption sits below the view centre; M109 rotates that
                # anchor with the view (its own spin, text stays upright)
                c0 = self.s2p(*self._spin(
                    fr, (fr["ctr"][0], fr["off"][1] + fr["min"][1] - 3.0)))
                p.setPen(QPen(_FAINT))
                p.drawText(QRectF(c0.x() - 40, c0.y(), 80,
                                  14 * self._zoom),
                           Qt.AlignHCenter | Qt.AlignTop,
                           " \u00b7 ".join(bits))
        self._draw_dims(p, placed)
        self._draw_balloons(p, placed)               # M110 item bubbles


    def _block_meta(self) -> dict:
        """Derived title-block strings the canvas (not the sheet) knows:
        fitted print scale and sheet position within the drawing set."""
        n = max(1, len(self.doc.drawings)) if self.doc else 1
        sc = max(1, round(1 / self.page_scale())) if self.views() else 1
        return {"scale": f"1:{sc}", "sheet": f"{self.sheet_idx + 1} / {n}"}

    def _paint_block(self, p: QPainter):
        """Draw the ISO title block bottom-right from the pure resolver.
        It's sheet furniture, not view geometry: it paints here (and thus
        into the PNG) but never enters the DXF line stream — and it saves /
        restores the painter so its pen + font can't leak into the views,
        bubbles and section hatch painted after it."""
        p.save()
        tb = drawing.title_block(self.sheet(), meta=self._block_meta(),
                                 page=self.page)
        p.setPen(QPen(_BORDER, 1))
        for (ax, ay), (bx, by) in tb["lines"]:
            p.drawLine(self.s2p(ax, ay), self.s2p(bx, by))
        p.setPen(QPen(_SHEET))
        self._paint_cells(p, tb["cells"])
        p.restore()

    def _paint_cells(self, p: QPainter, cells):
        """Paint resolver cells inside their column boxes (shared by the
        title block, M108, and the parts list, M110): text is clipped to
        its own box so a long description can never bleed across a
        divider, and the bold flag marks a heading row."""
        for c in cells:
            if not c["text"]:
                continue
            top = self.s2p(c["xa"], c["y"] + c["size"])
            bot = self.s2p(c["xb"], c["y"] - c["size"])
            box = QRectF(min(top.x(), bot.x()), min(top.y(), bot.y()),
                         abs(bot.x() - top.x()), abs(bot.y() - top.y()))
            f = p.font()
            f.setPixelSize(max(5, int(c["size"] * self._zoom)))
            f.setBold(bool(c.get("bold")))
            p.setFont(f)
            al = {"l": Qt.AlignLeft, "c": Qt.AlignHCenter,
                  "r": Qt.AlignRight}[c["align"]]
            p.drawText(box.adjusted(2, 0, -2, 0), al | Qt.AlignVCenter,
                       c["text"])

    def _paint_bom(self, p: QPainter):
        """The parts list (M110, ISO 7573): rows are DERIVED from the
        document at paint time — bodies, volumes, materials — so the
        list can no more go stale than the title block's scale. Docks
        on the block's top edge; paper-only, like the block: the DXF
        line stream never sees it."""
        if self.doc is None or not self.doc.drawings:
            return
        if not self.sheet().get("bom"):
            return
        p.save()
        rows = drawing.parts_list(self.doc.body_list(),
                                  self.doc.body_solids())
        tb = drawing.title_block(self.sheet(), meta=self._block_meta(),
                                 page=self.page)
        t = drawing.parts_list_table(rows, tb["rect"], page=self.page)
        p.setPen(QPen(_BORDER, 1))
        for (ax, ay), (bx, by) in t["lines"]:
            p.drawLine(self.s2p(ax, ay), self.s2p(bx, by))
        if t["overflow"]:
            x0, y0, w, h = t["rect"]
            t["cells"].append({"text": f"… {t['overflow']} more",
                               "xa": x0, "xb": x0 + w,
                               "y": y0 + h + 2.5, "size": 1.6,
                               "align": "l"})
        p.setPen(QPen(_SHEET))
        self._paint_cells(p, t["cells"])
        p.restore()

    def _draw_balloons(self, p: QPainter, placed: dict):
        """ISO 6433 item references (M110): a leader dot on the part,
        a circle, the item number — anchored in MODEL millimetres, so
        a spun or dragged view carries its balloons like dimensions
        do. Numbers speak in sheet px, staying upright and legible."""
        g = self.sheet()
        groups = g.get("balloons") or {}
        if not groups:
            return
        f = p.font()
        f.setPixelSize(max(8, int(5.0 * self._zoom)))
        p.setFont(f)
        r = max(6.0, 3.4 * self._zoom)
        for view, items in groups.items():
            fr = placed.get(view)
            if fr is None:
                continue
            for b in items:
                ax, ay = self._m2p(fr, (b["x"], b["y"]))
                a = self.s2p(ax, ay)
                cx, cy = a.x() + 2 * r, a.y() - 2 * r
                c = QPointF(cx, cy)
                p.setPen(QPen(_SHEET,
                              max(1.0, 0.35 * self._zoom)))
                p.drawLine(a, QPointF(cx - r * 0.8, cy + r * 0.8))
                p.setBrush(_PAPER)
                p.drawEllipse(c, r, r)
                p.setBrush(Qt.NoBrush)
                p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r),
                           Qt.AlignCenter, str(b.get("item", "")))

    def _draw_dims(self, p: QPainter, placed: dict):
        """Draughtsman bubbles: extension lines, arrowed dimension line
        offset away from the view, and the live millimetre text in a
        knocked-out gap.  Endpoints live in MODEL space, so the solid
        moving carries the dimension with it (M94)."""
        if self.doc is None or not self.doc.drawings:
            return
        g = self.sheet()                           # M96: this sheet only
        dims = g.get("dims", [])
        self.resolve_dims(placed)
        ink = QPen(_RED, max(1.0, 0.5 * self._zoom))
        f = p.font()
        f.setPointSizeF(max(6.5, 9 * min(self._zoom, 2.0)))
        if self._dim_first is not None:                   # pending pick
            view = placed.get(self._dim_first[0])
            if view is not None:
                q = self.s2p(*self._m2p(view, self._dim_first[1]))
                p.setPen(QPen(_SELECT, 1.6))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(q, 5, 5)
        for d in dims:
            view = placed.get(d["view"])
            if view is None:
                continue
            if d.get("diameter"):                          # M95 Ø style
                self._draw_diameter(p, f, ink, d, view)
                continue
            if d.get("radius"):            # M103: R, centre to rim
                self._draw_radius(p, f, ink, d, view)
                continue
            A = self.s2p(*self._m2p(view, d["a"]))
            B = self.s2p(*self._m2p(view, d["b"]))
            v = B - A
            L = math.hypot(v.x(), v.y())
            if L < 1e-6:
                continue
            u = QPointF(v.x() / L, v.y() / L)             # along the dim
            n = QPointF(-u.y(), u.x())                    # perpendicular
            # offset the dim line AWAY from the view's centre, draughting-
            # like, then lay extension lines and arrows along it.  ctr is
            # the view centre; a spin (M109) leaves it fixed, so a plain
            # s2p of it is correct at any angle.
            ctr = self.s2p(*view["ctr"])
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
                p.setBrush(_RED)
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
            p.setBrush(_PAPER)                 # knockout gap
            p.drawRect(gap)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(_RED))
            p.setFont(f)
            p.drawText(gap, Qt.AlignCenter, d["text"])

    def _draw_diameter(self, p: QPainter, f, ink, d, fr):
        """A Ø bubble spans the whole circle: from the far rim through
        the centre to the near rim, arrowheads at both, text in the
        middle. Endpoints come from centre + dir*r, so the span follows
        the live circle resolve_dims just re-found (M109: the whole span
        is mapped through _m2p so a spun view carries its bubble with
        it, while the text stays upright)."""
        cx, cy = d["a"]
        ux, uy = d.get("dir", (1.0, 0.0))
        r = float(d.get("r", math.dist(d["a"], d["b"])))
        if r < 1e-9:
            return
        far = self.s2p(*self._m2p(fr, (cx - ux * r, cy - uy * r)))
        near = self.s2p(*self._m2p(fr, (cx + ux * r, cy + uy * r)))
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
            p.setBrush(_RED)
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
        p.setBrush(_PAPER)
        p.drawRect(gap)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_RED))
        p.setFont(f)
        p.drawText(gap, Qt.AlignCenter, d["text"])

    def _draw_radius(self, p: QPainter, f, ink, d, fr):
        """M103: an R leader runs from the arc's centre out to the rim,
        one arrowhead on the rim, text on the paper just past the tip.
        Endpoints ride centre + dir*r so the leader follows the live
        arc resolve_dims re-found (a redrilled scallop moves alone).
        M109 maps both through _m2p so a spun view carries its leader."""
        cx, cy = d["a"]
        ux, uy = d.get("dir", (1.0, 0.0))
        r = float(d.get("r", math.dist(d["a"], d["b"])))
        if r < 1e-9:
            return
        centre = self.s2p(*self._m2p(fr, (cx, cy)))
        rim = self.s2p(*self._m2p(fr, (cx + ux * r, cy + uy * r)))
        p.setPen(ink)
        p.drawLine(centre, rim)
        v = rim - centre
        L = math.hypot(v.x(), v.y())
        if L < 1e-6:
            return
        u = QPointF(v.x() / L, v.y() / L)
        n = QPointF(-u.y(), u.x())
        base = QPointF(rim.x() - u.x() * 7, rim.y() - u.y() * 7)
        path = QPainterPath()
        path.moveTo(rim)
        path.lineTo(QPointF(base.x() + n.x() * 1.8, base.y() + n.y() * 1.8))
        path.lineTo(QPointF(base.x() - n.x() * 1.8, base.y() - n.y() * 1.8))
        path.closeSubpath()
        p.setBrush(_RED)
        p.setPen(Qt.NoPen)
        p.drawPath(path)
        p.setBrush(Qt.NoBrush)
        fm = p.fontMetrics()
        br = fm.boundingRect(d["text"])
        mid = QPointF(0.5 * (centre.x() + rim.x()) + n.x() * 9,
                      0.5 * (centre.y() + rim.y()) + n.y() * 9)
        gap = QRectF(mid.x() - br.width() / 2 - 3,
                     mid.y() - br.height() / 2 - 2,
                     br.width() + 6, br.height() + 4)
        p.setPen(Qt.NoPen)
        p.setBrush(_PAPER)
        p.drawRect(gap)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_RED))
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
        if self._balloon_mode and ev.button() == Qt.LeftButton:
            self._balloon_click(ev)          # M110: pin, don't pan
            return
        if self._dim_mode and ev.button() == Qt.LeftButton:
            self._dim_click(ev)          # M94: bubbles, not panning
            return
        if ev.button() == Qt.LeftButton:
            # M96: a press ON a view grabs the view; the desk still pans
            placed = self.placed()
            view = self._view_at(self.p2s(ev.position()), placed,
                                 slack=0.0) if placed else None
            if view is not None:
                base = self.sheet().get("move", {}).get(view, (0.0, 0.0))
                self._view_drag = [view, self.p2s(ev.position()),
                                   (float(base[0]), float(base[1])),
                                   False]
                return
        if ev.button() in (Qt.MiddleButton, Qt.LeftButton):
            self._drag = ev.position()

    def mouseMoveEvent(self, ev):
        if self._view_drag is not None:                  # M96: move a view
            view, start, base, moved = self._view_drag
            sp = self.s2p(start[0], start[1])
            pdx = (ev.position().x() - sp.x()) / self._zoom
            pdy = -(ev.position().y() - sp.y()) / self._zoom
            if not moved and abs(ev.position().x() - sp.x()) + \
                    abs(ev.position().y() - sp.y()) <= 2.0:
                return
            if not moved:
                self._view_drag[3] = moved = True
                self.view_drag_begin.emit()              # undo capture
            g = self.sheet()
            g.setdefault("move", {})[view] = [base[0] + pdx,
                                              base[1] + pdy]
            if self.doc is not None:
                self.doc.dirty = True
            self.update()
            return
        if self._drag is not None:
            d = ev.position() - self._drag
            self._center += QPointF(-d.x() / self._zoom, d.y() / self._zoom)
            self._drag = ev.position()
            self.update()

    def mouseReleaseEvent(self, ev):
        self._drag = None
        self._view_drag = None

    def mouseDoubleClickEvent(self, ev):
        # M100: double-click a view -> its Scale dialog
        if self._dim_mode or ev.button() != Qt.LeftButton:
            return
        placed = self.placed()
        if not placed:
            return
        view = self._view_at(self.p2s(ev.position()), placed, slack=0.0)
        if view is not None:
            self.view_scale_requested.emit(view)

    def _balloon_click(self, ev):
        """One click, one balloon (M110): the anchor is stored in MODEL
        millimetres like a dimension, so spins and drags carry it; the
        item number is the next unused one across the sheet — balloons
        count parts, and the parts list already ordered them."""
        placed = self.placed()
        if not placed:
            return
        sheet = self.p2s(ev.position())
        view = self._view_at(sheet, placed)
        if view is None:
            return
        raw = self.page_to_model(view, sheet)
        self.balloon_added.emit(view, (float(raw[0]), float(raw[1])),
                                self._next_balloon_item())
        self.update()

    def _next_balloon_item(self) -> int:
        items = [b.get("item", 0)
                 for group in (self.sheet().get("balloons") or {}).values()
                 for b in group]
        return max(items, default=0) + 1

    def _scale_dialog(self, cur):
        """Fusion's scale picker: Fit plus the standard ratios. Returns
        the chosen wording (None = cancelled)."""
        from . import cmddialog
        v = cmddialog.ask(self, "View scale", [
            dict(key="scale", kind="combo", label="Scale",
                 choices=["Fit (auto)", "1:1", "1:2", "1:5", "1:10",
                          "2:1", "5:1"])])
        return None if v is None else str(v["scale"])
