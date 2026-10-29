"""M166 rung 1 - navigation feel: THE MENU LEARNS THE GLIDE (fleet spec:
research/specs/m166_build_plan.md; laws FD8-19, L7.6).

Before this rung the viewport kept TWO snap laws: key 1 glided through
_orbit_to while menu "Front", the marking menu and the palette's
view:front teleported straight into cam privates (MainWindow.action_view
writing set_view). One action, one feel: every orientation door now
rides the viewport's own glide door snap_view, and the default duration
moved 0.3 -> 0.5 s per FD8-19 (cite-the-move in viewport.py:158).
Fit doors stay instant until rung 3 - a plan, not an accident.
"""
import math
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import (QEvent, QPoint, QPointF, Qt)  # noqa: E402
from PySide6.QtGui import QKeyEvent, QWheelEvent         # noqa: E402
from PySide6.QtTest import QTest                         # noqa: E402
from PySide6.QtWidgets import QApplication               # noqa: E402

from tracer.core.document import PrimitiveFeature        # noqa: E402
from tracer.ui.camera import view_orient                 # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def win(qapp):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


def _settle(vp, qapp, ms=2500):
    import time
    t0 = time.monotonic()
    while vp._anim is not None and (time.monotonic() - t0) < ms / 1000:
        qapp.processEvents()
        time.sleep(0.01)


def test_the_menu_view_glides_now_not_teleports(win, qapp):
    vp = win.viewport
    vp._cam.yaw, vp._cam.pitch = view_orient("iso")      # staged start
    vp._cam.roll = 0.0
    assert win._run_command("view:front")                # the PALETTE door
    assert vp._anim is not None                          # IN FLIGHT: this
    #                                                       exact door
    #                                                       teleported
    #                                                       before rung 1
    _settle(vp, qapp)
    assert (vp._cam.yaw, vp._cam.pitch) == view_orient("front")
    # lands on the EXACT canonical values - the glide is transit, the
    # table is truth (m154's byte-exactness law survives the new door)
    assert vp._cam.roll == 0.0


def test_the_zero_door_still_lands_instant(win):
    vp = win.viewport
    vp.view_anim_s = 0.0                                 # the escape
    win._run_command("view:front")                       #  hatch survives:
    assert vp._anim is None                              #  same door,
    assert (vp._cam.yaw, vp._cam.pitch) == view_orient("front")


def test_the_key_path_fires_once_never_twice(win, qapp):
    # The focused canvas CONSUMES orientation keys (:keyPressEvent
    # _VIEWS table) - MainWindow must never see them, and the same
    # target must not glide twice.
    vp = win.viewport
    vp.view_anim_s = 0.0                                 # counting only
    hits = []
    real = vp._orbit_to
    vp._orbit_to = lambda *a, **k: (hits.append(a), real(*a, **k))[1]
    reached = []
    win._dispatch_key = lambda *a, **k: reached.append(a) or False
    vp.setFocus()
    qapp.processEvents()
    QApplication.sendEvent(
        vp, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_1,
                      Qt.KeyboardModifier.NoModifier))
    qapp.processEvents()
    assert len(hits) == 1 and tuple(hits[0]) == view_orient("front")
    assert reached == []                                 # consumed, not
    #                                                       forwarded


def test_default_glide_duration_is_half_a_second(win):
    # FD8-19: Fusion's snap transition measures ~500 ms. M154's 0.3 s
    # was ours-said; the digest outranks the draft - cite-the-move lives
    # at viewport.py:158. No new QSettings key: the attribute IS the
    # knob (feel-settings are a future rung).
    assert win.viewport.view_anim_s == 0.5


# ---- Rung 2: home flies; the hand beats the ghost --------------------------

def _box(win):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="block", kind="box",
                                 dims={"dx": 40, "dy": 20, "dz": 10}))
    win.recompute()
    qapp = QApplication.instance()
    qapp.processEvents()


def _tick(vp, qapp, sec):
    """Run the REAL event loop for sec seconds - the flight advances on
    the wall clock exactly as it does in the app."""
    import time
    t0 = time.monotonic()
    while time.monotonic() - t0 < sec:
        qapp.processEvents()
        time.sleep(0.005)


def test_home_with_a_saved_pose_flies_and_lands_exact(win, qapp):
    vp = win.viewport
    _box(win)
    vp._cam.yaw, vp._cam.pitch, vp._cam.roll = 0.0, 0.0, 0.0
    vp._cam.distance = 250.0
    vp._set_home_from_view()                 # home = (0, 0, 0, 250)
    assert vp._doc.home == {"yaw": 0.0, "pitch": 0.0,
                            "distance": 250.0, "roll": 0.0}
    vp._cam.yaw, vp._cam.pitch, vp._cam.roll = 1.0, -0.4, 0.3
    vp._cam.distance = 40.0
    vp.home()
    assert vp._anim is not None              # the trip is REAL now
    _settle(vp, qapp)
    assert (vp._cam.yaw, vp._cam.pitch, vp._cam.roll,
            vp._cam.distance) == (0.0, 0.0, 0.0, 250.0)   # EXACT landing


