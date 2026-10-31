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

_LIVE: list = []


@pytest.fixture(autouse=True)
def _close_live():
    """ROUTING LAW (test_m164's lesson): every SHOWed canvas must CLOSE
    with its test - offscreen windows share the pointer, and a survivor
    steals the next test's moves."""
    yield
    while _LIVE:
        w = _LIVE.pop()
        w.close()
        w.deleteLater()
    QApplication.processEvents()


def _editor(qapp):
    from tracer.core.sketch.model import SketchModel
    from tracer.ui.sketcheditor import SketchCanvas
    cv = SketchCanvas()
    cv.set_model(SketchModel())
    cv.resize(600, 400)
    cv.show()
    for _ in range(3):
        qapp.processEvents()
    _LIVE.append(cv)                       # ROUTING LAW (test_m164):
    return cv                             #  leaked windows steal moves


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


# ---- R2: THE INFERENCE BRAKE [LAW-57, documented] ---------------------------
# "While there is no option to turn off or disable the creation of
# automatic sketch constraints, you may avoid them by holding the CTRL
# key" - and staff wording ties grid snapping into the same brake.
# Tracer already ships the OTHER brakes: Alt silences the whole magnet
# (M120) and Shift is the ortho hand (M173) - the vendor's Shift slot
# is taken by OUR law, so the clone lands where the vendor's TEXT and
# our free key agree: CTRL, held at the moment of drawing, parks the
# GRID candidate and the H/V auto-constraint inference. The endpoint
# magnet is a DIFFERENT brake's business (Alt) and stays strong.

from PySide6.QtCore import QEvent, QPointF, QPoint, Qt, QSettings     # noqa
from PySide6.QtGui import QMouseEvent                                 # noqa
from PySide6.QtTest import QTest                                      # noqa
from PySide6.QtWidgets import QApplication                            # noqa
from tracer.core.sketch.constraints import Horizontal                 # noqa


@pytest.fixture
def ed(qapp):
    QSettings().remove("sketch/grid_snap")        # POLLUTION LAW
    from tracer.core.sketch.model import SketchModel
    from tracer.ui.sketcheditor import SketchCanvas
    e = SketchCanvas()
    e.set_model(SketchModel())
    e.resize(600, 400)
    e.show()
    for _ in range(3):
        qapp.processEvents()
    yield e
    e.close()                              # ROUTING LAW: close what you
    e.deleteLater()                        #  show, or later QtTests lie
    QSettings().remove("sketch/grid_snap")


def _sq2(ed, x, y):
    s = ed.w2s(x, y)
    return QPointF(s.x(), s.y())


def _mmove(ed, x, y, mods):
    p = _sq2(ed, x, y)
    g = QPointF(ed.mapToGlobal(p.toPoint()))
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, g,
                        Qt.LeftButton, Qt.LeftButton, mods))
    for _ in range(2):
        QApplication.processEvents()


def _draw_line(ed, qapp, start, end, mods):
    """House draw grammar (M176): the line CHAINS by clicks - click the
    start, MOVE (the cursor is the endpoint source), click the end.
    `mods` rides the END stroke: that is where inference decides."""
    ed.set_tool("line")
    _mmove(ed, start[0], start[1], Qt.NoModifier)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier,
                     _sq2(ed, *start).toPoint())
    QApplication.processEvents()
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier,
                       _sq2(ed, *start).toPoint())
    for _ in range(2):
        QApplication.processEvents()
    p1 = _sq2(ed, *end)
    g1 = QPointF(ed.mapToGlobal(p1.toPoint()))
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p1, g1,
                        Qt.NoButton, Qt.NoButton, mods))
    for _ in range(2):
        QApplication.processEvents()
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseButtonPress, p1, g1,
                        Qt.LeftButton, Qt.LeftButton, mods))
    for _ in range(2):
        QApplication.processEvents()
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseButtonRelease, p1, g1,
                        Qt.LeftButton, Qt.NoButton, mods))
    for _ in range(3):
        QApplication.processEvents()


