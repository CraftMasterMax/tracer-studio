"""M194 rung 1 - THE GREEN LOCK.

SKT-CONSTRAINTS, verbatim: "Fix/UnFix  The Fix/UnFix tool locks the
size and location of a point or object."  And SKT-CONSTRAIN-FIX-UNFIX
spends the visible half of the sentence: "The size and location of the
sketch geometry is locked. THE SELECTED GEOMETRY TURNS GREEN,
indicating that the geometry is locked."  Tracer always had the RECORD
(Fixed: per-axis rows, the ■ badge, the F verb on a selected point)
but never the PAINT: fixed geometry looked exactly like free geometry.
This rung pays that sentence:

- The lock reads its RECORD, not its mobility.  A point pinned by two
  Distance dimensions is fully DEFINED - M186's white ink is a
  DIFFERENT sentence (it speaks "every variable rests"); only a Fixed
  record turns the geometry green.  The two inks never substitute.
- Dot EXISTENCE stays M191's law (GUID-685B9D79: a welded point shows
  NO dot): green is the COLOR of a dot the existence law already
  shows - a welded-and-fixed point stays an open ring and its record
  speaks through the badge, not through an invented marker.
- Selection and hover OUTVOTE state (transient highlight over state
  color), exactly as they outvote blue and white today.
- The ■ badge moved BESIDE the point: dead-center it buried the 5 px
  dot under a 13x15 plate and the vendor's green never reached the
  screen - the geometry is what turns green, so the icon steps aside.
- The lock LEAVES with the record: the second verb (Rung 2's law)
  frees the point and the green goes back to white with the pixels.

Rung 2 pins the UNFIX half, verbatim: "To unfix sketch geometry,
select the Fix/UnFix tool again, then click the geometry in the
canvas."  The audit's honest verdict: the doors EXIST (act_fix is a
model.toggle, _push_hist sits before it, the serializer keeps "F"
rows) - so this rung adds NO implementation; it proves the whole
vendor sentence at the mouths that matter: the lock actually LOCKS
(a disturbed solver puts the pinned point back to its targets, x AND
y), the second verb frees those DOF again (the same disturbance then
STAYS), undo/redo walk the record both ways with the green riding
them, a saved file keeps the lock - and the reloaded sketch WEARS it,
pixels back - and the verb on nothing (or on the two-Line fillet
aim) mints no record at all.  A welded point's visit leaves the weld
whole.

Rung 3 pays the third word - "or OBJECT": Fix/UnFix now takes a
Line, Arc, Circle or Ellipse.  The record snapshots EVERY scalar the
entity owns - members' coordinates, then size (a circle's radius, an
ellipse's semi-axes; an arc's size IS its three points, so six
coordinates say it whole) - and the solver honours all of them: a
disturbed object returns to its record on every row.  The lock's green
now rides the STROKE (solid_for: lock outvotes the defined-white, the
selection glow still outvotes all), the ■ rides the entity's own
anchor (never a buried dot), the dots a locked line owns keep their
M191 sentence untouched, and a welded neighbour feels the shared
point's lock without wearing any of its own.  The file, undo and the
verb again all treat the object exactly as R2 pinned the point.
"""
import json
import math

import pytest

pytest.importorskip("PySide6")

import numpy as np                                                # noqa
from PySide6.QtCore import Qt                                     # noqa
from PySide6.QtGui import QColor, QImage                          # noqa
from PySide6.QtTest import QTest                                  # noqa
from PySide6.QtWidgets import QApplication                        # noqa

from tracer.core.sketch.model import (SketchModel, model_from_dict,      # noqa
                                      model_to_dict)
from tracer.core.sketch.constraints import (Distance, Fixed, expand,       # noqa
                                            fixed_lock)
from tracer.ui import theme                                       # noqa
from tracer.ui.sketcheditor import SketchCanvas                   # noqa

