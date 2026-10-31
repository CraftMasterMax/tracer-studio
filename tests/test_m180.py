"""M180 R1 - THE RULER SPEAKS WHILE YOU DRAW (FD5-L23).

Fusion shows a live LENGTH readout riding the cursor the instant a line
starts rubber-banding - the number is there BEFORE the click that commits,
so the hand sizes the line by eye AND by digits of the same field. The
kernel already had everything but the voice: _line_start is the pre-mint
anchor, mouseMoveEvent already tracks the hover - only the readout was
never painted. These gates pin the reading itself: live at the cursor,
gone when the drag ends, and honest pixels, not a hidden attribute.
"""
import pytest                                                   # noqa

pytest.importorskip("PySide6")                                  # noqa

from PySide6.QtCore import (QEvent, QPointF, QPoint,           # noqa
                            Qt)
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import math                                                   # noqa

import pytest                                                  # noqa

from tracer.core.sketch.constraints import Distance            # noqa
from tracer.core.sketch.model import SketchModel                # noqa
from tracer.ui.sketcheditor import SketchCanvas                 # noqa


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
    c.deleteLater()


def _move(ed, x, y):
    #  QTest.mouseMove cannot hold button state (m37 law) - send a real
    p = QPointF(300.0 + 4.0 * x, 200.0 - 4.0 * y)                 # event
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.NoButton, Qt.NoButton, Qt.NoModifier))


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
    """AA-tolerant WHITE ink: glyph cores survive any platform font -
    #e1e1e1 blended 50/50 with bg2 is still ~130 (Ubuntu CI law: a gate
    tuned to one machine's font is tuned to NO machine)."""
    w = img[max(0, cy - hh):cy + hh,
            max(0, cx - hw):cx + hw].reshape(-1, 3).astype(int)
    return int((w.min(axis=1) > 120).sum())


def test_the_rubber_band_carries_a_live_length(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0.0, 0.0)                      # the ANCHOR click (pre-mint)
    assert ed._line_start is not None         #  nothing minted yet
    assert len(ed.model.sketch.lines) == 0
    _move(ed, 6.0, 8.0)                       # hover away: rubber-band is ON
    qapp.processEvents()
    assert ed._line_live_text() == "10.00"    # THE READING, at the cursor
    _move(ed, 1.0, 1.0)
    assert ed._line_live_text().startswith("1.41")   # it FOLLOWS, live


def test_the_readout_is_pixels_where_the_cursor_is(ed, qapp):
    ed.set_tool("line")
    _move(ed, 0.0, 0.0)
    base = _white(_grab(ed), 352, 168)         # the future chip's band
    _click(ed, 0.0, 0.0)
    _move(ed, 6.0, 8.0)                        # cursor -> widget (324,168)
    qapp.processEvents()
    field = _white(_grab(ed), 324 + 22, 168 - 14)
    assert field > 20 and field > base + 15    # RELATIVE white: the reading


def test_the_reading_dies_with_the_drag(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0.0, 0.0)
    _move(ed, 6.0, 8.0)
    assert ed._line_live_text() == "10.00"
    n0 = len(ed.model.sketch.lines)
    _click(ed, 6.0, 8.0)                       # COMMIT the line
    assert len(ed.model.sketch.lines) == n0 + 1
    _move(ed, 9.0, 2.0)                        # the CHAIN re-arms from the
    assert len(ed.model.sketch.lines) == n0 + 1   #  endpoint... but HOVER
    assert ed._line_live_text() != "10.00"     #  never re-speaks the OLD


def test_a_plain_hover_never_whispers(ed, qapp):
    ed.set_tool("line")
    _move(ed, 6.0, 8.0)                        # hover with NO anchor click
    assert ed._line_start is None
    assert ed._line_live_text() is None        # rubber-band off -> no field


# ---- RUNG 2: THE TYPED NUMBER SIZES THE LEG (Fusion's cell grammar) ----

def _key(ed, k):
    QTest.keyClick(ed, k)


def test_typing_becomes_the_reading(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0.0, 0.0)
    _move(ed, 6.0, 8.0)
    assert ed._line_live_text() == "10.00"
    QTest.keyClicks(ed, "7.5")                       # the FIELD takes over
    assert ed._line_live_text() == "7.5"              # the TYPED truth, not
    assert len(ed.model.sketch.lines) == 0            #  the recomputed hover


