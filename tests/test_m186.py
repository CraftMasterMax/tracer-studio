"""M186 R1: EVERY ENTITY TELLS ITS OWN TRUTH [FD8-LAW-55, documented].

"When sketch geometry is fully constrained, it changes from its initial
color to black" - and the vendor's OWN caption shows the mixed state:
"the blue lines ... are unconstrained" while others already read as
defined. Tracer's flip exists but is WHOLE-SKETCH (paintEvent asks only
`dof == 0`): every line changes ink at the same instant, so the maker
never sees WHICH constraint just earned which entity its color. This
rung makes the truth per-entity: the solver publishes the null-space
mobility of the SIZE variables it already owns (circle radii, ellipse
rx/ry - M119 only sliced the POINT columns), and the canvas answers
`_ent_locked(ent)` - every variable an entity owns at zero mobility.
Black and blue COEXIST mid-solve, exactly like the vendor's figure.
No hex is copied (M160's law): our dark canvas keeps its reserved duo,
SKETCH under=blue / full=white - black there is unreadable ink.
Solver gates are pure math (no Qt); canvas gates ride the house
GL-skip door.
"""
import pytest

pytest.importorskip("PySide6")

import numpy as np                                                   # noqa
from PySide6.QtGui import QColor, QImage                             # noqa
from PySide6.QtWidgets import QApplication                           # noqa
from tracer.ui import theme                                          # noqa

from tracer.core.sketch.solver import Sketch                         # noqa
from tracer.core.sketch.constraints import Fixed, Radius             # noqa


def _fix(s, p, x, y):
    s.constrain(Fixed(p, x=x), Fixed(p, y=y))


@pytest.fixture
def qapp():
    yield QApplication.instance() or QApplication([])


# ---- the solver publishes the SIZE truth it already owns --------------------

def test_a_bare_circle_owns_exactly_one_size_dof():
    s = Sketch()
    c0 = s.point(0, 0)
    c = s.circle(c0, 10)
    _fix(s, c0, 0, 0)
    r = s.solve()
    assert r.point_dof[c0.id] == 0, "the center is pinned"
    assert r.size_dof[c.id] == 1, "ONE number still free: the radius"
    assert r.dof == 1, "the totals agree - sizes count in the bill"


def test_a_dimensioned_radius_reports_zero():
    s = Sketch()
    c0 = s.point(0, 0)
    c = s.circle(c0, 10)
    _fix(s, c0, 0, 0)
    s.constrain(Radius(c, 10))
    r = s.solve()
    assert r.size_dof[c.id] == 0, "center AND size at rest: defined"
    assert r.dof == 0


def test_the_all_float_path_counts_sizes_too():
    s = Sketch()
    c0 = s.point(0, 0)
    e0 = s.point(30, 30)
    c = s.circle(c0, 10)
    e = s.ellipse(e0, 20, 8)
    r = s.solve()
    assert r.size_dof[c.id] == 1, "nothing constrains: radius drifts"
    assert r.size_dof[e.id] == 2, "both ellipse axes drift"
    assert r.dof == 2 + 2 + 1 + 2, "4 pts + 1 r + 2 axes"


# ---- the canvas answers per-entity ------------------------------------------

def _editor(qapp):
    from tracer.core.sketch.model import SketchModel
    from tracer.ui.sketcheditor import SketchCanvas
    cv = SketchCanvas()
    cv.set_model(SketchModel())
    cv.resize(600, 400)
    cv.show()
    for _ in range(3):
        qapp.processEvents()
    return cv


def _two_lines(qapp):
    """a-b pinned (LOCKED), b-c free point (OPEN): the vendor's MIXED
    canvas in three points."""
    cv = _editor(qapp)
    m = cv.model
    a = m.point(-50, -20)
    b = m.point(50, -20)
    c = m.point(0, 40)
    l1 = m.add_line(a, b)
    l2 = m.add_line(b, c)
    _fix(m.sketch, a, -50, -20)
    _fix(m.sketch, b, 50, -20)
    cv._solve()
    return cv, l1, l2, c


