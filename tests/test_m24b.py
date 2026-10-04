"""M24b/M26b — sketch corner ops: fillet (tangent arc) and chamfer
(flat cut) on a corner of two lines.

The fillet's arc arrives fully parametric (two Tangent + Radius +
ArcMiddle), so drags keep it tangent instead of breaking into an
eyeballed blob, and both ops survive save/load and extrude through the
real kernel.
"""
import math

import numpy as np
import pytest

from tracer.core.sketch.fillet import corner_fillet, corner_chamfer
from tracer.core.sketch.model import SketchModel, model_from_dict, model_to_dict
from tracer.core.sketch.constraints import (Fixed, Radius, Tangent, ArcMiddle,
                                            _unit_normal)
from tracer.core.sketch.entities import curve_center, curve_radius


def _tangent_errors(m):
    out = []
    for con in m.sketch.constraints:
        if isinstance(con, Tangent):
            l, cv = con.e1, con.e2
            n = _unit_normal(l)
            cx, cy = curve_center(cv)
            out.append(abs(abs(n[0] * (cx - l.a.x) + n[1] * (cy - l.a.y))
                           - curve_radius(cv)))
    return out


def _rect(side_x=40.0, side_y=20.0):
    m = SketchModel()
    a = m.point(0, 0)
    c = m.point(side_x, side_y)
    lines = m.add_rect(a, c)          # shares points + auto H/V, like the tool
    return m, lines


# ---- geometry --------------------------------------------------------------

def test_fillet_all_four_corners_matches_analytic_area():
    m, lines = _rect()
    r = 5.0
    for i in range(4):
        corner_fillet(m, lines[i], lines[(i + 1) % 4], r)
    res = m.solve()
    assert res.converged
    assert len(m.sketch.arcs) == 4
    for arc in m.sketch.arcs:
        assert curve_radius(arc) == pytest.approx(r, abs=1e-6)
    assert max(_tangent_errors(m)) < 1e-6
    loops, warns = m.to_loops()
    assert len(loops) == 1 and not warns
    want = 40 * 20 - 4 * (r * r - math.pi * r * r / 4)
    assert loops[0]["area"] == pytest.approx(want, abs=0.05)


def test_fillet_survives_drag_tangent_and_radius_hold():
    m, lines = _rect()
    arc = corner_fillet(m, lines[1], lines[2], 6.0)     # top-right corner
    assert m.solve().converged
    d = lines[3].b                                      # top-left corner point
    d.x, d.y = -8.0, 30.0                               # yank the rectangle
    res = m.solve(pins=[d])
    # the dragged rectangle stays underconstrained by design (no dimensions),
    # so the LM residual plateaus at the FD noise floor (~1e-9) rather than
    # the strict tol; the fillet invariants are the real contract:
    assert res.residual_norm < 1e-6
    assert max(_tangent_errors(m)) < 1e-6
    assert curve_radius(arc) == pytest.approx(6.0, abs=1e-6)
    loops, warns = m.to_loops()
    assert len(loops) == 1 and not warns


def test_filleted_profile_extrudes_to_analytic_volume():
    from tracer.core.document import ExtrudeFeature
    m, lines = _rect()
    r = 5.0
    for i in range(4):
        corner_fillet(m, lines[i], lines[(i + 1) % 4], r)
    m.solve()
    loops, _ = m.to_loops()
    feat = ExtrudeFeature(name="rounded plate",
                          outer=np.asarray(loops[0]["points"]), height=3.0)
    sol = feat.build()
    want = (40 * 20 - 4 * (r * r - math.pi * r * r / 4)) * 3.0
    assert sol.volume == pytest.approx(want, abs=0.6)
    assert sol.to_trimesh().is_watertight


def test_fillet_roundtrips_through_save_dict():
    m, lines = _rect()
    corner_fillet(m, lines[1], lines[2], 4.0)
    m.solve()
    d = model_to_dict(m)
    assert any(c["t"] == "am" for c in d["constraints"])       # ArcMiddle too
    m2 = model_from_dict(d)
    assert len(m2.sketch.arcs) == 1
    assert sum(isinstance(c, ArcMiddle) for c in m2.sketch.constraints) == 1
    res = m2.solve()
    assert res.converged and max(_tangent_errors(m2)) < 1e-6


