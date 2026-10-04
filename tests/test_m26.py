"""M26 — Equal on curves and Concentric.

Equal gained a radius branch (two circles/arcs) beside its length branch,
and Concentric makes pairs of curves share the (derived) centre — the
bolt-circle pattern primitive. Both toggle order-independently, solve
through the numerical Jacobian, and round-trip through save/load.
"""
import math

import pytest

from tracer.core.sketch.constraints import (Concentric, Equal, Fixed, Radius)
from tracer.core.sketch.entities import curve_center, curve_radius
from tracer.core.sketch.model import (SketchModel, model_from_dict,
                                      model_to_dict)


# ---- kernel -----------------------------------------------------------------

def test_equal_circles_matches_radius():
    m = SketchModel()
    c1 = m.add_circle(m.point(0, 0), 7.0)
    c2 = m.add_circle(m.point(20, 0), 2.0)
    m.constrain(Radius(c1, 7.0), Fixed(c1.c, x=0, y=0))
    assert m.toggle(Equal, (c1, c2)) is True
    res = m.solve()
    assert res.converged and abs(c2.r - 7.0) < 1e-6
    assert m.toggle(Equal, (c2, c1)) is False      # order-independent remove
    assert not m.has(Equal, (c1, c2))


def test_equal_arcs_matches_circumradii():
    m = SketchModel()
    a1 = m.sketch.arc(m.point(0, 0), m.point(5, -5), m.point(10, 0))
    a2 = m.sketch.arc(m.point(20, 0), m.point(25, -3), m.point(30, 0))
    m.constrain(Fixed(a1.a, x=0, y=0), Fixed(a1.b, x=10, y=0),
                Fixed(a2.a, x=20, y=0), Fixed(a2.b, x=30, y=0),
                Radius(a1, 6.5), Equal(a1, a2))
    assert m.solve().converged
    assert abs(curve_radius(a2) - 6.5) < 1e-3


def test_concentric_circles():
    m = SketchModel()
    d1 = m.add_circle(m.point(0, 0), 5.0)
    d2 = m.add_circle(m.point(10, 6), 3.0)
    m.constrain(Fixed(d1.c, x=0, y=0), Radius(d1, 5.0), Radius(d2, 3.0),
                Concentric(d1, d2))
    res = m.solve()
    assert res.converged
    assert abs(d2.c.x) < 1e-6 and abs(d2.c.y) < 1e-6


def test_concentric_arc_onto_circle():
    """An arc has no centre point — the two rows differentiate through the
    three shared defining points and land the circumcentre on the ring."""
    m = SketchModel()
    ring = m.add_circle(m.point(0, 0), 8.0)
    p1 = m.point(8, 0)
    pm = m.point(3, 3)
    p2 = m.point(0, 8)
    ar = m.sketch.arc(p1, pm, p2)
    m.constrain(Fixed(ring.c, x=0, y=0), Radius(ring, 8.0),
                Fixed(p1, x=8, y=0), Fixed(p2, x=0, y=8),
                Concentric(ring, ar))
    assert m.solve().converged
    cx, cy = curve_center(ar)
    assert abs(cx) < 1e-4 and abs(cy) < 1e-4
    assert curve_radius(ar) == pytest.approx(8.0, abs=1e-4)


def test_concentric_toggle_roundtrip_and_removal():
    m = SketchModel()
    c1 = m.add_circle(m.point(0, 0), 4.0)
    c2 = m.add_circle(m.point(6, 0), 2.0)
    m.constrain(Fixed(c1.c, x=0, y=0))
    assert m.toggle(Concentric, (c1, c2)) is True
    assert m.has(Concentric, (c2, c1)) is True      # symmetric by ids
    d = model_to_dict(m)
    assert any(c["t"] == "cc" for c in d["constraints"])
    m2 = model_from_dict(d)
    cc = [c for c in m2.sketch.constraints if isinstance(c, Concentric)]
    assert len(cc) == 1 and cc[0].axis == 0         # stored as ONE row
    m2.solve()
    assert math.hypot(curve_center(cc[0].c2)[0],
                      curve_center(cc[0].c2)[1]) < 1e-6
    assert m.toggle(Concentric, (c1, c2)) is False
    assert not m.has(Concentric, (c1, c2))


