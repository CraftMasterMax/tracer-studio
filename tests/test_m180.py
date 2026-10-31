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
