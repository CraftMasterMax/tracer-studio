"""M173 rung 1 - MIDDLE-CLICK ZOOM-FIT (and the fit finally SEES it all).

Fusion's forgotten verb: a middle-button CLICK fits the view; a middle
DRAG pans. The pan half already existed; the click half did NOTHING.
The discrimination is ONE honest number - travel accumulated since the
press - and three pixels decide click from drag (never a timestamp).
fit_view itself was BLIND: it knew only lines and circles, missing the
arc's bulge (which lives beyond its chords), ellipses, and lone points
- the verb arrives with its eyes open. The empty canvas keeps the FILM
LAW: an empty fit resets EXACTLY to scale 4 / centre 0. And navigation
is NOT editing: no undo row, the pick survives, not one byte of
geometry moves.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, QPoint, Qt               # noqa
from PySide6.QtGui import QMouseEvent                                # noqa
from PySide6.QtTest import QTest                                    # noqa
from PySide6.QtWidgets import QApplication                          # noqa

from tracer.core.sketch.model import SketchModel                    # noqa
from tracer.ui.sketcheditor import SketchCanvas                     # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    c = SketchCanvas()
    c.set_model(SketchModel())        # empty once: scale 4 / centre 0 stay
    c.resize(600, 400)
    c._snap_grid = False
    yield c
    c.deleteLater()


def _scr(x, y):
    return QPoint(int(round(300 + 4.0 * x)), int(round(200 - 4.0 * y)))


def _mmove(ed, x, y):
    #  ONE middle-held move: QTest.mouseMove cannot hold buttons (m37)
    p = QPointF(300.0 + 4.0 * x, 200.0 - 4.0 * y)
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.MiddleButton, Qt.MiddleButton, Qt.NoModifier))


def _midclick(ed, x, y):
    QTest.mousePress(ed, Qt.MiddleButton, Qt.NoModifier, _scr(x, y))
    QTest.mouseRelease(ed, Qt.MiddleButton, Qt.NoModifier, _scr(x, y))


def test_middle_click_fits_the_view(ed):
    m = ed.model
    m.add_rect(m.point(-16, -6), m.point(16, 6))
    ed._solve()
    assert ed._scale == pytest.approx(4.0)          # start at film scale
    _midclick(ed, 0, 0)                             # press+release, ZERO
    assert ed._scale == pytest.approx(12.5)         #  travel: a CLICK.
    assert tuple(ed._center) == pytest.approx((0.0, 0.0))   # min(600/48,
    #  400/18): the rect's OWN numbers, 1.5 padding and all.


def test_middle_drag_pans_and_never_fits(ed):
    m = ed.model
    m.add_rect(m.point(-16, -6), m.point(16, 6))
    ed._solve()
    QTest.mousePress(ed, Qt.MiddleButton, Qt.NoModifier, _scr(0, 0))
    _mmove(ed, 6.25, 0)                             # 25 px: the pan rides
    QTest.mouseRelease(ed, Qt.MiddleButton, Qt.NoModifier, _scr(6.25, 0))
    assert ed._scale == pytest.approx(4.0)          # NO fit - it MOVED
    assert ed._center[0] == pytest.approx(-6.25)
    assert ed._center[1] == pytest.approx(0.0)


def test_the_fit_sees_arcs_ellipses_and_lone_points(ed):
    m = ed.model
    m.add_line(m.point(0, 0), m.point(10, 0))       # the old fit knew
    m.sketch.ellipse(m.point(-30, 5), 8.0, 3.0)     #  ONLY this line:
    m.sketch.arc(m.point(4, 20), m.point(5, 26), m.point(6, 20))
    m.point(20, -10)                                # a LONE point
    _midclick(ed, 0, 0)
    # full bbox x -38..20, y -10..26 (bulge and extents and wanderer):
    assert ed._scale == pytest.approx(600.0 / 87.0)  # span 58 * 1.5
    assert ed._center[0] == pytest.approx(-9.0)
    assert ed._center[1] == pytest.approx(8.0)
    # the blind fit would have answered scale 40, centre (5, 0)


def test_navigation_is_not_editing_and_the_empty_fit_is_the_default(ed):
    m = ed.model
    m.add_rect(m.point(-4, -3), m.point(4, 3))
    ed._solve()
    ed._sel = list(m.sketch.lines[:2])
    n_hist = len(ed._hist)
    s = m.sketch
    sig0 = (len(s.points), len(s.lines), len(s.arcs), len(s.circles),
            len(s.ellipses), len(s.constraints))
    _midclick(ed, 1, 1)                             # a LOOK pays NOTHING:
    assert len(ed._hist) == n_hist                  #  no undo row born
    assert (len(s.points), len(s.lines), len(s.arcs), len(s.circles),
            len(s.ellipses), len(s.constraints)) == sig0
    assert ed._sel == list(s.lines[:2])             # the pick SURVIVES
    assert tuple(ed._center) == pytest.approx((0.0, 0.0))
    ed.set_model(SketchModel())                     # empty canvas:
    QTest.mousePress(ed, Qt.MiddleButton, Qt.NoModifier, _scr(0, 0))
    _mmove(ed, 5, 5)                                # wander by panning...
    QTest.mouseRelease(ed, Qt.MiddleButton, Qt.NoModifier, _scr(5, 5))
    assert ed._center[0] == pytest.approx(-5.0)
    _midclick(ed, 5, 5)                             # a click BRINGS BACK
    assert ed._scale == pytest.approx(4.0)          #  the film law:
    assert tuple(ed._center) == pytest.approx((0.0, 0.0))  # exact 4 / 0
