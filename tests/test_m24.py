"""M24a — angular dimensions: angle of a line, angle between two lines.

Contract: the solver nails the requested branch (and never flips a line
180° on creation or edit), the badge is editable and serialized, and the
arc/label geometry tracks the live sketch.
"""
import math

import pytest

from tracer.core.sketch.constraints import (Angle, AngleBetween, Distance,
                                            Fixed, make_angle,
                                            make_angle_between, snapped)
from tracer.ui.cmddialog import Shell                    # noqa: E402
from tracer.core.sketch.model import (SketchModel, model_from_dict,
                                      model_to_dict)
from tracer.core.sketch.solver import Sketch


def _deg(v_rad: float) -> float:
    return math.degrees(v_rad) % 180


# ---- kernel ---------------------------------------------------------------

def test_angle_rotates_free_line():
    s = Sketch()
    a = s.point(0, 0)
    b = s.point(10 * math.cos(math.radians(5)), 10 * math.sin(math.radians(5)))
    ln = s.line(a, b)
    t = make_angle(ln, 40)
    s.constrain(Fixed(a, x=0, y=0), Distance(a, b, 10.0), t)
    res = s.solve()
    assert res.converged
    assert _deg(math.atan2(b.y - a.y, b.x - a.x)) == pytest.approx(40, abs=1e-6)


def test_angle_snaps_to_current_branch_no_flip():
    """A segment at 200° is already '20°' — constraining 20 must be a
    no-op, not a 180° teleport."""
    s = Sketch()
    a = s.point(0, 0)
    th = math.radians(200)
    b = s.point(10 * math.cos(th), 10 * math.sin(th))
    ln = s.line(a, b)
    t = make_angle(ln, 20)
    assert _deg(t.value) == pytest.approx(20)          # display 20°
    s.constrain(Fixed(a, x=0, y=0), Distance(a, b, 10.0), t)
    res = s.solve()
    assert res.converged and res.residual_norm < 1e-12
    assert math.degrees(math.atan2(b.y - a.y, b.x - a.x)) % 360 \
        == pytest.approx(200, abs=1e-6)                # nothing moved


def test_angle_between_two_lines_sharing_vertex():
    s = Sketch()
    o = s.point(0, 0); e1 = s.point(10, 0); e2 = s.point(3, 9)
    L1 = s.line(o, e1); L2 = s.line(o, e2)
    s.constrain(Fixed(o, x=0, y=0), Fixed(e1, x=10, y=0),
                Distance(o, e2, 10.0), make_angle_between(L1, L2, 45))
    res = s.solve()
    assert res.converged
    a1 = math.atan2(e1.y - o.y, e1.x - o.x)
    a2 = math.atan2(e2.y - o.y, e2.x - o.x)
    assert _deg(a2 - a1) == pytest.approx(45, abs=1e-6)


def test_snapped_helper():
    assert snapped(math.radians(200), math.radians(20)) == pytest.approx(
        math.radians(200))
    assert snapped(math.radians(10), math.radians(20)) == pytest.approx(
        math.radians(20))


def test_no_stall_at_90_degrees():
    """Regression: a sin-form residual has zero gradient exactly 90° from
    the target, so a horizontal→vertical angle edit stalled. The wrapped
    signed-angle error keeps gradient 1 and rotates through."""
    s = Sketch()
    a = s.point(0, 0); b = s.point(8, 0)
    ln = s.line(a, b)
    t = Angle(ln, math.pi / 2)
    s.constrain(Fixed(a, x=0, y=0), Distance(a, b, 8.0), t)
    res = s.solve()
    assert res.converged, f"stalled: residual {t.residual({})}"
    assert math.degrees(math.atan2(b.y - a.y, b.x - a.x)) == pytest.approx(
        90, abs=1e-6)


def test_degenerate_line_never_crashes():
    s = Sketch()
    a = s.point(2, 2); b = s.point(2, 2)
    ln = s.line(a, b)
    t = make_angle(ln, 30)
    s.constrain(Fixed(a, x=2, y=2), Fixed(b, x=2, y=2), t)
    res = s.solve()                       # zero-length: measured()==0
    assert t.residual({}) == pytest.approx(math.radians(-30))


# ---- save/load -------------------------------------------------------------

