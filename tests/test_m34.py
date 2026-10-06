"""M34 — Offset outline (U): a parallel mitred copy of a closed loop.

Fusion's Offset Entities, maker-cut: every edge slides along its own
outward normal and neighbours meet where the shifted edges cross — so
convex corners stretch, concave corners close in, and the copy stays
EXACT for straight-edge geometry (no approximation, no fuzz).  Offsetting
a profile inward past a feature is refused, never silently mangled.  The
twin loop lives in the same sketch, so nested loops extrude as a frame —
which is exactly what makers want from offset (walls, ribs, flanges).
"""
import math

import numpy as np
import pytest

from tracer.core.sketch.entities import Point
from tracer.core.sketch.model import SketchModel


def _rect(m, w=40.0, h=30.0):
    return m.add_rect(Point(0, 0), Point(w, h))


def _corners(lines):
    seen = []
    for l in lines:
        if l.a not in seen:
            seen.append(l.a)
    return [(p.x, p.y) for p in seen]


def _area(pts):
    pts = np.asarray(pts, float)
    n = len(pts)
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1]
                     - pts[i][1] * pts[(i + 1) % n][0] for i in range(n))


# ---- kernel -----------------------------------------------------------------

def test_outward_offset_of_a_rect_is_exact():
    m = SketchModel()
    _rect(m, 40.0, 30.0)
    twin = m.add_offset(5.0)
    assert len(twin) == 4
    assert _area(_corners(twin)) == pytest.approx(50.0 * 40.0)
    xs = {round(x, 9) for x, _ in _corners(twin)}
    ys = {round(y, 9) for _, y in _corners(twin)}
    assert xs == {-5.0, 45.0} and ys == {-5.0, 35.0}


def test_inward_offset_shrinks_from_the_same_frame():
    m = SketchModel()
    _rect(m, 40.0, 30.0)
    twin = m.add_offset(-5.0)
    assert _area(_corners(twin)) == pytest.approx(30.0 * 20.0)


def test_concave_corner_closes_in_on_an_L():
    m = SketchModel()
    ring = [(0, 0), (24, 0), (24, 12), (12, 12), (12, 24), (0, 24)]
    pts = [m.point(x, y) for x, y in ring]
    for i in range(len(pts)):
        m.add_line(pts[i], pts[(i + 1) % len(pts)])
    twin = m.add_offset(3.0)
    assert len(twin) == 6
    # mitre maths: A' = A + d*P + d^2*(convex - reflex) = 432+288+9*4
    assert _area(_corners(twin)) == pytest.approx(756.0)


def test_collinear_vertices_survive_the_offset():
    m = SketchModel()
    ring = [(0, 0), (20, 0), (40, 0), (40, 30), (0, 30)]   # extra vertex
    pts = [m.point(x, y) for x, y in ring]
    for i in range(len(pts)):
        m.add_line(pts[i], pts[(i + 1) % len(pts)])
    twin = m.add_offset(2.0)
    assert _area(_corners(twin)) == pytest.approx(44.0 * 34.0)


def test_collapse_and_pinch_are_refused_cleanly():
    m = SketchModel()
    _rect(m, 40.0, 30.0)
    with pytest.raises(ValueError, match="collapses or flips"):
        m.add_offset(-20.0)                    # past the 30 mm side
    assert len(m.sketch.lines) == 4            # original untouched


def test_arcs_circles_holes_and_ambiguity_are_refused():
    m = SketchModel()
    m.add_circle(m.point(0, 0), 5.0)
    with pytest.raises(ValueError, match="straight-edge"):
        m.add_offset(1.0)
    m2 = SketchModel()
    _rect(m2)
    m2.add_rect(Point(5, 5), Point(10, 10))    # second loop: ambiguous
    with pytest.raises(ValueError, match="exactly one closed"):
        m2.add_offset(1.0)


def test_nested_offset_extrudes_as_a_frame():
    from tracer.core.document import ExtrudeFeature
    from tracer.core.sketch.profile import regions
    m = SketchModel()
    _rect(m, 40.0, 30.0)
    m.add_offset(-4.0)
    loops, _warns = m.to_loops()
    assert sorted(round(r["area"], 3) for r in loops) == [704.0, 1200.0]
    regs = regions(list(loops))
    assert len(regs) == 1 and len(regs[0]["holes"]) == 1
    outer = regs[0]
    solid = ExtrudeFeature(name="frame", outer=outer["points"],
                           holes=[h["points"] for h in outer["holes"]],
                           height=5.0).build()
    assert solid.volume == pytest.approx((1200.0 - 32.0 * 22.0) * 5.0,
                                         abs=1.5)
    assert solid.to_trimesh().is_watertight


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


