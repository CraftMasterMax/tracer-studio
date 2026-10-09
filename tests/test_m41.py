"""M41 — Midpoint & Collinear constraints.

Two constraints Fusion sketches lean on that were still missing: Midpoint
(a point pinned to a segment's centre) and Collinear (two segments merged
onto one infinite line).  Both are 2-DOF, so they expand to two solver
rows like Coincident; the numerical Jacobian does the rest.

Kernel tests pin the reference geometry with Fixed so the answer has a
single ground-truth value; canvas tests drive the real act_* gestures and
check the semantic invariant (point == segment centre) survives a solve,
plus the guards and the context-menu wiring.
"""
import pytest

import numpy as np

from tracer.core.sketch.constraints import Collinear, Fixed, Midpoint
from tracer.core.sketch.entities import Point
from tracer.core.sketch.model import (SketchModel, model_from_dict,
                                      model_to_dict)


def _fixed_reference_line(m):
    ln = m.add_line(Point(0.0, 0.0), Point(20.0, 6.0))
    m.toggle(Fixed, (ln.a,))
    m.toggle(Fixed, (ln.b,))
    return ln


# ---- kernel ----------------------------------------------------------------

def test_midpoint_pins_a_free_point_to_the_segment_centre():
    m = SketchModel()
    ln = _fixed_reference_line(m)
    p = m.sketch.point(3.0, 15.0)          # a stray, far from the segment
    assert m.toggle(Midpoint, (p, ln))
    r = m.solve()
    assert r.converged and r.residual_norm < 1e-7
    assert p.x == pytest.approx(10.0, abs=1e-6)
    assert p.y == pytest.approx(3.0, abs=1e-6)


def test_midpoint_can_reuse_a_vertex_from_another_line():
    m = SketchModel()
    ref = _fixed_reference_line(m)
    v = m.sketch.point(-5.0, 9.0)
    m.add_line(v, m.sketch.point(4.0, 3.0))   # v is a real bracket corner
    m.toggle(Midpoint, (v, ref))
    assert m.solve().converged
    assert v.x == pytest.approx(10.0, abs=1e-6)
    assert v.y == pytest.approx(3.0, abs=1e-6)


def test_collinear_puts_two_segments_on_one_infinite_line():
    m = SketchModel()
    l1 = m.add_line(Point(0.0, 0.0), Point(10.0, 0.0))
    m.toggle(Fixed, (l1.a,))
    m.toggle(Fixed, (l1.b,))
    l2 = m.add_line(Point(2.0, 1.5), Point(12.0, 0.5))   # tilted + offset
    assert m.toggle(Collinear, (l1, l2))
    assert m.solve().converged
    for e in (l2.a, l2.b):                                # l2 now rides y=0
        assert abs(e.y) < 1e-6
    d1 = np.array([l1.b.x - l1.a.x, l1.b.y - l1.a.y])
    d2 = np.array([l2.b.x - l2.a.x, l2.b.y - l2.a.y])
    assert abs(d1[0] * d2[1] - d1[1] * d2[0]) < 1e-6       # parallel


def test_both_toggle_off_on_the_second_gesture():
    m = SketchModel()
    ln = _fixed_reference_line(m)
    p = m.sketch.point(3.0, 15.0)
    l2 = m.add_line(Point(1.0, 2.0), Point(5.0, 2.0))
    assert m.toggle(Midpoint, (p, ln)) is True
    assert m.toggle(Midpoint, (p, ln)) is False
    assert m.toggle(Collinear, (ln, l2)) is True
    assert m.toggle(Collinear, (ln, l2)) is False
    kinds = [type(c).__name__ for c in m.sketch.constraints]
    assert "Midpoint" not in kinds and "Collinear" not in kinds


def test_midpoint_and_collinear_survive_the_save_roundtrip():
    m = SketchModel()
    ln = _fixed_reference_line(m)
    p = m.sketch.point(3.0, 15.0)
    l2 = m.add_line(Point(2.0, 1.5), Point(12.0, 0.5))
    m.toggle(Midpoint, (p, ln))
    m.toggle(Collinear, (ln, l2))
    payload = model_to_dict(m)
    assert {"mid", "col"} <= {c["t"] for c in payload["constraints"]}
    back = model_from_dict(payload)
    kinds = [type(c).__name__ for c in back.sketch.constraints]
    assert "Midpoint" in kinds and "Collinear" in kinds
    mp = next(c for c in back.sketch.constraints
              if isinstance(c, Midpoint))
    assert mp.line is back.sketch.lines[0]        # re-bound to loaded line


