"""M27 — symmetry constraint: two points mirror across a line axis.

Contract: exact mirroring (midpoint on the axis + perpendicular chord),
live mirror-follow under drag, order-independent toggle, save round-trip,
and the point·point·line selection gate in keys/menu/glyph.
"""
import math

import pytest

from tracer.core.sketch.constraints import Fixed, Symmetry
from tracer.core.sketch.model import (SketchModel, model_from_dict,
                                      model_to_dict)


# ---- kernel ---------------------------------------------------------------

def test_vertical_axis_mirrors_exactly():
    m = SketchModel()
    a = m.point(0, -20); b = m.point(0, 20)
    axis = m.add_line(a, b)
    m.constrain(Fixed(a, x=0, y=-20), Fixed(b, x=0, y=20))
    p1 = m.point(6, 2); p2 = m.point(4, -3)
    m.constrain(Fixed(p1, x=6, y=2), Symmetry(p1, p2, axis))
    res = m.solve()
    assert res.converged
    assert p2.x == pytest.approx(-6, abs=1e-6)
    assert p2.y == pytest.approx(2, abs=1e-6)


def test_drag_mirrors_live_across_horizontal_axis():
    m = SketchModel()
    a = m.point(-30, 0); b = m.point(30, 0)
    axis = m.add_line(a, b)
    m.constrain(Fixed(a, x=-30, y=0), Fixed(b, x=30, y=0))
    p1 = m.point(5, 8); p2 = m.point(-4, -7)
    m.constrain(Symmetry(p1, p2, axis))
    assert m.solve().converged
    p1.x, p1.y = 9.0, 15.0
    assert m.solve(pins=[p1]).converged
    assert p2.x == pytest.approx(9, abs=1e-6)
    assert p2.y == pytest.approx(-15, abs=1e-6)


def test_tilted_axis_still_mirrors():
    """Axis at 30°: mirror of (10, 0) across it is (5, 8.66...) at the
    same distance — check invariants, not sign conventions."""
    ang = math.radians(30)
    ux, uy = math.cos(ang), math.sin(ang)
    m = SketchModel()
    a = m.point(-10 * ux, -10 * uy); b = m.point(10 * ux, 10 * uy)
    axis = m.add_line(a, b)
    m.constrain(Fixed(a, x=a.x, y=a.y), Fixed(b, x=b.x, y=b.y))
    p1 = m.point(10, 0); p2 = m.point(0, 1)         # wrong side to start
    m.constrain(Fixed(p1, x=10, y=0), Symmetry(p1, p2, axis))
    assert m.solve().converged
    want = (10 * math.cos(2 * ang), 10 * math.sin(2 * ang))
    assert p2.x == pytest.approx(want[0], abs=1e-6)
    assert p2.y == pytest.approx(want[1], abs=1e-6)


def test_symmetry_toggle_and_roundtrip():
    m = SketchModel()
    a = m.point(0, -9); b = m.point(0, 9)
    ax = m.add_line(a, b)
    p1 = m.point(2, 1); p2 = m.point(3, 4)
    assert m.toggle(Symmetry, (p1, p2, ax)) is True
    assert m.has(Symmetry, (p2, p1, ax)) is True     # order-independent
    d = model_to_dict(m)
    assert any(c["t"] == "sym" for c in d["constraints"])
    m2 = model_from_dict(d)
    syms = [c for c in m2.sketch.constraints if isinstance(c, Symmetry)]
    assert len(syms) == 1 and syms[0].row == 0       # ONE stored row
    assert m.toggle(Symmetry, (p2, p1, ax)) is False


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                      # noqa: E402
from PySide6.QtTest import QTest                                # noqa: E402
from PySide6.QtCore import Qt                                   # noqa: E402

from tracer.ui.mainwindow import MainWindow                     # noqa: E402
from tracer.ui.renderer import SceneRenderer                    # noqa: E402
from tracer.ui.sketcheditor import SketchCanvas                 # noqa: E402
from tracer.core.sketch.entities import Circle, Point           # noqa: E402


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


def _v_axis_setup(cv):
    m = cv.model
    a = m.point(0, -15); b = m.point(0, 15)
    ax = m.add_line(a, b)
    m.constrain(Fixed(a, x=0, y=-15), Fixed(b, x=0, y=15))
    p1 = m.point(5, 3); p2 = m.point(-2, -1)
    m.constrain(Fixed(p1, x=5, y=3))       # anchor: the mirror must move p2
    return m, ax, p1, p2


def test_M_key_symmetrizes_pair_and_toggles_off(win, qapp):
    cv = _canvas(win, qapp)
    m, ax, p1, p2 = _v_axis_setup(cv)
    cv._sel = [p1, p2, ax]
    QTest.keyClick(cv, Qt.Key_M)
    qapp.processEvents()
    syms = [c for c in m.sketch.constraints if isinstance(c, Symmetry)]
    assert len(syms) == 1
    assert p2.x == pytest.approx(-5, abs=1e-6)
    assert p2.y == pytest.approx(3, abs=1e-6)
    QTest.keyClick(cv, Qt.Key_M)                     # same pick, removed
    qapp.processEvents()
    assert not [c for c in m.sketch.constraints if isinstance(c, Symmetry)]


def test_circle_center_counts_as_a_point(win, qapp):
    cv = _canvas(win, qapp)
    m, ax, p1, p2 = _v_axis_setup(cv)
    cir = m.add_circle(m.point(8, -4), 2.0)
    cv._sel = [p1, cir, ax]
    cv.act_symmetry()
    qapp.processEvents()
    syms = [c for c in m.sketch.constraints if isinstance(c, Symmetry)]
    assert len(syms) == 1 and syms[0].p2 is cir.c
    assert cir.c.x == pytest.approx(-5, abs=1e-6)


def test_bad_selections_never_symmetrize(win, qapp):
    cv = _canvas(win, qapp)
    m, ax, p1, p2 = _v_axis_setup(cv)
    ln2 = m.add_line(m.point(-9, -9), m.point(9, 9))
    before = len(m.sketch.constraints)
    cv._sel = [p1, ln2, ax]                          # 2 lines + 1 point: no
    cv.act_symmetry()
    cv._sel = [p1, p2]                               # no axis: no
    cv.act_symmetry()
    qapp.processEvents()
    assert len(m.sketch.constraints) == before


def test_sym_ok_and_glyph_paint(win, qapp):
    cv = _canvas(win, qapp)
    m, ax, p1, p2 = _v_axis_setup(cv)
    cir = m.add_circle(m.point(8, -4), 2.0)
    assert SketchCanvas.sym_ok([p1, p2, ax])
    assert SketchCanvas.sym_ok([cir, p1, ax])        # centre substitution
    assert not SketchCanvas.sym_ok([p1, p2, cir])
    assert not SketchCanvas.sym_ok([p1, p2])
    m.constrain(Symmetry(p1, p2, ax))
    m.solve()
    cv.update(); qapp.processEvents()
    win.grab()                                       # badge "S" drawn
    qapp.processEvents()
    # the badge sits on the chord midpoint — which after solving lies ON
    # the axis (x=0 world), i.e. at the axis' screen x
    mid = cv.w2s((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
    assert abs(mid.x() - cv.w2s(0, 0).x()) < 1e-6
