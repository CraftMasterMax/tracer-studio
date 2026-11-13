"""M201 R37 - the BREAKOUT SECTION tool and its door, on the sheet.

[Create breakout section views, verbatim] "Click to place the first
point of the breakout section profile" / "Continue placing points as
needed. The Check icon displays after you place at least 3 points" /
"Click the Check icon to complete the breakout section profile" - the
polyline the drafter clicks, answered here through the house's own
double-click finishing gesture (M138's law: the vendor's polyline
grammar) and a click on the first point once three stand. These gates
drive the canvas with REAL mouse events and the window's handlers with
the ask() spy - stricter than peeking widgets, since the conftest
guard fails ANY real modal in headless pytest by design (the dialog's
PIXELS live in the film). [Breakout section views] "A drawing view
can contain only one breakout section", "remove material to a
specified depth", and [reference dialog] "half of your design's depth
by default" are each refused or stored exactly as printed. DEVIATION
declared and gated (the page prints it neither way): our four
standards are PEERS, not parent-and-child, so no other view inherits
a cut - the ink OUTSIDE the broken-out view never changes.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt                 # noqa: E402
from PySide6.QtGui import QMouseEvent                        # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402
import numpy as np                                           # noqa: E402

from tracer.core.document import (Document, HoleFeature,     # noqa: E402
                                  PrimitiveFeature)
from tracer.ui import cmddialog                              # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    """m225's proven plate: 40x30x6, a through bore, a blind pocket -
    real interior for a breakout to expose, and a front view whose ink
    must NEVER hear that the top was cut."""
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 800)
    w.show()
    qapp.processEvents()
    w.new_document()
    d = w.doc
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    d.add(HoleFeature(name="bore", op="subtract", center=(20, 15, 6),
                      normal=(0, 0, -1), radius=5.0, depth=6,
                      cut_length=6, through=True))
    d.add(PrimitiveFeature(name="pocket", op="subtract", kind="box",
                           dims={"dx": 20, "dy": 10, "dz": 3},
                           placement=(10.0, 10.0, 0.0)))
    w.recompute()
    w.action_new_drawing()
    w._show_page(w._drawing_page)
    qapp.processEvents()
    yield w
    w._unsaved = False
    w._discard_guard = lambda: True
    w.close()
    r.close()


def _p2c(cv, mm):
    z = cv._zoom
    return QPointF((mm[0] - cv._center.x()) * z + cv.width() / 2.0,
                   (cv._center.y() - mm[1]) * z + cv.height() / 2.0)


def _click(cv, mm):
    c = _p2c(cv, mm)
    for t in (QMouseEvent.Type.MouseButtonPress,
              QMouseEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(t, c, c, Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        (cv.mousePressEvent if t == QMouseEvent.Type.MouseButtonPress
         else cv.mouseReleaseEvent)(ev)


def _dclick(cv, mm):
    c = _p2c(cv, mm)
    ev = QMouseEvent(QEvent.Type.MouseButtonDblClick, c, c,
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    cv.mouseDoubleClickEvent(ev)


def _center_of(cv, name):
    fr = cv.placed()[name]
    return (fr["off"][0] + 0.5 * (fr["min"][0] + fr["max"][0]),
            fr["off"][1] + 0.5 * (fr["min"][1] + fr["max"][1]))


def _page_loop(cv, name, mat=(34.0, 24.0), s=(4.0, 3.0)):
    """A small quadrilateral squarely over SOLID material - model mm
    (mat)+-s (the default misses the bore at (20,15) r5 and the pocket
    x<=30,y<=20 entirely; a loop dropped INTO the through bore would
    cut NOTHING - the honest no-op - and the ink gates would go
    vacuous). Model corners ride the view's own map to PAGE mm. The
    ISO view is TIGHTER than the plate's page box (its silhouette is
    a diamond), so the iso gate passes its own smaller, more central
    anchor."""
    fr = cv.placed()[name]
    return [tuple(np.asarray(cv._m2p(fr, (mat[0] + du, mat[1] + dv)),
                             float))
            for du, dv in ((-s[0], -s[1]), (s[0], -s[1]),
                           (s[0], s[1]), (-s[0], s[1]))]


def _notes(cv):
    seen = []
    cv.tool_note.connect(lambda s: seen.append(s))
    return seen


_DEF = object()        # "the drafter typed nothing" is NOT "cancelled"


def _spy(monkeypatch, answer):
    seen = {}

    def ask(parent, title, fields, **kw):
        seen["title"] = title
        seen["spec"] = {f["key"]: f for f in fields}
        return dict(answer) if answer is not None else None

    monkeypatch.setattr(cmddialog, "ask", ask)
    return seen


def _draw(win, monkeypatch, name="top", answer=_DEF, dbl=True,
          mat=(34.0, 24.0), s=(4.0, 3.0)):
    """The whole page's gesture: arm, click the profile, close it."""
    if answer is _DEF:
        answer = {"depth": "", "half": None}
    seen = _spy(monkeypatch, answer)
    cv = win.drawing
    cv.set_breakout_mode(True)
    for pt in _page_loop(cv, name, mat=mat, s=s):
        _click(cv, pt)
    if dbl:
        _dclick(cv, _center_of(cv, name))    # the Check gesture
    qapp = QApplication.instance()
    qapp.processEvents()
    return seen


