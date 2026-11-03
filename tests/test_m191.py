"""M191 R1: THE SKETCH TELLS THE TRUTH AT ITS POINTS [endpoint truth].

The vendor law, verbatim (help.autodesk.com Fusion-Sketch, "Distinguish
coincident constraints", GUID-685B9D79): "When end points of lines or
splines are not constrained to other geometry, they are displayed as
white dots" - "Point to point coincident constraints show no dot" -
and the repair verb in the same page: "To remove a coincident
constraint, select the point then right-click and select Delete
Coincident." No parametric clone ships this; ours draws EVERY point
identically today, so the sketch says nothing about where its loose
ends are.

Our kernel speaks coincidence in two dialects - IDENTITY (a snap
reuses the Point object: "identity IS coincidence", M177) and RECORDS
(Coincident / PointOnLine / PointOnCircle constraints) - and the rung
answers BOTH with ONE mouth (endpoints.py: paint == menu == act).
"OTHER GEOMETRY" is the whole qualifier: a point pinned to the number
plane keeps its dot (the dot speaks coincidence, not mobility), and
a fully-dimensioned corner that touches nothing else keeps it too -
the vendor's page hides the dot at COINCIDENT ends and nowhere else.
No hex is copied: the dot wears our reserved DEFINED white (SKETCH
full), the same ink the defined entities wear.
"""
import pytest

pytest.importorskip("PySide6")

import numpy as np                                                   # noqa
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt                # noqa
from PySide6.QtGui import QColor, QImage, QMouseEvent                 # noqa
from PySide6.QtTest import QTest                                      # noqa
from PySide6.QtWidgets import QApplication                           # noqa
from tracer.ui import theme                                          # noqa

from tracer.core.sketch import endpoints                             # noqa
from tracer.core.sketch.constraints import (Coincident, Distance,     # noqa
                                            Fixed, Horizontal,
                                            Midpoint)


def _fix(s, p, x, y):
    s.constrain(Fixed(p, x=x), Fixed(p, y=y))


@pytest.fixture
def qapp():
    yield QApplication.instance() or QApplication([])


_LIVE: list = []


@pytest.fixture(autouse=True)
def _close_live():
    """ROUTING LAW (test_m164's lesson): every SHOWed canvas CLOSES
    with its test - offscreen windows share the pointer."""
    yield
    while _LIVE:
        w = _LIVE.pop()
        w.close()
        w.deleteLater()
    QApplication.processEvents()


def _editor(qapp):
    from tracer.core.sketch.model import SketchModel
    from tracer.ui.sketcheditor import SketchCanvas
    cv = SketchCanvas()
    cv.set_model(SketchModel())
    cv.resize(600, 400)
    cv.show()
    for _ in range(3):
        qapp.processEvents()
    _LIVE.append(cv)
    return cv


# ---- the ONE mouth: both dialects answer --------------------------------------

def test_identity_welds_and_records_weld_qapp_free(qapp):
    from tracer.core.sketch.model import SketchModel
    m = SketchModel()
    s = m.sketch
    a = m.point(0, 0)
    b = m.point(30, 0)
    c = m.point(60, 0)
    m.add_line(a, b)
    m.add_line(b, c)                      # IDENTITY: b serves two roles
    d = m.point(30, 40)
    e = m.point(60, 40)
    m.add_line(d, e)
    assert endpoints.is_welded(s, b), "shared by two segments: no dot"
    assert not endpoints.is_welded(s, a), "a loose end is loose"
    assert not endpoints.is_welded(s, d), "a float is loose"
    s.constrain(Coincident(e, c))          # RECORDS weld too
    assert endpoints.is_welded(s, e), "a Coincident paper is a weld"
    assert endpoints.is_welded(s, c), "...on BOTH endpoints it names"


# ---- the canvas answers, and the pixels SHIP it ---------------------------------

