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
COMMANDS the number - a ruler, not a reader. Rung 2 PROBED the solver
before asserting (cite-the-truth): editing the fillet's radius is HONORED
(arc radius == the number) and the arc STAYS TANGENT to both legs through
the change; on a corner whose legs are constrained (H/V + fixed far ends)
it re-trims the Fusion way - far ends hold EXACTLY, the two tangent points
SLIDE along the fixed legs. The probe also CORRECTED the card: the
"radius too large -> refuse" guard lives only in the hand's type-in
(corner_rmax), never in the dim path, and a big radius on a constrained
corner re-trims cleanly anyway - so "too-large refuses" was false; R2
asserts only the true resize-and-stay-tangent law. Rung 3 (PROBED first)
is the M178 driven grammar composing on a fillet dim - and it needed NO
product change: _dim_text already stacks the parentheses on a Radius
("(R 3.00)"), the single driven-guard already keeps the fillet's dim inert
at the editor door, and because the fillet radius is an ordinary driving
Radius, making it DRIVEN lets the corner walk and the chip RE-QUOTES the
drifted arc radius - a reader, reporting, never commanding - and flipping
it back PINS the reading it holds (no resurrected number). 3 composition
gates (file 10); this is a regression guarantee that a fillet dim is not
secretly special-cased away from the driven machinery.
"""
import math                                                    # noqa

import pytest                                                  # noqa

pytest.importorskip("PySide6")                                 # noqa

from PySide6.QtWidgets import QApplication                      # noqa

from tracer.core.sketch.constraints import (Fixed, Horizontal,  # noqa
                                            Radius, Vertical)
from tracer.core.sketch.entities import curve_center, curve_radius  # noqa
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


# ---- RUNG 2: editing the fillet's radius RESIZES it and stays TANGENT ----

def _dpl(p, a, b):
    """Distance from point p to the line through a, b (all (x,y) tuples) -
    tangency to a leg means this equals the arc's radius."""
    (x1, y1), (x2, y2) = a, b
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1.0
    return abs(dy * p[0] - dx * p[1] + x2 * y1 - y2 * x1) / L


def _constrained_corner(ed):
    """A corner a USER would actually fillet: legs pinned Horizontal /
    Vertical, FAR ends fully fixed - so the only freedom is the two tangent
    points sliding along fixed lines. This is Fusion's situation, and the
    only one where 're-trim' means anything (an unconstrained corner just
    rotates - tangency survives there too, but the geometry floats)."""
    m = ed.model
    far1 = m.point(8.0, -4.0)
    far2 = m.point(-6.0, 6.0)
    P = m.point(-6.0, -4.0)
    l1 = m.add_line(P, far1)
    l2 = m.add_line(P, far2)
    ed._corner_arm("fillet", l1, l2)
    ed._corner[4] = 4.0
    ed._corner_file()
    ed._close_dim_editor()
    m.sketch.constraints.extend([
        Horizontal(l1), Vertical(l2),
        Fixed(far1, x=8.0, axis=0), Fixed(far1, y=-4.0, axis=1),
        Fixed(far2, x=-6.0, axis=0), Fixed(far2, y=6.0, axis=1)])
    m.solve()
    return far1, far2


def test_editing_the_radius_keeps_the_fillet_tangent(ed, qapp):
    m = ed.model
    _P, l1, l2 = _right_angle(m)                 # NO extra constraints:
    ed._corner_arm("fillet", l1, l2)             #  the corner may float,
    ed._corner[4] = 4.0                           #  but tangency is the
    ed._corner_file()                             #   constraint set's job
    ed._close_dim_editor()
    arc, rr = _fillet_radius(ed)
    ed._apply_dim_edit(rr, "2.5")                # resize the fillet
    c = curve_center(arc); r = curve_radius(arc)
    assert r == pytest.approx(2.5, abs=1e-3)     # the arc IS the number
    for leg in (l1, l2):                         #  and touches BOTH legs
        d = _dpl(c, (leg.a.x, leg.a.y), (leg.b.x, leg.b.y))
        assert d == pytest.approx(r, abs=1e-2)   #   (tangent, err ~0)


