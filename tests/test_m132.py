"""M132 — the marking wheel: hold the right button and the ring blooms.

Fusion's signature canvas command surface, cloned as structure only:
four compass wedges (top=history, right=create, bottom=sketch, left=
modify), hover highlights, release-inside-executes, hub/void/Esc
dismiss. Everything rests on one pure function — wedge_at, the compass
sector of a pixel offset — so the whole radial grammar is checked
without a mouse. The second contract the tests guard is the COEXISTENCE
with what already lived on the right button: a quick tap still raises
the plain context menu, a drag still orbits, and ONLY a still hold past
HOLD_MS opens the ring. An accidental wheel must never steal a tap or a
spin, so those three paths are pinned against each other."""
import math

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tracer.ui.wheel import HOLD_MS, MarkingWheel, R_IN, R_OUT, wedge_at


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
    from tracer.core.document import PrimitiveFeature
    w.doc.add(PrimitiveFeature(name="plate", kind="box",
                               dims={"dx": 40, "dy": 30, "dz": 6}))
    w.recompute()
    qapp.processEvents()
    w._discard_guard = lambda: True
    yield w
    try:
        if w.viewport._wheel is not None:
            w.viewport.close_marking_wheel()
    except Exception:
        pass
    w._unsaved = False
    w.close()
    r.close()


# ---- the one pure function ------------------------------------------------

def test_dead_centre_and_void_are_not_wedges():
    assert wedge_at(0, 0) is None                 # hub: dismiss
    assert wedge_at(0, R_OUT + 1) is None         # beyond the ring
    assert wedge_at(0, -(R_IN - 1)) is None       # inside the hub


def test_the_four_wedge_centres_map_n_e_s_w():
    mid = (R_IN + R_OUT) / 2
    assert wedge_at(0, -mid) == 0                 # north = up = -y
    assert wedge_at(mid, 0) == 1                  # east
    assert wedge_at(0, mid) == 2                  # south
    assert wedge_at(-mid, 0) == 3                 # west


def test_quadrant_boundaries_are_deterministic():
    r = 60.0
    ne = math.radians(45)                         # exactly on the N/E line
    assert wedge_at(r * math.sin(ne), -r * math.cos(ne)) == 1   # E owns it
    assert wedge_at(r * math.sin(-ne), -r * math.cos(-ne)) == 0  # N's side


# ---- the ring object: pick and run, no events needed ----------------------

def test_the_hover_fill_lands_on_the_wedge_it_highlights(qapp):
    """Paint the ring twice — idle, then with the E wedge hovered —
    and READ PIXELS: only the east wedge's face may change, never its
    neighbours'. (A one-quadrant start-angle slip passes every pick
    test and lies on screen; this is what catches it.)"""
    from PySide6.QtGui import QFont, QImage, QPainter

    cmds = [("Undo", lambda: None), ("Extrude", lambda: None),
            ("Sketch", lambda: None), ("Move", lambda: None)]
    imgs = []
    for hov in (None, 1):
        img = QImage(240, 240, QImage.Format_RGBA8888)
        img.fill(Qt.transparent)
        p = QPainter(img)
        w = MarkingWheel(QPointF(120, 120), cmds)
        w.hover = hov
        w.paint(p, QFont())
        p.end()
        imgs.append(img)
    idle, hot = imgs
    east = (165, 140)       # inside the E wedge, clear of its label
    west = (75, 140)        # inside the W wedge, the mirror position
    assert hot.pixelColor(*east) != idle.pixelColor(*east)   # E lit up...
    assert hot.pixelColor(*west) == idle.pixelColor(*west)   # ...W didn't

def test_ring_pick_and_run_fire_the_won_wedge():
    hits = []
    w = MarkingWheel(QPointF(100, 100),
                     [("A", lambda: hits.append("A")),
                      ("B", lambda: hits.append("B")),
                      ("C", lambda: hits.append("C")),
                      ("D", lambda: hits.append("D"))])
    assert w.pick(QPointF(100, 100 - 59)) == 0        # N
    assert w.pick(QPointF(100, 100)) is None          # hub dismisses
    w.run(w.pick(QPointF(100 + 59, 100)))             # the E wedge won
    assert hits == ["B"]
    assert len(w.commands()) == 4


# ---- the viewport owns opening, and coexists with tap + orbit --------------