def _fg_band(cv, pt, half=8):
    """Pixels around a point, in the DEFINED-white family (the dot's
    ink). TIGHT window: the DEFINED STEEL also wears this white, so a
    wide band measures the line, not the dot; inside 6 px a loose
    end's FILL dominates and a welded corner is hollow. RGBA-normalized
    grab (the BGRA trap, M190 R2 law)."""
    img = cv.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    buf = np.frombuffer(img.constBits().tobytes(), np.uint8).reshape(
        img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), :3]
    q = cv.w2s(pt.x, pt.y)
    x0, y0 = int(q.x()), int(q.y())
    band = buf[max(0, y0 - half):y0 + half,
               max(0, x0 - half):x0 + half].reshape(-1, 3).astype(int)
    white = QColor(theme.SKETCH["full"]).getRgb()[:3]
    return int((np.abs(band - np.array(white)).max(axis=1) < 46).sum())


def test_a_loose_end_ships_the_white_dot(qapp):
    cv = _editor(qapp)
    m = cv.model
    a = m.point(-60, -30)
    b = m.point(0, -30)
    c = m.point(60, 30)
    m.add_line(a, b)
    m.add_line(b, c)
    _fix(m.sketch, a, -60, -30)           # a: anchored, but welded to
    cv._solve()                            #   NOTHING (other geometry
    assert cv._point_welded(b) is True, "identity weld hides the dot"
    assert cv._point_welded(a) is False, "a Fixed pin is not OTHER GEOMETRY"
    assert cv._point_welded(c) is False, "the loose end wears the dot"
    qapp.processEvents()
    assert _fg_band(cv, c) >= 12, "the shipped film frame HOLDS the dot"
    assert _fg_band(cv, b) < _fg_band(cv, c), \
        "the welded corner does not fake one (no blue ink there either)"


def test_no_witness_fails_open_to_the_dot(qapp):
    cv = _editor(qapp)
    m = cv.model
    ln = m.add_line(m.point(0, 0), m.point(10, 0))
    cv._last_result = None                # no solve has EVER answered
    assert cv._point_welded(ln.a) is False, \
        "no witness, no claim - M167's fail-OPEN law rides the dot too"


# ---- the VERB: Delete Coincident, at the dot's own menu --------------------------

def test_the_menu_offers_the_verb_only_at_a_weld(qapp):
    cv = _editor(qapp)
    m = cv.model
    a = m.point(-60, -30)
    b = m.point(0, -30)
    c = m.point(60, 30)
    m.add_line(a, b)
    m.add_line(b, c)
    cv._solve()
    cv._sel = [c]                          # the loose (dotted) end
    names = [x.text() for x in cv._build_menu().actions()]
    assert "Delete Coincident" not in names, \
        "the menu never lies about a weld that isn't"
    cv._sel = [b]                          # the welded corner
    names = [x.text() for x in cv._build_menu().actions()]
    assert "Delete Coincident" in names, "the vendor's own verb, at the dot"


def test_the_verb_frees_the_point_and_the_dot_arrives(qapp):
    cv = _editor(qapp)
    m = cv.model
    a = m.point(-60, -30)
    b = m.point(0, -30)
    c = m.point(60, 30)
    l1 = m.add_line(a, b)                  # role 1: b stays HERE
    l2 = m.add_line(b, c)                  # role 2: this end splits off
    cv._solve()
    assert cv._point_welded(b)
    cv.act_delete_coincident(b)
    qapp.processEvents()
    assert l1.b is b, "the picked point keeps its FIRST role"
    assert l2.a is not b, "the later role got a fresh copy"
    assert l2.a.x == pytest.approx(b.x) and l2.a.y == pytest.approx(b.y), \
        "the split opens AT the corner - the copy starts coincident"
    assert not cv._point_welded(b) and not cv._point_welded(l2.a), \
        "both halves wear the white dot with the click - the receipt"