def test_editing_the_radius_grows_the_fillet_on_fixed_legs(ed, qapp):
    far1, far2 = _constrained_corner(ed)         # legs pinned H/V, ends set
    arc, rr = _fillet_radius(ed)
    ed._apply_dim_edit(rr, "4.5")                # GROW it (a>4)
    assert (far1.x, far1.y) == pytest.approx((8.0, -4.0), abs=1e-6)
    assert (far2.x, far2.y) == pytest.approx((-6.0, 6.0), abs=1e-6)
    assert (arc.a.x, arc.a.y) == pytest.approx((-1.5, -4.0), abs=0.02)
    assert (arc.b.x, arc.b.y) == pytest.approx((-6.0, 0.5), abs=0.02)
    #   the tangent points SLID along the fixed legs to -6+4.5 / -4+4.5
    assert curve_radius(arc) == pytest.approx(4.5, abs=1e-3)


def test_editing_the_radius_shrinks_the_fillet_too(ed, qapp):
    far1, far2 = _constrained_corner(ed)
    arc, rr = _fillet_radius(ed)
    ed._apply_dim_edit(rr, "2.0")                # SHRINK it (a<4)
    assert (far1.x, far1.y) == pytest.approx((8.0, -4.0), abs=1e-6)
    assert (far2.x, far2.y) == pytest.approx((-6.0, 6.0), abs=1e-6)
    assert (arc.a.x, arc.a.y) == pytest.approx((-4.0, -4.0), abs=0.02)
    assert (arc.b.x, arc.b.y) == pytest.approx((-6.0, -2.0), abs=0.02)
    assert curve_radius(arc) == pytest.approx(2.0, abs=1e-3)   # tangency law


# ---- RUNG 3: the fillet dim OBEYS the M178 driven grammar (composition) ----

def _plain_fillet(ed, r=3.0):
    m = ed.model
    _P, l1, l2 = _right_angle(m)
    ed._corner_arm("fillet", l1, l2)
    ed._corner[4] = r
    ed._corner_file()
    ed._close_dim_editor()
    arc, rr = _fillet_radius(ed)
    return l1, arc, rr


def test_a_driven_fillet_radius_wears_parentheses_and_is_inert(ed, qapp):
    _l1, _arc, rr = _plain_fillet(ed)
    ed.act_driven(rr)                                  # make it a READER
    assert rr.driven
    assert ed._dim_text(rr) == "(R 3.00)"              # parens stack on a
    #   RADIUS too - _dim_text is the ONE wording mouth (M178 R1), it does
    #   not care the dim was minted by a fillet rather than placed by hand
    ed._open_dim_editor(rr)                            # M178's single guard:
    assert ed._dim_edit is None                        #  a reader opens naught


def test_a_driven_fillet_radius_quotes_the_walk(ed, qapp):
    l1, arc, rr = _plain_fillet(ed)
    ed.act_driven(rr)                                  # READER
    l1.b.x, l1.b.y = 10.0, 6.0                         # walk a leg (free)
    ed.model.solve()
    r_now = curve_radius(arc)
    assert r_now < 2.9                                 # the fillet moved OFF 3
    assert rr.value == pytest.approx(r_now, abs=1e-3)  #  the reader REPORTS
    assert ed._dim_text(rr) == f"(R {r_now:.2f})"      #   the drifted number


def test_reconverting_a_driven_fillet_pins_its_reading(ed, qapp):
    l1, arc, rr = _plain_fillet(ed)
    ed.act_driven(rr)                                  # reader...
    l1.b.x, l1.b.y = 10.0, 6.0
    ed.model.solve()                                   #  ...quotes the walk
    held = rr.value                                    # the reading it holds
    ed.act_driven(rr)                                  # back to DRIVING
    assert rr.value == pytest.approx(held, abs=1e-3)   #  PINS it - no
    l1.b.x, l1.b.y = 12.0, 2.0                         #   resurrected number
    ed.model.solve()                                   #   (the M178 truth)
    assert rr.value == pytest.approx(held, abs=1e-3)
    assert curve_radius(arc) == pytest.approx(held, abs=0.05)  # a ruler holds
