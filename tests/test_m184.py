"""M184 R1: THE SELECTION DRESS CODE (FD8 LAW-49).

"Crossing = DASHED, window = solid... SELECTIONAREAOPACITY = 25"
[documented appearance]. Direction semantics and the two colors landed
in M173; the DRESS did not: both canvases drew dot/dash lines at ~10%
fill. This rung lands ONE shared mouth (marquee_paint) and BOTH
canvases ride it - the drift gate proves it: spy on the mouth and both
bands must ask it the same question.
"""
import pytest

pytest.importorskip("PySide6")

import numpy as np                                                   # noqa
from PySide6.QtCore import QPointF, Qt                               # noqa
from PySide6.QtGui import QColor, QImage                             # noqa
from PySide6.QtWidgets import QApplication                           # noqa

from tracer.ui import theme                                          # noqa
from tracer.ui.marquee import marquee_paint                          # noqa

WIN_HEX = theme.SKETCH["under"]
X_HEX = theme.SKETCH["marquee_x"]


@pytest.fixture
def qapp():
    yield QApplication.instance() or QApplication([])


# ---- the pure mouth ---------------------------------------------------------
def test_window_is_solid_with_a_quarter_fill():
    style, fill = marquee_paint(False, WIN_HEX)
    assert style == Qt.PenStyle.SolidLine, "window = SOLID (LAW-49)"
    assert fill.alpha() == 64, "SELECTIONAREAOPACITY 25 -> 64/255"
    want = QColor(WIN_HEX)
    assert (fill.red(), fill.green(), fill.blue()) == \
        (want.red(), want.green(), want.blue()), "the band's own color"


def test_crossing_is_dashed_with_the_same_fill():
    style, fill = marquee_paint(True, X_HEX)
    assert style == Qt.PenStyle.DashLine, "crossing = DASHED (LAW-49)"
    assert fill.alpha() == 64


# ---- the sketch canvas rides it (pixels, not vibes) -------------------------
def _band_canvas(qapp, a, b):
    from tracer.core.sketch.model import SketchModel
    from tracer.ui.sketcheditor import SketchCanvas
    cv = SketchCanvas()
    cv.set_model(SketchModel())
    cv.resize(600, 400)
    cv._snap_grid = False
    cv.show()
    qapp.processEvents()
    cv._band = [QPointF(*a), QPointF(*b)]
    qapp.processEvents()
    qi = cv.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    arr = np.frombuffer(bytes(qi.bits()), np.uint8).reshape(
        qi.height(), qi.width(), 4)[:, :, :3].copy()
    return cv, arr


def _mask(arr, y, x0, x1, rgb, tol=170):
    """AA law (M182/M173 banked): a 1px edge on integer coords bleeds
    across two rows at ~55/45 - the edge ink measures (85,141,171) vs
    pure (106,192,231), a channel-sum distance of ~132. tol 170 is the
    BLEND band; the un-drawn gap (fill wash only) sits ~275 away."""
    win = arr[y, x0:x1].astype(int)
    return np.abs(win - np.array(rgb, int)).sum(axis=1) <= tol


def _max_run(mask):
    best = run = 0
    for v in mask:
        run = run + 1 if v else 0
        best = max(best, run)
    return best


def test_window_band_edge_runs_SOLID(qapp):
    cv, arr = _band_canvas(qapp, (120, 120), (480, 260))
    col = QColor(WIN_HEX)
    rgb = (col.red(), col.green(), col.blue())
    edge = next((y for y in range(110, 135)
                 if int(_mask(arr, y, 120, 480, rgb).sum()) > 200), None)
    assert edge is not None, "window band top edge found"
    run = _max_run(_mask(arr, edge, 120, 480, rgb))
    print("window edge run", run, "of 360")
    assert run >= 300, "a SOLID edge: one long contiguous run (no dashes)"
    cv.close()
    cv.deleteLater()


def test_crossing_band_edge_is_DASHED_and_green(qapp):
    cv, arr = _band_canvas(qapp, (480, 120), (120, 260))
    col = QColor(X_HEX)
    rgb = (col.red(), col.green(), col.blue())
    edge = next((y for y in range(110, 135)
                 if int(_mask(arr, y, 120, 480, rgb).sum()) > 60), None)
    assert edge is not None, "crossing band top edge found (green ink)"
    mask = _mask(arr, edge, 120, 480, rgb)
    run = _max_run(mask)
    print("crossing edge run", run, "of 360; ink", int(mask.sum()))
    assert run < 120, "a DASHED edge: the dashes break every run"
    assert int(mask.sum()) > 120, "and it is still really drawn"
    cv.close()
    cv.deleteLater()


