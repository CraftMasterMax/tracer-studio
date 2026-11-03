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
Anchoring also reads the solver's witness (a fully-defined corner is
AT REST, M186 R1's law); no converged witness fails OPEN to the dot
(M167's law). No hex is copied: the dot wears our reserved DEFINED
white (SKETCH full), the same ink the defined entities wear.
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

def _fg_band(cv, pt, half=14):
    """Pixels around a point, in the DEFINED-white family (the dot's
    ink). RGBA-normalized grab (the BGRA trap, M190 R2 law)."""
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
    _fix(m.sketch, a, -60, -30)           # a: anchored, but NOT welded
    cv._solve()
    assert cv._point_welded(b) is True, "identity weld hides the dot"
    assert cv._point_welded(a) is True, "at rest hides the dot (M186 law)"
    assert cv._point_welded(c) is False, "the loose end wears the dot"
    qapp.processEvents()
    assert _fg_band(cv, c) > 10, "the shipped film frame HOLDS the dot"
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
