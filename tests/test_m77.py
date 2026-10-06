"""M77 — The drawing magnet: origin, sharing, grid.

Fusion never lets a drawing click land on dead air when something is
worth catching.  Now the same grammar runs every tool, not just the
line: existing points first, the sketch origin (the local 0,0 of the
plane) next, and grid intersections when the toolbar's "Snap to grid"
is on — with the hover ring showing WHAT will be caught before the
click, and a crosshair while any draw tool is live.

Snapped corners SHARE the point they caught: a rectangle drawn from an
existing point leaves one Point in the model, so a later drag moves
both shapes together — Fusion's connectivity, not a coincidence of
coordinates.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QSettings, Qt                    # noqa: E402
from PySide6.QtTest import QTest                                    # noqa: E402
from PySide6.QtWidgets import QApplication                          # noqa: E402

from tracer.ui.sketcheditor import SketchCanvas, _HIT_PX            # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _grid_off():
    s = QSettings()                       # the magnet must rest OFF:
    s.setValue("sketch/grid_snap", False)  # other tests' clicks assume it
    s.sync()
    yield


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


def _cv(win, qapp, scale=4.0):
    """Fresh empty XY sketch, canvas at a known scale/centre so screen
    distances are predictable (origin click = w2s(0,0))."""
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    cv._scale = scale
    cv._center = np.array([0.0, 0.0])
    cv.set_tool("select")
    qapp.processEvents()
    return cv


def _click(cv, qapp, x, y, dx=0, dy=0):
    p = cv.w2s(x, y)
    q = QPoint(int(p.x()) + dx, int(p.y()) + dy)
    QTest.mouseClick(cv, Qt.LeftButton, Qt.NoModifier, q)
    qapp.processEvents()


def _pts(m):
    return m.sketch.points


# ---- origin magnet ----------------------------------------------------------

def test_line_first_click_snaps_to_the_origin(win, qapp):
    cv = _cv(win, qapp)
    cv.set_tool("line")
    _click(cv, qapp, 0, 0, dx=3, dy=3)              # 3 px off the origin
    _click(cv, qapp, 30, 22)                        # free air
    assert _pts(cv.model)
    a = min(_pts(cv.model), key=lambda p: p.x * p.x + p.y * p.y)
    assert (a.x, a.y) == (0.0, 0.0)                 # EXACTLY the origin


def test_free_air_stays_free_air(win, qapp):
    cv = _cv(win, qapp)
    cv.set_tool("line")
    _click(cv, qapp, 17, 13)                        # far from everything
    p = _pts(cv.model)[0]
    assert math.hypot(p.x - 17, p.y - 13) * cv._scale <= 1.5   # stays put


# ---- the magnet catches ALL tools (the M77 bug class) -----------------------

def test_rect_corner_reuses_the_point_it_caught(win, qapp):
    cv = _cv(win, qapp)
    p0 = cv.model.point(10.0, 10.0)                 # a lonely existing point
    cv.set_tool("rect")
    _click(cv, qapp, 10, 10, dx=2, dy=2)            # land on it (2 px)
    _click(cv, qapp, 34, 26)
    lines = cv.model.sketch.lines
    assert len(lines) == 4
    assert any(l.a is p0 or l.b is p0 for l in lines)   # SHARED, not cloned
    # and the rectangle actually started at the caught point
    xs = [q.x for l in lines for q in (l.a, l.b)]
    ys = [q.y for l in lines for q in (l.a, l.b)]
    assert min(xs) == 10.0 and min(ys) == 10.0


def test_circle_centre_snaps_to_existing_point(win, qapp):
    cv = _cv(win, qapp)
    c0 = cv.model.point(5.0, 5.0)
    cv.set_tool("circle")
    _click(cv, qapp, 5, 5, dx=2, dy=-2)
    _click(cv, qapp, 5, 18)
    assert len(cv.model.sketch.circles) == 1
    assert cv.model.sketch.circles[0].c is c0       # same Point object


# ---- grid snap ---------------------------------------------------------------

def test_grid_snap_lands_clicks_on_intersections(win, qapp):
    cv = _cv(win, qapp, scale=10.0)                 # step is 1 mm at 10 px
    cv.set_grid_snap(True)
    cv.set_tool("line")
    _click(cv, qapp, 14.6, 7.3)                     # 5 px off (15, 7)
    _click(cv, qapp, -14.6, -7.3)
    a, b = (_pts(cv.model)[0], _pts(cv.model)[1])
    assert (a.x, a.y) == (15.0, 7.0)
    assert (b.x, b.y) == (-15.0, -7.0)


def test_grid_snap_off_leaves_fine_offsets_alone(win, qapp):
    cv = _cv(win, qapp, scale=10.0)
    assert cv._snap_grid is False
    cv.set_tool("line")
    _click(cv, qapp, 14.6, 7.3)
    p = _pts(cv.model)[0]
    assert math.hypot(p.x - 14.6, p.y - 7.3) < 0.2   # NOT (15, 7)


def test_grid_snap_survives_the_session(win, qapp):
    cv = _cv(win, qapp)
    cv.set_grid_snap(True)
    fresh = SketchCanvas(None)                       # reads the same setting
    assert fresh._snap_grid is True
    cv.set_grid_snap(False)
    assert SketchCanvas(None)._snap_grid is False


# ---- the toolbar speaks for the editor --------------------------------------

def test_toolbar_toggle_drives_the_editor(win, qapp):
    cv = _cv(win, qapp)
    assert win._snap_btn.isChecked() == cv._snap_grid
    win._snap_btn.click()
    assert cv._snap_grid is True
    win._snap_btn.click()
    assert cv._snap_grid is False


# ---- hover ring + cursor (the feel) ------------------------------------------

def test_hover_shows_the_magnet_before_the_click(win, qapp):
    cv = _cv(win, qapp)
    cv.set_tool("line")
    q = cv.w2s(0, 0)
    QTest.mouseMove(cv, QPoint(int(q.x()) + 3, int(q.y()) - 3))
    qapp.processEvents()
    assert cv._snap_hint is not None
    hx, hy = (cv._snap_hint.x, cv._snap_hint.y) \
        if hasattr(cv._snap_hint, "x") else cv._snap_hint
    assert (hx, hy) == (0.0, 0.0)                    # the origin is caught


def test_draw_tools_wear_the_crosshair(win, qapp):
    cv = _cv(win, qapp)
    cv.set_tool("line")
    assert cv.cursor().shape() == Qt.CrossCursor
    cv.set_tool("rect")
    assert cv.cursor().shape() == Qt.CrossCursor
    cv.set_tool("select")
    assert cv.cursor().shape() == Qt.ArrowCursor
