"""M178 rung 1 - DRIVEN DIMENSIONS: REFERENCE, NOT RULE (FD5-L35).

Fusion's last uncloned clause of the dim law: a dimension can be made
DRIVEN - a READER. It keeps its chip, loses its vote: the solver never
sees the row, the DOF bill never grows, and after every solve the chip
QUOTES the geometry (never the other way round). Forum-verified
display law: a driven value wears PARENTHESES, in quiet colors.

The toggle rides the hover right-click (the menu M164 R3 opened and
M174 R3's dialect twin proved the anatomy) - and unlike the cosmetic
dialect flip, driven MUST re-solve. The round trip carries a subtlety
the first cut of these gates got WRONG (cite-the-truth again): while
driven the chip QUOTED the walking geometry, so making the dim driving
PINS THE READING IT HOLDS - there is no resurrection of an old number
(Fusion converting a driven dim re-pins the shown value). What returns
is the VOTE: from the flip on, geometry that strays is pulled back.

Rung 2 landed L35's EXACT creation mouth: right-click a NEWBORN while
it still follows the cursor and it arrives DRIVEN from birth, the
editor never opening (a reader has no number to command). Rung 3 is the
reader's INERTNESS: "can't be edited" [obs] enforced at ONE mouth -
_open_dim_editor refuses a driven constraint at EVERY door (dbl-click,
F2, palette _edit_dim), so no future driver can smuggle a value in.
What the reader KEEPS: its label still rides the drag (position is not
a value). One interaction the flip had to settle - toggling a chip
mid-edit now CLOSES the editor first (the field owns the ink; a reader
has none) - and the ring dies with it, rung-4's law. Angle-dim quoting
stays deferred: the painter's Angle branch bypasses _dim_text and the
menu never offers Make Driven there.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt                # noqa
from PySide6.QtGui import QMouseEvent                                  # noqa
from PySide6.QtTest import QTest                                        # noqa
from PySide6.QtWidgets import QApplication                         # noqa

from tracer.core.sketch.constraints import Distance, Radius        # noqa
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


def _two_points():
    m = SketchModel()
    p = m.point(0.0, 0.0)
    q = m.point(5.0, 0.0)
    d = Distance(p, q, 5.0)
    m.sketch.constraints.append(d)
    return m, p, q, d


def test_a_driven_distance_never_rules():
    m, p, q, d = _two_points()
    d.driven = True
    q.x = 9.0                                  # the geometry WALKS AWAY
    m.solve()                                  #  - and nothing pulls it
    assert math.hypot(q.x - p.x, q.y - p.y) == pytest.approx(9.0)


def test_the_driving_twin_still_rules():
    m, p, q, d = _two_points()
    q.x = 9.0
    m.solve()                                  # control: the same solve
    #  WITH a vote obeys - and note WHERE it lands: the least-norm pull
    #  divides across both free points (p AND q slide); the LAW is that
    #  the MEASUREMENT returns to the word, not which point moved.
    assert math.hypot(q.x - p.x, q.y - p.y) == pytest.approx(5.0)


def test_a_driven_dim_quotes_the_live_geometry():
    m, p, q, d = _two_points()
    d.driven = True
    q.x = 9.0
    q.y = 1.0
    m.solve()
    assert d.value == pytest.approx(math.hypot(9.0, 1.0))  # it REPORTS


def test_a_driven_dim_bills_no_dof():
    m, p, q, d = _two_points()
    assert m.solve().dof == 3                  # driving: 4 vars - 1 row
    d.driven = True
    assert m.solve().dof == 4                  # driven: the row was
    #                                           never cut - freedom kept


def test_remove_last_never_eats_the_driven_bystander():
    m, p, q, d = _two_points()
    d.driven = True
    m.remove_last(Distance, (p, q))            # re-dimming targets the
    assert m.sketch.constraints == [d]         #  DRIVING twin only
    t = Distance(p, q, 9.0)
    m.sketch.constraints.append(t)             # a driving twin is born
    m.remove_last(Distance, (p, q))
    assert m.sketch.constraints == [d]         #  and re-dim eats IT,
    #                                           never the reference


def test_the_hover_menu_flips_the_vote_both_ways(ed):
    m = ed.model
    ln = m.add_line(m.point(0.0, 0.0), m.point(6.0, 0.0))
    ed._sel = [ln]
    ed.act_dim()                               # the newborn...
    QTest.mouseClick(ed, Qt.LeftButton)        #  ...claims the click
    QApplication.instance().processEvents()
    dims = [c for c in m.sketch.constraints if isinstance(c, Distance)]
    assert len(dims) == 1
    d = dims[0]
    ed._hover_c = d
    texts = [a.text() for a in ed._build_menu().actions()]
    assert "Make Driven" in texts              # the door is there
    ed.act_driven(d)
    assert d.driven
    ln.b.x = 10.0                              # walk away...
    m.solve()
    assert ln.b.x == pytest.approx(10.0)       #  - driven lets it
    assert d.value == pytest.approx(10.0)      #   and QUOTES the walk
    ed._hover_c = d                            # the settle-first close
    #  killed the ring (rung-4 law: it DIES with the editor) - re-arm,
    #  the cursor never left the chip
    texts = [a.text() for a in ed._build_menu().actions()]
    assert "Make Driving" in texts             # the flip is two-way
    ed.act_driven(d)
    assert not d.driven                        # voting again: the pin
    ln.b.x = 13.0                              #  lands at the READING
    m.solve()                                  #   it holds (10, not the
    ln.b.x = 13.0                              #    original 6 - no
    m.solve()                                  #    resurrection), and
    assert math.hypot(ln.b.x - ln.a.x,        #     stray no more: the
                      ln.b.y - ln.a.y) == pytest.approx(10.0)  # vote RULES


def test_the_driven_chip_wears_parentheses(ed):
    m = ed.model
    c = m.sketch.circle(m.point(0.0, 0.0), 3.0)
    r = Radius(c, 3.0)
    m.sketch.constraints.append(r)
    assert ed._dim_text(r) == "\u00d8 6.00"    # dialect intact (M174 R3)
    r.driven = True
    assert ed._dim_text(r) == "(\u00d8 6.00)"  #  parentheses ride ON TOP
    d = Distance(m.point(0.0, 0.0), m.point(5.0, 0.0), 5.0)
    assert ed._dim_text(d) == "5.00"
    d.driven = True
    assert ed._dim_text(d) == "(5.00)"


# ---- RUNG 2: RIGHT-CLICK THE NEWBORN - DRIVEN FROM BIRTH (FD5-L35) -------
# L35's EXACT creation mouth: "right-click BEFORE placing = Driven dim".
# The hover menu cannot ride place mode (it is a select-mode door), so the
# gesture IS the law: a right press while the ghost follows the cursor
# LANDS the dim at the cursor, driven from birth - and the birth editor
# STAYS SHUT, because a reader has no number to command.


def _right(ed, x, y):
    p = ed.w2s(x, y).toPoint()
    QTest.mousePress(ed, Qt.RightButton, pos=p)
    QTest.mouseRelease(ed, Qt.RightButton, pos=p)
    QApplication.instance().processEvents()


def test_right_press_before_placing_lands_it_driven(ed, qapp):
    m = ed.model
    ln = m.add_line(m.point(0.0, 0.0), m.point(8.0, 0.0))
    ed._sel = [ln]
    ed.act_dim()                               # newborn follows cursor
    assert ed._dim_place is not None
    _right(ed, 4.0, -6.0)                      # right-click BEFORE placing
    assert ed._dim_place is None               #  it LANDS HERE...
    dims = [c for c in m.sketch.constraints if isinstance(c, Distance)]
    assert len(dims) == 1 and dims[0].driven   #   ...DRIVEN from birth
    assert ed._dim_edit is None                #    editor STAYS SHUT


def test_a_birth_driven_dim_never_owns_the_geometry(ed):
    m = ed.model
    ln = m.add_line(m.point(0.0, 0.0), m.point(8.0, 0.0))
    ed._sel = [ln]
    ed.act_dim()
    _right(ed, 4.0, -6.0)
    d = [c for c in m.sketch.constraints if isinstance(c, Distance)][0]
    assert d.value == pytest.approx(8.0)       # quoted at birth
    ln.b.x = 20.0
    m.solve()
    assert ln.b.x == pytest.approx(20.0)       # nobody yanked it back
    assert d.value == pytest.approx(20.0)      # the quote FOLLOWED


def test_the_left_press_still_lands_it_driving_unchanged(ed, qapp):
    m = ed.model
    ln = m.add_line(m.point(0.0, 0.0), m.point(8.0, 0.0))
    ed._sel = [ln]
    ed.act_dim()
    QTest.mouseClick(ed, Qt.LeftButton)        # control: the ORDINARY
    QApplication.instance().processEvents()    #  claim is UNTOUCHED
    d = [c for c in m.sketch.constraints if isinstance(c, Distance)][0]
    assert not d.driven                        # driving as ever...
    assert ed._dim_edit is not None            #  ...editor opens as ever
    ed._close_dim_editor()


# ---- RUNG 3: THE READER IS INERT - EVERY DOOR - (FD5-L35) ----------------
# "It shows up in parentheses and CAN'T BE EDITED" [obs, forum-verified].
# The law is one gate at _open_dim_editor, not four sprinkled guards: the
# dbl-click door, the F2 door, the palette's _edit_dim and any future
# driver all answer through it. What the reader KEEPS: its label rides
# the drag like any chip's (position is not a value) - and act_driven on
# a chip mid-edit settles the editor FIRST (ink ownership, then the flip).


def _settle_dim(ed, ln, wx=4.0, wy=-6.0):
    ed._sel = [ln]
    ed.act_dim()
    p = ed.w2s(wx, wy).toPoint()
    _slide(ed, p)                              # the ghost RIDES here on
    QTest.mouseClick(ed, Qt.LeftButton, pos=p) #  the way (sets label_off)
    QApplication.instance().processEvents()
    d = [c for c in ed.model.sketch.constraints
         if isinstance(c, Distance)][-1]
    ed._close_dim_editor()
    return d


def _chip_at(ed, c):
    ed.grab()                                    # paint == hit: _dim_hits
    for rect, cc in ed._dim_hits:                #  is PAINT's ledger
        if cc is c:
            return QPoint(int(rect.center().x()), int(rect.center().y()))
    raise AssertionError("chip not painted")


def _key(ed, k):
    QTest.keyClick(ed, k)
    QApplication.instance().processEvents()


def _slide(ed, pt, held=False):
    """A DELIVERED move (m174's law: QTest.mouseMove does not drive a
    hidden canvas's handler - sendEvent does). held=True rides a press."""
    btn = Qt.LeftButton if held else Qt.NoButton
    pos = QPointF(pt)
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, pos, pos, pos,
                        btn, btn, Qt.NoModifier))
    QApplication.instance().processEvents()


