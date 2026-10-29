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


# ---- Rung 2: the selection is ONE handle (crowd drag) ----------------------

def _click(ed, x, y, mods=Qt.NoModifier):
    _press(ed, x, y, mods)
    _release(ed, x, y)


def test_grabbing_a_member_moves_the_whole_point_selection(ed):
    sk = ed.model.sketch
    p1 = sk.point(10, 10); p2 = sk.point(30, 10); s = sk.point(60, -40)
    ed._solve()
    _click(ed, 10, 10)                      # select p1
    _click(ed, 30, 10, Qt.ControlModifier)  # Ctrl adds p2
    assert ed._sel == [p1, p2]
    _press(ed, 10, 10)                      # grab the ALREADY-SELECTED p1:
    assert ed._drag is not None             #  the CROWD arms, not a point
    assert ed._drag_pt is None
    _move(ed, 22.5, 22.5); _release(ed, 22.5, 22.5)
    assert (p1.x, p1.y) == pytest.approx((22.5, 22.5), abs=1e-9)
    assert (p2.x, p2.y) == pytest.approx((42.5, 22.5), abs=1e-9)  # rode too
    assert (s.x, s.y) == (60.0, -40.0)     # the stranger never budged


def test_a_mixed_selection_drags_as_one_crowd(ed):
    sk = ed.model.sketch
    a = sk.point(10, -30); b = sk.point(40, -30)
    l = ed.model.add_line(a, b)
    p = sk.point(60, -45); s = sk.point(60, -10)
    ed._solve()
    _click(ed, 60, -45)
    _click(ed, 25, -30, Qt.ControlModifier)        # line + point together
    assert ed._sel == [p, l]
    _press(ed, 60, -45)                            # grab the POINT…
    _move(ed, 67.5, -30); _release(ed, 67.5, -30)   # …the LINE rides with it
    for pt, x0, y0 in ((p, 60, -45), (a, 10, -30), (b, 40, -30)):
        assert (pt.x - x0, pt.y - y0) == pytest.approx((7.5, 15.0), abs=1e-9)
    assert (s.x, s.y) == (60.0, -10.0)            # byte-still bystander


def test_a_stranger_grab_reselects_and_moves_alone(ed):
    sk = ed.model.sketch
    a = sk.point(10, 10); b = sk.point(40, 10)
    l1 = ed.model.add_line(a, b)
    cc = sk.point(10, 25); d = sk.point(40, 25)
    l2 = ed.model.add_line(cc, d)
    ed._solve()
    _click(ed, 25, 10)                             # select l1
    assert ed._sel == [l1]
    _press(ed, 25, 25)                             # grab the stranger l2…
    assert ed._sel == [l2]                         #  …it becomes THE pick
    _move(ed, 37.5, 37.5); _release(ed, 37.5, 37.5)
    assert (cc.x, cc.y) == pytest.approx((22.5, 37.5), abs=1e-9)
    assert (d.x, d.y) == pytest.approx((52.5, 37.5), abs=1e-9)
    assert (a.x, a.y, b.x, b.y) == (10.0, 10.0, 40.0, 10.0)   # l1 byte-still


def test_a_lone_selected_point_still_follows_the_cursor_absolutely(ed):
    sk = ed.model.sketch
    p = sk.point(20, 40)
    ed._solve()
    _click(ed, 20, 40)                             # select p (alone)
    _press(ed, 20, 40)                             # grab it again: a crowd
    assert ed._drag_pt is p and ed._drag is None    #  of ONE is NOT a crowd
    _move(ed, 27.5, 45); _release(ed, 27.5, 45)
    assert p.x == 27.5 and p.y == 45.0            # absolute law, byte-exact


def test_the_point_crowd_rides_one_magnet_to_an_exact_catch(ed):
    sk = ed.model.sketch
    p1 = sk.point(10, 10); p2 = sk.point(40, 10); t = sk.point(52.5, 30)
    ed._solve()
    _click(ed, 10, 10)
    _click(ed, 40, 10, Qt.ControlModifier)
    _press(ed, 10, 10)
    _move(ed, 22, 29.75)                           # raw p2 = (52, 29.75):
    assert ed._snap_obj is not None                #  0.56mm short of t —
    assert ed._snap_obj.kind == "endpoint"         #  INSIDE tolerance
    _release(ed, 22, 29.75)
    assert math.dist((p2.x, p2.y), (52.5, 30.0)) < 1e-12   # EXACT catch
    assert (p1.x, p1.y) == pytest.approx((22.5, 30.0), abs=1e-9)
    #  the catch shifted the WHOLE crowd by (+0.5, +0.25) — p1 rode it


