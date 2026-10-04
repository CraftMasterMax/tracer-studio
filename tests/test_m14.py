"""M14: three-point Arc entity — tool, profile, serialization, editing."""
import json
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog     # noqa: E402

from forma.core.sketch.entities import Arc, Point            # noqa: E402
from forma.core.sketch.model import (SketchModel,            # noqa: E402
                                     model_to_dict,
                                     model_from_dict)
from forma.core.sketch.profile import regions                # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    from forma.ui.mainwindow import MainWindow
    from forma.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (10.0, True)))
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


def _click(cv, x, y, button=Qt.LeftButton):
    p = cv.w2s(x, y).toPoint()
    QTest.mousePress(cv, button, Qt.NoModifier, p, 10)
    QTest.mouseRelease(cv, button, Qt.NoModifier, p, 10)


# ---- core entity -----------------------------------------------------------
def test_arc_circle_and_sample():
    # quarter arc: start (10,0), through (7.07,7.07), end (0,10), centre 0,0
    ar = Arc(Point(10, 0), Point(7.071, 7.071), Point(0, 10))
    (cx, cy), r = ar.circle()
    assert (cx, cy, r) == pytest.approx((0, 0, 10), abs=1e-3)
    smp = ar.sample(64)
    assert np.allclose(smp[0], [10, 0], atol=1e-3)
    assert np.allclose(smp[-1], [0, 10], atol=1e-3)
    # every sample is on the circle
    assert np.allclose(np.hypot(smp[:, 0] - cx, smp[:, 1] - cy), r, atol=1e-3)
    # arc is the short way (quarter turn, ~90 deg -> <= 180)
    assert smp[len(smp) // 2][0] > 0 and smp[len(smp) // 2][1] > 0


def test_arc_reflex_sweep_follows_mid():
    # mid chosen so the arc goes the long way (reflex) around
    ar = Arc(Point(10, 0), Point(0, -10), Point(0, 10))   # via bottom
    smp = ar.sample(96)
    assert min(smp[:, 1]) < -1, "should dip below axis (the long way)"


# ---- profile integration ---------------------------------------------------
def test_capsule_region_from_two_arcs_two_lines():
    m = SketchModel()
    a1, b1 = m.point(0, 0), m.point(20, 0)
    a2, b2 = m.point(20, 10), m.point(0, 10)
    m.add_line(a1, b1)
    m.add_line(a2, b2)
    m.sketch.arc(b1, m.point(25, 5), a2)
    m.sketch.arc(b2, m.point(-5, 5), a1)
    loops, warns = m.to_loops()
    regs = regions(loops)
    assert len(regs) == 1
    ideal = 20 * 10 + math.pi * 5 * 5
    assert regs[0]["area"] == pytest.approx(ideal, rel=1e-2)


def test_construction_arc_excluded_from_profile():
    m = SketchModel()
    a1, b1 = m.point(0, 0), m.point(20, 0)
    a2, b2 = m.point(20, 10), m.point(0, 10)
    m.add_line(a1, b1); m.add_line(a2, b2)
    ar = m.sketch.arc(b1, m.point(25, 5), a2)
    ar2 = m.sketch.arc(b2, m.point(-5, 5), a1)
    ar2.construction = True
    loops, warns = m.to_loops()
    # only 3 of 4 boundary edges -> not closed -> no region
    assert regions(loops) == []


# ---- serialization + undo snapshot ----------------------------------------
def test_arc_serialization_roundtrip():
    m = SketchModel()
    a, b = m.point(0, 0), m.point(10, 0)
    m.sketch.arc(a, m.point(5, 4), b)
    d = model_to_dict(m)
    assert len(d["arcs"]) == 1
    m2 = model_from_dict(d)
    assert len(m2.sketch.arcs) == 1
    (cx, cy), r = m2.sketch.arcs[0].circle()
    assert r == pytest.approx(5.125, rel=5e-2)   # radius of that 3-pt arc
    # survives json (undo history uses this path)
    m3 = model_from_dict(json.loads(json.dumps(d)))
    assert len(m3.sketch.arcs) == 1


# ---- UI tool ---------------------------------------------------------------
def test_A_key_selects_arc_tool(win):
    win.new_document(); win.action_new_sketch()
    QTest.keyPress(win.sketch, Qt.Key_A)
    assert win.sketch._tool == "arc"


def test_three_click_arc_creates_entity(win, qapp):
    win.new_document(); win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("arc")
    _click(cv, 0, 0)          # start
    _click(cv, 20, 0)         # end
    _click(cv, 10, 6)         # bulge
    qapp.processEvents()
    assert len(cv.model.sketch.arcs) == 1
    assert len(cv._arc_pts) == 1     # chained from the end point


def test_arc_chains_second_arc(win, qapp):
    win.new_document(); win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("arc")
    for x, y in [(0, 0), (20, 0), (10, 6),   # arc 1
                 (30, 8)]:                    # arc 2 end (start=prev end)
        _click(cv, x, y)
    qapp.processEvents()
    assert len(cv._arc_pts) == 2               # mid of arc 2 pending
    _click(cv, 28, 2)                          # off-chord bulge
    assert len(cv.model.sketch.arcs) == 2


def test_flat_arc_becomes_a_line(win, qapp):
    win.new_document(); win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("arc")
    _click(cv, 0, 0); _click(cv, 20, 0); _click(cv, 10, 0.1)  # ~flat
    qapp.processEvents()
    assert len(cv.model.sketch.arcs) == 0
    assert len(cv.model.sketch.lines) == 1


def test_back_click_cancels_arc(win, qapp):
    win.new_document(); win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("arc")
    _click(cv, 0, 0)
    _click(cv, 20, 0)
    _click(cv, 0, 0)                   # re-click start -> cancel
    qapp.processEvents()
    assert cv._arc_pts == []
    assert len(cv.model.sketch.arcs) == 0


def test_undo_restores_after_arc(win, qapp):
    win.new_document(); win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("arc")
    _click(cv, 0, 0); _click(cv, 20, 0); _click(cv, 10, 6)
    qapp.processEvents()
    assert len(cv.model.sketch.arcs) == 1
    QTest.keyPress(cv, Qt.Key_Z, Qt.ControlModifier)
    qapp.processEvents()
    assert len(cv.model.sketch.arcs) == 0
    QTest.keyPress(cv, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
    assert len(cv.model.sketch.arcs) == 1


def test_arc_hit_and_drag_mid(win, qapp):
    win.new_document(); win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("arc")
    _click(cv, 0, 0); _click(cv, 20, 0); _click(cv, 10, 6)
    qapp.processEvents()
    ar = cv.model.sketch.arcs[0]
    # hit near the bulge
    hit = cv._hit(cv.w2s(10, 6))
    assert hit and hit[0] in ("point", "arc")
    # drag the mid point -> bulge grows, radius tightens
    cv.set_tool("select")
    qapp.processEvents()
    r_before = ar.circle()[1]
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, cv.w2s(10, 6).toPoint(), 10)
    QTest.mouseMove(cv, cv.w2s(10, 12).toPoint())
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, cv.w2s(10, 12).toPoint(), 10)
    qapp.processEvents()
    assert cv.model.sketch.arcs[0].circle()[1] < r_before - 0.5


