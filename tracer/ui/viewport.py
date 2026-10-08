"""Interactive 3D viewport.

Design choice: moderngl renders to RGBA, we blit via QPainter. This costs
one memcpy per frame (imperceptible for a CAD viewport) but buys a single
renderer code path that runs identically on-screen, headless in tests,
and on Wayland/X11/Windows without per-platform GL plumbing.
"""
from __future__ import annotations

import math

import numpy as np
import trimesh
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QCursor
from PySide6.QtWidgets import QWidget

from ..core.document import Document
from ..core.geometry import Solid
from .camera import Camera, perspective
from .renderer import SceneRenderer
from . import theme
from .viewcube import NavWidget, ViewCube


def draw_triad(p: QPainter, cam, w: float, h: float, palette: dict):
    """Fusion's bottom-left RGB axis triad: world X/Y/Z as screen vectors
    from a docked origin; the axis leading away from the viewer dims."""
    ox, oy, L = 36.0, h - 32.0, 26.0
    f = p.font()
    f.setPointSize(8)
    f.setBold(True)
    p.setFont(f)
    for lab, (dx, dyu), visible in cam.screen_axes():
        r, g, b = palette["axis_" + lab.lower()]
        col = QColor(int(r * 255), int(g * 255), int(b * 255))
        if not visible:
            col.setAlpha(88)
        ex, ey = ox + dx * L, oy - dyu * L
        pen = QPen(col, 2.2 if visible else 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(ox, oy), QPointF(ex, ey))
        p.setBrush(col)
        p.setPen(QPen(col))
        rr = 2.6 if visible else 1.7
        p.drawEllipse(QPointF(ex, ey), rr, rr)
        p.drawText(QRectF(ox + dx * (L + 12) - 8, oy - dyu * (L + 12) - 8,
                          16, 16), Qt.AlignCenter, lab)


