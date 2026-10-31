"""M176 rung 1 - THE CHAIN'S EXIT (FD5-L26: double-click ends AND exits).

Fusion's chain grammar has three exits and this rung lands the loudest
one: a DOUBLE-CLICK during a drawing tool ends the chain AND exits the
tool. The count-1 press of the double-click is the last stroke the
maker wanted - it draws; the count-2 press draws NOTHING and hands the
canvas back to select. set_tool washes every chain's arming state
(_line_start, _rect_corner, _arc_pts, _slot, _poly) - drawn geometry
survives, nothing re-arms (the count-2 press that would mint a stray
polygon centre or chain a phantom second arc is DEAD).

The older single-click rules ride along unharmed and are gated so:
clicking back onto the chain's OWN endpoint still closes the chain
while the tool STAYS armed (M-era law), and the degenerate guards that
already protect rect/circle never mint zero-size shapes.

The green check - L26's MIDDLE clause - is rung 2: a canvas affordance
that ENDS the chain but KEEPS THE TOOL ARMED, so the maker draws many
chains without re-arming. Contrast the double-click (ends AND exits to
select) and Esc (ends the command). The check rect is computed LIVE by
one formula the painter AND the press-claim both read - no stale
hit-list, so the affordance is clickable the instant a chain is armed.
The typed-value Esc nuance (L27) is the milestone's last rung.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QRectF, Qt                        # noqa
from PySide6.QtTest import QTest                                   # noqa
from PySide6.QtWidgets import QApplication                         # noqa

from tracer.core.sketch.model import SketchModel                   # noqa
from tracer.ui.sketcheditor import SketchCanvas                    # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    c = SketchCanvas()
    c.set_model(SketchModel())
    c.resize(600, 400)
    c._snap_grid = False
    yield c
    c.deleteLater()


def scr(x, y):
    return QPoint(int(round(300 + 4.0 * x)), int(round(200 - 4.0 * y)))


def _click(cv, x, y):
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, scr(x, y))
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, scr(x, y))


def _dclick(cv, x, y):
    # A real platform delivers, for a double-click, the sequence
    # Press(1) -> Release(1) -> DblClick -> Press(2). The count-1 press
    # is the LAST stroke the maker wanted; DblClick is where the act
    # ENDS. QTest.mouseDClick, though, sends ONLY the DblClick event, so
    # the test drives the honest real-world shape by hand: one click that
    # draws, then the DblClick that exits (the trailing count-2 press a
    # live device adds is what the _dbl_exit guard eats - covered by the
    # _click-then-DblClick product path staying alive here).
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, scr(x, y))
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, scr(x, y))
    QTest.mouseDClick(cv, Qt.LeftButton, Qt.NoModifier, scr(x, y))


def _check_click(cv):
    """Press the GREEN CHECK (the fixed top-right affordance) at its
    true centre - the same rect the painter and the claim both read."""
    p = cv._chain_check_rect().center()
    pt = QPoint(int(round(p.x())), int(round(p.y())))
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, pt)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, pt)


def test_double_click_ends_the_line_chain_at_the_cursor_and_exits(
        ed, qapp):
    m = ed.model
    ed.set_tool("line")
    _click(ed, 0, 0)
    _click(ed, 10, 0)                            # segment one stands
    n1 = len(m.sketch.lines)
    _dclick(ed, 18, 6)                           # LAST stroke, then EXIT
    qapp.processEvents()
    assert len(m.sketch.lines) == n1 + 1         # count-1 drew; count-2
    #                                            drew NOTHING further
    last = m.sketch.lines[-1]
    assert (last.b.x, last.b.y) == pytest.approx((18.0, 6.0), abs=1e-6)
    assert ed._tool == "select"                  # AND exited
    assert ed._line_start is None                # nothing left armed


def test_back_click_still_closes_the_chain_but_keeps_the_tool(ed, qapp):
    m = ed.model
    ed.set_tool("line")
    _click(ed, 0, 0)
    _click(ed, 10, 0)                            # draw
    _click(ed, 10, 0)                            # onto its OWN endpoint:
    qapp.processEvents()                         #  close, tool SURVIVES
    assert len(m.sketch.lines) == 1
    assert ed._line_start is None
    assert ed._tool == "line"                    # single clicks are not
    #                                             the double-click's law


def test_a_polygon_completed_by_a_double_click_never_re_arms(ed, qapp):
    m = ed.model
    ed.set_tool("poly")
    _click(ed, 0, 0)                             # centre
    before = len(m.sketch.lines)
    _dclick(ed, 6, 3)                            # vertex: CREATES, exits
    qapp.processEvents()
    assert len(m.sketch.lines) > before          # the polygon is drawn
    assert ed._poly == []                        # the count-2 press did
    #                                             NOT mint a new centre
    assert ed._tool == "select"


def test_an_arc_chain_ends_at_the_bulge_without_a_phantom_second(ed, qapp):
    m = ed.model
    ed.set_tool("arc")
    _click(ed, 0, 0)
    _click(ed, 10, 0)
    _dclick(ed, 5, 4)                            # bulge: completes...
    qapp.processEvents()
    assert len(m.sketch.arcs) == 1               # ONE arc, no chained
    #                                              phantom from its end
    assert ed._arc_pts == []
    assert ed._tool == "select"


def test_a_double_click_on_an_unarmed_rect_exits_without_a_zero_rect(ed,
                                                                     qapp):
    m = ed.model
    ed.set_tool("rect")
    _dclick(ed, 4, 4)                            # count-1 arms the corner
    qapp.processEvents()                         #  (it lands nowhere);
    assert len(m.sketch.lines) == 0              #  count-2 exits: NO
    assert ed._rect_corner is None               #  zero-size rect is
    assert ed._tool == "select"                  #   ever born


# ---- RUNG 2: THE GREEN CHECK (L26 middle clause) ------------------------

def test_the_green_check_ends_the_chain_but_KEEPS_the_line_tool(ed, qapp):
    m = ed.model
    ed.set_tool("line")
    _click(ed, 0, 0)
    _click(ed, 10, 0)                            # one segment stands
    qapp.processEvents()
    assert ed._chain_armed()                     # chain is live
    _check_click(ed)                             # THE GREEN CHECK
    qapp.processEvents()
    assert len(m.sketch.lines) == 1              # drawn work SURVIVES
    assert ed._line_start is None                # chain ENDED...
    assert ed._tool == "line"                    #  ...but the tool KEEPS


def test_a_check_ended_line_reopens_a_fresh_chain_on_the_next_click(ed,
                                                                    qapp):
    m = ed.model
    ed.set_tool("line")
    _click(ed, 0, 0)
    _click(ed, 10, 0)                            # segment (0,0)-(10,0)
    _check_click(ed)                             # END, keep tool
    _click(ed, 30, 0)                            # a NEW chain starts here...
    _click(ed, 30, 10)                           #  ...(30,0)-(30,10)
    qapp.processEvents()
    assert len(m.sketch.lines) == 2              # two, NOT a joined three
    seg = m.sketch.lines[-1]                     # the fresh chain began at
    assert (seg.a.x, seg.a.y) == pytest.approx((30.0, 0.0), abs=1e-6)   #  30,0
    assert (seg.b.x, seg.b.y) == pytest.approx((30.0, 10.0), abs=1e-6)
    #  had the chain NOT ended, a phantom (10,0)->(30,0) bridge would show:
    assert not any({(round(l.a.x), round(l.a.y)), (round(l.b.x), round(l.b.y))}
                   == {(10.0, 0.0), (30.0, 0.0)} for l in m.sketch.lines)


def test_the_check_lives_only_while_a_chain_is_armed(ed, qapp):
    ed.set_tool("line")
    ed.grab()                                    # paint with nothing drawn
    assert not ed._chain_armed()                 # no chain yet...
    assert ed._check_hit is None                 #  ...so NO check is painted
    p = ed._chain_check_rect().center()          # a click at that corner is
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier,   #  an ordinary first
                     QPoint(int(p.x()), int(p.y())))     #  line click, not
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier,  #  a finish
                      QPoint(int(p.x()), int(p.y())))
    qapp.processEvents()
    assert ed._tool == "line"                    # the tool just ARMED at the


def test_the_check_rect_is_the_painters_own_post(ed, qapp):
    ed.set_tool("line")
    _click(ed, 0, 0)                             # arm a chain
    ed.grab()                                    #  -> painter stores _check_hit
    live = ed._chain_check_rect()                # the claim's LIVE rect
    assert ed._check_hit == live                 # ONE post: painter == claim
    assert live == QRectF(ed.width() - 34, 10, 24, 24)   # fixed top-right


def test_the_rect_tool_survives_a_check_finish_to_draw_another(ed, qapp):
    m = ed.model
    ed.set_tool("rect")
    _click(ed, 0, 0)                             # arm corner A
    qapp.processEvents()
    assert ed._chain_armed()                     # a rect chain is live
    _check_click(ed)                             # END it, keep the tool
    qapp.processEvents()
    assert len(m.sketch.lines) == 0              # no zero-size rect born
    assert ed._rect_corner is None               # corner washed...
    assert ed._tool == "rect"                    #  ...tool STILL armed