FIXED_RGB = np.array(QColor(theme.SKETCH["fixed"]).getRgb()[:3], np.int16)
FG_RGB = np.array(QColor(theme.SKETCH["full"]).getRgb()[:3], np.int16)
SEL_RGB = np.array(QColor(theme.SKETCH["sel"]).getRgb()[:3], np.int16)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    c = SketchCanvas()
    c.set_model(SketchModel())
    c.resize(600, 400)
    c._scale = 8.0                       # generous px/unit: the dot's
    c._snap_grid = False                 #  few honest pixels stay countable
    yield c
    c.deleteLater()


def _sp(cv, x, y):
    return cv.w2s(x, y).toPoint()


def _click(cv, x, y):
    p = _sp(cv, x, y)
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, p)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, p)
    QApplication.instance().processEvents()


def _grab(cv):
    img = cv.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(img.constBits().tobytes(), np.uint8).reshape(
        img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), :3].copy()


def _near(rgb, d=40):
    """Pixel MATCH against an exact theme color, antialias-friendly."""
    def f(arr):
        return int((np.abs(arr.astype(np.int16)
                           - rgb.astype(np.int16)).max(axis=2) < d).sum())
    return f


def _dot(cv, pt, half=6):
    """The dot's own window - tight enough that the offset ■ badge never
    lends a pixel to any census."""
    q = _sp(cv, pt.x, pt.y)
    a = _grab(cv)
    return a[max(0, q.y() - half):q.y() + half + 1,
             max(0, q.x() - half):q.x() + half + 1]


def _fix_verb(cv, *ents):
    """The vendor's door in Tracer's dialect: SELECT, then F.  Returns
    with selection CLEARED - state ink is measured unselected (R1's own
    precedence law)."""
    cv._sel = list(ents)
    QTest.keyClick(cv, Qt.Key_F)
    QApplication.instance().processEvents()
    cv._sel = []
    cv.update()
    QApplication.instance().processEvents()


def _leg(cv, ax, ay, bx, by):
    """A DIAGONAL leg: no auto-inferred H/V joins the party, so every
    constraint on the page is one this test wrote."""
    cv.set_tool("line")
    _click(cv, ax, ay)
    _click(cv, bx, by)
    cv.set_tool("select")
    QApplication.instance().processEvents()