def test_open_marks_wedges_and_runs_the_provider_side_effect(win, qapp):
    vp = win.viewport
    fired = []
    vp.set_wheel_commands(
        lambda: [("Undo", lambda: fired.append(0)),
                 ("Extrude", lambda: fired.append(1)),
                 ("Sketch", lambda: fired.append(2)),
                 ("Move", lambda: fired.append(3))])
    w = vp.open_marking_wheel(QPoint(vp.width() // 2, vp.height() // 2))
    qapp.processEvents()
    try:
        assert w is not None and vp._wheel is w
        vp._run_wheel_cmd(2)                      # the S wedge won
        assert fired == [2]
    finally:
        vp.close_marking_wheel()
        qapp.processEvents()
    assert vp._wheel is None                       # closed → cleaned up


def test_open_is_idempotent_while_a_ring_is_showing(win, qapp):
    vp = win.viewport
    vp.set_wheel_commands(lambda: [("U", lambda: None)] * 4)
    vp.open_marking_wheel(QPoint(vp.width() // 2, vp.height() // 2))
    try:
        assert vp.open_marking_wheel(QPoint(10, 10)) is None   # no 2nd ring
    finally:
        vp.close_marking_wheel()
        qapp.processEvents()


def test_release_on_a_wedge_runs_it_on_the_hub_it_dismisses(win, qapp):
    vp = win.viewport
    fired = []
    vp.set_wheel_commands(
        lambda: [("N", lambda: fired.append("N")),
                 ("E", lambda: fired.append("E")),
                 ("S", lambda: fired.append("S")),
                 ("W", lambda: fired.append("W"))])
    c = QPoint(vp.width() // 2, vp.height() // 2)
    vp.open_marking_wheel(c)
    QTest.mouseRelease(vp, Qt.RightButton, Qt.NoModifier,
                       QPoint(c.x() + 59, c.y()), 0)     # release on E
    qapp.processEvents()
    assert fired == ["E"] and vp._wheel is None
    vp.open_marking_wheel(c)
    QTest.mouseRelease(vp, Qt.RightButton, Qt.NoModifier,
                       QPoint(c.x(), c.y()), 0)          # release on hub
    qapp.processEvents()
    assert fired == ["E"] and vp._wheel is None          # dismiss, no fire


def test_escape_key_collapses_an_open_ring(win, qapp):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    vp = win.viewport
    vp.set_wheel_commands(lambda: [("U", lambda: None)] * 4)
    vp.open_marking_wheel(QPoint(vp.width() // 2, vp.height() // 2))
    vp.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape,
                               Qt.NoModifier))
    assert vp._wheel is None


def test_a_quick_right_tap_still_raises_the_menu_not_the_ring(win, qapp):
    vp = win.viewport
    taps = []
    vp.context_request.connect(lambda pos: taps.append(pos))
    QTest.mousePress(vp, Qt.RightButton, Qt.NoModifier, QPoint(500, 350), 0)
    QTest.mouseRelease(vp, Qt.RightButton, Qt.NoModifier, QPoint(500, 350), 0)
    qapp.processEvents()
    assert len(taps) == 1 and vp._wheel is None    # old grammar intact


def test_a_right_drag_orbits_and_never_blooms_the_ring(win, qapp):
    vp = win.viewport
    taps = []
    vp.context_request.connect(lambda pos: taps.append(pos))
    before = vp._cam.yaw
    QTest.mousePress(vp, Qt.RightButton, Qt.NoModifier, QPoint(500, 350), 0)
    QTest.mouseMove(vp, QPoint(560, 352))
    QTest.mouseRelease(vp, Qt.RightButton, Qt.NoModifier, QPoint(560, 352), 0)
    qapp.processEvents()
    assert vp._cam.yaw != before                   # it spun
    assert vp._wheel is None and taps == []        # no ring, no menu


def test_arm_opens_only_when_still_holding_still(win, qapp):
    vp = win.viewport
    vp.set_wheel_commands(lambda: [("U", lambda: None)] * 4)
    vp._buttons |= Qt.RightButton                 # pretend it's still held
    try:
        vp._rmb_at = None
        vp._arm_marking_wheel()                    # nothing pending: no-op
        assert vp._wheel is None
        vp._rmb_at = QPoint(400, 300)              # pressed, not dragged
        vp._arm_marking_wheel()
        assert vp._wheel is not None               # a still hold opened it
        vp.close_marking_wheel()
        qapp.processEvents()
        vp._dragged = True                         # dragged → orbit, not wheel
        vp._rmb_at = QPoint(400, 300)
        vp._arm_marking_wheel()
        assert vp._wheel is None
    finally:
        vp._dragged = False
        vp._buttons &= ~Qt.RightButton
        if vp._wheel is not None:
            vp.close_marking_wheel()
            qapp.processEvents()


# ---- the command table itself ----------------------------------------------

def test_the_canvas_table_is_four_guarded_verbs(win):
    cmds = win._wheel_commands()
    assert [label for label, _ in cmds] == ["Undo", "Extrude", "Sketch",
                                            "Move"]
    assert all(callable(fn) for _, fn in cmds)


def test_hold_ms_is_a_sane_stillness_window():
    assert 120 <= HOLD_MS <= 400                   # longer than a click,
    assert R_OUT > R_IN > 0                         # shorter than doubt
