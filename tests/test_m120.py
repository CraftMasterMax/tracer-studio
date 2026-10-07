"""M120 — object snaps + live auto-constrain on drop.

core/snaps.py is pure geometry, so its contract is pinned with hand-
computed truths (crossings land on exact coordinates, arc spans admit
only their own roots).  The editor then does three things: reuse an
existing Point when the magnet carries one (identity IS coincidence),
mint + BIND when the snap only implies a constraint (the live, free
twin of Fusion's premium batch AutoConstrain [ui_sketchmode]), and
show a typed glyph.  Alt suppresses everything.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF                      # noqa: E402

from tracer.core import snaps as SP                     # noqa: E402
from tracer.core.sketch.solver import Sketch            # noqa: E402
from tracer.core.sketch.constraints import PointOnLine   # noqa: E402


# ---- the pure core (no Qt) ----------------------------------------------------
def _cross_sketch():
    sk = Sketch()
    a, b = sk.point(0, 0), sk.point(20, 20)
    c, d = sk.point(0, 20), sk.point(20, 0)
    l1, l2 = sk.line(a, b), sk.line(c, d)
    return sk, (a, b, c, d, l1, l2)


def test_intersection_wins_over_a_closer_curve_slide():
    sk, _ = _cross_sketch()
    s = SP.best(sk, 10.2, 9.9, 1.0)          # on-entity is nearer...
    assert s.kind == "intersection"          # ...but typed magnets rule
    assert (s.x, s.y) == pytest.approx((10.0, 10.0), abs=1e-9)


def test_endpoint_wins_the_exact_tie():
    sk, (a, b, c, d, l1, l2) = _cross_sketch()
    sk.point(20, 20)                          # free point sitting ON b
    s = SP.best(sk, 20.0, 20.0, 1.0)
    assert s.kind == "endpoint" and s.pt in (b, sk.points[-1])


def test_circle_centre_reuses_the_very_point_object():
    sk = Sketch()
    cc = sk.circle(sk.point(40, 10), 5.0)
    s = SP.best(sk, 40.1, 9.9, 1.0)
    assert s.kind == "center" and s.pt is cc.c


def test_quadrants_report_their_exact_stations():
    sk = Sketch()
    sk.circle(sk.point(0, 0), 5.0)
    got = {(round(s.x, 9), round(s.y, 9))
           for s in SP.candidates(sk, 5.05, 0.0, 1.0)
           if s.kind == "quadrant"}
    assert (5.0, 0.0) in got


def test_arc_span_admits_only_its_own_roots():
    sk = Sketch()
    sk.arc(sk.point(60, 0), sk.point(70, 10), sk.point(80, 0))
    sk.line(sk.point(65, 2), sk.point(65, 20))    # crosses the full circle
    roots = [(s.x, s.y) for s in SP.candidates(sk, 65.0, 8.66, 1.0)
             if s.kind == "intersection"]
    assert len(roots) == 1                       # the lower root is off-arc
    assert roots[0][1] == pytest.approx(math.sqrt(75.0), abs=1e-6)


def test_on_entity_is_the_fallback_and_skip_kills_self_snap():
    sk, (a, b, c, d, l1, l2) = _cross_sketch()
    s = SP.best(sk, 4.9, 5.05, 1.0)            # mid-line, nothing typed
    assert s.kind == "onentity" and s.entity is l1
    hits = SP.candidates(sk, b.x + 0.1, b.y, 0.5, skip=b)
    assert not any(x.pt is b for x in hits)


def test_candidates_sort_nearest_first():
    sk, _ = _cross_sketch()
    ds = [s.dist for s in SP.candidates(sk, 10.0, 10.0, 5.0)]
    assert ds == sorted(ds)


def test_autolink_table():
    sk, (a, b, c, d, l1, l2) = _cross_sketch()
    cc = sk.circle(sk.point(40, 10), 5.0)
    p = sk.point(0, 0)
    kinds = lambda sn: [type(x).__name__ for x in SP.autolink(sn, p)]
    assert SP.autolink(SP.Snap(b.x, b.y, "endpoint", pt=b, entity=l1), p) \
        == []                                   # reuse needs nothing
    assert kinds(SP.Snap(4.9, 4.9, "onentity", entity=l1)) == ["PointOnLine"]
    assert kinds(SP.Snap(45.0, 10.0, "onentity", entity=cc)) == \
        ["PointOnCircle"]
    assert kinds(SP.Snap(10, 10, "intersection", entity=l1, entity2=l2)) \
        == ["PointOnLine", "PointOnLine"]
    assert kinds(SP.Snap(10, 10, "midpoint", entity=l1)) == ["Midpoint"]
    assert kinds(SP.Snap(0, 0, "origin")) == []


# ---- the editor contract (Qt, offscreen) --------------------------------------
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(qapp):
    from tracer.core.sketch.model import SketchModel
    from tracer.ui.sketcheditor import SketchCanvas
    ed = SketchCanvas()
    ed.set_model(SketchModel())
    ed.resize(600, 400)
    yield ed
    ed.deleteLater()


def _sq(ed, x, y):                            # world → the screen QPointF
    s = ed.w2s(x, y)
    return QPointF(s.x(), s.y())


def test_magnet_reuses_existing_points(editor, qapp):
    sk = editor.model.sketch
    a = sk.point(10, 10)
    t = editor._snap_target(_sq(editor, 10.1, 9.9))
    assert t is a
    assert editor._snap_obj.kind == "endpoint"


def test_drop_on_a_line_mints_AND_binds(editor, qapp):
    sk = editor.model.sketch
    ln = sk.line(sk.point(0, 0), sk.point(50, 0))
    before = len(sk.constraints)
    p = editor._place_point(_sq(editor, 35.05, 0.15))
    assert p is not ln.a and p is not ln.b
    assert p.y == pytest.approx(0.0, abs=0.2)
    added = sk.constraints[before:]
    assert any(isinstance(c, PointOnLine) and c.p is p for c in added)
    r = editor._solve()                        # the bind must actually close
    res = editor._last_result
    assert res.converged


def test_alt_suppresses_the_whole_magnet(editor, qapp):
    sk = editor.model.sketch
    a = sk.point(10, 10)
    editor._no_snap = True
    try:
        assert editor._snap_target(_sq(editor, 10.0, 10.0)) is None
        assert editor._snap_obj is None
    finally:
        editor._no_snap = False


def test_origin_still_magnetizes(editor, qapp):
    t = editor._snap_target(_sq(editor, 0.1, -0.1))
    assert t == (0.0, 0.0)
    assert editor._snap_obj.kind == "origin"


def test_drop_on_a_station_gets_the_stronger_bind(editor, qapp):
    # midpoint beats on-entity even at equal distance — and the bind is
    # the Midpoint constraint, not the weak slide
    from tracer.core.sketch.constraints import Midpoint
    sk = editor.model.sketch
    ln = sk.line(sk.point(0, 0), sk.point(50, 0))
    before = len(sk.constraints)
    p = editor._place_point(_sq(editor, 25.05, 0.15))
    added = sk.constraints[before:]
    assert any(isinstance(c, Midpoint) and c.p is p for c in added)


def test_glyph_pixels_paint_without_crashing(editor, qapp):
    sk = editor.model.sketch
    sk.circle(sk.point(20, 20), 8.0)
    editor._snap_target(_sq(editor, 28.1, 20.0))      # quadrant of circle
    assert editor._snap_obj is not None
    pix = editor.grab()
    assert not pix.isNull()
