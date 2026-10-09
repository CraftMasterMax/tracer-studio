"""Orbit camera with pure-numpy matrices (Z-up, mm).

No Qt and no GL dependency here so the projection math is unit-testable
headless. Matrices are column-major 4x4, matching GLSL `mat4` uploads.
"""
from __future__ import annotations

import math

import numpy as np

_UP = np.array([0.0, 0.0, 1.0])


def look_at(eye, target, up=_UP) -> np.ndarray:
    eye, target, up = map(np.asarray, (eye, target, up))
    f = target - eye
    f = f / max(np.linalg.norm(f), 1e-12)
    s = np.cross(f, up)
    if np.linalg.norm(s) < 1e-9:  # looking straight down/up: pick a stable right
        s = np.array([1.0, 0.0, 0.0])
    s = s / np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -np.array([s @ eye, u @ eye, -f @ eye])
    return m


def perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    m = np.zeros((4, 4))
    m[0, 0] = f / max(aspect, 1e-9)
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


class Camera:
    def __init__(self, fov: float = 38.0):
        self.target = np.zeros(3)
        self.distance = 120.0
        self.yaw = math.radians(45.0)      # azimuth around Z
        self.pitch = math.radians(28.0)    # elevation, clamped to +/-89deg
        self.fov = fov
        self.model = np.eye(4)             # model matrix (identity for now)

    # ---- derived state ---------------------------------------------------
    @property
    def position(self) -> np.ndarray:
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        return self.target + self.distance * np.array(
            [cp * math.cos(self.yaw), cp * math.sin(self.yaw), sp])

    def view_matrix(self) -> np.ndarray:
        return look_at(self.position, self.target)

    def ray(self, px: float, py: float, w_px: float, h_px: float):
        """Screen pixel -> (world origin, unit direction)."""
        vp = self.proj_matrix(w_px / max(h_px, 1.0)) @ self.view_matrix()
        inv = np.linalg.inv(vp)
        nx, ny = 2 * px / w_px - 1.0, 1.0 - 2 * py / h_px
        near = inv @ np.array([nx, ny, -1.0, 1.0])
        far = inv @ np.array([nx, ny, 1.0, 1.0])
        near, far = near[:3] / near[3], far[:3] / far[3]
        d = far - near
        return near, d / max(np.linalg.norm(d), 1e-12)

    def proj_matrix(self, aspect: float) -> np.ndarray:
        radius = max(self.distance, 1e-3)
        return perspective(self.fov, aspect, max(radius * 0.002, 0.05),
                           radius * 20.0)

    # ---- interaction -------------------------------------------------------
    def screen_axes(self):
        """World X/Y/Z drawn as 2D vectors for the corner triad:
        [(label, (dx_right, dy_up), visible)] — 'visible' is False when
        the axis points away from the camera (the dimmed one)."""
        v = self.view_matrix()
        s, u = v[0, :3], v[1, :3]          # view basis right / up
        f = -v[2, :3]                      # look_at stores −forward
        out = []
        for i, lab in enumerate("XYZ"):
            e = np.zeros(3)
            e[i] = 1.0
            out.append((lab, (float(e @ s), float(e @ u)),
                        bool(float(e @ f) < 0.15)))
        return out

    def orbit(self, dx_px: float, dy_px: float, view_h_px: float):
        self.yaw += math.radians(dx_px * 0.4)
        self.pitch += math.radians(dy_px * 0.4)
        lim = math.radians(89.0)
        self.pitch = max(-lim, min(lim, self.pitch))

    def zoom(self, factor: float):
        self.distance = max(1e-3, min(1e9, self.distance * factor))

    def zoom_to(self, factor: float, anchor):
        """Zoom with the world point under the cursor pinned on screen:
        scale the whole rig (target AND position) about the anchor, which
        is the exact perspective answer — P' − A = k·(P − A)."""
        a = np.asarray(anchor, float)
        self.distance = max(1e-3, min(1e9, self.distance * factor))
        self.target = a + (self.target - a) * factor

    def project(self, pt, w_px: float, h_px: float):
        """World point -> screen pixel (x, y), or None if behind the
        camera.  The inverse of ray()."""
        vp = self.proj_matrix(w_px / max(h_px, 1.0)) @ self.view_matrix()
        c = vp @ np.append(np.asarray(pt, float), 1.0)
        if c[3] <= 1e-9:
            return None
        return ((c[0] / c[3] + 1.0) * 0.5 * w_px,
                (1.0 - c[1] / c[3]) * 0.5 * h_px)

    def pan(self, dx_px: float, dy_px: float, view_h_px: float):
        """Screen-space pan in mm, scaled by camera distance & fov."""
        mm_per_px = (2.0 * self.distance * math.tan(math.radians(self.fov) / 2.0)
                     / max(view_h_px, 1.0))
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        fwd = -np.array([cp * math.cos(self.yaw), cp * math.sin(self.yaw), sp])
        right = np.cross(fwd, _UP)
        right = right / max(np.linalg.norm(right), 1e-12)
        upv = np.cross(right, fwd)
        self.target = self.target + right * (-dx_px * mm_per_px) \
                      + upv * (dy_px * mm_per_px)

    # ---- framing ------------------------------------------------------------
    def fit(self, bbox: np.ndarray, margin: float = 1.35):
        bbox = np.asarray(bbox, float).reshape(2, 3)
        center = bbox.mean(axis=0)
        radius = max(float(np.linalg.norm(bbox[1] - bbox[0])) / 2.0, 1e-3)
        self.target = center
        self.distance = radius / math.sin(math.radians(self.fov) / 2.0) * margin

    def set_view(self, kind: str):
        self.yaw, self.pitch = view_orient(kind)


# the axis views as DATA (M154: the animation law needs the same
# orientations the instant law always shipped — one table, two doors).
# top/bottom carry the shipped +/-89 pole clamp (look_at degeneracy).
def view_orient(kind: str) -> tuple:
    """(yaw, pitch) for front (-Y), back (+Y), right (+X), left (-X),
    top, bottom, iso — byte-identical to the values set_view shipped
    since M20; iso stays the hand-picked 28-deg HOME art (the true
    isometric 35.264390 belongs to cube-corner clicks, receipt V2)."""
    deg = math.radians
    if kind == "top":
        return 0.0, deg(89.0)
    if kind == "bottom":
        return 0.0, deg(-89.0)
    if kind == "front":
        return deg(-90.0), 0.0
    if kind == "back":
        return deg(90.0), 0.0
    if kind == "right":
        return 0.0, 0.0
    if kind == "left":
        return deg(180.0), 0.0
    return deg(45.0), deg(28.0)