def test_the_record_path_deletes_the_paper(qapp):
    cv = _editor(qapp)
    m = cv.model
    a = m.point(-60, 0)
    b = m.point(0, 0)
    d = m.point(-60, 40)
    e = m.point(0, 40)
    m.add_line(a, b)
    m.add_line(d, e)
    m.sketch.constrain(Coincident(b, e))   # paper weld, separate objects
    cv._solve()
    assert cv._point_welded(b)
    hist_before = len(cv._hist)
    cv.act_delete_coincident(b)
    assert not any(isinstance(c, Coincident)
                   for c in m.sketch.constraints), "the paper is gone"
    assert len(cv._hist) == hist_before + 1, "ONE undo step for one weld"
    cv.undo_op()
    assert any(isinstance(c, Coincident)
               for c in m.sketch.constraints), "undo restores the weld"


def test_a_stale_click_leaves_zero_trace(qapp):
    cv = _editor(qapp)
    m = cv.model
    ghost = m.point(999, 999)              # minted, never added to geometry
    hist_before = len(cv._hist)
    cv.act_delete_coincident(ghost)
    assert len(cv._hist) == hist_before, "a stale point: no snapshot, no debt"


# ---- R2: EDIT PARKS THE MARKER (LAW-10, completed) --------------------------------
# The API doc names the behavior outright: "the behavior you see in
# the user interface when you manually edit a sketch where Fusion
# AUTOMATICALLY ROLLS THE TIMELINE BACK while you're editing the
# sketch." M161 shipped the half where the target sat BEHIND the
# marker; the whole law parks the marker just past the feature being
# edited - even from a clean end-of-timeline start - and sends it
# HOME when the maker leaves. The marker is view state (M88), so the
# park can never poison a file; LAW-8's words ride: hidden, never
# deleted.

from PySide6.QtWidgets import QApplication                           # noqa
from tracer.ui.renderer import SceneRenderer                         # noqa


@pytest.fixture(scope="module")
def qapp2():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win2(qapp2):
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp2.processEvents()
    yield w
    w._unsaved = False
    r.close()
    w.close()


def _sketch_at(win, i):
    """Plate, [fillers], Boss (a REAL sketched extrude), Plate2."""
    from tracer.core.document import PrimitiveFeature, ExtrudeFeature
    win.new_document()
    win._edit_park_on = False            # module-scoped win2: a prior
    win._edit_park = None                #   test's visit must not leak
    d = win.doc
    d.add(PrimitiveFeature(name="Plate", kind="box", op="union",
                           dims={"dx": 40.0, "dy": 40.0, "dz": 4.0}))
    for k in range(i - 1):
        d.add(PrimitiveFeature(name=f"F{k}", kind="box", op="union",
                               dims={"dx": 8.0, "dy": 8.0, "dz": 2.0}))
    boss = d.add(ExtrudeFeature(
        name="Boss", outer=np.array([[0, 0], [10, 0], [10, 5]], float),
        height=4.0, sid=777000 + i,               # M191 R3: a REAL sid -
        sketch={"name": "SketchBoss",              #   the display-sync
                "lines": [], "circles": [], "arcs": [], "points": [],
                "constraints": [], "dims": []}))   #   finds features by it
    d.add(PrimitiveFeature(name="Plate2", kind="box", op="union",
                           dims={"dx": 40.0, "dy": 40.0, "dz": 1.0}))
    win.recompute()
    return d, boss


def test_editing_parks_the_marker_even_from_the_end(win2, qapp2):
    d, boss = _sketch_at(win2, 2)
    assert d.rollback_to is None                # a clean, FULL timeline
    win2.edit_sketch(boss)
    qapp2.processEvents()
    assert d.rollback_to == 3, \
        "the marker parks JUST PAST the feature being edited"
    assert win2.stack.currentWidget() is win2._sketch_page
    assert win2._edit_park_on and win2._edit_park is None, \
        "the memory holds HOME (None) - the position the maker was at"


def test_leaving_sends_the_marker_home(win2, qapp2):
    d, boss = _sketch_at(win2, 2)
    win2.edit_sketch(boss)
    qapp2.processEvents()
    win2._leave_sketch_page()                   # the Back door
    qapp2.processEvents()
    assert d.rollback_to is None, "the timeline is WHOLE again"
    assert win2._edit_park is None, "the memory retires with the visit"


