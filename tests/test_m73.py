"""M73 — The constraint voice: fully / under-constrained, said out loud.

Fusion never leaves you guessing whether a sketch is tamed.  The sketch
toolbar now reads it straight off the LM solver (dof = free variables
minus Jacobian rank), and the browser appends the same verdict to every
sketch node — "(fully constrained)", "(under-constrained)", or the
honest "(⚠ conflicting constraints)" when the numbers fight.  An empty
sketch keeps its mouth shut; a loaded one answers immediately.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from tracer.core.sketch.constraints import Fixed                       # noqa: E402
from tracer.core.sketch.model import SketchModel, model_to_dict        # noqa: E402
from tracer.core.document import ExtrudeFeature                        # noqa: E402


def _rect(dx=40.0, dy=20.0):
    return np.array([[0, 0], [dx, 0], [dx, dy], [0, dy]], float)


def _sketch_items(win):
    out = []

    def walk(node):
        for i in range(node.childCount()):
            ch = node.child(i)
            if ch.text(0).startswith("\u270e"):
                out.append(ch)
            walk(ch)
    walk(win.rail.tree.invisibleRootItem())
    return out


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


# ---- toolbar voice ------------------------------------------------------------------

def test_empty_sketch_stays_silent(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    assert win._sketch_state.text() == ""


def test_toolbar_counts_free_dof_then_declares_fully(win, qapp):
    win.new_document()
    win.action_new_sketch()
    m = win.sketch.model
    a, b = m.point(0.0, 0.0), m.point(30.0, 10.0)
    m.add_line(a, b)
    win.sketch._solve()
    qapp.processEvents()
    t = win._sketch_state.text()
    assert "under-constrained" in t and "4 dof free" in t   # two free pts
    m.constrain(Fixed(a, x=0.0, y=0.0))
    win.sketch._solve()
    qapp.processEvents()
    assert "under-constrained" in win._sketch_state.text()
    assert "2 dof free" in win._sketch_state.text()
    m.constrain(Fixed(b, x=30.0, y=10.0))
    win.sketch._solve()
    qapp.processEvents()
    assert win._sketch_state.text() == "Sketch fully constrained"


def test_conflicting_constraints_get_the_warning_voice(win, qapp):
    win.new_document()
    win.action_new_sketch()
    m = win.sketch.model
    a = m.point(0.0, 0.0)
    m.constrain(Fixed(a, x=0.0, y=0.0))
    m.constrain(Fixed(a, x=5.0, y=5.0))        # the same point, elsewhere
    win.sketch._solve()
    qapp.processEvents()
    assert "conflicting" in win._sketch_state.text()


# ---- browser voice ------------------------------------------------------------------

def _payload(fix_b):
    mm = SketchModel()
    mm.name = "Sketch1"
    a, b = mm.point(0.0, 0.0), mm.point(40.0, 0.0)
    mm.add_line(a, b)
    mm.constrain(Fixed(a, x=0.0, y=0.0))
    if fix_b:
        mm.constrain(Fixed(b, x=40.0, y=0.0))
    return model_to_dict(mm)


def test_browser_appends_constraint_state(win, qapp):
    win.new_document()
    win.doc.add(ExtrudeFeature(name="w", outer=_rect(), height=10.0,
                               sketch=_payload(fix_b=False)))
    win.recompute()
    qapp.processEvents()
    items = _sketch_items(win)
    assert items and all("(under-constrained)" in it.text(0)
                         for it in items)
    assert all("Sketch1" in it.text(0) for it in items)


def test_fully_constrained_payload_says_so_in_the_tree(win, qapp):
    win.new_document()
    win.doc.add(ExtrudeFeature(name="w", outer=_rect(), height=10.0,
                               sketch=_payload(fix_b=True)))
    win.recompute()
    qapp.processEvents()
    items = _sketch_items(win)
    assert items and all("(fully constrained)" in it.text(0)
                         for it in items)


def test_sketches_stay_clickable_with_suffixes(win, qapp):
    # the role data still points at the feature, rename suffix or not
    win.new_document()
    win.doc.add(ExtrudeFeature(name="w", outer=_rect(), height=10.0,
                               sketch=_payload(fix_b=True)))
    win.recompute()
    qapp.processEvents()
    from PySide6.QtCore import Qt
    it = _sketch_items(win)[0]
    assert it.data(0, Qt.UserRole)[0] == "sketch"
