"""M28 — trim / extend two lines to their corner (/).

The cleanup verb for hand-drawn profiles: ends land EXACTLY on the
infinite-line intersection and merge into ONE shared Point (loops join
by identity). Extends may reach any distance; trims only cut stubs —
T-junction bars and true X crossings are never halved.
"""
import math

import pytest

from tracer.core.sketch.constraints import Fixed

from tracer.core.sketch.model import (SketchModel, model_from_dict,
                                      model_to_dict)
from tracer.core.sketch.trim import close_corner


def _gap_rect():
    """Four lines, each corner a deliberate gap/overshoot of ~0.3mm."""
    m = SketchModel()
    L0 = m.add_line(m.point(0.0, -0.3), m.point(40.2, 0.1))
    L1 = m.add_line(m.point(40.0, -0.2), m.point(39.8, 20.3))
    L2 = m.add_line(m.point(40.1, 20.0), m.point(-0.2, 19.9))
    L3 = m.add_line(m.point(0.0, 20.1), m.point(0.15, -0.1))
    return m, [L0, L1, L2, L3]


# ---- kernel -----------------------------------------------------------------

def test_four_sloppy_lines_become_one_closed_loop():
    m, (L0, L1, L2, L3) = _gap_rect()
    for a, b in ((L0, L1), (L1, L2), (L2, L3), (L3, L0)):
        close_corner(m, a, b)
    loops, warns = m.to_loops()
    assert len(loops) == 1 and not warns
    # sloppy input -> the EXACT corner is each pair's own crossing:
    assert 795.0 < loops[0]["area"] < 802.0
    # every corner is now ONE shared point, and the loser left sk.points
    assert len(m.sketch.points) == 4
    for a, b in ((L0, L1), (L1, L2), (L2, L3), (L3, L0)):
        assert any(pa is pb for pa in (a.a, a.b) for pb in (b.a, b.b))


def test_merge_drops_orphan_and_shared_point_sits_on_both_lines():
    m = SketchModel()
    a1, a2 = m.point(0, 0), m.point(10, 0.3)
    LA = m.add_line(a1, a2)
    LB = m.add_line(m.point(9.6, 6), m.point(10.1, 0.1))   # b2 near corner
    P = close_corner(m, LA, LB)
    assert P is a2                              # l1's end survives
    assert any(p is P for p in (LB.a, LB.b))    # l2 adopted it
    assert math.dist((P.x, P.y), (10.08, 0.30)) < 0.05
    assert len(m.sketch.points) == 3            # loser gone from the store


def test_extend_reaches_far_and_leaves_the_through_bar_alone():
    """T-junction: the stem's end extends ANY distance; the bar is never
    halved just because the crossing sits mid-span."""
    m = SketchModel()
    bar = m.add_line(m.point(0, 0), m.point(20, 0))
    stem = m.add_line(m.point(10, 8), m.point(9.9, 3))
    X = close_corner(m, stem, bar)
    assert (bar.a.x, bar.b.x) == (0.0, 20.0)          # untouched
    tip = stem.b
    assert tip is X                                    # the moved end IS P
    assert math.isclose(X.y, 0.0, abs_tol=1e-9)        # reached the bar
    assert math.isclose(X.x, 9.84, abs_tol=1e-3)


def test_stub_overshoot_is_cut_back_exactly():
    m = SketchModel()
    h = m.add_line(m.point(0, 0), m.point(20, 0))
    v = m.add_line(m.point(5, -1), m.point(5, 10))
    P = close_corner(m, h, v)
    assert (P.x, P.y) == pytest.approx((5.0, 0.0))
    assert math.dist((h.a.x, h.a.y), (5, 0)) < 1e-9   # 5mm stub cut off h
    assert math.dist((v.a.x, v.a.y), (5, 0)) < 1e-9   # 1mm stub cut off v
    assert h.a is P and any(p is P for p in (v.a, v.b))


def test_symmetric_crossing_refuses_and_touches_nothing():
    m = SketchModel()
    A = m.add_line(m.point(-10, -10), m.point(10, 10))
    B = m.add_line(m.point(-10, 10), m.point(10, -10))
    before = [(l.a.x, l.a.y, l.b.x, l.b.y) for l in m.sketch.lines]
    with pytest.raises(ValueError, match="cross mid-span"):
        close_corner(m, A, B)
    assert [(l.a.x, l.a.y, l.b.x, l.b.y) for l in m.sketch.lines] == before


def test_guard_messages():
    m = SketchModel()
    p1 = m.add_line(m.point(0, 0), m.point(10, 0))
    p2 = m.add_line(m.point(0, 5), m.point(10, 5))
    with pytest.raises(ValueError, match="parallel"):
        close_corner(m, p1, p2)
    with pytest.raises(ValueError, match="two different lines"):
        close_corner(m, p1, p1)
    p3 = m.add_line(p1.b, m.point(10, 9))
    with pytest.raises(ValueError, match="already share"):
        close_corner(m, p1, p3)


def test_constrained_loose_end_refuses_to_move():
    """When EVERY candidate end carries a constraint, the refusal names
    the constraint (not 'mid-span' or 'joined')."""
    m = SketchModel()
    h = m.add_line(m.point(0, 0), m.point(10, 0))
    v = m.add_line(m.point(5, -4), m.point(5, 3))
    m.constrain(Fixed(h.a, x=0, y=0), Fixed(h.b, x=10, y=0),
                Fixed(v.a, x=5, y=-4), Fixed(v.b, x=5, y=3))
    with pytest.raises(ValueError, match="carries a constraint"):
        close_corner(m, h, v)


