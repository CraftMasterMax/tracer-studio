"""M156 — the cube is draggable. §8's laws, each executed as a
receipt first (spike_m156/live_m156.py, all green at 9e41e2e) against
research/m156_cube_drag.md. The choreography is the milestone: press
ARMS (M155's highlight law unchanged), release DECIDES — under the
3.0-px law the click table answers verbatim (M154's moment moved to
release, cited; the table never moved), past it the drag owns the
camera and the click NEVER fires; snap-to-nearest glides on M154's
transition law. The upright lock is structural (a yaw/pitch camera)
and gated anyway."""
import math
import time

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from tracer.core.document import Document, PrimitiveFeature
from tracer.ui.camera import Camera
from tracer.ui.viewcube import (ZONE_IDS, ZONES, nearest_zone,
                                zone_look)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def vp(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    w.new_document()
    d = Document("drag")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    w.doc = d
    w.recompute()
    for _ in range(12):
        qapp.processEvents()
        time.sleep(0.02)
    yield w.viewport
    w._unsaved = False
    w.close()
    qapp.processEvents()


def _m(vpx, kind, pos, button):
    btns = button if kind in (QEvent.Type.MouseButtonPress,
                              QEvent.Type.MouseMove,
                              QEvent.Type.MouseButtonRelease) else \
        Qt.MouseButton.NoButton
    return QMouseEvent(kind, QPointF(pos), QPointF(pos), button,
                       btns, Qt.KeyboardModifier.NoModifier)


def _press(vp, pos):
    vp.mousePressEvent(_m(vp, QEvent.Type.MouseButtonPress, pos,
                          Qt.MouseButton.LeftButton))


def _move(vp, pos):
    vp.mouseMoveEvent(_m(vp, QEvent.Type.MouseMove, pos,
                         Qt.MouseButton.NoButton))


def _release(vp, pos):
    vp.mouseReleaseEvent(_m(vp, QEvent.Type.MouseButtonRelease, pos,
                            Qt.MouseButton.LeftButton))


def _cube_center(vp):
    vp._cube.place(vp.width(), vp.height())
    return QPointF(vp._cube.rect.center())


def _settle(vp, qapp, ms=2500):
    t0 = time.monotonic()
    while vp._anim is not None and (time.monotonic() - t0) < ms / 1000:
        qapp.processEvents()
        time.sleep(0.01)


# ---- G1: press ARMS, under-threshold release == the old law ---------------

def test_press_arms_and_under_threshold_release_clicks(vp, qapp):
    vp.view_anim_s = 0.0
    c = _cube_center(vp)
    zone = vp._cube.hit(c)
    assert zone is not None
    y0, p0 = vp._cam.yaw, vp._cam.pitch
    _press(vp, c)
    assert vp._cube_drag is not None           # armed, not fired
    assert (vp._cam.yaw, vp._cam.pitch) == (y0, p0)   # press alone
    #                                                   never steers
    _move(vp, QPointF(c.x() + 1, c.y() + 1))   # sqrt2 < 3.0
    _release(vp, QPointF(c.x() + 1, c.y() + 1))
    assert (vp._cam.yaw, vp._cam.pitch) == zone_look(zone)   # the
    #   M154 table, answered at RELEASE now (cited moment-move)
    assert vp._cube_last is not None


# ---- G2/G4: a drag NEVER fires the click; the flag is sticky --------------

def test_past_threshold_release_never_clicks(vp, qapp):
    vp.view_anim_s = 0.0
    vp.cube_snap = False                       # the pure refusal door
    c = _cube_center(vp)
    vp._cam.set_view("iso")
    y0, p0 = vp._cam.yaw, vp._cam.pitch
    _press(vp, c)
    _move(vp, QPointF(c.x() + 40, c.y() + 12))
    y1, p1 = vp._cam.yaw, vp._cam.pitch
    assert (y1, p1) != (y0, p0)                # the drag ORBITED
    _release(vp, QPointF(c.x() + 40, c.y() + 12))
    assert (vp._cam.yaw, vp._cam.pitch) == (y1, p1)  # click law did
    assert vp._cube_last is None               #   NOT run: no glide,
    #     no double-fit, no table landing
    for z in ZONES:                            # and it sits on NO
        assert (vp._cam.yaw, vp._cam.pitch) != zone_look(z)


def test_drag_flag_is_sticky(vp, qapp):
    vp.view_anim_s = 0.0
    vp.cube_snap = False
    c = _cube_center(vp)
    _press(vp, c)
    _move(vp, QPointF(c.x() + 60, c.y()))      # past 3.0
    _move(vp, QPointF(c.x() + 1, c.y()))       # drift back under it
    _release(vp, QPointF(c.x() + 1, c.y()))
    assert vp._cube_last is None               # V4: a drag that
    #   wandered back cannot un-drag or double-fit


# ---- G3: snap lands EXACTLY on the nearest of the 26 ----------------------

def test_snap_on_glides_to_the_nearest(vp, qapp):
    vp.view_anim_s = 0.05
    vp.cube_snap = True
    vp._cam.set_view("iso")
    c = _cube_center(vp)
    _press(vp, c)
    _move(vp, QPointF(c.x() + 40, c.y() + 12))
    _release(vp, QPointF(c.x() + 40, c.y() + 12))
    target = zone_look(nearest_zone(vp._cam))  # nearest from the LIVE
    assert vp._anim is not None                # the glide is in flight
    _settle(vp, qapp)
    assert (vp._cam.yaw, vp._cam.pitch) == target  # lands EXACT


# ---- G5: the upright lock is structural (L8.5) ----------------------------

def test_a_violent_drag_never_flips_a_pole(vp, qapp):
    vp.cube_snap = False
    c = _cube_center(vp)
    _press(vp, c)
    y, p = c.x(), c.y()
    for _ in range(2000):
        p += 40.0                              # a relentless down-drag
        _move(vp, QPointF(y, p))
        assert abs(vp._cam.pitch) <= math.radians(89.0) + 1e-12
    _release(vp, QPointF(y, p))
    assert abs(vp._cam.pitch) <= math.radians(89.0) + 1e-12


# ---- G6: the snap table (receipt V3, in-product) ---------------------------

def test_nearest_zone_is_total_self_maximal_and_tied_by_order():
    cam = Camera()
    for name in ZONE_IDS:                       # self-maximal
        cam.yaw, cam.pitch = zone_look(name)
        assert nearest_zone(cam) == name, name
    cam.yaw, cam.pitch = zone_look("front")     # a real bisector tie:
    bis = np.array([ZONES["front"][0] + ZONES["front-top"][0],
                    ZONES["front"][1] + ZONES["front-top"][1],
                    ZONES["front"][2] + ZONES["front-top"][2]], float)
    bis /= np.linalg.norm(bis)
    cam.yaw = math.atan2(bis[1], bis[0])
    cam.pitch = math.asin(bis[2])
    assert abs(float(np.array(ZONES["front"]) @ bis)
               - float(np.array(ZONES["front-top"]) @ bis)) < 1e-12
    assert nearest_zone(cam) == "front"         #   TABLE ORDER wins
    rng = np.random.default_rng(156)
    for _ in range(500):
        v = rng.normal(size=3)
        n = norm = np.linalg.norm(v)
        cam.yaw = math.atan2(v[1] / n, v[0] / n)
        cam.pitch = math.asin(v[2] / n)
        assert nearest_zone(cam) in ZONES


# ---- G7: the snap option persists ------------------------------------------

def test_snap_toggle_persists(vp, qapp):
    from PySide6.QtCore import QSettings
    before = vp.cube_snap
    vp._toggle_snap()
    assert vp.cube_snap is not before
    assert (str(QSettings().value("viewcube/snap_to_closest")
                ).lower() == "true") == vp.cube_snap
    vp._toggle_snap()
    assert vp.cube_snap is before
