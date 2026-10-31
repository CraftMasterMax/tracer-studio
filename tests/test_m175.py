"""M175 rung 1 - THE DIMENSION FOLLOWS THE CURSOR (act one: the modal dies).

FD5 LAW 35's opening clause: pick the entity, the dimension appears and
value input opens IMMEDIATELY (Enter keeps it). The product answered
that verb with a MODAL QInputDialog - the one panel Fusion has never
had. act_dim now BIRTHS the dimension at the geometry's own measurement
(the same remove_last honesty M90 kept) and opens the INLINE chip
editor on the newborn: pick, dim, type, Enter - never a dialog. The
dialect from M174 rides at birth: a circle's chip already speaks
diameter, so the typed number is halved into core by the very same
commit every other edit pays; arcs keep radius. Re-dimming still never
stacks. The witnesses patch the old door to RAISE - a rung whose
headline is "the dialog is dead" proves it by trying to open one.

Rung 2 puts the FD5-L35 MIDDLE clause on the mouse: between the verb
and the answer the dimension FOLLOWS THE CURSOR - the newborn's chip
(chips are real from birth: value, solver, ledger row all spent) tracks
the free pointer until a press PLACES it, and only then does the value
field open on the settled chip. That press is claimed absolutely - no
selection touched, no band, no geometry grab. A click near the default
post PARKS the label at home EXACTLY, so the bytes still read "never
moved". And Esc (or walking to another tool) UNBIRTHS the un-placed
dimension: the birth row is spent back, coordinates byte-identical -
the act leaves zero trace at both of its ends.

Rung 3 buries the LAST dim modal: act_angle answered FD5-L35 with a
QInputDialog too, and now the angle is BORN speaking its own opening
(one line: from +X; two lines: between) and rides the very same place
rails - follows the cursor, clicks to rest into the degrees field, Esc
unbirths. snapped() turned out to be a branch picker, not a grid round,
so birth-at-measurement is exact: the newborn never drags the geometry
it was measured from. The angle's post is the painter's OWN arc label
(_dim_anchor_screen learned it), and the I key's two witnesses in m24
migrated to the seam - the combo seat m175 lost the first time (keys
are mouths) is now permanent.
"""
import json
import math
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt                      # noqa
from PySide6.QtGui import QMouseEvent                               # noqa
from PySide6.QtTest import QTest                                    # noqa
from PySide6.QtWidgets import QApplication                          # noqa

from tracer.core.sketch.constraints import (Angle, AngleBetween,    # noqa
                                            Distance, Radius)
from tracer.core.sketch.model import SketchModel, model_to_dict     # noqa
from tracer.ui.cmddialog import Shell                               # noqa
from tracer.ui.sketcheditor import SketchCanvas                     # noqa

from conftest import place_dim, script_dim_edit                      # noqa


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


