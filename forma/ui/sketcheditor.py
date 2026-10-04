"""2D sketch canvas (QPainter — crisp text/glyphs, no GL needed in 2D).

Tools: S select · L line chain · R rectangle · C circle.
Constraint keys act on selection: H/V (line), F (point), D (distance on
line), plus Del. X finishes into profile(s). Solver runs live on every
drag with the grabbed point pinned — like it should.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QKeyEvent, QMouseEvent, QPainter,
                           QPen, QWheelEvent)
from PySide6.QtWidgets import QInputDialog, QWidget

from ..core.sketch.constraints import (Distance, Fixed, Horizontal, Radius,
                                       Vertical)
from ..core.sketch.entities import Circle, Line, Point
from ..core.sketch.model import SketchModel, math_dist
from ..core.sketch.profile import regions

ACCENT = QColor("#4ea1ff")
FG = QColor("#e8eaed")
DIM = QColor("#9aa1ac")
FAINT = QColor("#454b55")
BG = QColor("#1b1d22")
GRID = QColor(255, 255, 255, 14)
GRID_MAJOR = QColor(255, 255, 255, 28)
AXIS_X = QColor(200, 100, 105)
AXIS_Y = QColor(120, 185, 110)
OK = QColor("#7ec97e")
WARN = QColor("#e5b567")

_HIT_PX = 9


class SketchCanvas(QWidget):
    profiles_ready = Signal(list, str)      # [(outer Nx2, [holes Nx2...])], name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)      # live coordinate readout, like Fusion
        self._cursor: tuple | None = None
        self.model: SketchModel | None = None
        self._scale = 4.0                   # px per mm
        self._center = np.array([0.0, 0.0])  # world point at widget center
        self._tool = "select"
        self._sel: list = []
        self._drag_pt: Point | None = None
        self._pan_from: QPointF | None = None
        self._line_start: Point | None = None
        self._preview: tuple | None = None  # tool drag preview
        self._snap_hint: Point | None = None
        self._last_result = None
        self._dim_hits: list = []
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        f = QFont()
        f.setPointSize(9)
        self._font = f

    # ---- model attach ---------------------------------------------------
    def set_model(self, model: SketchModel):
        self.model = model
        self._sel = []
        self._line_start = None
        self._preview = None
        self._last_result = None
        self.set_tool("select")
        self.fit_view()
        self.update()

    def set_tool(self, tool: str):
        self._tool = tool
        if tool != "line":
            self._line_start = None
        self._preview = None
        self.update()

    # ---- view transform -------------------------------------------------
    def w2s(self, x, y) -> QPointF:
        cx, cy = self.width() / 2.0, self.height() / 2.0
        return QPointF(cx + (x - self._center[0]) * self._scale,
                       cy - (y - self._center[1]) * self._scale)

    def fit_view(self):
        pts = []
        if self.model:
            for l in self.model.sketch.lines:
                pts += [(l.a.x, l.a.y), (l.b.x, l.b.y)]
            for c in self.model.sketch.circles:
                pts += [(c.c.x - c.r, c.c.y - c.r), (c.c.x + c.r, c.c.y + c.r)]
        if not pts:
            self._scale, self._center = 4.0, np.array([0.0, 0.0])
            return
        p = np.array(pts, float)
        lo, hi = p.min(0), p.max(0)
        span = np.maximum(hi - lo, 1.0) * 1.5
        self._scale = min(self.width() / span[0], self.height() / span[1])
        self._center = (lo + hi) / 2

    # ---- hit testing ------------------------------------------------------
    def _snap_point(self, q: QPointF) -> Point | None:
        best, bd = None, _HIT_PX
        for p, _ in self._all_points():
            s = self.w2s(p.x, p.y)
            d = math.hypot(s.x() - q.x(), s.y() - q.y())
            if d <= bd:
                best, bd = p, d
        return best

    def _all_points(self):
        sk = self.model.sketch
        seen = {}
        for l in sk.lines:
            for p in (l.a, l.b):
                seen[p.id] = p
        for c in sk.circles:
            seen[c.c.id] = c.c
        for p in sk.points:
            seen[p.id] = p
        return [(p, None) for p in seen.values()]

    def _hit(self, q: QPointF):
        sk = self.model.sketch
        p = self._snap_point(q)
        if p is not None:
            return ("point", p)
        for c in sk.circles:
            d = math.hypot(q.x() - self.w2s(c.c.x, c.c.y).x(),
                           q.y() - self.w2s(c.c.x, c.c.y).y())
            if abs(d - c.r * self._scale) <= _HIT_PX:
                return ("circle", c)
        for l in sk.lines:
            if self._pt_seg_px(q, l.a, l.b) <= _HIT_PX:
                return ("line", l)
        return None

    def _pt_seg_px(self, q, a, b) -> float:
        ax, ay = self.w2s(a.x, a.y).x(), self.w2s(a.x, a.y).y()
        bx, by = self.w2s(b.x, b.y).x(), self.w2s(b.x, b.y).y()
        ab = np.array([bx - ax, by - ay])
        L2 = float(ab @ ab)
        if L2 < 1e-9:
            return math.hypot(q.x() - ax, q.y() - ay)
        t = max(0.0, min(1.0, ((q.x() - ax) * ab[0] + (q.y() - ay) * ab[1]) / L2))
        proj = np.array([ax, ay]) + t * ab
        return math.hypot(q.x() - proj[0], q.y() - proj[1])

    # ---- mouse -----------------------------------------------------------
    def mousePressEvent(self, ev: QMouseEvent):
        if self.model is None:
            return
        q = ev.position()
        if ev.button() in (Qt.MiddleButton, Qt.RightButton):
            if ev.button() == Qt.RightButton and self._tool == "select":
                self._context_menu(ev)
                return
            self._pan_from = q
            return
        if ev.button() != Qt.LeftButton:
            return
        if self._tool == "select":
            hit = self._hit(q)
            if hit is None:
                self._sel = []
            elif ev.modifiers() & Qt.ControlModifier:
                if hit[1] in self._sel:
                    self._sel.remove(hit[1])
                else:
                    self._sel.append(hit[1])
            else:
                self._sel = [hit[1]]
                if hit[0] == "point":
                    self._drag_pt = hit[1]
            self.update()
            return
        wp = self._world(q)
        if self._tool == "line":
            snap = self._snap_point(q)
            p = snap if snap is not None else self.model.point(*wp)
            if self._line_start is None:
                self._line_start = p
            else:
                if p is self._line_start:
                    self._line_start = None          # close chain
                else:
                    ln = self.model.add_line(self._line_start, p)
                    self._auto_constraints(ln, q)
                    self._solve()
                    self._line_start = p
            self.update()
        elif self._tool == "rect":
            self._preview = ("rect", wp, wp)
        elif self._tool == "circle":
            self._preview = ("circle", wp, wp)

    def _auto_constraints(self, ln: Line, end_q: QPointF):
        """Fusion's drawing feel: release near-horizontal -> it IS
        horizontal (snapped), and the constraint is recorded."""
        a, b = self.w2s(ln.a.x, ln.a.y), self.w2s(ln.b.x, ln.b.y)
        dx, dy = abs(b.x() - a.x()), abs(b.y() - a.y())
        if max(dx, dy) < 4:
            return
        if dy <= 3 and dx > 6:                      # near horizontal
            ln.b.y = ln.a.y
            self.model.constrain(Horizontal(ln))
        elif dx <= 3 and dy > 6:                    # near vertical
            ln.b.x = ln.a.x
            self.model.constrain(Vertical(ln))

    def mouseMoveEvent(self, ev: QMouseEvent):
        q = ev.position()
        self._cursor = self._world(q)
        self.update()                    # keep the readout live
        if self._pan_from is not None:
            d = (q - self._pan_from)
            self._center -= np.array([d.x() / self._scale, -d.y() / self._scale])
            self._pan_from = q
            self.update()
            return
        if self._tool == "select":
            if self._drag_pt is not None:
                wp = self._world(q)
                self._drag_pt.x, self._drag_pt.y = float(wp[0]), float(wp[1])
                self._solve(pins=[self._drag_pt])
                self.update()
            return
        if self._preview:
            wp = self._world(q)
            kind, start = self._preview[0], self._preview[1]
            self._preview = (kind, start, wp)
            if self._tool == "line":
                self._snap_hint = self._snap_point(q)
            self.update()

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if ev.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_from = None
            return
        if self._tool == "select":
            self._drag_pt = None
            return
        if not self._preview:
            return
        kind, a, b = self._preview
        self._preview = None
        if kind == "rect" and np.linalg.norm(b - a) * self._scale > 6:
            p0 = self.model.point(*a)
            p1 = self.model.point(*b)
            self.model.add_rect(p0, p1)
            self._solve()
        elif kind == "circle":
            r = float(np.linalg.norm(b - a))
            if r * self._scale > 4:
                c = self.model.add_circle(self.model.point(*a), r)
                self._solve()
        self.update()

    def wheelEvent(self, ev: QWheelEvent):
        before = self._world(ev.position())
        self._scale *= pow(1.0015, ev.angleDelta().y())
        self._scale = min(max(self._scale, 0.01), 1e4)
        after = self._world(ev.position())
        self._center += before - after       # zoom toward cursor
        self.update()

    def _world(self, q: QPointF) -> np.ndarray:
        cx, cy = self.width() / 2.0, self.height() / 2.0
        return np.array([(q.x() - cx) / self._scale + self._center[0],
                         (cy - q.y()) / self._scale + self._center[1]])

    # ---- keyboard ----------------------------------------------------------
    # ---- constraint actions (keys + context menu share these) --------------
    def act_H(self):
        if len(self._sel) == 1 and isinstance(self._sel[0], Line):
            self.model.toggle(Horizontal, (self._sel[0],))
            self._solve(); self.update()

    def act_V(self):
        if len(self._sel) == 1 and isinstance(self._sel[0], Line):
            self.model.toggle(Vertical, (self._sel[0],))
            self._solve(); self.update()

    def act_fix(self):
        if len(self._sel) == 1 and isinstance(self._sel[0], Point):
            self.model.toggle(Fixed, (self._sel[0],))
            self._solve(); self.update()

    def act_dim(self):
        from PySide6.QtWidgets import QInputDialog
        if len(self._sel) != 1:
            return
        e = self._sel[0]
        if isinstance(e, Line):
            cur = math_dist(e.a, e.b)
            val, ok = QInputDialog.getDouble(self, "Dimension", "Length (mm):",
                                             round(cur, 3), 0.001, 1e6, 3)
            if ok:
                self.model.remove_last(Distance, (e.a, e.b))
                self.model.constrain(Distance(e.a, e.b, val))
                self._solve(); self.update()
        elif isinstance(e, Circle):
            val, ok = QInputDialog.getDouble(self, "Dimension", "Radius (mm):",
                                             round(e.r, 3), 0.001, 1e6, 3)
            if ok:
                self.model.remove_last(Radius, (e,))
                self.model.constrain(Radius(e, val))
                self._solve(); self.update()

    def act_delete(self):
        for e in list(self._sel):
            self.model.delete_entity(e)
        self._sel = []
        self._solve(); self.update()

    def _context_menu(self, ev: QMouseEvent):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        sel = self._sel
        if len(sel) == 1 and isinstance(sel[0], Line):
            menu.addAction("Horizontal", self.act_H)
            menu.addAction("Vertical", self.act_V)
            menu.addAction("Dimension…", self.act_dim)
        elif len(sel) == 1 and isinstance(sel[0], Circle):
            menu.addAction("Radius…", self.act_dim)
        elif len(sel) == 1 and isinstance(sel[0], Point):
            menu.addAction("Fix", self.act_fix)
        if sel:
            menu.addSeparator()
            menu.addAction("Delete", self.act_delete)
        else:
            menu.addAction("Rectangle tool", lambda: self.set_tool("rect"))
            menu.addAction("Line tool", lambda: self.set_tool("line"))
            menu.addAction("Circle tool", lambda: self.set_tool("circle"))
        menu.exec(ev.globalPosition().toPoint())
        self.update()

    def keyPressEvent(self, ev: QKeyEvent):
        k = ev.key()
        if self.model is None:
            return super().keyPressEvent(ev)
        sel = self._sel
        if k == Qt.Key_Escape:
            self._line_start = None
            self.set_tool("select")
            return
        if k == Qt.Key_S:
            self.set_tool("select")
        elif k == Qt.Key_L:
            self.set_tool("line")
        elif k == Qt.Key_R and not sel:
            self.set_tool("rect")
        elif k == Qt.Key_C and not sel:
            self.set_tool("circle")
        elif k == Qt.Key_Return and self._tool == "line":
            self._line_start = None
            self.set_tool("select")
        elif k == Qt.Key_X:
            self.finish()
            return
        elif k == Qt.Key_Delete:
            self.act_delete()
        elif k == Qt.Key_H:
            self.act_H()
        elif k == Qt.Key_V:
            self.act_V()
        elif k == Qt.Key_F:
            self.act_fix()
        elif k == Qt.Key_D:
            self.act_dim()
        else:
            return super().keyPressEvent(ev)
        self.update()

    def _solve(self, pins=()):
        self._last_result = self.model.solve(pins=pins)

    # ---- finish -----------------------------------------------------------
    def finish(self):
        loops, warns = self.model.to_loops()
        if warns:
            self.setToolTip("Warnings: " + "; ".join(warns))
        regs = regions(loops)
        if not regs:
            self._warn("No closed profile found — close your sketch (line tool: click the start point to finish a chain).")
            return
        out = []
        for r in regs:
            holes = [h["points"] for h in r.get("holes", [])]
            neg = sum(h["area"] for h in r.get("holes", []))
            if r["area"] - neg <= 1e-9:
                self._warn("Hole bigger than its outline — fix the sketch.")
                return
            out.append((r["points"], holes))
        self.profiles_ready.emit(out, self.model.name)

    def _warn(self, msg: str):
        self._warn_text = msg
        self.update()

    # ---- painting -----------------------------------------------------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), BG)
        self._draw_grid(p)
        if self.model:
            self._draw_entities(p)
            self._draw_dimensions(p)
            self._draw_glyphs(p)
            self._draw_preview(p)
        self._draw_hud(p)
        p.end()

    # ---- dimension labels (double-click editable, Fusion-style) ------------
    def _draw_dimensions(self, p: QPainter):
        self._dim_hits = []
        sk = self.model.sketch
        p.setFont(self._font)
        fm = p.fontMetrics()
        for c in sk.constraints:
            text = pos = None
            if isinstance(c, Distance):
                mid = self.w2s((c.p.x + c.q.x) / 2, (c.p.y + c.q.y) / 2)
                d = QPointF(c.q.x - c.p.x, c.q.y - c.p.y)
                ln = math.hypot(d.x(), d.y())
                if ln < 1e-9:
                    continue
                nx, ny = -d.y() / ln, d.x() / ln        # screen-space-ish normal
                pos = QPointF(mid.x() + nx * 16, mid.y() - ny * 16)
                text = f"{c.value:.2f}"
            elif isinstance(c, Radius):
                cen = self.w2s(c.circle.c.x, c.circle.c.y)
                pos = QPointF(cen.x(), cen.y() - c.circle.r * self._scale - 12)
                text = f"R {c.value:.2f}"
            if text is None:
                continue
            br = fm.boundingRect(text)
            rect = QRectF(pos.x() - br.width() / 2 - 5,
                          pos.y() - br.height() / 2 - 2,
                          br.width() + 10, br.height() + 4)
            p.setBrush(QColor("#23262c"))
            p.setPen(QPen(QColor("#2c6fb8"), 1))
            p.drawRoundedRect(rect, 3, 3)
            p.setPen(FG)
            p.drawText(rect, Qt.AlignCenter, text)
            p.setBrush(Qt.NoBrush)
            self._dim_hits.append((rect, c))

    def mouseDoubleClickEvent(self, ev: QMouseEvent):
        q = ev.position()
        for rect, c in getattr(self, "_dim_hits", []):
            if rect.contains(q):
                self._edit_dim(c)
                return
        super().mouseDoubleClickEvent(ev)

    def _edit_dim(self, c):
        val, ok = QInputDialog.getDouble(self, "Edit dimension",
                                         "Value (mm):", float(c.value),
                                         0.001, 1e6, 3)
        if not ok:
            return
        c.value = float(val)
        self._solve()
        self.update()

    def _grid_step(self) -> float:
        for s in (0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500):
            if s * self._scale >= 7:
                return s
        return 1000.0

    def _draw_grid(self, p: QPainter):
        step = self._grid_step()
        w0 = self._world(QPointF(0, 0))
        w1 = self._world(QPointF(self.width(), self.height()))
        x0, x1 = sorted((w0[0], w1[0]))
        y0, y1 = sorted((w1[1], w0[1]))
        font_before = p.font()
        p.setFont(self._font)
        for i in range(int(x0 // step) - 1, int(x1 // step) + 2):
            major = abs(i * step - round(i * step / (step * 5)) * step * 5) < step * 0.01
            p.setPen(QPen(GRID_MAJOR if major else GRID, 1))
            x = int(self.w2s(i * step, 0).x()) + 0.5
            p.drawLine(x, 0, x, self.height())
        for j in range(int(y0 // step) - 1, int(y1 // step) + 2):
            major = abs(j * step - round(j * step / (step * 5)) * step * 5) < step * 0.01
            p.setPen(QPen(GRID_MAJOR if major else GRID, 1))
            y = int(self.w2s(0, j * step).y()) + 0.5
            p.drawLine(0, y, self.width(), y)
        p.setPen(QPen(AXIS_X, 1.4))
        p.drawLine(self.w2s(x0, 0), self.w2s(x1, 0))
        p.setPen(QPen(AXIS_Y, 1.4))
        p.drawLine(self.w2s(0, y0), self.w2s(0, y1))
        p.setFont(font_before)

    def _draw_entities(self, p: QPainter):
        sk = self.model.sketch
        r = self._last_result
        constrained = r is not None and r.converged and r.dof == 0
        p.setPen(QPen(FG if constrained else ACCENT, 1.7))
        for l in sk.lines:
            p.drawLine(self.w2s(l.a.x, l.a.y), self.w2s(l.b.x, l.b.y))
        for c in sk.circles:
            cen = self.w2s(c.c.x, c.c.y)
            r = c.r * self._scale
            p.drawEllipse(cen, r, r)
        # selected
        p.setPen(QPen(ACCENT, 2.4))
        for e in self._sel:
            if isinstance(e, Line):
                p.drawLine(self.w2s(e.a.x, e.a.y), self.w2s(e.b.x, e.b.y))
            elif isinstance(e, Circle):
                cen = self.w2s(e.c.x, e.c.y)
                p.drawEllipse(cen, e.r * self._scale, e.r * self._scale)
        # points
        for pt, _ in self._all_points():
            pos = self.w2s(pt.x, pt.y)
            selected = pt in self._sel
            p.setPen(QPen(ACCENT if selected else DIM, 1.2))
            p.setBrush(ACCENT if selected else BG)
            s = 3.8 if selected else 2.6
            p.drawRect(QRectF(pos.x() - s, pos.y() - s, 2 * s, 2 * s))
        p.setBrush(Qt.NoBrush)
        if self._snap_hint is not None:
            pos = self.w2s(self._snap_hint.x, self._snap_hint.y)
            p.setPen(QPen(ACCENT, 1.6))
            p.drawEllipse(pos, 7, 7)

    def _draw_glyphs(self, p: QPainter):
        font = p.font()
        p.setFont(self._font)
        sk = self.model.sketch
        for c in sk.constraints:
            if isinstance(c, Horizontal) and isinstance(c.line, Line):
                m = self.w2s((c.line.a.x + c.line.b.x) / 2,
                             (c.line.a.y + c.line.b.y) / 2)
                self._badge(p, m, "H")
            elif isinstance(c, Vertical) and isinstance(c.line, Line):
                m = self.w2s((c.line.a.x + c.line.b.x) / 2,
                             (c.line.a.y + c.line.b.y) / 2)
                self._badge(p, m, "V")
            elif isinstance(c, Fixed):
                m = self.w2s(c.p.x, c.p.y)
                self._badge(p, m, "\u25a0")   # ■
            elif isinstance(c, Distance) and isinstance(c.p, Point):
                m = self.w2s((c.p.x + c.q.x) / 2, (c.p.y + c.q.y) / 2)
                self._badge(p, m, f"{c.value:g}", wide=True)
            elif isinstance(c, Radius):
                edge = self.w2s(c.circle.c.x + c.circle.r * 0.7071,
                                c.circle.c.y + c.circle.r * 0.7071)
                self._badge(p, edge, f"R{c.value:g}", wide=True)
        p.setFont(font)

    def _badge(self, p: QPainter, at: QPointF, text: str, wide=False):
        w = 20 if wide else 13
        rect = QRectF(at.x() - w / 2, at.y() - 8, w, 15)
        p.setPen(QPen(DIM, 1))
        p.setBrush(QColor(27, 29, 34, 200))
        p.drawRoundedRect(rect, 3, 3)
        p.setPen(FG)
        p.drawText(rect, Qt.AlignCenter, text)
        p.setBrush(Qt.NoBrush)

    def _draw_preview(self, p: QPainter):
        if self._tool == "line" and self._line_start is not None:
            cur = self.mapFromGlobal(self.cursor().pos())
            wp = self._world(QPointF(cur))
            p.setPen(QPen(ACCENT, 1.2, Qt.DashLine))
            p.drawLine(self.w2s(self._line_start.x, self._line_start.y),
                       self.w2s(*wp))
        if not self._preview:
            return
        kind, a, b = self._preview
        p.setPen(QPen(ACCENT, 1.4, Qt.DashLine))
        if kind == "rect":
            p.drawRect(min(a[0], b[0]), max(a[1], b[1]),
                       abs(b[0] - a[0]), abs(b[1] - a[1]))
        else:
            r = float(np.linalg.norm(b - a))
            cen = self.w2s(a[0], a[1])
            p.drawEllipse(cen, r * self._scale, r * self._scale)

    def _draw_hud(self, p: QPainter):
        lines = []
        if self.model:
            lines.append((f"Sketch: {self.model.name}  ·  plane {self.model.plane}",
                          FG))
        if self._cursor is not None:
            cx, cy = self._cursor
            lines.append((f"X {cx:.2f}   Y {cy:.2f} mm", DIM))
        tool = {"select": "Select (S/L/R/C) · H/V/F/D constraints · X extrude",
                "line": "Line — click points, Enter/Esc stops",
                "rect": "Rectangle — drag corners",
                "circle": "Circle — drag from center"}
        lines.append(("Tool: " + tool.get(self._tool, "?"), DIM))
        if self._last_result is not None:
            r = self._last_result
            if r.converged and r.dof == 0:
                lines.append(("Fully constrained", OK))
            elif not r.converged:
                lines.append(("Solver struggling (check constraints)", WARN))
            else:
                lines.append((f"{r.dof} DOF remaining", WARN))
        if getattr(self, "_warn_text", None):
            lines.append((self._warn_text, WARN))
        font = p.font()
        p.setFont(self._font)
        y = 16
        for text, col in lines:
            p.setPen(col)
            p.drawText(10, y, text)
            y += 16
        p.setFont(font)
