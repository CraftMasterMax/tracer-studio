"""M133 — orbit around the point you point at (re-pivot).

The vendor's "Orbit around point" gesture, cloned as behaviour: Shift
and PRESS the middle button over geometry and the orbit centre moves
to the rayed point — the view parallel-translates so the point lands
dead centre (with our eye derived from the target, that is literally
one assignment; yaw, pitch and distance all survive untouched) — and
every drag until release spins about it. Press over EMPTY space is a
no-op and the gesture keeps its existing pan meaning, so the binding
splits on what the cursor points at and steals nothing. The probe's
horror story — a sticky pivot that outlives the session and only dies
with a restart — cannot exist here: the pivot IS the camera target,
which every pan already relocates, and Home (one MMB click) doubles
as Reset Orbit Centre. Modifiers are sampled AT PRESS: a late Shift
change flips nothing, per the latching findings.
"""
import math

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tracer.core.document import PrimitiveFeature


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    w.new_document()
    w.doc.add(PrimitiveFeature(name="plate", kind="box",
                               dims={"dx": 40, "dy": 30, "dz": 6}))
    w.recompute()
    w.action_view("iso")
    w.action_view("fit")
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


# ---- the pure seam: press decides, geometry decides ------------------------

def test_a_press_on_geometry_repoints_the_orbit_at_the_rayed_point(win):
    vp = win.viewport
    cx, cy = vp.width() / 2, vp.height() / 2
    hit0 = vp._shoot(vp._tm, cx, cy)          # same ray the gesture will fly
    assert hit0 is not None                   # the fitted plate fills centre
    yaw0, pitch0, dist0 = vp._cam.yaw, vp._cam.pitch, vp._cam.distance
    assert vp._maybe_repivot(QPointF(cx, cy)) is True
    assert np.allclose(vp._cam.target, hit0[0])
    # A parallel translate: orientation and distance must survive.
    assert vp._cam.yaw == yaw0 and vp._cam.pitch == pitch0
    assert vp._cam.distance == dist0


def test_the_pivoted_point_lands_dead_centre(win):
    """A repivot AT the centre would centre trivially; the meaningful
    contract is an OFF-centre point: ray one, recentre, and the old
    pixel must be far from where it now sits — while the point itself
    snaps to the screen centre."""
    vp = win.viewport
    cx, cy = vp.width() / 2, vp.height() / 2
    corner = vp._cam.project(np.array([40.0, 0.0, 6.0]),   # plate corner
                             vp.width(), vp.height())
    assert corner is not None
    off = (cx + (corner[0] - cx) * 0.6, cy + (corner[1] - cy) * 0.6)
    hit0 = vp._shoot(vp._tm, *off)
    assert hit0 is not None                     # convex silhouette: inside
    assert math.hypot(off[0] - cx, off[1] - cy) > 50
    assert vp._maybe_repivot(QPointF(*off))
    px = vp._cam.project(vp._cam.target, vp.width(), vp.height())
    assert px is not None
    assert abs(px[0] - cx) < 1.5 and abs(px[1] - cy) < 1.5


def test_a_press_on_empty_space_pivots_nothing(win):
    vp = win.viewport
    before = vp._cam.target.copy()
    assert vp._maybe_repivot(QPointF(4, 4)) is False   # past the silhouette
    assert np.array_equal(vp._cam.target, before)


# ---- the real gesture -------------------------------------------------------

def test_after_a_repivot_press_the_drag_spins_about_the_new_pivot(win,
                                                                  qapp):
    vp = win.viewport
    cx, cy = vp.width() // 2, vp.height() // 2
    hit0 = vp._shoot(vp._tm, cx, cy)
    QTest.mousePress(vp, Qt.MiddleButton, Qt.ShiftModifier,
                     QPoint(cx, cy), 0)
    assert vp._repivot and vp._pivot is not None
    q0 = vp._cam.yaw
    QTest.mouseMove(vp, QPoint(cx + 60, cy + 2), 0)
    qapp.processEvents()
    assert vp._cam.yaw != q0                      # it spun...
    assert np.allclose(vp._cam.target, hit0[0])   # ...about the pointed-at pt
    QTest.mouseRelease(vp, Qt.MiddleButton, Qt.ShiftModifier,
                       QPoint(cx + 60, cy + 2), 0)
    qapp.processEvents()
    assert not vp._repivot and vp._pivot is None  # dot died with the gesture
    assert np.allclose(vp._cam.target, hit0[0])   # but nothing snapped back:
    #                                             # pivot lives on as plain
    #                                             # target, exactly like a pan


