"""2D sketch canvas (QPainter — crisp text/glyphs, no GL needed in 2D).

Tools: S select · L line chain · R rectangle · C circle · A arc.
Constraint keys act on selection: H/V (line), F (point), D (distance on
line), plus Del. X finishes into profile(s). Solver runs live on every
drag with the grabbed point pinned — like it should.
"""
from __future__ import annotations

import json
import math

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QSettings, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QKeyEvent, QMouseEvent, QPainter,
                           QPen, QWheelEvent)
from PySide6.QtWidgets import QWidget

from ..core.sketch.constraints import (Angle, AngleBetween, Collinear,
                                       Concentric, Distance, Equal, Fixed,
                                       Horizontal, Midpoint, Perpendicular,
                                       PointOnCircle, PointOnLine, Radius,
                                       Symmetry, Tangent, Vertical,
                                       make_angle, make_angle_between,
                                       make_tangent, snapped)
from ..core.sketch.entities import (Arc, Circle, Ellipse, Line, Point,
                                     curve_center, curve_radius)
from ..core.sketch.model import (_dim_tag, SketchModel, math_dist,
                                 model_from_dict, model_to_dict)
from ..core.sketch.profile import regions
from . import theme
from .cmddialog import Shell
from .commands import SKETCH_KEYS

# keys the canvas owns (M113): plain printables from the command table,
# claimed from Qt's shortcut-override system so the global layer can't
# steal them; anything else bubbles to the window's model dispatch
_CLAIM_TEXT = {c.lower() for c in SKETCH_KEYS
               if "+" not in c and c not in ("Enter", "Esc")}

ACCENT = QColor(theme.SKETCH["under"])       # unconstrained / active blue
SEL = QColor(theme.SKETCH["sel"])            # picked geometry
PROJ = QColor(theme.SKETCH["projected"])     # projected reference edges
INFER = QColor(theme.SKETCH["infer"])        # inference + snap hint
FG = QColor(theme.SKETCH["full"])            # fully constrained = white
DIM = QColor(theme.CHAR[".500"])
CONSTR = QColor(theme.SKETCH["construction"])
DIMC = QColor(theme.SKETCH["dim"])           # dimensions are green
HUD = QColor(theme.SKETCH["hud"])            # heads-up readouts are blue
FAINT = QColor(theme.DB[".200"])
BG = QColor(theme.DB[".250"])
GRID = QColor(theme.rgba(theme.DB[".100"], 46))
GRID_MAJOR = QColor(theme.rgba(theme.DB[".100"], 76))
AXIS_X = QColor.fromRgbF(*theme.DARK["axis_x"])
AXIS_Y = QColor.fromRgbF(*theme.DARK["axis_y"])
OK = QColor(theme.SUCCESS)
WARN = QColor(theme.WARNING)

_HIT_PX = 9


def _line_pivot(l1, l2):
    """Shared endpoint if any, else the intersection of the two infinite
    lines, else None when parallel (an AngleBetween on parallel lines has
    no visible vertex, so no arc is drawn)."""
    for p in (l1.a, l1.b):
        if p is l2.a or p is l2.b:
            return p.x, p.y
    d1 = (l1.b.x - l1.a.x, l1.b.y - l1.a.y)
    d2 = (l2.b.x - l2.a.x, l2.b.y - l2.a.y)
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-12:
        return None
    t = ((l2.a.x - l1.a.x) * d2[1] - (l2.a.y - l1.a.y) * d2[0]) / den
    return l1.a.x + d1[0] * t, l1.a.y + d1[1] * t


def _in_box(pt, lo, hi) -> bool:
    return lo[0] <= pt.x <= hi[0] and lo[1] <= pt.y <= hi[1]


def _segs_cross(p1, p2, p3, p4) -> bool:
    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2 = cr(p3, p4, p1), cr(p3, p4, p2)
    d3, d4 = cr(p1, p2, p3), cr(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _seg_hits_box(p1, p2, lo, hi) -> bool:
    """Segment touches the box: an end inside, OR it crosses an edge —
    a line passing clean through with both ends outside still hits,
    exactly like Fusion's marquee."""
    def inside(p):
        return lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1]
    if inside(p1) or inside(p2):
        return True
    c = [(lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1])]
    return any(_segs_cross(p1, p2, c[i], c[(i + 1) % 4]) for i in range(4))


