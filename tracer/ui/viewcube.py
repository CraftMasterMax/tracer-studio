"""Mini ViewCube: real 3D projection of a labeled cube in the viewport
corner. M44b shipped the three camera-facing faces as clickable views;
M154 grew the full 26-zone map the vendors really have (contract
research/m154_viewcube_zones.md, receipts research/m154_spike1.md):
6 faces + 12 edges + 8 corners, resolved through an offscreen PICK
BUFFER (Format_RGB32, antialiasing OFF, 24-bit ids — AA would blend
two ids into a third that never existed). Clicks land on the table's
own (yaw,pitch); corner views are TRUE isometric at the measured
asin(1/sqrt3) = 35.264390 deg, which the hand-set "home" iso (28 deg)
is NOT — and stays untouched. Zone names here are our own (clean room:
the checklist's LGPL reference ids FrontTop... informed the SHAPE of
the taxonomy, never the strings)."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QImage, QPainter,
                           QPainterPath, QPen, QPolygonF)

from .camera import Camera, perspective
from .theme import VIEWCUBE

SIZE = 66          # cube corner-to-corner px (LOGICAL; settings wait)
MARGIN = 12

# ---- the 26 zones as DATA (L4.1; spike V1: yaw/pitch carries them all)
_FACE_DIR = {"front": (0, -1, 0), "back": (0, 1, 0), "right": (1, 0, 0),
             "left": (-1, 0, 0), "top": (0, 0, 1), "bottom": (0, 0, -1)}
_FACE_ORDER = ("front", "back", "right", "left", "top", "bottom")

ZONES: dict[str, tuple] = dict(_FACE_DIR)
for _i in range(6):
    for _j in range(_i + 1, 6):
        _a, _b = _FACE_ORDER[_i], _FACE_ORDER[_j]
        _va = np.array(_FACE_DIR[_a], float)
        _vb = np.array(_FACE_DIR[_b], float)
        if abs(float(_va @ _vb)) > 1e-12:
            continue                              # opposite: no edge
        _d = _va + _vb
        ZONES[f"{_a}-{_b}"] = tuple(_d / np.linalg.norm(_d))
for _sx in (1, -1):
    for _sy in (1, -1):
        for _sz in (1, -1):
            _n = (f"corner {'front' if _sy == -1 else 'back'}-"
                  f"{'top' if _sz == 1 else 'bottom'}-"
                  f"{'right' if _sx == 1 else 'left'}")
            ZONES[_n] = (_sx / math.sqrt(3.0), _sy / math.sqrt(3.0),
                         _sz / math.sqrt(3.0))
assert len(ZONES) == 26
ZONE_IDS = list(ZONES)             # pick id = index + 1; 0 is free space


def zone_look(name: str) -> tuple:
    """(yaw, pitch) the camera must take to LOOK ALONG the zone's
    direction. Faces agree BYTE-EXACTLY with Camera.set_view (receipt
    V1 — including the +/-89 pole clamp); edges and corners fall out
    of camera.py's own forward law, corners at true iso."""
    d = np.array(ZONES[name], float)
    if name == "top":
        return 0.0, math.radians(89.0)
    if name == "bottom":
        return 0.0, math.radians(-89.0)
    return math.atan2(d[1], d[0]), math.asin(float(np.clip(d[2], -1, 1)))


# ---- drawing tables ------------------------------------------------------
# M154 RETARGET (cited, the milestone's second finding): the M44b table
# paired labels with the WRONG normals — "F"/front carried normal
# (0,0,-1), so at the shipped front view (camera at -Y) the face
# filling the widget center was the one LABELED D. The loop was
# self-consistent (center click re-set the same view), but the LETTER
# lied: L3.1's counter-rotation law demands that the face marked "F"
# faces the viewer when the camera stands at front. The pairing below
# is the honest one (front<=>-Y, top<=>+Z, right<=>+X — matching
# Camera.set_view's own documented geometry); old gates that only ask
# "does the cube answer" cannot see the difference, gates that ask
# WHICH face now get the truth.
FACES = [  # (corners idx, normal, label, view-kind)
    ((0, 1, 5, 4), (0, -1, 0.0), "F", "front"),    # -Y
    ((3, 2, 6, 7), (0, 1, 0.0), "B", "back"),      # +Y
    ((1, 2, 6, 5), (1, 0, 0.0), "R", "right"),     # +X
    ((0, 3, 7, 4), (-1, 0, 0.0), "L", "left"),     # -X
    ((4, 5, 6, 7), (0, 0, 1.0), "T", "top"),       # +Z
    ((0, 1, 2, 3), (0, 0, -1.0), "D", "bottom"),   # -Z
]
# local cube coords (x right, y depth, z up); corners:
C = np.array([
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
], float) * 0.5

