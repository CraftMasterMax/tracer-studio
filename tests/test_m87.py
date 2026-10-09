"""M87 — solver intelligence: redundant & conflicting constraints.

FreeCAD/SolveSpace treat DIAGNOSED constraints as a first-class
feature, and Fusion marks them too: a constraint that repeats what
geometry already knows is REDUNDANT (amber badge), one that fights the
rest of the sketch is CONFLICTING (red badge + the status bar counts
them).  Until now Tracer only said "⚠ conflicting constraints" when the
solve didn't close, with no idea WHICH.

The math: after the solve, the residual Jacobian's rows are swept in
constraint order with Gram-Schmidt — a row living in the span of its
predecessors adds no information and is redundant (the LATER of two
duplicates gets the badge, exactly like FreeCAD).  Rows whose residual
refuses to close are conflicting, mapped back through expand() to the
user constraints that minted them.  DOF math is untouched: this only
NAMES what the rank already knew.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QPainter, QPixmap                    # noqa: E402
from PySide6.QtWidgets import QApplication                             # noqa: E402

from tracer.core.sketch.model import SketchModel                       # noqa: E402
from tracer.core.sketch.solver import Sketch                           # noqa: E402
from tracer.core.sketch.constraints import (Distance, Fixed,           # noqa: E402
                                            Horizontal, Parallel,
                                            Radius, Vertical)


def _rect(s: Sketch, w=40.0, h=30.0):
    a, b = s.point(0, 0), s.point(w, 0)
    c, d = s.point(w, h), s.point(0, h)
    l1 = s.line(a, b)
    l2 = s.line(b, c)
    l3 = s.line(c, d)
    l4 = s.line(d, a)
    return (a, b, c, d), (l1, l2, l3, l4)


# ---------------------------------------------------------------- core math

def test_clean_sketch_diagnoses_nothing():
    s = Sketch()
    (a, b, c, d), (l1, l2, l3, l4) = _rect(s)
    s.constrain(Horizontal(l1), Horizontal(l3), Vertical(l2), Vertical(l4),
                Distance(a, b, 40.0), Distance(b, c, 30.0))
    r = s.solve()
    assert r.redundant == [] and r.conflicting == []


def test_duplicate_constraint_is_redundant():
    s = Sketch()
    (a, b, c, d), (l1, l2, l3, l4) = _rect(s)
    h1 = Horizontal(l1)
    h1b = Horizontal(l1)                      # same thing twice
    s.constrain(h1, h1b)
    r = s.solve()
    assert r.redundant == [h1b]               # the LATER one is blamed
    assert r.conflicting == []


def test_parallel_after_two_horizontals_is_redundant():
    s = Sketch()
    (a, b, c, d), (l1, l2, l3, l4) = _rect(s, 40, 30)
    par = Parallel(l1, l3)
    s.constrain(Horizontal(l1), Horizontal(l3), par)
    r = s.solve()
    assert r.redundant == [par]


def test_conflict_names_the_fighting_constraint():
    s = Sketch()
    a, b = s.point(0, 0), s.point(10, 0)
    ln = s.line(a, b)
    h = Horizontal(ln)
    v = Vertical(ln)                          # endpoints pinned below: the
    s.constrain(Fixed(a, x=0.0, y=0.0), Fixed(b, x=10.0, y=0.0),
                h, v)                         # line can never go vertical
    r = s.solve()
    assert not r.converged
    assert v in r.conflicting                 # the fighter is named
    # LM's least-squares compromise may nick the pins too — the exact
    # blame set is the solver's, but V is always in it and nothing is
    # ever blamed twice (a failing row is never also redundant)
    assert not (set(map(id, r.conflicting)) & set(map(id, r.redundant)))


def test_double_radius_conflict():
    s = Sketch()
    c0 = s.point(0, 0)
    circ = s.circle(c0, 5.0)
    r1 = Radius(circ, 5.0)
    r2 = Radius(circ, 8.0)
    s.constrain(r1, r2)
    r = s.solve()
    assert not r.converged
    assert len(r.conflicting) == 2            # both radii fight
    assert r.redundant == []                  # dependent but BAD: conflict


def test_redundant_does_not_bend_dof():
    s = Sketch()
    (a, b, c, d), (l1, l2, l3, l4) = _rect(s)
    s.constrain(Horizontal(l1), Horizontal(l3), Vertical(l2), Vertical(l4))
    r1 = s.solve()
    s.constrain(Horizontal(l1))               # pile on a duplicate
    r2 = s.solve()
    assert r2.dof == r1.dof                   # naming, not bending
    assert len(r2.redundant) == 1


# -------------------------------------------------------------------- UI

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
        r.close()
    except Exception:
        raise


def _rect_sketch(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    m = cv.model
    a, b = m.point(0, 0), m.point(40, 0)
    c, d = m.point(40, 30), m.point(0, 30)
    l1, l2 = m.add_line(a, b), m.add_line(b, c)
    l3, l4 = m.add_line(c, d), m.add_line(d, a)
    cv._scale = 5.0
    cv._center = None if False else cv._center      # keep pan
    return cv, (l1, l2, l3, l4)


def test_editor_tracks_diagnosis_sets(win, qapp):
    cv, (l1, l2, l3, l4) = _rect_sketch(win, qapp)
    cv.model.sketch.constrain(Horizontal(l1))
    cv.model.sketch.constrain(Horizontal(l1))
    cv._solve()
    qapp.processEvents()
    assert len(cv._redundant) == 1
    assert cv._conflicting == set()


def test_status_bar_counts_redundant(win, qapp):
    cv, (l1, l2, l3, l4) = _rect_sketch(win, qapp)
    cv.model.sketch.constrain(Horizontal(l1))
    cv.model.sketch.constrain(Horizontal(l1))
    cv._solve()
    qapp.processEvents()
    t = win._sketch_state.text()
    assert "1 redundant" in t
    assert "dof free" in t                    # the classic family survives


def test_status_bar_counts_conflicting(win, qapp):
    cv, (l1, l2, l3, l4) = _rect_sketch(win, qapp)
    a = cv.model.sketch.lines[0].a
    b = cv.model.sketch.lines[0].b
    cv.model.sketch.constrain(Fixed(a, x=a.x, y=a.y),
                              Fixed(b, x=b.x, y=b.y))
    cv.model.sketch.constrain(Horizontal(l1))
    cv.model.sketch.constrain(Vertical(l1))   # l1 is truly horizontal
    cv._solve()
    qapp.processEvents()
    t = win._sketch_state.text()
    assert t.startswith("\u26a0")             # the warning family survives
    assert "conflicting constraint" in t      # counted and named (⚠ N ...)


def test_clean_sketch_status_is_untouched(win, qapp):
    # the pinned grammar contract: no diagnosis, old words exactly
    cv, (l1, l2, l3, l4) = _rect_sketch(win, qapp)
    cv.model.sketch.constrain(Horizontal(l1), Horizontal(l3),
                              Vertical(l2), Vertical(l4))
    cv._solve()
    qapp.processEvents()
    assert win._sketch_state.text() == ("Sketch under-constrained "
                                        "\u00b7 4 dof free")


def test_badges_paint_amber_for_redundant(win, qapp):
    import numpy as np
    cv, (l1, l2, l3, l4) = _rect_sketch(win, qapp)
    cv.model.sketch.constrain(Horizontal(l1))
    cv.model.sketch.constrain(Horizontal(l1))     # second: amber
    cv._solve()
    cv.resize(600, 400)
    cv._center = __import__("numpy").array([20.0, 15.0])
    pm = QPixmap(600, 400)
    pm.fill(QColor(20, 20, 24))
    p = QPainter(pm)
    cv._draw_glyphs(p)                            # raises LOUDLY if broken
    p.end()
    cx, cy = 300, 400 / 2 - (0 - 15) * 5.0        # badge at l1's midpoint
    box = [(cx + dx, cy + dy) for dx in (-4, 0, 4) for dy in (-2, 2)]
    hit = False
    img = pm.toImage()
    for x, y in box:
        q = img.pixelColor(int(x), int(y))
        if q.red() > 170 and 110 < q.green() < 220 and q.blue() < 110:
            hit = True
    assert hit, "redundant badge should paint amber"
