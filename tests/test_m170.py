"""M170 rung 1 — THE WELD (weld_points: two Points, ONE identity).

The drag magnet catches today and forgets tomorrow: two distinct Points
merely share coordinates, and the next drag drifts them apart. The join
law of this product is IDENTITY (close_corner merges, split_entity
reuses its seam, extend_end drives one Point through stub+joint+halves),
so the weld is the generic form of all three: every entity and EVERY
constraint naming the loser names the survivor after the merge.

The re-home law differs from the CUT's on purpose: a cut splits one
thing into two and a metric on it becomes AMBIGUOUS (drop); a weld fuses
two things into one, so re-homing every fact is never ambiguous - the
Distance the user pinned to that corner FOLLOWS the corner. The one
cleanup: a Coincident whose two sides just became the same Point is
vacuous and dies. keep's coordinates WIN (the magnet target is what the
user aimed at); gone leaves sk.points exactly as close_corner's loser
does. Refusals land BEFORE mutation; no hist push (the caller's gesture
owns the one snapshot the drag already paid).

This rung is kernel-only: the canvas wires the drop in rung 2.
"""
import pytest

pytest.importorskip("PySide6")

from tracer.core.sketch.constraints import Coincident, Distance      # noqa: E402
from tracer.core.sketch.entities import Point                        # noqa: E402
from tracer.core.sketch.model import SketchModel                      # noqa: E402
from tracer.core.sketch.trim import weld_points                       # noqa: E402
from tracer.ui.sketcheditor import SketchCanvas                       # noqa: E402


def _snap_state(m):
    sk = m.sketch
    return (len(sk.points), len(sk.lines), len(sk.arcs), len(sk.circles),
            len(sk.ellipses), len(sk.constraints),
            [(l.a.x, l.a.y, l.b.x, l.b.y) for l in sk.lines])


def test_two_ends_one_identity():
    """The magnet-caught corner (two Points, one coordinate) becomes ONE
    Point serving both lines; the loser leaves sk.points."""
    m = SketchModel()
    pa, pb, pc, pd = (m.point(0, 0), m.point(5, 5),
                      m.point(10, 0), m.point(5, 5))       # pd rides pb
    l1 = m.add_line(pa, pb)
    l2 = m.add_line(pc, pd)
    out = weld_points(m, pb, pd)
    sk = m.sketch
    assert out is pb and l1.b is pb and l2.b is pb         # ONE identity
    assert pd not in sk.points and len(sk.points) == 3
    assert (l2.b.x, l2.b.y) == (5.0, 5.0)


def test_metric_follows_the_corner():
    """The weld law vs the cut law: fusing is never ambiguous, so the
    Distance that named the loser now names the survivor - re-homed,
    not dropped."""
    m = SketchModel()
    o, p, gone = m.point(0, 0), m.point(8, 0), m.point(8, 0)
    m.add_line(o, p)
    m.constrain(Distance(o, gone, 8.0))
    weld_points(m, p, gone)
    (d,) = [c for c in m.sketch.constraints]
    assert d.q is p and abs(d.value - 8.0) < 1e-12


def test_tautological_coincident_dies_sibling_survives():
    """Coincident(gone, keep) welded itself shut - vacuous, deleted. The
    Coincident onto a THIRD point is a real join: re-homed, alive."""
    m = SketchModel()
    keep, gone, third = m.point(1, 1), m.point(1, 1), m.point(4, 4)
    m.sketch.constraints.append(Coincident(gone, keep))
    m.sketch.constraints.append(Coincident(gone, third))
    weld_points(m, keep, gone)
    (c,) = [c for c in m.sketch.constraints if isinstance(c, Coincident)]
    assert c.p is keep and c.q is third                    # one real join


def test_refusals_land_before_mutation():
    """Self-weld and a stranger Point refuse with the scene byte-kept."""
    m = SketchModel()
    a, b = m.point(0, 0), m.point(3, 4)
    m.add_line(a, b)
    state = _snap_state(m)
    with pytest.raises(ValueError):
        weld_points(m, a, a)                               # self-weld
    with pytest.raises(ValueError):
        weld_points(m, a, Point(9, 9))                     # off-scene twin
    assert _snap_state(m) == state


def test_every_carrier_field_rewires():
    """Line.a, Arc.m, Circle.c, Ellipse.c - the flat identity scan sees
    every Point slot there is (audit: no constraint or entity hides a
    Point inside a composite)."""
    m = SketchModel()
    gone = m.point(2, 2)
    keep = m.point(2, 2)
    s = m.sketch
    s.line(m.point(0, 0), gone)
    s.arc(gone, m.point(1, 4), m.point(3, 1))
    s.circle(gone, 1.5)
    s.ellipse(gone, 2.0, 1.0)
    weld_points(m, keep, gone)
    assert s.lines[0].b is keep and s.arcs[0].a is keep
    assert s.circles[0].c is keep and s.ellipses[0].c is keep
    assert gone not in s.points


def test_the_weld_closes_the_loop_and_the_target_coords_win():
    """The user story in kernel form: two legs fell SHORT of the corner
    (0.5 apart - no eps-weld saves that); the weld lands both on keep's
    coordinates and the profile suddenly has a loop."""
    m = SketchModel()
    pa = m.point(0, 0)
    pb = m.point(10, 10)                                   # magnet target
    pc = m.point(10, 10.5)                                 # the drifted end
    pd = m.point(20, 0)
    m.add_line(pa, pb)
    m.add_line(pd, pc)
    m.add_line(pd, pa)                                     # the base
    loops0, _ = m.to_loops()
    assert loops0 == []                                    # gap: no loop
    weld_points(m, pb, pc)
    assert m.sketch.lines[1].b is pb and pb.y == 10.0      # keep's coords
    loops, _warns = m.to_loops()
    assert len(loops) == 1