class SketchCanvas(QWidget):
    profiles_ready = Signal(list, str, bool)   # profiles, name, revolve?
    state_changed = Signal(object)             # SolveResult after each
                                               # solve — the constraint
                                               # voice (M73)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)      # live coordinate readout, like Fusion
        self._cursor: tuple | None = None
        self.model: SketchModel | None = None
        self._scale = 4.0                   # px per mm
        self._center = np.array([0.0, 0.0])  # world point at widget center
        self._tool = "select"
        self._sel: list = []
        self._redundant: set = set()          # M87 diagnosis (ids)
        self._conflicting: set = set()        # M87 diagnosis (ids)
        self._params_provider = lambda: ({}, 1.0)   # M89 fx look at sheet
        self._pending = None                 # M90: ("line"|"circle"|..., e)
        self._num_buf = ""                   # M90: type-in digits so far
        self._pending_stage = 0              # M90: rect width then height
        self._drag_pt: Point | None = None
        self._pan_from: QPointF | None = None
        self._line_start: Point | None = None
        self._rect_corner: np.ndarray | None = None
        self._arc_pts: list[Point] = []       # 3-pt tool: start, end, bulge
        self._preview: tuple | None = None  # tool drag preview
        self._band: list | None = None      # select marquee (2 QPoints)
        self._snap_hint: Point | tuple | None = None
        self._snap_grid = bool(QSettings().value("sketch/grid_snap",
                                                 False, type=bool))
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
        self._rect_corner = None
        self._arc_pts = []
        self._slot: list = []                  # slot tool: c1, c2, width
        self._poly: list = []                  # polygon tool: centre, vertex
        self._poly_n = 6                       # sides, 3..9 (sticky setting)
        self._preview = None
        self._band = None
        self._last_result = None
        self._hist = []
        self._fut = []
        self._drag_pushed = False
        self.set_tool("select")
        self._solve()           # state of the loaded sketch, spoken now
        self.fit_view()
        self.update()

    # ---- sketch-level undo/redo (entity ops; document ops use main undo) ----
    def _push_hist(self):
        self._hist.append(json.dumps(model_to_dict(self.model)))
        if len(self._hist) > 50:
            self._hist.pop(0)
        self._fut.clear()

    def undo_op(self) -> bool:
        if not self._hist:
            return False
        self._fut.append(json.dumps(model_to_dict(self.model)))
        self._restore(json.loads(self._hist.pop()))
        return True

    def redo_op(self) -> bool:
        if not self._fut:
            return False
        self._hist.append(json.dumps(model_to_dict(self.model)))
        self._restore(json.loads(self._fut.pop()))
        return True

    def _restore(self, d: dict):
        tmp = model_from_dict(d)
        # keep THIS model's identity: sid links features to their sketch
        self.model.sketch = tmp.sketch
        self.model.refs = tmp.refs              # projected edges undo too
        self.model.dim_exprs = tmp.dim_exprs    # M89 fx bindings undo too
        self._pending = None                    # M90: type-ins don't survive
        self._num_buf = ""                      # a history jump
        self._sel = []
        self._drag_pt = None
        self._line_start = None
        self._rect_corner = None
        self._arc_pts = []
        self._slot: list = []                  # slot tool: c1, c2, width
        self._poly: list = []                  # polygon tool: centre, vertex
        self._preview = None
        self._solve()
        self.update()

    def set_tool(self, tool: str):
        self._tool = tool
        if tool != "line":
            self._line_start = None
        self._rect_corner = None
        self._arc_pts = []
        self._slot: list = []                  # slot tool: c1, c2, width
        self._poly: list = []                  # polygon tool: centre, vertex
        self._preview = None
        self._band = None
        self._snap_hint = None
        self.setCursor(Qt.ArrowCursor if tool == "select"
                       else Qt.CrossCursor)    # Fusion's drafting cursor
        self.update()

    def set_grid_snap(self, on: bool):
        self._snap_grid = bool(on)
        QSettings().setValue("sketch/grid_snap", self._snap_grid)
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
    def _snap_point(self, q: QPointF, skip=None) -> Point | None:
        best, bd = None, _HIT_PX
        for p, _ in self._all_points():
            if p is skip:
                continue                 # dragged point must not eat itself
            s = self.w2s(p.x, p.y)
            d = math.hypot(s.x() - q.x(), s.y() - q.y())
            if d <= bd:
                best, bd = p, d
        return best

    def _snap_target(self, q: QPointF, skip=None):
        """Fusion's drawing magnet: an existing point first, the sketch
        origin next, then (when the toggle is on) grid intersections.
        Returns the existing Point, an (x, y) candidate that would have
        to be minted, or None for free space.  skip= excludes a point
        (the drag must not snap to its own cursor)."""
        p = self._snap_point(q, skip=skip)
        if p is not None:
            return p
        wp = self._world(q)
        for r in getattr(self.model, "refs", []):       # M82: projected
            for x, y in np.asarray(r["pts"], float):    # edges magnetize
                if math.hypot(x - wp[0], y - wp[1]) * self._scale <= _HIT_PX:
                    return (float(x), float(y))
        if math.hypot(wp[0], wp[1]) * self._scale <= _HIT_PX:
            return (0.0, 0.0)                      # the sketch origin
        if self._snap_grid:
            s = self._grid_step()
            gx, gy = round(wp[0] / s) * s, round(wp[1] / s) * s
            if math.hypot(gx - wp[0], gy - wp[1]) * self._scale <= _HIT_PX:
                return (gx, gy)
        return None

    def _place_point(self, q: QPointF) -> Point:
        """_snap_target made real: reuse the existing Point, or mint it
        at the origin/grid candidate / free-world position."""
        t = self._snap_target(q)
        if isinstance(t, Point):
            return t
        return self.model.point(*(t if t is not None else self._world(q)))

    def _band_select(self, a: QPointF, b: QPointF, additive: bool):
        """Everything the marquee TOUCHES (window + crossing at once,
        the way Fusion's sketch box behaves)."""
        w0, w1 = self._world(a), self._world(b)
        lo = np.array([min(w0[0], w1[0]), min(w0[1], w1[1])])
        hi = np.array([max(w0[0], w1[0]), max(w0[1], w1[1])])
        sk = self.model.sketch
        found = []
        for p in sk.points:
            if _in_box(p, lo, hi):
                found.append(p)
        for ln in sk.lines:
            if _seg_hits_box((ln.a.x, ln.a.y), (ln.b.x, ln.b.y), lo, hi):
                found.append(ln)
        for c in sk.circles:
            d = np.array([max(lo[0] - c.c.x, 0.0, c.c.x - hi[0]),
                          max(lo[1] - c.c.y, 0.0, c.c.y - hi[1])])
            dmin = float(np.hypot(*d))
            dmax = max(math.hypot(c.c.x - cx, c.c.y - cy)
                       for cx in (lo[0], hi[0]) for cy in (lo[1], hi[1]))
            if dmin <= c.r or dmax <= c.r:
                found.append(c)
        for ar in sk.arcs:                    # two chords trace the curve
            if (any(_in_box(pt, lo, hi) for pt in (ar.a, ar.m, ar.b))
                    or _seg_hits_box((ar.a.x, ar.a.y), (ar.m.x, ar.m.y),
                                     lo, hi)
                    or _seg_hits_box((ar.m.x, ar.m.y), (ar.b.x, ar.b.y),
                                     lo, hi)):
                found.append(ar)
        if additive:
            for e in found:
                if e not in self._sel:
                    self._sel.append(e)
        else:
            self._sel = found

    def _draw_band(self, p: QPainter):
        if self._band is None:
            return
        p.setPen(QPen(ACCENT, 1.0, Qt.DotLine))
        p.setBrush(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 28))
        p.drawRect(QRectF(self._band[0], self._band[1]).normalized())
        p.setBrush(Qt.NoBrush)

    def _all_points(self):
        sk = self.model.sketch
        seen = {}
        for l in sk.lines:
            for p in (l.a, l.b):
                seen[p.id] = p
        for c in sk.circles:
            seen[c.c.id] = c.c
        for a in sk.arcs:
            for p in (a.a, a.b, a.m):
                seen[p.id] = p
        for e in sk.ellipses:
            seen[e.c.id] = e.c
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
        for ar in sk.arcs:
            if self._arc_hit(ar, q):
                return ("arc", ar)
        for e in sk.ellipses:               # same polyline grammar
            if self._arc_hit(e, q):
                return ("ellipse", e)
        for l in sk.lines:
            if self._pt_seg_px(q, l.a, l.b) <= _HIT_PX:
                return ("line", l)
        return None

    def _arc_hit(self, ar, q: QPointF) -> bool:
        smp = ar.sample(32)
        for i in range(len(smp) - 1):
            a = self.w2s(float(smp[i][0]), float(smp[i][1]))
            b = self.w2s(float(smp[i + 1][0]), float(smp[i + 1][1]))
            abx, aby = b.x() - a.x(), b.y() - a.y()
            L2 = abx * abx + aby * aby
            if L2 < 1e-9:
                if math.hypot(q.x() - a.x(), q.y() - a.y()) <= _HIT_PX:
                    return True
                continue
            t = max(0.0, min(1.0, ((q.x() - a.x()) * abx
                                   + (q.y() - a.y()) * aby) / L2))
            px, py = a.x() + t * abx, a.y() + t * aby
            if math.hypot(q.x() - px, q.y() - py) <= _HIT_PX:
                return True
        return False

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
        if (ev.button() == Qt.LeftButton
                and self._pending is not None):        # M90: new stroke
            self._pending = None                       # drops the type-in
            self._num_buf = ""
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
                if not (ev.modifiers() & Qt.ControlModifier):
                    self._sel = []          # plain click clears; Ctrl keeps
                self._band = [QPointF(q), QPointF(q)]   # drag = marquee
            elif ev.modifiers() & Qt.ControlModifier:
                if hit[1] in self._sel:
                    self._sel.remove(hit[1])
                else:
                    self._sel.append(hit[1])
            else:
                self._sel = [hit[1]]
                if hit[0] == "point":
                    self._drag_pt = hit[1]
                    self._drag_pushed = False
            self.update()
            return
        wp = self._world(q)
        if self._tool == "line":
            p = self._place_point(q)              # point/origin/grid magnet
            if self._line_start is None:
                self._line_start = p
            else:
                if p is self._line_start:
                    self._line_start = None          # close chain
                else:
                    self._push_hist()
                    ln = self.model.add_line(self._line_start, p)
                    self._auto_constraints(ln, q)
                    self._solve()
                    self._line_start = p
                    self._pending = ("line", ln)      # M90: type a length
                    self._pending_stage = 0
                    self._num_buf = ""
            self.update()
        elif self._tool == "rect":
            # Fusion parity: supports BOTH corner-drag and click-move-click,
            # and corners SNAPPED TO AN EXISTING POINT share that point —
            # the corner belongs to both shapes, as in Fusion.
            if self._rect_corner is None:
                a = self._place_point(q)
                self._rect_corner = a
                self._preview = ("rect", np.array([a.x, a.y]),
                                 np.array([a.x, a.y]))
            else:
                a = self._rect_corner
                b = self._place_point(q)
                self._rect_corner = None
                self._preview = None
                if math.hypot(b.x - a.x, b.y - a.y) * self._scale > 6:
                    self._push_hist()
                    lines = self.model.add_rect(a, b)
                    self._solve()
                    if lines:                         # M90: width, height
                        self._pending = ("rect", lines)
                        self._pending_stage = 0
                        self._num_buf = ""
            self.update()
        elif self._tool == "circle":
            if self._rect_corner is None:
                c = self._place_point(q)
                self._rect_corner = c
                self._preview = ("circle", np.array([c.x, c.y]),
                                 np.array([c.x, c.y]))
            else:
                a = self._rect_corner
                t = self._snap_target(q)       # aim, but mint NO point:
                xy = ((t.x, t.y) if isinstance(t, Point)      # a stray
                      else (t if t is not None else wp))      # free point
                self._rect_corner = None
                self._preview = None
                r = math.hypot(xy[0] - a.x, xy[1] - a.y)      # would add 2
                if r * self._scale > 4:                       # phantom dof
                    self._push_hist()
                    cc = self.model.add_circle(a, r)
                    self._solve()
                    self._pending = ("circle", cc)  # M90: type a diameter
                    self._pending_stage = 0
                    self._num_buf = ""
            self.update()
        elif self._tool == "ellipse":
            # centre-first, exactly like the circle: the second click's
            # offsets from the centre ARE the two radii — and, like the
            # circle, the radius click must NOT mint a stray point.
            if self._rect_corner is None:
                c = self._place_point(q)
                self._rect_corner = c
                self._preview = ("ellipse", np.array([c.x, c.y]),
                                 np.array([c.x, c.y]))
            else:
                a = self._rect_corner
                t = self._snap_target(q)
                xy = ((t.x, t.y) if isinstance(t, Point)
                      else (t if t is not None else wp))
                self._rect_corner = None
                self._preview = None
                rx, ry = abs(xy[0] - a.x), abs(xy[1] - a.y)
                if rx * self._scale > 4 and ry * self._scale > 4:
                    self._push_hist()
                    self.model.sketch.ellipse(a, rx, ry)
                    self._solve()
            self.update()
        elif self._tool == "arc":
            # 3-point arc: start · end · point-on-arc, chained like a line.
            p = self._place_point(q)
            if len(self._arc_pts) == 2 and p is self._arc_pts[0]:
                self._arc_pts = []                   # back-click cancels
                self.update()
                return
            self._arc_pts.append(p)
            if len(self._arc_pts) == 3:
                a, b, mid = self._arc_pts
                self._arc_pts = [b]                  # chain from our end
                chord = math.hypot(b.x - a.x, b.y - a.y)
                bulge = abs((b.x - a.x) * (mid.y - a.y)
                            - (b.y - a.y) * (mid.x - a.x))
                # bulge = chord * sagitta, so bulge/chord**2 is the sagitta
                # as a fraction of chord: flat below 1 % (a ~5.7 deg arc).
                # Purely geometric — zooming must not change the entity type.
                flat = bulge < 0.01 * chord * chord
                if chord > 1e-9:
                    self._push_hist()
                    if flat:
                        self.model.add_line(a, b)    # flat enough -> line
                    else:
                        ar = self.model.sketch.arc(a, mid, b)
                        self._pending = ("arc", ar)  # M90: type a radius
                        self._pending_stage = 0
                        self._num_buf = ""
                    self._solve()
            self.update()
        elif self._tool == "slot":
            # 3 clicks: centre1 · centre2 · width. Snaps are honoured but we
            # snapshot coordinates (the slot owns its tangent-point geometry,
            # like corner_fillet), so no stray points are registered.
            t = self._snap_target(q)
            xy = ((t.x, t.y) if isinstance(t, Point)
                  else (t if t is not None else wp))
            self._slot.append(xy)
            self.update()
            if len(self._slot) == 3:
                (x1, y1), (x2, y2), (wx, wy) = self._slot
                self._slot = []
                self._preview = None
                dx, dy = x2 - x1, y2 - y1
                L = math.hypot(dx, dy)
                if L > 1e-9:
                    r = abs((wx - x1) * dy - (wy - y1) * dx) / L
                    if r * self._scale > 3:
                        self._push_hist()
                        self.model.add_slot(Point(x1, y1), Point(x2, y2), r)
                        self._solve()
            self.update()
        elif self._tool == "poly":
            # 2 clicks: centre · vertex. The circumradius is the click
            # distance, the rotation the click angle — and the number
            # keys (3..9) set the side count live while drawing.
            t = self._snap_target(q)
            xy = ((t.x, t.y) if isinstance(t, Point)
                  else (t if t is not None else wp))
            self._poly.append(xy)
            self.update()
            if len(self._poly) == 2:
                (cx, cy), (vx, vy) = self._poly
                self._poly = []
                self._preview = None
                r = math.hypot(vx - cx, vy - cy)
                if r * self._scale > 3:
                    self._push_hist()
                    self.model.add_polygon(cx, cy, r,
                                           math.atan2(vy - cy, vx - cx),
                                           self._poly_n)
                    self._solve()
            self.update()

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
                if not self._drag_pushed:
                    self._push_hist()
                    self._drag_pushed = True
                # dragged points CLICK onto origins, grid and other
                t = self._snap_target(q, skip=self._drag_pt)
                if isinstance(t, Point):       # points, Fusion-style
                    wp = np.array([t.x, t.y])
                elif t is not None:
                    wp = np.array(t)
                else:
                    wp = self._world(q)
                self._drag_pt.x, self._drag_pt.y = float(wp[0]), float(wp[1])
                self._solve(pins=[self._drag_pt])
                self._snap_hint = t
                self.update()
            elif self._band is not None:
                self._band[1] = q
                self.update()
            return
        if self._tool != "select":
            # Fusion shows the magnet while you HOVER, not only mid-drag
            self._snap_hint = self._snap_target(q)
        if self._preview:
            wp = self._world(q)
            kind, start = self._preview[0], self._preview[1]
            self._preview = (kind, start, wp)
            self.update()

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if ev.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_from = None
            return
        if self._tool == "select":
            self._drag_pt = None
            if self._band is not None:
                a, b = self._band
                self._band = None
                if (abs(a.x() - b.x()) > 3
                        or abs(a.y() - b.y()) > 3):
                    self._band_select(           # real drag: marquee wins
                        a, b, bool(ev.modifiers() & Qt.ControlModifier))
                self.update()                    # else it was a click
            return
        if not self._preview:
            return
        kind, a, b = self._preview
        self._preview = None
        committed = False
        # The armed corner IS a real Point since M77 — the drag must
        # REUSE it, not mint a second centre and orphan the first.
        rc = self._rect_corner if isinstance(self._rect_corner, Point) \
            else None
        if kind == "rect" and np.linalg.norm(b - a) * self._scale > 6:
            self._rect_corner = None            # drag wins; disarm click-mode
            self._push_hist()
            p0 = rc if rc is not None else self.model.point(*a)
            p1 = self.model.point(*b)
            lines = self.model.add_rect(p0, p1)
            self._solve()
            committed = True
            if lines:                           # M90: width, height
                self._pending = ("rect", lines)
                self._pending_stage = 0
                self._num_buf = ""
        elif kind == "circle":
            r = float(np.linalg.norm(b - a))
            if r * self._scale > 4:
                self._rect_corner = None
                self._push_hist()
                c0 = rc if rc is not None else self.model.point(*a)
                c = self.model.add_circle(c0, r)
                self._solve()
                committed = True
                self._pending = ("circle", c)   # M90: type a diameter
                self._pending_stage = 0
                self._num_buf = ""
        elif kind == "ellipse":
            rx, ry = abs(float(b[0] - a[0])), abs(float(b[1] - a[1]))
            if rx * self._scale > 4 and ry * self._scale > 4:
                self._rect_corner = None
                self._push_hist()
                c0 = rc if rc is not None else self.model.point(*a)
                self.model.sketch.ellipse(c0, rx, ry)
                self._solve()
                committed = True
        # click-move-click: a plain click leaves the first corner armed;
        # re-show the rubber band so moving the mouse previews the shape.
        # (Since M77 the armed corner is a Point — the preview wants
        # plain coordinates, or _draw_preview's subscripts crash.)
        if not committed and self._rect_corner is not None:
            rc = self._rect_corner
            xy = np.array([rc.x, rc.y]) if isinstance(rc, Point) else rc
            self._preview = (kind, xy, xy)
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
            self._push_hist()
            self.model.toggle(Horizontal, (self._sel[0],))
            self._solve(); self.update()

    def act_V(self):
        if len(self._sel) == 1 and isinstance(self._sel[0], Line):
            self._push_hist()
            self.model.toggle(Vertical, (self._sel[0],))
            self._solve(); self.update()

    def act_fix(self):
        if len(self._sel) == 1 and isinstance(self._sel[0], Point):
            self._push_hist()
            self.model.toggle(Fixed, (self._sel[0],))
            self._solve(); self.update()

    def act_dim(self):
        if len(self._sel) == 2 and all(isinstance(e, Point) for e in self._sel):
            p, q = self._sel
            cur = math_dist(p, q)
            val, ok = Shell.getDouble(self, "Dimension",
                                             "Distance (mm):",
                                             round(cur, 3), 0.001, 1e6, 3)
            if ok:
                self._push_hist()
                self.model.remove_last(Distance, (p, q))
                self.model.constrain(Distance(p, q, val))
                self._solve(); self.update()
            return
        if len(self._sel) != 1:
            return
        e = self._sel[0]
        if isinstance(e, Line):
            cur = math_dist(e.a, e.b)
            val, ok = Shell.getDouble(self, "Dimension", "Length (mm):",
                                             round(cur, 3), 0.001, 1e6, 3)
            if ok:
                self._push_hist()
                self.model.remove_last(Distance, (e.a, e.b))
                self.model.constrain(Distance(e.a, e.b, val))
                self._solve(); self.update()
        elif isinstance(e, (Circle, Arc)):
            dia = isinstance(e, Circle)               # M98: Ø for circles
            cur = curve_radius(e)
            val, ok = Shell.getDouble(
                self, "Dimension",
                "Diameter (mm):" if dia else "Radius (mm):",
                round(cur * 2 if dia else cur, 3), 0.001, 1e6, 3)
            if ok:
                self._push_hist()
                self.model.remove_last(Radius, (e,))
                self.model.constrain(Radius(e, val / 2 if dia else val))
                self._solve(); self.update()

    def act_perp(self):
        if len(self._sel) == 2 and all(isinstance(e, Line) for e in self._sel):
            self._push_hist()
            self.model.toggle(Perpendicular, tuple(self._sel))
            self._solve(); self.update()

    def act_equal(self):
        """Equal length (two lines) or equal radius (two circles/arcs) —
        the Q key and menu handle both, mixed pairs are refused."""
        if len(self._sel) != 2:
            return
        pairs = (all(isinstance(e, Line) for e in self._sel)
                 or all(isinstance(e, (Circle, Arc)) for e in self._sel))
        if not pairs:
            return
        self._push_hist()
        self.model.toggle(Equal, tuple(self._sel))
        self._solve(); self.update()

    def act_concentric(self):
        """Two circles/arcs share a centre (Fusion's '2')."""
        if len(self._sel) == 2 and all(isinstance(e, (Circle, Arc))
                                       for e in self._sel):
            self._push_hist()
            self.model.toggle(Concentric, tuple(self._sel))
            self._solve(); self.update()

    @staticmethod
    def on_ok(sel) -> bool:
        """point + curve — see _on_roles for the accepted pairings."""
        if len(sel) != 2:
            return False
        p, c = SketchCanvas._on_roles(sel)
        return p is not None and c is not None

    @staticmethod
    def _on_roles(sel):
        """Resolve (point, curve) out of a two-entity pick: Line/Arc can
        only be the curve, a bare Point only the point; a lone Circle
        plays either role (its centre), never both at once."""
        curves = [e for e in sel if isinstance(e, (Line, Arc))]
        pts = [e for e in sel if isinstance(e, Point)]
        circles = [e for e in sel if isinstance(e, Circle)]
        if curves and pts:
            return pts[0], curves[0]
        if len(circles) == 1 and (pts or curves):
            return (pts[0], circles[0]) if pts else (circles[0].c, curves[0])
        return None, None

    def act_on(self):
        """Pin a point onto a line/circle/arc — Fusion's On-Curve. A
        circle picked as the point contributes its centre; a circle
        picked as the curve hosts the point on its ring."""
        if not self.on_ok(self._sel):
            return
        p, curve = self._on_roles(self._sel)
        ctype = PointOnLine if isinstance(curve, Line) else PointOnCircle
        self._push_hist()
        self.model.toggle(ctype, (p, curve))
        self._solve(); self.update()

    @staticmethod
    def sym_ok(sel) -> bool:
        """point · point · line (a circle stands in for its centre)."""
        if len(sel) != 3:
            return False
        lines = sum(isinstance(e, Line) for e in sel)
        pts = sum(isinstance(e, (Point, Circle)) for e in sel)
        return lines == 1 and pts == 2

    def act_symmetry(self):
        """Mirror two points across a construction line (the classic
        symmetric-bracket trick around a centreline)."""
        if not self.sym_ok(self._sel):
            return
        axis = next(e for e in self._sel if isinstance(e, Line))
        pts = [e.c if isinstance(e, Circle) else e
               for e in self._sel if isinstance(e, (Point, Circle))]
        self._push_hist()
        self.model.toggle(Symmetry, (pts[0], pts[1], axis))
        self._solve(); self.update()

    @staticmethod
    def midpoint_ok(sel) -> bool:
        """point + line (a circle stands in for its centre)."""
        if len(sel) != 2:
            return False
        lines = sum(isinstance(e, Line) for e in sel)
        pts = sum(isinstance(e, (Point, Circle)) for e in sel)
        return lines == 1 and pts == 1

    def act_midpoint(self):
        """Pin a point to the middle of a line (Fusion's Midpoint): the
        line pivots about it while both ends stay free."""
        if not self.midpoint_ok(self._sel):
            return
        line = next(e for e in self._sel if isinstance(e, Line))
        pt = next((e for e in self._sel if isinstance(e, Point)),
                  None) or next(e for e in self._sel
                                if isinstance(e, Circle)).c
        self._push_hist()
        self.model.toggle(Midpoint, (pt, line))
        self._solve(); self.update()

    @staticmethod
    def collinear_ok(sel) -> bool:
        """exactly two lines."""
        return len(sel) == 2 and all(isinstance(e, Line) for e in sel)

    def act_collinear(self):
        """Merge two segments onto one infinite line (Fusion's Collinear)
        — the two-segment top edge of a bracket reads as one datum."""
        if not self.collinear_ok(self._sel):
            return
        l1, l2 = self._sel
        self._push_hist()
        self.model.toggle(Collinear, (l1, l2))
        self._solve(); self.update()

    @staticmethod
    def tangent_ok(sel) -> bool:
        """line + curve or curve + curve — the pairs tangent can relate."""
        curves = sum(isinstance(e, (Circle, Arc)) for e in sel)
        lines = sum(isinstance(e, Line) for e in sel)
        return len(sel) == 2 and (curves == 2 or (curves == 1 and lines == 1))

    def act_tangent(self):
        """Tangent between a line and a circle/arc, or between two curves.
        Mirrors Fusion: one gesture, the geometry decides the branch."""
        if not self.tangent_ok(self._sel):
            return
        self._push_hist()
        line = next((e for e in self._sel if isinstance(e, Line)), None)
        curves = tuple(e for e in self._sel if isinstance(e, (Circle, Arc)))
        self.model.toggle(Tangent, (line, curves[0]) if line else curves)
        self._solve(); self.update()

    def act_fillet(self):
        """Trim the selected corner to a tangent arc (Fusion's sketch F)."""
        from ..core.sketch.fillet import corner_fillet
        self._corner_op("Fillet corner", "Radius (mm):",
                        lambda l1, l2, v: corner_fillet(self.model, l1, l2, v))

    def act_chamfer(self):
        """Cut the selected corner flat by an equal trim on both legs."""
        from ..core.sketch.fillet import corner_chamfer
        self._corner_op("Chamfer corner", "Distance (mm):",
                        lambda l1, l2, v: corner_chamfer(self.model, l1, l2, v))

    def act_trim(self):
        """Close the corner between two loose lines (Fusion's trim):
        overshoot is cut back, gaps are extended — ends land EXACTLY on
        the infinite-line intersection and merge into one shared point."""
        from ..core.sketch.trim import close_corner
        if len(self._sel) != 2 or not all(isinstance(e, Line)
                                          for e in self._sel):
            return
        self._push_hist()
        try:
            close_corner(self.model, *self._sel)
        except ValueError as e:
            self._hist.pop()                      # nothing was mutated yet
            self._warn(str(e))
            return
        self._sel = []
        self._solve(); self.update()

    def act_offset(self):
        """Copy the outline with a parallel offset (Fusion's Offset
        Entities): a twin loop at signed distance, outward positive —
        walls, ribs and clearance rings.  Mitre joins on plain straight
        loops stay exact; rounded joins, arcs, circles and holed
        outlines ride the manifold kernel's robust offset (M84)."""
        if self.model is None:
            return
        from . import cmddialog
        v = cmddialog.ask(self, "Offset Entities", [
            dict(key="d", kind="double",
                 label="Distance (mm, negative = inward)",
                 default=3.0, min=-10000.0, max=10000.0, decimals=2),
            dict(key="j", kind="combo", label="Join",
                 choices=["mitre", "round"], default="mitre")])
        if v is None:
            return
        self._push_hist()
        try:
            self.model.add_offset(v["d"], join=v["j"])
        except ValueError as e:
            self._hist.pop()                      # nothing was mutated
            self._warn(str(e))
            return
        self._sel = []
        self.set_tool("select")
        self._solve()
        self.update()

    def _corner_op(self, title, label, apply):
        """Shared plumbing for fillet/chamfer: two selected lines sharing a
        corner, a size dialog defaulted from the shorter leg, and refusals
        surfaced as canvas warnings (never a half-cut sketch)."""
        if len(self._sel) != 2 or not all(isinstance(e, Line)
                                          for e in self._sel):
            return
        l1, l2 = self._sel
        shared = next((p for p in (l1.a, l1.b) if p in (l2.a, l2.b)), None)
        if shared is None:
            self._warn("These two lines don't share a corner")
            return
        others = [p for p in (l1.a, l1.b) if p is not shared] + \
                 [p for p in (l2.a, l2.b) if p is not shared]
        leg = min(math.dist((shared.x, shared.y), (p.x, p.y)) for p in others)
        default = max(0.5, round(min(5.0, leg / 4.0), 1))
        v, ok = Shell.getDouble(self, title, label, default, 0.01,
                                       max(0.02, leg / 2.0 - 0.01), 2)
        if not ok:
            return
        self._push_hist()
        try:
            apply(l1, l2, v)
        except ValueError as e:
            self._hist.pop()                      # nothing was mutated yet
            self._warn(str(e))
            return
        self._sel = []
        self._solve(); self.update()

    def act_angle(self):
        """Angular dimension: one line → angle from +X; two lines → angle
        between (Fusion pivots the arc at the shared/intersection point)."""
        sel = self._sel
        if len(sel) == 1 and isinstance(sel[0], Line):
            ln = sel[0]
            deg = math.degrees(math.atan2(ln.b.y - ln.a.y, ln.b.x - ln.a.x)) % 180
            val, ok = Shell.getDouble(self, "Angular dimension",
                                             "Angle from +X (deg):",
                                             round(deg, 2), 0.0, 179.99, 2)
            if not ok:
                return
            self._push_hist()
            self.model.remove_last(Angle, (ln,))
            self.model.constrain(make_angle(ln, val))
            self._solve(); self.update()
        elif len(sel) == 2 and all(isinstance(e, Line) for e in sel):
            l1, l2 = sel
            t1 = math.atan2(l1.b.y - l1.a.y, l1.b.x - l1.a.x)
            t2 = math.atan2(l2.b.y - l2.a.y, l2.b.x - l2.a.x)
            deg = math.degrees(t2 - t1) % 180
            val, ok = Shell.getDouble(self, "Angular dimension",
                                             "Angle between (deg):",
                                             round(deg, 2), 0.0, 179.99, 2)
            if not ok:
                return
            self._push_hist()
            self.model.remove_last(AngleBetween, (l1, l2))
            self.model.constrain(make_angle_between(l1, l2, val))
            self._solve(); self.update()

    def act_construction(self):
        curves = (Line, Arc, Circle, Ellipse)
        if not any(isinstance(e, curves) for e in self._sel):
            return
        self._push_hist()
        for e in self._sel:
            if isinstance(e, curves):
                e.construction = not e.construction
        self._solve(); self.update()

    def act_mirror(self):
        """Mirror (Shift+M): the FIRST selected line is the axis; every
        other curve in the selection gets a mirrored twin.  Geometry on
        the axis shares its points, so the halves stay ONE profile."""
        lines = [e for e in self._sel if isinstance(e, Line)]
        if not lines:
            return
        axis = lines[0]
        ents = [e for e in self._sel if e is not axis
                and isinstance(e, (Line, Circle, Arc, Ellipse))]
        if not ents:
            return
        self._push_hist()
        made = self.model.mirror_about(axis, ents)
        if made:
            self._sel = made                 # the twins stay selected
        self._solve(); self.update()

    def act_delete(self):
        if not self._sel:
            return
        self._push_hist()
        for e in list(self._sel):
            self.model.delete_entity(e)
        self._sel = []
        self._solve(); self.update()

    def _context_menu(self, ev: QMouseEvent):
        self._build_menu().exec(ev.globalPosition().toPoint())
        self.update()

    def _build_menu(self):
        """The selection menu, split out so the action table is testable
        without popping a real (uninterceptable) popup."""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        sel = self._sel
        if len(sel) == 1 and isinstance(sel[0], Line):
            menu.addAction("Horizontal", self.act_H)
            menu.addAction("Vertical", self.act_V)
            menu.addAction("Dimension…", self.act_dim)
            menu.addAction("Angle…", self.act_angle)
            menu.addSeparator()
            menu.addAction("Hide construction"
                           if sel[0].construction else
                           "Construction geometry", self.act_construction)
        elif len(sel) == 2 and all(isinstance(e, Line) for e in sel):
            menu.addAction("Perpendicular", self.act_perp)
            menu.addAction("Equal length", self.act_equal)
            menu.addAction("Collinear", self.act_collinear)
            menu.addAction("Angle between…", self.act_angle)
            if any(p in (sel[1].a, sel[1].b) for p in (sel[0].a, sel[0].b)):
                menu.addAction("Fillet corner…", self.act_fillet)
                menu.addAction("Chamfer corner…", self.act_chamfer)
            else:
                menu.addAction("Trim / extend to corner", self.act_trim)
            menu.addSeparator()
            menu.addAction("Mirror about first line", self.act_mirror)
        elif not sel and self.model and (self.model.sketch.lines
                                         or self.model.sketch.circles):
            menu.addAction("Offset outline\u2026 (U)", self.act_offset)
        elif self.tangent_ok(sel):
            menu.addAction("Tangent", self.act_tangent)
            if all(isinstance(e, (Circle, Arc)) for e in sel):
                menu.addAction("Equal radius", self.act_equal)
                menu.addAction("Concentric", self.act_concentric)
        elif len(sel) == 2 and all(isinstance(e, Point) for e in sel):
            menu.addAction("Dimension…", self.act_dim)
        elif self.on_ok(sel):
            menu.addAction("On curve", self.act_on)
            if self.midpoint_ok(sel):
                menu.addAction("Midpoint", self.act_midpoint)
        elif self.sym_ok(sel):
            menu.addAction("Symmetric about line", self.act_symmetry)
        elif len(sel) == 1 and isinstance(sel[0], Circle):
            menu.addAction("Radius…", self.act_dim)
        elif len(sel) == 1 and isinstance(sel[0], Arc):
            menu.addAction("Radius…", self.act_dim)
            menu.addSeparator()
            menu.addAction("Hide construction"
                           if sel[0].construction else
                           "Construction geometry", self.act_construction)
        elif len(sel) == 1 and isinstance(sel[0], Point):
            menu.addAction("Fix", self.act_fix)
        if sel:
            menu.addSeparator()
            menu.addAction("Delete", self.act_delete)
        else:
            for label, t in (("Rectangle tool", "rect"), ("Line tool", "line"),
                             ("Circle tool", "circle"), ("Slot tool", "slot"),
                             ("Polygon tool", "poly"), ("Arc tool", "arc")):
                menu.addAction(label, lambda t=t: self.set_tool(t))
        return menu

    def event(self, ev):
        """Claim our letters against the global command layer (M113).

        Fusion truth: keys sleep while a text field types, and a sketch
        answers its own alphabet while the model layer answers the rest
        — E extrudes FROM a sketch precisely because it is not one of
        these letters."""
        if ev.type() == QEvent.Type.ShortcutOverride:
            mods = ev.modifiers()
            if not (mods & (Qt.ControlModifier | Qt.AltModifier
                            | Qt.MetaModifier)):
                txt = ev.text()
                if txt and txt.lower() in _CLAIM_TEXT:
                    ev.accept()
                    return True
        return super().event(ev)

    def keyPressEvent(self, ev: QKeyEvent):
        k = ev.key()
        if self.model is None:
            return super().keyPressEvent(ev)
        if self._pending is not None:               # M90: type-in first
            txt = ev.text()
            if txt.isdigit() or txt == ".":
                if len(self._num_buf) < 12:
                    self._num_buf += txt
                self.update()
                return
            if k == Qt.Key_Backspace:
                self._num_buf = self._num_buf[:-1]
                self.update()
                return
            if k in (Qt.Key_Return, Qt.Key_Enter) and self._num_buf:
                self._commit_typed()
                return
            self._pending = None                    # any other key lets go
            self._num_buf = ""                      # ...and is still heard
        sel = self._sel
        if k == Qt.Key_Escape:
            self._line_start = None
            self.set_tool("select")
            return
        if self._tool == "poly" and Qt.Key_3 <= k <= Qt.Key_9:
            self._poly_n = k - Qt.Key_0            # live side count (3..9)
            self.update()
            return
        if k == Qt.Key_Z and ev.modifiers() & Qt.ControlModifier:
            if ev.modifiers() & Qt.ShiftModifier:
                self.redo_op()
            else:
                self.undo_op()
            return
        if k == Qt.Key_Y and ev.modifiers() & Qt.ControlModifier:
            self.redo_op()
            return
        if k == Qt.Key_R and ev.modifiers() & Qt.ShiftModifier:
            self.finish(revolve=True)
            return
        elif k == Qt.Key_L and self.collinear_ok(sel):
            self.act_collinear()
        elif k == Qt.Key_L:
            self.set_tool("line")                 # Fusion: L is the line
        elif k == Qt.Key_R and not sel:
            self.set_tool("rect")
        elif k == Qt.Key_C and ev.modifiers() & Qt.ShiftModifier:
            self.set_tool("ellipse")              # circle family, Shift
        elif k == Qt.Key_C and not sel:
            self.set_tool("circle")
        elif k == Qt.Key_A and not sel:
            self.set_tool("arc")
        elif k == Qt.Key_Y and not sel:
            self.set_tool("poly")
        elif k == Qt.Key_K and not sel:
            self.set_tool("slot")                 # slot moved to K (free)
        elif k in (Qt.Key_O, Qt.Key_U):
            self.act_offset()                     # Fusion: O offsets
        elif k == Qt.Key_T and ev.modifiers() & Qt.ShiftModifier:
            self.act_tangent()                    # tangent took the Shift
        elif k == Qt.Key_T and len(sel) == 2 and \
                all(isinstance(e, Line) for e in sel):
            self.act_trim()                       # Fusion: T trims corners
        elif k == Qt.Key_Return and self._tool == "line":
            self._line_start = None
            self.set_tool("select")
        elif k == Qt.Key_Return:
            self.finish()                         # Finish Sketch: Enter
            return
        elif k == Qt.Key_X:
            self.act_construction()               # Fusion: X toggles
        elif k == Qt.Key_Delete:
            self.act_delete()
        elif k == Qt.Key_H:
            self.act_H()
        elif k == Qt.Key_V:
            self.act_V()
        elif k == Qt.Key_F:
            if len(sel) == 2 and all(isinstance(e, Line) for e in sel):
                self.act_fillet()                 # Fusion: F fillets a corner
            else:
                self.act_fix()
        elif k == Qt.Key_G and len(sel) == 2 and \
                all(isinstance(e, Line) for e in sel):
            self.act_chamfer()                    # G = the corner's flat twin
        elif k == Qt.Key_Period and self.on_ok(sel):
            self.act_on()                         # . pins a point on a curve
        elif k == Qt.Key_D:
            self.act_dim()
        elif k == Qt.Key_P and ev.modifiers() & Qt.ShiftModifier:
            self.act_perp()                       # perpendicular took Shift
        elif k == Qt.Key_P:
            proj = getattr(self.window(), "_project_model_edges", None)
            if proj is not None:                  # Fusion: P projects
                proj()
        elif k == Qt.Key_Q:
            self.act_equal()
        elif k == Qt.Key_I:
            self.act_angle()
        elif k == Qt.Key_2 and len(sel) == 2 and \
                all(isinstance(e, (Circle, Arc)) for e in sel):
            self.act_concentric()
        elif k == Qt.Key_M and ev.modifiers() & Qt.ShiftModifier \
                and len(sel) >= 2:
            self.act_mirror()               # shift+M: mirror entities
        elif k == Qt.Key_M:
            self.act_symmetry()
        elif k == Qt.Key_J:
            self.act_midpoint()
        else:
            return super().keyPressEvent(ev)
        self.update()

    def _solve(self, pins=()):
        self._last_result = self.model.solve(pins=pins)
        res = self._last_result
        self._redundant = {id(c) for c in getattr(res, "redundant", [])}
        self._conflicting = {id(c) for c in getattr(res, "conflicting", [])}
        self.state_changed.emit(self._last_result)

    # ---- finish -----------------------------------------------------------
    def finish(self, revolve: bool = False):
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
        self.profiles_ready.emit(out, self.model.name, bool(revolve))

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
            self._draw_refs(p)
            self._draw_entities(p)
            self._draw_dimensions(p)
            self._draw_glyphs(p)
            self._draw_typein(p)              # M90: the live number chip
            self._draw_preview(p)
        self._draw_band(p)
        self._draw_hud(p)
        p.end()

    # ---- dimension labels (double-click editable, Fusion-style) ------------
    def _dim_text(self, c) -> str:
        """The chip's wording (M98): circles speak DIAMETER like Fusion
        (the constraint underneath stays a radius — only the UI
        translates); arcs keep R, what a fillet gauge measures."""
        if isinstance(c, Radius):
            return (f"\u00d8 {2 * c.value:.2f}"
                    if isinstance(c.curve, Circle)
                    else f"R {c.value:.2f}")
        if isinstance(c, Distance):
            return f"{c.value:.2f}"
        return ""

    def _draw_dimensions(self, p: QPainter):
        self._dim_hits = []
        sk = self.model.sketch
        p.setFont(self._font)
        fm = p.fontMetrics()
        seen_pivots = []                 # screen pts of angle dims so far
        for ci, c in enumerate(sk.constraints):
            bound = ci in self.model.dim_exprs      # M89: fx-driven dims
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
                pos = self._radius_pos(c.curve)
                text = self._dim_text(c)          # Ø on circles (M98)
            elif isinstance(c, (Angle, AngleBetween)):
                arc = None
                pv = self._angle_pivot(c)
                ring = 0
                if pv is not None:
                    s = self.w2s(pv[0], pv[1])
                    ring = sum(1 for q in seen_pivots
                               if math.hypot(s.x() - q.x(), s.y() - q.y()) < 14)
                    seen_pivots.append(s)
                arc = self._angle_arc_pts(c, ring)
                if arc is None:
                    continue
                pts, label = arc
                self._draw_arc(p, pts)
                pos = label
                text = f"{math.degrees(c.value) % 180:.2f}\u00b0"
            if text is None:
                continue
            if bound:                       # M89: Fusion shows "=" driven
                text = f"= {text}"
            br = fm.boundingRect(text)
            rect = QRectF(pos.x() - br.width() / 2 - 5,
                          pos.y() - br.height() / 2 - 2,
                          br.width() + 10, br.height() + 4)
            p.setBrush(QColor(theme.DARK["bg2"]))
            p.setPen(QPen(QColor(theme.DARK["accent"]) if bound
                          else QColor(theme.DARK["accent_dim"]), 1))
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
        if isinstance(c, (Angle, AngleBetween)):
            deg = math.degrees(c.value) % 180
            val, ok = Shell.getDouble(self, "Edit angle",
                                             "Angle (deg):", round(deg, 2),
                                             0.0, 179.99, 2)
            if not ok:
                return
            self._push_hist()
            # re-snap to the branch the geometry currently occupies, so
            # editing never flips the line through 180°
            c.value = snapped(c.measured(), math.radians(val))
        else:
            # M89: the number field plus an fx line — a formula here
            # binds the dimension to the parameter sheet, live
            from . import cmddialog
            from ..core.params import ParamError, eval_expr
            i = next((j for j, cc in
                      enumerate(self.model.sketch.constraints)
                      if cc is c), None)
            rec = self.model.dim_exprs.get(i) if i is not None else None
            dia = isinstance(c, Radius) and isinstance(c.curve, Circle)
            v = cmddialog.ask(self, "Edit dimension", [
                dict(key="val", kind="double",
                     label="Diameter (mm)" if dia else "Value (mm)",
                     default=round(2 * float(c.value) if dia
                                   else float(c.value), 3),
                     min=0.001,
                     max=1e6, decimals=3),
                dict(key="fx", kind="text",
                     label="fx  (blank = plain number)",
                     default=(rec or {}).get("e", ""))])
            if v is None:
                return
            expr = str(v["fx"]).strip().lstrip("=").strip()
            if expr:
                vals, sc = self._params_provider()
                try:
                    newv = float(eval_expr(expr, vals)) * sc
                except ParamError as e:
                    self._warn(f"Binding refused: {e}")
                    self.update()
                    return                       # the number stays honest
                self._push_hist()
                if i is not None:
                    self.model.dim_exprs[i] = {"e": expr, "t": _dim_tag(c)}
                c.value = newv * 0.5 if dia else newv   # M98: fx speaks Ø
            else:
                self._push_hist()
                if i is not None:
                    self.model.dim_exprs.pop(i, None)
                c.value = (float(v["val"]) * 0.5 if dia
                           else float(v["val"]))
        self._solve()
        self.update()

    def _commit_typed(self):
        """M90: Enter mid-type-in mints exactly the constraint act_dim
        would — same remove_last habit (re-typing never stacks), same
        solver — only without the dialog."""
        try:
            v = max(float(self._num_buf), 0.001)
        except ValueError:
            self._num_buf = ""          # blank or stray ".": Enter is a no-op
            self.update()
            return
        kind, ent = self._pending
        self._push_hist()
        if kind == "line":
            self.model.remove_last(Distance, (ent.a, ent.b))
            self.model.constrain(Distance(ent.a, ent.b, v))
            self._pending = None
        elif kind in ("circle", "arc"):
            self.model.remove_last(Radius, (ent,))
            # M98: after a CIRCLE the typed number is the DIAMETER
            # (what the chip will read); an arc still speaks radius.
            self.model.constrain(Radius(ent, v / 2 if kind == "circle"
                                        else v))
            self._pending = None
        elif kind == "rect":
            ln = ent[0] if self._pending_stage == 0 else ent[1]
            self.model.remove_last(Distance, (ln.a, ln.b))
            self.model.constrain(Distance(ln.a, ln.b, v))
            if self._pending_stage == 0:
                self._pending_stage = 1     # the next number is the height
            else:
                self._pending = None
        self._num_buf = ""
        self._solve()
        self.update()

    def _typein_pos(self):
        """Where Fusion's little white box lives for the armed entity."""
        kind, ent = self._pending
        if kind == "line":
            return self.w2s((ent.a.x + ent.b.x) / 2, (ent.a.y + ent.b.y) / 2)
        if kind == "circle":
            return self.w2s(ent.c.x + ent.r, ent.c.y)
        if kind == "arc":
            return self.w2s(ent.m.x, ent.m.y)
        if kind == "rect":
            ln = ent[0] if self._pending_stage == 0 else ent[1]
            return self.w2s((ln.a.x + ln.b.x) / 2, (ln.a.y + ln.b.y) / 2)
        return None

    def _draw_typein(self, p: QPainter):
        """The chip itself: same visual family as a dimension label, so
        it reads as 'this number is about to become that dimension'."""
        if self._pending is None or not self._num_buf:
            return
        at = self._typein_pos()
        if at is None:
            return
        fm = p.fontMetrics()
        br = fm.boundingRect(self._num_buf)
        rect = QRectF(at.x() - br.width() / 2 - 6,
                      at.y() - br.height() / 2 - 3,
                      br.width() + 12, br.height() + 6)
        p.setFont(self._font)
        p.setBrush(QColor(theme.DARK["bg2"]))
        p.setPen(QPen(QColor(theme.DARK["accent"]), 1.4))
        p.drawRoundedRect(rect, 3, 3)
        p.setPen(FG)
        p.drawText(rect, Qt.AlignCenter, self._num_buf)
        p.setBrush(Qt.NoBrush)

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

    def _draw_refs(self, p: QPainter):
        """M82: projected model contours — thin dashed violet (Fusion's
        projected-edge purple), never selectable, never solved."""
        if not getattr(self.model, "refs", None):
            return
        p.save()
        p.setPen(QPen(PROJ, 1.4, Qt.DashLine))
        for r in self.model.refs:
            pts = [self.w2s(float(x), float(y))
                   for x, y in np.asarray(r["pts"], float)]
            loop = pts + pts[:1] if r["closed"] else pts
            for a, b in zip(loop, loop[1:]):
                p.drawLine(a, b)
        p.restore()

    def _draw_entities(self, p: QPainter):
        sk = self.model.sketch
        r = self._last_result
        constrained = r is not None and r.converged and r.dof == 0
        solid_pen = QPen(FG if constrained else ACCENT, 1.7)
        constr_pen = QPen(CONSTR, 1.2, Qt.DashLine)
        for l in sk.lines:
            p.setPen(constr_pen if l.construction else solid_pen)
            p.drawLine(self.w2s(l.a.x, l.a.y), self.w2s(l.b.x, l.b.y))
        for ar in sk.arcs:
            p.setPen(constr_pen if ar.construction else solid_pen)
            smp = ar.sample(64)
            q_prev = self.w2s(float(smp[0][0]), float(smp[0][1]))
            for xy in smp[1:]:
                qn = self.w2s(float(xy[0]), float(xy[1]))
                p.drawLine(q_prev, qn)
                q_prev = qn
        p.setPen(solid_pen)
        for c in sk.circles:
            p.setPen(constr_pen if getattr(c, "construction", False)
                     else solid_pen)
            cen = self.w2s(c.c.x, c.c.y)
            r = c.r * self._scale
            p.drawEllipse(cen, r, r)
        for e in sk.ellipses:
            p.setPen(constr_pen if getattr(e, "construction", False)
                     else solid_pen)
            cen = self.w2s(e.c.x, e.c.y)
            p.drawEllipse(cen, e.rx * self._scale, e.ry * self._scale)
        # selected
        p.setPen(QPen(SEL, 2.4))
        for e in self._sel:
            if isinstance(e, Line):
                p.drawLine(self.w2s(e.a.x, e.a.y), self.w2s(e.b.x, e.b.y))
            elif isinstance(e, Circle):
                cen = self.w2s(e.c.x, e.c.y)
                p.drawEllipse(cen, e.r * self._scale, e.r * self._scale)
            elif isinstance(e, Ellipse):
                cen = self.w2s(e.c.x, e.c.y)
                p.drawEllipse(cen, e.rx * self._scale, e.ry * self._scale)
            elif isinstance(e, Arc):
                smp = e.sample(64)
                q_prev = self.w2s(float(smp[0][0]), float(smp[0][1]))
                for xy in smp[1:]:
                    qn = self.w2s(float(xy[0]), float(xy[1]))
                    p.drawLine(q_prev, qn)
                    q_prev = qn
        # points
        for pt, _ in self._all_points():
            pos = self.w2s(pt.x, pt.y)
            selected = pt in self._sel
            p.setPen(QPen(SEL if selected else DIM, 1.2))
            p.setBrush(SEL if selected else BG)
            s = 3.8 if selected else 2.6
            p.drawRect(QRectF(pos.x() - s, pos.y() - s, 2 * s, 2 * s))
        p.setBrush(Qt.NoBrush)
        if self._snap_hint is not None:
            hx, hy = ((self._snap_hint.x, self._snap_hint.y)
                      if isinstance(self._snap_hint, Point)
                      else self._snap_hint)
            pos = self.w2s(hx, hy)
            p.setPen(QPen(INFER, 1.6))
            p.drawEllipse(pos, 7, 7)

    def _draw_glyphs(self, p: QPainter):
        font = p.font()
        p.setFont(self._font)
        sk = self.model.sketch
        for c in sk.constraints:
            if isinstance(c, Horizontal) and isinstance(c.line, Line):
                m = self.w2s((c.line.a.x + c.line.b.x) / 2,
                             (c.line.a.y + c.line.b.y) / 2)
                self._badge(p, m, "H", c=c)
            elif isinstance(c, Vertical) and isinstance(c.line, Line):
                m = self.w2s((c.line.a.x + c.line.b.x) / 2,
                             (c.line.a.y + c.line.b.y) / 2)
                self._badge(p, m, "V", c=c)
            elif isinstance(c, Fixed):
                m = self.w2s(c.p.x, c.p.y)
                self._badge(p, m, "\u25a0", c=c)   # ■
            elif isinstance(c, Symmetry):
                m = self.w2s((c.p1.x + c.p2.x) / 2, (c.p1.y + c.p2.y) / 2)
                self._badge(p, m, "S", c=c)
            elif isinstance(c, Midpoint):
                self._badge(p, self.w2s(c.p.x, c.p.y), "\u25c7", c=c)   # ◇
            elif isinstance(c, Tangent):
                pt = self._tangent_point(c)
                if pt is not None:
                    self._tangent_mark(p, pt)
            # Distance & Radius: no badge — the editable dimension label
            # from _draw_dimensions is the single indicator (as in
            # Fusion). Two glyphs for one value used to collide
            # ("26.00" drawn over a stale "26").
        p.setFont(font)

    def _tangent_point(self, c: Tangent):
        """World point where the two entities touch (screen via w2s)."""
        from ..core.sketch.constraints import _split_line_curve
        l, cv = _split_line_curve(c.e1, c.e2)
        if l is not None:                       # line touches curve
            d = np.array([l.b.x - l.a.x, l.b.y - l.a.y])
            ln = np.linalg.norm(d)
            if ln < 1e-12:
                return None
            t = d / ln
            cx, cy = curve_center(cv)
            s = (cx - l.a.x) * t[0] + (cy - l.a.y) * t[1]   # project centre
            return self.w2s(l.a.x + t[0] * s, l.a.y + t[1] * s)
        c1x, c1y = curve_center(c.e1)            # curve touches curve
        c2x, c2y = curve_center(c.e2)
        dx, dy = c2x - c1x, c2y - c1y
        dist = math.hypot(dx, dy)
        if dist < 1e-12:
            return None
        ux, uy = dx / dist, dy / dist
        r1 = curve_radius(c.e1)
        if not c.internal:                      # contact between centres
            return self.w2s(c1x + ux * r1, c1y + uy * r1)
        sign = 1.0 if r1 >= curve_radius(c.e2) else -1.0
        return self.w2s(c1x + ux * r1 * sign, c1y + uy * r1 * sign)

    def _tangent_mark(self, p: QPainter, at: QPointF):
        p.setPen(QPen(ACCENT, 1.4))
        p.setBrush(BG)
        p.drawEllipse(at, 3.4, 3.4)
        p.setBrush(Qt.NoBrush)

    def _radius_pos(self, e, dist: float = 16.0) -> QPointF:
        """Editable dimension anchor: top of a full circle, or the bulge
        point of an arc — the spot the maker actually drew, wherever the
        arc sits on its circumcircle."""
        if isinstance(e, Arc):
            c0, _r = e.circle()
            dx, dy = e.m.x - c0[0], e.m.y - c0[1]
            ln = math.hypot(dx, dy) or 1.0
            s = self.w2s(e.m.x, e.m.y)
            return QPointF(s.x() + dx / ln * dist, s.y() - dy / ln * dist)
        cen = self.w2s(e.c.x, e.c.y)
        return QPointF(cen.x(), cen.y() - e.r * self._scale - dist + 4)

    @staticmethod
    def _angle_pivot(c):
        """World vertex the angle arc is drawn around (None if unknown)."""
        if isinstance(c, Angle):
            return c.line.a.x, c.line.a.y
        return _line_pivot(c.l1, c.l2)

    def _angle_arc_pts(self, c, ring: int = 0):
        """Arc polyline + label anchor for an angular dimension. The arc
        spans the CURRENT geometry (Fusion behaves the same: the witness
        follows the line, the badge shows the constraint value). ring
        staggers stacked arcs that share a vertex."""
        scale = self._scale
        if scale <= 1e-9:
            return None
        r = (24.0 + 16.0 * ring) / scale               # world → px radii
        if isinstance(c, Angle):
            ln = c.line
            px, py = ln.a.x, ln.a.y
            a0, a1 = 0.0, math.atan2(ln.b.y - py, ln.b.x - px)
        else:
            p = _line_pivot(c.l1, c.l2)
            if p is None:
                return None                          # parallel, unshared
            px, py = p
            a0 = math.atan2(c.l1.b.y - py, c.l1.b.x - px)
            a1 = math.atan2(c.l2.b.y - py, c.l2.b.x - px)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi    # short way
        n = max(8, int(abs(da) / 0.18))
        pts = [self.w2s(px + r * math.cos(a0 + da * i / n),
                        py + r * math.sin(a0 + da * i / n))
               for i in range(n + 1)]
        mid = a0 + da * 0.5
        lab = r + 18.0 / scale
        return pts, self.w2s(px + lab * math.cos(mid), py + lab * math.sin(mid))

    def _draw_arc(self, p: QPainter, pts):
        p.setPen(QPen(DIMC, 1))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)

    def _badge(self, p: QPainter, at: QPointF, text: str, wide=False,
               c=None):
        w = 20 if wide else 13
        rect = QRectF(at.x() - w / 2, at.y() - 8, w, 15)
        fill = QColor(theme.rgba(theme.DB[".350"], 200))
        if c is not None:                 # M87: diagnosed constraints glow
            if id(c) in self._conflicting:
                fill = QColor(theme.rgba(theme.ERROR, 210))    # conflict red
            elif id(c) in self._redundant:
                fill = QColor(theme.rgba(theme.WARNING, 210))  # amber
        p.setPen(QPen(DIM, 1))
        p.setBrush(fill)
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
        if self._tool == "arc" and self._arc_pts:
            cur = self.mapFromGlobal(self.cursor().pos())
            wp = self._world(QPointF(cur))
            p.setPen(QPen(ACCENT, 1.2, Qt.DashLine))
            if len(self._arc_pts) == 1:
                a = self._arc_pts[0]
                p.drawLine(self.w2s(a.x, a.y), self.w2s(*wp))
            elif len(self._arc_pts) == 2:
                a, b = self._arc_pts
                tmp = Arc(a, Point(float(wp[0]), float(wp[1])), b)
                smp = tmp.sample(48)
                q_prev = self.w2s(float(smp[0][0]), float(smp[0][1]))
                for xy in smp[1:]:
                    qn = self.w2s(float(xy[0]), float(xy[1]))
                    p.drawLine(q_prev, qn)
                    q_prev = qn
        if self._tool == "slot" and self._slot:
            cur = self.mapFromGlobal(self.cursor().pos())
            wp = self._world(QPointF(cur))
            p.setPen(QPen(ACCENT, 1.2, Qt.DashLine))
            if len(self._slot) == 1:
                x1, y1 = self._slot[0]
                p.drawLine(self.w2s(x1, y1), self.w2s(*wp))
            else:
                x1, y1 = self._slot[0]
                x2, y2 = self._slot[1]
                dx, dy = x2 - x1, y2 - y1
                L = math.hypot(dx, dy)
                if L > 1e-9:
                    r = abs((wp[0] - x1) * dy - (wp[1] - y1) * dx) / L
                    nx, ny = -dy / L * r, dx / L * r
                    for (px, py) in ((x1, y1), (x2, y2)):
                        s = self.w2s(px, py)
                        p.drawEllipse(s, r * self._scale, r * self._scale)
                    p.drawLine(self.w2s(x1 + nx, y1 + ny),
                               self.w2s(x2 + nx, y2 + ny))
                    p.drawLine(self.w2s(x1 - nx, y1 - ny),
                               self.w2s(x2 - nx, y2 - ny))
        if self._tool == "poly" and self._poly:
            cur = self.mapFromGlobal(self.cursor().pos())
            wp = self._world(QPointF(cur))
            cx, cy = self._poly[0]
            r = math.hypot(wp[0] - cx, wp[1] - cy)
            if r * self._scale > 2:
                rot = math.atan2(wp[1] - cy, wp[0] - cx)
                n = self._poly_n
                p.setPen(QPen(ACCENT, 1.2, Qt.DashLine))
                p.drawEllipse(self.w2s(cx, cy), r * self._scale,
                              r * self._scale)
                vs = [self.w2s(cx + r * math.cos(rot + 2 * math.pi * i / n),
                               cy + r * math.sin(rot + 2 * math.pi * i / n))
                      for i in range(n)]
                for i in range(n):
                    p.drawLine(vs[i], vs[(i + 1) % n])
        if not self._preview:
            return
        kind, a, b = self._preview
        p.setPen(QPen(ACCENT, 1.4, Qt.DashLine))
        if kind == "rect":
            p.drawRect(min(a[0], b[0]), max(a[1], b[1]),
                       abs(b[0] - a[0]), abs(b[1] - a[1]))
        elif kind == "ellipse":
            cen = self.w2s(a[0], a[1])
            p.drawEllipse(cen, abs(b[0] - a[0]) * self._scale,
                          abs(b[1] - a[1]) * self._scale)
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
            lines.append((f"X {cx:.2f}   Y {cy:.2f} mm", HUD))
        tool = {"select": ("Select · L/R/C/A/Y/K draw · H/V/F/D/Q/T "
                           "constraints · Enter finish · . on-curve"),
                "line": "Line — click points, Enter/Esc stops",
                "rect": "Rectangle — drag corners or click · move · click",
                "circle": "Circle — drag from center or click · move · click",
                "ellipse": "Ellipse — drag from centre or click · move · "
                           "click (radii follow the cursor)",
                "arc": "Arc — 3 clicks: start · end · bulge (chains)",
                "slot": "Slot — 3 clicks: centre · centre · width",
                "poly": "Polygon — click centre · click vertex · "
                        "3-9 sides"}
        lines.append(("Tool: " + tool.get(self._tool, "?"), HUD))
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