# per corner-vertex: which zone names own it, per face side: the edge
_SIDE_ZONE = {}                                  # frozenset(2 corners)
for _k, (_idx, _nrm, _lab, _kind) in enumerate(FACES):
    for _p in range(4):
        _pair = frozenset((_idx[_p], _idx[(_p + 1) % 4]))
        _SIDE_ZONE.setdefault(_pair, []).append(_kind)
_EDGE_OF = {}                                    # pair -> canonical name
for _pair, _ks in _SIDE_ZONE.items():
    _a, _b = sorted(_ks, key=_FACE_ORDER.index)
    _EDGE_OF[_pair] = f"{_a}-{_b}" if _a in ZONES else None
_CORNER_OF = {}                                  # vertex -> corner zone
for _v in range(8):
    _sx, _sy, _sz = (1 if c > 0 else -1 for c in C[_v])
    _CORNER_OF[_v] = (f"corner {'front' if _sy == -1 else 'back'}-"
                      f"{'top' if _sz == 1 else 'bottom'}-"
                      f"{'right' if _sx == 1 else 'left'}")

HIT_CHAMFER = 0.22       # [ours] generous hit band: L4.2's arithmetic
#   proves vendor-thin 0.1 bands are un-hittable without a pick buffer;
#   WITH one we still choose a pointer-friendly ring, said out loud.


def _qcol(i: int) -> QColor:
    """pick id -> colour (V4: Format_RGB32 pixels read BIG-endian
    0xRRGGBB, so the id rides the full 24 bits, never one byte)."""
    return QColor((i >> 16) & 255, (i >> 8) & 255, i & 255)


def auto_size(viewport_w: int, viewport_h: int) -> int:
    """M155 (L10.3 is a PROPOSAL, this formula is OURS — receipt V5):
    AUTO grows the cube on big screens and keeps the shipped 66 px
    continuity on ours: clamp(round(0.08 x min side), 60, 140)."""
    return max(60, min(140, round(0.08 * min(viewport_w, viewport_h))))