# ---- Rung 2: the canvas KEEPS the promise (weld on drop) ------------------
#
# mouseReleaseEvent re-probes the magnet at the drop: a catch that names
# an EXISTING Point welds identity (no constraint, no second snapshot -
# the weld rides the drag's own push, so one undo restores the whole
# gesture). Alt still suppresses; a catch on no-Point (origin/grid/curve
# body) keeps today's exact-coords law (rung 3 takes the curves); and
# the scene itself may refuse - an entity or constraint naming BOTH
# points hushes the drop.

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa
from PySide6.QtGui import QMouseEvent                                # noqa
from PySide6.QtTest import QTest                                     # noqa
from PySide6.QtWidgets import QApplication                           # noqa


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


def _scr(x, y):                   # world mm -> widget px (scale 4, centre 0)
    return (int(round(300 + 4.0 * x)), int(round(200 - 4.0 * y)))


def _press(ed, x, y, mods=Qt.NoModifier):
    QTest.mousePress(ed, Qt.LeftButton, mods, QPoint(*_scr(x, y)))


def _move(ed, x, y, mods=Qt.NoModifier):
    p = QPointF(*_scr(x, y))
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.LeftButton, Qt.LeftButton, mods))


def _release(ed, x, y):
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, QPoint(*_scr(x, y)))


def _open_frame(m):
    """Triangle with ONE leg 2mm short of the top corner: p4 hovers at
    (10,12) above p2(10,10) - the unbuilt joint, two squares, no loop."""
    p1, p2, p3 = m.point(0, 0), m.point(10, 10), m.point(10, 0)
    p4 = m.point(10, 12)
    m.add_line(p1, p2)
    m.add_line(p4, p3)
    m.add_line(p3, p1)
    return p1, p2, p3, p4


def test_a_caught_drop_welds_and_the_frame_closes(ed):
    m = ed.model
    sk = m.sketch
    p1, p2, p3, p4 = _open_frame(m)
    ed._solve()
    n0 = len(ed._hist)
    _press(ed, 10, 12)
    assert ed._drag_pt is p4
    _move(ed, 10, 10.2)                          # the magnet CATCHES p2
    _release(ed, 10, 10.2)
    assert sk.lines[1].a is p2                   # identity, not contact
    assert p4 not in sk.points
    assert len(m.to_loops()[0]) == 1             # and the loop is REAL
    assert len(ed._hist) == n0 + 1               # one snapshot rode it
    ed.undo_op()                                 #  the WHOLE gesture:
    sk2 = m.sketch                               #  _restore swaps objects
    ends = [(l.a.x, l.a.y) for l in sk2.lines]
    assert (10.0, 12.0) in ends                  # p4 rides back
    assert len(sk2.points) == 4
    assert m.to_loops()[0] == []


def test_alt_releases_raw_and_the_corner_stays_two_points(ed):
    m = ed.model
    sk = m.sketch
    *_, p4 = _open_frame(m)
    p2 = sk.points[1]
    ed._solve()
    _press(ed, 10, 12)
    _move(ed, 10, 10.2, Qt.AltModifier)          # Alt suppresses the magnet
    _move(ed, 10, 10.0, Qt.AltModifier)          #  DROPPED dead on target:
    _release(ed, 10, 10.0)                       #   still NO weld (explicit
    assert p4 in sk.points                       #    bypass, exact coords)
    assert sk.lines[1].a is p4 and p4.y == 10.0


def test_a_drop_on_no_magnet_keeps_the_absolute_law(ed):
    m = ed.model
    sk = m.sketch
    *_, p4 = _open_frame(m)
    ed._solve()
    _press(ed, 10, 12)
    _move(ed, 25, 25)
    _release(ed, 25, 25)                         # free air: cursor law,
    assert (p4.x, p4.y) == (25.0, 25.0)          #   points untouched
    assert p4 in sk.points and len(sk.points) == 4


def test_a_click_that_never_moved_never_welds(ed):
    m = ed.model
    sk = m.sketch
    p1, p2, p3, p4 = _open_frame(m)
    p4.x = p4.y = 10.0                           # sitting EXACTLY on p2:
    ed._solve()                                  #   a click must not fuse
    n0 = len(ed._hist)
    _press(ed, 10, 10)
    _release(ed, 10, 10)
    assert p4 in sk.points and sk.lines[1].a is p4
    assert len(ed._hist) == n0                   #  and pays nothing at all


def test_a_fact_naming_both_points_refuses_the_weld(ed):
    m = ed.model
    sk = m.sketch
    p1, p2, p3, p4 = _open_frame(m)
    m.constrain(Distance(p4, p2, 2.0))           # the scene says: TWO
    ed._solve()
    n0 = len(ed._hist)
    _press(ed, 10, 12)
    _move(ed, 10, 10.2)
    _release(ed, 10, 10.2)
    assert p4 in sk.points and sk.lines[1].a is p4   # refusal hushes
    assert len(ed._hist) == n0 + 1               #  (the drag paid as usual)


def test_the_end_that_would_collapse_its_own_line_refuses(ed):
    m = ed.model
    sk = m.sketch
    a = m.point(5, 5)
    b = m.point(10, 10)                          # far from the origin
    m.add_line(a, b)
    ed._solve()
    _press(ed, 10, 10)
    _move(ed, 5, 5)                              # dragging b ONTO a: the
    _release(ed, 5, 5)                           #   line would zero out
    assert b in sk.points and sk.lines[0].b is b     # refused whole
    assert (b.x, b.y) == (5.0, 5.0)              #  coords ride as dragged