# ---- one tool in the seat -------------------------------------------------
def test_a_breakout_and_detail_share_the_one_tool_seat(win, qapp):
    cv = win.drawing
    cv.set_detail_mode(True)
    assert cv._det_mode and not cv._bk_mode
    cv.set_breakout_mode(True)
    qapp.processEvents()
    assert cv._bk_mode and not cv._det_mode
    cv.set_detail_mode(True)
    assert cv._det_mode and not cv._bk_mode


# ---- the first click answers the page's "Select the drawing view" ---------
def test_b_bare_paper_is_refused_by_name(win, qapp):
    cv = win.drawing
    seen = _notes(cv)
    cv.set_breakout_mode(True)
    _click(cv, (5.0, 5.0))                   # the paper's far corner
    assert any("click INSIDE the view" in s for s in seen)
    assert cv._bk_pts == []


def test_c_iso_answers_for_breakout(  # the page names NO parent list here
        win, qapp, monkeypatch):
    """The detail's page NAMED its parents and the iso was not among
    them; the breakout's page prints only "the drawing view", and the
    core gates prove an iso column cuts as true - so iso ACCEPTS."""
    cv = win.drawing
    _draw(win, monkeypatch, name="iso", mat=(27.0, 15.0), s=(2.5, 2.0))
    bks = cv.breakouts()
    assert len(bks) == 1
    assert bks[0]["view"] == "iso"
    assert set(bks[0]) == {"view", "loop"}   # deviations only, blank
    #   depth is ABSENT (the page default stays LIVE, never a frozen number)
    assert len(bks[0]["loop"]) == 4


def test_d_one_breakout_per_view_verbatim(win, qapp, monkeypatch):
    cv = win.drawing
    _draw(win, monkeypatch, name="top")
    assert len(cv.breakouts()) == 1
    seen = _notes(cv)
    cv.set_breakout_mode(True)
    _click(cv, _center_of(cv, "top"))
    assert any("only one" in s.lower() for s in seen)
    assert len(cv.breakouts()) == 1


def test_e_the_check_needs_three_points(win, qapp, monkeypatch):
    cv = win.drawing
    seen = _notes(cv)
    _spy(monkeypatch, {"depth": "", "half": None})
    cv.set_breakout_mode(True)
    pts = _page_loop(cv, "top")
    for pt in pts[:2]:
        _click(cv, pt)
    _dclick(cv, pts[1])                      # a too-early Check
    assert any("at least three" in s for s in seen)
    assert len(cv.breakouts()) == 0
    assert len(cv._bk_pts) == 2              # the profile survives, open
    for pt in pts[2:]:
        _click(cv, pt)
    _dclick(cv, pts[3])                      # the real Check now
    qapp.processEvents()
    assert len(cv.breakouts()) == 1


def test_f_stay_inside_the_view(win, qapp, monkeypatch):
    cv = win.drawing
    seen = _notes(cv)
    cv.set_breakout_mode(True)
    pts = _page_loop(cv, "top")
    _click(cv, pts[0])
    _click(cv, _center_of(cv, "front"))      # a neighbour's paper
    assert any("Stay inside" in s for s in seen)
    assert len(cv._bk_pts) == 1


# ---- the cut itself: live, local, ours ------------------------------------
def test_g_the_default_inks_the_view_it_rides(
        win, qapp, monkeypatch):
    """Two laws in one gate: the cut is a LIVE PROJECTION (the broken-
    out view's ink CHANGES the moment the entry exists - a floor and
    walls arrive through _sources), and it is STRICTLY LOCAL to that
    view (DEVIATION declared: our four standards are peers, not
    parent-and-child, so nothing inherits - the page's iso-inheritance
    sentence speaks of a lineage our sheet does not have)."""
    cv = win.drawing
    before_top = cv.views().get("top")
    before_front = cv.views().get("front")
    before_iso = cv.views().get("iso")
    _draw(win, monkeypatch, name="top")
    assert len(cv.breakouts()) == 1
    assert cv.views().get("top") != before_top
    assert cv.views().get("front") == before_front
    assert cv.views().get("iso") == before_iso