def test_angles_survive_roundtrip():
    m = SketchModel()
    th = math.radians(12.5)
    p1 = m.point(0, 0)
    p2 = m.point(9 * math.cos(th), 9 * math.sin(th))       # already at 12.5°
    ln = m.add_line(p1, p2)
    p3 = m.point(9, 8)                                     # free end
    ln2 = m.add_line(p2, p3)
    m.constrain(Fixed(p1, x=0, y=0), Fixed(p2, x=p2.x, y=p2.y),
                make_angle(ln, 12.5), make_angle_between(ln, ln2, 70))
    assert m.solve().converged
    d = model_to_dict(m)
    m2 = model_from_dict(d)
    asb = [c for c in m2.sketch.constraints if isinstance(c, Angle)]
    bbs = [c for c in m2.sketch.constraints if isinstance(c, AngleBetween)]
    assert len(asb) == 1 and len(bbs) == 1
    assert abs(asb[0].value - math.radians(12.5)) < 1e-9
    assert _deg(bbs[0].value) == pytest.approx(70, abs=1e-9)
    res = m2.solve()
    assert res.converged


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QInputDialog        # noqa: E402
from PySide6.QtTest import QTest                                # noqa: E402
from PySide6.QtCore import Qt                                   # noqa: E402

from tracer.ui.mainwindow import MainWindow                     # noqa: E402
from tracer.ui.renderer import SceneRenderer                    # noqa: E402
from tracer.ui.sketcheditor import _line_pivot                  # noqa: E402


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


def test_key_I_angles_a_line_and_edits_it(win, qapp, monkeypatch):
    cv = _canvas(win, qapp)
    m = cv.model
    a = m.point(0, 0)
    b = m.point(10 * math.cos(math.radians(5)), 10 * math.sin(math.radians(5)))
    ln = m.add_line(a, b)
    m.constrain(Fixed(a, x=0, y=0), Distance(a, b, 10.0))
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *A, **K: (40.0, True)))
    cv._sel = [ln]
    QTest.keyClick(cv, Qt.Key_I)
    qapp.processEvents()
    angs = [c for c in m.sketch.constraints if isinstance(c, Angle)]
    assert len(angs) == 1
    assert _deg(math.atan2(b.y - a.y, b.x - a.x)) == pytest.approx(40, abs=1e-6)
    # re-run with a different value: replaces, never stacks
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *A, **K: (55.0, True)))
    QTest.keyClick(cv, Qt.Key_I)
    qapp.processEvents()
    angs = [c for c in m.sketch.constraints if isinstance(c, Angle)]
    assert len(angs) == 1
    assert _deg(math.atan2(b.y - a.y, b.x - a.x)) == pytest.approx(55, abs=1e-6)


def test_angle_badge_is_editable_via_doubleclick_path(win, qapp, monkeypatch):
    cv = _canvas(win, qapp)
    m = cv.model
    a = m.point(0, 0); b = m.point(8, 0)
    ln = m.add_line(a, b)
    m.constrain(Fixed(a, x=0, y=0), Distance(a, b, 8.0), make_angle(ln, 90))
    assert m.solve().converged             # wraps to exactly vertical now
    qapp.processEvents()
    win.grab(); qapp.processEvents()          # paints dims -> fills _dim_hits
    angs = [c for c in m.sketch.constraints if isinstance(c, Angle)]
    assert len(angs) == 1
    badge = [cc for (_r, cc) in cv._dim_hits if isinstance(cc, Angle)]
    assert len(badge) == 1                     # label rendered & hittable
    assert b.x == pytest.approx(0, abs=1e-4)   # solved up to vertical
    assert b.y == pytest.approx(8, abs=1e-4)
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *A, **K: (30.0, True)))
    cv._edit_dim(angs[0])                      # the double-click target
    qapp.processEvents()
    assert _deg(angs[0].value) == pytest.approx(30, abs=1e-9)
    ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x)) % 180
    assert ang == pytest.approx(30, abs=1e-4)


