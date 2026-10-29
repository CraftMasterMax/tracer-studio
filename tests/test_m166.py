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
import math                                              # noqa: F401
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt                    # noqa: E402
from PySide6.QtGui import QKeyEvent                      # noqa: E402
from PySide6.QtWidgets import QApplication               # noqa: E402

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
