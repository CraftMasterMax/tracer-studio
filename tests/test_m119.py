"""M119 — the degrees-of-freedom overlay.

Fusion shows constraint status by colour and begs to show WHERE the
remaining motion is — the forums never got the feature
[fusion_kernel_architecture §3, threads 6803824/10057799]. Tracer's
solver answers the kinematic question exactly: the null space of the
final Jacobian, projected into each point's two coordinates, IS the
set of motions still allowed. These tests pin that truth; the canvas
just draws it.
"""
import pytest

pytest.importorskip("PySide6")

from tracer.core.sketch.solver import Sketch                      # noqa: E402
from tracer.core.sketch.constraints import (Coincident, Distance,  # noqa: E402
                                            Fixed, PointOnLine)


def _fix(s, p, x, y):
    s.constrain(Fixed(p, x=x), Fixed(p, y=y))


# ---- the analysis (headless) ------------------------------------------------
def test_unconstrained_sketch_every_point_floats():
    s = Sketch()
    a, b = s.point(0, 0), s.point(10, 0)
    s.line(a, b)
    r = s.solve()
    assert r.dof == 4
    assert r.point_dof[a.id] == 2 and r.point_dof[b.id] == 2


def test_pinned_base_leaves_only_the_apex_free():
    s = Sketch()
    a, b, c = s.point(0, 0), s.point(50, 0), s.point(25, 40)
    s.line(a, b), s.line(b, c), s.line(c, a)
    _fix(s, a, 0, 0)
    _fix(s, b, 50, 0)
    r = s.solve()
    assert r.dof == 2
    assert r.point_dof[a.id] == 0 and r.point_dof[b.id] == 0
    assert r.point_dof[c.id] == 2


def test_fully_constrained_line_reports_zero_everywhere():
    s = Sketch()
    a, b = s.point(0, 0), s.point(30, 0)
    s.line(a, b)
    _fix(s, a, 0, 0)
    _fix(s, b, 30, 0)
    s.constrain(Distance(a, b, 30.0))
    r = s.solve()
    assert r.converged and r.dof == 0
    assert all(v == 0 for v in r.point_dof.values())
    assert r.free_dirs == {}


def test_point_on_a_pinned_line_slides_in_exactly_one_direction():
    s = Sketch()
    la, lb, p = s.point(0, 0), s.point(10, 0), s.point(5, 0.5)
    ln = s.line(la, lb)
    _fix(s, la, 0, 0)
    _fix(s, lb, 10, 0)
    s.constrain(PointOnLine(p, ln))
    r = s.solve()
    assert r.dof == 1
    assert r.point_dof[la.id] == 0 and r.point_dof[lb.id] == 0
    assert r.point_dof[p.id] == 1
    dx, dy = r.free_dirs[p.id]
    assert abs(dx) == pytest.approx(1.0, abs=1e-6)   # the slide is +/−x
    assert abs(dy) < 1e-6


def test_coincident_pair_moves_as_one():
    # chain a-b-c with a pinned: b and c hinge — 2 params free, both
    # endpoints of the free links must report motion
    s = Sketch()
    a, b = s.point(0, 0), s.point(20, 0)
    c, d = s.point(20, 20), s.point(0, 20)
    s.line(a, b), s.line(c, d)
    _fix(s, a, 0, 0)
    s.constrain(Coincident(b, c))
    r = s.solve()
    assert r.converged
    assert r.point_dof[a.id] == 0
    assert r.point_dof[b.id] >= 1 and r.point_dof[c.id] >= 1
    assert r.point_dof[d.id] >= 1


# ---- the canvas (Qt, offscreen) ----------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(qapp):
    from tracer.core.sketch.model import SketchModel
    from tracer.ui.sketcheditor import SketchCanvas
    ed = SketchCanvas()
    ed.set_model(SketchModel())
    yield ed
    ed.deleteLater()


def _tri(editor):
    sk = editor.model.sketch
    a, b, c = sk.point(0, 0), sk.point(50, 0), sk.point(25, 40)
    sk.line(a, b), sk.line(b, c), sk.line(c, a)
    sk.constraints += [Fixed(p=a, x=0.0), Fixed(p=a, y=0.0)]
    return a, b, c


def test_toggle_moves_the_flag_and_summarises(editor, qapp):
    _tri(editor)
    editor._solve()
    editor.set_show_dof(True)
    assert editor._show_dof is True
    summ = editor.dof_summary()
    assert "free point" in summ and "dof" in summ
    pix = editor.grab()                        # the pass must actually paint
    assert not pix.isNull()
    editor.set_show_dof(False)
    assert editor._show_dof is False


def test_empty_sketch_summary_does_not_crash(editor, qapp):
    editor.set_show_dof(True)
    editor._solve()
    assert isinstance(editor.dof_summary(), str)
    editor.grab()


def test_the_menu_offers_the_overlay_with_live_state(editor, qapp):
    _tri(editor)                             # geometry: the entry appears
    editor._sel = []
    menu = editor._build_menu()
    acts = {a.text(): a for a in menu.actions() if a.isCheckable()}
    assert "Show degrees of freedom" in acts
    a = acts["Show degrees of freedom"]
    assert a.isChecked() == editor._show_dof
    a.trigger()                              # menu is the switch
    assert editor._show_dof is True