def test_a_prior_user_park_survives_the_visit(win2, qapp2):
    d, boss = _sketch_at(win2, 2)
    win2._apply_rollback(1)                     # the maker parked at 1
    win2.edit_sketch(boss)
    qapp2.processEvents()
    assert d.rollback_to == 3, "the edit parks at the target anyway"
    win2._leave_sketch_page()
    qapp2.processEvents()
    assert d.rollback_to == 1, "and RESTORES where the maker left it"


def test_editing_the_last_feature_parks_home(win2, qapp2):
    d, boss = _sketch_at(win2, 3)               # Boss: last REAL feature
    i = d.features.index(boss)
    win2.edit_sketch(boss)
    qapp2.processEvents()
    assert d.rollback_to in (i + 1, None), \
        "the park lands just past the edited feature - and when that " \
        f"IS the end the band ENDS (total={len(d.features)} i={i} " \
        f"rb={d.rollback_to}); it never hides the Boss itself"
    win2._leave_sketch_page()
    assert d.rollback_to is None, "and leaving is home"


def test_a_new_document_drops_the_memory(win2, qapp2):
    d, boss = _sketch_at(win2, 2)
    win2.edit_sketch(boss)
    qapp2.processEvents()
    win2.new_document()                         # a hard context switch
    assert win2._edit_park is None, \
        "the park memory is bound to the doc it parked"
    assert win2.doc.rollback_to is None


# ---- R3: THE SKETCH CARRIES ITS OWN EYES [per-sketch display truth] ----------
# The vendor stores WHAT A SKETCH SHOWS on the sketch itself, in the
# FILE: the API exposes isProjectedGeometryShown / areConstraintsShown
# on the Sketch object (palette GUID-4183A4B7: "displayed when the
# sketch is not active" is a SEPARATE per-sketch set). No parametric
# clone persists these; a global toolbar switch forgets the moment
# you leave. Three gates of law here: the flags ROUND-TRIP THE FILE,
# hiding a layer also retires its HITS (the menu and the clicks never
# lie about markup the eye cannot see), and Back - the discard door -
# drops STROKES but keeps the EYES (M162's visibility law, one level
# down: display is not design, so no history capture either).

def test_display_flags_round_trip_the_file():
    from tracer.core.sketch.model import SketchModel, model_to_dict, \
        model_from_dict
    m = SketchModel()
    a, b = m.point(0, 0), m.point(40, 0)
    m.add_line(a, b)
    assert m.vis == {"refs": True, "dims": True, "constraints": True}, \
        "a fresh sketch shows everything - the pre-M191 file still does"
    m.vis["dims"] = False
    back = model_from_dict(model_to_dict(m))
    assert back.vis["dims"] is False, "the flag rode the dict (and so \
the FILE, which is these dicts as JSON)"
    assert back.vis["refs"] and back.vis["constraints"], "untouched \
eyes stay open"
    legacy = model_to_dict(m)
    legacy.pop("vis")                           # a file from BEFORE the rung
    assert all(model_from_dict(legacy).vis.values()), \
        "an old file wakes with every eye open, never a KeyError"