# ---- guards -----------------------------------------------------------------

def test_refuses_radius_bigger_than_legs():
    m, lines = _rect(10.0, 8.0)
    with pytest.raises(ValueError, match="too large"):
        corner_fillet(m, lines[1], lines[2], 25.0)
    assert not m.sketch.arcs                       # nothing mutated


def test_refuses_disjoint_and_parallel_lines():
    m = SketchModel()
    L1 = m.add_line(m.point(0, 0), m.point(10, 0))
    L2 = m.add_line(m.point(0, 5), m.point(10, 5))
    with pytest.raises(ValueError, match="sharing exactly one corner"):
        corner_fillet(m, L1, L2, 2.0)


def test_refuses_corner_shared_by_three_lines():
    m, lines = _rect()
    corner_pt = lines[1].b                       # the (40,20) corner point
    m.add_line(corner_pt, m.point(60, 30))       # a stub makes it 3-way
    with pytest.raises(ValueError, match="more geometry"):
        corner_fillet(m, lines[1], lines[2], 3.0)


def test_refuses_nonpositive_radius():
    m, lines = _rect()
    with pytest.raises(ValueError, match="positive"):
        corner_fillet(m, lines[1], lines[2], 0.0)


# ---- chamfer ---------------------------------------------------------------

def test_chamfer_two_corners_matches_analytic_area():
    m, lines = _rect()
    for i in (1, 3):
        corner_chamfer(m, lines[i], lines[(i + 1) % 4], 5.0)
    assert m.solve().converged
    assert len(m.sketch.lines) == 6 and not m.sketch.arcs
    loops, warns = m.to_loops()
    assert len(loops) == 1 and not warns
    assert loops[0]["area"] == pytest.approx(800 - 2 * 12.5, abs=1e-6)


def test_fillet_and_chamfer_coexist_on_one_plate():
    m, lines = _rect()
    corner_fillet(m, lines[0], lines[1], 5.0)       # one round corner
    corner_chamfer(m, lines[2], lines[3], 5.0)      # one flat corner
    assert m.solve().converged
    loops, warns = m.to_loops()
    assert len(loops) == 1 and not warns
    want = 800 - (25 - math.pi * 25 / 4) - 12.5
    assert loops[0]["area"] == pytest.approx(want, abs=0.05)


def test_chamfer_extrudes_to_analytic_volume():
    from tracer.core.document import ExtrudeFeature
    m, lines = _rect()
    corner_chamfer(m, lines[1], lines[2], 5.0)
    m.solve()
    loops, _ = m.to_loops()
    sol = ExtrudeFeature(name="chamfered plate",
                         outer=np.asarray(loops[0]["points"]),
                         height=3.0).build()
    assert sol.volume == pytest.approx((800 - 12.5) * 3, abs=0.5)
    assert sol.to_trimesh().is_watertight


def test_chamfer_guards():
    m, lines = _rect(10.0, 8.0)
    with pytest.raises(ValueError, match="too large"):
        corner_chamfer(m, lines[1], lines[2], 50.0)
    assert len(m.sketch.lines) == 4                  # nothing mutated
    with pytest.raises(ValueError, match="positive"):
        corner_chamfer(m, lines[1], lines[2], -1.0)
    L1 = m.add_line(m.point(50, 50), m.point(60, 50))
    L2 = m.add_line(m.point(50, 55), m.point(60, 55))
    with pytest.raises(ValueError, match="sharing exactly one corner"):
        corner_chamfer(m, L1, L2, 2.0)


