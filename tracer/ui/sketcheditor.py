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
                           QPen, QPolygonF, QWheelEvent)
from PySide6.QtWidgets import QApplication, QWidget

from ..core.sketch.constraints import (Angle, AngleBetween, Collinear,
                                       Concentric, Distance, Equal, Fixed,
                                       Horizontal, Midpoint, Perpendicular,
                                       PointOnCircle, PointOnLine, Radius,
                                       Symmetry, Tangent, Vertical,
                                       make_angle, make_angle_between,
                                       make_tangent, snapped, speaks_dia)
from ..core.sketch.entities import (Arc, Circle, Ellipse, Line, Point,
                                     curve_center, curve_radius)
from ..core.sketch.model import (_dim_tag, SketchModel, math_dist,
                                 model_from_dict, model_to_dict)
from ..core.sketch.profile import regions
from ..core.sketch.solver import _eligible, find_removable
from ..core import snaps
from . import cmdpanel, dimedit, theme
from .cmddialog import Shell
from .commands import SKETCH_KEYS

# keys the canvas owns (M113): plain printables from the command table,
# claimed from Qt's shortcut-override system so the global layer can't
# steal them; anything else bubbles to the window's model dispatch
_CLAIM_TEXT = {c.lower() for c in SKETCH_KEYS
               if "+" not in c and c not in ("Enter", "Esc")}

# the HUD's voice per tool (M169 R1: split out of _draw_hud so "the surfaces
# speak" is a TESTED claim - trim joining the family exposed a "Tool: ?")
TOOL_HINTS = {
    "select": ("Select · L/R/C/A/Y/K draw · H/V/F/D/Q constraints · "
               "Enter finish · . on-curve"),
    "trim": "Trim — click a piece or scribe across pieces to cut (T)",
    "line": "Line — click points, Enter/Esc stops",
    "rect": "Rectangle — drag corners or click · move · click",
    "circle": "Circle — drag from center or click · move · click",
    "ellipse": "Ellipse — drag from centre or click · move · "
               "click (radii follow the cursor)",
    "arc": "Arc — 3 clicks: start · end · bulge (chains)",
    "slot": "Slot — 3 clicks: centre · centre · width",
    "poly": "Polygon — click centre · click vertex · 3-9 sides",
}

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

CHAIN_TOOLS = ("line", "rect", "circle", "arc",            # M176: the
               "ellipse", "slot", "poly")                  #  chain verbs
