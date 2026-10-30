"""M172 rung 1 - THE ROUNDING HAND: F pulls the arc, the release files it.

Canvas F retires the dialog for corners: with two selected lines sharing
a corner, F AIMS the rounding hand (the kernel's OWN validator answers -
a corner three geometries share refuses with the kernel's own words and
the scene stays byte-identical: aiming is not editing). A press ON the
aimed corner starts the pull; the move SIZES the ghost (cursor distance
to the corner, clamped by the kernel's own leg max - a pull can never
outrun the legs); the release FILES it: corner_fillet at the pulled r,
ONE history row, the arc becomes the pick, and the aim is spent. A
click without a pull files the dialog's own default radius; a click
elsewhere voids the aim and carries on as an ordinary click; tool
switch and Escape kill the arm (the M168 graveyard law). A refused
commit pops its row - a no-op leaves no undo. The aim is not modal:
the rung-2 NUDGE moves the corner and the aim RIDES it (the state holds
LIVE entities, not coordinates). One undo erases the whole fillet: the
arc, the two minted points, all four structural constraints.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, QPoint, Qt               # noqa
from PySide6.QtGui import QMouseEvent                                # noqa
from PySide6.QtTest import QTest                                    # noqa
from PySide6.QtWidgets import QApplication                          # noqa

from tracer.core.sketch.constraints import Radius                   # noqa
from tracer.core.sketch.model import SketchModel                    # noqa
from tracer.ui.sketcheditor import SketchCanvas                     # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    c = SketchCanvas()
    c.set_model(SketchModel())        # empty once: scale 4 / centre 0 stay
    c.resize(600, 400)
    c._snap_grid = False
    yield c
    c.deleteLater()


def _scr(x, y):
    return QPoint(int(round(300 + 4.0 * x)), int(round(200 - 4.0 * y)))


def _key(ed, k, mods=Qt.NoModifier):
    QTest.keyClick(ed, k, mods)


def _move(ed, x, y):
    #  QTest.mouseMove cannot hold button state (m37 law) - send a real
    p = QPointF(300.0 + 4.0 * x, 200.0 - 4.0 * y)                 # event
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))


def _click(ed, x, y):
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(x, y))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(x, y))


def _clickc(ed, x, y):
    QTest.mousePress(ed, Qt.LeftButton, Qt.ControlModifier, _scr(x, y))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.ControlModifier, _scr(x, y))


def _scene(ed):
    m = ed.model
    far1 = m.point(-2, 6)
    P = m.point(6, 6)
    far2 = m.point(6, -2)
    m.add_line(far1, P)
    m.add_line(P, far2)
    ed._solve()
    return m, far1, P, far2


def _pick2(ed):
    _click(ed, 2, 6)                               # l1 by its mid...
    _clickc(ed, 6, 2)                              #  l2 joins via Ctrl


def _sig(m):
    sk = m.sketch
    return (len(sk.points), len(sk.lines), len(sk.arcs),
            len(sk.constraints),
            tuple(sorted((round(p.x, 4), round(p.y, 4)) for p in sk.points)))


def test_f_arms_the_corner_and_touches_nothing(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    assert len(ed._sel) == 2
    st = _sig(m)
    n0 = len(ed._hist)
    _key(ed, Qt.Key_F)
    assert ed._corner is not None                  # the hand is aimed...
    assert ed._corner[4] == pytest.approx(2.0)     #  at the old default
    assert len(ed._hist) == n0 and _sig(m) == st   #   and THAT is all


def test_a_press_and_release_files_the_default_round(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    n0 = len(ed._hist)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    sk = m.sketch
    assert len(sk.arcs) == 1                       # no pull = the default
    rad = [c for c in sk.constraints if isinstance(c, Radius)]
    assert len(rad) == 1 and rad[0].value == pytest.approx(2.0)
    assert len(sk.points) == 5                     # tangent 2 + bulge born
    assert ed._sel == [sk.arcs[0]]                 # the arc is the pick
    assert len(ed._hist) == n0 + 1                 # one act, one undo row
    assert ed._corner is None                      # the aim is spent
    assert P.x == pytest.approx(4.0)               # P REUSED as tangent 1
    assert ed.undo_op()                            # one undo erases all
    assert len(m.sketch.arcs) == 0 and len(m.sketch.points) == 3
    assert len(ed._hist) == n0


def test_the_pull_sizes_the_arc(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    n0 = len(ed._hist)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    _move(ed, 2.5, 6)                              # pull 3.5 mm out...
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(2.5, 6))
    rad = [c for c in m.sketch.constraints if isinstance(c, Radius)]
    assert len(rad) == 1
    assert rad[0].value == pytest.approx(3.5, abs=1e-9)   # the pull IS r
    assert P.x == pytest.approx(2.5)               # tan(45): tan_len = r
    assert len(ed._hist) == n0 + 1


def test_refusals_pay_nothing(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    ed._corner[4] = 99.0                           # an impossible commit
    st = _sig(m)
    n0 = len(ed._hist)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(6, 6))
    assert _sig(m) == st and len(ed._hist) == n0   # popped: zero ambient
    assert ed._corner is None and len(m.sketch.arcs) == 0
    far3 = m.point(12, 6)                          # a corner of THREE:
    m.add_line(P, far3)                            #  the ARM itself
    ed._solve()                                    #   refuses, kernel-
    st2 = _sig(m)                                  #    worded, silent
    n1 = len(ed._hist)
    _key(ed, Qt.Key_F)
    assert ed._corner is None
    assert "more geometry" in ed._warn_text
    assert _sig(m) == st2 and len(ed._hist) == n1


def test_a_click_elsewhere_voids_the_aim(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    st = _sig(m)
    n0 = len(ed._hist)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(-4, -4))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(-4, -4))
    assert ed._corner is None                      # the aim is void...
    assert ed._sel == []                           #  and the click went
    assert len(ed._hist) == n0                     #   through as a click
    assert _sig(m) == st


def test_the_aim_rides_the_nudge_and_dies_with_the_tool(ed):
    m, far1, P, far2 = _scene(ed)
    _pick2(ed)
    _key(ed, Qt.Key_F)
    _key(ed, Qt.Key_Right)                         # M171's nudge steps
    assert P.x == pytest.approx(7.25)              #  the whole corner -
    assert ed._corner is not None                  #   the aim RIDES it
    assert ed._corner[3] is P                      #    (live entities)
    _key(ed, Qt.Key_T)                             # tool switch KILLS it
    assert ed._corner is None                      #  (M168 graveyard)
    _key(ed, Qt.Key_Escape)                        # back to select: the
    _key(ed, Qt.Key_F)                             #  still-picked pair
    assert ed._corner is not None                  #  RE-ARMS the hand
    _key(ed, Qt.Key_Escape)                        # Esc kills the aim
    assert ed._corner is None
