"""Interactive 3D viewport.

Design choice: moderngl renders to RGBA, we blit via QPainter. This costs
one memcpy per frame (imperceptible for a CAD viewport) but buys a single
renderer code path that runs identically on-screen, headless in tests,
and on Wayland/X11/Windows without per-platform GL plumbing.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt, QPoint, QSize, Signal
from PySide6.QtGui import QImage, QPainter, QCursor
from PySide6.QtWidgets import QWidget

from ..core.document import Document
from ..core.geometry import Solid
from .camera import Camera
from .renderer import SceneRenderer
from .viewcube import ViewCube


class Viewport(QWidget):
    face_picked = Signal(object, object)   # world point, outward normal (planar)

    def __init__(self, renderer: SceneRenderer, parent=None):
        super().__init__(parent)
        self._r = renderer
        self._cam = Camera()
        self._cube = ViewCube()
        self._doc: Document | None = None
        self._bbox: np.ndarray | None = None
        self._last: QPoint | None = None
        self._buttons = Qt.MouseButtons()
        self.setMinimumSize(QSize(320, 240))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWindowTitle("3D Viewport")

    # ---- model -----------------------------------------------------------
    def set_document(self, doc: Document):
        self._doc = doc
        self.refresh(fit=True)

    def refresh(self, fit: bool = False):
        solid = self._doc.result if self._doc else None
        if solid is None:
            self._r.clear_mesh()
            self._bbox = None
        else:
            v, n, f = solid.to_render_arrays()
            self._r.set_mesh(v, n, f)
            self._bbox = solid.bounding_box
            self._r._grid_auto(self._bbox)
            if fit:
                self._cam.fit(self._bbox)
        self.update()

    def solid(self) -> Solid | None:
        return self._doc.result if self._doc else None

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
        self._cube.place(self.width(), self.height())
        self._cube.draw(p, self._cam)
        p.end()

    # ---- mouse (Fusion default scheme) ------------------------------------
    # LMB: select (picking lands in M4)   MMB drag: orbit
    # Shift+MMB drag: pan                  wheel: zoom at cursor-ish depth
    # MMB click (no drag): return home
    def mousePressEvent(self, ev):
        hit = self._cube.hit(ev.position())
        if hit:
            self._cam.set_view(hit)
            self.update()
            ev.accept()
            return
        self._last = ev.position().toPoint()
        self._buttons |= ev.button()
        self._dragged = False
        if ev.button() == Qt.MiddleButton:
            self.setCursor(QCursor(Qt.ClosedHandCursor))

    def mouseMoveEvent(self, ev):
        if self._last is None:
            return
        d = ev.position().toPoint() - self._last
        if d.manhattanLength() > 2:
            self._dragged = True
        self._last = ev.position().toPoint()
        if Qt.MiddleButton in self._buttons:
            if ev.modifiers() & Qt.ShiftModifier:
                self._cam.pan(d.x(), d.y(), self.height())
            else:
                self._cam.orbit(d.x(), d.y(), self.height())
            self.update()
        elif Qt.RightButton in self._buttons:
            self._cam.orbit(d.x(), d.y(), self.height())
            self.update()

    def mouseReleaseEvent(self, ev):
        self._buttons &= ~ev.button()
        if ev.button() == Qt.MiddleButton:
            self.unsetCursor()
            if not getattr(self, "_dragged", False):
                self.home()
        if not (self._buttons & (Qt.MiddleButton | Qt.RightButton)):
            self.unsetCursor()

    def wheelEvent(self, ev):
        self._cam.zoom(pow(1.0015, -ev.angleDelta().y()))
        self.update()

    # ---- picking (double-click a planar face -> sketch on it) ---------------
    def _shoot(self, tm, px: float, py: float):
        o, d = self._cam.ray(px, py, self.width(), self.height())
        # NB: trimesh returns (locations, index_RAY, index_TRI)
        locs, _, itri = tm.ray.intersects_location([o], [d],
                                                   multiple_hits=False)
        if len(locs) == 0:
            return None
        return locs[0], tm.face_normals[itri[0]]

    def _pick_planar(self, pos):
        """Hit test at pos; accept only faces flat within ~2 degrees across
        a +/-3 px neighbourhood (kills cylinders/cones hiding in meshes)."""
        solid = self._doc.result if self._doc else None
        if solid is None:
            return None
        tm = solid.to_trimesh()
        hit = self._shoot(tm, pos.x(), pos.y())
        if hit is None:
            return None
        point, n0 = hit
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

    # ---- keys (F fit, G grid, 0/1/2/3 views) -------------------------------
    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key_F:
            if self._bbox is not None:
                self._cam.fit(self._bbox)
        elif k == Qt.Key_G:
            self._r.show_grid = not self._r.show_grid
        elif k == Qt.Key_E:
            self._r.show_edges = not self._r.show_edges
        elif k == Qt.Key_0:
            self._cam.set_view("iso")
        elif k == Qt.Key_1:
            self._cam.set_view("front")
        elif k == Qt.Key_2:
            self._cam.set_view("top")
        elif k == Qt.Key_3:
            self._cam.set_view("right")
        else:
            super().keyPressEvent(ev)
        self.update()

    # ---- helpers ------------------------------------------------------------
    def camera(self) -> Camera:
        return self._cam
