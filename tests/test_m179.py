"""M179 - THE CORNER'S READING (FD5-L30, the fillet's radius dim).

A sketch fillet in Fusion ships WITH a permanent radius dimension, and
the moment you place it the radius input box AUTO-OPENS - the number is
asked right there, in the same editor a hand-placed dim uses, and the
dim is double-click editable. (SKT-ADD-FILLETS.htm [documented].)

Cite-the-truth first: the kernel (corner_fillet) ALREADY mints a
Radius(arc, r); _draw_dimensions renders EVERY Radius/Distance with no
src/construction filter - so a fillet ALREADY carries a visible,
double-click-editable R chip (M178's driven guard now protects it), and
M172's rounding hand ALREADY shows the proportional preview + a
pre-placement type-in. The ONE unshipped distinctive is the box
AUTO-OPENING AT PLACEMENT - so this rung is a door, not a feature build.

Rung 1 files a fillet through _corner_file (the single door release AND
Enter both knock on) and asserts the newborn radius editor springs open
ON THE FILLET'S OWN Radius - found by IDENTITY on the arc, never list
position (the kernel appends Radius THEN ArcMiddle, so a positional read
would open the wrong chip). The box must open OVER a chip the painter
actually posts (paint == hit == place). A CHAMFER is a flat Line with no
radius, so it keeps its silence and opens NOTHING. And the opened box
COMMANDS the number - a ruler, not a reader. The solver's re-trim-and-
stay-tangent round trip is rung 2 (probe the answer before asserting it);
the M178 driven grammar composing on a fillet dim is rung 3.
"""
import pytest                                                  # noqa

pytest.importorskip("PySide6")                                 # noqa

from PySide6.QtWidgets import QApplication                      # noqa

from tracer.core.sketch.constraints import Radius               # noqa
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
    yield c
    c.deleteLater()


def _right_angle(m):
    """An L corner: two lines sharing ONE Point at the origin, legs of
    10 along +X and +Y (theta 90, so the hand's default r=2.5 sits well
    under the legs' max ~4.98)."""
    P = m.point(0.0, 0.0)
    l1 = m.add_line(P, m.point(10.0, 0.0))
    l2 = m.add_line(P, m.point(0.0, 10.0))
    return P, l1, l2


def _fillet_radius(cv):
    """The Radius the fillet just minted, found by IDENTITY on the new
    arc - never by position (Radius is followed by ArcMiddle)."""
    arc = cv.model.sketch.arcs[-1]
    return arc, next(c for c in cv.model.sketch.constraints
                     if isinstance(c, Radius) and c.curve is arc)


def test_a_fillet_auto_opens_its_own_radius(ed, qapp):
    m = ed.model
    _P, l1, l2 = _right_angle(m)
    assert ed._corner_arm("fillet", l1, l2)          # the HAND aims
    assert ed._corner_file() is True                 #  then FILES
    arc, rr = _fillet_radius(ed)
    assert ed._dim_edit is not None                  # THE BOX OPENED
    assert ed._dim_edit.constraint is rr             #  on the OWN R
    assert rr.value == pytest.approx(2.5)            #   the hand default


def test_the_opening_lands_on_a_painted_chip(ed, qapp):
    #  the auto-open must seat the field OVER a chip the painter posts,
    #  else the box floats unanchored - paint == hit == place (M175).
    m = ed.model
    _P, l1, l2 = _right_angle(m)
    ed._corner_arm("fillet", l1, l2)
    ed._corner_file()
    _arc, rr = _fillet_radius(ed)
    ed.grab()                                        # force a paint
    assert any(cc is rr for _r, cc in ed._dim_hits)  #  the box opens
    #                                                   OVER a real R


def test_a_chamfer_opens_no_box(ed, qapp):
    m = ed.model
    _P, l1, l2 = _right_angle(m)
    assert ed._corner_arm("chamfer", l1, l2)
    assert ed._corner_file() is True
    assert ed._dim_edit is None                      # a flat Line has
    #  NO radius to command - the door stays honest and SHUT
    assert not any(isinstance(c, Radius) for c in m.sketch.constraints)


def test_the_opened_box_commands_the_number(ed, qapp):
    m = ed.model
    _P, l1, l2 = _right_angle(m)
    ed._corner_arm("fillet", l1, l2)
    ed._corner_file()
    arc, rr = _fillet_radius(ed)
    assert ed._dim_edit is not None                  # the box is open
    ed._apply_dim_edit(rr, "3.5")                    # the hand TYPES a R
    assert rr.value == pytest.approx(3.5)            # the dim is a RULER
    assert arc in m.sketch.arcs                      #  the arc takes it
    m.solve()                                        #   and re-solves