def test_hidden_layers_keep_no_phantom_hits(qapp):
    cv = _editor(qapp)
    m = cv.model
    a, b = m.point(-40, 0), m.point(40, 0)
    ln = m.add_line(a, b)
    m.sketch.constrain(Distance(a, b, 80.0))
    m.sketch.constrain(Horizontal(ln))
    m.refs = [{"pts": [[-50.0, 25.0], [50.0, 25.0]], "closed": False}]
    cv._solve()
    _paint(cv)                                  # OFFSCREEN LAW: grab() is
    #  the synchronous paint - processEvents can skip one, and the hit
    #  lists are PER-PAINT (M164 R2), so an unforced read sees a stale
    #  frame (the first run of this gate proved it)
    assert cv._dim_hits and cv._constraint_hits, \
        "the visible markup is real on the pixels AND clickable"
    # the chip's WORDS wear the DEFINED white (FG ink on a bg2 plate -
    # the DIMC green is the M9x heritage; a census must measure what
    # the painter actually puts down)
    dims_px = _ink_near(cv, (0.0, 4.0), QColor(theme.SKETCH["full"]),
                        half=20)
    assert dims_px > 20, "the dimension TEXT is on the pixels"
    refs_px = _ink_near(cv, (0.0, 25.0), QColor(theme.SKETCH["projected"]),
                        half=20, tol=60)
    assert refs_px > 15, "the projected dash is on the pixels too"
    cv.set_show_layer("dims", False)
    cv.set_show_layer("constraints", False)
    cv.set_show_layer("refs", False)
    _paint(cv)
    assert not cv._dim_hits, "hidden dims keep no click target - the \
double-click door cannot answer a label the eye cannot see"
    assert not cv._constraint_hits, "hidden glyphs keep no hover ring \
either (M164 R2's ring cannot circle a vanished mark)"
    assert _ink_near(cv, (0.0, 4.0), QColor(theme.SKETCH["full"]),
                     half=20) < max(6, dims_px // 4), \
        "the shipped frame LOST the chip's words (pixel census, not a \
state assertion)"
    assert _ink_near(cv, (0.0, 25.0), QColor(theme.SKETCH["projected"]),
                     half=20, tol=60) < 10, "the projected dash went \
dark too (same tol as the on-census - a fair before/after)"


def _paint(cv):
    """Force one SYNCHRONOUS paint. Offscreen processEvents may skip a
    repaint entirely, and the hit lists are per-paint state - grab()
    is the house door (same one _ink_near uses)."""
    cv.grab()


def _ink_near(cv, world, color, half=20, tol=46):
    """Pixels near a world point within the color family (RGBA-
    normalized grab - the BGRA trap law). tol widens for THIN dashed
    ink: the 1.4px projected dash anti-aliases far from its nominal
    violet (measured (139,108,188) vs (179,132,242) - 54 apart)."""
    img = cv.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    buf = np.frombuffer(img.constBits().tobytes(), np.uint8).reshape(
        img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), :3]
    q = cv.w2s(*world)
    x0, y0 = int(q.x()), int(q.y())
    band = buf[max(0, y0 - half):y0 + half,
               max(0, x0 - half):x0 + half].reshape(-1, 3).astype(int)
    return int((np.abs(band - np.array(color.getRgb()[:3])).max(axis=1)
                < tol).sum())


def test_the_empty_canvas_offers_the_three_eyes(qapp):
    cv = _editor(qapp)
    m = cv.model
    m.add_line(m.point(-40, 0), m.point(40, 0))
    cv._solve()
    cv._sel = []
    acts = {a.text(): a for a in cv._build_menu().actions() if a.text()}
    trio = ("Show constraint symbols", "Show dimension values",
            "Show projected geometry")
    for t in trio:
        assert t in acts and acts[t].isCheckable(), f"{t} rides the menu"
        assert acts[t].isChecked(), "a fresh sketch answers CHECKED"
    cv.model.vis["dims"] = False
    acts = {a.text(): a for a in cv._build_menu().actions() if a.text()}
    assert not acts["Show dimension values"].isChecked(), \
        "the check mirrors the SKETCH's own answer, not a global state"
    acts["Show dimension values"].toggle()      # the click itself
    assert cv.model.vis["dims"] is True, "one click flips the flag"


def test_history_carries_the_eyes(qapp):
    cv = _editor(qapp)
    m = cv.model
    m.add_line(m.point(-40, 0), m.point(40, 0))
    cv._push_hist()
    cv.set_show_layer("refs", False)
    assert cv.model.vis["refs"] is False
    assert cv.undo_op(), "the toggle was one step"
    assert cv.model.vis["refs"] is True, "undo reopens the eye - the \
flags ride history like the projected edges beside them (M82's seam)"


