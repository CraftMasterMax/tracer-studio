"""M154 — the cube learns its corners: 26 zones, the click table, the
glide. Every law is a receipt from research/m154_spike1.md (script
spike_m154/live_m154.py green at this tree) executed against
research/ui_navcube_cloning_checklist.md (7d2edfae) §4/§6/§7. The old
M44b/M63 laws survive: the six faces answer with the SAME names and
land on BYTE-IDENTICAL set_view orientations (G1 pins it); the one
retarget (test_fusion_parity center pixel) cites the move — the
buffer's truth is stricter than the painter-order guess it replaces.
"""
import math

import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from tracer.ui.camera import Camera, view_orient
from tracer.ui.viewcube import (ZONES, ZONE_IDS, ViewCube, zone_look,
                                _FACE_ORDER)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def cube(qapp):
    c = ViewCube()
    c.place(800, 600)
    return c


def _paint(cube, cam, dpr=1.0):
    img = QImage(800, 600, QImage.Format.Format_RGB32)
    img.fill(0)
    p = QPainter(img)
    cube.draw(p, cam, dpr=dpr)
    p.end()
    return img


# ---- G1: the table law ------------------------------------------------

def test_26_zones_are_data_and_the_faces_never_moved():
    assert len(ZONES) == len(ZONE_IDS) == 26
    for k in _FACE_ORDER:                          # byte-identical law
        assert zone_look(k) == view_orient(k), k
    # the shipped set_view itself (not just the extracted table):
    c = Camera()
    for k in _FACE_ORDER:
        c.set_view(k)
        assert (c.yaw, c.pitch) == zone_look(k), k


def test_corner_rows_are_true_isometric_and_edges_are_two_axis():
    iso = math.asin(1.0 / math.sqrt(3.0))
    n_edges = 0
    for name, d in ZONES.items():
        y, p = zone_look(name)
        if name.startswith("corner"):
            assert min(abs(p - iso), abs(p + iso)) < 1e-12, name
            #   true iso pitch, sign by top/bottom family
            assert min(abs(abs(y) - math.pi / 4),
                       abs(abs(y) - 3 * math.pi / 4)) < 1e-12, name
        elif "-" in name:
            n_edges += 1
            assert abs(p) < math.radians(89.0)     # never a pole
            # two-axis means the DIRECTION has exactly two non-zero
            # components — a vertical edge (front-right) rides pitch
            # 0 and is STILL a two-face view (the old prose pin here
            # was the lie; the direction is the truth)
            assert sum(1 for c in d if abs(c) > 1e-12) == 2, name
    assert n_edges == 12


def test_home_iso_pin_stands_untouched():
    # G9-partial: the hand-set 28-deg HOME art is NOT the corner law
    assert math.degrees(view_orient("iso")[1]) == 28.0
    assert abs(math.degrees(zone_look("corner front-top-right")[1])
               - 35.264390) < 1e-5


# ---- G2: the pick buffer — complete, clean, DPR-honest ---------------

def test_buffer_serves_all_26_zones_and_no_off_id_pixels(cube):
    seen = set()
    for kind in _FACE_ORDER + ("iso",):
        cam = Camera()
        cam.set_view(kind)
        _paint(cube, cam)
        b = cube._pick
        assert b.width() == round(cube.rect.width())       # G8-half
        for x in range(b.width()):
            for y in range(b.height()):
                i = b.pixel(x, y) & 0xFFFFFF
                if i:
                    assert i <= len(ZONE_IDS)              # AT-01: no
                    seen.add(ZONE_IDS[i - 1])              # phantom id
    assert seen == set(ZONES), len(seen)                   # all 26 seen


def test_buffer_is_physical_at_dpr(cube):
    cam = Camera()
    _paint(cube, cam, dpr=2.0)
    assert cube._pick.width() == round(cube.rect.width() * 2.0)
    assert cube._pick.height() == round(cube.rect.height() * 2.0)


def test_free_space_never_hits(cube):
    _paint(cube, Camera())
    assert cube.hit(QPointF(10, 300)) is None      # far outside
    corner_out = QPointF(cube.rect.right() + 20, cube.rect.top() - 20)
    assert cube.hit(corner_out) is None


# ---- G3: hover IS the pick id; geometry agrees ------------------------

def test_center_of_a_face_core_hits_that_face(cube):
    cam = Camera()
    cam.set_view("front")                          # one face full-on
    _paint(cube, cam)
    got = cube.hit(cube.rect.center())
    assert got == "front", got                     # the CORE, not a band


def test_edge_zone_is_hittable_and_hovers_itself(cube):
    cam = Camera()
    cam.set_view("iso")                            # centre == an edge
    _paint(cube, cam)                              # (parity retarget:
    got = cube.hit(cube.rect.center())             #  the honest truth)
    assert "-" in got and not got.startswith("corner"), got
    glow = QImage(800, 600, QImage.Format.Format_RGB32)
    glow.fill(0)
    p = QPainter(glow)
    cube.draw(p, cam, hover=got)                   # hover resolves to
    p.end()                                        #   the same id
    arr = np.frombuffer(glow.constBits(), np.uint8,
                        glow.sizeInBytes()).reshape(600, 800, 4)
    assert (arr[:, :, 0] > 100).sum() > 30         # SOMETHING glows