def _click(cv, qapp, wx, wy):
    s = cv.w2s(wx, wy).toPoint()
    QTest.mousePress(cv, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, s, 10)
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, s, 10)
    qapp.processEvents()


def _rect_sketch(win, qapp):
    win.new_document()
    win.action_new_sketch()                     # starts on the rect tool
    qapp.processEvents()
    QTest.qWaitForWindowExposed(win)
    QTest.qWait(25)                             # let the page settle its fit
    cv = win.sketch
    for attempt in (0, 1):
        _click(cv, qapp, 0, 0)
        _click(cv, qapp, 40, 30)
        qapp.processEvents()
        lines = cv.model.sketch.lines
        xs = [v for l in lines for v in (l.a.x, l.b.x)]
        ys = [v for l in lines for v in (l.a.y, l.b.y)]
        exact = (len(lines) == 4
                 and round(min(xs or [0]), 6) == 0.0
                 and round(max(xs or [0]), 6) == 40.0
                 and round(min(ys or [0]), 6) == 0.0
                 and round(max(ys or [0]), 6) == 30.0)
        if exact or attempt:
            return cv
        # The view refit mid-click and knocked the corners off integers:
        # redraw from a clean canvas now that the transform has settled.
        cv.set_model(SketchModel())
        cv.set_tool("rect")
        qapp.processEvents()
    return cv


def test_U_key_offsets_the_rect_through_the_canvas(win, qapp, monkeypatch):
    cv = _rect_sketch(win, qapp)
    assert len(cv.model.sketch.lines) == 4
    monkeypatch.setattr("tracer.ui.cmddialog.Shell.getDouble",
                        staticmethod(lambda *a, **k: (-5.0, True)))
    QTest.keyClick(cv, Qt.Key_U)
    qapp.processEvents()
    lines = cv.model.sketch.lines
    assert len(lines) == 8                      # original + mitred twin
    areas = sorted(round(r["area"], 3) for r in cv.model.to_loops()[0])
    assert areas == [600.0, 1200.0]             # the frame's two rings


def test_collapse_warning_leaves_the_sketch_alone(win, qapp, monkeypatch):
    cv = _rect_sketch(win, qapp)
    monkeypatch.setattr("tracer.ui.cmddialog.Shell.getDouble",
                        staticmethod(lambda *a, **k: (-20.0, True)))
    QTest.keyClick(cv, Qt.Key_U)
    qapp.processEvents()
    assert len(cv.model.sketch.lines) == 4      # original untouched
    assert "collapses or flips" in cv._warn_text
    # the refusal pushed NO undo step: a single Ctrl+Z lands back before
    # the rectangle — if the refusal had dirtied history, this would stop
    # at the 4-line pre-offset state instead
    QTest.keyClick(cv, Qt.Key_Z, Qt.ControlModifier)
    qapp.processEvents()
    assert len(cv.model.sketch.lines) == 0


def test_cancel_in_the_dialog_changes_nothing(win, qapp, monkeypatch):
    cv = _rect_sketch(win, qapp)
    monkeypatch.setattr("tracer.ui.cmddialog.Shell.getDouble",
                        staticmethod(lambda *a, **k: (0.0, False)))
    QTest.keyClick(cv, Qt.Key_U)
    qapp.processEvents()
    assert len(cv.model.sketch.lines) == 4


def test_context_menu_offers_offset_with_nothing_selected(win, qapp):
    cv = _rect_sketch(win, qapp)
    cv._sel = []
    labels = [a.text() for a in cv._build_menu().actions()]
    assert any("Offset outline" in t for t in labels)


def test_screenshot_proof(win, qapp, monkeypatch):
    import os
    cv = _rect_sketch(win, qapp)
    monkeypatch.setattr("tracer.ui.cmddialog.Shell.getDouble",
                        staticmethod(lambda *a, **k: (-4.0, True)))
    QTest.keyClick(cv, Qt.Key_U)
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m34_offset.png")