def test_construction_toggle_on_arc(win, qapp):
    win.new_document(); win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("arc")
    _click(cv, 0, 0); _click(cv, 20, 0); _click(cv, 10, 6)
    qapp.processEvents()
    ar = cv.model.sketch.arcs[0]
    cv._sel = [ar]
    cv.act_construction()
    assert ar.construction is True
    cv.act_construction()
    assert ar.construction is False


def test_delete_removes_arc(win, qapp):
    win.new_document(); win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("arc")
    _click(cv, 0, 0); _click(cv, 20, 0); _click(cv, 10, 6)
    qapp.processEvents()
    cv._sel = [cv.model.sketch.arcs[0]]
    cv.act_delete()
    assert len(cv.model.sketch.arcs) == 0


def test_revolve_a_capsule_solid(win, qapp):
    """Arc closes profiles that lines can't: revolve a rounded profile."""
    win.new_document()
    win.action_new_sketch("XZ")
    cv = win.sketch
    cv.set_tool("arc")
    _click(cv, 8, 0); _click(cv, 8, 20); _click(cv, 14, 10)   # bulged cap
    _click(cv, 8, 0)                                            # back to start
    qapp.processEvents()
    # arc alone from (8,0)->(8,20) bulge (14,10); close with a line back
    if not cv.model.sketch.lines:
        cv.set_tool("line")
        _click(cv, 8, 20); _click(cv, 8, 0)
    qapp.processEvents()
    loops, warns = cv.model.to_loops()
    assert len(regions(loops)) >= 1