def test_back_discards_strokes_but_keeps_the_eyes(win2, qapp2):
    from tracer.core.sketch.model import SketchModel
    d, boss = _sketch_at(win2, 1)
    assert boss.sketch.get("vis", {}).get("dims", True) is True, \
        "a pre-M191 feature dict wakes with every eye open"
    win2.edit_sketch(boss)
    qapp2.processEvents()
    cv = win2.sketch
    cv.model.add_line(cv.model.point(5.0, 5.0), cv.model.point(15.0, 15.0))
    cv.set_show_layer("dims", False)            # one honest mouth
    lines_before = len(boss.sketch["lines"])
    win2._leave_sketch_page()                   # the DISCARD door
    qapp2.processEvents()
    assert boss.sketch["vis"]["dims"] is False, \
        "the eye persists to the FEATURE (and so to the file) - Back \
dropped the stroke, not the display"
    assert len(boss.sketch["lines"]) == lines_before, \
        "the stroke WAS discarded - display is not design (M162)"
    assert d.dirty, "a kept eye is a real change: the doc is dirty"
    from tracer.core.document import Document
    revived = Document.from_dict(d.to_dict())   # save/load IS these dicts
    boss2 = next(f for f in revived.features if f.name == "Boss")
    cv.set_model(SketchModel())                 # the editor's visit is
    win2._editing_sid = None                    #   over before the rebirth
    win2.doc = revived
    win2.edit_sketch(boss2)
    qapp2.processEvents()
    assert win2.sketch.model.vis["dims"] is False, \
        "a REVIVED file reopens with the same eye closed - the vendor's \
sentence, end to end"
    assert not cv.model.sketch.lines, "the discarded stroke stayed \
discarded through the file too"


# ---- R4: SHIFT SUMMONS THE MIDPOINT [GUID-F0491540] --------------------------
# The vendor's shortcut page ("Sketch Coincident Constraint at Midpoint |
# Shift") hands Shift a second voice: the INVERSE of Ctrl's brake (M186
# R2 suppresses inference; Shift CRIES FOR one). Hold Shift while a new
# endpoint lands and the MIDPOINT coincidence is summoned ahead of even
# a nearer magnet - and the fresh weld outranks M173's ortho leash, the
# same "a stated constraint beats a suggestion" law one level up: an
# ortho re-mint here would orphan the just-filed Midpoint record on a
# point no line owns.
# Scene math (scale 4, centre (0,0), magnet 9 px = 2.25 world):
#   base line (-2,20)-(2,24): midpoint (0,22); cursor (1.25,23.0) sits
#   1.25 from the ENDPOINT and 1.60 from the MIDPOINT - nearer the
#   endpoint, both inside the magnet. Shift is the ONLY thing that can
#   flip that race.

def _scr4(x, y):
    return QPoint(int(round(300 + 4.0 * x)), int(round(200 - 4.0 * y)))


def _summon_scene(cv):
    cv._snap_grid = False          # m173's law: no grid candidate may
    m = cv.model                   #   enter the endpoint/midpoint race
    a, b = m.point(-2.0, 20.0), m.point(2.0, 24.0)
    ln = m.add_line(a, b)
    return m, ln, b


def test_the_key_promotes_the_midpoint_over_a_nearer_rival():
    from tracer.core import snaps
    from tracer.core.sketch.model import SketchModel
    m = SketchModel()
    a, b = m.point(-2, 20), m.point(2, 24)
    ln = m.add_line(a, b)
    plain = snaps.best(m.sketch, 1.25, 23.0, 2.25)
    assert plain.kind == "endpoint" and plain.pt is b
    summon = snaps.best(m.sketch, 1.25, 23.0, 2.25, prefer="midpoint")
    assert summon.kind == "midpoint" and summon.entity is ln
    assert summon.pt is None, "a line-mid is no stored Point: the mint "  \
        "+ autolink path is the one that files the Midpoint"
    assert snaps.candidates(m.sketch, 1.25, 23.0, 2.25,
                            prefer="midpoint")[0].kind == "midpoint"
    assert snaps.best(m.sketch, 1.25, 23.0, 2.25,
                      prefer="bogus").kind == "endpoint", \
        "a preference for a kind NOT in the tolerance changes nothing"


