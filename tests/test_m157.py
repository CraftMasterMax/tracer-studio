"""M157 — the cube gets its wrist. Every law here was executed as a
receipt first (spike_m157/live_m157.py, V1-V9 green at 2c27e92)
against research/m157_cube_wrist.md (checklist L4.1/L6.3a/L6.7/
L11.5/L12.5). The milestone's spine is ADDITIVITY: roll=0 IS the
shipped call — byte-exactness is structural, not lucky — so the
whole older suite riding green is not a hope, it is G1's theorem.
The compass is DEAD HERE by the checklist's OWN law (L11.5:
mechanical CAD has no North) — said, not painted."""
import math
import time

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QImage, QPainter, QMouseEvent
from PySide6.QtWidgets import QApplication

from tracer.core.document import Document, PrimitiveFeature
from tracer.ui.camera import Camera, look_at, view_orient
from tracer.ui.viewcube import (NavWidget, ViewCube, ZONES,
                                nearest_zone, zone_look)


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
    d = Document("wrist")
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


def _draw_cube(camera):
    img = QImage(400, 300, QImage.Format.Format_RGB32)
    img.fill(0)
    p = QPainter(img)
    cube = ViewCube()
    cube.place(400, 300)
    cube.draw(p, camera)
    p.end()
    arr = np.frombuffer(img.constBits(), np.uint8,
                        img.sizeInBytes()).reshape(300, 400, 4)
    return cube, arr[..., :3].astype(int)


# ---- G1: additive growth — roll=0 IS the shipped call --------------------

def test_roll_zero_is_the_shipped_matrix_byte_exact():
    cam = Camera()
    for name in ZONES:
        cam.yaw, cam.pitch = zone_look(name)
        cam.roll = 0.0
        assert np.array_equal(cam.view_matrix(),
                              look_at(cam.position, cam.target)), name
    cam.yaw, cam.pitch = view_orient("iso")
    assert np.array_equal(cam.view_matrix(),
                          look_at(cam.position, cam.target))


# ---- G2: the wrist in view space (receipt V2 in-product) ------------------

def test_roll_spins_the_view_at_unchanged_depth_and_radius():
    cam = Camera()
    cam.yaw, cam.pitch, cam.distance = 0.7, 0.4, 200.0
    cam.roll = 0.0
    p0 = cam.view_matrix() @ np.array([30.0, 10.0, 5.0, 1.0])
    cam.roll = math.pi / 2
    p90 = cam.view_matrix() @ np.array([30.0, 10.0, 5.0, 1.0])
    assert abs(p0[2] - p90[2]) < 1e-12             # depth frozen
    r0 = math.hypot(p0[0], p0[1])
    r90 = math.hypot(p90[0], p90[1])
    assert abs(r0 - r90) < 1e-12                   # radius frozen
    ang = math.atan2(p90[1], p90[0]) - math.atan2(p0[1], p0[0])
    ang = (ang + math.pi) % (2 * math.pi) - math.pi
    assert abs(abs(ang) - math.pi / 2) < 1e-9      # EXACTLY +/-90


# ---- G3: orbit spends nothing ---------------------------------------------

def test_orbit_preserves_the_wrist():
    cam = Camera()
    cam.roll = 1.1
    for _ in range(300):
        cam.orbit(7, -23, 720)
    assert cam.roll == 1.1
    assert abs(cam.pitch) <= math.radians(89.0) + 1e-12


# ---- G4: the cube RIDES the wrist (pixel differential) --------------------

def test_the_widget_rotates_with_the_wrist(qapp):
    cam = Camera()
    cam.yaw, cam.pitch, cam.distance = math.radians(-45), \
        math.radians(30), 2.6
    cam.roll = 0.0
    cube_a, px_a = _draw_cube(cam)
    r = cube_a.rect
    x0, y0, x1, y1 = int(r.left()), int(r.top()), \
        int(r.right()), int(r.bottom())
    cam.roll = math.pi / 2
    cube_b, px_b = _draw_cube(cam)
    a, b = px_a[y0:y1, x0:x1], px_b[y0:y1, x0:x1]
    turned = int((np.abs(a - b).sum(axis=2) > 30).sum())
    assert turned > 300, f"the widget never turned: {turned} px"
    # under roll the buffer still speaks ONLY the 26:
    seen = set()
    for yy in range(y0, y1, 3):
        for xx in range(x0, x1, 3):
            z = cube_b.hit(QPointF(xx + 0.5, yy + 0.5))
            if z is not None:
                seen.add(z)
    assert seen <= set(ZONES), seen - set(ZONES)
    cam.roll = 0.0                                  # and it REVERTS
    _, px_back = _draw_cube(cam)
    assert np.array_equal(px_a, px_back), \
        "paint is deterministic — the wrist was the only change"


# ---- G5: the arrows (L4.1 class, L6.7 step law) ----------------------------

def test_stack_carries_the_roll_doors():
    assert NavWidget.KINDS == ("home", "in", "out",
                               "roll-left", "roll-right")