def test_window_fill_is_a_quarter_of_blue(qapp):
    cv, arr = _band_canvas(qapp, (120, 120), (480, 260))
    inside = arr[180, 250].astype(int)          # interior, OFF the axes
    col = np.array(QColor(WIN_HEX).getRgb()[:3], int)
    bg = arr[5, 5].astype(int)                  # plain canvas background
    for a_bad in (28 / 255, 24 / 255):          # the OLD washes
        pred_bad = bg * (1 - a_bad) + col * a_bad
        assert np.abs(inside - pred_bad).sum() > 12, \
            f"fill must NOT still read the old {a_bad:.0%} wash"
    pred_25 = bg * (1 - 64 / 255) + col * (64 / 255)
    assert np.abs(inside - pred_25).sum() <= 45, \
        f"interior reads the 25% wash (got {inside}, want {pred_25})"
    cv.close()
    cv.deleteLater()


# ---- the 3D viewport rides the SAME mouth -----------------------------------
def test_viewport_rubber_style_folds_the_dress():
    from tracer.ui.viewport import Viewport
    pen, brush = Viewport.rubber_style(True)
    assert pen.style() == Qt.PenStyle.SolidLine, "3D window = solid too"
    assert pen.color().name() == theme.DARK["accent_soft"]
    pen2, brush2 = Viewport.rubber_style(False)
    assert pen2.style() == Qt.PenStyle.DashLine, "3D crossing stays dashed"
    assert pen2.color().name() == theme.DARK["success"]
    assert brush.alpha() == 64 and brush2.alpha() == 64, "25% on BOTH"


# ---- the drift law: BOTH canvases ride THE mouth ----------------------------
def test_both_canvases_ask_the_same_mouth(qapp, monkeypatch):
    from tracer.ui import marquee, sketcheditor                        # noqa
    from tracer.ui import viewport as vp_mod
    calls = []
    real = marquee.marquee_paint

    def spy(crossing, color):
        calls.append(bool(crossing))
        return real(crossing, color)
    monkeypatch.setattr(marquee, "marquee_paint", spy)
    cv, _ = _band_canvas(qapp, (120, 120), (480, 260))     # window band
    vp_mod.Viewport.rubber_style(True)
    vp_mod.Viewport.rubber_style(False)
    cv.close()
    cv.deleteLater()
    assert len(calls) >= 3, \
        f"sketch AND viewport must ask the SAME mouth (saw {calls})"
    assert any(c is False for c in calls), "the window answer was asked"
    assert any(c is True for c in calls), "the crossing answer was asked"


# ---- R2: THE BAND SHOWS ITS TAKE (LAW-49's "otherwise highlighted") --------
# While the band is ALIVE, the entities it currently TAKES must shine -
# Fusion highlights what the window grabs as you sweep. The commit law
# does not move a byte: _band_hits is the SAME mouth the release rides,
# and the preview wears the commit's OWN face (the SEL glow), early.

from PySide6.QtCore import QEvent, QPoint                            # noqa
from PySide6.QtGui import QMouseEvent                                # noqa
from PySide6.QtTest import QTest                                     # noqa
from PySide6.QtWidgets import QApplication                           # noqa


@pytest.fixture
def ed(qapp):
    from tracer.core.sketch.model import SketchModel
    from tracer.ui.sketcheditor import SketchCanvas
    c = SketchCanvas()
    c.set_model(SketchModel())
    c.resize(600, 400)
    c._snap_grid = False
    yield c
    c.close()
    c.deleteLater()


def _scr(x, y):
    return QPoint(int(round(300 + 4.0 * x)), int(round(200 - 4.0 * y)))


def _two_lines(ed):
    m = ed.model
    l1 = m.add_line(m.point(-20, 2), m.point(20, 2))
    l2 = m.add_line(m.point(-20, -2), m.point(20, -2))
    ed._solve()
    return l1, l2


