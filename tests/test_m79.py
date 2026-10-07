"""M79 — The ellipse: the sketcher's last basic shape.

Fusion's sketch toolbar carries Line, Rectangle, Circle, Slot, Polygon,
Arc and ELLIPSE; we shipped everything but the ellipse.  It now exists
as a first-class entity: a shared centre Point (so the origin magnet,
snapping, Fixed/Coincident constraints and dragging all work on it for
free) plus two radii carried as real solver variables — a bare ellipse
counts FOUR degrees of freedom, and a fixed centre leaves exactly two.

Centre-first UX, like the circle: click (or drag) the centre, then the
second click's offsets ARE rx and ry.  Profile extraction treats it as
a 96-gon CCW loop, so an elliptical prism's volume is π·rx·ry·h and
JSON round-trips carry it whole.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from tracer.core.document import Document, ExtrudeFeature            # noqa: E402
from tracer.core.sketch.constraints import Fixed                     # noqa: E402
from tracer.core.sketch.model import (SketchModel, model_from_dict,  # noqa: E402
                                      model_to_dict)


def _oval(rx=12.0, ry=5.0, cx=20.0, cy=8.0, construction=False):
    m = SketchModel()
    c = m.point(cx, cy)
    m.sketch.ellipse(c, rx, ry, construction)
    return m


# ---- the core: entities, solver, profiles ------------------------------------

def test_a_bare_ellipse_has_four_dof():
    r = _oval().sketch.solve()
    assert r.converged
    assert r.dof == 4                      # centre (2) + rx + ry


def test_a_fixed_centre_owns_two_dof():
    m = _oval()
    c = m.sketch.ellipses[0].c
    m.constrain(Fixed(c, x=c.x, y=c.y))       # act_fix's own grammar
    r = m.sketch.solve()
    assert r.converged and r.dof == 2          # the radii are still free


def test_the_ellipse_bounds_a_closed_loop():
    loops, warns = _oval(12.0, 5.0, 0.0, 0.0).to_loops()
    assert len(loops) == 1
    assert loops[0]["area"] == pytest.approx(math.pi * 60.0, rel=2e-3)


def test_a_construction_ellipse_never_bounds_a_profile():
    m = _oval(construction=True)
    loops, _w = m.to_loops()
    assert loops == []


def test_the_oval_survives_the_round_trip():
    m2 = model_from_dict(model_to_dict(_oval()))
    assert len(m2.sketch.ellipses) == 1
    e = m2.sketch.ellipses[0]
    assert (e.rx, e.ry) == (12.0, 5.0)
    assert (e.c.x, e.c.y) == (20.0, 8.0)
    assert m2.sketch.solve().dof == 4


def test_an_elliptical_prism_weighs_pi_rx_ry_h():
    loops, _w = _oval(12.0, 5.0, 0.0, 0.0).to_loops()
    doc = Document()
    doc.add(ExtrudeFeature(name="boss", outer=loops[0]["points"],
                           height=4.0))
    s = doc.recompute()
    assert s.volume == pytest.approx(math.pi * 60.0 * 4.0, rel=2e-3)


# ---- the editor: the centre-first UX ------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        from tracer.ui.renderer import SceneRenderer
        from tracer.ui.mainwindow import MainWindow
        try:
            r = SceneRenderer()
        except Exception as e:                 # CI windows runners: no GL
            pytest.skip(f"no headless GL available: {e}")
        w = MainWindow(renderer=r)
        w.resize(1000, 700)
        w.show()
        qapp.processEvents()
        yield w
        w._unsaved = False
        w.close()
        r.ctx.release()
    except Exception:
        raise


def _cv(win, qapp, scale=4.0):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    cv.set_grid_snap(False)                  # the magnet rests OFF here
    cv._scale = scale
    cv._center = np.array([0.0, 0.0])
    cv.set_tool("select")
    qapp.processEvents()
    return cv


def _click(cv, qapp, x, y, dx=0, dy=0):
    p = cv.w2s(x, y)
    QTest.mouseClick(cv, Qt.LeftButton, Qt.NoModifier,
                     QPoint(int(p.x()) + dx, int(p.y()) + dy))
    qapp.processEvents()


def test_ellipse_tool_lands_the_centre_on_the_origin(win, qapp):
    cv = _cv(win, qapp)
    cv.set_tool("ellipse")
    _click(cv, qapp, 0, 0, dx=2, dy=2)       # magnet: the centre IS (0,0)
    _click(cv, qapp, 14, 9)                  # offsets are the radii
    e = cv.model.sketch.ellipses[0]
    assert (e.c.x, e.c.y) == (0.0, 0.0)
    assert e.rx == pytest.approx(14.0, abs=0.3)
    assert e.ry == pytest.approx(9.0, abs=0.3)


def test_drag_a_whole_ellipse_in_one_motion(win, qapp):
    cv = _cv(win, qapp)
    cv.set_tool("ellipse")
    a = cv.w2s(0, 0)
    b = cv.w2s(20, 10)
    pa, pb = QPoint(int(a.x()), int(a.y())), QPoint(int(b.x()), int(b.y()))
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, pa)
    QTest.mouseMove(cv, pb)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, pb)
    qapp.processEvents()
    e = cv.model.sketch.ellipses[0]
    assert e.rx == pytest.approx(20.0, abs=0.3)
    assert e.ry == pytest.approx(10.0, abs=0.3)
    assert len(cv.model.sketch.points) == 1      # drag REUSES the armed
    assert cv.model.sketch.solve().dof == 4      # centre — no orphans


def test_the_radius_click_leaves_no_stray_point(win, qapp):
    # Fusion consumes the radius click; it must not litter the model
    # with an unreferenced Point (2 phantom DOF + a snap magnet).
    cv = _cv(win, qapp)
    cv.set_tool("ellipse")
    _click(cv, qapp, 0, 0)
    _click(cv, qapp, 14, 9)
    assert len(cv.model.sketch.points) == 1      # only the centre exists
    assert cv.model.sketch.solve().dof == 4      # and no phantom DOF


def test_click_the_curve_selects_it_and_delete_removes_it(win, qapp):
    cv = _cv(win, qapp)
    m = cv.model
    e = m.sketch.ellipse(m.point(0, 0), 15.0, 8.0)
    cv.set_tool("select")
    _click(cv, qapp, 15, 0)                  # dead on the ring at t=0
    assert cv._sel == [e]
    cv.act_delete()
    assert m.sketch.ellipses == []


def test_shift_C_and_the_toolbar_agree(win, qapp):
    cv = _cv(win, qapp)
    QTest.keyClick(cv, Qt.Key_C, Qt.ShiftModifier)   # M113: ellipse is the
    qapp.processEvents()                             # circle family, Shift
    assert cv._tool == "ellipse"
    QTest.keyClick(cv, Qt.Key_Escape)                # Esc = back to select
    qapp.processEvents()
    assert cv._tool == "select"
    win._tool_btns["ellipse"].click()
    assert cv._tool == "ellipse"
    assert win._tool_btns["ellipse"].isChecked()
