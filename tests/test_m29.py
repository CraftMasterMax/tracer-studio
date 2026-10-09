"""M29 — regular polygon tool (Y): the hex-nut primitive.

Not a dumb polyline: n shared-endpoint edges + a CONSTRUCTION circumring,
locked by PointOnCircle×n + Equal×(n-1) + one Radius. That is 2n-1
equations on 2n vertex coords, leaving exactly {x, y, spin} — so a drag
rotates a true regular polygon, and double-clicking the ring's R badge
resizes the whole part. The ring itself is guide geometry: the profile
is the polygon, and it extrudes watertight.
"""
import math

import pytest

from tracer.core.sketch.constraints import (Equal, PointOnCircle, Radius)
from tracer.core.sketch.model import (SketchModel, model_from_dict,
                                      model_to_dict)


def _area(m):
    loops, warns = m.to_loops()
    assert len(loops) == 1 and not warns
    return loops[0]["area"]


def _want(n, R):
    return 0.5 * n * R * R * math.sin(2 * math.pi / n)


# ---- kernel -----------------------------------------------------------------

@pytest.mark.parametrize("n", (3, 4, 5, 6, 8))
def test_built_exactly_and_closed_without_the_ring(n):
    m = SketchModel()
    edges = m.add_polygon(0, 0, 5.0, rot=0.7, n=n)
    assert len(edges) == n
    # every vertex on the ring:
    for e in edges:
        assert math.hypot(e.a.x, e.a.y) == pytest.approx(5.0, abs=1e-9)
    assert len(m.sketch.circles) == 1
    assert m.sketch.circles[0].construction is True
    assert _area(m) == pytest.approx(_want(n, 5.0), abs=1e-6)


def test_dof_is_exactly_translation_plus_spin():
    m = SketchModel()
    m.add_polygon(0, 0, 6.0, rot=0.0, n=6)
    res = m.solve()
    assert res.converged
    assert res.dof == 3                     # centre x,y + rotation


def test_drag_rotates_a_true_regular_polygon():
    m = SketchModel()
    edges = m.add_polygon(0, 0, 6.0, rot=0.0, n=6)
    m.solve()
    v0 = edges[0].a
    v0.x, v0.y = 6 * math.cos(0.9), 6 * math.sin(0.9)
    res = m.solve(pins=[v0])
    assert res.residual_norm < 1e-6
    C = m.sketch.circles[0].c
    rs = [math.dist((p.x, p.y), (C.x, C.y)) for p in
          (e.a for e in m.sketch.lines)]
    es = [math.dist((e.a.x, e.a.y), (e.b.x, e.b.y)) for e in m.sketch.lines]
    assert max(rs) - min(rs) < 1e-5          # still concyclic
    assert max(es) - min(es) < 1e-5          # still equilateral
    assert _area(m) == pytest.approx(_want(6, 6.0), abs=1e-4)


def test_editing_the_radius_badge_resizes_the_whole_polygon():
    m = SketchModel()
    m.add_polygon(0, 0, 4.0, rot=0.0, n=5)
    rad = next(c for c in m.sketch.constraints if isinstance(c, Radius))
    rad.value = 9.0
    assert m.solve().converged
    assert _area(m) == pytest.approx(_want(5, 9.0), abs=1e-4)


def test_constraint_signature_and_toggle():
    m = SketchModel()
    edges = m.add_polygon(0, 0, 3.0, rot=0.0, n=6)
    sk = m.sketch
    assert sum(isinstance(c, PointOnCircle) for c in sk.constraints) == 6
    assert sum(isinstance(c, Equal) for c in sk.constraints) == 5
    assert m.has(PointOnCircle, (edges[0].a, sk.circles[0]))
    assert m.toggle(PointOnCircle, (edges[0].a, sk.circles[0])) is False
    assert sum(isinstance(c, PointOnCircle) for c in sk.constraints) == 5


def test_garbage_inputs_build_nothing():
    m = SketchModel()
    assert m.add_polygon(0, 0, 5.0, n=2) == []
    assert m.add_polygon(0, 0, 0.0, n=6) == []
    assert not m.sketch.lines and not m.sketch.circles


