"""M25 — centerline slot tool: 3 clicks to a fully-tangent, extrudable slot.

Contract: the construction is exact on creation (tangent error < 1e-6,
area = πr² + 2rL), the slot is a single closed profile that extrudes to
the analytic volume, it round-trips through save/load, and the UI tool
places it from real synthetic clicks with no stray anchor points.
"""
import math

import numpy as np
import pytest

from tracer.core.sketch.model import SketchModel, model_from_dict, model_to_dict
from tracer.core.sketch.constraints import Tangent, Radius, _unit_normal
from tracer.core.sketch.entities import Point, curve_center, curve_radius


def _tan_err(m):
    out = []
    for c in m.sketch.constraints:
        if isinstance(c, Tangent):
            l, cv = c.e1, c.e2
            n = _unit_normal(l)
            cx, cy = curve_center(cv)
            out.append(abs(abs(n[0] * (cx - l.a.x) + n[1] * (cy - l.a.y))
                           - curve_radius(cv)))
    return max(out) if out else 9e9


def _slot(x1, y1, x2, y2, r):
    m = SketchModel()
    m.add_slot(m.point(x1, y1), m.point(x2, y2), r)
    return m


# ---- construction -----------------------------------------------------------

@pytest.mark.parametrize("x1,y1,x2,y2,r", [
    (0, 0, 20, 0, 5),          # horizontal
    (3, 2, 3, 15, 3),          # vertical
    (0, 0, 15, 10, 4),         # diagonal
    (-8, -8, 12, 6, 2.5),      # offset diagonal
])
def test_slot_is_exact_and_analytic(x1, y1, x2, y2, r):
    m = _slot(x1, y1, x2, y2, r)
    res = m.solve()
    assert res.converged
    assert len(m.sketch.lines) == 2 and len(m.sketch.arcs) == 2
    assert _tan_err(m) < 1e-6
    radii = [curve_radius(c.curve) for c in m.sketch.constraints
             if isinstance(c, Radius)]
    assert len(radii) == 2 and all(abs(x - r) < 1e-9 for x in radii)
    L = math.hypot(x2 - x1, y2 - y1)
    loops, warns = m.to_loops()
    assert len(loops) == 1 and not warns
    assert loops[0]["area"] == pytest.approx(math.pi * r * r + 2 * r * L,
                                             abs=0.1)      # poly-chord deficit


def test_degenerate_slot_makes_nothing():
    m = SketchModel()
    assert m.add_slot(m.point(1, 1), m.point(1, 1), 3) == []
    assert m.add_slot(m.point(0, 0), m.point(5, 0), 0) == []
    assert not m.sketch.lines and not m.sketch.arcs


def test_slot_extrudes_to_analytic_volume():
    from tracer.core.document import ExtrudeFeature
    m = _slot(0, 0, 30, 0, 6)
    m.solve()
    loops, _ = m.to_loops()
    feat = ExtrudeFeature(name="slot", outer=np.asarray(loops[0]["points"]),
                          height=4)
    sol = feat.build()
    want = (math.pi * 36 + 2 * 6 * 30) * 4
    assert sol.volume == pytest.approx(want, abs=0.5)
    assert sol.to_trimesh().is_watertight


def test_slot_survives_save_roundtrip():
    m = _slot(0, 0, 15, 10, 4)
    m.solve()
    d = model_to_dict(m)
    m2 = model_from_dict(d)
    assert len(m2.sketch.arcs) == 2 and len(m2.sketch.lines) == 2
    assert m2.solve().converged
    assert _tan_err(m2) < 1e-6
    loops, _ = m2.to_loops()
    L = math.hypot(15, 10)
    assert loops[0]["area"] == pytest.approx(math.pi * 16 + 2 * 4 * L, abs=0.05)


def test_slot_extends_keeping_radius_and_tangency():
    """Anchor one cap, drag the other out along the axis: the slot grows
    but stays a true r-constant slot (tangent + radius hold)."""
    from tracer.core.sketch.constraints import Fixed
    m = SketchModel()
    a = m.point(0, 0)
    b = m.point(15, 0)
    top, bot, cap2, cap1 = m.add_slot(a, b, 4.0)
    m.constrain(Fixed(cap2.a, x=cap2.a.x, y=cap2.a.y))   # anchor far cap
    m.solve()
    c1 = curve_center(cap1)
    c2 = curve_center(cap2)
    ux = (c2[0] - c1[0]) / math.dist(c1, c2)
    uy = (c2[1] - c1[1]) / math.dist(c1, c2)
    L0 = math.dist(c1, c2)
    cap1.m.x -= ux * 8
    cap1.m.y -= uy * 8
    m.solve(pins=[cap1.m])
    assert _tan_err(m) < 1e-5                  # holds to solver noise floor
    cc1, cc2 = curve_center(cap1), curve_center(cap2)
    assert math.dist(cc1, cc2) > L0 + 6
    radii = [curve_radius(c.curve) for c in m.sketch.constraints
             if isinstance(c, Radius)]
    assert all(abs(x - 4.0) < 1e-3 for x in radii)
    loops, warns = m.to_loops()
    assert len(loops) == 1 and not warns


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QInputDialog       # noqa: E402
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


def _click(cv, qapp, wx, wy):
    s = cv.w2s(wx, wy).toPoint()
    QTest.mousePress(cv, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, s, 10)
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, s, 10)
    qapp.processEvents()


def test_O_key_and_three_clicks_build_a_clean_slot(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    QTest.keyClick(cv, Qt.Key_O)
    qapp.processEvents()
    assert cv._tool == "slot"
    n_before = len(cv.model.sketch.points)
    _click(cv, qapp, 0, 0)
    _click(cv, qapp, 40, 0)
    _click(cv, qapp, 20, 10)
    sk = cv.model.sketch
    assert len(sk.lines) == 2 and len(sk.arcs) == 2
    assert _tan_err(cv.model) < 1e-6
    # the slot added its OWN 6 points; the centre/width clicks left nothing
    assert len(sk.points) == n_before + 6
    # ...and the finished slot is a single closed profile
    loops, warns = cv.model.to_loops()
    assert len(loops) == 1 and not warns


def test_tiny_slot_click_is_dropped_not_degenerate(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    QTest.keyClick(cv, Qt.Key_O)
    _click(cv, qapp, 0, 0)
    _click(cv, qapp, 30, 0)
    _click(cv, qapp, 15, 0.2)                   # width near-zero on screen
    qapp.processEvents()
    assert not cv.model.sketch.arcs              # refused, stays empty


def test_slot_paints_live_capsule_preview(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    QTest.keyClick(cv, Qt.Key_O)
    _click(cv, qapp, 0, 0)
    _click(cv, qapp, 30, 0)
    assert len(cv._slot) == 2                     # awaiting the width click
    QTest.mouseMove(cv, cv.w2s(15, 8).toPoint())
    qapp.processEvents()
    win.grab()                                    # runs the preview painter
    qapp.processEvents()