# ---- G4/G5/G6/G7: the viewport laws (click, glide, wrap, double-fit) --

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
    from tracer.core.document import Document, PrimitiveFeature
    d = Document("g")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    w.doc = d
    w.recompute()
    qapp.processEvents()
    yield w.viewport
    w._unsaved = False
    w.close()
    qapp.processEvents()


def _settle(vp, qapp, ms=2500):
    import time
    t0 = time.monotonic()
    while vp._anim is not None and (time.monotonic() - t0) < ms / 1000:
        qapp.processEvents()
        time.sleep(0.01)


def test_clicks_land_on_the_table(vp, qapp):
    vp.view_anim_s = 0.0                           # instant door first
    for zone in ("front", "front-top", "corner front-top-right"):
        vp._cube_click(zone)
        assert (vp._cam.yaw, vp._cam.pitch) == zone_look(zone), zone


def test_face_clicks_are_byte_identical_to_the_old_law(vp, qapp):
    vp.view_anim_s = 0.0
    old = Camera()
    for kind in _FACE_ORDER:
        old.set_view(kind)
        vp._cube_click(kind)
        assert (vp._cam.yaw, vp._cam.pitch) == (old.yaw, old.pitch)


def test_click_glide_lands_on_the_law(vp, qapp):
    vp.view_anim_s = 0.12
    vp._cube_click("corner front-top-right")
    assert vp._anim is not None                    # in flight
    _settle(vp, qapp)
    assert (vp._cam.yaw, vp._cam.pitch) == zone_look(
        "corner front-top-right")                  # EXACTLY (no drift)


def test_retarget_mid_flight_never_snaps_back(vp, qapp):
    vp.view_anim_s = 0.6
    vp._cam.yaw, vp._cam.pitch = 0.0, 0.0
    vp._orbit_to(math.pi, 0.6)                     # A far away
    qapp.processEvents()
    vp._anim_step()                                # one tick forward
    mid = (vp._cam.yaw, vp._cam.pitch)
    vp._orbit_to(-2.0, -0.3)                       # B: re-target NOW
    assert abs(vp._cam.yaw - mid[0]) < 1e-9, "snap-back on re-target"
    _settle(vp, qapp)
    assert (vp._cam.yaw, vp._cam.pitch) == (-2.0, -0.3)   # lands on B


def test_wrapped_yaw_takes_the_short_arc(vp, qapp):
    vp.view_anim_s = 0.3
    vp._cam.yaw, vp._cam.pitch = math.radians(170), 0.0
    vp._orbit_to(math.radians(-170), 0.0)
    worst = 0.0
    import time
    t0 = time.monotonic()
    while vp._anim is not None and time.monotonic() - t0 < 2:
        qapp.processEvents()
        worst = max(worst, abs(((vp._cam.yaw - math.radians(170)
                                 + math.pi) % (2 * math.pi))
                               - math.pi))
        time.sleep(0.005)
    assert worst <= math.radians(20) + 1e-9, math.degrees(worst)
    assert vp._cam.yaw == math.radians(-170)


def test_same_zone_double_click_fits_different_zone_does_not(vp, qapp):
    vp.view_anim_s = 0.0
    vp._cam.yaw, vp._cam.pitch = 0.4, 0.2          # off-canonical
    vp._cam.zoom(1.6)                              # UN-fit on purpose
    vp._cube_last = None
    d0 = vp._cam.distance
    vp._cube_click("front")                        # first: no fit yet
    assert vp._cam.distance == d0
    vp._cube_click("front")                        # same zone, twice
    assert vp._cam.distance != d0                  # the FIT ran (AT-09)
    assert (vp._cam.yaw, vp._cam.pitch) == zone_look("front")
    #   ...and the fit steers NOTHING: orientation stayed the zone's
    vp._cam.zoom(1.6)
    d2 = vp._cam.distance
    vp._cube_last = None
    vp._cube_click("top")
    vp._cube_click("right")                        # fast, DIFFERENT
    assert vp._cam.distance == d2                  # zone switch: never


def test_home_and_key_iso_keep_their_pins(vp, qapp):
    vp.view_anim_s = 0.0
    vp.home()
    assert math.degrees(vp._cam.pitch) == 28.0     # the home art pin
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    vp._cam.yaw, vp._cam.pitch = 0.0, 0.0
    vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_1,
                               Qt.KeyboardModifier.NoModifier))
    assert (vp._cam.yaw, vp._cam.pitch) == view_orient("front")
    vp._cam.yaw, vp._cam.pitch = 0.0, 0.0
    vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_0,
                               Qt.KeyboardModifier.NoModifier))
    assert (vp._cam.yaw, vp._cam.pitch) == view_orient("iso")
