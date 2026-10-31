"""M182 R1 - THE RECTANGLE REMEMBERS WHERE IT IS (FD5-L23 siblings).

The M182 probe caught the rect rubber-band painting at RAW world numbers
used as pixels (a 6x4 speck at the canvas top-left) while the ellipse and
circle branches mapped through w2s - the drag preview was invisible where
the eye waited for it. And no shape spoke its size while drawn. These
gates pin both halves: the band lives at the cursor, and the live W x H
readings ride it, following the hover and dying with the mint - the same
grammar the line tool earned in M180 R1.
"""
import pytest                                                   # noqa

pytest.importorskip("PySide6")                                  # noqa

from PySide6.QtCore import QEvent, QPointF, QPoint, Qt           # noqa
from PySide6.QtGui import QMouseEvent                            # noqa
from PySide6.QtTest import QTest                                 # noqa
from PySide6.QtWidgets import QApplication                       # noqa

from tracer.core.sketch.model import SketchModel                 # noqa
from tracer.ui.sketcheditor import ACCENT, SketchCanvas          # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    c = SketchCanvas()
    c.set_model(SketchModel())
    c.resize(600, 400)
    c._snap_grid = False
    c.show()
    qapp.processEvents()
    yield c
    # M181 POLLUTION LAW: close() BEFORE deleteLater() or a ghost window
    # kills every later module's hover path in this process.
    c.close()
    qapp.processEvents()
    c.deleteLater()


def _move(ed, x, y):
    # QTest.mouseMove cannot hold button state (m37 law) - real event
    p = QPointF(300.0 + 4.0 * x, 200.0 - 4.0 * y)
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.NoButton, Qt.NoButton, Qt.NoModifier))
    ed.update()


def _click(ed, x, y):
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier,
                     QPoint(int(300 + 4.0 * x), int(200 - 4.0 * y)))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier,
                       QPoint(int(300 + 4.0 * x), int(200 - 4.0 * y)))


def _grab(ed):
    from PySide6.QtGui import QImage
    import numpy as np
    qi = ed.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    a = np.frombuffer(bytes(qi.bits()), np.uint8).reshape(
        qi.height(), qi.width(), 4)[:, :, :3]
    return a.copy()


def _white(img, cx, cy, hw=18, hh=9):
    """AA-tolerant WHITE ink (Ubuntu CI font law): glyph cores survive;
    the ACCENT blue (min channel 106) never passes - band and reading
    cannot confuse each other's gates."""
    w = img[max(0, cy - hh):cy + hh,
            max(0, cx - hw):cx + hw].reshape(-1, 3).astype(int)
    return int((w.min(axis=1) > 120).sum())


def _accent(img, x0, x1, y0, y1):
    """ACCENT dashed rubber-band ink inside a screen box. Tolerance 50:
    an AA 1.4px stroke blends to ~(89,152,183) and NEVER hits pure
    ACCENT (106,192,231) - a ±30 box counts only lucky pixels and LIES
    (M182 film law). Grid (69,79,97), bg (46,52,64) and HUD white stay
    outside ±50."""
    w = img[y0:y1, x0:x1].astype(int)
    return int(((abs(w[:, :, 0] - ACCENT.red()) < 50)
                & (abs(w[:, :, 1] - ACCENT.green()) < 50)
                & (abs(w[:, :, 2] - ACCENT.blue()) < 50)).sum())


def _cell(cx, cy):
    """The W (dy -22) / H (dy +4) cell centers the line tool's M180 R1
    grammar paints at cursor screen s: (s.x()+14, s.y()+dy)."""
    return (cx + 14, cy)


# ---- THE BAND: it must live where the cursor is -------------------------

def test_the_rubber_band_lives_where_you_draw_it(ed, qapp):
    ed.set_tool("rect")
    _click(ed, 2.0, 3.0)                        # corner one, pre-mint
    _move(ed, 10.0, 8.0)                        # hover away: band is ON
    qapp.processEvents()
    img = _grab(ed)
    # world (2,3)-(10,8) at scale 4, center 0: x 308..340, y 168..188
    true_px = _accent(img, 304, 344, 164, 192)
    # the M182 probe's WRONG post: drawRect raw world-as-pixels, a speck
    # top-left (the corner numbers themselves, in px)
    raw_px = _accent(img, 0, 12, 0, 14)
    assert true_px >= 8, f"band absent at the cursor ({true_px} px)"
    assert raw_px == 0, f"band still painting raw world-as-pixels " \
                        f"({raw_px} px top-left)"


