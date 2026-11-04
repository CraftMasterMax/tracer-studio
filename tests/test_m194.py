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

Rung 2 pins the UNFIX half ("To unfix ... select the Fix/UnFix tool
again, then click"): record gone, green gone, DOF returns, undo and
file round-trip.  Rung 3 pays "or OBJECT": fixing a line/arc/circle/
ellipse locks size AND location, all the variables it owns.
"""
import math

import pytest

pytest.importorskip("PySide6")

import numpy as np                                                # noqa
from PySide6.QtCore import Qt                                     # noqa
from PySide6.QtGui import QColor, QImage                          # noqa
from PySide6.QtTest import QTest                                  # noqa
from PySide6.QtWidgets import QApplication                        # noqa

from tracer.core.sketch.model import SketchModel                  # noqa
from tracer.core.sketch.constraints import Distance, Fixed        # noqa
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


def test_fix_answers_only_points_for_now(ed):
    """Honest CURRENT law (Rung 3 will MOVE this line with the vendor's
    "or object"): today the F verb locks a POINT; selecting a whole
    LINE and pressing F files NOTHING - no record, no green, no
    half-lock pretending to be the object sentence."""
    cv = ed
    _leg(cv, 2, 4, 10, 7)
    ln = cv.model.sketch.lines[-1]
    _fix_verb(cv, ln)
    assert not any(isinstance(c, Fixed)
                   for c in cv.model.sketch.constraints)
    assert _near(FIXED_RGB)(_grab(cv)) == 0