HOVER = QColor(theme.SKETCH["hover"])       # M164 R2: constraint-hover ring

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
    dim_edited = Signal(object)                # M165 R3: a chip COMMITTED
    #   (what ran, not what was attempted) - the window notes the ring
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
        self._drag_pt_start: np.ndarray | None = None  # M173 R3: the
        self._dim_drag: tuple | None = None       # M174 R1: a LABEL is
        self._dim_pushed = False                  #  being dragged
        self._dim_place = None                    # M175 R2: a NEWBORN
        #   dimension follows the CURSOR (FD5-L35) until a press places
        #   it and the value field opens; Esc unbirths it.
        self._dbl_exit: tuple | None = None       # M176 R1 (L26): the
        #   timestamp+pos of a chain-exit DblClick; the press-2 a real
        #   platform sends afterwards is swallowed within the interval.
        self._check_hit: QRectF | None = None     # M176 R2 (L26): the
        #   green-check affordance's rect (end the chain, KEEP the tool);
        #   painted only while a chain tool is armed.
        self._drag: tuple | None = None        # M167 R1: body drag
        #   (pts, starts, anchor_world) — the delta law's record
        self._pend_toggle = None               # M167 R3: Ctrl-press on a
        #   SELECTED member defers the toggle: release = deselect (today),
        #   motion = photocopy the selection instead (the copy-drag law).
        self._trim_arm = None                  # M168 R3: the trim TOOL:
        self._trim_hover = None                #   press arm / hover piece
        self._corner = None                    # M172 R1: the ROUNDING
        self._corner_pull = False              #   HAND: [kind,l1,l2,P,r]
        self._corner_buf = ""                  # M172 R3: its OWN typed
        self._corner_typed = False             #   mouth (not M90's)
        self._trim_last = None                 # M169 R3: the STROKE: last
        self._trim_done: set = set()           #   probe point, inert ids
        self._trim_stroke = False              #   held-drag flag + the one
        self._trim_pushed = False              #   snapshot the gesture pays
        self._pan_from: QPointF | None = None
        self._pan_travel = 0.0                 # M173 R1: a CLICK is a
        self._line_start: Point | None = None  #   drag that never moved
        self._line_typed = ""                  # M180 R2: the pre-mint cell
        self._line_angle = ""                  # M180 R3: its angle twin
        self._line_cell = "len"                #  Tab toggles WHICH one
        self._rect_corner: np.ndarray | None = None
        self._arc_pts: list[Point] = []       # 3-pt tool: start, end, bulge
        self._preview: tuple | None = None  # tool drag preview
        self._band: list | None = None      # select marquee (2 QPoints)
        self._snap_hint: Point | tuple | None = None
        self._snap_obj = None                    # M120: typed Snap (glyph)
        self._placed_free = True                 # L25: _place_point verdict
        self._no_snap = False                    # M120: Alt suppresses snaps
        self._snap_grid = bool(QSettings().value("sketch/grid_snap",
                                                 False, type=bool))
        self._last_result = None
        self._dim_hits: list = []
        self._constraint_hits: list = []     # M164 R2: (rect, constraint)
        self._hover_c = None                 # constraint under the cursor
        self._dim_edit = None                # M165 R1: open chip editor
        self._last_dim = None                # M165 R1: rung-3 seed
        self._show_dof = False            # M119: degrees-of-freedom overlay
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        f = QFont()
        f.setPointSize(9)
        self._font = f

    # ---- model attach ---------------------------------------------------
    def set_model(self, model: SketchModel):
        self._close_dim_editor()   # M165: a swapped model means a dead chip
        self.model = model
        self._sel = []
        self._line_start = None
        self._line_reset()                     # M180 R2/R3: cells die with
        #                                       the  model they were typed into
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
        self._close_dim_editor()   # M165: never type into a pre-jump object
        tmp = model_from_dict(d)
        # keep THIS model's identity: sid links features to their sketch
        self.model.sketch = tmp.sketch
        self.model.refs = tmp.refs              # projected edges undo too
        self.model.dim_exprs = tmp.dim_exprs    # M89 fx bindings undo too
        self._pending = None                    # M90: type-ins don't survive
        self._num_buf = ""                      # a history jump
        self._sel = []
        self._drag_pt = None
        self._drag_pt_start = None                 # M173 R3: the leash
        self._dim_drag = None                      # M174 R1: label grips
        self._dim_place = None                     # M175 R2: place mode
        self._drag = None                      # M167 R1: grabs don't
        self._pend_toggle = None               # M167 R3: Ctrl-presses die
        self._line_start = None                #   survive a history jump
        self._line_reset()                     # M180 R2/R3:  neither do the
        #                                       half-typed  pre-mint cell
        self._rect_corner = None
        self._arc_pts = []
        self._slot: list = []                  # slot tool: c1, c2, width
        self._poly: list = []                  # polygon tool: centre, vertex
        self._preview = None
        self._solve()
        self.update()

    def set_tool(self, tool: str):
        if self._dim_place is not None and tool != self._tool:
            self._cancel_dim_place()        # M175 R2: walking to another
        #                    tool unbirths the un-placed dimension; a
        #                    REDUNDANT same-tool call never kills a live
        #                    gesture (no re-entrancy guard exists here).
        self._tool = tool
        if tool != "line":
            self._line_start = None
            self._line_reset()                 # M180 R2/R3: a swapped tool
        #                    never inherits a half-typed cell
        self._rect_corner = None
        self._arc_pts = []
        self._slot: list = []                  # slot tool: c1, c2, width
        self._poly: list = []                  # polygon tool: centre, vertex
        self._trim_arm = None                  # M168 R3: the trim tool's
        self._trim_hover = None                #   click-arm / piece preview
        self._trim_last = None                 # M169 R3: stroke state dies
        self._trim_done = set()                #   with the tool switch
        self._trim_stroke = False
        self._trim_pushed = False
        self._corner = None                    # M172 R1: the rounding
        self._corner_pull = False              #  hand dies with the tool
        self._corner_buf = ""                  # M172 R3: and so does
        self._corner_typed = False             #  the typed mouth
        self._preview = None
        self._band = None
        self._snap_hint = None
        self._snap_obj = None                    # M120: stale magnet glyph
        self._hover_c = None                     # M164 R2: stale ring dies
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
            for e in self.model.sketch.arcs + self.model.sketch.ellipses:
                pts += [(float(s[0]), float(s[1]))          # M173 R1:
                        for s in e.sample(24)]              #  the curve's
            for p in self.model.sketch.points:              #  own pixels
                pts.append((p.x, p.y))                      #  + lone pts
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
        """The typed magnet (M120): every kind core/snaps.py knows —
        endpoints, intersections, midpoints, quadrants, centres — with
        projected refs, the origin and (when toggled) grid points as
        minted extras.  Returns the reusable Point, an (x, y) to mint,
        or None; the full Snap lands in _snap_obj for the glyph."""
        self._snap_obj = None
        if self._no_snap:                        # Alt = suppress, always
            return None
        wp = self._world(q)
        tol = _HIT_PX / max(self._scale, 1e-6)
        extra = [(0.0, 0.0, "origin")]
        for r in getattr(self.model, "refs", []):       # M82: projected
            for x, y in np.asarray(r["pts"], float):    # edges magnetize
                extra.append((float(x), float(y), "reference"))
        if self._snap_grid:
            s = self._grid_step()
            extra.append((round(wp[0] / s) * s, round(wp[1] / s) * s,
                          "grid"))
        sn = snaps.best(self.model.sketch, wp[0], wp[1], tol, extra=extra,
                        skip=skip)
        self._snap_obj = sn
        if sn is None:
            return None
        return sn.pt if sn.pt is not None else (sn.x, sn.y)

    def _place_point(self, q: QPointF) -> Point:
        """_snap_target made real: reuse the existing Point, or mint it
        — and bind the mint to what the snap IMPLIED (live auto-constrain,
        free; theirs is batch and premium-gated [ui_sketchmode])."""
        t = self._snap_target(q)
        if isinstance(t, Point):
            self._placed_free = False            # L25 (M177 R3): identity
            return t                             #  IS coincidence - AND
        #                                        EXISTING geometry
        pt = self.model.point(*(t if t is not None else self._world(q)))
        sn = self._snap_obj
        self._placed_free = True                 # empty-space/origin/grid
        if t is not None and sn is not None and sn.pt is None:
            for c in snaps.autolink(sn, pt):     #  mints ride free; a
                c.src = "snap"                   #   DROP that autolinks
                self.model.sketch.constraints.append(c)
                self._placed_free = False        #   binds EXISTING
        return pt

    def _band_select(self, a: QPointF, b: QPointF, additive: bool):
        """M173 R2: the marquee learned its LEFT from its RIGHT - the
        real Fusion split. A left->right drag is a WINDOW: only
        geometry FULLY INSIDE is caught. A right->left drag is a
        CROSSING: everything it TOUCHES lands in the set (a vertical
        drag reads as a window: the >= law). The direction needs NO
        new state - it is written in the band's OWN stored endpoints.
        Ellipses - invisible to the marquee until today - ride both
        tests on their own samples, beside the arcs."""
        window = b.x() >= a.x()
        w0, w1 = self._world(a), self._world(b)
        lo = np.array([min(w0[0], w1[0]), min(w0[1], w1[1])])
        hi = np.array([max(w0[0], w1[0]), max(w0[1], w1[1])])

        def ins(xy):                             # tuple twin of _in_box
            return lo[0] <= xy[0] <= hi[0] and lo[1] <= xy[1] <= hi[1]

        sk = self.model.sketch
        found = []
        for p in sk.points:
            if _in_box(p, lo, hi):               # a point is its OWN
                found.append(p)                  #  whole bbox
        for ln in sk.lines:
            if window:
                if _in_box(ln.a, lo, hi) and _in_box(ln.b, lo, hi):
                    found.append(ln)
            elif _seg_hits_box((ln.a.x, ln.a.y), (ln.b.x, ln.b.y), lo, hi):
                found.append(ln)
        for c in sk.circles:
            if window:
                if (lo[0] <= c.c.x - c.r and c.c.x + c.r <= hi[0]
                        and lo[1] <= c.c.y - c.r and c.c.y + c.r <= hi[1]):
                    found.append(c)
            else:
                d = np.array([max(lo[0] - c.c.x, 0.0, c.c.x - hi[0]),
                              max(lo[1] - c.c.y, 0.0, c.c.y - hi[1])])
                dmin = float(np.hypot(*d))
                dmax = max(math.hypot(c.c.x - cx, c.c.y - cy)
                           for cx in (lo[0], hi[0]) for cy in (lo[1], hi[1]))
                if dmin <= c.r or dmax <= c.r:
                    found.append(c)
        for e in sk.arcs + sk.ellipses:          # the curve family:
            smp = [(float(s[0]), float(s[1]))    #  honest bboxes -
                   for s in e.sample(32)]        #   32 samples deep
            if window:
                if all(ins(xy) for xy in smp):
                    found.append(e)
            elif (any(ins(xy) for xy in smp)
                  or any(_seg_hits_box(smp[i], smp[i + 1], lo, hi)
                         for i in range(len(smp) - 1))):
                found.append(e)
        if additive:
            for e in found:
                if e not in self._sel:
                    self._sel.append(e)
        else:
            self._sel = found

    def _draw_band(self, p: QPainter):
        if self._band is None:
            return
        crossing = self._band[1].x() < self._band[0].x()   # M173 R2: the
        col = (QColor(theme.SKETCH["marquee_x"]) if crossing
               else ACCENT)                                #  band WEARS
        p.setPen(QPen(col, 1.0, Qt.DotLine))               #  its meaning
        p.setBrush(QColor(col.red(), col.green(), col.blue(), 28))
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

    def _dof_of(self, p: Point) -> int:
        """M167 R1: local mobility from the LAST solve's witness
        (M119 point_dof). No witness = fail OPEN to the old law."""
        res = getattr(self, "_last_result", None)
        dof = getattr(res, "point_dof", {}).get(p.id)
        return 2 if dof is None else int(dof)

    def _grab_points(self, ent) -> list:
        """M167 R1: the points a body drag translates. A line carries
        both ends; an arc all three defining points (SAME delta each →
        a rigid slide, chord & sagitta invariant); circles and ellipses
        their centre — radius/axes are scalars, so the SHAPE rides the
        move. Deduped by id: chain corners are one shared Point."""
        if isinstance(ent, Point):
            return [ent]
        if isinstance(ent, Line):
            pool = (ent.a, ent.b)
        elif isinstance(ent, Arc):
            pool = (ent.a, ent.b, ent.m)
        else:                                   # circle / ellipse
            pool = (ent.c,)
        seen, out = set(), []
        for p in pool:
            if id(p) not in seen:
                seen.add(id(p))
                out.append(p)
        return out

    def _commit_copy_drag(self):
        """M167 R3: a Ctrl-press on a selected member MOVED — the deferred
        deselect dies and the selection is PHOTO COPIED under the hand.
        Ghosts are minted at the originals' spots, then ride rung 1's delta
        law as an ordinary crowd grab; the ORIGINALS never enter the drag
        set. A ghost never magnetizes onto ITS OWN NEGATIVE: the skip crowd
        covers ghost + source points AND entities — without the source
        points a 1-px first move snaps the ghost back onto its source
        endpoint (delta' = -delta: the copy could never leave); without the
        source entities it clamps to the stale curve (rung 1's onentity
        hazard, one level deeper). Copies arrive FREE (no constraints,
        Fusion law) and BORN FREE: the dof-0 refusal does not filter a
        ghost — nothing resists a photocopy."""
        src = list(self._sel)
        _, anchor = self._pend_toggle            # the world at PRESS: the
        self._pend_toggle = None                 #  grab offset dates from there
        self._push_hist()
        copies = self.model.copy_geometry(src)
        pts, seen = [], set()
        for c in copies:
            for p in self._grab_points(c):
                if id(p) not in seen:
                    seen.add(id(p))
                    pts.append(p)
        skip = copies + src
        for e in src:
            skip += self._grab_points(e)        # the negative's POINTS too
        self._drag = (pts, np.array([[p.x, p.y] for p in pts]),
                      anchor, skip)
        self._drag_pushed = True                # history was made at arm
        self._sel = copies                      # the copy is the pick now
    def mousePressEvent(self, ev: QMouseEvent):
        self._no_snap = bool(ev.modifiers() & Qt.AltModifier)
        if (ev.button() == Qt.LeftButton
                and self._pending is not None):        # M90: new stroke
            self._pending = None                       # drops the type-in
            self._num_buf = ""
        if self.model is None:
            return
        q = ev.position()
        if ev.button() in (Qt.MiddleButton, Qt.RightButton):
            if (ev.button() == Qt.RightButton
                    and self._dim_place is not None):  # M178 R2 (FD5-
                c = self._dim_place                    #  L35): right-
                self._dim_place = None                 #  click BEFORE
                pos = self._dim_anchor_screen(c)       #  placing: the
                if pos is not None:                    #  newborn LANDS
                    qm = ev.position()                 #  HERE - the
                    c.label_off = ((qm.x() - pos.x()) / self._scale,   #
                                   -(qm.y() - pos.y()) / self._scale)  #
                c.driven = True                        #  ghost's OWN
                self._solve()                          #  formula - and
                self.update()                          #  arrives
                return                                 #  DRIVEN from
                #                                       birth: it
                #                                       REPORTS, so the
                #                                       editor STAYS SHUT
            if ev.button() == Qt.RightButton and self._tool == "select":
                self._context_menu(ev)
                return
            self._pan_from = q                 # M173 R1: the pan half
            self._pan_travel = 0.0             #  of the middle button
            return                             #  starts its travel count
        if ev.button() != Qt.LeftButton:
            return
        if self._dbl_exit is not None:                      # M176 R1
            qt, qp = self._dbl_exit                         #  (L26): the
            self._dbl_exit = None                           #  press-2 a
            if (ev.timestamp() - qt                         #   real platform
                    <= QApplication.instance()              #   sends AFTER
                    .doubleClickInterval()                  #   its DblClick
                    and (q - qp).manhattanLength() <= 6):   #  is a GHOST -
                return                                      #  the act is
            #                                               #  already over
        if self._chain_armed() and self._chain_check_rect().contains(q):
            #  M176 R2 (L26): a press on the GREEN CHECK ends the chain but
            #  KEEPS the tool. The rect is computed LIVE (same formula the
            #  painter uses - one post, no stale hit-list, paint-independent).
            self._finish_chain()
            return
        if self._dim_place is not None:                     # M175 R2: PLACE
            c = self._dim_place                           #  claims EVERY
            self._dim_place = None                        #   left press,
            lo = getattr(c, "label_off", None)            #   UNDER ANY
            near = lo is not None and (                   #   TOOL (the
                max(abs(lo[0]), abs(lo[1]))               #   pending act
                * self._scale < 2.0)                      #   owns the
            if near:                                      #   next click -
                c.label_off = (0.0, 0.0)                  #   m165's tool
            self._open_dim_editor(c)                      #   ledger says
            return                                        #   so itself)
        if self._tool == "select":
            if self._hover_c is not None:        # M164 R2: no ring while
                self._hover_c = None             # grabbing (viewport's law)
                self.setCursor(Qt.ArrowCursor)
            if self._corner is not None:         # M172 R1: the ROUNDING
                wp0 = self._world(q)             #  HAND: a press ON the
                P = self._corner[3]              #   aimed corner starts
                tol = 12.0 / max(self._scale, 1e-6)   #  the pull; a press
                if math.hypot(wp0[0] - P.x, wp0[1] - P.y) <= tol:
                    self._corner_pull = True     #   anywhere else VOIDS
                    self._corner_typed = False   #  a fresh grip gives
                    return                       #  the HAND the word
                self._corner = None              #   click carries on
            for rect, c in reversed(self._dim_hits):    # M174 R1: THE
                if rect.contains(q):             #  LABEL CLAIMS THE
                    self._dim_drag = (c, self._world(q),                #
                                      tuple(getattr(c, "label_off",     #
                                                    (0.0, 0.0))))  # A
                    self._dim_pushed = False     #  chip outranks the
                    return                       #   canvas beneath it
            hit = self._hit(q)
            if hit is None:
                if not (ev.modifiers() & Qt.ControlModifier):
                    self._sel = []          # plain click clears; Ctrl keeps
                self._band = [QPointF(q), QPointF(q)]   # drag = marquee
            elif ev.modifiers() & Qt.ControlModifier:
                if hit[1] in self._sel:
                    # M167 R3: Ctrl on a SELECTED member is a CLICK waiting
                    # to happen — the deselect defers to release; motion
                    # kills it and turns the hand into a photocopy instead.
                    self._pend_toggle = (hit[1], self._world(q))
                else:
                    self._sel.append(hit[1])   # a stranger joins at once
            else:
                e = hit[1]
                # M167 R2: THE SELECTION IS ONE HANDLE. Grabbing a member
                # of a MULTI selection drags the WHOLE selection (points
                # AND bodies); grabbing a stranger re-selects it alone —
                # universal CAD law. A lone selected point keeps rung 1's
                # absolute cursor law byte-exact (crowd=False at len 1).
                crowd = e in self._sel and len(self._sel) > 1
                members = list(self._sel) if crowd else [e]
                if not crowd:
                    self._sel = [e]
                movable, seen = [], set()
                for m in members:               # union, id-deduped;
                    for p in self._grab_points(m):   # locked members drop
                        if id(p) not in seen and self._dof_of(p) > 0:
                            seen.add(id(p))
                            movable.append(p)
                if hit[0] == "point" and not crowd:
                    if movable:
                        self._drag_pt = e
                        self._drag_pt_start = np.array([e.x, e.y])
                        self._drag_pushed = False
                elif movable:
                    # The record: (pts, starts, anchor, members) — moves
                    # are DELTAS, so the grab offset survives (no jump).
                    self._drag = (movable,
                                  np.array([[p.x, p.y] for p in movable]),
                                  self._world(q), members)
                    self._drag_pushed = False
            self.update()
            return
        if self._tool == "trim":                  # M168 R3: the trim TOOL
            hit = self._hit(q)                    #  (Fusion's T): a press
            self._trim_arm = hit[1] if hit else None   #  ARMS the entity
            self._trim_last = self._world(q)      #   under the cursor; the
            self._trim_done = set()               #   RELEASE does the cut,
            self._trim_stroke = False             #   a HELD MOVE starts the
            self._trim_pushed = False             #   scribe (M169 R3)
            return
        wp = self._world(q)
        if self._tool == "line":
            p = self._place_point(q)              # point/origin/grid magnet
            if self._line_start is None:
                self._line_start = p
            else:
                if p is self._line_start:
                    self._line_start = None          # close chain
                    self._line_reset()               # M180 R2/R3: cells too
                else:
                    self._push_hist()
                    if ev.modifiers() & Qt.ShiftModifier:      # M173
                        sx, sy = self._line_start.x, self._line_start.y
                        dx, dy = p.x - sx, p.y - sy            #  R3: a
                        if abs(dx) >= abs(dy) and dy != 0.0:   #  SECOND
                            p = self.model.point(p.x, sy)      #  click
                            self._placed_free = True           #  ORTHO -
                        elif abs(dy) > abs(dx) and dx != 0.0:  #  mints a
                            p = self.model.point(sx, p.y)      #  free end
                            self._placed_free = True           #  ONLY
                            # when the leash MOVES the magnet's answer;
                            # a shared snapped Point at an already-ortho
                            # spot is reused untouched - and stays the
                            # EXISTING point the L25 land rule reads.
                    tl, ta = self._line_cells()        # M180 R2/R3: the
                    hover_d = math.hypot(p.x - self._line_start.x,   #  cells
                                         p.y - self._line_start.y)   #  rule
                    d = ux = uy = None                 #  placement; plain
                    if tl is not None or ta is not None:             #  click
                        if ta is not None:
                            rad = math.radians(ta)
                            ux, uy = math.cos(rad), math.sin(rad)
                        elif hover_d > 1e-9:
                            ux = (p.x - self._line_start.x) / hover_d
                            uy = (p.y - self._line_start.y) / hover_d
                        else:
                            ux = uy = None
                        d = tl if tl is not None else hover_d
                        if ux is not None and d > 1e-9:
                            p = self.model.point(self._line_start.x + ux * d,
                                                 self._line_start.y + uy * d)
                    typed_d = d if (tl is not None or ta is not None) \
                        and ux is not None else None
                    self._line_reset()         #  the cells empty either way
                    ln = self.model.add_line(self._line_start, p)
                    self._auto_constraints(ln, q)
                    if ta is not None:         # a typed ANGLE is a REAL
                        self.model.remove_last(Angle, (ln,))     #  dim from
                        self.model.constrain(make_angle(ln, ta % 360.0))  #  birth
                    self._solve()
                    self._line_start = p
                    self._pending = ("line", ln)      # M90: type a length
                    self._pending_stage = 0
                    self._num_buf = ""
                    if typed_d is not None:    # the TYPED/derived length
                        self._num_buf = f"{typed_d:g}"   #  rides as the chip
                    #                                  number - the click
                    #  PLACED it; Enter now files it (M177's grammar)
                    if not self._placed_free:         # L25 (M177 R3):
                        self._line_start = None       #  the chain ENDS
                        #  on EXISTING geometry - the TOOL lives and
                        #  RE-ARMS: the next click is a fresh start.
                        #  A free end keeps chaining (Fusion's exact
                        #  free-point exception, inverted).
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
            self.model.constrain(Horizontal(ln),
                                 src="inferred")    # auto, offered last
        elif dx <= 3 and dy > 6:                    # near vertical
            ln.b.x = ln.a.x
            self.model.constrain(Vertical(ln),
                                 src="inferred")    # auto, offered last

    def mouseMoveEvent(self, ev: QMouseEvent):
        q = ev.position()
        self._no_snap = bool(ev.modifiers() & Qt.AltModifier)
        self._cursor = self._world(q)
        self.update()                    # keep the readout live
        if self._pan_from is not None:
            d = (q - self._pan_from)
            self._pan_travel += abs(d.x()) + abs(d.y())   # M173 R1:
            self._center -= np.array([d.x() / self._scale, -d.y() / self._scale])
            self._pan_from = q
            self.update()
            return
        if self._dim_place is not None:               # M175 R2: the ghost
            c = self._dim_place                       #  follows the FREE
            pos = self._dim_anchor_screen(c)          #  CURSOR (no button
            if pos is not None:                       #   held) until the
                qm = ev.position()                    #   press places it.
                c.label_off = ((qm.x() - pos.x()) / self._scale,
                               -(qm.y() - pos.y()) / self._scale)
                self.update()
            return
        if self._corner is not None and self._corner_pull:
            # M172 R1: the pull SIZES the ghost - r is the cursor's own
            # distance to the corner, clamped to the kernel's own max
            # (a pull can never outrun the legs; commit stays honest).
            kind, l1, l2, P, r = self._corner
            wp = self._world(q)
            g = self._corner_geom()
            if g is None:
                self._corner = self._corner_pull = None
            else:
                if not self._corner_typed:       # M172 R3: once the
                    _P, _o1, _o2, _u1, _u2, len1, len2, theta = g
                    rmax = math.tan(theta / 2.0) * (min(len1, len2)
                                                    / 2.0 - 0.02)
                    self._corner[4] = max(0.05, min(math.hypot(
                        wp[0] - P.x, wp[1] - P.y), rmax))
                self.update()                    # mouth spoke? then the
            return                               #  cursor just rides
        if self._dim_drag is not None:           # M174 R1: a LABEL is
            c, grab, lo0 = self._dim_drag        #  not GEOMETRY: raw
            if not self._dim_pushed:             #  delta, NO magnet,
                self._push_hist()                #   no solve, no
                self._dim_pushed = True          #    selection change
            wp = self._world(q)
            c.label_off = (lo0[0] + wp[0] - grab[0],
                           lo0[1] + wp[1] - grab[1])
            self.update()
            return                               #  chrome costs the
        if self._tool == "trim":                  # M168 R3: hover previews
            if ev.buttons() & Qt.LeftButton and self._trim_last is not None:
                # M169 R3: HELD LMB = the scribe. Past the click radius the
                # gesture is a STROKE, not an aim: hover dies, the segment
                # since the last probe eats whatever it crosses.
                w = self._world(q)
                if (np.hypot(*(w - self._trim_last)) * self._scale
                        > _HIT_PX):
                    self._trim_hover = None
                    self._trim_stroke = True
                    self._trim_scribe(self._trim_last, w)
                    self._trim_last = w
                self.update()
                return
            hit = self._hit(q)                    #  the WHOLE piece the
            self._trim_hover = None               #   click would take. The
            if hit is not None:                   #   question is READ-ONLY:
                from ..core.sketch.trim import piece_bounds   # nothing cuts
                e = hit[1]
                pb = piece_bounds(self.model, e, *self._world(q))
                if pb is not None:
                    bounds, t0, _c = pb
                    for i in range(len(bounds) - 1):
                        if bounds[i] <= t0 <= bounds[i + 1]:
                            self._trim_hover = (e, bounds[i], bounds[i + 1])
                            break
            self.update()
            return
        if self._tool == "select":
            if self._pend_toggle is not None:      # M167 R3: motion commits
                self._commit_copy_drag()           #  the Ctrl-press as a
            if self._drag_pt is not None:          #  COPY; this same move
                if not self._drag_pushed:          #  then rides the crowd
                    self._push_hist()
                    self._drag_pushed = True
                # dragged points CLICK onto origins, grid and other
                ortho = bool(ev.modifiers() & Qt.ShiftModifier)  # M173
                t = None if ortho else self._snap_target(        #  R3:
                    q, skip=self._drag_pt)     #  the LEASH outranks the
                if isinstance(t, Point):       # points, Fusion-style   #
                    wp = np.array([t.x, t.y])  #  MAGNET: no suggestion
                elif t is not None:            #  may bend a stated
                    wp = np.array(t)           #   constraint, so under
                else:                          #   Shift the magnet is
                    wp = self._world(q)        #    simply OFF
                if ortho and self._drag_pt_start is not None:    #  R3:
                    d = wp - self._drag_pt_start      #  the LEASH: the
                    if abs(d[0]) >= abs(d[1]):        #   dominant axis
                        wp = np.array([wp[0],         #   rules from the
                                       self._drag_pt_start[1]])    # grab
                    else:                             #   point (raw -
                        wp = np.array([self._drag_pt_start[0],     #  the
                                       wp[1]])        #   magnet slept)
                self._drag_pt.x, self._drag_pt.y = float(wp[0]), float(wp[1])
                self._solve(pins=[self._drag_pt])
                self._snap_hint = t
                self.update()
            elif self._drag is not None:
                if not self._drag_pushed:
                    self._push_hist()
                    self._drag_pushed = True
                pts, starts, anchor, ents = self._drag
                delta = self._world(q) - anchor
                hint = None
                ortho = bool(ev.modifiers() & Qt.ShiftModifier)
                if not ortho:                 # M173 R3: the LEASH
                    for s0 in starts:         #  outranks the MAGNET:
                        w = s0 + delta        #   under Shift no snap
                        t = self._snap_target(self.w2s(w[0], w[1]),
                                              skip=pts + list(ents))
                        if t is not None:                     #  the
                            tv = (np.array([t.x, t.y])       #  WHOLE
                                  if isinstance(t, Point)
                                  else np.asarray(t, float))  #  crowd
                            delta = delta + (tv - w)         #  (Fusion)
                            hint = t
                            break
                if ortho:                     #  R3: the dominant axis
                    if abs(delta[0]) >= abs(delta[1]):   #  of the RAW
                        delta = np.array([delta[0], 0.0])   #  total
                    else:                     #  displacement rules the
                        delta = np.array([0.0, delta[1]])   #  whole drag
                for p, s0 in zip(pts, starts):
                    p.x, p.y = float(s0[0] + delta[0]), float(s0[1] + delta[1])
                self._solve(pins=pts)
                self._snap_hint = hint
                self.update()
            elif self._band is not None:
                self._band[1] = q
                self.update()
            else:                              # M164 R2: idle select hover
                hit = self._hover_hit(q)
                new = hit[1] if hit else None
                if new is not self._hover_c:   # identity, never __eq__:
                    self._hover_c = new        # twin constraints compare equal
                    self.setCursor(Qt.PointingHandCursor if new is not None
                                   else Qt.ArrowCursor)
                    self.update()              # ONE repaint per hover change
            return
        if self._tool != "select":
            # Fusion shows the magnet while you HOVER, not only mid-drag
            self._snap_hint = self._snap_target(q)
        if self._preview:
            wp = self._world(q)
            kind, start = self._preview[0], self._preview[1]
            self._preview = (kind, start, wp)
            self.update()

    def leaveEvent(self, ev):
        # M164 R2: cursor gone, ring gone - no ghost (viewport's law).
        # Offscreen never synthesizes Leave; real pointers do.
        if self._hover_c is not None:
            self._hover_c = None
            self.setCursor(Qt.ArrowCursor if self._tool == "select"
                           else Qt.CrossCursor)    # same law as set_tool
        if self._trim_hover is not None:             # M168 R3: the piece
            self._trim_hover = None                  #  preview dies too
        self._trim_last = None                       # M169 R3: a Leave ends
        self._trim_stroke = False                    #  the stroke where the
        self._trim_done = set()                      #   pointer left the room
        super().leaveEvent(ev)

    def _trim_scribe(self, a, b):
        """M169 R3: one SEGMENT of a held stroke eats everything it
        crosses. Samples ride the click's OWN _hit grammar (world
        tolerance _HIT_PX/scale), so scribe and click speak one language;
        per new target trim_piece decides - ON-cut refusals hush (R2).
        An entity is touched ONCE per gesture: the touched object AND its
        split survivor (a half sharing one of its Points) join the inert
        set. The gesture keeps EXACTLY ONE history snapshot - popped when
        nothing fell, the zero-ambient law."""
        from ..core.sketch.trim import piece_bounds, trim_piece
        seg = b - a
        steps = max(2, int(np.hypot(float(seg[0]), float(seg[1]))
                           * self._scale / 3.0) + 1)
        touches = []
        seen = set()
        for k in range(steps + 1):
            w = a + seg * (k / steps)
            hit = self._hit(self.w2s(float(w[0]), float(w[1])))
            if hit is None:
                continue
            e = hit[1]
            if id(e) in self._trim_done or id(e) in seen:
                continue
            if piece_bounds(self.model, e, float(w[0]), float(w[1])) \
                    is None:
                self._trim_done.add(id(e))         # a Point: never trimmable
                continue
            seen.add(id(e))
            touches.append((e, float(w[0]), float(w[1])))
        if not touches:
            return

        def inert(e0):
            self._trim_done.add(id(e0))
            if isinstance(e0, (Line, Arc)):        # the survivor half is
                for cand in list(self.model.sketch.lines) + \
                        list(self.model.sketch.arcs):   #  BORN of this cut:
                    if e0.a in (cand.a, cand.b) or e0.b in (cand.a, cand.b):
                        self._trim_done.add(id(cand))   #  inert for the rest
        if self._trim_pushed:                      # gesture already paid
            for e, x, y in touches:
                trim_piece(self.model, e, x, y)   #  cuts without a second
                inert(e)                          #   snapshot
        else:
            self._push_hist()
            took = False
            for e, x, y in touches:
                if trim_piece(self.model, e, x, y) is not None:
                    took = True
                inert(e)
            if took:
                self._trim_pushed = True
            else:
                self._hist.pop()                   # took nothing: push nothing
        self._solve()
        self.update()

    def _weld_drop(self, grab, q):
        """IF IT SNAPPED, IT JOINED (M170 R2/R3): the magnet that CAUGHT a
        point-drag mid-flight becomes a REAL join at the drop - today it
        only promised pixel peace, and the next drag drifted the corner
        apart. Alt still suppresses (_no_snap rode the last sampled move).
        A catch on an EXISTING Point welds identity (rung 2); a drop onto
        a LINE/ARC BODY splits it reusing the dropped end as seam (rung
        3) - ONE Point serves stub, joint and both halves, the T-junction
        law of extend_end read backwards - but only when the point is a
        real END on some other entity: a free point (or a refused own-
        body drop) never mint topology. Every other kind lands EXACTLY
        what the draw tool's autolink table already promises for it
        (X->PointOnLine pair, circle/quadrant->PointOnCircle, midpoint->
        Midpoint), src="snap". Refusals HUSH. The join pays NO history of
        its own - it rides the drag's single snapshot - and it dismisses
        the magnet glyph: a kept promise stops advertising itself."""
        sk = self.model.sketch
        skip = [grab] + [e for e in sk.lines + sk.arcs       # M170 R3: the
                         if grab in                          #  release probe
                         (e.a, getattr(e, "m", None), e.b)]  #  rides over
        t = self._snap_target(q, skip=skip)                  #  its OWN stub
        if isinstance(t, Point) and t is not grab:
            sk = self.model.sketch
            for e in (list(sk.lines) + list(sk.arcs) + list(sk.circles)
                      + list(sk.ellipses) + list(sk.constraints)):
                g = sum(v is grab for v in vars(e).values())
                k = sum(v is t for v in vars(e).values())
                if g and k:                    # zero-collapse or a fact
                    self.update()              #  that names them APART
                    return
            from ..core.sketch.trim import weld_points
            try:
                weld_points(self.model, t, grab)
            except ValueError:
                self.update()
                return
            self._sel = [t if p is grab else p for p in self._sel]
            self._join_done()
            self._solve()
            self.update()
            return
        sn = self._snap_obj
        if sn is None or t is None:
            self.update()
            return
        carrier = sn.entity if sn.kind == "onentity" else None
        if isinstance(carrier, (Line, Arc)):
            def _ends(e):                      # real Points an entity rides
                return [x for x in (e.a, getattr(e, "m", None), e.b)
                        if x is not None]
            if grab in _ends(carrier):         # own-body drop: the line
                self.update()                  #  would eat itself - hush
                return
            if not any(grab in _ends(e) for e in
                       list(self.model.sketch.lines)
                       + list(self.model.sketch.arcs) if e is not carrier):
                carrier = None                 # a FREE point glues to the
        if carrier is not None:                #  body (table below), never
            from ..core.sketch.trim import split_entity   #  cuts it
            try:                               # T-JUNCTION: the dropped
                split_entity(self.model, carrier, grab.x, grab.y,
                             seam=grab)        #  end IS the seam - ONE
            except ValueError:                 #  Point serves stub, joint
                self.update()                  #  and both halves (M168
                return                         #  reuse law, backwards)
            self._join_done()
            self._solve()
            self.update()
            return
        joined = False

        def _rides(e):                        # a segment grab already ends
            return isinstance(e, (Line, Arc)) and grab in (
                e.a, getattr(e, "m", None), e.b)
        for c in snaps.autolink(sn, grab):     # the draw tool's OWN table:
            if any(_rides(e) for e in c.entities()):
                continue                      #  self-facts hush: a line
            c.src = "snap"                     #  cannot eat itself twice
            self.model.sketch.constraints.append(c)   #  scribe, drag and
            joined = True                     #  drop speak ONE language
        if joined:
            self._join_done()
            self._solve()
        self.update()

    def _join_done(self):
        self._snap_hint = None
        self._snap_obj = None                  # the CHIP is the glyph too:
                                               #  a kept promise dismisses it

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if ev.button() in (Qt.MiddleButton, Qt.RightButton):
            if (ev.button() == Qt.MiddleButton        # M173 R1: the
                    and self._pan_from is not None    #  middle CLICK is
                    and self._pan_travel <= 3.0):     #  Fusion's ZOOM
                self.fit_view()                       #  FIT; a DRAG was
                self.update()                         #  a PAN, and the
            self._pan_from = None                     #  right button
            return                                    #  never fits
        grab = self._drag_pt                    # M170 R2: remember WHOSE
        moved = grab is not None and self._drag_pushed   #  grab it was,
        self._drag_pt = None                    # M167 R1: a release ends
        self._drag_pt_start = None              #  M173 R3: leash state
        self._dim_drag = None                   #  M174 R1: label grips
        self._drag = None                       #  ANY grab, tool or no tool
        if self._tool == "trim":                 # M168 R3: the armed entity
            if self._trim_stroke:                # M169 R3: a stroke ends at
                self._trim_arm = None            #  the release - the aim is
                self._trim_last = None           #   spent and a drag that
                self._trim_stroke = False        #   took NOTHING pushes
                self._trim_done = set()          #   nothing
                return
            e, self._trim_arm = self._trim_arm, None    #  is CUT, never
            if e is None:                        #   dragged: release is the
                return                           #   commit, press is the aim
            self._trim_last = None
            self._trim_done = set()
            wx, wy = self._world(ev.position())
            from ..core.sketch.trim import extend_end, trim_piece
            self._push_hist()
            try:
                extend_end(self.model, e, wx, wy)
            except ValueError:
                gone = trim_piece(self.model, e, wx, wy)
                if gone is None:                 # ON a cut: refuse whole
                    self._hist.pop()             #  (no mutation happened)
                    self._warn("That click is ON a crossing - pick a side")
                    self.update()
                    return
            self._trim_hover = None
            self._solve(); self.update()
            return
        if self._tool == "select":
            if self._corner_pull:                # M172 R1: THE ROUNDING
                self._corner_pull = False        #  HAND files its cut
                self._corner_file()              #  (R3: same door Enter
                return                           #   knocks from the
                                                 #   keyboard side)
            if moved:                            # M170 R2: a point drag
                self._weld_drop(grab, ev.position())   #  that ENDED on a
                self._solve()                    #  magnet welds on drop.
                return                           #  M171 R2: a CLEAN settle
            if self._pend_toggle is not None:   # M167 R3: the Ctrl-press on
                e, _ = self._pend_toggle        #  a member never MOVED —
                self._pend_toggle = None        #  the deferred deselect
                if e in self._sel:              #  lands: today's law at
                    self._sel.remove(e)         #  the byte level
                self.update()
            elif self._band is not None:
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
        """M175 R1 (FD5-L35): the dimension is BORN of the geometry's
        own measurement and asks for its number IN-CANVAS - the modal
        dialog is dead. The remove_last habit survives (M90: re-dimming
        never stacks); the chip editor opens on the newborn (M165's
        door), so the whole pipeline is pick-dim-type-Enter without a
        panel. Dialect rides for free: a circle chip already speaks
        diameter and the commit does the honest halving."""
        tgt = None
        if len(self._sel) == 2 and all(isinstance(e, Point) for e in self._sel):
            p, q = self._sel
            self._push_hist()
            self.model.remove_last(Distance, (p, q))
            tgt = Distance(p, q, math_dist(p, q))
            self.model.constrain(tgt)
        elif len(self._sel) == 1:
            e = self._sel[0]
            if isinstance(e, Line):
                self._push_hist()
                self.model.remove_last(Distance, (e.a, e.b))
                tgt = Distance(e.a, e.b, math_dist(e.a, e.b))
                self.model.constrain(tgt)
            elif isinstance(e, (Circle, Arc)):
                self._push_hist()
                self.model.remove_last(Radius, (e,))
                tgt = Radius(e, curve_radius(e))
                self.model.constrain(tgt)
        if tgt is None:
            return
        self._solve()
        self._dim_place = tgt                   # M175 R2 (FD5-L35): the
        self.update()                           #  newborn FOLLOWS THE
        #               CURSOR until a press places it - the value
        #               field then opens on the placed chip (R1's door).

    def _cancel_dim_place(self):
        """M175 R2: Esc (or a real tool switch) ABORTS the act - the
        dimension never existed. The birth already paid one ledger row,
        so the unbirth spends it: undo_op pops the birth snapshot and
        the model is byte-for-byte what it was. Zero trace, both ends."""
        self._dim_place = None
        self.undo_op()

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
        """M175 R3 (FD5-L35): the angle is BORN speaking its own opening
        and asks for degrees IN-CANVAS - the LAST dim modal is dead. One
        line -> angle from +X; two lines -> angle between (Fusion pivots
        the arc at the shared/intersection point). snapped() is a branch
        picker, not a grid round, so birth-at-measurement never drags
        geometry. The newborn rides the R2 place rails: it follows the
        cursor, a press settles it (the field opens), Esc unbirths."""
        sel = self._sel
        tgt = None
        if len(sel) == 1 and isinstance(sel[0], Line):
            ln = sel[0]
            deg = math.degrees(math.atan2(ln.b.y - ln.a.y, ln.b.x - ln.a.x)) % 180
            self._push_hist()
            self.model.remove_last(Angle, (ln,))
            tgt = make_angle(ln, deg)
            self.model.constrain(tgt)
        elif len(sel) == 2 and all(isinstance(e, Line) for e in sel):
            l1, l2 = sel
            t1 = math.atan2(l1.b.y - l1.a.y, l1.b.x - l1.a.x)
            t2 = math.atan2(l2.b.y - l2.a.y, l2.b.x - l2.a.x)
            deg = math.degrees(t2 - t1) % 180
            self._push_hist()
            self.model.remove_last(AngleBetween, (l1, l2))
            tgt = make_angle_between(l1, l2, deg)
            self.model.constrain(tgt)
        if tgt is None:
            return
        self._solve()
        self._dim_place = tgt                     # the R2 rails take it
        self.update()                             #  from here

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
        hv = self._hover_c                         # M164 R3: right-click
        if hv is not None and self._is_fixable(hv):    # rides WITH the
            menu.addAction("Remove Constraint",    # hover (mousePress
                           lambda c=hv: self.act_remove_constraint(c))
            menu.addSeparator()                    # :427-429 clears not)
        if hv is not None and isinstance(hv, Radius):   # M174 R3 (FD5-
            menu.addAction("Toggle Radius / Diameter",  #  L35): a radial
                           lambda c=hv: self.act_dia(c))  #  chip speaks
                                                          #  EITHER way
        if hv is not None and isinstance(hv, (Distance, Radius)):
            menu.addAction("Make Driving" if getattr(hv, "driven",
                                                     False)
                           else "Make Driven",   # M178 R1 (FD5-L35): the
                           lambda c=hv: self.act_driven(c))  #  reference
                                                             #  toggle
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
            menu.addSeparator()
            dof = menu.addAction("Show degrees of freedom")
            dof.setCheckable(True)
            dof.setChecked(self._show_dof)
            dof.toggled.connect(self.set_show_dof)
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
        if getattr(self, "_dim_edit", None) is not None \
                and ev.type() == QEvent.Type.Paint:
            r = super().event(ev)            # paintEvent -> _dim_hits FRESH
            self._reseat()                   # field glued before stale shows
            return r
        if ev.type() == QEvent.Type.ShortcutOverride:
            mods = ev.modifiers()
            if not (mods & (Qt.ControlModifier | Qt.AltModifier
                            | Qt.MetaModifier)):
                txt = ev.text()
                if txt and txt.lower() in _CLAIM_TEXT:
                    ev.accept()
                    return True
        return super().event(ev)

    def _scroll_key(self, ev: QKeyEvent):
        """M171 R1: the empty-handed arrows are VIEW keys - the sketcher
        scrolls a screen-CONSTANT step (10 px worth of world, Shift x5).
        Nothing is modelled: the sketch and the history come out
        byte-identical - only the centre rides (and _center is THE view
        field, the M169 law: an alias here would be a silent no-op)."""
        step = 10.0 / max(self._scale, 1e-6)
        if ev.modifiers() & Qt.ShiftModifier:
            step *= 5.0
        k = ev.key()
        if k == Qt.Key_Left:
            self._center[0] -= step
        elif k == Qt.Key_Right:
            self._center[0] += step
        elif k == Qt.Key_Up:
            self._center[1] += step
        else:
            self._center[1] -= step
        self.update()

    def _nudge_key(self, ev: QKeyEvent):
        """THE NUDGE (M171 R2): a selection plus an arrow steps EVERY
        movable Point of the selection - the crowd's _grab_points + dof>0
        law, deduped by identity so a shared corner moves once - by a
        screen-CONSTANT 5 px of world (Shift x5), then solves with the
        moved points pinned: chains flex exactly as under a drag, because
        a nudge IS a drag with keyboard manners. EXACTLY one history
        snapshot per press that MOVES something; a scene that cannot move
        pays NOTHING - no undo row is born for a no-op (the M169
        zero-ambient law). Auto-repeat presses are consecutive undo
        steps: one press, one step (Fusion)."""
        k = ev.key()
        dx = (k == Qt.Key_Right) - (k == Qt.Key_Left)
        dy = (k == Qt.Key_Up) - (k == Qt.Key_Down)
        step = 5.0 / max(self._scale, 1e-6)
        if ev.modifiers() & Qt.ShiftModifier:
            step *= 5.0
        pts, seen = [], set()
        for e in list(self._sel):
            for p in self._grab_points(e):
                if id(p) not in seen and self._dof_of(p) > 0:
                    seen.add(id(p))
                    pts.append(p)
        if not pts:
            return                                 # locked scene: silence
        self._push_hist()
        for p in pts:
            p.x = float(p.x) + dx * step
            p.y = float(p.y) + dy * step
        self._solve(pins=pts)                      # the HAND holds (pins)...
        self._solve()                              #  ...then a CLEAN settle
        self.update()                              #  refreshes the witness:
                                                   #   a pinned solve truth-
                                                   #   fully says the pinned
                                                   #   had 0 dof - but the
                                                   #   NEXT press must find
                                                   #   the stepper mobile

    def _photocopy_key(self):
        """CTRL+D (M171 R3): the photocopy WITHOUT a hand - the same kernel
        the Ctrl+DRAG arms (:505), no gesture required. The selection is
        copied by copy_geometry (distinct points minted ONCE: identity
        survives - a shared corner copies shared), the copy lands ONE
        NUDGE STEP to the right so it is SEEN and grabbable beside its
        source, copies arrive FREE (no constraint rides - Fusion law) and
        BORN FREE (no dof filter - nothing resists a photocopy), the
        SELECTION re-homes to the copy (you keep working on what you
        made), and the whole act costs EXACTLY ONE undo row. Empty
        selection never reaches here: the key door hears the tool and the
        hands, and pays nothing it cannot charge."""
        self._push_hist()
        copies = self.model.copy_geometry(list(self._sel))
        step = 5.0 / max(self._scale, 1e-6)
        seen = set()
        for e in copies:
            for p in self._grab_points(e):
                if id(p) not in seen:
                    seen.add(id(p))
                    p.x += step
        self._solve()                              # originals were kept;
        self._sel = copies                         #  the copy is the pick
        self.update()

    # ---- M172: the ROUNDING HAND (fillet & chamfer follow the drag) ----

    def _corner_arm(self, kind: str, l1: Line, l2: Line) -> bool:
        """F/G AIM the corner: the kernel's OWN validator is asked first
        (every refusal it can raise - no shared point, a corner three
        geometries share, near-parallel legs - surfaces as the canvas
        warning it already words, and NOTHING arms: a refused aim is
        byte-silent, no hist, no model touch). On success the state
        holds the LIVE entities, not coordinates: nudges and solves
        move the corner and the ghost rides it."""
        g = self._corner_geom(l1, l2, kind, warn=True)
        if g is None:
            return False
        _P, _o1, _o2, _u1, _u2, len1, len2, theta = g
        leg = min(len1, len2)
        default = max(0.5, round(min(5.0, leg / 4.0), 1))   # the dialog's
        rmax = math.tan(theta / 2.0) * (leg / 2.0 - 0.02)   #  own default
        self._corner = [kind, l1, l2, _P, min(default, rmax)]
        self._corner_pull = False
        self._corner_buf = ""                    # M172 R3: fresh aim,
        self._corner_typed = False               #  fresh mouth
        self.update()
        return True

    def _corner_geom(self, l1=None, l2=None, kind="fillet", warn=False):
        """Live, READ-ONLY revalidation through the kernel's _corner:
        every arm/ghost/pull question is answered against TODAY's
        geometry, and a corner that died under the aim (trimmed,
        welded, deleted) answers None - the aim dies with it, SILENT
        per-frame; only the ARM refusal speaks (warn=True)."""
        if l1 is None:
            if self._corner is None:
                return None
            kind, l1, l2 = self._corner[0], self._corner[1], self._corner[2]
        from ..core.sketch.fillet import _corner as _ck
        try:
            return _ck(self.model, l1, l2, kind)
        except ValueError as e:
            if warn:
                self._warn(str(e))
            return None

    def _corner_ghost(self) -> list:
        """The preview arc at the aimed corner, computed with the
        KERNEL's OWN fillet geometry at the state's r - paint only, the
        model is never touched (the same sentence the trim hover lives
        by). Returns world tuples, or [] when the corner went stale."""
        if self._corner is None:
            return []
        kind, l1, l2, _P, r = self._corner
        g = self._corner_geom()
        if g is None:
            return []
        P, _o1, _o2, u1, u2, len1, len2, theta = g
        if kind != "fillet":                       # R2 grows the flat
            return [(P.x + u1[0] * r, P.y + u1[1] * r),
                    (P.x + u2[0] * r, P.y + u2[1] * r)]
        tan_len = r / math.tan(theta / 2.0)
        t1 = (P.x + u1[0] * tan_len, P.y + u1[1] * tan_len)
        t2 = (P.x + u2[0] * tan_len, P.y + u2[1] * tan_len)
        cd = r / math.sin(theta / 2.0)
        hx, hy = u1[0] + u2[0], u1[1] + u2[1]
        hl = math.hypot(hx, hy)
        bx, by = hx / hl, hy / hl
        cen = (P.x + bx * cd, P.y + by * cd)
        bul = (cen[0] - bx * r, cen[1] - by * r)
        a1 = math.atan2(t1[1] - cen[1], t1[0] - cen[0])
        a2 = math.atan2(t2[1] - cen[1], t2[0] - cen[0])
        ab = math.atan2(bul[1] - cen[1], bul[0] - cen[0])
        TAU = 2.0 * math.pi
        ccw = (a2 - a1) % TAU
        delta = ccw if (ab - a1) % TAU <= ccw else -(TAU - ccw)
        return [(cen[0] + r * math.cos(a1 + delta * i / 23.0),
                 cen[1] + r * math.sin(a1 + delta * i / 23.0))
                for i in range(24)]

    def _corner_file(self) -> bool:
        """FILE whatever the arm holds - the release and the Enter key
        knock on this ONE door: ONE history row, the kernel's own
        refusal POPs it (took nothing = paid nothing), the cut becomes
        the pick, and the aim is spent. Returns True when it filed."""
        corner, self._corner, self._corner_buf = self._corner, None, ""
        if corner is None:
            return False
        kind, l1, l2, _P, r = corner
        self._push_hist()
        from ..core.sketch.fillet import corner_chamfer, corner_fillet
        try:
            made = (corner_fillet(self.model, l1, l2, r)
                    if kind == "fillet"
                    else corner_chamfer(self.model, l1, l2, r))
        except ValueError as e:
            self._hist.pop()
            self._warn(str(e))
            self.update()
            return False
        self._solve()
        self._sel = [made]                       # the cut is the pick
        self.update()
        # M179 R1 (FD5-L30): a FILLET ships with a permanent radius dim,
        # and the moment the corner is rounded its input box AUTO-OPENS -
        # Fusion asks the number on placement, in the SAME editor a
        # hand-placed dim uses (so M178's driven-guard + settle-first ride
        # for free). The newborn is found by IDENTITY on the arc, NEVER by
        # list position: the kernel appends Radius THEN ArcMiddle, so a
        # positional read would open the wrong chip. A CHAMFER is a flat
        # Line with no radius, so it keeps its silence.
        if kind == "fillet":
            rr = next((cc for cc in reversed(self.model.sketch.constraints)
                       if isinstance(cc, Radius) and cc.curve is made), None)
            if rr is not None:
                self._open_dim_editor(rr)
        return True

    def _corner_rmax(self) -> float:
        """The legs' own answer to 'how big?' - the kernel's numbers,
        live (0.0 when the corner died under the aim)."""
        g = self._corner_geom()
        if g is None:
            return 0.0
        _P, _o1, _o2, _u1, _u2, len1, len2, theta = g
        return math.tan(theta / 2.0) * (min(len1, len2) / 2.0 - 0.02)

    def _corner_type_key(self, k: int):
        """THE TYPE-IN RIDE (M172 R3): while the rounding hand is armed,
        digits feed the CORNER'S OWN buffer - two verbs must not share
        one mouth (M90's _num_buf belongs to the dimmer, and this hook
        only fires when nothing is pending, so every digit that was
        rightfully the dimmer's stays its own). Enter files the EXACT
        typed number with NO MOUSE: the mouth outruns the hand (typed
        text replaces a pull in flight; the cursor afterwards just
        rides). Empty buffer + Enter commits the ghost's own number -
        the default, or the pulled radius. Garbage WARNS and the ARM
        STAYS ALIVE: a typo is not a cancelled verb. And the number
        must still fit the legs - steel is steel for the mouth too."""
        if k in (Qt.Key_Return, Qt.Key_Enter):
            buf = self._corner_buf
            if not buf:
                self._corner_file()              # the ghost's own number
                return
            try:
                v = float(buf)
            except ValueError:
                self._warn(f'"{buf}" is not a number')
                return
            rmax = self._corner_rmax()
            if v <= 0.0:
                self._warn("The cut needs a positive number")
                return
            if v > rmax:
                self._warn(f"Too large for these legs (max {rmax:.2f})")
                return
            self._corner[4] = v                  # typed text OUTRANKS
            self._corner_file()                  #  the pull: one door
            return
        if k == Qt.Key_Backspace:
            self._corner_buf = self._corner_buf[:-1]
        elif k == Qt.Key_Period:
            if "." not in self._corner_buf:
                self._corner_buf += "."          # one mouth, one point
        else:
            self._corner_buf += chr(k)           # Key_0..9 == '0'..'9'
        self._corner_typed = True                # the mouth has the floor
        try:                                     # the ghost rides every
            v = float(self._corner_buf)          #  honest keystroke...
            if 0.0 < v <= self._corner_rmax():
                self._corner[4] = v
        except ValueError:                       # ...and a half-typed
            pass                                 #  "2.." moves nothing
        self.update()

    def keyPressEvent(self, ev: QKeyEvent):
        k = ev.key()
        if self.model is None:
            return super().keyPressEvent(ev)
        if k == Qt.Key_F2:                         # M165 R2: the KEYBOARD
            target = self._chip_under_cursor()     #  door to the chip -
            if target is not None:                 #  deliberately NOT in
                self._open_dim_editor(target)      #   SKETCH_KEYS (F2 is
                return                             #   non-printable: a
                                                   #   claim would be
                                                   #   inert dead code)
        if (self._tool == "line" and self._pending is None
                and self._line_start is not None):
            # M180 R2 (FD5-L23): the rubber-band carries a live TYPE-IN
            # CELL - the same numeric grammar M90 runs AFTER the commit,
            # now voiced BEFORE it. Documented Fusion law (staff, forum
            # 11459066): typing feeds the length cell, a CLICK places at
            # the typed length, ENTER places AND ends, Esc surrenders the
            # NUMBER but keeps the drag alive.
            txt = ev.text()
            cell = self._line_angle if self._line_cell == "ang" \
                else self._line_typed
            if txt.isdigit() or txt == "." or (
                    self._line_cell == "ang" and txt == "-"):
                if len(cell) < 12:
                    if self._line_cell == "ang":
                        self._line_angle = cell + txt
                    else:
                        self._line_typed = cell + txt
                self.update()
                return
            if k == Qt.Key_Backspace:
                if self._line_cell == "ang":
                    self._line_angle = cell[:-1]
                else:
                    self._line_typed = cell[:-1]
                self.update()
                return
            if k in (Qt.Key_Return, Qt.Key_Enter):
                if self._line_typed or self._line_angle:
                    self._place_typed_line()
                self.set_tool("select")        #  ENTER = (place and) DONE
                return
            if k == Qt.Key_Tab:                # M180 R3 (FD5-L23): the
                self._line_cell = ("ang" if self._line_cell == "len"
                                   else "len")  #  staff law - Tab TOGGLES
                self.update()                  #   the two live cells
                return
            if k == Qt.Key_Escape:             # M180 R3: Esc frees the
                if self._line_cell == "ang" and self._line_angle:
                    self._line_angle = ""      #   LIVE CELL only - the
                    self.update()              #    other keeps its
                    return                       #   number, the DRAG
                if self._line_cell == "len" and self._line_typed:   #    lives
                    self._line_typed = ""
                    self.update()
                    return
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
                # M177 R1 (L24): Enter COMMITS AND ENDS - and the END
                # comes at the END of the ENTRY SEQUENCE: a staged rect's
                # width-Enter leaves the lock ADVANCED (m90's two-number
                # grammar, FD5-L29's mid-command W/H entry) and stays in
                # the command; the commit that CLEARS the lock - line/
                # circle/arc, and a rect's height - is the one that ENDS
                # it, handing the canvas back to select.
                # (select-mode commits - M90's own stage - stay inert.)
                if self._pending is None and self._tool in CHAIN_TOOLS:
                    self.set_tool("select")
                return
            if k == Qt.Key_Tab:                      # M177 R2 (L24): Tab
                if self._num_buf:                    #  is Enter's COMMIT-
                    self._commit_typed()             #  AND-CONTINUE twin -
                self.update()                        #  the number files,
                return                               #  the command STAYS
                #  ARMED (a staged rect stays mid-walk; even the FINAL
                #  commit keeps the tool - that is the whole contrast
                #  with Enter). Swallowing Tab while a lock lives also
                #  saves the canvas from FOCUS TRAVERSALS mid-gesture:
                #  before this branch Tab was unclaimed and could hand
                #  the whole editor the boot. FD5-L23's length+angle
                #  field-cycling is the [observed] sibling - deferred.
            if k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
                self._scroll_key(ev)               # M171 R1: view keys
                return                             #  neither eat digits
            if k == Qt.Key_Escape:                 # M176 R3 (L27): Esc NEAR
                if self._num_buf:                  #  the LOCK HONORS the
                    self._commit_typed()           #  number - the typed
                self._pending = None               #  length PERSISTS (the
                self._pending_stage = 0            #  very solver act Enter
                self._num_buf = ""                 #  performs)...
                self.update()
                return                             #  ...and ONLY the lock
                                                   #   icon goes out. The
                                                   #   COMMAND survives:
                                                   #   the next Esc ends it
                                                   #   (L26's cascade, below)
            self._pending = None                    # any other key lets go
            self._num_buf = ""                      # ...and is still heard
        if k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            if not self._sel:                      # M171 R1: EMPTY HANDS
                self._scroll_key(ev)               #  make VIEW keys
            elif self._tool == "select":           # M171 R2: HANDS FULL
                self._nudge_key(ev)                #  in select mode the
            return                                 #  SAME keys NUDGE
        sel = self._sel
        if k == Qt.Key_Escape:
            if self._dim_place is not None:               # M175 R2: the
                self._cancel_dim_place()                  #  cascade's
                return                                    #  FIRST rung:
            self._line_start = None                       #  an un-placed
            self._line_reset()                 # M180 R2/R3: the cells go out
            self.set_tool("select")                       #  dimension
            return                                        #  UNBIRTHS it
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
        if k == Qt.Key_D and ev.modifiers() & Qt.ControlModifier:
            if self._tool == "select" and self._sel:   # M171 R3: the
                self._photocopy_key()                  #  photocopy WITH
            return                                     #  NO hand - and
                                                       #  never the plain
                                                       #  D's dim either
        if self._corner is not None and self._pending is None \
                and (Qt.Key_0 <= k <= Qt.Key_9
                     or k in (Qt.Key_Period, Qt.Key_Backspace,
                              Qt.Key_Return, Qt.Key_Enter)):
            self._corner_type_key(k)             # M172 R3: the numeral
            return                               #  is TYPE-ABLE - the
                                                 #   corner's OWN mouth,
                                                 #   behind M90's door
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
        elif k == Qt.Key_T:
            # M168 R3: T is the trim TOOL (Fusion). The two-line corner
            # act this key used to run MIGRATED to the menu, the palette
            # and direct act_trim() calls - the key now only arms the
            # mode; pressing T again lays it down. Shift+T (tangent) is
            # handled above and untouched.
            self.set_tool("select" if self._tool == "trim" else "trim")
        elif k == Qt.Key_Return and self._tool in CHAIN_TOOLS:
            # M177 R1 (L24): Enter ENDS THE DRAW COMMAND. The law that
            # once guarded the line alone now keeps every chain verb -
            # rect/circle/arc/ellipse/slot/poly return to select too.
            self._line_start = None
            self._line_reset()                 # M180 R2/R3: quiet the cells
            self.set_tool("select")
        elif k == Qt.Key_Return:
            self.finish()                         # Finish Sketch: Enter
            return
        elif k == Qt.Key_X:
            self.act_construction()               # Fusion: X toggles
        elif k == Qt.Key_Delete:
            if not sel and self._cursor is not None:     # M181 R1 (L32):
                qp = self.w2s(*self._cursor)             #  EMPTY hands +
                chip = next((c for r, c in reversed(     #   a DIM CHIP
                    getattr(self, "_dim_hits", []))      #   under the
                    if r.contains(qp)), None)            #  CURSOR: Delete
                if chip is not None:                     #  eats THE DIM,
                    self.act_remove_constraint(chip)     #   not the
                    return                               #   geometry.
            self.act_delete()
        elif k == Qt.Key_H:
            self.act_H()
        elif k == Qt.Key_V:
            self.act_V()
        elif k == Qt.Key_F:
            if len(sel) == 2 and all(isinstance(e, Line) for e in sel):
                self._corner_arm("fillet", sel[0], sel[1])
            else:                                # M172 R1: canvas F is
                self.act_fix()                   #  the HAND now (aim,
                                                 #   pull, file); the
                                                 #   dialog lives on ONE
                                                 #   door: menu Fillet...
        elif k == Qt.Key_G and len(sel) == 2 and \
                all(isinstance(e, Line) for e in sel):
            self._corner_arm("chamfer", sel[0], sel[1])
                                                 # M172 R2: the SAME hand
                                                 #  files the FLAT cut
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
            self._draw_hover(p)                # M164 R2: ring + re-stroke
            if self._tool == "trim":             # M168 R3: the piece the
                self._draw_trim_piece(p)         #   click WOULD take
            if self._corner is not None:         # M172 R1: the rounding
                self._draw_corner_ghost(p)       #  hand's arc rides the
            if self._show_dof:                    # M119: the DOF overlay
                self._draw_dof(p)
            self._draw_typein(p)              # M90: the live number chip
            self._draw_preview(p)
            if self._chain_armed():            # M176 R2 (L26): the GREEN
                self._draw_chain_check(p)      #  CHECK ends the chain but
            else:                              #  KEEPS the tool armed -
                self._check_hit = None         #  painted on top, last.
        self._draw_band(p)
        self._draw_hud(p)
        p.end()

    # ---- M119: the degrees-of-freedom overlay ------------------------------
    def set_show_dof(self, on: bool):
        """The toggle Fusion's forums begged for and its UI never gave
        (kernel report §3): show WHERE a sketch can still move, not just
        that it can."""
        self._show_dof = bool(on)
        if self._show_dof and self.model:
            self._solve()                     # fresh kinematics to draw
        self.update()

    def _draw_dof(self, p: QPainter):
        res = self._last_result
        if res is None or not getattr(res, "point_dof", None):
            return
        L = 15.0                                   # arrow reach, px
        pen = QPen(ACCENT, 1.6)
        p.setPen(pen)
        for ent in self._dof_points():
            d = res.point_dof.get(ent.id, 0)
            if not d:
                continue
            at = self.w2s(ent.x, ent.y)
            dirs = []
            dx, dy = res.free_dirs.get(ent.id, (1.0, 0.0))
            nrm = (dx * dx + dy * dy) ** 0.5 or 1.0
            dirs.append((dx / nrm, dy / nrm))
            if d >= 2:                             # cross of two directions
                dirs.append((-dy / nrm, dx / nrm))
            for ux, uy in dirs:
                tip = self.w2s(ent.x + ux * L / max(self._scale, 1e-6),
                               ent.y + uy * L / max(self._scale, 1e-6))
                p.drawLine(at, tip)                # double-ended: motion
                p.drawLine(at, self.w2s(ent.x - ux * L / max(self._scale, 1e-6),
                                        ent.y - uy * L / max(self._scale, 1e-6)))
                self._arrow_head(p, at, tip)
                self._arrow_head(p, at, self.w2s(
                    ent.x - ux * L / max(self._scale, 1e-6),
                    ent.y - uy * L / max(self._scale, 1e-6)))

    @staticmethod
    def _arrow_head(p: QPainter, frm, to):
        import math as _m
        v = to - frm
        ln = (v.x() ** 2 + v.y() ** 2) ** 0.5
        if ln < 6:
            return
        ux, uy = v.x() / ln, v.y() / ln
        from PySide6.QtCore import QPointF
        a = 5.0
        p.drawLine(to, QPointF(to.x() - a * (ux * 0.866 - uy * 0.5),
                               to.y() - a * (uy * 0.866 + ux * 0.5)))
        p.drawLine(to, QPointF(to.x() - a * (ux * 0.866 + uy * 0.5),
                               to.y() - a * (uy * 0.866 - ux * 0.5)))

    def _dof_points(self):
        """Every value-carrying point the solver may have analysed."""
        sk = self.model.sketch
        out = []
        for ln in sk.lines:
            out += [ln.a, ln.b]
        for c in sk.circles:
            out.append(c.c)
        for a in sk.arcs:
            out += [a.a, a.m, a.b]
        for e in sk.ellipses:
            out.append(e.c)
        out += list(sk.points)
        seen, uniq = set(), []
        for q in out:
            if q.id not in seen:
                seen.add(q.id)
                uniq.append(q)
        return uniq

    def dof_summary(self) -> str:
        res = self._last_result
        if res is None or not getattr(res, "point_dof", None):
            return "no sketch"
        free = sum(1 for v in res.point_dof.values() if v)
        return f"{free} free point{'s' if free != 1 else ''}, {res.dof} dof"

    def select_underconstrained(self):
        """M164 R2 chip click: pick every point the solve says can still
        move.  Reads the cached M119 point_dof - zero new solve, zero new
        hit-test (the one-round-trip law)."""
        res = self._last_result
        if res is None or not getattr(res, "point_dof", None):
            return
        self._sel = [q for q in self._dof_points()
                     if res.point_dof.get(q.id, 0) > 0]
        self.update()

    def select_blamed(self):
        """M164 R2 chip click on the warning: select the geometry of the
        blamed constraints.  Rung 2 SELECTS; the remove-one finder is
        rung 3's sentence."""
        res = self._last_result
        if res is None:
            return
        out = []
        for c in getattr(res, "conflicting", []) or []:
            for e in c.entities():
                if not any(e is oo for oo in out):     # identity dedup
                    out.append(e)
        if out:
            self._sel = out
            self.update()

    # ---- M164 R3: the fixer ----------------------------------------------

    def describe_constraint(self, c) -> str:
        """Combo row text, 'Distance 26.00 mm · line 2'.  DISPLAY ONLY -
        twins print identical rows, so the finder's payload is the INDEX
        in the frozen candidate list, never this string (the D3 handle
        law made concrete)."""
        t = type(c).__name__
        if isinstance(c, (Angle, AngleBetween)):
            v = f" {math.degrees(c.value) % 180:.2f}\u00b0"
        elif isinstance(c, (Distance, Radius)):
            v = f" {c.value:.2f} mm"
        else:
            v = ""
        ent = " + ".join(self._ent_name(e) for e in c.entities())
        return f"{t}{v} \u00b7 {ent}"

    def _ent_name(self, e) -> str:
        """'line 2' = 1-based place in the owning list (identity walk,
        never __eq__); a point that owns no list falls back to the line
        end it welds, then to its class."""
        sk = self.model.sketch
        for name, seq in (("line", sk.lines), ("circle", sk.circles),
                          ("arc", sk.arcs), ("point", sk.points)):
            i = next((j for j, x in enumerate(seq) if x is e), -1)
            if i >= 0:
                return f"{name} {i + 1}"
        for i, ln in enumerate(sk.lines):
            if e in (ln.a, ln.b):
                return f"line {i + 1} end"
        return type(e).__name__.lower()

    def open_finder_panel(self, parent_win):
        """M164 R3: the chip's fixer.  ONE on-demand drop-one scan at
        open (never from _solve/paint/mouse - the structural grep gate
        pins that); the combo previews through rung 2's _hover_c
        (cosmetic, zero solve - the press-pull law); Commit removes by
        identity in ONE undo step.  Returns the panel, or None when
        nothing is nameable (the chip then keeps its rung-2 selection
        voice - never a dead click)."""
        res = self._last_result
        if res is None or not (getattr(res, "conflicting", [])
                               or getattr(res, "redundant", [])):
            return None
        rep = find_removable(res, self.model.sketch.constraints)
        if not rep.removable:
            return None
        box = {"cands": list(rep.removable), "panel": None,
               "reopened": False}
        fields = [dict(key="pick", kind="combo", label="Remove",
                       choices=[self.describe_constraint(c)
                                for c in box["cands"]], default=None)]
        if rep.timed_out:                       # D1: a partial says so
            fields.append(dict(
                key="note", kind="note", label="",
                text=f"{len(box['cands'])} listed \u2014 the scan stopped "
                     f"at its budget; more candidates may exist"))

        def _pick():
            p = box["panel"]
            w = p._edits["pick"] if p is not None else None
            i = w.currentIndex() if w is not None else -1
            return box["cands"][i] if 0 <= i < len(box["cands"]) else None

        def _preview(_vals):                    # cosmetic-only law
            c = _pick()
            self._hover_c = (c if c is not None and any(
                cc is c for cc in self.model.sketch.constraints) else None)
            self.update()

        def _abort_fix():
            self._hover_c = None                # ring dies, nothing else
            self.update()

        def _commit(_vals):
            c = _pick()
            if c is None:
                return
            if not any(cc is c for cc in self.model.sketch.constraints):
                self._abort_fix()               # stale pick: re-scan at
                if box["reopened"]:             # a fresh panel, never
                    return                      # delete a ghost twice
                box["reopened"] = True
                box["panel"] = None             # the nested run() has
                return self.open_finder_panel(parent_win)   # aborted this
            self._push_hist()                   # panel already
            self.model.remove_constraint(c)
            self._hover_c = None
            self._solve()                       # ONE undo step

        box["panel"] = cmdpanel.run(
            parent_win, "sketch_fix", "Remove to fix", fields,
            preview=_preview, commit=_commit, abort=_abort_fix,
            remember_key=False)                 # forgetful by law (R3)
        return box["panel"]

    def _is_fixable(self, c) -> bool:
        """Finder eligibility for the badge menu - the SAME solver law
        (rank order, welds/witnesses/structural srcs never nameable),
        so a structural badge never grows a Remove entry.  Cheap: no
        rank algebra, no scan."""
        return _eligible(c, {id(cc) for cc in
                             self.model.sketch.constraints}) is not None

    def act_dia(self, c):
        """M174 R3 (FD5-L35): the chip changes DIALECT, never magnitude.
        The stored value stays a radius - the solver never stirs; only
        the explicit override flips. ONE undo row, no re-solve."""
        if not any(cc is c for cc in self.model.sketch.constraints):
            return                              # stale: zero trace (m164)
        self._push_hist()
        c.dia = not speaks_dia(c)
        self.update()

    def act_driven(self, c):
        """M178 R1 (FD5-L35): DRIVEN = reference. The chip reports the
        live measurement; the solver never sees the row. Unlike act_dia
        (cosmetic dialect, solver asleep) the flip MUST re-solve. Note
        the round trip: while driven the chip QUOTED the walking
        geometry, so making it driving PINS WHERE IT READS - the old
        number is gone (Fusion semantics: converting re-pins the shown
        value) - and from then on the geometry must obey again."""
        if not any(cc is c for cc in self.model.sketch.constraints):
            return                              # stale: zero trace (m164)
        ed = getattr(self, "_dim_edit", None)   # M178 R3: the flip
        if ed is not None and ed.constraint is c:   #  settles ink
            self._close_dim_editor()            #  ownership first -
            #                                     the editor commands
            #                                     numbers; a reader has
            #                                     none to command
        self._push_hist()
        c.driven = not getattr(c, "driven", False)
        self._solve()
        self.update()

    def act_remove_constraint(self, c):
        """Badge right-click: straight through the finder's door -
        identity-guarded, ONE undo step, re-solve.  Same anatomy as the
        panel commit, which is why the menu needs no scan at all."""
        if not any(cc is c for cc in self.model.sketch.constraints):
            return                              # stale: zero trace
        self._push_hist()
        self.model.remove_constraint(c)
        self._hover_c = None                    # the ring's subject left
        self._solve()
        self.update()

    def _dof_hud_text(self) -> str:
        """M164 R1: the DOF line the HUD paints - dof_summary()'s contract
        byte-exact, plus the rank truth the solve now remembers
        '(rank r/m)'.  A helper, not inline paint code, so the gate can
        read the exact sentence without a QPainter."""
        r = self._last_result
        tail = (f" (rank {r.rank}/{len(r.rows)})"
                if r is not None and r.rank >= 0 and r.rows else "")
        return "DOF \u00b7 " + self.dof_summary() + tail

    # ---- dimension labels (double-click editable, Fusion-style) ------------
    def _dim_text(self, c) -> str:
        """The chip's wording: the DIALECT oracle (M174 R3) decides who
        speaks diameter - the stored value stays a radius either way.
        M178 R1: a DRIVEN quote wears PARENTHESES [obs: forum-verified];
        the painter routes EVERY Distance/Radius word through here."""
        if isinstance(c, Radius):
            text = (f"\u00d8 {2 * c.value:.2f}" if speaks_dia(c)
                    else f"R {c.value:.2f}")
        elif isinstance(c, Distance):
            text = f"{c.value:.2f}"
        else:
            text = ""
        if text and getattr(c, "driven", False):
            text = f"({text})"
        return text

    def _draw_dimensions(self, p: QPainter):
        self._dim_hits = []
        sk = self.model.sketch
        p.setFont(self._font)
        fm = p.fontMetrics()
        seen_pivots = []                 # screen pts of angle dims so far
        for ci, c in enumerate(sk.constraints):
            bound = ci in self.model.dim_exprs      # M89: fx-driven dims
            text = pos = None
            if isinstance(c, (Distance, Radius)):
                pos = self._dim_anchor_screen(c)  # M175 R2: painter and
                if pos is None:                   #  place mode read ONE
                    continue                      #   post (paint == hit)
                text = self._dim_text(c)          # M178 R1: ONE mouth -
                #                                  dialect, parens and the
                #                                  "\u00d8 on circles (M98)"
                #                                  all answer from here
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
            off = getattr(c, "label_off", None)  # M174 R1: the label
            if off:                              #  keeps its HOME -
                pos = QPointF(pos.x() + off[0] * self._scale,
                              pos.y() - off[1] * self._scale)
            rect = dimedit.chip_rect(fm, pos, text)   # shared with the seat
            ed = getattr(self, "_dim_edit", None)     #  (early-Paint law)
            if not (ed is not None and ed.constraint is c):   # M165 R1:
                p.setBrush(QColor(theme.DARK["bg2"]))  # the chip under
                dr = getattr(c, "driven", False)       # M178 R1: a driven
                p.setPen(QPen(QColor(theme.DARK["accent"]) if bound
                              else QColor(theme.DARK["fg_faint"] if dr
                                             else theme.DARK["accent_dim"]),
                              1))                      #  quote is a quiet
                p.drawRoundedRect(rect, 3, 3)          #  citizen: faint
                p.setPen(QColor(theme.DARK["fg_dim"]) if dr else FG)  # ring,
                #                                       dim ink
                p.drawText(rect, Qt.AlignCenter, text) #   field draws it
                p.setBrush(Qt.NoBrush)
            self._dim_hits.append((rect, c))     # hits ALWAYS: paint ==

    def _hover_hit(self, q: QPointF):
        """M164 R2: (rect, constraint) under the cursor - topmost wins.
        Badges paint over dim labels, so _constraint_hits answers first;
        within either list later appends were painted later, hence the
        reversed() walk.  The lists are per-paint; a move between paints
        rides <=1 frame-old rects - honest for a cosmetic-only consumer."""
        for hits in (self._constraint_hits, self._dim_hits):
            for rect, c in reversed(hits):
                if rect.contains(q):
                    return rect, c
        return None

    def mouseDoubleClickEvent(self, ev: QMouseEvent):
        q = ev.position()
        for rect, c in getattr(self, "_dim_hits", []):
            if rect.contains(q):
                self._open_dim_editor(c)           # M165 R2: every chip
                return                             #  kind, ONE door
        if self._tool in CHAIN_TOOLS:
            # FD5-L26 (M176 R1): a DOUBLE-CLICK ENDS THE CHAIN AND EXITS.
            # The count-1 press already drew its stroke - that is the last
            # segment the maker wanted; the act ENDS HERE, and the press-2
            # a real platform still sends arrives DEAD (guarded above).
            # set_tool washes every chain's arming; drawn geometry
            # SURVIVES.
            self._dbl_exit = (ev.timestamp(), QPointF(q))
            self.set_tool("select")
            return
        super().mouseDoubleClickEvent(ev)

    # ---- M176 R2 (L26): the green check ends the chain, KEEPS the tool ----
    def _chain_armed(self) -> bool:
        """Is a chain tool live with work in progress (a start point, a
        corner, or in-progress poly/arc/slot points)? The check glyph is
        painted only when this is true - a bare armed tool with nothing
        drawn yet has no chain to END."""
        if self._tool not in CHAIN_TOOLS:
            return False
        return (self._line_start is not None
                or self._rect_corner is not None
                or bool(getattr(self, "_poly", []))
                or bool(getattr(self, "_arc_pts", []))
                or bool(getattr(self, "_slot", [])))

    def _finish_chain(self):
        """FD5-L26 middle clause (M176 R2): the check mark ENDS THE CHAIN
        but LEAVES THE TOOL ARMED - the next click opens a FRESH chain, so
        the maker draws many lines without re-arming. Contrast the
        double-click (ends AND exits to select) and Esc (ends the command).
        Every committed stroke already stands on its own click, so ending
        means only: wash the pending arming + the number chip."""
        self._line_start = None
        self._line_reset()                     # M180 R2/R3: finish washes
        #                                       the  cell with the arming
        self._rect_corner = None
        self._poly = []
        self._arc_pts = []
        self._slot = []
        self._preview = None
        self._pending = None
        self._num_buf = ""
        self.update()

    def _chain_check_rect(self) -> QRectF:
        """The fixed top-right affordance (the SAME post the painter and
        the press claim read - one rectangle, three mouths)."""
        return QRectF(self.width() - 34, 10, 24, 24)

    def _draw_chain_check(self, p: QPainter):
        """A Fusion-style GREEN CHECK: a rounded success square with a
        dark tick, seated top-right while a chain is armed. Clicking it
        finishes the chain and KEEPS the tool (vs the double-click's
        end-AND-exit)."""
        rect = self._chain_check_rect()
        self._check_hit = rect
        p.save()
        p.setBrush(BG.darker(150))               # a neutral pressed-button
        p.setPen(QPen(BG.darker(240), 1))        #  square so the tick reads
        p.drawRoundedRect(rect, 4, 4)            #   green (Fusion's check)
        tick = QPen(OK)                          # the GREEN check itself
        tick.setWidthF(2.4)
        tick.setCapStyle(Qt.RoundCap)
        tick.setJoinStyle(Qt.RoundJoin)
        p.setPen(tick)
        cx, cy = rect.center().x(), rect.center().y()
        p.drawPolyline(QPolygonF([
            QPointF(cx - 6, cy + 0.5), QPointF(cx - 1.5, cy + 5),
            QPointF(cx + 6.5, cy - 5)]))
        p.restore()

    # ---- M165 R1: the inline chip editor (design m165_rung1_chipfield) ----
    def _open_dim_editor(self, c):
        if getattr(c, "driven", False):
            return                               # M178 R3 (FD5-L35): a
            #                                     READER cannot be
            #                                     commanded - the editor
            #                                     stays shut at EVERY
            #                                     door (dbl-click, F2,
            #                                     palette, _edit_dim):
            #                                     one gate, all mouths
        if self._dim_edit is not None:
            if self._dim_edit.constraint is c:   # same chip: just refocus
                self._dim_edit.edit.setFocus()
                return
            self._close_dim_editor()             # a new chip closes the
        self._pending = None                     #  last (one verb, one ed)
        self._num_buf = ""                       # M90: type-ins never
        self._hover_c = c                        #  coexist; rung-4's ring
        dimedit.open(self, c)                    #  marks what is being edited

    def _close_dim_editor(self):
        ed = self._dim_edit
        if ed is None:
            return                               # re-entrancy: every hook
        self._dim_edit = None                    #   tests this FIRST
        try:                                     # a DISCARD close must never
            ed.committed.disconnect()            #   commit through the
            ed.closeRequested.disconnect()       #   hide()-induced focus-out
        except (RuntimeError, TypeError):
            pass
        if self._hover_c is ed.constraint:       # the ring dies with the
            self._hover_c = None                 #  editor, rung-4 law
        ed.edit.clearFocus()
        ed.hide()
        ed.deleteLater()                         # null-then-deleteLater,
        fw = self.window().focusWidget() if self.window() else None
        if fw is None or fw is ed or fw is ed.edit or fw is self:
            self.setFocus()                      # the Esc ladder resumes

    def _on_chip_close(self):                    # Esc / unchanged Enter
        self._close_dim_editor()

    def _on_chip_commit(self, _mm):              # committed(float): the
        ed = self._dim_edit                      #  float is a validity
        if ed is None:                           #  witness, TEXT is input
            return
        c, text = ed.constraint, ed.edit.text()
        self._close_dim_editor()                 # close BEFORE mutating
        if not any(cc is c for cc in self.model.sketch.constraints):
            return                               # dead object: no audience
        self._apply_dim_edit(c, text)

    def _apply_dim_edit(self, c, text) -> bool:
        """M165 R1 (angles in, R2): the dim commit, headless-callable
        (the seam's target).  The panel-era semantics, ported whole:
        identity door first (a dead dim edits nobody), "=expr" binds
        (M89 - the prefix IS the old fx row, doc units x scale), a plain
        number RELEASES the binding, Ø halves on circles (M98), loud
        refusal strictly BEFORE any _push_hist, and the spin era's
        0.001..1e6 range restored on the plain path (a chip can clamp
        where the panel could not).  Angles: bare degrees, branch
        re-snap, never bind - the panel's angle leg retired here."""
        from ..core.params import ParamError, eval_expr
        i = next((j for j, cc in enumerate(self.model.sketch.constraints)
                  if cc is c), None)
        if i is None:                            # rung-3/4 identity law
            return False
        dia = dimedit.is_dia(c)
        t = str(text).strip()
        if dimedit.is_angle(c):                  # M165 R2: the panel's
            try:                                 #  last dim leg retired
                deg = dimedit.parse_degrees(t)   #  INTO the chip - bare
            except ParamError as e:              #  degrees only, no
                self._warn(str(e))               #  (M89 stays lengths-
                self.update()                    #   only)
                return False
            self._push_hist()
            # re-snap to the branch the geometry currently occupies, so
            # editing never flips the line through 180 deg (m24 law)
            c.value = snapped(c.measured(), math.radians(deg))
            self._last_dim = c                   # rung-3 seed (also here)
            self.dim_edited.emit(c)              #  the ring notes angles
            self._solve()                        #  too (M165 R3)
            self.update()
            return True
        expr = t.lstrip("=").strip() if t.startswith("=") else ""
        if expr:
            vals, sc = self._params_provider()   # fx: doc units x scale,
            try:                                 #  no units, no clamp
                newv = float(eval_expr(expr, vals)) * sc
            except ParamError as e:              #  (M89's old contract)
                self._warn(f"Binding refused: {e}")
                self.update()
                return False                     # the number stays honest
            self._push_hist()                    # strictly AFTER eval
            self.model.dim_exprs[i] = {"e": expr, "t": _dim_tag(c)}
            c.value = newv * 0.5 if dia else newv        # M98: "=expr" is Ø
        else:
            try:
                vals, _sc = self._params_provider()
                newv = dimedit.parse_scalar(t, vals)     # plain: NATIVE mm
            except ParamError as e:                      #  (the double-
                self._warn(str(e))                       #   scale trap: sc
                self.update()                            #   never touches
                return False                             #   this path)
            if not 0.001 <= newv <= 1e6:         # the restored spin range
                self._warn(f"Dimension out of range (0.001..1e6): {t!r}")
                self.update()
                return False
            self._push_hist()
            self.model.dim_exprs.pop(i, None)    # plain ON A BOUND dim =
            c.value = newv * 0.5 if dia else newv        #  release (M89)
        self._last_dim = c                       # rung-3 adjust-last seed
        self.dim_edited.emit(c)                  # M165 R3: note the ring
        self._solve()
        self.update()
        return True

    def _reseat(self):
        """Paint-derived geometry (plan law): runs from event() AFTER the
        frame that rebuilt _dim_hits - pan/zoom/solve all end in
        update(), so the field cannot lag the chip."""
        ed = self._dim_edit
        if ed is None:
            return
        rect = next((r for r, cc in self._dim_hits
                     if cc is ed.constraint), None)
        if rect is None:                         # chip gone this frame
            ed.edit.clearFocus()                 # focus-out: commits IF
            if not any(cc is ed.constraint       #  alive (shielded by
                       for cc in self.model.sketch.constraints):
                self._close_dim_editor()         #  _on_chip_commit's own
            return                               #   identity recheck)
        geom = rect.toRect().adjusted(-2, -2, 2, 2)          # chip + halo
        if geom != ed.geometry():                # MOVE-ONLY-IF-MOVED: the
            ed.setGeometry(geom)                 #   paint-loop guard
        ed.raise_()

    def _edit_dim(self, c):
        """M165 R2: EVERY chip kind edits inline now - the M164 R4
        panel's angle leg retired into the chip's degree grammar
        (dimedit.parse_degrees + the angle clause of _apply_dim_edit).
        The door stays for direct drivers (m24) and the palette."""
        self._open_dim_editor(c)

    def _chip_under_cursor(self):
        """F2's target (M165 R2): the chip whose rect owns the mouse
        point, else the last dim EDITED if it still lives (the rung-1
        _last_dim seed finally gets a consumer), else None - and then
        F2 is inert, like every verb without a selection."""
        if self._cursor is not None:
            s = self.w2s(*self._cursor)
            for rect, c in self._dim_hits:
                if rect.contains(s):
                    return c
        if self._last_dim is not None and any(
                cc is self._last_dim
                for cc in self.model.sketch.constraints):
            return self._last_dim
        return None

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

    def _line_live_text(self):
        """M180 R1 (FD5-L23): the rubber-band's live LENGTH reading - the
        anchor is set and the hover is elsewhere; None once the line mints
        (the pre-mint anchor dies with the commit) or when either end of
        the gesture is missing."""
        if self._tool != "line" or self._line_start is None \
                or self._cursor is None:
            return None
        if self._line_typed:                   # M180 R2 (FD5-L23): the
            return self._line_typed            #  TYPED cell outranks the
        import math                            #   recomputed hover reading
        L = math.hypot(self._cursor[0] - self._line_start.x,
                       self._cursor[1] - self._line_start.y)
        return f"{L:.2f}" if L > 1e-9 else None

    def _place_typed_line(self):
        """M180 R2/R3 (FD5-L23): the rubber-band PLACES at the typed
        length/angle - a missing cell rides the hover (typed LENGTH along
        the hover RAY; typed ANGLE at the hover LENGTH; both typed wins
        outright). The numbers survive as REAL parametric dimensions:
        Distance via M90's _commit_typed, Angle through the kernel's own
        make_angle mouth. ONE mouth serves click-place and Enter-place."""
        L, A = self._line_cells()
        ax, ay = self._line_start.x, self._line_start.y
        if self._cursor is None:
            self._line_reset()
            return
        hx, hy = self._cursor[0] - ax, self._cursor[1] - ay
        n = math.hypot(hx, hy)
        if A is not None:
            rad = math.radians(A)
            ux, uy = math.cos(rad), math.sin(rad)
        elif n > 1e-9:
            ux, uy = hx / n, hy / n
        else:
            self._line_reset()
            return
        d = L if L is not None else n
        if d <= 1e-9:
            self._line_reset()
            return
        self._push_hist()
        p = self.model.point(ax + ux * d, ay + uy * d)
        ln = self.model.add_line(self._line_start, p)
        self._auto_constraints(ln, self.w2s(*self._cursor))
        self._solve()
        if A is not None:
            self.model.remove_last(Angle, (ln,))
            self.model.constrain(make_angle(ln, A % 360.0))
            self._solve()
        self._line_reset()
        self._line_start = None                # placed: the drag is OVER
        self._pending = ("line", ln)
        self._pending_stage = 0
        self._num_buf = f"{d:g}"
        self._commit_typed()                   # M90's own mouth: the dim

    def _line_reset(self):
        """M180 R3: both pre-mint cells and the focus go dark together -
        the wash law: wherever the anchor dies, the cells die with it."""
        self._line_typed = ""
        self._line_angle = ""
        self._line_cell = "len"

    def _line_cells(self):
        """(typed length, typed angle deg) - None where the cell is blank
        or half-typed; the PLACEMENT fills those from the hover."""
        def one(s):
            if not s.strip("."):
                return None
            try:
                return float(s)
            except ValueError:
                return None
        L = one(self._line_typed)
        if L is not None and L <= 0:
            L = None
        return L, one(self._line_angle)

    def _line_live_angle(self):
        """M180 R3 (FD5-L23): the ray's angle in degrees, 0..360 from +X -
        the SAME convention the kernel's Angle.measured() speaks."""
        if self._tool != "line" or self._line_start is None \
                or self._cursor is None:
            return None
        if self._line_angle:
            return self._line_angle
        deg = math.degrees(math.atan2(
            self._cursor[1] - self._line_start.y,
            self._cursor[0] - self._line_start.x)) % 360.0
        return f"{deg:.1f}"

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
        sn = self._snap_obj                        # M120: typed magnet glyph
        if sn is not None:
            pos = self.w2s(sn.x, sn.y)
            p.setPen(QPen(INFER, 1.6))
            k = sn.kind
            if k in ("intersection",):             # ×  = exact crossing
                for dx, dy in ((6, 6), (6, -6)):
                    p.drawLine(QPointF(pos.x() - dx, pos.y() - dy),
                               QPointF(pos.x() + dx, pos.y() + dy))
            elif k in ("midpoint", "quadrant"):    # +  = marked station
                p.drawLine(QPointF(pos.x() - 6, pos.y()),
                           QPointF(pos.x() + 6, pos.y()))
                p.drawLine(QPointF(pos.x(), pos.y() - 6),
                           QPointF(pos.x(), pos.y() + 6))
            elif k == "grid":                      # ▫ = lattice
                p.drawRect(QRectF(pos.x() - 4, pos.y() - 4, 8, 8))
            elif k == "onentity":                  # ··· curve slide, small
                p.drawEllipse(pos, 4, 4)
            else:                                  # endpoint/centre/origin:
                p.drawEllipse(pos, 7, 7)           # the classic open ring
            f = p.font()
            f.setPointSize(7)
            p.setFont(f)
            p.drawText(QPointF(pos.x() + 9, pos.y() + 14), k.upper())
            p.setFont(self._font)
        elif self._snap_hint is not None:
            hx, hy = ((self._snap_hint.x, self._snap_hint.y)
                      if isinstance(self._snap_hint, Point)
                      else self._snap_hint)
            pos = self.w2s(hx, hy)
            p.setPen(QPen(INFER, 1.6))
            p.drawEllipse(pos, 7, 7)

    def _draw_glyphs(self, p: QPainter):
        self._constraint_hits = []                 # M164 R2: rebuilt per
        font = p.font()                            # paint, like _dim_hits
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
                    self._constraint_hits.append(   # M164 R2: the mark is
                        (QRectF(pt.x() - 5, pt.y() - 5, 10, 10), c))  # hot
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

    def _dim_anchor_screen(self, c):
        """M175 R2: the chip's DEFAULT post in screen pixels, computed by
        the SAME formula the painter uses (paint == hit == place law).
        None = degenerate (zero-length line) or no post for this kind."""
        if isinstance(c, Distance):
            d = QPointF(c.q.x - c.p.x, c.q.y - c.p.y)
            ln = math.hypot(d.x(), d.y())
            if ln < 1e-9:
                return None
            mid = self.w2s((c.p.x + c.q.x) / 2, (c.p.y + c.q.y) / 2)
            return QPointF(mid.x() + (-d.y() / ln) * 16,
                           mid.y() - (d.x() / ln) * 16)
        if isinstance(c, Radius):
            return self._radius_pos(c.curve)
        if isinstance(c, (Angle, AngleBetween)):
            arc = self._angle_arc_pts(c, 0)       # ring 0 = the natural
            return arc[1] if arc is not None else None   #  post of ONE
        return None                               #   angle in the scene

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
        if c is not None:                          # M164 R2: every badge
            self._constraint_hits.append((rect, c))  # is a hover target
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

    def _draw_corner_ghost(self, p: QPainter):
        """M172 R1: the ghost arc at the aimed corner - dashed accent,
        paint only (the model is untouched until the release FILES it).
        While armed a numeral rides beside the arc's bulge: the exact
        radius the release would commit (R3 makes typing replace it)."""
        pts = self._corner_ghost()
        if not pts:
            return
        p.setPen(QPen(ACCENT, 1.2, Qt.DashLine))
        q_prev = self.w2s(*pts[0])
        for xy in pts[1:]:
            qn = self.w2s(*xy)
            p.drawLine(q_prev, qn)
            q_prev = qn
        r = self._corner[4]
        tag = "R" if self._corner[0] == "fillet" else "D"
        mid = pts[len(pts) // 2]
        qm = self.w2s(*mid)
        p.setPen(DIM)
        p.drawText(int(qm.x()) + 8, int(qm.y()) - 8, f"{tag} {r:.2f}")

    def _draw_trim_piece(self, p: QPainter):
        """M168 R3: the trim tool paints the ENTIRE piece the next click
        would delete - the cut preview lives in pixels only; piece_bounds
        is read-only, nothing splits until the release commits."""
        if self._trim_hover is None:
            return
        e, lo, hi = self._trim_hover
        p.setPen(QPen(SEL, 2.4))
        if isinstance(e, Line):
            ax, ay, bx, by = e.a.x, e.a.y, e.b.x, e.b.y
            p.drawLine(self.w2s(ax + (bx - ax) * lo, ay + (by - ay) * lo),
                       self.w2s(ax + (bx - ax) * hi, ay + (by - ay) * hi))
        elif isinstance(e, Arc):
            pts = e.sample(64)
            i0 = int(round(lo * 64))
            i1 = max(int(round(hi * 64)), i0 + 1)
            q_prev = self.w2s(float(pts[i0][0]), float(pts[i0][1]))
            for xy in pts[i0 + 1:i1 + 1]:
                qn = self.w2s(float(xy[0]), float(xy[1]))
                p.drawLine(q_prev, qn)
                q_prev = qn
        elif isinstance(e, Circle):
            cen = self.w2s(e.c.x, e.c.y)
            p.drawEllipse(cen, e.r * self._scale, e.r * self._scale)
        elif isinstance(e, Ellipse):
            cen = self.w2s(e.c.x, e.c.y)
            p.drawEllipse(cen, e.rx * self._scale, e.ry * self._scale)

    def _draw_hover(self, p: QPainter):
        """M164 R2: the culprit under the cursor - a ring around its rect
        and its geometry re-stroked.  Cosmetic only: never touches _sel,
        never solves, never removes (that vocabulary is rung 3's)."""
        c = self._hover_c
        if c is None or not self.model:
            return
        if not any(cc is c for cc in self.model.sketch.constraints):
            self._hover_c = None                   # deleted mid-flight: the
            return                                 # ring dies, it never lies
        rect = next((r for r, cc in reversed(self._constraint_hits)
                     if cc is c), None)
        if rect is None:
            rect = next((r for r, cc in reversed(self._dim_hits)
                         if cc is c), None)
        hot = (QColor(theme.SKETCH["error"])       # the fight escalates red
               if id(c) in self._conflicting else HOVER)   # (badge's own law)
        p.setPen(QPen(hot, 1.6))
        if rect is not None:
            p.drawRoundedRect(QRectF(rect).adjusted(-2.5, -2.5, 2.5, 2.5),
                              4, 4)
        for e in c.entities():                     # the referenced geometry
            if isinstance(e, Point):               # glows with its badge
                pos = self.w2s(e.x, e.y)
                p.drawRect(QRectF(pos.x() - 4.6, pos.y() - 4.6, 9.2, 9.2))
            elif isinstance(e, Line):
                p.drawLine(self.w2s(e.a.x, e.a.y), self.w2s(e.b.x, e.b.y))
            elif isinstance(e, Circle):
                cen = self.w2s(e.c.x, e.c.y)
                p.drawEllipse(cen, e.r * self._scale, e.r * self._scale)
            elif isinstance(e, Arc):
                smp = e.sample(64)
                q_prev = self.w2s(float(smp[0][0]), float(smp[0][1]))
                for xy in smp[1:]:
                    qn = self.w2s(float(xy[0]), float(xy[1]))
                    p.drawLine(q_prev, qn)
                    q_prev = qn

    def _draw_preview(self, p: QPainter):
        if self._tool == "line" and self._line_start is not None:
            cur = self.mapFromGlobal(self.cursor().pos())
            wp = self._world(QPointF(cur))
            p.setPen(QPen(ACCENT, 1.2, Qt.DashLine))
            p.drawLine(self.w2s(self._line_start.x, self._line_start.y),
                       self.w2s(*wp))
            for key, txt, dy in (("len", self._line_live_text(), -22),
                                 ("ang", self._line_live_angle(), 4)):
                if not txt:
                    continue
                if key == "ang" and not self._line_angle:
                    txt = txt + "\N{DEGREE SIGN}"    # hover readings wear
                #                                       the unit; typing raw
                s = self.w2s(*self._cursor)
                fm = p.fontMetrics()
                br = fm.boundingRect(txt)
                rect = QRectF(s.x() + 14 - br.width() / 2 - 6,
                              s.y() + dy - br.height() / 2 - 3,
                              br.width() + 12, br.height() + 6)
                p.setFont(self._font)
                p.setBrush(QColor(theme.DARK["bg2"]))
                if self._line_cell == key:           # M180 R3: the LIVE
                    p.setPen(QPen(QColor(theme.DARK["accent"]), 1.4))  #  cell
                else:                                #   wears the accent
                    p.setPen(Qt.NoPen)               #     border (Tab moves
                p.drawRoundedRect(rect, 3, 3)        #     it, staff law)
                p.setPen(FG)
                p.drawText(rect, Qt.AlignCenter, txt)
                p.setBrush(Qt.NoBrush)
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
        lines.append(("Tool: " + TOOL_HINTS.get(self._tool, "?"), HUD))
        if self._show_dof:                       # M119 overlay is on: speak
            # M164 R1: the solver now remembers its arithmetic - speak it.
            lines.append((self._dof_hud_text(), WARN))
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
