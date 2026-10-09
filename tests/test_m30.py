"""M30 — the On-curve constraint, reachable at last.

PointOnLine lived in the kernel and serializer since the early sketcher
milestones but no UI path could ever CREATE one; PointOnCircle arrived
with polygons (M29) sharing that invisibility. '.' plus a
point + curve pick exposes both, arc and circle centres included.
"""
import math

import pytest

from tracer.core.sketch.constraints import (Fixed, PointOnCircle,
                                            PointOnLine, Radius)
from tracer.core.sketch.model import (SketchModel, model_from_dict,
                                      model_to_dict)


# ---- kernel -----------------------------------------------------------------

def test_point_on_line_toggle_and_projection():
    m = SketchModel()
    L = m.add_line(m.point(0, 0), m.point(10, 0))
    m.constrain(Fixed(L.a, x=0, y=0), Fixed(L.b, x=10, y=0))
    p = m.point(4, 3)
    assert m.toggle(PointOnLine, (p, L)) is True
    assert m.solve().converged
    assert p.y == pytest.approx(0.0, abs=1e-6)
    assert p.x == pytest.approx(4.0, abs=1e-4)      # slides freely along:
    assert m.toggle(PointOnLine, (p, L)) is False   # FD noise floor governs


def test_point_on_circle_slides_along_the_ring():
    m = SketchModel()
    c = m.add_circle(m.point(0, 0), 5.0)
    m.constrain(Fixed(c.c, x=0, y=0), Radius(c, 5.0))
    p = m.point(2, 2)
    assert m.toggle(PointOnCircle, (p, c)) is True
    assert m.solve().converged
    assert math.hypot(p.x, p.y) == pytest.approx(5.0, abs=1e-6)
    ang = math.atan2(p.y, p.x) + 1.0                # drag ON the ring
    p.x, p.y = 5 * math.cos(ang), 5 * math.sin(ang)
    assert m.solve(pins=[p]).converged
    assert math.hypot(p.x, p.y) == pytest.approx(5.0, abs=1e-6)
    assert m.toggle(PointOnCircle, (p, c)) is False


def test_both_forms_roundtrip_through_saves():
    m = SketchModel()
    L = m.add_line(m.point(0, 0), m.point(10, 0))
    c = m.add_circle(m.point(5, 8), 3.0)
    p1 = m.point(3, 4)
    p2 = m.point(6, 9)
    m.constrain(Fixed(L.a, x=0, y=0), Fixed(L.b, x=10, y=0),
                Fixed(c.c, x=5, y=8), Radius(c, 3.0),
                PointOnLine(p1, L), PointOnCircle(p2, c))
    d = model_to_dict(m)
    tags = {c_["t"] for c_ in d["constraints"]}
    assert {"on", "oc"} <= tags
    m2 = model_from_dict(d)
    kinds = [type(c).__name__ for c in m2.sketch.constraints]
    assert kinds.count("PointOnLine") == 1
    assert kinds.count("PointOnCircle") == 1
    m2.solve()
    p1b, p2b = m2.sketch.points[-2], m2.sketch.points[-1]
    assert abs(p1b.y) < 1e-5                        # still on the line
    assert math.hypot(p2b.x - 5, p2b.y - 8) == pytest.approx(3.0, abs=1e-5)


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                      # noqa: E402
from PySide6.QtTest import QTest                                # noqa: E402
from PySide6.QtCore import Qt                                   # noqa: E402

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


def _canvas(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    return win.sketch


def test_period_key_glues_point_to_line_and_back_out(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    L = m.add_line(m.point(0, 0), m.point(10, 0))
    m.constrain(Fixed(L.a, x=0, y=0), Fixed(L.b, x=10, y=0))
    p = m.point(4, 3)
    cv._sel = [p, L]
    QTest.keyClick(cv, Qt.Key_Period)
    qapp.processEvents()
    assert any(isinstance(c, PointOnLine) for c in m.sketch.constraints)
    assert p.y == pytest.approx(0.0, abs=1e-6)
    QTest.keyClick(cv, Qt.Key_Period)               # same pick, removed
    qapp.processEvents()
    assert not any(isinstance(c, PointOnLine) for c in m.sketch.constraints)


def test_line_first_pick_order_still_adds_correctly(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    L = m.add_line(m.point(0, 0), m.point(0, 10))
    p = m.point(3, 5)
    cv._sel = [L, p]                                # curve picked first
    cv.act_on()
    qapp.processEvents()
    pol = [c for c in m.sketch.constraints if isinstance(c, PointOnLine)]
    assert len(pol) == 1 and pol[0].p is p and pol[0].line is L


def test_circle_serves_as_the_point_arc_as_the_curve(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    c = m.add_circle(m.point(0, 0), 4.0)
    a, b, mid = m.point(15, 8), m.point(20, 2), m.point(19, 6)
    ar = m.sketch.arc(a, mid, b)
    m.constrain(Radius(c, 4.0), Fixed(a, x=15, y=8), Fixed(b, x=20, y=2),
                Fixed(mid, x=19, y=6))            # arc ring is rigid
    cv._sel = [c, ar]
    cv.act_on()                                   # CENTRE onto the ARC
    qapp.processEvents()
    poc = [x for x in m.sketch.constraints if isinstance(x, PointOnCircle)]
    assert len(poc) == 1 and poc[0].p is c.c and poc[0].curve is ar
    from tracer.core.sketch.entities import curve_center, curve_radius
    cx, cy = curve_center(ar)
    assert math.hypot(c.c.x - cx, c.c.y - cy) == pytest.approx(
        curve_radius(ar), abs=1e-5)               # landed exactly on it
    assert math.hypot(c.c.x, c.c.y) > 5.0         # it travelled to the arc


def test_bad_picks_do_not_swallow_the_period(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    p1 = m.point(0, 0)
    p2 = m.point(4, 4)
    before = len(m.sketch.constraints)
    cv._sel = [p1, p2]
    QTest.keyClick(cv, Qt.Key_Period)
    cv._sel = [p1]
    QTest.keyClick(cv, Qt.Key_Period)
    qapp.processEvents()
    assert len(m.sketch.constraints) == before      # nothing added


def test_menu_offers_on_curve_for_point_plus_curve_only(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    L = m.add_line(m.point(0, 0), m.point(10, 0))
    c = m.add_circle(m.point(5, 8), 3.0)
    p = m.point(3, 4)
    texts = lambda: [a.text() for a in cv._build_menu().actions()]
    cv._sel = [p, L]
    assert "On curve" in texts()
    cv._sel = [p, c]
    assert "On curve" in texts()
    cv._sel = [L, c]
    assert "On curve" not in texts()                # tangent branch owns it
    assert SketchCanvas.on_ok([p, L])
    assert not SketchCanvas.on_ok([p, m.point(1, 1)])


def test_period_survives_undo(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    L = m.add_line(m.point(0, 0), m.point(10, 0))
    m.constrain(Fixed(L.a, x=0, y=0), Fixed(L.b, x=10, y=0))
    p = m.point(4, 3)
    cv._sel = [p, L]
    QTest.keyClick(cv, Qt.Key_Period)
    qapp.processEvents()
    assert p.y == pytest.approx(0.0, abs=1e-6)
    cv.undo_op()
    qapp.processEvents()
    assert not any(isinstance(x, PointOnLine)
                   for x in m.sketch.constraints)