def test_dbl_click_on_a_driven_opens_nothing(ed, qapp):
    m = ed.model
    ln = m.add_line(m.point(0.0, 0.0), m.point(8.0, 0.0))
    d = _settle_dim(ed, ln)
    assert ed._dim_edit is None
    ed.act_driven(d)
    QTest.mouseDClick(ed, Qt.LeftButton, pos=_chip_at(ed, d))
    QApplication.instance().processEvents()
    assert ed._dim_edit is None                # the reader edits NOTHING
    ed.act_driven(d)                           # driving again: the SAME
    QTest.mouseDClick(ed, Qt.LeftButton, pos=_chip_at(ed, d))  #  dbl now
    QApplication.instance().processEvents()                    #  ASKS
    assert ed._dim_edit is not None and ed._dim_edit.constraint is d
    ed._close_dim_editor()


def test_the_f2_door_and_the_palette_door_stay_shut(ed, qapp):
    m = ed.model
    ln = m.add_line(m.point(0.0, 0.0), m.point(8.0, 0.0))
    d = _settle_dim(ed, ln)
    ed.act_driven(d)
    _slide(ed, _chip_at(ed, d))                # the canvas's OWN eyes:
    _key(ed, Qt.Key_F2)                        #  _cursor lives in moves
    assert ed._dim_edit is None                #  inert on a reader
    ed._edit_dim(d)                            # the PALETTE door:
    assert ed._dim_edit is None                #  inert too
    ed.act_driven(d)                           # while DRIVING, both
    _slide(ed, _chip_at(ed, d))                #  doors still open
    _key(ed, Qt.Key_F2)
    assert ed._dim_edit is not None
    ed._close_dim_editor()


