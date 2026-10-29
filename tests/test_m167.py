"""M167 rung 1 — BODIES MOVE (the select tool grabs geometry).

Today only a POINT could be dragged (absolutely, onto the cursor). A line,
arc, circle or ellipse selected then pulled moved NOTHING; today's most-hit
CAD gesture was inert in ours. Rung 1's law:

  A point follows YOUR cursor (the old absolute law, byte-exact — gate 8).
  A body follows YOUR HAND: every grab point = start + (world(now) −
  world(press)), so the grab offset survives (no jump when you catch a line
  at its middle). ONE magnet: the first dragged member to reach a candidate
  shifts the WHOLE delta so that member lands EXACT on it — the crowd rides
  the catch. A dragged body never magnetizes onto ITSELF (snaps skip the
  dragged points AND entities), and LOCKED geometry refuses the grab (the
  M119 point_dof witness; today a fixed point rubber-banded to a solver
  halfway-house — Fusion simply holds it). Connected chains follow for
  free: the shared corner IS one Point, and solve(pins=...) holds what the
  hand moves and flexes everything else.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa
from PySide6.QtGui import QMouseEvent                                # noqa
from PySide6.QtTest import QTest                                     # noqa
from PySide6.QtWidgets import QApplication                           # noqa

from tracer.core.sketch.constraints import Fixed                     # noqa
from tracer.core.sketch.entities import Arc                          # noqa
from tracer.core.sketch.model import SketchModel                     # noqa
from tracer.ui.sketcheditor import SketchCanvas                      # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    c = SketchCanvas()
    c.set_model(SketchModel())
    c.resize(600, 400)
    c._snap_grid = False          # the magnet's minted grid off: gates speak
    yield c                       #   world mm, settings cannot move them
    c.deleteLater()


def scr(x, y):                    # world mm -> widget px (scale 4, centre 0)
    return (int(round(300 + 4.0 * x)), int(round(200 - 4.0 * y)))


def _press(ed, x, y, mods=Qt.NoModifier):
    QTest.mousePress(ed, Qt.LeftButton, mods, QPoint(*scr(x, y)))


def _move(ed, x, y, mods=Qt.NoModifier):
    # this PySide6 QTest.mouseMove can't hold button state (m37 law), and
    # the drag's move path RE-SAMPLES Alt (:681) — send a real event.
    p = QPointF(*scr(x, y))
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.LeftButton, Qt.LeftButton, mods))


def _release(ed, x, y):
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, QPoint(*scr(x, y)))


def test_a_line_body_drag_translates_uniformly(ed):
    sk = ed.model.sketch
    a = sk.point(20, 10); b = sk.point(50, 10)
    l = ed.model.add_line(a, b)
    ed._solve()
    n_hist = len(ed._hist)
    _press(ed, 35, 10)                       # the middle of the BODY
    assert ed._drag is not None
    assert ed._sel == [l]                    # grabbing selects, Fusion law
    _move(ed, 35.25, 10.25)                  # sub-tolerance first steps:
    assert a.y > 10.0                        #  the old self-line onentity
    _move(ed, 35.5, 10.5)                    #  clamp (1 mm tol) can't hold
    _move(ed, 45, 20)                        #  the crowd on the stale line
    _release(ed, 45, 20)
    assert ed._drag is None                  # a release ends the grab
    assert (a.x - 20, a.y - 10) == pytest.approx((10.0, 10.0), abs=1e-9)
    assert (b.x - 50, b.y - 10) == pytest.approx((10.0, 10.0), abs=1e-9)
    assert math.dist((a.x, a.y), (b.x, b.y)) == pytest.approx(30.0, abs=1e-9)
    assert len(ed._hist) == n_hist + 1       # ONE history push per drag


def test_a_dragged_body_pulls_its_chain_through_the_solver(ed):
    sk = ed.model.sketch
    a = sk.point(20, 10); b = sk.point(50, 10); c = sk.point(50, 40)
    ed.model.add_line(a, b); ed.model.add_line(b, c)   # shared corner b
    ed._solve()
    _press(ed, 35, 10)                       # drag l1 by its middle
    _move(ed, 40, 5)                         # delta (+5, -5)
    _release(ed, 40, 5)
    assert (b.x, b.y) == pytest.approx((55.0, 5.0), abs=1e-9)   # rode along
    assert sk.lines[1].a is b                # identity IS coincidence —
    assert math.dist((c.x, c.y), (b.x, b.y)) != pytest.approx(   #  l2 swung
        30.0, abs=0.5)                       #   to follow its moved end
    assert (c.x, c.y) == pytest.approx((50.0, 40.0), abs=1e-9)  # c unpinned


def test_a_circle_drag_moves_the_centre_and_keeps_the_radius(ed):
    sk = ed.model.sketch
    c = sk.point(30, 20)
    circ = ed.model.add_circle(c, 12)
    ed._solve()
    _press(ed, 42, 20)                       # ON THE RING (east point):
    assert ed._drag is not None              #  a body grab, not a point
    _move(ed, 45, 35)
    _release(ed, 45, 35)
    assert (c.x, c.y) == pytest.approx((33.0, 35.0), abs=1e-9)  # raw delta
    assert circ.r == 12.0                    # radius is a scalar: the SHAPE
    assert circ.c is c                       #  rides the move, never drifts


def test_an_arc_drag_is_a_rigid_slide(ed):
    sk = ed.model.sketch
    a = sk.point(20, -30); m = sk.point(35, -20); b = sk.point(50, -30)
    ar = Arc(a, m, b)
    sk.arcs.append(ar)
    ed._solve()
    chord0 = (b.x - a.x, b.y - a.y)
    sag0 = abs(m.y - (a.y + b.y) / 2)
    _press(ed, 27.5, -24.0)                  # the a-m stretch of the curve
    assert ed._drag is not None              #  (never a defining point)
    _move(ed, 32.5, -19.0)                   # delta (+5, +5)
    _release(ed, 32.5, -19.0)
    for p, s0 in ((a, 20), (m, 35), (b, 50)):
        assert p.x == pytest.approx(s0 + 5.0, abs=1e-9)
    assert (b.y - a.y) == pytest.approx(0.0, abs=1e-9)          # chord
    assert abs(m.y - (a.y + b.y) / 2) == pytest.approx(sag0, abs=1e-9)
    assert (b.x - a.x, b.y - a.y) == pytest.approx(chord0, abs=1e-9)


def test_the_crowd_rides_the_magnet_that_catches(ed):
    sk = ed.model.sketch
    a = sk.point(20, 10); b = sk.point(50, 10)
    ed.model.add_line(a, b)
    e = sk.point(70, 31)                     # a distant body's endpoint
    ed.model.add_line(e, sk.point(95, 40))
    ed._solve()
    _press(ed, 35, 10)
    _move(ed, 54.5, 30.75)                   # raw b = (69.5, 30.75): 0.56 mm
    assert ed._snap_obj is not None          #  short of e — INSIDE the
    assert ed._snap_obj.kind == "endpoint"   #  2.25 mm tolerance: CATCH
    _release(ed, 54.5, 30.75)
    assert math.dist((b.x, b.y), (70.0, 31.0)) < 1e-12   # b EXACT on e
    assert (a.x, a.y) == pytest.approx((40.0, 31.0), abs=1e-9)
    #  the catch shifted the WHOLE delta (+0.5, +0.25) — the crowd rode it
    assert math.dist((a.x, a.y), (b.x, b.y)) == pytest.approx(30.0, abs=1e-9)


def test_alt_suppresses_the_crowd_magnet(ed):
    sk = ed.model.sketch
    a = sk.point(20, 10); b = sk.point(50, 10)
    ed.model.add_line(a, b)
    e = sk.point(70, 31)
    ed.model.add_line(e, sk.point(95, 40))
    ed._solve()
    _press(ed, 35, 10, Qt.AltModifier)       # the magnet's off switch —
    _move(ed, 54.5, 30.75, Qt.AltModifier)   #  HELD through the drag
    _release(ed, 54.5, 30.75)
    assert (b.x, b.y) == pytest.approx((69.5, 30.75), abs=1e-9)  # RAW
    assert math.dist((b.x, b.y), (70.0, 31.0)) > 0.3             # no catch
    assert ed._snap_hint is None


def test_locked_geometry_refuses_the_grab(ed):
    sk = ed.model.sketch
    a = sk.point(20, 10); b = sk.point(50, 10)
    l = ed.model.add_line(a, b)
    ed.model.toggle(Fixed, (a,))
    ed.model.toggle(Fixed, (b,))
    ed._solve()                              # the M119 witness: dof 0,0
    assert ed._last_result.point_dof[a.id] == 0
    n_hist = len(ed._hist)
    _press(ed, 35, 10)                       # the body: refuse, but SELECT
    assert ed._drag is None
    _move(ed, 45, 20); _release(ed, 45, 20)
    assert (a.x, a.y, b.x, b.y) == (20.0, 10.0, 50.0, 10.0)   # NOT a wobble
    assert len(ed._hist) == n_hist           #   (no solver halfway-house)
    assert ed._sel == [l]
    _press(ed, 20, 10)                       # the locked POINT: same law —
    assert ed._drag_pt is None               #   today it would fight Fixed
    _move(ed, 30, 15); _release(ed, 30, 15)
    assert (a.x, a.y) == (20.0, 10.0)


def test_the_single_point_law_still_follows_the_cursor_absolutely(ed):
    sk = ed.model.sketch
    p = sk.point(30, 30)
    ed._solve()
    _press(ed, 30, 30)                       # dead centre on the point
    assert ed._drag_pt is p and ed._drag is None
    _move(ed, 37.5, 35)
    _release(ed, 37.5, 35)
    assert p.x == 37.5 and p.y == 35.0       # EXACTLY the cursor's world —
    #   the old absolute law, untouched by the crowd's delta law


def test_a_no_move_click_selects_without_history_or_motion(ed):
    sk = ed.model.sketch
    a = sk.point(20, 10); b = sk.point(50, 10)
    l = ed.model.add_line(a, b)
    ed._solve()
    n_hist = len(ed._hist)
    _press(ed, 35, 10)
    _release(ed, 35, 10)                     # a click, not a drag
    assert ed._sel == [l]
    assert len(ed._hist) == n_hist           # nothing pushed
    assert (a.x, a.y, b.x, b.y) == (20.0, 10.0, 50.0, 10.0)
