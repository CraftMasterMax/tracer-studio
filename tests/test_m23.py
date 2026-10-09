"""M23 — tangent constraints: line↔circle/arc and curve↔curve.

The solver contract: contact is achieved (signed distance == r, or
centre distance == r1±r2), the branch chosen at creation (side of the
line, external vs internal) never flips, the toggle/UI/serialization
paths round-trip, and degenerate pairs are refused instead of solving
junk.
"""
import math

import numpy as np
import pytest

from tracer.core.sketch.solver import Sketch
from tracer.core.sketch.constraints import (Fixed, Radius, Tangent,
                                            make_tangent, _unit_normal)
from tracer.core.sketch.entities import Circle, Line, curve_center, curve_radius
from tracer.core.sketch.model import (SketchModel, model_from_dict,
                                      model_to_dict)


def _sd(t: Tangent) -> float:
    """Signed distance from the line's normal side to the curve centre."""
    n = _unit_normal(t.e1)
    cx, cy = curve_center(t.e2)
    return n[0] * (cx - t.e1.a.x) + n[1] * (cy - t.e1.a.y)


# ---- kernel -------------------------------------------------------------

def test_line_circle_tangent_pulls_centre_to_radius():
    s = Sketch()
    a = s.point(0, 0); b = s.point(10, 0); ln = s.line(a, b)
    cen = s.point(5, 6); cir = s.circle(cen, 2.0)
    t = make_tangent(ln, cir)
    s.constrain(Fixed(a, x=0, y=0), Fixed(b, x=10, y=0), Radius(cir, 2.0), t)
    res = s.solve()
    assert res.converged and t.side > 0
    assert abs(_sd(t) - cir.r) < 1e-6
    assert abs(cen.y - 2.0) < 1e-6


def test_tangent_side_frozen_circle_below_stays_below():
    s = Sketch()
    a = s.point(0, 0); b = s.point(10, 0); ln = s.line(a, b)
    cen = s.point(5, -6); cir = s.circle(cen, 2.0)
    t = make_tangent(ln, cir)
    s.constrain(Fixed(a, x=0, y=0), Fixed(b, x=10, y=0), Radius(cir, 2.0), t)
    res = s.solve()
    assert res.converged and t.side < 0
    assert cen.y < 0 and abs(cen.y + 2.0) < 1e-6


def test_circle_circle_external():
    s = Sketch()
    c1 = s.circle(s.point(0, 0), 5.0); c2 = s.circle(s.point(12, 4), 3.0)
    t = make_tangent(c1, c2)
    s.constrain(Fixed(c1.c, x=0, y=0), Radius(c1, 5.0), Radius(c2, 3.0), t)
    res = s.solve()
    assert res.converged and not t.internal
    assert abs(math.hypot(c2.c.x, c2.c.y) - 8.0) < 1e-6


def test_circle_circle_internal_branch():
    s = Sketch()
    c1 = s.circle(s.point(0, 0), 10.0); c2 = s.circle(s.point(2, 1), 3.0)
    t = make_tangent(c1, c2)
    s.constrain(Fixed(c1.c, x=0, y=0), Radius(c1, 10.0), Radius(c2, 3.0), t)
    res = s.solve()
    assert res.converged and t.internal
    assert abs(math.hypot(c2.c.x, c2.c.y) - 7.0) < 1e-6


def test_line_arc_tangent_moves_bulge():
    """Arc radius is not a DOF — the constraint differentiates through the
    three shared points (same machinery Radius relies on)."""
    s = Sketch()
    a = s.point(-2, 10); b = s.point(12, 10); ln = s.line(a, b)
    p1 = s.point(0, 0); pm = s.point(5, -5); p2 = s.point(10, 0)
    ar = s.arc(p1, pm, p2)
    t = make_tangent(ln, ar)
    s.constrain(Fixed(a, x=-2, y=10), Fixed(b, x=12, y=10),
                Fixed(p1, x=0, y=0), Fixed(p2, x=10, y=0), t)
    res = s.solve()
    assert res.converged
    cx, cy = curve_center(ar)
    assert abs((10.0 - cy) - curve_radius(ar)) < 1e-6