def _inferred(ed):
    return [c for c in ed.model.sketch.constraints
            if getattr(c, "src", "") == "inferred"]


def test_the_brake_parks_the_grid(ed, qapp):
    ed.set_grid_snap(True)
    t = ed._snap_target(_sq2(ed, 10.1, 9.9))
    assert t is not None and ed._snap_obj.kind == "grid", \
        "the grid station is offered as you draw"
    ed._brake = True
    assert ed._snap_target(_sq2(ed, 10.1, 9.9)) is None, \
        "Ctrl: the grid candidate is PARKED (staff wording, verbatim)"
    assert ed._snap_obj is None, "no candidate, no glyph"


def test_the_brake_leaves_the_endpoint_magnet_strong(ed, qapp):
    a = ed.model.sketch.point(10, 10)
    ed._brake = True
    assert ed._snap_target(_sq2(ed, 10.1, 9.9)) is a, \
        "the object magnet is Alt's business (M120) - Ctrl does not " \
        "silence the whole magnet"


def test_alt_still_silences_everything_under_the_brake(ed, qapp):
    ed.model.sketch.point(10, 10)
    ed._brake = True
    ed._no_snap = True
    try:
        assert ed._snap_target(_sq2(ed, 10.0, 10.0)) is None
    finally:
        ed._no_snap = False
        ed._brake = False


def test_ctrl_at_release_sends_the_inference_home(ed, qapp):
    ed.set_grid_snap(False)                 # exact endpoints, no magnet
    _draw_line(ed, qapp, (10, 10), (60, 10.35), Qt.ControlModifier)
    ln = ed.model.sketch.lines[0]
    assert _inferred(ed) == [], \
        "'you may avoid them by holding the CTRL key' - the H/V " \
        "auto-constraint stays in its pocket"
    assert ln.b.y == pytest.approx(10.35, abs=0.05), \
        "and the line stays AS DRAWN - no silent flattening"


def test_the_inference_lives_without_the_brake(ed, qapp):
    ed.set_grid_snap(False)
    _draw_line(ed, qapp, (10, 10), (60, 10.35), Qt.NoModifier)
    inf = _inferred(ed)
    assert any(isinstance(c, Horizontal) for c in inf), \
        "the same stroke WITHOUT Ctrl still infers horizontal"
    ln = ed.model.sketch.lines[0]
    assert ln.b.y == pytest.approx(ln.a.y, abs=1e-6), \
        "snapped, recorded - the M120-era law untouched"


def test_the_brake_is_sampled_live_off_the_move(ed, qapp):
    ed.set_tool("line")
    p0 = _sq2(ed, 10, 10)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, p0.toPoint())
    _mmove(ed, 40, 30, Qt.ControlModifier)
    assert ed._brake is True, "Ctrl pressed MID-stroke is seen at once"
    _mmove(ed, 45, 32, Qt.NoModifier)
    assert ed._brake is False, "released mid-stroke, inference returns"
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier,
                       _sq2(ed, 45, 32).toPoint())


def test_select_time_ctrl_never_met_the_brake(ed, qapp):
    sk = ed.model.sketch
    l1 = sk.line(sk.point(0, 0), sk.point(40, 0))
    l2 = sk.line(sk.point(0, 10), sk.point(40, 10))
    ed.set_tool("select")
    QTest.mouseClick(ed, Qt.LeftButton, Qt.ControlModifier,
                     _sq2(ed, 20, 0).toPoint())
    QTest.mouseClick(ed, Qt.LeftButton, Qt.ControlModifier,
                     _sq2(ed, 20, 10).toPoint())
    assert l1 in ed._sel and l2 in ed._sel, \
        "Ctrl at REST still adds to selection - the brake lives ONLY " \
        "in the drawing hand"