def test_home_less_flight_lands_iso_and_fit_exact(win, qapp):
    from tracer.ui.camera import fit_frame
    vp = win.viewport
    _box(win)
    assert vp._doc.home is None
    vp._cam.yaw, vp._cam.pitch, vp._cam.roll = 0.0, 0.0, 0.0
    vp._cam.distance = 400.0
    cam = vp.camera()
    center, dist = fit_frame(vp._bbox, cam.fov)
    vp.home()
    assert vp._anim is not None              # one 6-dial flight
    _settle(vp, qapp)
    assert math.degrees(cam.pitch) == 28.0   # iso home ART...
    assert cam.distance == dist              #  ...plus Camera.fit's
    #                                           EXACT numbers (pure
    assert np.allclose(cam.target, center)   #   fit_frame, formula law)


def test_re_home_mid_flight_never_snaps_back(win, qapp):
    vp = win.viewport
    _box(win)
    vp._cam.yaw, vp._cam.pitch, vp._cam.roll = 0.0, 0.0, 0.0
    vp._cam.distance = 300.0
    vp._set_home_from_view()
    vp._cam.yaw, vp._cam.pitch = 1.2, 0.6
    vp._cam.distance = 20.0
    vp.home()
    _tick(vp, qapp, 0.15)                    # partway along the arc
    y_live, p_live = vp._cam.yaw, vp._cam.pitch
    vp.home()                                # re-home mid-flight:
    assert vp._cam.yaw == y_live             #  NO snap to start, NO
    assert vp._cam.pitch == p_live           #  freeze - retarget from
    assert vp._anim is not None              #  the LIVE camera...
    _settle(vp, qapp)
    assert (vp._cam.yaw, vp._cam.pitch, vp._cam.distance) == (
        0.0, 0.0, 300.0)                     #  ...and still lands exact


def test_the_wheel_beats_the_ghost(win, qapp):
    vp = win.viewport
    _box(win)
    vp._cam.yaw, vp._cam.pitch, vp._cam.roll = 0.0, 0.0, 0.0
    vp._cam.distance = 300.0
    vp._set_home_from_view()
    vp._cam.distance = 30.0
    vp.home()                                # a flight that OWNS
    assert vp._anim is not None              #  distance
    _tick(vp, qapp, 0.1)
    d_mid = vp._cam.distance
    ev = QWheelEvent(QPointF(300, 200), vp.mapToGlobal(QPointF(300, 200)),
                     QPoint(0, 0), QPoint(0, 120),
                     Qt.MouseButtons.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(vp, ev)           # the wheel IS the hand
    assert vp._anim is None                  # glide killed WHERE IT
    d_after = vp._cam.distance               #  STANDS
    assert d_after < d_mid - 1e-9            # zoom applied from the
    #                                          mid-flight distance...
    _tick(vp, qapp, 0.1)
    assert vp._cam.distance == d_after       # ...and SURVIVES the next
    #                                          ticks: no ghost overwrite


def test_a_press_takes_the_camera_from_the_flight(win, qapp):
    vp = win.viewport
    _box(win)
    vp._cam.yaw, vp._cam.pitch, vp._cam.roll = 0.0, 0.0, 0.0
    vp._cam.distance = 300.0
    vp._set_home_from_view()
    vp._cam.yaw, vp._cam.pitch = 1.2, 0.6
    vp.home()
    _tick(vp, qapp, 0.12)
    snapshot = (vp._cam.yaw, vp._cam.pitch, vp._cam.distance)
    QTest.mousePress(vp, Qt.MouseButton.MiddleButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(300, 200))
    assert vp._anim is None                  # press = hand takes over
    assert (vp._cam.yaw, vp._cam.pitch,
            vp._cam.distance) == snapshot    # cancel MOVES NOTHING
    QTest.mouseRelease(vp, Qt.MouseButton.MiddleButton,
                       Qt.KeyboardModifier.NoModifier, QPoint(300, 200))
    _settle(vp, qapp)                        # no-drag release homes


def test_the_zero_door_home_is_the_old_instant(win):
    vp = win.viewport
    _box(win)
    vp.view_anim_s = 0.0                     # the escape hatch stays
    vp._cam.yaw, vp._cam.pitch, vp._cam.roll = 0.0, 0.0, 0.0
    vp._cam.distance = 300.0
    vp._set_home_from_view()
    vp._cam.yaw, vp._cam.pitch, vp._cam.distance = 1.1, 0.5, 55.0
    vp.home()
    assert vp._anim is None                  # byte-exact instant home,
    assert (vp._cam.yaw, vp._cam.pitch, vp._cam.roll,   #  the pre-rung-2
            vp._cam.distance) == (0.0, 0.0, 0.0, 300.0)  #  law