def test_round_tip_slot_two_lines_two_circles():
    """The maker classic: lines must settle to y=±r around fixed circles."""
    s = Sketch()
    k1 = s.circle(s.point(0, 0), 4.0); k2 = s.circle(s.point(10, 0), 4.0)
    L1 = s.line(s.point(-2, 5), s.point(12, 5))
    L2 = s.line(s.point(-2, -5), s.point(12, -5))
    s.constrain(Radius(k1, 4.0), Radius(k2, 4.0),
                Fixed(k1.c, x=0, y=0), Fixed(k2.c, x=10, y=0),
                make_tangent(L1, k1), make_tangent(L1, k2),
                make_tangent(L2, k1), make_tangent(L2, k2))
    res = s.solve()
    assert res.converged
    for L, want in ((L1, 4.0), (L2, -4.0)):
        assert abs(L.a.y - want) < 1e-4 and abs(L.b.y - want) < 1e-4


def test_make_tangent_rejects_non_entities():
    s = Sketch()
    a = s.point(0, 0); b = s.point(1, 1)
    with pytest.raises(ValueError):
        make_tangent(a, b)                       # two points
    ln = s.line(a, b)
    with pytest.raises(ValueError):
        make_tangent(ln, s.point(5, 5))          # line + loose point


def test_drag_radius_follows_line_distance():
    """Dragging a tangent circle's centre away makes its radius follow."""
    m = SketchModel()
    a = m.point(0, 0); b = m.point(10, 0); ln = m.add_line(a, b)
    cen = m.point(5, 6); cir = m.add_circle(cen, 2.0)
    m.constrain(Fixed(a, x=0, y=0), Fixed(b, x=10, y=0),
                make_tangent(ln, cir))
    assert m.solve().converged
    cen.x, cen.y = 8.0, 7.0                      # user drags centre up
    assert m.solve(pins=[cen]).converged
    assert cir.r == pytest.approx(7.0, abs=1e-6)
    assert cen.x == pytest.approx(8.0, abs=1e-6)       # stays under the cursor
    assert cen.y == pytest.approx(7.0, abs=1e-6)


def test_drag_line_pivot_rolls_circle_along():
    """Lifting a pivot line's free end slides the tangent circle to keep
    contact instead of breaking the constraint."""
    m = SketchModel()
    a = m.point(0, 0); b = m.point(10, 0); ln = m.add_line(a, b)
    cen = m.point(5, 2.0); cir = m.add_circle(cen, 2.0)
    m.constrain(Fixed(a, x=0, y=0), Radius(cir, 2.0), make_tangent(ln, cir))
    assert m.solve().converged
    b.x, b.y = 10.0, 6.0
    assert m.solve(pins=[b]).converged
    n = _unit_normal(ln)
    cx, cy = curve_center(cir)
    assert abs(abs(n[0] * (cx - ln.a.x) + n[1] * (cy - ln.a.y)) - 2.0) < 1e-6


# ---- model: toggle + serialization ---------------------------------------

def _slot_model():
    m = SketchModel()
    a = m.point(0, 0); b = m.point(10, 0)
    ln = m.add_line(a, b)
    cir = m.add_circle(m.point(5, 6), 2.0)
    m.constrain(Fixed(a, x=0, y=0), Fixed(b, x=10, y=0), Radius(cir, 2.0))
    return m, ln, cir


def test_toggle_adds_then_removes():
    m, ln, cir = _slot_model()
    assert m.toggle(Tangent, (ln, cir)) is True
    assert m.has(Tangent, (ln, cir))
    assert m.toggle(Tangent, (cir, ln)) is False   # order-independent
    assert not m.has(Tangent, (ln, cir))


def test_tangent_survives_save_roundtrip_with_branch():
    m, ln, cir = _slot_model()
    m.constrain(make_tangent(ln, cir))
    # arc tangent too, so both ref kinds serialize
    p1 = m.point(20, 0); p2 = m.point(30, 0); p3 = m.point(25, -5)
    ar = m.sketch.arc(p1, p2, p3)
    ln2 = m.add_line(m.point(20, 8), m.point(30, 8))
    m.constrain(make_tangent(ln2, ar))
    d = model_to_dict(m)
    m2 = model_from_dict(d)
    tans = [c for c in m2.sketch.constraints if isinstance(c, Tangent)]
    assert len(tans) == 2
    assert tans[0].side > 0 and not tans[0].internal
    assert isinstance(tans[1].e2, type(ar))        # arc ref restored
    res = m2.solve()
    assert res.converged
    assert abs(tans[0].e2.c.y - 2.0) < 1e-6


