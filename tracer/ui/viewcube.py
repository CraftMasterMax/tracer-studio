"""Mini ViewCube: real 3D projection of a labeled cube in the viewport
corner. The three camera-facing faces are clickable (Front/Top/Right and
their opposites rotate the model view like Fusion's)."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from .camera import Camera, perspective
from .theme import VIEWCUBE

SIZE = 66          # cube corner-to-corner px
MARGIN = 12

FACES = [  # (corners idx, normal, label, view-kind)
    ((0, 1, 2, 3), (0, 0, -1.0), "F", "front"),    # -Y
    ((4, 5, 6, 7), (0, 0, 1.0), "B", "back"),      # +Y
    ((1, 2, 6, 5), (1, 0, 0.0), "R", "right"),     # +X
    ((0, 3, 7, 4), (-1, 0, 0.0), "L", "left"),     # -X
    ((3, 2, 6, 7), (0, 1, 0.0), "T", "top"),       # +Z
    ((0, 1, 5, 4), (0, -1, 0.0), "D", "bottom"),   # -Z
]
# local cube coords (x right, y depth, z up); corners:
C = np.array([
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
], float) * 0.5


class ViewCube:
    def __init__(self):
        self.rect = QRectF(0, 0, SIZE, SIZE)
        self._screen: dict = {}     # label -> (path_pts_2d, view_kind)

    def place(self, widget_w: int, widget_h: int):
        self.rect = QRectF(widget_w - SIZE - MARGIN, MARGIN,
                           SIZE, SIZE * 0.86)
    # ---- drawing -----------------------------------------------------------
    def project(self, camera: Camera):
        cam = Camera(fov=30.0)
        cam.distance = 2.6
        cam.yaw, cam.pitch, cam.target = camera.yaw, camera.pitch, np.zeros(3)
        view = cam.view_matrix()
        proj = perspective(30.0, 1.0, 0.1, 20.0)
        vp = proj @ view
        eye = cam.position
        out = []
        for v in C:
            clip = vp @ np.append(v, 1.0)
            ndc = clip[:3] / clip[3]
            out.append(ndc)
        return np.array(out), view, eye

    @staticmethod
    def _to_px(ndc, rect):
        return QPointF(rect.left() + (ndc[0] * 0.5 + 0.5) * rect.width(),
                       rect.top() + (0.5 - ndc[1] * 0.5) * rect.height())

    def draw(self, p: QPainter, camera: Camera, hover: str | None = None):
        p.setRenderHint(QPainter.Antialiasing)
        ndc, view, eye = self.project(camera)
        Rv = view[:3, :3]
        visible = []
        for idx, nrm, label, kind in FACES:
            wn = np.array(nrm, float)
            face_center = C[list(idx)].mean(axis=0)
            to_eye = eye - face_center
            if wn @ to_eye <= 0:
                continue
            # camera looks down -z_view: nearer faces have larger z_view
            z_view = (Rv @ face_center)[2]
            visible.append((z_view, idx, label, kind, wn))
        self._screen = {}
        for z_view, idx, label, kind, wn in sorted(visible):
            path = QPainterPath()
            pts = [self._to_px(ndc[i], self.rect) for i in idx]
            path.moveTo(pts[0])
            for q in pts[1:]:
                path.lineTo(q)
            path.closeSubpath()
            to_eye_v = eye - face_center
            cos_view = float(wn @ to_eye_v / max(np.linalg.norm(to_eye_v), 1e-9))
            front = cos_view > 0.75
            hot = hover == kind               # hit() hands back the kind
            if hot:
                p.setBrush(QColor(VIEWCUBE["hover"]))
                p.setPen(QPen(QColor(VIEWCUBE["hover_edge"]), 1))
            else:
                p.setBrush(QColor(VIEWCUBE["face_front"] if front
                                 else VIEWCUBE["face"]))
                p.setPen(QPen(QColor(VIEWCUBE["edge"]), 1))
            p.drawPath(path)
            f = QFont(p.font())
            f.setPointSize(8)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(VIEWCUBE["text"]))
            p.drawText(path.boundingRect(), Qt.AlignCenter, label)
            self._screen[label] = (path, kind)

    # ---- hit test ------------------------------------------------------------
    def hit(self, pos: QPointF) -> str | None:
        if not self.rect.adjusted(-8, -8, 8, 8).contains(pos):
            return None
        best = None
        for label, (path, kind) in self._screen.items():
            if path.contains(pos):
                best = kind      # dict order = painter order; last drawn wins
        return best


class NavWidget:
    """Fusion's mini nav stack that sits under the ViewCube: Home,
    Zoom In, Zoom Out.  Pure geometry + hit-testing; the viewport owns
    the behaviour (same split as the cube itself)."""
    SIZE = 24
    GAP = 4

    KINDS = ("home", "in", "out")

    def __init__(self):
        self.rects: dict[str, QRectF] = {}
        self.hover: str | None = None

    def place(self, widget_w: int, top_y: float):
        x = widget_w - self.SIZE - MARGIN
        for i, kind in enumerate(self.KINDS):
            self.rects[kind] = QRectF(x, top_y + i * (self.SIZE + self.GAP),
                                      self.SIZE, self.SIZE)

    def hit(self, pos) -> str | None:
        for kind, r in self.rects.items():
            if r.contains(pos):
                return kind
        return None

    def set_hover(self, pos) -> bool:
        h = self.hit(pos)
        if h != self.hover:
            self.hover = h
            return True
        return False

    def draw(self, p: QPainter):
        for kind, r in self.rects.items():
            p.setBrush(QColor(VIEWCUBE["nav_hover"]) if self.hover == kind
                       else QColor(VIEWCUBE["nav_bg"]))
            p.setPen(QPen(QColor(VIEWCUBE["nav_edge"]), 1))
            p.drawRoundedRect(r, 5, 5)
            pen = QPen(QColor(VIEWCUBE["nav_glyph"]))
            pen.setWidthF(1.7)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            cx, cy = r.center().x(), r.center().y()
            if kind == "home":
                roof = QPainterPath()
                roof.moveTo(cx - 6, cy - 1)
                roof.lineTo(cx, cy - 6)
                roof.lineTo(cx + 6, cy - 1)
                p.drawPath(roof)
                p.drawRect(QRectF(cx - 4, cy - 1, 8, 6))
            elif kind == "in":
                p.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))
                p.drawLine(QPointF(cx, cy - 5), QPointF(cx, cy + 5))
            else:
                p.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))
