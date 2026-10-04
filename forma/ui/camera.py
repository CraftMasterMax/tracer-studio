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

    def proj_matrix(self, aspect: float) -> np.ndarray:
        radius = max(self.distance, 1e-3)
        return perspective(self.fov, aspect, max(radius * 0.002, 0.05),
                           radius * 20.0)

    # ---- interaction -------------------------------------------------------
    def orbit(self, dx_px: float, dy_px: float, view_h_px: float):
        self.yaw += math.radians(dx_px * 0.4)
        self.pitch += math.radians(dy_px * 0.4)
        lim = math.radians(89.0)
        self.pitch = max(-lim, min(lim, self.pitch))

    def zoom(self, factor: float):
        self.distance = max(1e-3, min(1e9, self.distance * factor))

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
        """'front' (-Y), 'top' (+Z), 'right' (+X), 'iso'."""
        if kind == "top":
            self.yaw, self.pitch = 0.0, math.radians(89.0)
        elif kind == "front":
            self.yaw, self.pitch = -math.radians(90.0), 0.0
        elif kind == "right":
            self.yaw, self.pitch = 0.0, 0.0
        else:
            self.yaw, self.pitch = math.radians(45.0), math.radians(28.0)