pytest.importorskip("PySide6")

from PySide6.QtTest import QTest                                          # noqa: E402
from PySide6.QtWidgets import QApplication                                # noqa: E402

from tracer.core.sketch.entities import Line                              # noqa: E402
from tracer.ui.mainwindow import MainWindow                               # noqa: E402
from tracer.ui.renderer import SceneRenderer                              # noqa: E402


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


@pytest.fixture
def canvas(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    return win.sketch


# ---- canvas gestures --------------------------------------------------------

def test_act_midpoint_pins_and_solves(canvas):
    m = canvas.model
    ln = m.add_line(Point(0.0, 0.0), Point(20.0, 0.0))
    p = m.sketch.point(4.0, 12.0)
    canvas._sel = [p, ln]
    canvas.act_midpoint()
    assert any(isinstance(c, Midpoint) for c in m.sketch.constraints)
    # underconstrained like any live sketch: the invariant, not positions
    assert p.x == pytest.approx((ln.a.x + ln.b.x) / 2, abs=1e-4)
    assert p.y == pytest.approx((ln.a.y + ln.b.y) / 2, abs=1e-4)


def test_act_collinear_merges_two_selected_lines(canvas):
    m = canvas.model
    l1 = m.add_line(Point(0.0, 0.0), Point(10.0, 0.0))
    l2 = m.add_line(Point(0.0, 3.0), Point(10.0, 0.2))
    canvas._sel = [l1, l2]
    canvas.act_collinear()
    assert any(isinstance(c, Collinear) for c in m.sketch.constraints)
    # after solve the two lines share a line: l2 ends lie on l1's line
    d1 = np.array([l1.b.x - l1.a.x, l1.b.y - l1.a.y])
    for e in (l2.a, l2.b):
        v = np.array([e.x - l1.a.x, e.y - l1.a.y])
        assert abs(d1[0] * v[1] - d1[1] * v[0]) < 1e-3 * (np.linalg.norm(d1))


def test_midpoint_and_collinear_refuse_wrong_selections(canvas):
    m = canvas.model
    l1 = m.add_line(Point(0, 0), Point(10, 0))
    l2 = m.add_line(Point(0, 3), Point(10, 3))
    pa = m.sketch.point(2, 2)
    pb = m.sketch.point(6, 5)
    canvas._sel = [pa, pb]          # two points: not a midpoint pair
    canvas.act_midpoint()
    canvas._sel = [l1]              # one line: not collinear
    canvas.act_collinear()
    canvas._sel = [pa, l1, l2]      # three entities: not midpoint either
    canvas.act_midpoint()
    assert not any(isinstance(c, (Midpoint, Collinear))
                   for c in m.sketch.constraints)


# ---- context menu wiring -----------------------------------------------------

def test_two_line_menu_offers_collinear(canvas):
    m = canvas.model
    l1 = m.add_line(Point(0, 0), Point(9, 0))
    l2 = m.add_line(Point(0, 2), Point(9, 2))
    canvas._sel = [l1, l2]
    texts = [a.text() for a in canvas._build_menu().actions()]
    assert "Collinear" in texts


def test_point_line_menu_offers_midpoint(canvas):
    m = canvas.model
    ln = m.add_line(Point(0, 0), Point(9, 0))
    p = m.sketch.point(4, 4)
    canvas._sel = [p, ln]
    texts = [a.text() for a in canvas._build_menu().actions()]
    assert "Midpoint" in texts
    assert "On curve" in texts            # both valid; both offered


# ---- proof of life -----------------------------------------------------------

def test_screenshot_proof(win, qapp):
    import os
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    m = cv.model
    l1 = m.add_line(Point(0, 0), Point(60, 0))
    l2 = m.add_line(Point(0, 3), Point(60, 0.4))
    cv._sel = [l1, l2]; cv.act_collinear()
    p = m.sketch.point(5, 20)
    m.add_line(p, m.sketch.point(30, 14))
    cv._sel = [p, l1]; cv.act_midpoint()
    qapp.processEvents()
    cv.update(); qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win._sketch_page.grab().save(f"{out}/m41_constraints.png")
