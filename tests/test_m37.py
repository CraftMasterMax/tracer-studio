"""M37 — Fusion navigation & selection grammar.

The single most "Fusion-feeling" layer of the app: MMB drags PAN and
Shift+MMB (or RMB) ORBIT, the wheel zooms TOWARD the cursor (the point
under it stays pinned, the exact perspective answer), and a left-drag on
empty space is Fusion's rubber-band: left→right is a WINDOW (only faces
fully inside), right→left is CROSSING (anything the box touches).
Selections are whole coplanar face groups and now wear Fusion orange.

Camera math is tested pure-numpy; gestures run through real Qt events on
the offscreen viewport with two known boxes so counts are exact.
"""
import math

import numpy as np
import pytest

from tracer.ui.camera import Camera

W, H = 800, 600


def _cam():
    c = Camera()
    c.fit([[-10, -10, 0], [10, 10, 20]])
    return c


# ---- camera: project / zoom_to ----------------------------------------------

def test_project_puts_the_target_at_screen_center():
    c = _cam()
    px = c.project(c.target, W, H)
    assert px is not None
    assert px[0] == pytest.approx(W / 2, abs=0.01)
    assert px[1] == pytest.approx(H / 2, abs=0.01)


def test_project_inverts_ray():
    c = _cam()
    o, d = c.ray(240, 420, W, H)
    p = o + d * (c.distance * 1.5)
    back = c.project(p, W, H)
    assert back[0] == pytest.approx(240, abs=0.5)
    assert back[1] == pytest.approx(420, abs=0.5)


def test_points_behind_the_camera_do_not_project():
    c = _cam()
    behind = c.position - (c.target - c.position)   # mirror past the eye
    assert c.project(behind, W, H) is None


def test_zoom_to_pins_the_cursor_point():
    c = _cam()
    o, d = c.ray(610, 130, W, H)
    anchor = o + d * c.distance                     # point under cursor
    before = c.project(anchor, W, H)
    c.zoom_to(0.5, anchor)
    after = c.project(anchor, W, H)
    assert after[0] == pytest.approx(before[0], abs=0.02)
    assert after[1] == pytest.approx(before[1], abs=0.02)
    assert c.distance == pytest.approx(_cam().distance * 0.5)


def test_zoom_to_at_the_target_is_plain_zoom():
    c = _cam()
    t0 = c.target.copy()
    c.zoom_to(2.0, t0)
    assert np.allclose(c.target, t0)
    assert c.distance == pytest.approx(_cam().distance * 2.0)


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt                    # noqa: E402
from PySide6.QtGui import QMouseEvent                                     # noqa: E402
from PySide6.QtTest import QTest                                          # noqa: E402
from PySide6.QtWidgets import QApplication                                # noqa: E402

from tracer.core.document import Document, PrimitiveFeature          # noqa: E402
from tracer.ui.mainwindow import MainWindow                          # noqa: E402
from tracer.ui.renderer import SceneRenderer                         # noqa: E402
from tracer.ui.theme import DARK                                     # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


def _two_boxes(win, qapp):
    """Two 20mm cubes far apart — twelve logical faces to select."""
    win.new_document()
    win.doc.add(PrimitiveFeature(name="A", kind="box",
                                 dims={"dx": 20, "dy": 20, "dz": 20},
                                 placement=(-50.0, -10.0, 0.0)))
    win.doc.add(PrimitiveFeature(name="B", kind="box",
                                 dims={"dx": 20, "dy": 20, "dz": 20},
                                 placement=(30.0, -10.0, 0.0)))
    win.recompute()
    win._show_page(win.viewport)
    win.action_view("iso")
    win.viewport.refresh(fit=True)
    qapp.processEvents()
    return win.viewport


def _drag(cv, qapp, button, start, end, mods=Qt.NoModifier):
    """Press → move(holding) → release.  This PySide6 QTest.mouseMove only
    takes (widget, pos) without button state, so the move is a real
    QMouseEvent — same handler path a physical drag takes."""
    QTest.mousePress(cv, button, mods, QPoint(*start), 10)
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(*end), QPointF(*end),
                     QPointF(*end), button, button, mods)
    QApplication.sendEvent(cv, ev)
    QTest.mouseRelease(cv, button, mods, QPoint(*end), 10)
    qapp.processEvents()


def _pixel_of(cam, cv, pt):
    return tuple(int(round(v)) for v in cam.project(pt, cv.width(),
                                                    cv.height()))


# ---- mouse roles: Fusion's scheme --------------------------------------------

def test_mmb_orbits_and_shift_pans(win, qapp):
    cv = _two_boxes(win, qapp)
    cam = cv._cam
    yaw0, t0 = cam.yaw, cam.target.copy()
    _drag(cv, qapp, Qt.MiddleButton, (500, 350), (530, 365))
    assert cam.yaw != pytest.approx(yaw0)           # MMB: orbits (Fusion)
    assert np.linalg.norm(cam.target - t0) < 1e-6   # ...no panning
    yaw1, t1 = cam.yaw, cam.target.copy()
    _drag(cv, qapp, Qt.MiddleButton, (500, 350), (535, 365),
          Qt.ShiftModifier)
    assert cam.yaw == pytest.approx(yaw1)           # Shift+MMB: pans
    assert np.linalg.norm(cam.target - t1) > 1.0    # ...no orbiting
    yaw2 = cam.yaw
    _drag(cv, qapp, Qt.RightButton, (500, 350), (465, 340))
    assert cam.yaw != pytest.approx(yaw2)           # RMB orbits too