def test_act_driven_settles_an_open_editor_first(ed, qapp):
    m = ed.model
    ln = m.add_line(m.point(0.0, 0.0), m.point(8.0, 0.0))
    ed._sel = [ln]
    ed.act_dim()                               # newborn... editor OPEN
    QTest.mouseClick(ed, Qt.LeftButton)
    QApplication.instance().processEvents()
    d = [c for c in m.sketch.constraints if isinstance(c, Distance)][-1]
    assert ed._dim_edit is not None
    ed.act_driven(d)                           # flip MID-EDIT:
    assert ed._dim_edit is None                #  editor settled FIRST...
    assert d.driven                            #   ...then the vote left


def test_a_driven_label_still_rides_the_drag(ed, qapp):
    m = ed.model
    ln = m.add_line(m.point(0.0, 0.0), m.point(8.0, 0.0))
    d = _settle_dim(ed, ln)
    ed.act_driven(d)
    p0 = _chip_at(ed, d)
    off0 = tuple(d.label_off)
    QTest.mousePress(ed, Qt.LeftButton, pos=p0)      # THE LABEL CLAIMS
    p1 = QPoint(p0.x(), p0.y() + 20)                 #  a drag: position
    _slide(ed, p1, held=True)                        #  is not a value -
    QTest.mouseRelease(ed, Qt.LeftButton, pos=p1)    #  the reader still
    QApplication.instance().processEvents()          #  rearranges freely
    assert ed._dim_edit is None                      # no editor by drag
    assert d.label_off != off0                       # the label MOVED
    assert d.value == pytest.approx(8.0)             # the read survives
    assert ln.b.x == pytest.approx(8.0)              # geometry untouched