def test_click_places_at_the_typed_length_as_a_real_dimension(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0.0, 0.0)
    _move(ed, 10.0, 0.0)                             # pure +X ray
    QTest.keyClicks(ed, "4")
    _click(ed, 10.0, 0.0)                            # PLACE (Fusion: click)
    assert len(ed.model.sketch.lines) == 1
    ln = ed.model.sketch.lines[0]
    assert ln.b.x == pytest.approx(4.0, abs=1e-6)    # typed length ALONG
    assert ln.b.y == pytest.approx(0.0, abs=1e-6)    #   THE CURSOR RAY
    _key(ed, Qt.Key_Return)                          # Enter FILES the dim
    dim = [c for c in ed.model.sketch.constraints
           if isinstance(c, Distance)
           and {c.p, c.q} == {ln.a, ln.b}]           #  a REAL parametric
    assert len(dim) == 1 and dim[0].value == pytest.approx(4.0)
    assert ed._tool == "select"                      #  (M177's grammar)


def test_enter_completes_the_tool_after_a_typed_number(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0.0, 0.0)
    _move(ed, 6.0, 8.0)
    QTest.keyClicks(ed, "7.5")
    _key(ed, Qt.Key_Return)                          # ENTER = PLACE + DONE
    assert len(ed.model.sketch.lines) == 1           # the number PLACED
    ln = ed.model.sketch.lines[0]                    #  its leg, along the
    assert math.hypot(ln.b.x - ln.a.x, ln.b.y - ln.a.y) \
        == pytest.approx(7.5, abs=1e-6)              #   cursor's RAY
    assert ed._tool == "select"                      # the TOOL is done
    assert ed._line_live_text() is None              # the voice goes quiet


def test_esc_surrenders_the_number_not_the_drag(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0.0, 0.0)
    _move(ed, 6.0, 8.0)
    QTest.keyClicks(ed, "7.5")
    _key(ed, Qt.Key_Escape)                          # the FIELD lets go...
    assert len(ed.model.sketch.lines) == 0           # ...no line was born
    assert ed._line_live_text() == "10.00"           # cursor reading again
    assert ed._line_start is not None                # the drag is ALIVE


# ---- RUNG 3: THE SECOND CELL - ANGLE, AND TAB TOGGLES THE CELLS ----

def test_the_angle_cell_follows_the_cursor(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0.0, 0.0)
    _move(ed, 6.0, 8.0)                            # atan2(8,6) = 53.13 deg
    assert ed._line_live_angle() == "53.1"
    _move(ed, -6.0, 8.0)                           # quadrant II
    assert ed._line_live_angle() == "126.9"
    _move(ed, 0.0, -5.0)                           # straight down = 270
    assert ed._line_live_angle() == "270.0"


def test_tab_toggles_which_cell_the_digits_enter(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0.0, 0.0)
    _move(ed, 6.0, 8.0)
    QTest.keyClicks(ed, "7.5")                     # LENGTH cell
    assert ed._line_live_text() == "7.5"
    _key(ed, Qt.Key_Tab)                           # the staff law: Tab
    assert ed._line_cell == "ang"                  #  TOGGLES the cells
    QTest.keyClicks(ed, "30")                      # now digits feed angle
    assert ed._line_live_angle() == "30"
    assert ed._line_live_text() == "7.5"           # the length holds its own


def test_a_typed_angle_rotates_the_placed_leg(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0.0, 0.0)
    _move(ed, 10.0, 0.0)                           # hover: ray 0 deg, len 10
    _key(ed, Qt.Key_Tab)                           # straight to the angle
    QTest.keyClicks(ed, "90")                      # type 90 degrees
    _click(ed, 10.0, 0.0)                          # PLACE: 10 long UP
    ln = ed.model.sketch.lines[0]
    assert ln.b.x == pytest.approx(0.0, abs=1e-6)
    assert ln.b.y == pytest.approx(10.0, abs=1e-6)
    _key(ed, Qt.Key_Return)                        # FILE the pair + done
    ang = [c for c in ed.model.sketch.constraints
           if type(c).__name__ == "Angle" and c.line is ln]
    assert len(ang) == 1
    assert math.degrees(ang[0].measured()) == pytest.approx(90.0, abs=1e-3)
    assert ed._tool == "select"


def test_esc_surrenders_only_the_live_cell(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0.0, 0.0)
    _move(ed, 6.0, 8.0)
    QTest.keyClicks(ed, "7.5")                     # length typed
    _key(ed, Qt.Key_Tab)
    QTest.keyClicks(ed, "30")                      # angle typed too
    _key(ed, Qt.Key_Escape)                        # Esc: the ANGLE lets go
    assert ed._line_live_angle() == "53.1"         #  hover reading returns
    assert ed._line_live_text() == "7.5"           # the LENGTH cell KEEPS
    assert ed._line_start is not None              # the drag still lives