class _Pos:
    def __init__(self, x, y):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


class _Delta:
    def __init__(self, y):
        self._y = y

    def y(self):
        return self._y


class _Wheel:
    def __init__(self, x, y, dy):
        self._p, self._d = _Pos(x, y), _Delta(dy)

    def position(self):
        return self._p

    def angleDelta(self):
        return self._d


# ---- wheel: zoom toward the cursor -------------------------------------------

def test_wheel_zooms_toward_the_cursor(win, qapp):
    cv = _two_boxes(win, qapp)
    px, py = _pixel_of(cv._cam, cv, (-40.0, 0.0, 20.0))   # box A top face
    hit = cv._shoot(cv._tm, px, py)
    assert hit is not None                          # model under cursor
    anchor = np.asarray(hit[0], float)
    # Sample the viewport size ONCE: zoom_to pins the cursor fraction, so
    # a stray layout pass between the two project() calls must not be
    # able to fake (or mask) the drift this test measures.
    vw, vh = cv.width(), cv.height()
    before = cv._cam.project(anchor, vw, vh)
    d0, t0 = cv._cam.distance, cv._cam.target.copy()
    cv.wheelEvent(_Wheel(px, py, 120))
    qapp.processEvents()
    after = cv._cam.project(anchor, vw, vh)
    assert cv._cam.distance < d0                    # zoomed in
    assert not np.allclose(cv._cam.target, t0)      # target dove at anchor
    assert abs(after[0] - before[0]) < 2.0          # anchor stayed put
    assert abs(after[1] - before[1]) < 2.0


def test_wheel_above_the_horizon_pure_dollies(win, qapp):
    cv = _two_boxes(win, qapp)
    t0 = cv._cam.target.copy()
    d0 = cv._cam.distance
    cv.wheelEvent(_Wheel(cv.width() - 2, 2, -240))  # sky corner, zoom out
    qapp.processEvents()
    assert cv._cam.distance > d0
    assert np.isfinite(cv._cam.target).all()


# ---- rubber-band selection ----------------------------------------------------

def test_window_box_grabs_everything_inside(win, qapp):
    cv = _two_boxes(win, qapp)
    cv._select_box(QPoint(2, 2), QPoint(cv.width() - 2, cv.height() - 2))
    assert len(cv.selected_groups()) == 12          # both cubes, all faces
    assert len(cv._sel) > 0


def test_crossing_box_only_needs_to_touch(win, qapp):
    cv = _two_boxes(win, qapp)
    # one cube in front view: a narrow band must hit exactly the four
    # side faces (top/bottom project to lines outside the band)
    win.doc.features = win.doc.features[:1]
    win.recompute()
    cv._cam.set_view("front")
    cv.refresh(fit=True)
    qapp.processEvents()
    lo, hi = win.doc.result.bounding_box
    mid = (lo[1] + hi[1]) / 2
    z0, rz = lo[2], (hi - lo)[2]
    top = cv._cam.project([(lo + hi)[0] / 2, mid, z0 + rz * 0.35],
                          cv.width(), cv.height())   # band from z 7 mm
    bot = cv._cam.project([(lo + hi)[0] / 2, mid, z0 + rz * 0.65],
                          cv.width(), cv.height())   # ...to z 13 mm
    x_r = cv._cam.project([hi[0] + 30, mid, (lo + hi)[2] / 2],
                          cv.width(), cv.height())
    x_l = cv._cam.project([lo[0] - 30, mid, (lo + hi)[2] / 2],
                          cv.width(), cv.height())
    cv._select_box(QPoint(int(x_r[0]), int(top[1])),
                   QPoint(int(x_l[0]), int(bot[1])))   # right→left
    assert len(cv.selected_groups()) == 4


def test_empty_box_clears_and_gesture_routes_from_a_drag(win, qapp):
    cv = _two_boxes(win, qapp)
    cv._select_box(QPoint(4, 4), QPoint(9, 9))      # tiny, off in the sky
    assert len(cv.selected_groups()) == 0
    _drag(cv, qapp, Qt.LeftButton, (5, 5),
          (cv.width() - 6, cv.height() - 6))        # LMB drag on empty
    assert len(cv.selected_groups()) == 12          # reached _select_box


def test_click_select_then_click_empty_clears(win, qapp):
    cv = _two_boxes(win, qapp)
    centre = _pixel_of(cv._cam, cv, (-40.0, 0.0, 20.0))   # box A top face
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, QPoint(*centre), 10)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, QPoint(*centre), 10)
    qapp.processEvents()
    assert len(cv.selected_groups()) >= 1
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, QPoint(3, 3), 10)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, QPoint(3, 3), 10)
    qapp.processEvents()
    assert len(cv.selected_groups()) == 0


def test_selection_is_fusion_blue():
    # M112: the unified theme picks geometry in autodeskBlue; the 2019
    # orange lives on HOVER now, as the famous peach
    r, g, b = DARK["hi_sel"]
    assert b >= 0.8 and r <= 0.2
    hr, hg, hb = DARK["hi_hover"]
    assert hr >= 0.85 and hb <= 0.55


# ---- proof of life ------------------------------------------------------------

def test_screenshot_proof(win, qapp):
    import os
    cv = _two_boxes(win, qapp)
    cv._select_box(QPoint(2, 2), QPoint(cv.width() - 2, cv.height() - 2))
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m37_boxselect.png")
