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


# ---- R3: THE BROWSER WEARS THE RED LOCK [LAW-55, documented] ----------------
# "In the Browser, a red lock displays on the icon next to the sketch
# when it is fully constrained." M73 banked the TEXT of that truth;
# the LOCK itself is the missing pixel. One solve answers both voices
# (the label and the lock can never disagree because they are the same
# answer read once) - and our one red token (SKETCH error) wears it:
# the vendor publishes no hex (M160's law), and no artwork is copied -
# the face is OUR drawn sketch glyph, the badge a drawn padlock.

import tracer.ui.icons as icons                                        # noqa
from PySide6.QtGui import QIcon                                        # noqa
from tracer.core.sketch.model import (SketchModel, model_from_dict,      # noqa
                                      model_to_dict)
from tracer.core.document import ExtrudeFeature                        # noqa

_RED = np.array([QColor(theme.SKETCH["error"]).red(),
                 QColor(theme.SKETCH["error"]).green(),
                 QColor(theme.SKETCH["error"]).blue()])


def _icon_arr(icon):
    pm = icon.pixmap(32, 32)
    img = pm.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(bytes(img.bits()), np.uint8).reshape(32, 32, 4)


def _icon_red(icon):
    a = _icon_arr(icon)
    d = np.abs(a[:, :, :3].astype(int) - _RED).sum(axis=2)
    return int(((d <= 150) & (a[:, :, 3] > 40)).sum())


def _icon_ink(icon):
    return int((_icon_arr(icon)[:, :, 3] > 40).sum())


@pytest.fixture
def win(qapp):
    try:
        from tracer.ui.renderer import SceneRenderer
        from tracer.ui.mainwindow import MainWindow
        try:
            r = SceneRenderer()
        except Exception as e:                 # CI windows: no headless GL
            pytest.skip(f"no headless GL available: {e}")
        w = MainWindow(renderer=r)
        w.resize(1000, 700)
        w.show()
        qapp.processEvents()
        yield w
        w._unsaved = False
        w.close()
        r.close()
    except AttributeError:                     # skip raised inside try
        raise
    finally:
        QApplication.processEvents()


def _r3_rect():
    return np.array([[0, 0], [40, 0], [40, 20], [0, 20]], float)


def _r3_payload(mode):
    mm = SketchModel()
    mm.name = "Sketch1"
    a, b = mm.point(0.0, 0.0), mm.point(40.0, 0.0)
    mm.add_line(a, b)
    mm.constrain(Fixed(a, x=0.0, y=0.0))
    if mode == "full":
        mm.constrain(Fixed(b, x=40.0, y=0.0))
    elif mode == "conflict":
        mm.constrain(Fixed(b, x=40.0, y=0.0))
        mm.constrain(Fixed(b, x=11.0, y=0.0))    # same point, elsewhere
    return model_to_dict(mm)


def _sketch_rows(win):
    out = []

    def walk(node):
        for i in range(node.childCount()):
            ch = node.child(i)
            role = ch.data(0, Qt.UserRole)
            if role and role[0] == "sketch":
                out.append(ch)
            walk(ch)
    walk(win.rail.tree.invisibleRootItem())
    return out


def test_the_lock_lives_only_in_the_locked_icon(qapp):
    off = icons.sketch_icon(locked=False)
    on = icons.sketch_icon(locked=True)
    assert isinstance(off, QIcon) and isinstance(on, QIcon)
    assert _icon_ink(off) > 8 and _icon_ink(on) > 8, \
        "both wear the sketch face - the lock is a badge, not a swap"
    assert _icon_red(off) == 0, "an unlocked icon shows NO red"
    assert _icon_red(on) >= 4, "the locked icon's padlock burns red"


def test_the_browser_locks_a_fully_constrained_sketch(win, qapp):
    win.new_document()
    win.doc.add(ExtrudeFeature(name="w", outer=_r3_rect(), height=10.0,
                               sketch=_r3_payload("full")))
    win.recompute()
    qapp.processEvents()
    rows = _sketch_rows(win)
    assert rows, "the sketch family still lives in the browser"
    for it in rows:
        assert "(fully constrained)" in it.text(0), \
            "M73's text voice rides UNTOUCHED"
        ic = it.icon(0)
        assert not ic.isNull() and _icon_red(ic) >= 4, \
            "and the SAME truth now wears the documented red lock"


def test_the_underconstrained_row_carries_no_lock(win, qapp):
    win.new_document()
    win.doc.add(ExtrudeFeature(name="w", outer=_r3_rect(), height=10.0,
                               sketch=_r3_payload("under")))
    win.recompute()
    qapp.processEvents()
    for it in _sketch_rows(win):
        assert "(under-constrained)" in it.text(0)
        assert not it.icon(0).isNull() and _icon_red(it.icon(0)) == 0, \
            "the face is always honest; the lock is always EARNED"


def test_conflict_is_the_warning_not_the_lock(win, qapp):
    win.new_document()
    win.doc.add(ExtrudeFeature(name="w", outer=_r3_rect(), height=10.0,
                               sketch=_r3_payload("conflict")))
    win.recompute()
    qapp.processEvents()
    for it in _sketch_rows(win):
        assert "conflicting" in it.text(0)
        assert _icon_red(it.icon(0)) == 0, \
            "a red lock would SAY DEFINED - a fighting sketch owns no lie"