def test_angle_edit_resnaps_and_does_not_flip(win, qapp, monkeypatch):
    """Line sits at 200° (displays 20°); editing 20 -> 25 must rotate the
    short way from where it is, ending still in the 200° branch."""
    cv = _canvas(win, qapp)
    m = cv.model
    a = m.point(0, 0)
    th = math.radians(200)
    b = m.point(10 * math.cos(th), 10 * math.sin(th))
    ln = m.add_line(a, b)
    m.constrain(Fixed(a, x=0, y=0), Distance(a, b, 10.0), make_angle(ln, 20))
    m.solve()
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *A, **K: (25.0, True)))
    angs = [c for c in m.sketch.constraints if isinstance(c, Angle)]
    cv._edit_dim(angs[0])
    qapp.processEvents()
    end = math.degrees(math.atan2(b.y - a.y, b.x - a.x)) % 360
    assert end == pytest.approx(205, abs=1e-4)     # 200 + 5, never 25
    assert _deg(angs[0].value) == pytest.approx(25)


def test_two_lines_angle_between_via_menu_action(win, qapp, monkeypatch):
    cv = _canvas(win, qapp)
    m = cv.model
    o = m.point(0, 0); e1 = m.point(10, 0); e2 = m.point(0, 10)
    L1 = m.add_line(o, e1); L2 = m.add_line(o, e2)
    m.constrain(Fixed(o, x=0, y=0), Fixed(e1, x=10, y=0))
    # rotate L2 to 30° while keeping its length
    e2.x, e2.y = 10 * math.cos(math.radians(120)), 10 * math.sin(math.radians(120))
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *A, **K: (45.0, True)))
    cv._sel = [L1, L2]
    cv.act_angle()
    qapp.processEvents()
    assert _deg(math.atan2(e2.y, e2.x)) == pytest.approx(45, abs=1e-6)


def test_line_pivot_shared_endpoint_and_parallel():
    m = SketchModel()
    p0 = m.point(0, 0); p1 = m.point(5, 0); p2 = m.point(0, 5)
    L1 = m.add_line(p0, p1); L2 = m.add_line(p0, p2)
    assert _line_pivot(L1, L2) == (0.0, 0.0)
    L3 = m.add_line(m.point(0, 2), m.point(5, 2))      # parallel to L1
    assert _line_pivot(L1, L3) is None
    L4 = m.add_line(m.point(2, -5), m.point(2, 5))     # crosses L1 at (2,0)
    x, y = _line_pivot(L1, L4)
    assert abs(x - 2) < 1e-9 and abs(y) < 1e-9


def test_angle_arc_and_label_paint_cleanly(win, qapp):
    """Full paint path for Angle + AngleBetween badges (arc polyline,
    label, edit hit rects) must run without exceptions."""
    cv = _canvas(win, qapp)
    m = cv.model
    o = m.point(0, 0); e1 = m.point(10, 0); e2 = m.point(4, 8)
    L1 = m.add_line(o, e1); L2 = m.add_line(o, e2)
    m.constrain(Fixed(o, x=0, y=0), Fixed(e1, x=10, y=0),
                make_angle(L1, 10), make_angle_between(L1, L2, 60))
    qapp.processEvents()
    w = cv._angle_arc_pts([c for c in m.sketch.constraints
                           if isinstance(c, AngleBetween)][0])
    assert w is not None
    pts, label = w
    assert len(pts) >= 8
    win.grab()
    qapp.processEvents()
    kinds = {type(c).__name__ for _r, c in cv._dim_hits}
    assert {"Angle", "AngleBetween"} <= kinds


def test_stacked_angle_labels_are_staggered(win, qapp):
    """Two angle dims sharing the vertex must not print one badge over the
    other (a '40°' arc stacked on a '0°' arc) — rings separate the radii,
    so the label rects stay disjoint."""
    cv = _canvas(win, qapp)
    m = cv.model
    o = m.point(0, 0); e1 = m.point(70, 0); tip = m.point(40, 38)
    base = m.add_line(o, e1); arm = m.add_line(o, tip)
    m.constrain(Fixed(o, x=0, y=0), Fixed(e1, x=70, y=0),
                make_angle(base, 0.0), make_angle_between(base, arm, 40.0))
    m.solve()
    qapp.processEvents()
    win.grab(); qapp.processEvents()
    badges = [r for (r, c) in cv._dim_hits if isinstance(c, (Angle, AngleBetween))]
    assert len(badges) == 2
    a, b = badges
    assert not a.intersects(b), f"angle labels collide: {a} vs {b}"