def test_h_typed_depth_is_stored_made_real(win, qapp, monkeypatch):
    cv = win.drawing
    _draw(win, monkeypatch, name="top", answer={"depth": " 1.5 ",
                                                "half": None})
    assert cv.breakouts()[0]["depth"] == 1.5


def test_i_a_depth_that_swallows_the_design_is_a_section(
        win, qapp, monkeypatch):
    cv = win.drawing
    _draw(win, monkeypatch, name="top", answer={"depth": "99",
                                                "half": None})
    assert "refused" in win.status.currentMessage()
    assert cv.breakouts() == []


def test_j_a_word_is_not_a_distance(win, qapp, monkeypatch):
    cv = win.drawing
    _draw(win, monkeypatch, name="top", answer={"depth": "wide",
                                                "half": None})
    assert "not a number" in win.status.currentMessage()
    assert cv.breakouts() == []


def test_k_cancelling_changes_nothing(win, qapp, monkeypatch):
    cv = win.drawing
    _draw(win, monkeypatch, name="top", answer=None)
    assert cv.breakouts() == []


# ---- the door: its own spec, its own round trip ----------------------------
def test_k2_the_door_is_distance_and_measure_half_depth(
        win, qapp, monkeypatch):
    cv = win.drawing
    _draw(win, monkeypatch, name="top")
    cv.set_breakout_mode(False)     # M138's law: while armed a dbl-click
    #   is the FINISHING gesture - never a dialog. The door answers the
    #   drafter who has STOOD THE TOOL DOWN and reaches back for the
    #   profile ([Edit breakout sections] "double-click ... to edit it").
    loop0 = cv.breakouts()[0]["loop"]
    seen = _spy(monkeypatch, {"depth": "1.0", "half": None})
    fr = cv.placed()["top"]
    hit = cv._m2p(fr, loop0[0])              # dbl-click ON the outline
    _dclick(cv, (float(hit[0]), float(hit[1])))
    qapp.processEvents()
    assert seen["title"] == "Breakout Section View"
    assert list(seen["spec"]) == ["depth", "half"]      # the page's rows
    assert seen["spec"]["depth"]["label"] == "Distance"
    assert seen["spec"]["depth"]["kind"] == "text"
    assert seen["spec"]["depth"]["default"] == ""       # live half at rest
    assert seen["spec"]["half"]["kind"] == "button"     # the page's CLICK verb
    assert seen["spec"]["half"]["target"] == "depth"
    assert cv.breakouts()[0]["depth"] == 1.0
    _spy(monkeypatch, {"depth": "", "half": None})      # Measure Half Depth
    _dclick(cv, (float(hit[0]), float(hit[1])))         # back to the default
    qapp.processEvents()
    assert "depth" not in cv.breakouts()[0]


def test_l_a_double_click_off_the_outline_keeps_the_view_door(
        win, qapp, monkeypatch):
    cv = win.drawing
    _draw(win, monkeypatch, name="top")
    cv.set_breakout_mode(False)              # tool down (M138's law)
    fired = []
    cv.view_scale_requested.connect(fired.append)
    cx, cy = _center_of(cv, "top")           # the bore's page centre -
    _dclick(cv, (cx, cy))                    #   far off the (34,24) loop
    qapp.processEvents()
    assert fired == ["top"]


# ---- the painter walks the profile's ink without complaint -----------------
def test_m_paint_survives_cut_and_rubber(win, qapp):
    cv = win.drawing
    g = cv.sheet()
    fr = cv.placed()["top"]
    cx, cy = _center_of(cv, "top")
    g["breakouts"] = [{"view": "top",
                       "loop": [[float(x), float(y)] for x, y in
                                (cv._p2m(fr, (px, py)) for px, py in
                                 [(cx - 3, cy - 2), (cx + 3, cy - 2),
                                  (cx + 3, cy + 2.5), (cx - 3, cy + 2.5)])]}]
    cv.set_breakout_mode(True)               # rubber mid-loop, real pts
    cv._bk_view = "front"
    cv._bk_pts = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)]
    cv._bk_hover = (3.0, 3.0)
    qapp.processEvents()
    img = cv.grab()                          # paintEvent through both
    assert img.width() > 0                   # committed ink and rubber