def test_the_band_REPAINTS_when_the_hover_moves(ed, qapp):
    # M182 R1 film law: the F2 frame caught a dead band at first glance -
    # a move that RE-EXTENDS an already-painted band must repaint it at
    # the NEW span. A still frame is a lie; the band must TRACK every
    # move (root-caused to a lying ±30 color box, not the product - the
    # gate stays as the tracking law it encodes).
    ed.set_tool("rect")
    _click(ed, 2.0, 3.0)
    _move(ed, 10.0, 8.0)                        # first extension: painted
    qapp.processEvents()
    assert _accent(_grab(ed), 304, 344, 164, 192) >= 8
    _move(ed, 14.0, 12.0)                       # RE-extension: must repaint
    qapp.processEvents()
    later = _accent(_grab(ed), 304, 360, 148, 192)
    assert later >= 8, f"band went stale on the second move ({later} px)"


# ---- THE VOICE: live W x H at the cursor (M180 R1 grammar) --------------

def test_the_rectangle_says_width_and_height_live(ed, qapp):
    ed.set_tool("rect")
    _click(ed, 2.0, 3.0)
    _move(ed, 5.0, 5.0)
    qapp.processEvents()
    assert ed._rect_live_wh() == ("3.00", "2.00")
    _move(ed, 1.0, 9.0)                         # it FOLLOWS, live
    qapp.processEvents()
    assert ed._rect_live_wh() == ("1.00", "6.00")


def test_the_readouts_are_pixels_where_the_cursor_is(ed, qapp):
    ed.set_tool("rect")
    wcx, wcy = _cell(320, 158)                  # cursor (5,5) -> s(320,180)
    hcx, hcy = _cell(320, 184)
    img0 = _grab(ed)                            # base: nothing drawn yet
    bw, bh = _white(img0, wcx, wcy), _white(img0, hcx, hcy)
    _click(ed, 2.0, 3.0)
    _move(ed, 5.0, 5.0)
    qapp.processEvents()
    img = _grab(ed)
    wf, hf = _white(img, wcx, wcy), _white(img, hcx, hcy)
    assert wf > 20 and wf > bw + 15, f"W cell white {wf} (base {bw})"
    assert hf > 20 and hf > bh + 15, f"H cell white {hf} (base {bh})"


def test_the_readings_follow_the_hover(ed, qapp):
    ed.set_tool("rect")
    _click(ed, 2.0, 3.0)
    _move(ed, 8.0, 7.0)                         # s = (332,172)
    qapp.processEvents()
    wcx, wcy = _cell(332, 150)
    hcx, hcy = _cell(332, 176)
    img = _grab(ed)
    assert _white(img, wcx, wcy) > 20           # cells rode the cursor
    assert _white(img, hcx, hcy) > 20


def test_the_cells_die_with_the_mint(ed, qapp):
    ed.set_tool("rect")
    _click(ed, 2.0, 3.0)
    _move(ed, 5.0, 5.0)
    n0 = len(ed.model.sketch.lines)
    _click(ed, 5.0, 5.0)                        # COMMIT the rect
    assert len(ed.model.sketch.lines) == n0 + 4
    _move(ed, 12.0, -3.0)                       # fresh cursor post: the
    qapp.processEvents()                        #  readings must NOT rearm
    assert ed._rect_live_wh() == (None, None)
    img = _grab(ed)
    wcx, wcy = _cell(348, 190)                  # s = (348,212)
    hcx, hcy = _cell(348, 216)
    assert _white(img, wcx, wcy) < 8 and _white(img, hcx, hcy) < 8


def test_a_plain_hover_never_whispers(ed, qapp):
    ed.set_tool("rect")
    _move(ed, 6.0, 8.0)                         # hover with NO corner armed
    qapp.processEvents()
    assert ed._rect_live_wh() == (None, None)
    img = _grab(ed)
    wcx, wcy = _cell(324, 146)                  # s = (324,168)
    hcx, hcy = _cell(324, 172)
    assert _white(img, wcx, wcy) < 8 and _white(img, hcx, hcy) < 8


# ---- RUNG 2: THE CELLS TAKE NUMBERS - AND FILE REAL DIMENSIONS ----------
# Deepdive law (official "Create rectangles" + staff, forum 6042363): two
# fields, Tab advances, typing feeds "the length, width, OR BOTH", the
# typed MAGNITUDE rules while the hover still picks the QUADRANT; a value
# tied in at creation is a REAL dimension (staff accepted, forum 10679423).

def _type(ed, s):
    QTest.keyClicks(ed, s)


def _key(ed, k):
    QTest.keyClick(ed, k)


def _arm(ed, x=2.0, y=3.0):
    ed.set_tool("rect")
    _click(ed, x, y)


def _dims_of(ed):
    from tracer.core.sketch.constraints import Distance
    return sorted(round(c.value, 6) for c in ed.model.sketch.constraints
                  if type(c) is Distance)