def test_the_lock_arrives_with_the_last_constraint(win, qapp):
    win.new_document()
    feat = ExtrudeFeature(name="w", outer=_r3_rect(), height=10.0,
                          sketch=_r3_payload("under"))
    win.doc.add(feat)
    win.recompute()
    qapp.processEvents()
    rows = _sketch_rows(win)
    assert all(_icon_red(it.icon(0)) == 0 for it in rows)
    feat.sketch = _r3_payload("full")            # the last constraint lands
    win.recompute()
    qapp.processEvents()
    rows = _sketch_rows(win)
    assert rows and all(_icon_red(it.icon(0)) >= 4 for it in rows), \
        "the browser answers the LATEST solve, never the last-known one"


def test_a_pin_survives_the_save_as_the_value_it_demanded():
    # R3's fidelity repair: model_to_dict used to write a Fixed from
    # the point's CURRENT POSITION - two pins fighting over one point
    # serialized as two copies of wherever the point sat, and the
    # browser (which solves the stored payload) cheerfully reported
    # the fight as converged. The payload must keep what was DEMANDED.
    mm = SketchModel()
    mm.name = "S"
    a = mm.point(0.0, 0.0)
    mm.constrain(Fixed(a, x=0.0, y=0.0))
    mm.constrain(Fixed(a, x=5.0, y=5.0))          # the honest FIGHT
    back = model_from_dict(model_to_dict(mm))
    xs = sorted(c.x for c in back.sketch.constraints)
    assert xs == [0.0, 5.0], \
        "both demands ride the payload - no silent rewrite of the book"
    r = back.solve()
    assert not r.converged or r.conflicting, \
        "and the solve-from-payload now FEELS the fight"


# ---- R4: THE FIRST RADIUS SCALES WITH THE CORNER [LAW-58 documented] --------
# "The initial fillet preview displays a radius value that is
# PROPORTIONAL TO THE SMALLER of the selected objects." M172's hand
# quartered the shorter leg and then CAPPED it at 5 mm - a 12 mm corner
# and a 1 m corner both opened at R5: a constant wearing a
# proportional name. Quarter the leg and let it grow; the floor keeps
# microscopic corners visible; the kernel's own rmax keeps skinny
# corners inside the steel. ONE mouth - the dialog and the F-ghost
# open with the same number because it is the same answer read once.

import math                                                          # noqa
from tracer.ui.sketcheditor import _corner_default                   # noqa


def test_the_first_radius_scales_with_the_corner():
    assert _corner_default(8.0) == pytest.approx(2.0)     # M172's own
    assert _corner_default(12.0) == pytest.approx(3.0)    #  corner is
    assert _corner_default(20.0) == pytest.approx(5.0)    #  unchanged
    assert _corner_default(80.0) == pytest.approx(20.0)   # where the
    assert _corner_default(400.0) == pytest.approx(100.0)  # cap died
    assert _corner_default(1.0) == pytest.approx(0.5)     # floor: ink
    assert _corner_default(80.0) > _corner_default(40.0), \
        "a bigger corner MUST open bigger - no flat 5 mm lie"


def test_the_armed_ghost_opens_proportional(qapp):
    from tracer.ui.sketcheditor import SketchCanvas
    c = SketchCanvas()
    c.set_model(SketchModel())
    c.resize(600, 400)
    m = c.model
    a = m.point(-80.0, 0.0)
    P = m.point(0.0, 0.0)
    b = m.point(0.0, -80.0)
    l1 = m.add_line(a, P)
    l2 = m.add_line(P, b)
    assert c._corner_arm("fillet", l1, l2)
    assert c._corner[4] == pytest.approx(20.0), \
        "legs of 80 open the ghost at 80/4, not at a capped 5"
    c.deleteLater()


def test_steel_still_clamps_the_skinny_corner(qapp):
    from tracer.ui.sketcheditor import SketchCanvas
    c = SketchCanvas()
    c.set_model(SketchModel())
    c.resize(600, 400)
    m = c.model
    P = m.point(0.0, 0.0)
    t = math.radians(10.0)
    a = m.point(80.0 * math.cos(t), 80.0 * math.sin(t))
    b = m.point(80.0 * math.cos(t), -80.0 * math.sin(t))
    l1 = m.add_line(P, a)
    l2 = m.add_line(P, b)
    assert c._corner_arm("fillet", l1, l2)
    rmax = math.tan(t) * (80.0 / 2.0 - 0.02)      # the kernel's own max
    assert c._corner[4] == pytest.approx(rmax, abs=1e-9), \
        "the proportional ask bows to the geometry: r never outruns" \
        " the legs"
    assert c._corner[4] < 20.0
    c.deleteLater()


def test_the_dialog_opens_at_the_same_proportional_number(qapp,
                                                          monkeypatch):
    from tracer.ui import sketcheditor as sc
    c = sc.SketchCanvas()
    c.set_model(SketchModel())
    c.resize(600, 400)
    m = c.model
    a = m.point(-40.0, 0.0)
    P = m.point(0.0, 0.0)
    b = m.point(0.0, -40.0)
    l1 = m.add_line(a, P)
    l2 = m.add_line(P, b)
    c._sel = [l1, l2]
    seen = {}

    def fake_get_double(parent, title, label, default, mn, mx, dec):
        seen["default"] = default
        return default, True                      # the user just ENTERS

    monkeypatch.setattr(sc.Shell, "getDouble", staticmethod(
        fake_get_double))
    c.act_fillet()
    assert seen.get("default") == pytest.approx(10.0), \
        "the dialog's first number IS the proportional answer"
    arcs = m.sketch.arcs
    rad = [c for c in m.sketch.constraints
           if isinstance(c, Radius)]
    assert len(arcs) == 1 and len(rad) == 1 and \
        rad[0].value == pytest.approx(10.0), \
        "and ENTER files exactly the number the ghost showed"
    c.deleteLater()