def test_equal_and_concentric_serialize_with_refs():
    """A bolt arc on a pilot ring: both refs-based constraints must
    survive save/load and still solve (endpoints seeded on r=5)."""
    m = SketchModel()
    c1 = m.add_circle(m.point(0, 0), 5.0)
    p1 = m.point(4, 3)                               # |p| = 5 already
    p2 = m.point(-4, 3)
    ar = m.sketch.arc(p1, m.point(0, -3), p2)        # wrong centre to start
    m.constrain(Fixed(c1.c, x=0, y=0), Radius(c1, 5.0),
                Fixed(p1, x=4, y=3), Fixed(p2, x=-4, y=3),
                Equal(c1, ar), Concentric(c1, ar))
    assert m.solve().converged
    assert curve_radius(ar) == pytest.approx(5.0, abs=1e-6)
    assert max(abs(v) for v in curve_center(ar)) < 1e-6
    d = model_to_dict(m)
    m2 = model_from_dict(d)
    eq = [c for c in m2.sketch.constraints if isinstance(c, Equal)]
    cc = [c for c in m2.sketch.constraints if isinstance(c, Concentric)]
    assert len(eq) == 1 and len(cc) == 1
    assert eq[0].l1 is m2.sketch.circles[0] and eq[0].l2 is m2.sketch.arcs[0]
    assert m2.solve().converged


# ---- UI ----------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                      # noqa: E402
from PySide6.QtTest import QTest                               # noqa: E402
from PySide6.QtCore import Qt                                  # noqa: E402

from tracer.ui.mainwindow import MainWindow                    # noqa: E402
from tracer.ui.renderer import SceneRenderer                   # noqa: E402


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


def test_Q_key_equalizes_two_circles_on_canvas(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    c1 = m.add_circle(m.point(0, 0), 6.0)
    c2 = m.add_circle(m.point(18, 0), 2.0)
    m.constrain(Radius(c1, 6.0), Fixed(c1.c, x=0, y=0))
    cv._sel = [c1, c2]
    QTest.keyClick(cv, Qt.Key_Q)
    qapp.processEvents()
    eqs = [c for c in m.sketch.constraints if isinstance(c, Equal)]
    assert len(eqs) == 1
    assert abs(c2.r - 6.0) < 1e-6
    QTest.keyClick(cv, Qt.Key_Q)                     # toggles off again
    qapp.processEvents()
    assert not [c for c in m.sketch.constraints if isinstance(c, Equal)]


def test_mixed_line_circle_pair_refuses_equal(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    ln = m.add_line(m.point(0, 0), m.point(10, 0))
    cir = m.add_circle(m.point(5, 8), 3.0)
    cv._sel = [ln, cir]
    before = len(m.sketch.constraints)
    cv.act_equal()
    qapp.processEvents()
    assert len(m.sketch.constraints) == before       # refused silently


def test_two_key_concentric_on_canvas(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    d1 = m.add_circle(m.point(0, 0), 5.0)
    d2 = m.add_circle(m.point(9, 4), 2.0)
    m.constrain(Fixed(d1.c, x=0, y=0), Radius(d1, 5.0), Radius(d2, 2.0))
    cv._sel = [d1, d2]
    QTest.keyClick(cv, Qt.Key_2)
    qapp.processEvents()
    assert any(isinstance(c, Concentric) for c in m.sketch.constraints)
    assert math.hypot(d2.c.x, d2.c.y) < 1e-6
    QTest.keyClick(cv, Qt.Key_2)                     # toggle off
    qapp.processEvents()
    assert not any(isinstance(c, Concentric) for c in m.sketch.constraints)


def test_two_key_passes_through_without_two_curves(win, qapp):
    """'2' is a 3D view key outside the sketcher — the canvas must not
    swallow it unless the selection is two curves."""
    cv = _canvas(win, qapp)
    m = cv.model
    ln = m.add_line(m.point(0, 0), m.point(9, 0))
    cv._sel = [ln]
    QTest.keyClick(cv, Qt.Key_2)
    qapp.processEvents()
    assert not any(isinstance(c, Concentric) for c in m.sketch.constraints)


def test_curve_pair_menu_offers_all_three(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    c1 = m.add_circle(m.point(0, 0), 4.0)
    c2 = m.add_circle(m.point(8, 0), 6.0)
    ln = m.add_line(m.point(0, 0), m.point(9, 0))
    texts = lambda: [a.text() for a in cv._build_menu().actions()]
    cv._sel = [c1, c2]
    menu = texts()
    assert "Tangent" in menu and "Equal radius" in menu and "Concentric" in menu
    cv._sel = [ln, c1]
    menu = texts()
    assert "Tangent" in menu and "Concentric" not in menu
    cv._sel = []
    menu = texts()                                   # empty pick → tool list
    assert "Slot tool" in menu and "Tangent" not in menu