class Viewport(QWidget):
    face_picked = Signal(object, object)   # world point, outward normal (planar)
    coords = Signal(object)                # world point under cursor | None
    press_pull = Signal(object)            # Press-Pull drag payload dict
    move_drag = Signal(object)             # Move (M53) drag payload dict
    rotate_drag = Signal(object)           # Rotate (M55) drag payload dict
    context_request = Signal(object)       # RMB no-drag: marking menu pos
    selection_changed = Signal(int)        # live measure: faces now selected
    zoom_selection = Signal()              # Z hotkey: zoom to what's picked
    zoom_window = Signal(object)           # Zoom-window (M62) payload dict

    def __init__(self, renderer: SceneRenderer, parent=None):
        super().__init__(parent)
        self._r = renderer
        self._cam = Camera()
        self._cube = ViewCube()
        self._nav = NavWidget()
        self._doc: Document | None = None
        self._bbox: np.ndarray | None = None
        self._last: QPoint | None = None
        self._buttons = Qt.MouseButtons()
        self._tm = None                    # cached pick mesh (refresh)
        self._gid = None                   # face -> coplanar group id
        self._hover: list[int] | None = None
        self._sel: list[int] = []
        self._body_rng: list = []          # M131 stitch ranges (body->faces)
        self._body_hi: list[int] = []      # M131 browser-picked body wash
        self._pp = None                    # press-pull drag state
        self.show_cube = True              # Ctrl+Alt+V (M113 layout layer)
        self.show_nav = True               # Ctrl+Alt+N
        self._pp_drag = False
        self._box: list | None = None      # rubber-band select [p0, p1]
        self._box_drag = False
        self._mv = None                    # Move gesture state (M53)
        self._rot = None                   # Rotate gesture state (M55)
        self._zoom_win = None              # Zoom-window arming (M62)
        self._cube_hover = None            # ViewCube face under cursor (M63)
        self.setMinimumSize(QSize(320, 240))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWindowTitle("3D Viewport")

    # ---- model -----------------------------------------------------------
    def set_document(self, doc: Document):
        self._doc = doc
        self.refresh(fit=True)

    def refresh(self, fit: bool = False):
        doc = self._doc
        default = ((doc.appearance or {}).get("color")
                   if doc and doc.painted_bodies() else None)
        stitched, rng = (doc.display_ranges(default) if doc
                         else (None, []))
        arrays = None if stitched is None else stitched[:3]
        face_colors = None if stitched is None else stitched[3]
        had_sel = bool(self._sel)
        self._hover, self._sel = None, []
        self._body_hi = []                 # M131: the wash dies with its
        self._body_rng = rng               # mesh generation
        self._pp, self._pp_drag = None, False
        self._box, self._box_drag = None, False
        self._mv = None                    # Move gesture state (M53)
        self._rot = None                   # Rotate gesture state (M55)
        self._zoom_win = None              # Zoom-window arming (M62)
        self._r.set_triad(None)
        if had_sel:
            self.selection_changed.emit(0)
        if arrays is None:
            self._r.clear_mesh()
            self._bbox = None
            self._tm = self._gid = None
        else:
            v, n, f = arrays
            self._r.set_mesh(v, n, f, face_colors=face_colors)
            # Pick mesh shares the uploaded (needle-filtered) index space,
            # so raycast face ids map 1:1 onto highlight rows.  M104:
            # the mesh is the STITCHED visible bodies, so the index
            # space is exactly what the eye sees — pick_mesh owns it.
            self._tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
            self._gid = _coplanar_groups(self._tm)
            V = np.asarray(v, float)
            self._bbox = np.array([V.min(axis=0), V.max(axis=0)])
            self._r._grid_auto(self._bbox)
            if fit:
                self._cam.fit(self._bbox)
        self._r.set_planes(self._doc.planes if self._doc else [],
                           self._doc.axes if self._doc else [])
        self._r.set_decals(self._doc.thread_decals() if self._doc else [])
        self.update()

    def pick_mesh(self):
        """The trimesh behind the face ids this viewport hands out."""
        return self._tm

    def solid(self) -> Solid | None:
        return self._doc.result if self._doc else None

    def set_solid_visible(self, on: bool):
        """Browser body-menu toggle (Fusion's bulb)."""
        self._r.show_solid = bool(on)
        self.update()

    # ---- Section Analysis ----------------------------------------------------
    def set_section(self, spec):
        """spec: 'XY'|'XZ'|'YZ' | {'name','normal','origin'} | None (off).
        The clipped-away side is the one the normal points to; flip()
        sends it through to the other side, like Fusion's flip arrow."""
        if spec is None:
            self._r.clip = None
        elif isinstance(spec, str):
            n = {"XY": (0, 0, 1), "XZ": (0, 1, 0), "YZ": (1, 0, 0)}[spec]
            self._r.clip = {"normal": n, "origin": (0.0, 0.0, 0.0),
                            "label": spec}
        else:
            self._r.clip = {"normal": tuple(spec["normal"]),
                            "origin": tuple(spec["origin"]),
                            "label": spec.get("name", "Plane")}
        self.update()

    def flip_section(self):
        c = self._r.clip
        if c:
            c["normal"] = tuple(-float(t) for t in c["normal"])
            self.update()

    section = property(lambda self: self._r.clip)

    def attach(self, doc: Document):
        """Track a swapped-in document without refitting the camera."""
        self._doc = doc

    def preview_mesh(self, solid: Solid | None):
        """Swap the GPU mesh without touching the document (Press-Pull
        live preview); pass None to restore the committed model.
        During preview the body wears Fusion's amber ghost tint."""
        if solid is None:
            self._r.set_ghost(False)
            self.refresh()
            return
        v, n, f = solid.to_render_arrays()
        self._r.set_mesh(v, n, f)
        self._r.set_ghost(True)
        self.update()

    # ---- paint -------------------------------------------------------------
    def paintEvent(self, ev):
        dpr = self.devicePixelRatioF()
        w, h = int(self.width() * dpr), int(self.height() * dpr)
        self._r.resize(w, h)
        img = self._r.render(self._cam, self._bbox)
        qimg = QImage(img.tobytes(), w, h, QImage.Format_RGBA8888).copy()
        qimg.setDevicePixelRatio(dpr)
        p = QPainter(self)
        p.drawImage(0, 0, qimg)
        if self._box_drag and self._box is not None:
            pen_c, br_c = self.rubber_style(self._box_is_window())
            p.setPen(QPen(pen_c, 1, Qt.DashLine))
            p.setBrush(br_c)
            p.drawRect(QRect(self._box[0], self._box[1]).normalized())
        draw_triad(p, self._cam, self.width(), self.height(), self._r.palette)
        self._cube.place(self.width(), self.height())
        if self.show_cube:
            self._cube.draw(p, self._cam, self._cube_hover)
        self._nav.place(self.width(), self._cube.rect.bottom() + 8)
        if self.show_nav:
            self._nav.draw(p)
        p.end()

    @staticmethod
    def rubber_style(window: bool):
        """Fusion's two rubber voices: left→right WINDOW (blue, must
        contain) vs right→left CROSSING (green, just touches)."""
        if window:
            c = theme.DARK["accent_soft"]
        else:
            c = theme.DARK["success"]
        return QColor(c), QColor(theme.rgba(c, 24))

    def _box_is_window(self) -> bool:
        return self._box is not None and \
            self._box[1].x() >= self._box[0].x()

    # ---- mouse (Fusion scheme) ----------------------------------------------
    # LMB: pick a face · LMB drag on empty: rubber-band select ·
    #      LMB drag on a face: Press-Pull
    # MMB drag: pan                      Shift+MMB / RMB drag: orbit
    # MMB click (no drag): return home   wheel: zoom toward the cursor
    # ---- Move gesture (M53) ---------------------------------------------------
    def begin_move(self, origin, length: float):
        """Arm the Move gesture: RGB triad at `origin`; drag an arrow to
        slide the body along that axis, release commits, Esc/empty-click
        cancels — Fusion's Move mouse grammar on one grab."""
        self._mv = dict(origin=np.asarray(origin, float),
                        length=float(length), axis=None, s0=0.0,
                        off=np.zeros(3))
        self._r.set_triad(origin, length)
        self.update()

    def _cancel_move(self):
        if self._mv is None:
            return
        self._mv = None
        self._r.set_triad(None)
        self.unsetCursor()
        self.move_drag.emit(dict(cancel=True))
        self.update()

    def _triad_hit(self, px: float, py: float):
        """Which triad arrow (0/1/2) sits under the cursor, or None."""
        if self._mv is None:
            return None
        o, L = self._mv["origin"], self._mv["length"]
        best, bd = None, 14.0
        for i in range(3):
            p0 = self._cam.project(o, self.width(), self.height())
            p1 = self._cam.project(o + np.eye(3)[i] * L * 1.15,
                                   self.width(), self.height())
            if p0 is None or p1 is None:
                continue
            ax_, ay_ = p0
            bx, by = p1
            vx, vy = bx - ax_, by - ay_
            ln = vx * vx + vy * vy
            t = 0.0 if ln == 0 else max(
                0.0, min(1.0, ((px - ax_) * vx + (py - ay_) * vy) / ln))
            dx, dy = px - (ax_ + t * vx), py - (ay_ + t * vy)
            d = (dx * dx + dy * dy) ** 0.5
            if d < bd:
                best, bd = i, d
        return best

    def _axis_param(self, mv, px: float, py: float):
        """Where the cursor ray passes closest along the grabbed axis —
        dragging this value is what slides the body."""
        o0, d0 = self._cam.ray(px, py, self.width(), self.height())
        o0 = np.asarray(o0, float)
        d0 = np.asarray(d0, float) / max(
            float(np.linalg.norm(d0)), 1e-12)
        e = np.eye(3)[mv["axis"]]
        a = o0 - mv["origin"]
        b = float(d0 @ e)
        det = 1.0 - b * b
        if abs(det) < 1e-6:                # ray runs along the axis
            return None
        return (float(e @ a) - b * float(d0 @ a)) / det

    # ---- Rotate gesture (M55) ---------------------------------------------------
    def begin_rotate(self, center, radius: float):
        """Arm the Rotate gesture: RGB rings at `radius`; drag a ring
        and the body spins about that axis, release commits, Esc or an
        empty click cancels — Fusion's rotate-by-arc mouse grammar."""
        self._rot = dict(center=np.asarray(center, float),
                         radius=float(radius), axis=None, th0=0.0,
                         ang=0.0)
        self._r.set_triad(center, radius * 0.82, radius)
        self.update()

    def _cancel_rotate(self):
        if self._rot is None:
            return
        self._rot = None
        self._r.set_triad(None)
        self.unsetCursor()
        self.rotate_drag.emit(dict(cancel=True))
        self.update()

    def _ring_hit(self, px: float, py: float):
        """Which rotation ring (axis 0/1/2) is under the cursor."""
        if self._rot is None:
            return None
        c, R = self._rot["center"], self._rot["radius"]
        best, bd = None, 14.0
        for i in range(3):
            u, v = np.eye(3)[(i + 1) % 3], np.eye(3)[(i + 2) % 3]
            for k in range(48):
                a = 2.0 * np.pi * k / 48.0
                sp = self._cam.project(
                    c + (np.cos(a) * u + np.sin(a) * v) * R,
                    self.width(), self.height())
                if sp is None:
                    continue
                d = ((px - sp[0]) ** 2 + (py - sp[1]) ** 2) ** 0.5
                if d < bd:
                    best, bd = i, d
        return best

    def _ring_param(self, rot, px: float, py: float):
        """Polar angle (radians) where the cursor ray meets the grabbed
        ring's plane — dragging this is what turns the body."""
        o0, d0 = self._cam.ray(px, py, self.width(), self.height())
        o0 = np.asarray(o0, float)
        d0 = np.asarray(d0, float) / max(
            float(np.linalg.norm(d0)), 1e-12)
        e = np.eye(3)[rot["axis"]]
        de = float(d0 @ e)
        if abs(de) < 1e-6:
            return None
        t = float((rot["center"] - o0) @ e) / de
        p = o0 + d0 * t - rot["center"]
        u, v = np.eye(3)[(rot["axis"] + 1) % 3], \
            np.eye(3)[(rot["axis"] + 2) % 3]
        return float(np.arctan2(p @ v, p @ u))

    # ---- Zoom window (M62) ------------------------------------------------------
    def begin_zoom_window(self):
        """Fusion marking-menu Zoom window: arm the rectangle drag;
        release zooms the camera onto the mesh inside, a plain click or
        Esc aborts without touching the camera."""
        self._zoom_win = dict()
        self.setCursor(QCursor(Qt.CrossCursor))
        self.update()

    def _cancel_zoom_window(self):
        if self._zoom_win is None:
            return
        self._zoom_win = None
        self._box, self._box_drag = None, False
        self.unsetCursor()
        self.zoom_window.emit(dict(cancel=True))
        self.update()

    def _zoom_win_bbox(self, p0, p1):
        """World bbox of mesh vertices whose projection lands inside
        the screen rectangle — None when the box is a stub or empty."""
        if self._tm is None:
            return None
        w, h = self.width(), self.height()
        x0, x1 = sorted((p0.x(), p1.x()))
        y0, y1 = sorted((p0.y(), p1.y()))
        if x1 - x0 <= 4 or y1 - y0 <= 4:
            return None
        vs = np.asarray(self._tm.vertices, float)
        vp = perspective(self._cam.fov, w / max(h, 1),
                         0.01, 1e5) @ self._cam.view_matrix()
        ph = np.column_stack([vs, np.ones(len(vs))]) @ vp.T
        w_ = ph[:, 3]
        with np.errstate(divide="ignore", invalid="ignore"):
            sx = (ph[:, 0] / w_ * 0.5 + 0.5) * w
            sy = (0.5 - ph[:, 1] / w_ * 0.5) * h
        inside = ((w_ > 1e-9) & np.isfinite(sx) & np.isfinite(sy)
                  & (sx >= x0) & (sx <= x1) & (sy >= y0) & (sy <= y1))
        if not inside.any():
            return None
        pts = vs[inside]
        return (pts.min(axis=0), pts.max(axis=0))

    def mousePressEvent(self, ev):
        hit = self._cube.hit(ev.position()) if self.show_cube else None
        if hit:
            self._cam.set_view(hit)
            self.update()
            ev.accept()
            return
        nav = self._nav.hit(ev.position()) if self.show_nav else None
        if nav:
            if nav == "home":
                self.home()
            elif nav == "in":
                self._cam.zoom(1 / 1.25)
                self.update()
            else:
                self._cam.zoom(1.25)
                self.update()
            ev.accept()
            return
        self._last = ev.position().toPoint()
        self._buttons |= ev.button()
        self._ctrl_at_press = bool(ev.modifiers() & Qt.ControlModifier)
        self._dragged = False
        self._pp = None
        self._pp_drag = False
        self._box = None
        self._box_drag = False
        if (self._zoom_win is not None and ev.button() == Qt.LeftButton
                and Qt.KeyboardModifier(0) == ev.modifiers()):
            self._box = [ev.position().toPoint(), ev.position().toPoint()]
            self._box_drag = True
            ev.accept()
            return
        if (self._rot is not None and ev.button() == Qt.LeftButton
                and ev.modifiers() in (Qt.KeyboardModifier(0),
                                       Qt.ControlModifier)):
            self._rot["copy"] = bool(
                ev.modifiers() & Qt.ControlModifier)
            px, py = ev.position().x(), ev.position().y()
            ax = self._ring_hit(px, py)
            if ax is not None:
                self._rot["axis"] = ax
                th = self._ring_param(self._rot, px, py)
                self._rot["th0"] = th if th is not None else 0.0
                self.setCursor(QCursor(Qt.CrossCursor))
                if self._hover:
                    self._hover = None
                    self._apply_hi()
                ev.accept()
                return
        if (self._mv is not None and ev.button() == Qt.LeftButton
                and ev.modifiers() in (Qt.KeyboardModifier(0),
                                       Qt.ControlModifier)):
            self._mv["copy"] = bool(ev.modifiers() & Qt.ControlModifier)
            px, py = ev.position().x(), ev.position().y()
            ax = self._triad_hit(px, py)
            if ax is not None:
                self._mv["axis"] = ax
                s = self._axis_param(self._mv, px, py)
                self._mv["s0"] = s if s is not None else 0.0
                self.setCursor(QCursor(Qt.SizeAllCursor))
                if self._hover:
                    self._hover = None
                    self._apply_hi()
                ev.accept()
                return
        if ev.button() == Qt.LeftButton and self._tm is not None \
                and ev.modifiers() in (Qt.KeyboardModifier(0),
                                       Qt.ControlModifier) \
                and self._mv is None and self._rot is None:
            px, py = ev.position().x(), ev.position().y()
            hit = self._shoot(self._tm, px, py)
            if hit is not None \
                    and not (ev.modifiers() & Qt.ControlModifier):
                g = self._group(hit[2])
                n = np.asarray(self._tm.face_normals, float)[g].sum(0)
                n /= max(float(np.linalg.norm(n)), 1e-12)
                o0, d0 = self._cam.ray(px, py, self.width(), self.height())
                t0 = float((hit[0] - o0) @ d0)       # grab depth along ray
                self._pp = dict(faces=g, point=np.asarray(hit[0], float),
                                normal=n, px0=ev.position().toPoint(),
                                t0=t0, offset=0.0, ppid=object())
            else:
                self._box = [ev.position().toPoint(),
                             ev.position().toPoint()]
                self._box_add = bool(ev.modifiers() & Qt.ControlModifier)
        if self._hover:
            self._hover = None                       # no wash while dragging
            self._apply_hi()
        if ev.button() == Qt.MiddleButton:
            self.setCursor(QCursor(Qt.ClosedHandCursor))

    def mouseMoveEvent(self, ev):
        if not self._buttons:
            self._hover_update(ev.position())
            hk = self._cube.hit(ev.position()) if self.show_cube else None
            nav_changed = (self._nav.set_hover(ev.position())
                           if self.show_nav else False)
            if hk != self._cube_hover:
                self._cube_hover = hk
                if hk is not None:
                    self.setCursor(QCursor(Qt.PointingHandCursor))
                elif not self._nav.hover:
                    self.unsetCursor()
                self.update()
            elif nav_changed:
                self.setCursor(
                    Qt.CursorShape.PointingHandCursor
                    if self._nav.hover else Qt.CursorShape.ArrowCursor)
                self.update()
            return
        if self._last is None:
            return
        d = ev.position().toPoint() - self._last
        if d.manhattanLength() > 2:
            self._dragged = True
        self._last = ev.position().toPoint()
        if (self._rot is not None and self._rot["axis"] is not None
                and Qt.LeftButton in self._buttons):
            th = self._ring_param(self._rot, ev.position().x(),
                                  ev.position().y())
            if th is not None:
                self._rot["ang"] = th - self._rot["th0"]
                self.rotate_drag.emit(dict(
                    center=self._rot["center"], axis=self._rot["axis"],
                    rad=self._rot["ang"], live=True))
            self.update()
            return
        if (self._mv is not None and self._mv["axis"] is not None
                and Qt.LeftButton in self._buttons):
            s = self._axis_param(self._mv, ev.position().x(),
                                 ev.position().y())
            if s is not None:
                self._mv["off"] = (s - self._mv["s0"]) \
                    * np.eye(3)[self._mv["axis"]]
                self.move_drag.emit(dict(offset=self._mv["off"],
                                         live=True))
            self.update()
            return
        if self._pp is not None and Qt.LeftButton in self._buttons \
                and not (self._buttons & (Qt.MiddleButton | Qt.RightButton)):
            pos = ev.position().toPoint()
            if not self._pp_drag \
                    and (pos - self._pp["px0"]).manhattanLength() > 4:
                self._pp_drag = True
                self.setCursor(QCursor(Qt.SizeAllCursor))
            if self._pp_drag:
                self._pp["offset"] = self._plane_offset(pos.x(), pos.y())
                self.press_pull.emit({**self._pp, "live": True})
                self.update()
                return
        if self._box is not None and Qt.LeftButton in self._buttons:
            self._box[1] = ev.position().toPoint()
            if (self._box[1] - self._box[0]).manhattanLength() > 4:
                self._box_drag = True
            self.update()
            return
        if Qt.MiddleButton in self._buttons:
            if ev.modifiers() & Qt.ShiftModifier:
                self._cam.pan(d.x(), d.y(), self.height())   # Fusion: Shift+MMB pans
            else:
                self._cam.orbit(d.x(), d.y(), self.height()) # Fusion: MMB orbits
            self.update()
        elif Qt.RightButton in self._buttons:
            self._cam.orbit(d.x(), d.y(), self.height())
            self.update()

    def mouseReleaseEvent(self, ev):
        self._buttons &= ~ev.button()
        if ev.button() == Qt.LeftButton and self._zoom_win is not None:
            p0, p1 = (self._box if self._box is not None
                      else [ev.position().toPoint()] * 2)
            self._box, self._box_drag = None, False
            self._zoom_win = None
            self.unsetCursor()
            bbox = self._zoom_win_bbox(p0, p1)
            if bbox is None:
                self.zoom_window.emit(dict(
                    cancel=True,
                    empty=getattr(self, "_dragged", False)))
            else:
                self.zoom_window.emit(dict(bbox=bbox))
            self.update()
            ev.accept()
            return
        if ev.button() == Qt.LeftButton and self._rot is not None:
            if self._rot["axis"] is not None:
                pay = dict(center=self._rot["center"],
                           axis=self._rot["axis"],
                           rad=self._rot["ang"], live=False,
                           copy=bool(self._rot.get("copy", False)))
                self._rot = None
                self._r.set_triad(None)
                self.unsetCursor()
                self.rotate_drag.emit(pay)
            else:
                self._cancel_rotate()
            self.update()
            ev.accept()
            return
        if ev.button() == Qt.LeftButton and self._mv is not None:
            if self._mv["axis"] is not None:      # drag ends: commit gesture
                off = self._mv["off"]
                was_copy = bool(self._mv.get("copy", False))
                self._mv = None
                self._r.set_triad(None)
                self.unsetCursor()
                self.move_drag.emit(dict(offset=off, live=False,
                                         copy=was_copy))
            else:                                  # click off the arrows
                self._cancel_move()
            self.update()
            ev.accept()
            return
        if (ev.button() == Qt.LeftButton
                and not getattr(self, "_dragged", True)):
            self._click_select(ev.position(),       # Fusion: pick a face
                               ctrl=getattr(self, "_ctrl_at_press", False))
        if ev.button() == Qt.LeftButton and getattr(self, "_box_drag", False):
            p0, p1 = self._box
            self._box, self._box_drag = None, False
            self._select_box(p0, p1,
                             add=getattr(self, "_box_add", False))
        elif ev.button() == Qt.LeftButton and getattr(self, "_pp_drag", False):
            self.press_pull.emit({**self._pp, "live": False})
            self.unsetCursor()
            self._pp, self._pp_drag = None, False
        elif ev.button() == Qt.LeftButton:
            self._pp, self._pp_drag = None, False
            self._box, self._box_drag = None, False
        if ev.button() == Qt.RightButton \
                and not getattr(self, "_dragged", False):
            self.context_request.emit(ev.position().toPoint())
        if ev.button() == Qt.MiddleButton:
            self.unsetCursor()
            if not getattr(self, "_dragged", False):
                self.home()
        if not (self._buttons & (Qt.MiddleButton | Qt.RightButton)):
            self.unsetCursor()

    def _plane_offset(self, px: float, py: float) -> float:
        """Signed mm the face should travel along its normal under the
        cursor. The new ray is sampled at the original grab depth — that
        world move lies in the view plane, so divide out the foreshortening
        (1 − (view·n)²) of the normal's projection. Nearly head-on faces
        have no usable screen direction for their normal: fall back to
        vertical cursor travel in ground-plane mm (drag up = pull out)."""
        pp = self._pp
        n, c = pp["normal"], pp["point"]
        o, d = self._cam.ray(px, py, self.width(), self.height())
        o0, d0 = self._cam.ray(pp["px0"].x(), pp["px0"].y(),
                               self.width(), self.height())
        foresh = 1.0 - float(d0 @ n) ** 2
        if foresh < 0.05:                        # viewing along the normal
            f = getattr(self._cam, "fov", math.radians(45.0))
            mm_per_px = 2.0 * pp["t0"] * math.tan(f / 2.0) / self.height()
            k = (pp["px0"].y() - py) * mm_per_px  # drag up = toward viewer
            return k * (1.0 if float(d0 @ n) < 0 else -1.0)
        q = o + pp["t0"] * d
        return float((q - c) @ n) / foresh

    def wheelEvent(self, ev):
        """Fusion zooms toward the point under the cursor: raycast the
        model first, fall back to the ground plane, else plain dolly."""
        k = pow(1.0015, -ev.angleDelta().y())
        px, py = ev.position().x(), ev.position().y()
        anchor = None
        if self._tm is not None:
            hit = self._shoot(self._tm, px, py)
            if hit is not None:
                anchor = hit[0]
        if anchor is None:
            anchor = self._ground_point(px, py)
        if anchor is None:
            self._cam.zoom(k)
        else:
            self._cam.zoom_to(k, anchor)
        self.update()

    # ---- picking (double-click a planar face -> sketch on it) ---------------
    def _shoot(self, tm, px: float, py: float):
        o, d = self._cam.ray(px, py, self.width(), self.height())
        # NB: trimesh returns (locations, index_RAY, index_TRI)
        locs, _, itri = tm.ray.intersects_location([o], [d],
                                                   multiple_hits=False)
        if len(locs) == 0:
            return None
        return locs[0], tm.face_normals[itri[0]], int(itri[0])

    def _ground_point(self, px: float, py: float):
        o, d = self._cam.ray(px, py, self.width(), self.height())
        if abs(d[2]) < 1e-9:
            return None
        t = -o[2] / d[2]
        return o + d * t if t > 0 else None

    def _group(self, face: int) -> list[int]:
        """All mesh faces coplanar-neighbouring `face` (whole logical face)."""
        if self._gid is None:
            return [face]
        return np.flatnonzero(self._gid == self._gid[face]).tolist()

    def _apply_hi(self):
        # M131: a browser-picked body washes through the SELECTION value,
        # merged here at the single choke point — self._sel stays exactly
        # the picked faces, so measure-on-pick and every face command
        # keep their precise targets.
        sel = self._sel
        if self._body_hi:
            sel = sorted(set(sel) | set(self._body_hi))
        self._r.set_highlight(self._hover, sel)
        self.update()

    def _hover_update(self, pos):
        if self._tm is None:
            return
        hit = self._shoot(self._tm, pos.x(), pos.y())
        self.coords.emit(hit[0] if hit else
                         self._ground_point(pos.x(), pos.y()))
        faces = self._group(hit[2]) if hit else None
        if faces != self._hover:
            self._hover = faces
            self._apply_hi()

    def _click_select(self, pos, ctrl: bool = False):
        if self._tm is None:
            return
        hit = self._shoot(self._tm, pos.x(), pos.y())
        if hit is None:
            if not ctrl and self._sel:
                self._sel = []
                self._apply_hi()
                self.selection_changed.emit(0)
            return
        faces = self._group(hit[2])
        if ctrl:
            # Fusion: Ctrl+click toggles this face in/out of the set
            if faces[0] in self._sel:
                kill = set(faces)
                self._sel = [f for f in self._sel if f not in kill]
            else:
                self._sel += [f for f in faces if f not in self._sel]
        else:
            # Fusion: a plain click REPLACES the selection
            self._sel = list(faces)
        self._apply_hi()
        self.selection_changed.emit(len(self.selected_groups()))

    def _select_box(self, p0, p1, add: bool = False):
        """Fusion's rubber-band gestures: drag left→right is a WINDOW
        (faces whose triangles all land inside), right→left is CROSSING
        (faces whose silhouette the box touches).  Whole logical faces
        (coplanar groups); replaces the selection.  v1 selects by 2D
        containment — hidden faces behind the hit count too."""
        if self._tm is None:
            return
        x0, x1 = sorted((float(p0.x()), float(p1.x())))
        y0, y1 = sorted((float(p0.y()), float(p1.y())))
        window = float(p1.x()) >= float(p0.x())
        w, h = float(self.width()), float(self.height())
        V = np.asarray(self._tm.vertices, float)
        vp = self._cam.proj_matrix(w / max(h, 1.0)) @ self._cam.view_matrix()
        c = np.column_stack([V, np.ones(len(V))]) @ vp.T
        fin = c[:, 3] > 1e-9
        with np.errstate(invalid="ignore"):
            sx = np.where(fin, (c[:, 0] / np.where(fin, c[:, 3], 1.0) + 1.0)
                          * 0.5 * w, -1.0)
            sy = np.where(fin, (1.0 - c[:, 1] / np.where(fin, c[:, 3], 1.0))
                          * 0.5 * h, -1.0)
        tri = np.asarray(self._tm.faces, int)
        tx, ty = sx[tri], sy[tri]
        inside = (tx >= x0) & (tx <= x1) & (ty >= y0) & (ty <= y1)
        if window:
            pick = inside.all(axis=1)
        else:
            pick = ((tx.min(axis=1) <= x1) & (tx.max(axis=1) >= x0)
                    & (ty.min(axis=1) <= y1) & (ty.max(axis=1) >= y0))
            pick &= fin[tri].all(axis=1)
        if not add:
            self._sel = []
        if self._gid is not None and pick.any():
            for g in np.unique(self._gid[pick]):
                self._sel.extend(f for f in
                                 np.flatnonzero(self._gid == g).tolist()
                                 if f not in self._sel)
        self._hover = None
        self._apply_hi()
        self.selection_changed.emit(len(self.selected_groups()))

    def selected_groups(self) -> list[list[int]]:
        """The current selection split into whole logical face groups."""
        if self._tm is None or not self._sel:
            return []
        out, seen = [], set()
        for f in sorted(self._sel):
            if f in seen:
                continue
            g = self._group(f)
            seen.update(g)
            out.append(g)
        return out

    # ---- cross-highlight (M131) ----------------------------------------
    def emphasize_body(self, name: str | None):
        """Browser -> canvas: wash one body in the selection blue just
        by clicking its row. Visual only — the picked-face selection is
        untouched, so nothing downstream sees a phantom selection.
        None clears the wash (a non-body row was chosen)."""
        self._body_hi = self.body_faces(name) if name else []
        self._apply_hi()

    def body_faces(self, name: str) -> list[int]:
        """Every viewport mesh face that came from body `name` (from
        the stitch ranges); [] when the body is hidden or unknown."""
        for nm, lo, hi in self._body_rng:
            if nm == name:
                return list(range(lo, hi))
        return []

    def body_of_faces(self, faces) -> str | None:
        """Canvas -> browser: which body owns most of these faces —
        the pick resolves to a browser row (majority, since a marquee
        can catch two bodies' edges)."""
        if not self._body_rng or not faces:
            return None
        tally: dict = {}
        for f in faces:
            for nm, lo, hi in self._body_rng:
                if lo <= f < hi:
                    tally[nm] = tally.get(nm, 0) + 1
                    break
        return max(tally, key=tally.get) if tally else None

    def selected_body(self) -> str | None:
        """The body owning the current picked faces (None if none)."""
        return self.body_of_faces(self._sel)

    def focus_datum(self, role: str, name: str) -> bool:
        """Browser -> camera: centre the orbit on a construction plane
        or work axis (M131 zoom-to-datum). The frame IS the datum's
        only body, so we re-centre honestly rather than pretend to
        know an on-screen size for an infinite object."""
        if self._doc is None:
            return False
        store = (self._doc.planes if role == "cplane"
                 else self._doc.axes if role == "caxis" else [])
        for d in store:
            if d["name"] == name:
                self._cam.target = np.asarray(d["origin"], float)
                self.update()
                return True
        return False

    def selected_face(self) -> dict | None:
        """Reference frame of the current face selection: {'point',
        'normal'} — for commands that act ON a face (Shell).  None when
        nothing is picked."""
        if self._tm is None or not self._sel:
            return None
        idx = np.asarray(sorted(self._sel), int)
        n = np.asarray(self._tm.face_normals, float)[idx].sum(0)
        nn = float(np.linalg.norm(n))
        if nn < 1e-9:
            return None
        tris = np.asarray(self._tm.faces, int)[idx]
        pts = np.asarray(self._tm.vertices, float)[tris].reshape(-1, 3)
        return dict(point=pts.mean(0), normal=n / nn)

    def smooth_region(self, face: int) -> list[int]:
        """Every face reachable from `face` through neighbours that bend
        at most 30 degrees across their shared edge — the WHOLE curved
        face (a cylinder wall), not one mesh facet.  Flat faces come back
        as themselves (90-degree creases stop the flood)."""
        if self._tm is None:
            return [int(face)]
        fn = np.asarray(self._tm.face_normals, float)
        nbrs: dict[int, list[int]] = {}
        for a, b in np.asarray(self._tm.face_adjacency, int):
            if float(np.dot(fn[a], fn[b])) > math.cos(math.radians(30)):
                nbrs.setdefault(int(a), []).append(int(b))
                nbrs.setdefault(int(b), []).append(int(a))
        seen = {int(face)}
        stack = [int(face)]
        while stack:
            for q in nbrs.get(stack.pop(), ()):
                if q not in seen:
                    seen.add(q)
                    stack.append(q)
        return sorted(seen)

    def _pick_planar(self, pos):
        """Hit test at pos; accept only faces flat within ~2 degrees across
        a +/-3 px neighbourhood (kills cylinders/cones hiding in meshes)."""
        if self._tm is None:
            return None
        tm = self._tm
        hit = self._shoot(tm, pos.x(), pos.y())
        if hit is None:
            return None
        point, n0 = hit[0], hit[1]
        cos_lim = math.cos(math.radians(2.0))
        for dx, dy in ((10, 0), (-10, 0), (0, 10), (0, -10)):
            h = self._shoot(tm, pos.x() + dx, pos.y() + dy)
            if h is None or float(h[1] @ n0) < cos_lim:
                return None
        return point, n0

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            hit = self._pick_planar(ev.position())
            if hit is not None:
                self.face_picked.emit(hit[0], hit[1])
                ev.accept()
                return
        super().mouseDoubleClickEvent(ev)

    # ---- home view ---------------------------------------------------------
    def home(self):
        if self._bbox is not None:
            self._cam.set_view("iso")
            self._cam.fit(self._bbox)
        self.update()

    # ---- keys (F fit, G grid, 0/1/2/3 views, Esc deselect) ------------------
    def selection_bbox(self):
        """bbox of the currently picked faces, or None (M56 zoom-to).
        _sel is a list of TRIANGLES, so flatten the corner vertices
        first — per-triangle mins were a (3,3) lie (M59 regression)."""
        if self._tm is None or not self._sel:
            return None
        tris = np.asarray(self._tm.faces)[np.asarray(self._sel, int)]
        pts = np.asarray(self._tm.vertices, float)[tris].reshape(-1, 3)
        return (pts.min(axis=0), pts.max(axis=0))

    def zoom_to_selection(self):
        """M113: Z, callable from anywhere (viewport-local or the
        window's key table)."""
        if self._sel and self.selection_bbox() is not None:
            self.zoom_selection.emit()

    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key_Escape:
            if self._zoom_win is not None:           # abort a zoom window
                self._cancel_zoom_window()
                return
            if self._rot is not None:             # abort a rotate gesture
                self._cancel_rotate()
                return
            if self._mv is not None:               # abort a move gesture
                self._cancel_move()
                return
            if self._pp is not None:                 # abort a press-pull
                self._pp, self._pp_drag = None, False
                self.unsetCursor()
                self.press_pull.emit({"cancel": True})
                return
            if self._sel or self._hover:
                had = bool(self._sel)
                self._sel, self._hover = [], None
                self._apply_hi()
                if had:
                    self.selection_changed.emit(0)
            return
        _VIEWS = {Qt.Key_0: "iso", Qt.Key_1: "front",
                  Qt.Key_2: "top", Qt.Key_3: "right"}
        if k in _VIEWS:                 # our documented BEAT: Fusion
            self._cam.set_view(_VIEWS[k])   # ships no orientation keys
            self.update()
            return
        # M113: everything else answers from the one model table
        # (MainWindow's commands.MODEL_KEYS) — F fillets, E extrudes,
        # Z zooms to the pick, Ctrl+Alt toggles panels. Nothing here.
        w = self.window()
        if hasattr(w, "_dispatch_key") and w._dispatch_key(
                k, ev.modifiers()):
            self.update()
            return
        super().keyPressEvent(ev)

    # ---- helpers ------------------------------------------------------------
    def camera(self) -> Camera:
        return self._cam


def _coplanar_groups(tm) -> np.ndarray:
    """Union-find over face adjacency, merging neighbours whose normals
    agree within ~1 degree: hovering one triangle of a large planar (or
    finely tessellated smooth) face lights the whole logical face, like
    Fusion's selection behaviour."""
    fn = np.asarray(tm.face_normals)
    adj = np.asarray(tm.face_adjacency)
    gid = np.arange(len(fn))

    def find(i):
        while gid[i] != i:
            gid[i] = gid[gid[i]]
            i = gid[i]
        return i

    if len(adj):
        dots = np.einsum("ij,ij->i", fn[adj[:, 0]], fn[adj[:, 1]])
        for (f0, f1), same in zip(adj, dots > 0.9998):
            if same:
                r0, r1 = find(int(f0)), find(int(f1))
                if r0 != r1:
                    gid[r1] = r0
        for i in range(len(fn)):
            gid[i] = find(i)
    return gid