def test_a_shift_click_without_drag_centres_and_does_not_home(win, qapp):
    """MMB-no-drag release is Home; a SHIFT-pressed no-drag release is
    the point-centring itself — the re-pivot must not be undone."""
    vp = win.viewport
    cx, cy = vp.width() // 2, vp.height() // 2
    hit0 = vp._shoot(vp._tm, cx, cy)
    QTest.mousePress(vp, Qt.MiddleButton, Qt.ShiftModifier,
                     QPoint(cx, cy), 0)
    QTest.mouseRelease(vp, Qt.MiddleButton, Qt.ShiftModifier,
                       QPoint(cx, cy), 0)
    qapp.processEvents()
    assert np.allclose(vp._cam.target, hit0[0])   # home() would have
    assert hit0[0][2] != pytest.approx(           #  refitted to bbox centre
        vp._bbox.mean(axis=0)[2], abs=1e-9)       #  (top face ≠ mid-plane)


def test_a_shift_drag_on_empty_space_still_pans(win, qapp):
    vp = win.viewport
    before = vp._cam.target.copy()
    yaw0 = vp._cam.yaw
    QTest.mousePress(vp, Qt.MiddleButton, Qt.ShiftModifier,
                     QPoint(4, 4), 0)             # corner: nothing to hit
    assert not vp._repivot                        # fell through to pan
    # QTest.mouseMove carries no keyboard modifiers, so drive the move
    # as a real held-Shift event:
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(64, 64), QPointF(64, 64),
                     Qt.MouseButton.MiddleButton, Qt.MouseButton.MiddleButton,
                     Qt.KeyboardModifier.ShiftModifier)
    vp.mouseMoveEvent(ev)
    qapp.processEvents()
    assert not np.array_equal(vp._cam.target, before)   # panned
    assert vp._cam.yaw == yaw0                          # never orbited
    QTest.mouseRelease(vp, Qt.MiddleButton, Qt.ShiftModifier,
                       QPoint(64, 64), 0)
    qapp.processEvents()


def test_modifiers_are_sampled_at_press_not_mid_drag(win, qapp):
    """Shift OFF mid-orbit must not flip a live repivot drag into a pan
    (the latching trap the probe surfaced: FreeCAD #18202)."""
    vp = win.viewport
    cx, cy = vp.width() // 2, vp.height() // 2
    hit0 = vp._shoot(vp._tm, cx, cy)
    QTest.mousePress(vp, Qt.MiddleButton, Qt.ShiftModifier,
                     QPoint(cx, cy), 0)
    vp._buttons |= Qt.MiddleButton
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(cx + 50, cy + 4),
                     QPointF(cx + 50, cy + 4), Qt.MouseButton.MiddleButton,
                     Qt.MouseButton.MiddleButton,
                     Qt.KeyboardModifier.NoModifier)
    vp.mouseMoveEvent(ev)
    assert not math.isclose(vp._cam.yaw, math.radians(45.0))  # it spun
    assert np.allclose(vp._cam.target, hit0[0])               # no pan crept in
    vp._repivot = False
    vp._buttons = Qt.MouseButtons()


# ---- reset: the binding already paid for ------------------------------------

def test_home_is_the_reset_orbit_centre(win):
    vp = win.viewport
    vp._pivot = np.array([1.0, 2.0, 3.0])
    vp.home()
    assert vp._pivot is None
    assert np.allclose(vp._cam.target, vp._bbox.mean(axis=0))