def test_one_undo_restores_the_whole_crowd_byte_exact(ed):
    sk = ed.model.sketch
    p1 = sk.point(10, 10); p2 = sk.point(30, -20)
    ed._solve()
    _click(ed, 10, 10)
    _click(ed, 30, -20, Qt.ControlModifier)
    n_hist = len(ed._hist)
    _press(ed, 10, 10)
    _move(ed, 12.5, 12.5)
    _move(ed, 15, 15)                              # two moves…
    _release(ed, 15, 15)
    assert len(ed._hist) == n_hist + 1             #  ONE push for the drag
    assert ed.undo_op()
    #  _restore SWAPS model.sketch (new objects): assert on the RESTORED
    #  model, not on the pre-jump references — both members byte-exact.
    pos = sorted((p.x, p.y) for p, _ in ed._all_points())
    assert pos == [(10.0, 10.0), (30.0, -20.0)]


# ---- Rung 3: the hand becomes a PHOTOCOPY (Ctrl+drag duplicate) ------------

def test_ctrl_drag_photocopies_the_point_selection(ed):
    sk = ed.model.sketch
    p1 = sk.point(10, 10); p2 = sk.point(30, 10); s = sk.point(60, -40)
    ed._solve()
    _click(ed, 10, 10)
    _click(ed, 30, 10, Qt.ControlModifier)          # selection {p1, p2}
    _press(ed, 10, 10, Qt.ControlModifier)          # Ctrl on a MEMBER…
    _move(ed, 22.5, 22.5)                           # …motion = photocopy
    _release(ed, 22.5, 22.5)
    assert (p1.x, p1.y) == (10.0, 10.0)             # the ORIGINALS never
    assert (p2.x, p2.y) == (30.0, 10.0)             #  move: byte-exact
    assert (s.x, s.y) == (60.0, -40.0)
    ghosts = [p for p in sk.points if p not in (p1, p2, s)]
    assert len(ghosts) == 2                         # the crowd was copied
    got = sorted((round(g.x, 9), round(g.y, 9)) for g in ghosts)
    assert got == [(22.5, 22.5), (42.5, 22.5)]      # ghost delta (12.5,12.5)
    assert set(ed._sel) == set(ghosts)              # release picks the copies


def test_a_ctrl_click_without_motion_still_deselects(ed):
    sk = ed.model.sketch
    p = sk.point(20, 40); q = sk.point(40, 40)
    ed._solve()
    _click(ed, 20, 40)                              # select p
    _press(ed, 20, 40, Qt.ControlModifier)          # Ctrl on it: the toggle
    assert ed._sel == [p]                           #  DEFERS to release…
    _release(ed, 20, 40)
    assert ed._sel == []                            #  …where it lands
    _click(ed, 20, 40)
    _click(ed, 40, 40, Qt.ControlModifier)          # selection {p, q}
    _click(ed, 20, 40, Qt.ControlModifier)          # ctrl-click a member
    assert ed._sel == [q]                           #  drops just it (today)


def test_a_photocopied_line_lands_rigid_and_free(ed):
    sk = ed.model.sketch
    a = sk.point(20, 10); b = sk.point(50, 10)
    l = ed.model.add_line(a, b)
    ed.model.toggle(Fixed, (a,))                    # a constraint EXISTS…
    ed._solve()
    _click(ed, 35, 10)
    _press(ed, 35, 10, Qt.ControlModifier)
    _move(ed, 45, 20)                               # delta (10, 10)
    _release(ed, 45, 20)
    assert len(sk.lines) == 2
    g = sk.lines[1]
    assert (g.a.x, g.a.y) == pytest.approx((30.0, 20.0), abs=1e-9)
    assert (g.b.x, g.b.y) == pytest.approx((60.0, 20.0), abs=1e-9)
    assert math.dist((g.a.x, g.a.y), (g.b.x, g.b.y)) == 30.0   # EXACT rigid
    assert (a.x, a.y, b.x, b.y) == (20.0, 10.0, 50.0, 10.0)    # source still
    assert len(sk.constraints) == 1   # …but copies arrive FREE (rung-3 law)


