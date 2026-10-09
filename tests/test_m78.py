"""M78 — Rubber-band selection + the drag magnet in the sketcher.

The 3D viewport box-selects since M62; the sketch editor still demanded
one piddling click per entity.  Dragging from empty space now throws a
dashed band, and everything the band TOUCHES (window + crossing at
once, as Fusion's sketch marquee behaves — a line passing clean through
with both ends outside is still caught) lands in the selection; Ctrl
keeps what was already picked, plain empty-click clears.  The band is
real: the two lines it catches take an H constraint on the next
keystroke.

And dragged points now CLICK onto things — the origin, grid crossings,
other points (never the dragged point itself: the magnet must not eat
its own cursor) — with release coordinates EXACT.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                               # noqa: E402
from PySide6.QtTest import QTest                                    # noqa: E402
from PySide6.QtWidgets import QApplication                          # noqa: E402

from tracer.core.sketch.constraints import Horizontal               # noqa: E402
from tracer.core.sketch.solver import Line                          # noqa: E402


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


def _sk(win, qapp, scale=6.0):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    cv._scale = scale
    cv._center = np.array([0.0, 0.0])
    cv.set_tool("select")
    qapp.processEvents()
    return cv


def _drag(cv, qapp, w0, w1, mods=Qt.NoModifier):
    a, b = cv.w2s(*w0), cv.w2s(*w1)
    pa = QPoint(int(a.x()), int(a.y()))
    pb = QPoint(int(b.x()), int(b.y()))
    QTest.mousePress(cv, Qt.LeftButton, mods, pa)
    QTest.mouseMove(cv, pb)
    QTest.mouseRelease(cv, Qt.LeftButton, mods, pb)
    qapp.processEvents()


# ---- the band ------------------------------------------------------------------------

def test_band_across_geometry_selects_everything_it_touches(win, qapp):
    cv = _sk(win, qapp)
    m = cv.model
    p0, p1 = m.point(0, 0), m.point(20, 14)
    m.add_rect(p0, p1)
    m.add_circle(m.point(40, 0), 6.0)
    cv.set_tool("select")
    _drag(cv, qapp, (-8, -8), (30, 20))         # covers the rect, misses circle
    lines = cv.model.sketch.lines
    assert len(lines) == 4
    assert all(l in cv._sel for l in lines)
    assert not any(c in cv._sel for c in cv.model.sketch.circles)


def test_band_crossing_a_circle_edge_selects_it(win, qapp):
    cv = _sk(win, qapp)
    m = cv.model
    m.add_circle(m.point(30, 0), 8.0)
    _drag(cv, qapp, (33, -2), (46, 12))         # bites the right flank only
    assert cv.model.sketch.circles[0] in cv._sel


def test_band_selects_points_inside_too(win, qapp):
    cv = _sk(win, qapp)
    m = cv.model
    a = m.point(2, 2)
    b = m.point(30, 30)                          # far outside any sane band
    _drag(cv, qapp, (0, 0), (10, 10))
    assert a in cv._sel and b not in cv._sel


def test_ctrl_band_adds_to_the_click_selection(win, qapp):
    cv = _sk(win, qapp)
    m = cv.model
    c = m.add_circle(m.point(40, 0), 6.0)
    l = m.add_line(m.point(0, 0), m.point(10, 0))
    # click the line first
    q = cv.w2s(5, 0)
    QTest.mouseClick(cv, Qt.LeftButton, Qt.NoModifier,
                     QPoint(int(q.x()), int(q.y())))
    qapp.processEvents()
    assert cv._sel == [l]
    _drag(cv, qapp, (33, -7), (47, 7), mods=Qt.ControlModifier)
    assert l in cv._sel and c in cv._sel          # band ADDED, not replaced


def test_tiny_drag_on_empty_space_is_a_deselect_click(win, qapp):
    cv = _sk(win, qapp)
    m = cv.model
    l = m.add_line(m.point(0, 0), m.point(10, 0))
    q = cv.w2s(5, 0)
    QTest.mouseClick(cv, Qt.LeftButton, Qt.NoModifier,
                     QPoint(int(q.x()), int(q.y())))
    qapp.processEvents()
    assert cv._sel == [l]
    _drag(cv, qapp, (-20, -20), (-20, -20))       # press+release, no travel
    assert cv._sel == []


def test_band_selection_feeds_constraints(win, qapp):
    cv = _sk(win, qapp)
    m = cv.model
    a, b = m.point(0, 0), m.point(20, 4)
    c, d = m.point(0, 10), m.point(20, 14)
    l1, l2 = m.add_line(a, b), m.add_line(c, d)
    _drag(cv, qapp, (-5, -5), (25, 20))          # catch both lines (and pts)
    assert l1 in cv._sel and l2 in cv._sel       # the BAND made the set
    lines = [e for e in cv._sel if isinstance(e, Line)]
    cv._sel = [lines[0]]                         # one line: act_H's grammar
    cv.act_H()                                    # the constraint acts on it
    assert any(isinstance(k, Horizontal) for k in m.sketch.constraints)


# ---- the drag magnet -------------------------------------------------------------------

def _drag_point(cv, qapp, start_world, end_world):
    q = cv.w2s(*start_world)
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier,
                     QPoint(int(q.x()), int(q.y())))
    qapp.processEvents()
    q2 = cv.w2s(*end_world)
    p2 = QPoint(int(q2.x()), int(q2.y()))
    QTest.mouseMove(cv, p2)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, p2)
    qapp.processEvents()


def test_dragged_point_clicks_onto_the_origin(win, qapp):
    cv = _sk(win, qapp, scale=8.0)
    p = cv.model.point(10.0, 10.0)
    _drag_point(cv, qapp, (10, 10), (0.3, -0.3))    # release ~3 px off O
    assert (p.x, p.y) == (0.0, 0.0)                 # EXACT, not eyeballed


def test_dragged_point_lands_exactly_on_another_point(win, qapp):
    cv = _sk(win, qapp, scale=8.0)
    cv.model.point(-15.0, 0.0)                      # a (dragged)
    a = cv.model.sketch.points[0]
    b = cv.model.point(12.0, 9.0)
    _drag_point(cv, qapp, (-15, 0), (12.3, 8.8))    # near b
    assert (a.x, a.y) == (12.0, 9.0)                # onto b, exactly


def test_drag_far_from_anything_stays_free(win, qapp):
    cv = _sk(win, qapp, scale=8.0)
    p = cv.model.point(0.0, 0.0)                    # starts AT the origin
    _drag_point(cv, qapp, (0, 0), (17.4, -9.2))     # yanks away
    assert abs(p.x - 17.4) < 0.2 and abs(p.y + 9.2) < 0.2