def _no_modal(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a modal dialog opened - FD5-L35 says NO")
    monkeypatch.setattr(Shell, "getDouble", staticmethod(boom))


def _line_scene(ed):
    m = ed.model
    a, b = m.point(0, 0), m.point(10, 0)
    ln = m.add_line(a, b)
    ed._solve()
    return m, ln


def test_act_dim_opens_no_dialog_and_asks_on_the_canvas(ed, qapp,
                                                        monkeypatch):
    _no_modal(monkeypatch)                     # the dead door TESTIFIES
    m, ln = _line_scene(ed)
    ed._sel = [ln]
    h0 = len(ed._hist)
    ed.act_dim()                               # RAISES if a dialog lives
    place_dim(ed)                              # R2: the click places
    assert len(ed._hist) == h0 + 1             # birth costs ONE row
    d = next(x for x in m.sketch.constraints if isinstance(x, Distance))
    assert d.value == pytest.approx(10.0)      # born at the MEASUREMENT
    assert ed._dim_edit is not None and ed._dim_edit.constraint is d
    ed._close_dim_editor()                     # unchanged: no trace


def test_the_newborn_answers_in_canvas_and_redimming_never_stacks(
        ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    script_dim_edit(monkeypatch, "12")         # the seam IS the typing
    m, ln = _line_scene(ed)
    ed._sel = [ln]
    ed.act_dim()
    place_dim(ed)                              # the click answers via seam
    ds = [x for x in m.sketch.constraints if isinstance(x, Distance)]
    assert len(ds) == 1 and ds[0].value == pytest.approx(12.0)
    ed.act_dim()                               # dim it AGAIN
    place_dim(ed)
    ds = [x for x in m.sketch.constraints if isinstance(x, Distance)]
    assert len(ds) == 1                        # remove_last honesty


def test_two_points_dim_without_a_panel(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    script_dim_edit(monkeypatch, "5")
    m = ed.model
    p, q = m.point(0, 0), m.point(10, 0)       # a bare PAIR, no line
    ed._solve()
    ed._sel = [p, q]
    ed.act_dim()
    place_dim(ed)
    ds = [x for x in m.sketch.constraints if isinstance(x, Distance)]
    assert len(ds) == 1 and ds[0].value == pytest.approx(5.0)


def test_a_circle_is_born_speaking_diameter(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    script_dim_edit(monkeypatch, "10")         # TEN typed...
    m = ed.model
    ctr = m.point(0, 0)
    circ = m.add_circle(ctr, 3.0)
    ed._solve()
    ed._sel = [circ]
    ed.act_dim()                               # born R 3.00, speaks O
    place_dim(ed)                              # ...the click asks, TEN
    c = next(x for x in m.sketch.constraints if isinstance(x, Radius))
    assert c.value == pytest.approx(5.0)       # ...FIVE kept in core
    assert ed._dim_text(c) == "\u00d8 10.00"   # the chip says TEN


def test_an_arc_answers_in_radius(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    script_dim_edit(monkeypatch, "7.5")
    m = ed.model
    ar = m.sketch.arc(m.point(0, 0), m.point(10, 6), m.point(20, 0))
    ed._solve()
    ed._sel = [ar]
    ed.act_dim()
    place_dim(ed)
    c = next(x for x in m.sketch.constraints if isinstance(x, Radius))
    assert c.value == pytest.approx(7.5)       # arcs: no halving
    assert ed._dim_text(c) == "R 7.50"


# ---- RUNG 2: THE NEWBORN FOLLOWS THE CURSOR ---------------------------------

def _wander(ed, p):                              # a move with NO button
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.NoButton, Qt.NoButton, Qt.NoModifier))


def test_the_newborn_follows_the_cursor_until_the_click_places_it(
        ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    m, ln = _line_scene(ed)
    ed._sel = [ln]
    ed.act_dim()
    d = next(x for x in m.sketch.constraints if isinstance(x, Distance))
    assert ed._dim_place is d                    # born INTO place mode
    assert getattr(d, "label_off", None) is None  # nothing wandered yet
    p = QPointF(420.0, 260.0)                    # a free-cursor wander
    _wander(ed, p)
    pos = ed._dim_anchor_screen(d)               # the SAME post paint
    assert d.label_off[0] == pytest.approx((p.x() - pos.x()) / ed._scale)
    assert d.label_off[1] == pytest.approx(-(p.y() - pos.y()) / ed._scale)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, p.toPoint())
    assert ed._dim_place is None                 # the PRESS placed it...
    assert ed._dim_edit is not None and ed._dim_edit.constraint is d
    #                                            ...and opened the field
    assert ed._sel == [ln]                       # nothing else touched:
    assert ed._band is None                      #  no deselect, no band,
    assert ed._drag_pt is None                   #   no geometry grab
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, p.toPoint())
    ed._close_dim_editor()


def test_escape_unbirths_the_unplaced_dimension_with_zero_trace(
        ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    m, ln = _line_scene(ed)
    home = (ln.a.x, ln.a.y, ln.b.x, ln.b.y)
    base = json.dumps(model_to_dict(m), sort_keys=True)   # zero trace is
    ed._sel = [ln]                                        #  a BYTE claim
    h0 = len(ed._hist)
    ed.act_dim()
    _wander(ed, QPointF(420.0, 260.0))
    assert len([x for x in m.sketch.constraints
                if isinstance(x, Distance)]) == 1         # it DID exist
    QTest.keyClick(ed, Qt.Key_Escape)
    assert [x for x in m.sketch.constraints
            if isinstance(x, Distance)] == []             # now it doesn't
    assert ed._dim_place is None
    assert len(ed._hist) == h0                            # row spent back
    l0 = m.sketch.lines[0]                                # undo-SWAP law:
    assert (l0.a.x, l0.a.y, l0.b.x, l0.b.y) == home       #  RE-READ
    assert json.dumps(model_to_dict(m), sort_keys=True) == base


def test_a_click_near_home_parks_the_label_byte_clean(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    m, ln = _line_scene(ed)
    ed._sel = [ln]
    ed.act_dim()
    d = ed._dim_place
    ed.grab()
    rect = next(r for r, cc in ed._dim_hits if cc is d)
    wander = QPointF(rect.center().x() + 1.0, rect.center().y() - 1.0)
    _wander(ed, wander)                          # a 1px drift...
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, wander.toPoint())
    assert d.label_off == (0.0, 0.0)             # PARKED exactly home
    assert "lo" not in model_to_dict(m)["constraints"][0]
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, wander.toPoint())
    ed._close_dim_editor()


def test_tool_honesty_an_away_walk_unbirths_a_redundant_stay_does_not(
        ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    m, ln = _line_scene(ed)
    ed._sel = [ln]
    h0 = len(ed._hist)
    ed.act_dim()
    ed.set_tool("select")                        # redundant same-tool:
    assert ed._dim_place is not None             #  the gesture SURVIVES
    ed.set_tool("line")                          # an away walk:
    assert ed._dim_place is None                 #  UNBIRTHS the act
    assert [x for x in m.sketch.constraints
            if isinstance(x, Distance)] == []
    assert len(ed._hist) == h0


# ---- RUNG 3: THE LAST DIM MODAL DIES (act_angle goes inline) ---------------

def _angle_scene(ed, deg=30.0):
    m = ed.model
    a = m.point(0, 0)
    th = math.radians(deg)
    b = m.point(10 * math.cos(th), 10 * math.sin(th))
    ln = m.add_line(a, b)
    ed._solve()
    return m, ln


def test_the_angle_is_born_speaking_degrees(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)                       # the dead door TESTIFIES
    m, ln = _angle_scene(ed, 30.0)
    ed._sel = [ln]
    h0 = len(ed._hist)
    ed.act_angle()                               # RAISES if a dialog lives
    a = next(x for x in m.sketch.constraints if isinstance(x, Angle))
    assert ed._dim_place is a                    # born INTO the place rails
    assert math.degrees(a.value) % 180 == pytest.approx(30.0, abs=1e-6)
    assert (ln.b.x, ln.b.y) == pytest.approx((10 * math.cos(math.radians(30)),
                                              10 * math.sin(math.radians(30))),
                                             abs=1e-9)   # birth never drags
    place_dim(ed)
    assert ed._dim_edit is not None and ed._dim_edit.constraint is a
    assert float(ed._dim_edit.edit.text()) == pytest.approx(30.0, abs=1e-6)
    #                                   ...the field's tongue is DEGREES
    assert len(ed._hist) == h0 + 1               # birth costs ONE row
    ed._close_dim_editor()


def test_the_typed_angle_is_spent_by_the_solver(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    m, ln = _angle_scene(ed, 30.0)
    script_dim_edit(monkeypatch, "45")
    ed._sel = [ln]
    ed.act_angle()
    place_dim(ed)
    ang = next(x for x in m.sketch.constraints if isinstance(x, Angle))
    assert math.degrees(ang.value) % 180 == pytest.approx(45.0, abs=1e-6)
    got = math.degrees(math.atan2(ln.b.y - ln.a.y, ln.b.x - ln.a.x)) % 180
    assert got == pytest.approx(45.0, abs=1e-4)  # the LINE turned to obey


def test_escape_unbirths_an_angle_with_zero_trace(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    m = ed.model
    o = m.point(0, 0)
    e1 = m.point(10, 0)
    th = math.radians(70)
    e2 = m.point(10 * math.cos(th), 10 * math.sin(th))
    L1 = m.add_line(o, e1)
    L2 = m.add_line(o, e2)
    ed._solve()
    base = json.dumps(model_to_dict(m), sort_keys=True)
    ed._sel = [L1, L2]
    h0 = len(ed._hist)
    ed.act_angle()
    ab = next(x for x in m.sketch.constraints
              if isinstance(x, AngleBetween))
    assert math.degrees(ab.value) % 180 == pytest.approx(70.0, abs=1e-6)
    _wander(ed, QPointF(430.0, 150.0))           # the pair rides too
    QTest.keyClick(ed, Qt.Key_Escape)
    assert [x for x in m.sketch.constraints
            if isinstance(x, AngleBetween)] == []
    assert len(ed._hist) == h0
    assert json.dumps(model_to_dict(m), sort_keys=True) == base


def test_re_angling_never_stacks(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    m, ln = _angle_scene(ed, 30.0)
    ed._sel = [ln]
    ed.act_angle()
    place_dim(ed)
    ed._close_dim_editor()
    ed.act_angle()                               # the door re-enters
    place_dim(ed)
    ed._close_dim_editor()
    angs = [x for x in m.sketch.constraints if isinstance(x, Angle)]
    assert len(angs) == 1                        # remove_last honesty


def test_the_angle_anchor_is_the_painters_own_post(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    m, ln = _angle_scene(ed, 30.0)
    ed._sel = [ln]
    ed.act_angle()
    a = ed._dim_place
    pos = ed._dim_anchor_screen(a)
    assert pos is not None
    ed.grab()                                    # paint == hit == place
    rect = next(r for r, cc in ed._dim_hits if cc is a)
    assert abs(rect.center().x() - pos.x()) < 1.0
    assert abs(rect.center().y() - pos.y()) < 1.0
    _wander(ed, QPointF(pos.x() + 60.0, pos.y() + 40.0))
    assert a.label_off[0] == pytest.approx(60.0 / ed._scale)
    assert a.label_off[1] == pytest.approx(-40.0 / ed._scale)
    ed._cancel_dim_place()                       # leave no ghost behind