def test_shift_summons_the_midpoint_weld(qapp):
    cv = _editor(qapp)
    m, ln, b = _summon_scene(cv)
    cv.set_tool("line")
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, _scr4(-8, 18))
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, _scr4(-8, 18))
    QTest.mousePress(cv, Qt.LeftButton, Qt.ShiftModifier, _scr4(1.25, 23.0))
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.ShiftModifier, _scr4(1.25, 23.0))
    assert len(m.sketch.lines) == 2
    new = m.sketch.lines[1]
    assert (new.b.x, new.b.y) == (0.0, 22.0), \
        "the end landed EXACTLY on the midpoint - summoned, not grazed"
    assert new.b is not b, "the midpoint minted its own Point"
    rec = [c for c in m.sketch.constraints if isinstance(c, Midpoint)]
    assert len(rec) == 1 and rec[0].p is new.b and rec[0].line is ln
    assert rec[0].src == "snap", "paper autolink - free and live (M120)"
    assert endpoints.is_welded(m.sketch, new.b), \
        "the R1 rhyme: the coincidence you summoned closes its own dot"
    assert new.b.y != 18.0 and cv._line_start is None, \
        "the ortho leash would have bent this end to (-8,18)'s line - "  \
        "the fresh WELD outranked it (guard) and the chain ended (L25)"


def test_without_the_key_the_nearer_endpoint_wins_identity(qapp):
    cv = _editor(qapp)
    m, ln, b = _summon_scene(cv)
    cv.set_tool("line")
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, _scr4(-8, 18))
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, _scr4(-8, 18))
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, _scr4(1.25, 23.0))
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, _scr4(1.25, 23.0))
    assert len(m.sketch.lines) == 2
    assert m.sketch.lines[1].b is b, "plain magnet: nearest endpoint, "  \
        "identity reuse - the OLD truth unchanged by the rung"
    assert not any(isinstance(c, Midpoint) for c in m.sketch.constraints), \
        "no Midpoint record without the key: the summon IS the key"


def _mmove(cv, x, y, mods=Qt.NoModifier):
    p = QPointF(300.0 + 4.0 * x, 200.0 - 4.0 * y)
    QApplication.sendEvent(
        cv, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.NoButton, Qt.NoButton, mods))


def test_the_hover_glyph_promotes_with_the_key(qapp):
    cv = _editor(qapp)
    _summon_scene(cv)
    cv.set_tool("line")
    _mmove(cv, 1.25, 23.0)
    assert cv._snap_obj is not None and cv._snap_obj.kind == "endpoint"
    _mmove(cv, 1.25, 23.0, Qt.ShiftModifier)      # real modifier state
    assert cv._snap_obj.kind == "midpoint", \
        "the promise is on the GLYPH before the click: Shift shows the \
midpoint it WILL weld, though the endpoint sits closer"


def test_the_key_still_orthos_when_no_midpoint_answers(qapp):
    cv = _editor(qapp)
    _summon_scene(cv)                              # midpoint far at (0,22)
    cv.set_tool("line")
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, _scr4(-8, -6))
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, _scr4(-8, -6))
    QTest.mousePress(cv, Qt.LeftButton, Qt.ShiftModifier, _scr4(2.0, -5.25))
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.ShiftModifier, _scr4(2.0, -5.25))
    new = cv.model.sketch.lines[1]
    assert (new.b.x, new.b.y) == (2.0, -6.0), \
        "M173's voice is intact: no midpoint answering, Shift is the \
plain ortho leash - the guard is inert"
    assert not any(isinstance(c, Midpoint) for c in
                   cv.model.sketch.constraints)
