"""M171 rung 1 - THE ARROW KEYS: empty hands SCROLL the view.

The key grammar claims ~30 verbs and not ONE arrow: selected geometry
never nudged, empty-handed keys never scrolled. Fusion answers both;
today the view starts answering. The law of this rung: empty selection +
an arrow = the VIEW steps by a screen-CONSTANT 10 px of world (Shift
x5), the sketch and the history byte-identical - a scroll is not an
edit and must not leave an undo row. While the M90 type-in is armed the
arrows STILL scroll and neither eat nor lose the digit buffer (today any
other key drops the pending - arrows must not). A non-empty selection
PARKS the arrows for rung 2's nudge (honest no-op, nothing moves).

Arrows are NON-PRINTABLE: like F2 before them they stay out of
SKETCH_KEYS - a claim there would be inert dead code.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                               # noqa
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


def _key(ed, k, mods=Qt.NoModifier):
    QTest.keyClick(ed, k, mods)


def _state(m):
    sk = m.sketch
    return (len(sk.points), len(sk.lines), len(sk.constraints),
            [(l.a.x, l.a.y, l.b.x, l.b.y) for l in sk.lines])


def test_empty_handed_arrows_scroll_the_view(ed):
    m = ed.model
    a = m.point(-5, -5); b = m.point(5, 5)
    m.add_line(a, b)
    ed._solve()
    st = _state(m)
    n0 = len(ed._hist)
    c = ed._center.copy()
    _key(ed, Qt.Key_Left)                          # the VIEW shows more
    assert ed._center[0] == pytest.approx(c[0] - 2.5)   #  left: 10px/4
    _key(ed, Qt.Key_Right)                         #   Right brings it back
    assert ed._center[0] == pytest.approx(c[0])
    _key(ed, Qt.Key_Up)
    assert ed._center[1] == pytest.approx(c[1] + 2.5)   #  world y is UP
    _key(ed, Qt.Key_Down)
    assert ed._center[1] == pytest.approx(c[1])
    assert _state(m) == st                         # a scroll is NOT edit...
    assert len(ed._hist) == n0                     #  ...and pays no undo


def test_shift_multiplies_the_step(ed):
    c = ed._center.copy()
    _key(ed, Qt.Key_Right, Qt.ShiftModifier)
    assert ed._center[0] == pytest.approx(c[0] + 12.5)
    c = ed._center.copy()
    _key(ed, Qt.Key_Up, Qt.ShiftModifier)
    assert ed._center[1] == pytest.approx(c[1] + 12.5)


def test_scroll_survives_the_digit_gate(ed):
    m = ed.model
    _key(ed, Qt.Key_R)                             # R arms the rect tool
    assert ed._tool == "rect"
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(-10, 8))
    QTest.mouseMove(ed, _scr(2, -2))               # a rect drag commits...
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(2, -2))
    assert ed._pending is not None                 #  ...and arms type-in
    QTest.keyClick(ed, Qt.Key_5)                   # "5" rides the buffer
    assert ed._num_buf == "5"
    c = ed._center.copy()
    _key(ed, Qt.Key_Left)                          # an arrow scrolls...
    assert ed._center[0] == pytest.approx(c[0] - 10.0 / ed._scale)
    assert ed._num_buf == "5"                      #   ...keeps the digit
    assert ed._pending is not None                 #   ...and the pending


def test_a_selection_parks_the_arrows_for_rung_2(ed):
    m = ed.model
    sk = m.sketch
    p = sk.point(30, 30)
    ed._solve()
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(30, 30))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(30, 30))
    assert ed._sel == [p]
    c = ed._center.copy()
    n0 = len(ed._hist)
    _key(ed, Qt.Key_Right)                         # selection: arrows are
    assert ed._center[0] == pytest.approx(c[0])    #  PARKED (rung 2 owns
    assert (p.x, p.y) == (30.0, 30.0)              #   them tomorrow)
    assert len(ed._hist) == n0


def test_trim_mode_empty_hands_scroll_too(ed):
    _key(ed, Qt.Key_Escape)                        # lay down the trim
    _key(ed, Qt.Key_T)                             #  tool, empty select
    assert ed._tool == "trim"
    c = ed._center.copy()
    n0 = len(ed._hist)
    _key(ed, Qt.Key_Down)
    assert ed._center[1] == pytest.approx(c[1] - 2.5)
    assert ed._tool == "trim"                      # scroll keeps the tool
    assert len(ed._hist) == n0