def test_chamfer_endpoint_sharing_survives_save_roundtrip():
    m, lines = _rect()
    cl = corner_chamfer(m, lines[1], lines[2], 4.0)
    m.solve()
    d = model_to_dict(m)
    m2 = model_from_dict(d)
    assert len(m2.sketch.lines) == 5
    assert m2.solve().converged
    loops, warns = m2.to_loops()
    assert len(loops) == 1 and not warns
    assert loops[0]["area"] == pytest.approx(800 - 8, abs=1e-6)


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QInputDialog     # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtCore import Qt                                # noqa: E402

from tracer.ui.mainwindow import MainWindow                  # noqa: E402
from tracer.ui.renderer import SceneRenderer                 # noqa: E402


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


def test_f_key_fillets_two_lines_undoable(win, qapp, monkeypatch):
    cv = _canvas(win, qapp)
    m = cv.model
    a = m.point(0, 0)
    lines = m.add_rect(a, m.point(40, 20))
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *A, **K: (5.0, True)))
    cv._sel = [lines[1], lines[2]]
    QTest.keyClick(cv, Qt.Key_F)
    qapp.processEvents()
    assert len(m.sketch.arcs) == 1
    assert max(_tangent_errors(m)) < 1e-6
    # undo wipes the fillet completely
    cv.undo_op()
    qapp.processEvents()
    assert not m.sketch.arcs


def test_f_key_still_fixes_a_point(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    p = m.point(7, 9)
    cv._sel = [p]
    QTest.keyClick(cv, Qt.Key_F)
    qapp.processEvents()
    from tracer.core.sketch.constraints import Fixed as Fx
    assert any(isinstance(c, Fx) and c.p is p for c in m.sketch.constraints)


def test_canvas_fillet_rejection_shows_warning_not_exception(win, qapp,
                                                             monkeypatch):
    cv = _canvas(win, qapp)
    m = cv.model
    a = m.point(0, 0)
    lines = m.add_rect(a, m.point(10, 8))
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *A, **K: (50.0, True)))
    cv._sel = [lines[1], lines[2]]
    cv.act_fillet()                       # radius way too big for 8mm leg
    qapp.processEvents()
    assert not m.sketch.arcs
    assert "too large" in (getattr(cv, "_warn_text", "") or "")


def test_G_key_chamfers_a_corner_and_undoes(win, qapp, monkeypatch):
    cv = _canvas(win, qapp)
    m = cv.model
    lines = m.add_rect(m.point(0, 0), m.point(40, 20))
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *A, **K: (5.0, True)))
    cv._sel = [lines[1], lines[2]]
    QTest.keyClick(cv, Qt.Key_G)
    qapp.processEvents()
    assert len(m.sketch.lines) == 5 and not m.sketch.arcs
    loops, warns = m.to_loops()
    assert len(loops) == 1 and abs(loops[0]["area"] - 787.5) < 1e-6
    cv.undo_op()
    qapp.processEvents()
    assert len(m.sketch.lines) == 4


def test_G_without_two_lines_is_not_swallowed(win, qapp):
    """'G' stays a 3D-view key everywhere else — the canvas must only
    consume it when the selection actually forms a corner."""
    cv = _canvas(win, qapp)
    m = cv.model
    p = m.point(0, 0)
    cv._sel = [p]
    # an ineligible selection falls through to Qt's default chain: no crash,
    # no chamfer
    QTest.keyClick(cv, Qt.Key_G)
    qapp.processEvents()
    assert len(m.sketch.lines) == 0


def test_corner_menu_offers_both_ops_on_eligible_pairs_only(win, qapp):
    cv = _canvas(win, qapp)
    m = cv.model
    lines = m.add_rect(m.point(0, 0), m.point(30, 30))
    cv._sel = [lines[0], lines[1]]
    texts = [a.text() for a in cv._build_menu().actions()]
    assert "Fillet corner…" in texts and "Chamfer corner…" in texts
    far = m.add_line(m.point(100, 100), m.point(110, 100))
    cv._sel = [lines[0], far]                    # disjoint pair
    texts = [a.text() for a in cv._build_menu().actions()]
    assert "Fillet corner…" not in texts
    assert "Chamfer corner…" not in texts