# ---- R1: the vendor's green rides the RECORD ------------------------------
def test_fixed_point_turns_green(ed):
    """SKT-CONSTRAIN-FIX-UNFIX verbatim: "The selected geometry turns
    GREEN, indicating that the geometry is locked."  Press F on the
    selected free endpoint: the record files AND the dot's OWN pixels
    answer - the vendor's palette green, on the dot, nowhere else."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    pt = cv.model.sketch.lines[-1].b
    before = _grab(cv)
    assert _near(FIXED_RGB)(_dot(cv, pt)) == 0         # control: the
    #                          canvas wears NO lock-green before the verb
    assert _near(FIXED_RGB)(before) == 0
    _fix_verb(cv, pt)
    sk = cv.model.sketch
    assert [type(c).__name__ for c in sk.constraints] == ["Fixed"]
    w = _dot(cv, pt)
    got = _near(FIXED_RGB)(w)
    assert got >= 12, f"the locked dot wears only {got} green pixels"
    # the lock is LOCAL: nothing else on the canvas turned green
    assert _near(FIXED_RGB)(_grab(cv)) == got
    # and the paint MOVED (L∞>24, counted not averaged, sized to a dot)
    ch = int((np.abs(before.astype(int) - _grab(cv).astype(int))
              .max(axis=2) > 24).sum())
    assert ch >= 20, f"the green lock changed only {ch} pixels"


def test_defined_without_record_stays_neutral(ed):
    """HONESTY gate: the two sentences are different.  A point pinned
    DOWN by two Distance dimensions is held by NO Fixed record - it
    wears no green whatever its DOF says.  Green is the lock's own
    mouth (M186's defined-white is a different sentence)."""
    cv = ed
    _leg(cv, 2, 4, 10, 4)
    sk = cv.model.sketch
    a, b = sk.lines[-1].a, sk.lines[-1].b
    p = cv.model.point(6.0, 9.0)
    cv.model.constrain(Distance(a, p, math.hypot(4.0, 5.0)))
    cv.model.constrain(Distance(b, p, math.hypot(4.0, 5.0)))
    cv._solve()
    assert not any(isinstance(c, Fixed) for c in sk.constraints)
    assert _near(FIXED_RGB)(_dot(cv, p)) == 0          # no record: no green
    assert _near(FG_RGB)(_dot(cv, p)) >= 8             #  the dot still rides
    #                                       its OWN (free/white) sentence
    assert cv._fix_locked(p) is False


def test_welded_and_locked_still_shows_no_dot(ed):
    """M191's existence law SURVIVES the lock: "Point to point
    coincident constraints show no dot" - the shared corner is an open
    ring, and fixing it adds NO green fill inside the ring.  Green is
    the COLOR of the dots that exist; it never INVENTS one (the exact
    lie M191's pixel census was born to catch).  The record speaks
    through the badge instead - which now sits BESIDE the corner."""
    cv = ed
    cv.set_tool("line")
    _click(cv, 2, 4)
    _click(cv, 8, 4)                                   # weld at (8,4)
    _click(cv, 8, 9)
    cv.set_tool("select")
    sk = cv.model.sketch
    shared = sk.lines[0].b
    assert shared is sk.lines[1].a                     # identity weld
    _fix_verb(cv, shared)
    assert any(isinstance(c, Fixed) for c in sk.constraints)
    w = _dot(cv, shared)
    assert _near(FIXED_RGB)(w) == 0                    #  no dot: no green
    assert _near(FG_RGB)(w) == 0                       #  and no white fill


def test_selection_outvotes_the_lock(ed):
    """Transient highlight over state color: the SELECTED point wears
    the selection cyan even while locked - the same precedence that
    lets selection outvote blue and white.  Deselect and the green
    returns."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    pt = cv.model.sketch.lines[-1].b
    cv._sel = [pt]
    QTest.keyClick(cv, Qt.Key_F)
    QApplication.instance().processEvents()
    assert _near(SEL_RGB)(_dot(cv, pt)) >= 8           # selection speaks...
    assert _near(FIXED_RGB)(_dot(cv, pt)) == 0         #  the lock steps back
    cv._sel = []
    cv.update()
    assert _near(FIXED_RGB)(_dot(cv, pt)) >= 12        # ...the green returns


def test_unfix_frees_the_green_with_the_record(ed):
    """Rung 2's law PRE-PINNED at the paint mouth: "To unfix sketch
    geometry, select the Fix/UnFix tool again" - the second verb drops
    the record, and the dot reverts to its sentence BEFORE the lock
    (the free white dot), pixel for pixel."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    pt = cv.model.sketch.lines[-1].b
    _fix_verb(cv, pt)
    assert _near(FIXED_RGB)(_dot(cv, pt)) >= 12
    _fix_verb(cv, pt)                                  # the verb AGAIN
    sk = cv.model.sketch
    assert not any(isinstance(c, Fixed) for c in sk.constraints)
    w = _dot(cv, pt)
    assert _near(FIXED_RGB)(w) == 0
    assert _near(FG_RGB)(w) >= 8                       # back to free-white


def test_standalone_point_locks_green(ed):
    """A point is geometry too: a free-floating sketch point (the
    Show-Points layer's own member) wears the lock the same way -
    one mouth, wherever dots live."""
    cv = ed
    p = cv.model.point(5.0, 6.0)
    cv.update()
    assert _near(FIXED_RGB)(_dot(cv, p)) == 0
    _fix_verb(cv, p)
    assert _near(FIXED_RGB)(_dot(cv, p)) >= 12


def test_fix_takes_the_line_now(ed):
    """M194 R3 MOVED the line R2's snapshot pinned, on the vendor's own
    word ("a point OR OBJECT"): selecting a whole LINE and pressing F
    now files the OBJECT lock - one record, four coordinate rows, the
    stroke turns green. The two-Line F stays the corner fillet's aim."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    ln = cv.model.sketch.lines[-1]
    _fix_verb(cv, ln)
    recs = [c for c in cv.model.sketch.constraints if isinstance(c, Fixed)]
    assert len(recs) == 1 and recs[0].p is ln and len(recs[0].tgt) == 4
    assert _near(FIXED_RGB)(_grab(cv)) >= 60           # the STROKE wears it


# ---- R2: the UNFIX half - the verb again, end to end --------------------
def test_the_lock_locks_the_solver(ed):
    """A LOCK, not a preference: the pinned point's two coordinates are
    the "size and location" the vendor names.  Disturb the point behind
    the solver's back and the solve PUTS IT BACK, exactly; the same
    disturbance on a FREE point stays put - the rows exist because the
    record does."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    pt = cv.model.sketch.lines[-1].b
    target = (pt.x, pt.y)
    _fix_verb(cv, pt)                                  # the lock files
    pt.x, pt.y = 99.0, -13.0                           #  behind its back
    cv._solve()
    assert (pt.x, pt.y) == pytest.approx(target, abs=1e-9)
    free = cv.model.point(1.0, 1.0)                    # the control:
    free.x, free.y = 42.0, 42.0                        #  nothing pins it
    cv._solve()
    assert (free.x, free.y) == pytest.approx((42.0, 42.0), abs=1e-9)


def test_unfix_returns_the_freedom(ed):
    """The vendor's second click frees the SAME two scalars the lock
    took: after the verb again, a disturbance STAYS (no row pulls it
    back) - freedom, pixel-visible as R1's white return, is measured
    here at the solver, the DOF's own court."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    pt = cv.model.sketch.lines[-1].b
    _fix_verb(cv, pt)
    _fix_verb(cv, pt)                                  # the verb AGAIN
    assert not any(isinstance(c, Fixed)
                   for c in cv.model.sketch.constraints)
    pt.x, pt.y = 5.0, 5.0
    cv._solve()
    assert (pt.x, pt.y) == pytest.approx((5.0, 5.0), abs=1e-9)


def test_undo_and_redo_walk_the_lock_both_ways(ed):
    """History is a door like any other: undo takes the lock (and its
    green) OFF, redo puts BOTH back - the record and the paint ride the
    SAME state, never one without the other."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    pt = cv.model.sketch.lines[-1].b
    _fix_verb(cv, pt)
    assert _near(FIXED_RGB)(_dot(cv, pt)) >= 12
    assert cv.undo_op() is True                        # the lock OFF...
    assert not any(isinstance(c, Fixed)
                   for c in cv.model.sketch.constraints)
    assert _near(FIXED_RGB)(_dot(cv, pt)) == 0         #   ...with its green
    assert cv.redo_op() is True                        # and BACK, both
    assert any(isinstance(c, Fixed)
               for c in cv.model.sketch.constraints)
    assert _near(FIXED_RGB)(_dot(cv, pt)) >= 12


def test_file_round_trip_keeps_and_wears_the_lock(ed, tmp_path):
    """The vendor stores the sketch, not a screenshot: save the fixed
    model through the file door, reload it, and the Fixed record
    returns WITH its x/y targets - and a canvas wearing the reloaded
    model shows the green AGAIN. The lock lives in the FILE."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    pt = cv.model.sketch.lines[-1].b
    _fix_verb(cv, pt)
    d = model_to_dict(cv.model)
    path = tmp_path / "locked.json"                    # the file door,
    path.write_text(json.dumps(d), encoding="utf-8")   #  honestly paid
    reloaded = model_from_dict(json.loads(path.read_text(encoding="utf-8")))
    recs = [c for c in reloaded.sketch.constraints if isinstance(c, Fixed)]
    assert len(recs) == 1
    assert (recs[0].p.x, recs[0].p.y) == pytest.approx((pt.x, pt.y),
                                                       abs=1e-9)
    assert recs[0].x == pytest.approx(pt.x, abs=1e-9)  #  the TARGETS
    assert recs[0].y == pytest.approx(pt.y, abs=1e-9)  #   survived too
    c2 = SketchCanvas()                                # a fresh wearer
    c2.set_model(reloaded)
    c2.resize(600, 400)
    c2._scale = 8.0
    c2._snap_grid = False
    #  NO show(): grab() paints unshown; a SHOWN leftover steals the
    #  offscreen platform's enter/leave traffic from later hover tests.
    QApplication.instance().processEvents()
    try:
        assert c2._fix_locked(recs[0].p) is True
        assert _near(FIXED_RGB)(_dot(c2, recs[0].p)) >= 12
    finally:
        c2.deleteLater()


def test_the_verb_on_wrong_answers_mints_nothing(ed):
    """The F key has OTHER owners (two Lines aim the corner fillet) and
    NO owner at empty selection: neither route files a Fixed record -
    the lock's door is the point, full stop (until Rung 3 moves that
    line with the vendor's "or object")."""
    cv = ed
    cv._sel = []
    QTest.keyClick(cv, Qt.Key_F)
    assert not cv.model.sketch.constraints
    _leg(cv, 2, 4, 10, 7)
    _leg(cv, 3, 9, 12, 9)                              # a second, DIAGONAL
    cv._sel = [cv.model.sketch.lines[0],               #  no auto-gifts
               cv.model.sketch.lines[1]]
    before = len(cv.model.sketch.constraints)
    QTest.keyClick(cv, Qt.Key_F)                       # the fillet AIM,
    QApplication.instance().processEvents()            #   not the lock
    assert sum(isinstance(c, Fixed)
               for c in cv.model.sketch.constraints) == 0
    assert len(cv.model.sketch.constraints) == before


def test_welded_visit_leaves_the_weld_whole(ed):
    """A welded corner through the whole lock visit - fix, verb again:
    the identity weld (the SHARED Point that IS coincidence, M177)
    survives untouched, the constraint list ends as empty as it
    started, and no half-record hides anywhere in it."""
    cv = ed
    cv.set_tool("line")
    _click(cv, 2, 4)
    _click(cv, 8, 4)
    _click(cv, 8, 9)
    cv.set_tool("select")
    sk = cv.model.sketch
    shared = sk.lines[0].b
    assert shared is sk.lines[1].a
    structural = list(sk.constraints)                  # the auto H/V, if
    _fix_verb(cv, shared)                              #   the page gave
    assert shared is sk.lines[1].a                     #  any; the weld
    _fix_verb(cv, shared)                              #   rides through
    assert shared is sk.lines[1].a
    assert not any(isinstance(c, Fixed) for c in sk.constraints)
    assert [type(c).__name__ for c in sk.constraints] == \
        [type(c).__name__ for c in structural]


# ---- R3: "or OBJECT" - the lock takes the whole entity -------------------
def _mk_circle(cv, x, y, r):
    return cv.model.sketch.circle(cv.model.point(x, y), r)


def _mk_ellipse(cv, x, y, rx, ry):
    return cv.model.sketch.ellipse(cv.model.point(x, y), rx, ry)


def _mk_arc(cv, ax, ay, mx, my, bx, by):
    return cv.model.sketch.arc(cv.model.point(ax, ay), cv.model.point(mx, my),
                               cv.model.point(bx, by))


def test_object_rows_are_every_owned_scalar():
    """Pure kernel: the record's SHAPE is the vendor's sentence - one
    row per scalar the entity owns. A line speaks four coordinates, a
    circle two plus its radius, an ellipse two plus BOTH semi-axes, an
    arc SIX coordinates and no seventh number (its size IS its three
    points - Radius's own lesson, M94's)."""
    m = SketchModel()
    ln = m.add_line(m.point(0, 0), m.point(5, 5))
    cir = m.sketch.circle(m.point(9, 9), 3.0)
    ell = m.sketch.ellipse(m.point(2, 14), 6.0, 2.5)
    arc = m.sketch.arc(m.point(20, 2), m.point(24, 6), m.point(28, 2))
    for ent, want_rows, want_sizes in ((ln, 4, ()), (cir, 3, ("r",)),
                                       (ell, 4, ("rx", "ry")),
                                       (arc, 6, ())):
        rec = fixed_lock(ent)
        assert rec.sizes() == want_sizes
        rows = [c for c in expand([rec]) if isinstance(c, Fixed)]
        assert len(rows) == want_rows and \
            [r.axis for r in rows] == list(range(want_rows))
        assert rec.tgt == rec.tgt                      # snapshot frozen
        assert len(rec.tgt) == want_rows
    assert fixed_lock(ln).tgt == (0.0, 0.0, 5.0, 5.0)
    assert fixed_lock(cir).tgt == (9.0, 9.0, 3.0)
    assert fixed_lock(ell).tgt == pytest.approx((2.0, 14.0, 6.0, 2.5))
    # the size row carries Radius's own scale (the solver's conditioning)
    rrow = [c for c in expand([fixed_lock(cir)]) if c.axis == 2][0]
    cir.r = 4.0
    assert rrow.residual(None) == pytest.approx(0.01, abs=1e-12)


def test_line_lock_restores_and_the_verb_again_frees(ed):
    """Four rows, four numbers: the line's OWNERSHIP of its endpoints
    is what the object lock takes. Yank a locked endpoint - both
    coordinates return; unfix, yank again - it STAYS (all four rows
    leave with the one record)."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    ln = cv.model.sketch.lines[-1]
    _fix_verb(cv, ln)
    ln.b.x, ln.b.y = 99.0, -13.0
    cv._solve()
    assert (ln.a.x, ln.a.y, ln.b.x, ln.b.y) == pytest.approx(
        (2, 4, 10, 7), abs=1e-6)
    _fix_verb(cv, ln)                                  # the verb again
    assert not any(isinstance(c, Fixed)
                   for c in cv.model.sketch.constraints)
    ln.b.x, ln.b.y = 4.0, 4.0
    cv._solve()
    assert (ln.b.x, ln.b.y) == pytest.approx((4.0, 4.0), abs=1e-9)


def test_circle_lock_pins_size_AND_location(ed):
    """The vendor's OWN words - "size and location": the centre's two
    coordinates AND the radius all return to the record. And the
    STROKE wears the green: a locked circle is trivially "defined" too
    (every scalar rests), yet the RECORD outvotes M186's white - the
    whole circumference answers in the lock's palette."""
    cv = ed
    c = _mk_circle(cv, 12.0, 4.0, 3.0)
    cv.update()
    _fix_verb(cv, c)
    assert _near(FIXED_RGB)(_grab(cv)) >= 60           # the RING is green
    c.c.x, c.c.y, c.r = 1.0, 1.0, 99.0                 # yank everything
    cv._solve()
    assert (c.c.x, c.c.y, c.r) == pytest.approx((12.0, 4.0, 3.0),
                                                abs=1e-6)
    _fix_verb(cv, c)                                   # freed - and the
    assert _near(FIXED_RGB)(_grab(cv)) == 0            #  green leaves too


def test_ellipse_and_arc_locks_whole_themselves(ed):
    """An ellipse owes FOUR numbers (centre, BOTH axes) and an arc owes
    SIX coordinates - and the lock collects them all.  Yank the
    ellipse's ry and the arc's BULGE point: both return; no size row
    exists for the arc, and none is needed - pin the three points and
    its circumradius rides along (that IS its size)."""
    cv = ed
    e = _mk_ellipse(cv, 10.0, 5.0, 5.0, 2.0)
    a = _mk_arc(cv, 2.0, 12.0, 6.0, 16.0, 10.0, 12.0)
    _fix_verb(cv, e)
    _fix_verb(cv, a)
    e.ry, e.rx = 50.0, 50.0
    a.m.x, a.m.y = 6.0, 2.0
    cv._solve()
    assert (e.rx, e.ry) == pytest.approx((5.0, 2.0), abs=1e-6)
    assert (a.a.x, a.a.y, a.m.x, a.m.y, a.b.x, a.b.y) == pytest.approx(
        (2.0, 12.0, 6.0, 16.0, 10.0, 12.0), abs=1e-6)
    (cx, cy), r0 = a.circle()
    a.m.x = 6.0                                        # a mid yank the
    a.m.y = 15.9                                       #  points alone
    cv._solve()                                        #  re-impose
    (_cx, _cy), r1 = a.circle()
    assert r1 == pytest.approx(r0, abs=1e-6)


def test_welded_neighbour_feels_the_shared_pin(ed):
    """Honest side-effect law: the lock pins SCALARS, and a weld means
    SHARED scalars (identity IS coincidence, M177).  Fixing line 2
    freezes the weld's coordinates - which line 1 also lives off - so
    the shared point returns when yanked, while line 1's OWN far end
    stays free: the neighbour feels the pin it SHARES and nothing it
    does not. (The far end is only reachable through its own record.)"""
    cv = ed
    cv.set_tool("line")
    _click(cv, 2, 4)
    _click(cv, 8, 4)                                   # weld at (8,4)
    _click(cv, 8, 9)                                   #   straight up...
    cv.set_tool("select")
    l1, l2 = cv.model.sketch.lines
    shared = l1.b
    assert shared is l2.a
    _fix_verb(cv, l2)
    assert 25 <= _near(FIXED_RGB)(_grab(cv)) < 200     # only line 2 green
    #   (a 5-unit stroke: dozens of honest pixels, NOT the whole page)
    shared.x, shared.y = 20.0, 20.0                    # yank the WELD...
    l1.a.x = 50.0                                      # ...and line 1's
    cv._solve()                                        #   far end
    assert (shared.x, shared.y) == pytest.approx((8.0, 4.0), abs=1e-6)
    assert abs(l1.a.x - 50.0) < 1e-9                   # the far end stayed
    #                                                     (its own anchor)
    # NB: line 1 carries auto-H/coincedent-free rows; a.x moved because
    # NOTHING pins it - that is the honesty this gate pays for.


def test_object_lock_wears_the_lock_after_a_file_visit(ed, tmp_path):
    """The object record lives in the FILE with its targets, and a
    brand-new canvas wearing the reloaded model paints the ring green
    again - R2's law, object edition (and no point smuggled into the
    points array: the stamp is a reference, not a coordinate pair)."""
    cv = ed
    c = _mk_circle(cv, 12.0, 4.0, 3.0)
    _fix_verb(cv, c)
    d = model_to_dict(cv.model)
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(d), encoding="utf-8")
    reloaded = model_from_dict(json.loads(path.read_text(encoding="utf-8")))
    recs = [x for x in reloaded.sketch.constraints if isinstance(x, Fixed)]
    assert len(recs) == 1 and len(recs[0].tgt) == 3
    assert recs[0].tgt == pytest.approx((12.0, 4.0, 3.0))
    c2 = SketchCanvas()                                # unshown wearer!
    c2.set_model(reloaded)
    c2.resize(600, 400)
    c2._scale = 8.0
    c2._snap_grid = False
    QApplication.instance().processEvents()
    try:
        assert c2._fix_locked(recs[0].p) is True
        assert _near(FIXED_RGB)(_grab(c2)) >= 60       # green from file
    finally:
        c2.deleteLater()


