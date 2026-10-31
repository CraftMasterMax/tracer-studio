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

Rung 2 splits the marquee by DIRECTION like real Fusion: left->right is
a WINDOW (only fully-inside geometry), right->left a CROSSING (anything
touched); the band wears its meaning (blue border vs green), Ctrl stays
additive both ways, and ellipses - absent from the marquee until today
- ride both tests on their own samples beside the arcs.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, QPoint, Qt               # noqa
from PySide6.QtGui import QImage, QMouseEvent                        # noqa
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


# ---- RUNG 2: WINDOW vs CROSSING -------------------------------------------

def _marquee(ed):
    m = ed.model
    ent = {}
    ent["l_in"] = m.add_line(m.point(0.5, 2), m.point(8.5, 2))
    ent["l_out"] = m.add_line(m.point(6, 2), m.point(24, 2))
    ent["c_in"] = m.add_circle(m.point(4, -4), 1.5)
    ent["c_out"] = m.add_circle(m.point(10, -4), 3.0)
    ent["p_in"] = m.point(5, 5)
    ent["p_out"] = m.point(20, 5)
    ent["e_in"] = m.sketch.ellipse(m.point(3, -1), 1.5, 1.0)
    ent["e_out"] = m.sketch.ellipse(m.point(9.5, -2), 2.0, 1.0)
    ent["a_in"] = m.sketch.arc(m.point(0.8, 5), m.point(2, 5.7),
                               m.point(3.5, 5))
    ent["a_out"] = m.sketch.arc(m.point(7.5, -3), m.point(9.5, -4),
                                m.point(8, -5))
    ed._solve()
    return m, ent


def _band_drag(ed, a_xy, b_xy, ctrl=False, mid=None, qapp=None):
    """press-EMPTY, one big move, release - the marquee's whole life.
    mid(ed) runs while the band is still ALIVE (pixel witness)."""
    mods = Qt.ControlModifier if ctrl else Qt.NoModifier
    a, b = _scr(*a_xy), _scr(*b_xy)
    QTest.mousePress(ed, Qt.LeftButton, mods, a)
    p = QPointF(float(b.x()), float(b.y()))
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.LeftButton, Qt.LeftButton, mods))
    for _ in range(3):
        qapp.processEvents()
    shot = mid(ed) if mid is not None else None
    QTest.mouseRelease(ed, Qt.LeftButton, mods, b)
    for _ in range(3):
        qapp.processEvents()
    return shot


def _grab_px(ed):
    qimg = ed.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(bytes(qimg.bits()), np.uint8).reshape(
        qimg.height(), qimg.width(), 4)[:, :, :3].copy()


def test_window_drag_takes_only_what_is_fully_inside(ed, qapp):
    m, e = _marquee(ed)
    _band_drag(ed, (0, -6), (9, 6), qapp=qapp)      # left->right: WINDOW
    sel = ed._sel
    assert e["l_in"] in sel and e["c_in"] in sel    # whole bboxes IN
    assert e["p_in"] in sel                         #  (a point is its own)
    assert e["l_out"] not in sel                    # one end pokes out
    assert e["c_out"] not in sel                    # circle bulges out...
    assert e["c_out"].c not in sel                  #  centre outside: out
    assert e["l_out"].b not in sel                  #  the far END too
    assert e["l_out"].a in sel                      # inside end: IN (a
    assert e["p_out"] not in sel                    #  point is its bbox)


def test_crossing_drag_takes_everything_it_touches(ed, qapp):
    m, e = _marquee(ed)
    _band_drag(ed, (9, 6), (0, -6), qapp=qapp)      # right->left: CROSS
    sel = ed._sel
    assert e["l_out"] in sel and e["c_out"] in sel  # touching is enough
    assert e["l_in"] in sel and e["c_in"] in sel    # enclosed still IN
    assert e["p_out"] not in sel                    # untouched stays out


def test_the_band_wears_its_direction(ed, qapp):
    _marquee(ed)

    def slate(f):                                   # the dotted WINDOW
        px = f[170:230, 294:342].reshape(-1, 3).astype(int)      # border
        return int(((np.abs(px[:, 0] - 78) <= 6)                   # as
                    & (np.abs(px[:, 1] - 126) <= 8)                # MEASURED
                    & (np.abs(px[:, 2] - 152) <= 8)).sum())

    def grn(f):                                     # the dotted CROSSING
        px = f[170:230, 294:342].reshape(-1, 3).astype(int)       # green
        return int(((px[:, 0] >= 55) & (px[:, 0] <= 100)
                    & (px[:, 1] >= 130) & (px[:, 1] <= 196)
                    & (px[:, 2] >= 90) & (px[:, 2] <= 130)).sum())

    fw = _band_drag(ed, (0, -6), (9, 6), mid=_grab_px, qapp=qapp)
    fc = _band_drag(ed, (9, 6), (0, -6), mid=_grab_px, qapp=qapp)
    assert slate(fw) >= 40 and slate(fc) <= 5       # 76 vs 0 measured
    assert grn(fc) >= 40 and grn(fw) <= 5           # 108 vs 0 measured


def test_ctrl_stays_additive_both_ways(ed, qapp):
    m, e = _marquee(ed)
    _band_drag(ed, (0, -6), (9, 6), qapp=qapp)      # plain WINDOW first
    base = list(ed._sel)
    assert e["l_in"] in base and e["l_out"] not in base
    _band_drag(ed, (9, 6), (0, -6), ctrl=True, qapp=qapp)   # Ctrl CROSS
    sel = ed._sel
    assert e["l_out"] in sel and e["c_out"] in sel  # the crossing ADDED
    for keep in base:                               # and the WINDOW set
        assert keep in sel                          #  is KEPT whole
    _band_drag(ed, (0, -6), (9, 6), qapp=qapp)      # plain again: law of
    assert e["l_out"] not in ed._sel                #  REPLACE unharmed


def test_the_curves_ride_the_split_and_ellipses_join_the_marquee(ed, qapp):
    m, e = _marquee(ed)
    _band_drag(ed, (0, -6), (9, 6), qapp=qapp)
    sel = ed._sel
    assert e["e_in"] in sel                         # ellipse IN a window
    assert e["e_out"] not in sel                    #  (absent till today)
    assert e["a_in"] in sel                         # arc wholly inside
    assert e["a_out"] not in sel                    # arc pokes past x=9...
    assert e["a_out"].a in sel                      #  ...its inside END is
    _band_drag(ed, (9, 6), (0, -6), qapp=qapp)
    sel = ed._sel
    assert e["e_out"] in sel and e["a_out"] in sel  # crossing takes both
    assert e["e_out"].c not in sel                  # centres outside: out