class ViewCube:
    def __init__(self):
        self.rect = QRectF(0, 0, SIZE, SIZE)
        self.size_px = SIZE              # LOGICAL (L10.5; AUTO mode
        #   is the viewport's decision, this is the outcome)
        self.corner = "top-right"        # L10.1 corner picker
        self._screen: dict = {}     # label -> (path_pts_2d, view_kind)
        self._zones: dict = {}      # zone name -> list of QPolygonF pts
        self._pick: QImage | None = None
        self._pick_dpr = 1.0

    def place(self, widget_w: int, widget_h: int):
        s, m = self.size_px, MARGIN
        h = s * 0.86
        x = m if self.corner.endswith("left") else widget_w - s - m
        y = m if self.corner.startswith("top") else widget_h - h - m
        self.rect = QRectF(x, y, s, h)
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

    def _visible_faces(self, camera):
        ndc, view, eye = self.project(camera)
        Rv = view[:3, :3]
        vis = []
        for idx, nrm, label, kind in FACES:
            wn = np.array(nrm, float)
            fc = C[list(idx)].mean(axis=0)
            if wn @ (eye - fc) <= 0:
                continue
            vis.append(((Rv @ fc)[2], idx, label, kind, wn, fc))
        return ndc, sorted(vis), eye

    def draw(self, p: QPainter, camera: Camera, hover: str | None = None,
             dpr: float = 1.0):
        p.setRenderHint(QPainter.Antialiasing)
        ndc, vis, eye = self._visible_faces(camera)
        pts = {i: self._to_px(ndc[i], self.rect) for i in range(8)}
        self._screen = {}
        self._zones = {}
        layers = []                                # paint order (both
        #   buffer and screen share it: face full -> edge -> corner ->
        #   core; ids agree by construction, hover IS the pick id)
        for z_view, idx, label, kind, wn, fc in vis:
            ring = [pts[i] for i in idx]
            core = []
            cx = sum(q.x() for q in ring) / 4.0
            cy = sum(q.y() for q in ring) / 4.0
            s = 1.0 - 2.0 * HIT_CHAMFER
            for q in ring:
                core.append(QPointF(cx + (q.x() - cx) * s,
                                    cy + (q.y() - cy) * s))
            layers.append((kind, ring))
            for n in range(4):
                a, b = idx[n], idx[(n + 1) % 4]
                zname = _EDGE_OF[frozenset((a, b))]
                if zname:
                    layers.append((zname, [pts[a], pts[b], core[(n + 1) % 4],
                                           core[n]]))
            for n in range(4):                    # wedges: vertex + the
                v = idx[n]                        #   two neighbouring
                zname = _CORNER_OF[v]             #   core corners
                layers.append((zname, [pts[v], core[(n - 1) % 4],
                                       core[(n + 1) % 4]]))
            layers.append((kind, core))
        # the pick buffer: SAME geometry, flat ids, AA OFF, NoPen
        bw = max(1, int(round(self.rect.width() * dpr)))
        bh = max(1, int(round(self.rect.height() * dpr)))
        buf = QImage(bw, bh, QImage.Format.Format_RGB32)
        buf.fill(0)
        bp = QPainter(buf)
        for zname, ring in layers:
            poly = QPolygonF([QPointF((q.x() - self.rect.left()) * dpr,
                                      (q.y() - self.rect.top()) * dpr)
                              for q in ring])
            bp.setBrush(_qcol(ZONE_IDS.index(zname) + 1))
            bp.setPen(Qt.PenStyle.NoPen)
            bp.drawPolygon(poly)
        bp.end()
        self._pick = buf
        self._pick_dpr = dpr
        # the visible cube (M44b/M63 law unchanged for faces)
        for z_view, idx, label, kind, wn, fc in vis:
            path = QPainterPath()
            ring = [pts[i] for i in idx]
            path.moveTo(ring[0])
            for q in ring[1:]:
                path.lineTo(q)
            path.closeSubpath()
            to_eye_v = eye - fc
            cos_view = float(wn @ to_eye_v / max(
                np.linalg.norm(to_eye_v), 1e-9))
            front = cos_view > 0.75
            hot = hover == kind               # hover==id law (L5.4)
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
        # edge/corner hover rides the SAME buffer geometry (per-region
        # glow, never a whole-cube wash — L5.4)
        if hover and hover not in _FACE_DIR:
            p.setBrush(QColor(VIEWCUBE["hover"]))
            p.setPen(QPen(QColor(VIEWCUBE["hover_edge"]), 1))
            for zname, ring in layers:
                if zname == hover:
                    p.drawPolygon(QPolygonF(ring))

    # ---- hit test ------------------------------------------------------------
    def hit(self, pos: QPointF, dpr: float | None = None) -> str | None:
        """The buffer answers, not rectangle maths (L4.3). Unknown
        pixel (a 1-px seam) repairs from the 4-neighbourhood (L4.4);
        free space is None — the Backside flip waits for a widget
        that can SEE the far side (receipt V5, said out loud)."""
        if not self.rect.adjusted(-8, -8, 8, 8).contains(pos):
            return None
        buf = self._pick
        if buf is None:
            return None
        # the buffer was painted at self._pick_dpr; pos arrives in the
        # SAME logical widget coords the draw used (the viewport hands
        # it raw), so scale by the buffer's own truth, never the ask.
        x = int(round((pos.x() - self.rect.left()) * self._pick_dpr))
        y = int(round((pos.y() - self.rect.top()) * self._pick_dpr))
        if not (0 <= x < buf.width() and 0 <= y < buf.height()):
            return None

        def at(px, py):
            if not (0 <= px < buf.width() and 0 <= py < buf.height()):
                return 0
            return buf.pixel(px, py) & 0xFFFFFF

        i = at(x, y)
        if i == 0:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                j = at(x + dx, y + dy)
                if j:
                    i = j
                    break
        if i == 0:
            return None
        return ZONE_IDS[i - 1]


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

    def place(self, widget_w: int, top_y: float, corner: str = "top-right"):
        x = (MARGIN if corner.endswith("left")
             else widget_w - self.SIZE - MARGIN)
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