def test_polygon_survives_save_roundtrip():
    m = SketchModel()
    m.add_polygon(10, -4, 7.0, rot=0.35, n=7)
    area = _area(m)
    d = model_to_dict(m)
    assert d["circles"][0][2] == 1                    # construction stored
    assert any(c["t"] == "oc" for c in d["constraints"])
    m2 = model_from_dict(d)
    assert m2.sketch.circles[0].construction
    assert sum(isinstance(c, PointOnCircle)
               for c in m2.sketch.constraints) == 7
    assert m2.solve().converged
    assert _area(m2) == pytest.approx(area, abs=1e-4)


def test_legacy_two_field_circle_dict_still_loads():
    m = SketchModel()
    c = m.add_circle(m.point(1, 2), 4.0)
    d = model_to_dict(m)
    d["circles"] = [[e[0], e[1]] for e in d["circles"]]   # pre-M29 file
    m2 = model_from_dict(d)
    assert m2.sketch.circles[0].construction is False
    assert m2.sketch.circles[0].r == pytest.approx(4.0)


def test_extrudes_watertight_to_analytic_volume():
    import numpy as np
    from tracer.core.document import ExtrudeFeature
    m = SketchModel()
    m.add_polygon(0, 0, 8.0, rot=0.0, n=6)
    loops, _ = m.to_loops()
    sol = ExtrudeFeature(name="hex boss",
                         outer=np.asarray(loops[0]["points"]),
                         height=5.0).build()
    assert sol.volume == pytest.approx(_want(6, 8.0) * 5, abs=0.6)
    assert sol.to_trimesh().is_watertight


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
    r.close()


def _click(cv, qapp, wx, wy):
    s = cv.w2s(wx, wy).toPoint()
    QTest.mousePress(cv, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, s, 10)
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, s, 10)
    qapp.processEvents()


def _sketch(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    return win.sketch


def test_Y_key_two_clicks_hexagon(win, qapp):
    cv = _sketch(win, qapp)
    QTest.keyClick(cv, Qt.Key_Y)
    assert cv._tool == "poly"
    _click(cv, qapp, 0, 0)                          # snaps to origin
    _click(cv, qapp, 6, 2)                          # vertex: r, rot
    m = cv.model
    assert len(m.sketch.lines) == 6
    assert len(m.sketch.circles) == 1 and m.sketch.circles[0].construction
    r = m.sketch.circles[0].r            # the ACTUAL snapped-pixel radius
    loops, warns = m.to_loops()
    assert len(loops) == 1 and not warns
    assert loops[0]["area"] == pytest.approx(_want(6, r), abs=1e-3)


def test_number_keys_set_sides_live(win, qapp):
    cv = _sketch(win, qapp)
    QTest.keyClick(cv, Qt.Key_Y)
    QTest.keyClick(cv, Qt.Key_8)
    qapp.processEvents()
    assert cv._poly_n == 8
    _click(cv, qapp, 20, 10)
    _click(cv, qapp, 24, 10)
    assert len(cv.model.sketch.lines) == 8
    # sides count is sticky across polygons (a tool setting, not state)
    _click(cv, qapp, -20, 10)
    _click(cv, qapp, -16, 10)
    assert len(cv.model.sketch.lines) == 16


def test_preview_and_commit_paint_without_crashing(win, qapp):
    cv = _sketch(win, qapp)
    QTest.keyClick(cv, Qt.Key_Y)
    _click(cv, qapp, 0, 0)
    QTest.mouseMove(cv, cv.w2s(4, 3).toPoint())
    cv.update()
    qapp.processEvents()
    win.grab()                                     # dashed ring + n-gon
    _click(cv, qapp, 4, 3)
    qapp.processEvents()
    assert len(cv.model.sketch.lines) == 6


def test_polygon_undo_and_tour_menu_reach(win, qapp):
    cv = _sketch(win, qapp)
    QTest.keyClick(cv, Qt.Key_Y)
    _click(cv, qapp, 10, 10)
    _click(cv, qapp, 14, 10)
    assert len(cv.model.sketch.lines) == 6
    cv.undo_op()
    qapp.processEvents()
    assert not cv.model.sketch.lines
    assert not cv.model.sketch.circles
    cv.set_tool("select")
    cv._sel = []
    assert "Polygon tool" in [a.text() for a in cv._build_menu().actions()]