def _bbox(ed):
    xs = [v for l in ed.model.sketch.lines for v in (l.a.x, l.b.x)]
    ys = [v for l in ed.model.sketch.lines for v in (l.a.y, l.b.y)]
    return (round(min(xs), 6), round(max(xs), 6),
            round(min(ys), 6), round(max(ys), 6))


def test_typing_feeds_the_width_cell(ed, qapp):
    _arm(ed)
    _move(ed, 5.0, 5.0)
    assert ed._rect_live_wh() == ("3.00", "2.00")
    _type(ed, "45")
    assert ed._rect_typed_w == "45"
    assert ed._rect_live_wh() == ("45", "2.00")     # typed OUTRANKS hover


def test_tab_moves_the_focus(ed, qapp):
    _arm(ed)
    _move(ed, 5.0, 5.0)
    _type(ed, "45")
    _key(ed, Qt.Key_Tab)
    assert ed._rect_cell == "h"
    _type(ed, "30")
    assert ed._rect_typed_h == "30"
    assert ed._rect_typed_w == "45"                 # W keeps its number
    assert ed._rect_live_wh() == ("45", "30")


def test_esc_frees_the_live_cell_only(ed, qapp):
    _arm(ed)
    _move(ed, 5.0, 5.0)
    _type(ed, "45")
    _key(ed, Qt.Key_Tab)
    _type(ed, "30")
    _key(ed, Qt.Key_Escape)                         # the M180 R3 law:
    assert ed._rect_typed_h == ""                   #  Esc frees the LIVE
    assert ed._rect_typed_w == "45"                 #  cell, the other stays
    _key(ed, Qt.Key_Escape)                         # empty live cell ->
    assert ed._rect_typed_w == ""                   #  next Esc frees THAT


def test_click_places_typed_size_in_the_hover_quadrant(ed, qapp):
    _arm(ed)
    _move(ed, -6.0, 7.0)                            # up-LEFT of the corner
    _type(ed, "10")
    _key(ed, Qt.Key_Tab)
    _type(ed, "5")
    n0 = len(ed.model.sketch.lines)
    _click(ed, -6.0, 7.0)                           # the click FILES
    assert len(ed.model.sketch.lines) == n0 + 4
    assert _bbox(ed) == (-8.0, 2.0, 3.0, 8.0)       # 2-10, 3+5: magnitude
    assert _dims_of(ed) == [5.0, 10.0]              #  typed, quadrant hover's
    assert ed._pending is None                      #  both numbers filed
    assert ed._tool == "rect"                       #  click keeps the tool
                                                    #   live (docs multi-run)


def test_one_typed_cell_rides_the_other_on_the_hover(ed, qapp):
    _arm(ed)
    _move(ed, -6.0, 7.0)
    _type(ed, "10")                                 # W only
    _click(ed, -6.0, 7.0)
    assert _bbox(ed) == (-8.0, 2.0, 3.0, 7.0)       # H rides the hover (4)
    assert _dims_of(ed) == [10.0]                   #  only the typed dim
    assert ed._pending is not None                  #  stage 1 stands READY
    assert ed._pending_stage == 1                   #   for a late height


def test_enter_places_files_and_ends(ed, qapp):
    _arm(ed)
    _move(ed, -6.0, 7.0)
    _type(ed, "10")
    _key(ed, Qt.Key_Tab)
    _type(ed, "5")
    _key(ed, Qt.Key_Return)                         # staff law: Enter
    assert _bbox(ed) == (-8.0, 2.0, 3.0, 8.0)       #  PLACES...
    assert _dims_of(ed) == [5.0, 10.0]              #  ...FILES...
    assert ed._tool == "select"                     #  ...and ENDS


def test_zero_hover_delta_never_flips_the_sign(ed, qapp):
    _arm(ed)
    _move(ed, 2.0, 7.0)                             # straight UP: dx = 0
    _type(ed, "10")
    _click(ed, 2.0, 7.0)
    assert _bbox(ed) == (2.0, 12.0, 3.0, 7.0)       # the RIGHT by law
    assert _dims_of(ed) == [10.0]


def test_the_typed_cells_wash_with_the_tool(ed, qapp):
    _arm(ed)
    _move(ed, 5.0, 5.0)
    _type(ed, "45")
    _key(ed, Qt.Key_Tab)
    _type(ed, "30")
    ed.set_tool("line")                             # the wash law (M180 R3):
    assert ed._rect_typed_w == ""                   #  swapped tool ->
    assert ed._rect_typed_h == ""                   #   every cell dark
    assert ed._rect_cell == "w"                     #    focus re-homed