def test_locked_line_keeps_dots_their_own_ink(ed):
    """M191 survives the object: the dots a locked line OWNS keep
    their own sentence (white = free of OTHER geometry).  The object's
    green rides the STROKE; it never recruits the dots - the badge and
    the ink carry the lock, the dot carries coincidence."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    ln = cv.model.sketch.lines[-1]
    _fix_verb(cv, ln)
    w = _dot(cv, ln.b)
    assert _near(FG_RGB)(w) >= 8                       # white dot speaks
    assert _near(FIXED_RGB)(_grab(cv)) >= 60           # green stroke too
    assert w.shape[0] >= 13                            # (window intact)


def test_object_undo_and_redo_walk_record_and_green(ed):
    """R2's history law, object edition: undo takes the stroke's green
    off WITH the record; redo returns both - never one without the
    other."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    ln = cv.model.sketch.lines[-1]
    _fix_verb(cv, ln)
    assert _near(FIXED_RGB)(_grab(cv)) >= 60
    assert cv.undo_op() is True
    assert not any(isinstance(c, Fixed)
                   for c in cv.model.sketch.constraints)
    assert _near(FIXED_RGB)(_grab(cv)) == 0
    assert cv.redo_op() is True
    assert any(isinstance(c, Fixed) for c in cv.model.sketch.constraints)
    assert _near(FIXED_RGB)(_grab(cv)) >= 60