def test_joined_corner_never_ripped_by_third_line():
    """A rect corner is a SHARED point (usage 2) — trimming a new line
    against a rect EDGE must extend the new line, not drag the corner."""
    m = SketchModel()
    a = m.point(0, 0)
    m.add_rect(a, m.point(20, 10))                  # closed rect, shared
    top = next(l for l in m.sketch.lines
               if abs(l.a.y - 10) < 1e-9 and abs(l.b.y - 10) < 1e-9)
    before = [(l.a.x, l.a.y, l.b.x, l.b.y) for l in m.sketch.lines]
    diag = m.add_line(m.point(35, 25), m.point(28, 16))
    P = close_corner(m, diag, top)
    rect_now = [b for b in before]
    assert [(l.a.x, l.a.y, l.b.x, l.b.y)
            for l in m.sketch.lines if l is not diag] == rect_now
    assert math.isclose(P.y, 10.0, abs_tol=1e-9)    # diag reached the edge


def test_solve_keeps_trimmed_corner_exact():
    m, (L0, L1, L2, L3) = _gap_rect()
    P = close_corner(m, L0, L1)
    X0 = (P.x, P.y)
    m.constrain(Fixed(L0.a, x=L0.a.x, y=L0.a.y))
    assert m.solve().converged
    assert math.dist((P.x, P.y), X0) < 1e-9


def test_trimmed_profile_survives_save_roundtrip():
    m, (L0, L1, L2, L3) = _gap_rect()
    for a, b in ((L0, L1), (L1, L2), (L2, L3), (L3, L0)):
        close_corner(m, a, b)
    area = m.to_loops()[0][0]["area"]
    m2 = model_from_dict(model_to_dict(m))
    loops, warns = m2.to_loops()
    assert len(loops) == 1 and not warns
    assert loops[0]["area"] == pytest.approx(area, abs=1e-6)


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                      # noqa: E402
from PySide6.QtTest import QTest                                # noqa: E402
from PySide6.QtCore import Qt                                   # noqa: E402

from tracer.ui.mainwindow import MainWindow                     # noqa: E402
from tracer.ui.renderer import SceneRenderer                    # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


def _canvas(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    return win.sketch


def test_slash_key_closes_a_corner_and_merges_points(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    LA = m.add_line(m.point(0, 0), m.point(10, 0.3))
    LB = m.add_line(m.point(9.6, 6), m.point(10.1, 0.1))
    cv._sel = [LA, LB]
    QTest.keyClick(cv, Qt.Key_T)
    qapp.processEvents()
    assert any(pa is pb for pa in (LA.a, LA.b) for pb in (LB.a, LB.b))
    assert len(m.sketch.points) == 3                # orphan dropped


def test_slash_undo_restores_both_loose_ends(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    LA = m.add_line(m.point(0, 0), m.point(10, 0.3))
    LB = m.add_line(m.point(9.6, 6), m.point(10.1, 0.1))
    cv._sel = [LA, LB]
    QTest.keyClick(cv, Qt.Key_T)
    qapp.processEvents()
    assert len(m.sketch.points) == 3
    cv.undo_op()
    qapp.processEvents()
    assert len(m.sketch.points) == 4
    l0, l1 = m.sketch.lines
    assert not any(pa is pb for pa in (l0.a, l0.b) for pb in (l1.a, l1.b))
    near = [p for e in (l0, l1) for p in (e.a, e.b)
            if math.dist((p.x, p.y), (10, 0.3)) < 0.35]
    assert near                                   # original tip back


def test_slash_refusal_warns_and_changes_nothing(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    p1 = m.add_line(m.point(0, 0), m.point(10, 0))
    p2 = m.add_line(m.point(0, 5), m.point(10, 5))
    cv._sel = [p1, p2]
    QTest.keyClick(cv, Qt.Key_T)
    qapp.processEvents()
    assert "parallel" in (getattr(cv, "_warn_text", "") or "")
    assert len(m.sketch.points) == 4                # untouched


def test_slash_without_a_line_pair_is_left_alone(win, qapp):
    """'/' must not be swallowed unless exactly two lines are picked."""
    cv = _canvas(win, qapp)
    m = cv.model
    L = m.add_line(m.point(0, 0), m.point(10, 0))
    c = m.add_circle(m.point(5, 5), 2.0)
    cv._sel = [L]
    QTest.keyClick(cv, Qt.Key_T)
    cv._sel = [L, c]
    QTest.keyClick(cv, Qt.Key_T)
    qapp.processEvents()
    assert len(m.sketch.points) == 3                # nothing merged


def test_corner_menu_routes_trim_vs_fillet_by_topology(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    lines = m.add_rect(m.point(0, 0), m.point(30, 30))
    cv._sel = [lines[0], lines[1]]                  # shared corner
    texts = [a.text() for a in cv._build_menu().actions()]
    assert "Fillet corner…" in texts
    assert "Trim / extend to corner" not in texts
    loose = m.add_line(m.point(40, 40), m.point(60, 40.4))
    far = m.add_line(m.point(59, 30), m.point(61, 55))
    cv._sel = [loose, far]                          # near-crossing, unshared
    texts = [a.text() for a in cv._build_menu().actions()]
    assert "Trim / extend to corner" in texts
    assert "Fillet corner…" not in texts