def test_locked_and_free_lines_coexist(qapp):
    cv, l1, l2, c = _two_lines(qapp)
    assert cv._ent_locked(l1) is True, \
        "both endpoints at rest - THIS line is already defined"
    assert cv._ent_locked(l2) is False, \
        "a line touching a free point cannot claim the defined ink"
    assert cv._last_result.dof != 0, \
        "the WHOLE truth still says under-constrained - the MIX is the " \
        "law, not a contradiction"


def test_no_witness_fails_open_to_blue(qapp):
    from tracer.core.sketch.model import SketchModel
    from tracer.ui.sketcheditor import SketchCanvas
    cv = SketchCanvas()
    cv.set_model(SketchModel())
    m = cv.model
    ln = m.add_line(m.point(0, 0), m.point(10, 0))
    cv._last_result = None                 # no solve has EVER answered
    assert cv._ent_locked(ln) is False, \
        "no witness, no claim - M167's fail-OPEN law rides the color too"
    cv._solve()
    cv._last_result.point_dof.pop(ln.a.id, None)
    cv._last_result.point_dof.pop(ln.b.id, None)
    assert cv._ent_locked(ln) is False, \
        "a STALE witness that never saw these points fails open too"


def test_a_circle_needs_center_AND_size_to_turn_white(qapp):
    cv = _editor(qapp)
    m = cv.model
    c = m.add_circle(m.point(-40, 10), 20)
    _fix(m.sketch, c.c, -40, 10)
    cv._solve()
    assert cv._ent_locked(c) is False, \
        "a pinned center with a free radius is NOT defined - the whole-" \
        "sketch law and the per-entity law must agree here"
    m.constrain(Radius(c, 20))
    cv._solve()
    assert cv._ent_locked(c) is True, "center + size: now it reads defined"


def test_the_two_truths_never_disagree(qapp):
    cv, l1, l2, c = _two_lines(qapp)
    m = cv.model
    _fix(m.sketch, c, 0, 40)                 # pin the last wanderer
    cv._solve()
    res = cv._last_result
    assert res.dof == 0
    assert cv._ent_locked(l1) and cv._ent_locked(l2), \
        "when the WHOLE sketch reads defined, EVERY entity must read " \
        "defined - one truth, two questions"


# ---- the ink (pixels, not vibes) --------------------------------------------

BLUE = QColor(theme.SKETCH["under"])
WHITE = QColor(theme.SKETCH["full"])


def _grab(cv):
    qi = cv.grab().toImage().convertToFormat(
        QImage.Format.Format_RGBA8888)
    return np.frombuffer(bytes(qi.bits()), np.uint8).reshape(
        qi.height(), qi.width(), 4)[:, :, :3].copy()


def _ink_near(arr, pt, want, tol=90):
    x, y = int(round(pt.x())), int(round(pt.y()))
    win = arr[y - 5:y + 6, x - 5:x + 6].reshape(-1, 3).astype(int)
    d = np.abs(win - np.array([want.red(), want.green(),
                               want.blue()])).sum(axis=1)
    return int((d <= tol).sum())


def test_the_canvas_inks_the_mixed_state(qapp):
    cv, l1, l2, _ = _two_lines(qapp)
    for _ in range(3):
        qapp.processEvents()
    arr = _grab(cv)
    m = cv.model
    mid1 = cv.w2s((m.sketch.lines[0].a.x + m.sketch.lines[0].b.x) / 2,
                  (m.sketch.lines[0].a.y + m.sketch.lines[0].b.y) / 2)
    mid2 = cv.w2s((m.sketch.lines[1].a.x + m.sketch.lines[1].b.x) / 2,
                  (m.sketch.lines[1].a.y + m.sketch.lines[1].b.y) / 2)
    assert _ink_near(arr, mid1, WHITE) >= 2, \
        "the locked line ALREADY wears the defined color mid-solve"
    assert _ink_near(arr, mid2, BLUE) >= 2, \
        "the free line is STILL blue beside it"
    assert _ink_near(arr, mid2, WHITE) < 2, \
        "and it is NOT yet white - the vendor's mixed canvas, in pixels"