def test_arrow_steps_land_exact(vp, qapp):
    vp.view_anim_s = 0.0
    vp.roll_steps = 4
    vp._cam.roll = 0.0
    vp._roll_by(+1)
    assert vp._cam.roll == math.pi / 2
    vp._roll_by(+1)                    # 180 -> the wrap passes -pi
    vp._roll_by(+1)
    vp._roll_by(+1)                    # V8: four clicks return EXACTLY
    assert vp._cam.roll == 0.0, vp._cam.roll
    vp.roll_steps = 8                  # 45-deg steps
    vp._roll_by(+1)
    assert abs(vp._cam.roll - math.pi / 4) < 1e-15
    vp.roll_steps = 2                  # clamp low: a rogue 2 can
    vp._cam.roll = 0.0                 #   NEVER smuggle a 180 step
    vp._roll_by(+1)
    assert vp._cam.roll == math.pi / 2
    vp._cam.roll = 0.0
    vp.roll_steps = 40                 # clamp high likewise
    vp._roll_by(+1)
    assert abs(vp._cam.roll - math.pi / 18) < 1e-12


def test_the_nav_button_itself_drives_the_wrist(vp, qapp):
    vp.view_anim_s = 0.0
    vp.roll_steps = 4
    vp._cam.roll = 0.0
    vp.update()
    for _ in range(4):
        qapp.processEvents()           # nav places itself per paint
    rect = vp._nav.rects["roll-right"]
    c = QPointF(rect.center())
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, c, QPointF(c),
                     Qt.MouseButton.LeftButton,
                     Qt.MouseButtons.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    vp.mousePressEvent(ev)
    assert vp._cam.roll == math.pi / 2


# ---- G6: canonical means canonical (L6.3a exact mode) ----------------------

def test_every_canonical_door_clears_the_wrist(vp, qapp):
    vp.view_anim_s = 0.0
    vp._cam.roll = 0.7
    vp._cube_click("front")
    assert (vp._cam.yaw, vp._cam.pitch) == zone_look("front")
    assert vp._cam.roll == 0.0                      # the table lands
    #                                                     the WHOLE
    vp._cam.roll = -2.0                             #   orientation
    vp._orbit_to(*view_orient("iso"))               # the keys' door
    assert vp._cam.roll == 0.0


# ---- G7: home remembers the wrist (and old files don't) --------------------

def test_home_grows_a_fourth_key_old_files_stay_faithful(vp, qapp):
    vp._cam.yaw, vp._cam.pitch, vp._cam.distance = 0.3, 0.5, 77.0
    vp._cam.roll = 0.35
    vp._set_home_from_view()
    assert vp._doc.home["roll"] == 0.35
    vp._cam.roll = 0.0
    vp.home()
    assert vp._cam.roll == 0.35                     # restored exact
    vp._doc.home = {"yaw": 0.1, "pitch": 0.2,
                    "distance": 30.0}               # a PRE-M157 file
    vp._cam.roll = 1.9
    vp.home()
    assert vp._cam.roll == 0.0                      # receipt V7
    assert abs(vp._cam.yaw - 0.1) < 1e-15


# ---- G8: the gear is the menu's drawn door (L12.5) --------------------------

def test_gear_is_drawn_beside_the_box_the_buffer_can_never_see_it(qapp):
    cam = Camera()
    cam.yaw, cam.pitch, cam.distance = math.radians(-45), \
        math.radians(30), 2.6
    cube, px = _draw_cube(cam)
    g = cube.gear
    gx0, gy0 = int(g.left()), int(g.top())
    gx1, gy1 = int(g.right()), int(g.bottom())
    glyph = int((px[gy0:gy1, gx0:gx1].sum(axis=2) > 0).sum())
    assert glyph > 8, f"the door was never drawn: {glyph} px"
    # MEASURED LAW (this gate's first draft ate the truth): a door
    # INSIDE the bbox steals real zone pixels — the probe at a corner
    # pose found the silhouette band running through the box corner
    # (hexagon edge ~5 px inside it). So the door lives OUTSIDE, in
    # the margin, and the buffer's ±8 px entry gate CANNOT see it:
    # every corner, every pose, the door answers no zone.
    assert not cube.rect.contains(cube.gear.center())
    for name in ZONES:
        cam.yaw, cam.pitch = zone_look(name)
        cube2, _ = _draw_cube(cam)
        assert cube2.hit(QPointF(cube2.gear.center())) is None, name
    # flipped corners keep the door on the widget's inside edge:
    for corner in ("top-left", "top-right", "bottom-left",
                   "bottom-right"):
        c3 = ViewCube()
        c3.corner = corner
        c3.place(400, 300)
        assert c3.gear.isValid()
        assert not c3.rect.contains(c3.gear.center()), corner


def test_gear_click_opens_the_menu_not_a_view(vp, qapp, monkeypatch):
    vp.view_anim_s = 0.0
    seen = {}
    monkeypatch.setattr(vp, "_show_menu",
                        lambda menu, at: seen.setdefault(
                            "n", len([a for a in menu.actions()
                                      if not a.isSeparator()])))
    vp.update()
    for _ in range(4):
        qapp.processEvents()
    y0, p0 = vp._cam.yaw, vp._cam.pitch
    c = QPointF(vp._cube.gear.center())
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, c, QPointF(c),
                     Qt.MouseButton.LeftButton,
                     Qt.MouseButtons.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    vp.mousePressEvent(ev)
    assert seen.get("n") == 6                       # the M156 set
    assert (vp._cam.yaw, vp._cam.pitch) == (y0, p0)  # steered NOTHING


# ---- G9: the wrist is additive — the snap never saw it ---------------------

def test_the_snap_is_roll_blind(vp, qapp):
    vp._cam.yaw, vp._cam.pitch = zone_look("corner back-bottom-left")
    z0 = nearest_zone(vp._cam)
    vp._cam.roll = 2.225
    assert nearest_zone(vp._cam) == z0 == "corner back-bottom-left"