def test_the_photocopy_keeps_corner_identity(ed):
    sk = ed.model.sketch
    a = sk.point(10, 10); b = sk.point(40, 10); c = sk.point(40, 35)
    l1 = ed.model.add_line(a, b); l2 = ed.model.add_line(b, c)
    ed._solve()
    _click(ed, 25, 10)
    _click(ed, 40, 22.5, Qt.ControlModifier)        # the CHAIN {l1, l2}
    _press(ed, 25, 10, Qt.ControlModifier)
    _move(ed, 35, 20)                               # delta (10, 10)
    _release(ed, 35, 20)
    g1, g2 = sk.lines[2], sk.lines[3]
    assert g1.b is g2.a                             # one shared NEW corner:
    assert (g1.b.x, g1.b.y) == pytest.approx((50.0, 20.0), abs=1e-9)
    assert (a.x, a.y, b.x, b.y, c.x, c.y) == \
        (10.0, 10.0, 40.0, 10.0, 40.0, 35.0)        # negatives untouched


def test_the_ghost_never_magnetizes_onto_its_own_negative(ed):
    sk = ed.model.sketch
    a = sk.point(20, 10); b = sk.point(50, 10)
    ed.model.add_line(a, b)
    ed._solve()
    _click(ed, 35, 10)
    _press(ed, 35, 10, Qt.ControlModifier)
    _move(ed, 35.25, 10.25)                         # ONE pixel (0.25 mm):
    g = sk.lines[1]                                 #  without the source-
    assert (g.a.x, g.a.y) == pytest.approx((20.25, 10.25), abs=1e-9)  # skip
    assert ed._snap_hint is None                    #  law the ghost would
    _release(ed, 35.25, 10.25)                      #  never leave home
    assert (a.x, a.y) == (20.0, 10.0)


def test_the_ghost_rides_a_third_bodys_magnet(ed):
    sk = ed.model.sketch
    a = sk.point(20, 10); b = sk.point(50, 10)
    ed.model.add_line(a, b)
    e = sk.point(70, 31)                            # a THIRD body's endpoint
    ed._solve()
    _click(ed, 35, 10)
    _press(ed, 35, 10, Qt.ControlModifier)
    _move(ed, 54.5, 30.75)                          # ghost b raw: 0.56 short
    assert ed._snap_obj is not None
    assert ed._snap_obj.kind == "endpoint"          #  — INSIDE tolerance
    _release(ed, 54.5, 30.75)
    g = sk.lines[1]
    assert math.dist((g.b.x, g.b.y), (70.0, 31.0)) < 1e-12   # EXACT catch
    assert (g.a.x, g.a.y) == pytest.approx((40.0, 31.0), abs=1e-9)
    assert (b.x, b.y) == (50.0, 10.0)               # the source holds still


def test_one_undo_eats_the_photocopy_whole(ed):
    sk = ed.model.sketch
    a = sk.point(20, 10); b = sk.point(50, 10)
    l = ed.model.add_line(a, b)
    ed._solve()
    n_pts, n_lines = len(sk.points), len(sk.lines)
    n_hist = len(ed._hist)
    _click(ed, 35, 10)
    _press(ed, 35, 10, Qt.ControlModifier)
    _move(ed, 45, 20)
    assert len(ed._hist) == n_hist + 1              # ONE push, at copy-arm
    _release(ed, 45, 20)
    assert ed.undo_op()
    sk2 = ed.model.sketch                           # _restore SWAPS it:
    assert len(sk2.lines) == n_lines                #  assert on the model
    assert len(sk2.points) == n_pts                 #   as it stands after
    pos = sorted((p.x, p.y) for p, _ in ed._all_points())
    assert pos == [(20.0, 10.0), (50.0, 10.0)]      # byte-exact, ghosts gone


def test_ctrl_press_on_a_stranger_adds_immediately_and_copies_nothing(ed):
    sk = ed.model.sketch
    a = sk.point(10, 10); b = sk.point(40, 10)
    l1 = ed.model.add_line(a, b)
    cc = sk.point(10, 25); d = sk.point(40, 25)
    l2 = ed.model.add_line(cc, d)
    ed._solve()
    _click(ed, 25, 10)                              # select l1
    _press(ed, 25, 25, Qt.ControlModifier)          # Ctrl on the STRANGER:
    assert ed._sel == [l1, l2]                      #  append AT PRESS (the
    assert ed._pend_toggle is None                  #   rung-2 law stands)
    _move(ed, 30, 30)                               # motion WITHOUT a copy
    _release(ed, 30, 30)
    assert len(sk.lines) == 2                       # nothing was photocopied
    assert (a.x, a.y, cc.x, cc.y) == (10.0, 10.0, 10.0, 25.0)  # all byte-still
