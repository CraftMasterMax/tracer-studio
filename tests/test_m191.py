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
from PySide6.QtGui import QColor, QImage                             # noqa
from PySide6.QtWidgets import QApplication                           # noqa
from tracer.ui import theme                                          # noqa

from tracer.core.sketch import endpoints                             # noqa
from tracer.core.sketch.constraints import Coincident, Fixed         # noqa


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
        height=4.0,
        sketch={"name": "SketchBoss",
                "lines": [], "circles": [], "arcs": [], "points": [],
                "constraints": [], "dims": []}))
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