# ---- UI --------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                   # noqa: E402
from PySide6.QtGui import QKeyEvent                             # noqa: E402
from PySide6.QtTest import QTest                                # noqa: E402
from PySide6.QtWidgets import QApplication                      # noqa: E402

from tracer.ui.mainwindow import MainWindow                     # noqa: E402
from tracer.ui.renderer import SceneRenderer                    # noqa: E402
from tracer.ui.sketcheditor import SketchCanvas                 # noqa: E402


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
    r.close()


def _sketch_canvas(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    return win.sketch


def test_key_T_toggles_tangent_on_canvas(win, qapp):
    cv = _sketch_canvas(win, qapp)
    m = cv.model
    a = m.point(0, 0); b = m.point(10, 0)
    ln = m.add_line(a, b)
    cir = m.add_circle(m.point(5, 6), 2.0)
    m.constrain(Fixed(a, x=0, y=0), Fixed(b, x=10, y=0), Radius(cir, 2.0))
    cv._sel = [ln, cir]
    QTest.keyClick(cv, Qt.Key_T, Qt.ShiftModifier)
    qapp.processEvents()
    tans = [c for c in m.sketch.constraints if isinstance(c, Tangent)]
    assert len(tans) == 1
    assert abs(cir.c.y - 2.0) < 1e-6               # solved on the spot
    # same key again removes it (toggle)
    QTest.keyClick(cv, Qt.Key_T, Qt.ShiftModifier)
    qapp.processEvents()
    assert not [c for c in m.sketch.constraints if isinstance(c, Tangent)]


def test_line_line_selection_is_ignored(win, qapp):
    cv = _sketch_canvas(win, qapp)
    m = cv.model
    l1 = m.add_line(m.point(0, 0), m.point(10, 0))
    l2 = m.add_line(m.point(0, 5), m.point(10, 5))
    cv._sel = [l1, l2]
    QTest.keyClick(cv, Qt.Key_T, Qt.ShiftModifier)
    qapp.processEvents()
    assert not [c for c in m.sketch.constraints if isinstance(c, Tangent)]


def test_tangent_point_and_paint_path(win, qapp):
    """The contact marker must land on the curve (within a pixel) and the
    full paint path must run without errors."""
    cv = _sketch_canvas(win, qapp)
    m = cv.model
    a = m.point(0, 0); b = m.point(10, 0)
    ln = m.add_line(a, b)
    cir = m.add_circle(m.point(5, 2.0), 2.0)       # already tangent
    t = make_tangent(ln, cir)
    scr = cv._tangent_point(t)
    cen = cv.w2s(cir.c.x, cir.c.y)
    scale = cv._scale
    assert abs(scr.x() - cen.x()) < 1e-6            # directly above centre
    assert abs(scr.y() - (cen.y() + 2.0 * scale)) < 1e-3   # r down on screen
    m.constrain(t)
    cv.update(); qapp.processEvents()
    win.grab()                                      # paints _tangent_mark
    qapp.processEvents()


def test_context_menu_offers_tangent_only_for_valid_pairs(win, qapp):
    cv = _sketch_canvas(win, qapp)
    m = cv.model
    ln = m.add_line(m.point(0, 0), m.point(9, 0))
    cir = m.add_circle(m.point(4, 4), 2.0)
    ar = m.sketch.arc(m.point(20, 0), m.point(25, 5), m.point(30, 0))
    pt = m.point(1, 1)
    assert SketchCanvas.tangent_ok((ln, cir))
    assert SketchCanvas.tangent_ok((cir, ln))       # order irrelevant
    assert SketchCanvas.tangent_ok((cir, ar))
    assert not SketchCanvas.tangent_ok((ln, m.add_line(m.point(0, 2), m.point(9, 2))))
    assert not SketchCanvas.tangent_ok((ln, pt))
    assert not SketchCanvas.tangent_ok((cir,))