def _drag_live(ed, a_xy, b_xy, mid, qapp):
    """press-EMPTY, move, WITNESS with the band alive, release.
    PICK-RADIUS LAW (learned in red): presses here keep >=20px of air
    from ALL geometry - a press closer GRABS the endpoint and drags
    (the right product behavior, the wrong test)."""
    a, b = _scr(*a_xy), _scr(*b_xy)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, a)
    p = QPointF(float(b.x()), float(b.y()))
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    for _ in range(3):
        qapp.processEvents()
    witness = mid(ed)
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, b)
    for _ in range(3):
        qapp.processEvents()
    return witness


def test_band_hits_is_a_pure_window_mouth(ed):
    l1, l2 = _two_lines(ed)
    got = ed._band_hits(_scr(-30, 4), _scr(30, 1))   # L->R window:
    assert l1 in got and l2 not in got, \
        "the mouth answers ALONE: fully-inside only for a window"


def test_band_hits_is_a_pure_crossing_mouth(ed):
    l1, l2 = _two_lines(ed)
    tight = ed._band_hits(_scr(-30, 3), _scr(30, 3))  # degenerate: misses
    assert l2 not in tight
    win_narrow = ed._band_hits(_scr(-10, -4), _scr(10, 4))
    assert l1 not in win_narrow and l2 not in win_narrow, \
        "L->R narrow WINDOW: both lines poke out - takes NOTHING"
    got = ed._band_hits(_scr(10, 4), _scr(-10, -4))   # SAME box flipped
    assert l1 in got and l2 in got, \
        "R->L CROSSING over the same box: touchers are TAKEN"


def test_drag_previews_takes_without_committing(ed, qapp):
    l1, l2 = _two_lines(ed)

    def witness(c):
        return dict(prev=list(c._band_prev), sel=list(c._sel))
    w = _drag_live(ed, (-30, 4), (30, 1), witness, qapp)
    assert l1 in w["prev"], "the LIVE band shows its take as it drags"
    assert l2 not in w["prev"]
    assert w["sel"] == [], "preview is PREVIEW: the set commits at release"


def test_preview_bows_to_the_direction_law(ed, qapp):
    l1, l2 = _two_lines(ed)
    w_win = _drag_live(ed, (-30, 4), (30, 1),      # WINDOW: l2 below out
                       lambda c: list(c._band_prev), qapp)
    assert l1 in w_win and l2 not in w_win
    ed._sel = []                                    # settle, then CROSS
    w_cross = _drag_live(ed, (10, 10), (-10, -10),  # R->L through middle:
                         lambda c: list(c._band_prev), qapp)   #  both poke
    assert l1 in w_cross and l2 in w_cross, \
        "flipping the drag flips the PREVIEW's law too (same mouth)"


def test_release_clears_the_preview(ed, qapp):
    l1, _ = _two_lines(ed)
    _drag_live(ed, (-30, 4), (30, 1), lambda c: None, qapp)
    assert ed._band_prev == [], \
        "the ghost dies at release - only the COMMITTED set glows"
    assert l1 in ed._sel                            # commit law intact


def test_click_never_paints_a_take(ed, qapp):
    _two_lines(ed)
    a = _scr(-6, 4)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, a)
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, a)
    for _ in range(3):
        qapp.processEvents()
    assert ed._band_prev == [], "a click is not a band - no live take"


def test_the_take_is_frame_cyan(ed, qapp):
    import numpy
    l1, l2 = _two_lines(ed)

    def witness(c):
        qimg = c.grab().toImage().convertToFormat(
            QImage.Format.Format_RGBA8888)
        return numpy.frombuffer(bytes(qimg.bits()), numpy.uint8).reshape(
            qimg.height(), qimg.width(), 4)[:, :, :3].copy()
    F = _drag_live(ed, (-30, 4), (30, 1), witness, qapp)

    def cyan_rows(img, y0, y1):
        best = 0
        for y in range(y0, y1):
            px = img[y, 100:500].astype(int)
            best = max(best, int(((px[:, 2] - px[:, 0]) > 120).sum()))
        return best
    c1 = cyan_rows(F, 189, 196)      # l1's screen row (world y 2)
    c2 = cyan_rows(F, 205, 212)      # l2's screen row (world y -2)
    print("cyan taken", c1, "cyan untouched", c2)
    assert c1 >= 30, "the TAKEN line glows SEL cyan WHILE THE BAND LIVES"
    assert c2 <= 8, "the UNTOUCHED line keeps its base ink"
