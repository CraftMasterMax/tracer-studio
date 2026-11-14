"""M201 R38 - the hole table's ORIGIN on the sheet: the tool, its door.

[Create a hole table, verbatim] "In the canvas, select a drawing view
to associate with the hole table and click to place the origin" / "The
empty hole table displays at the cursor" / "Click to place the hole
table on the sheet" - TWO beats with the page's Table dialog between
them, driven here with REAL mouse events and the ask() spy (m227's
law: the conftest guard fails any real modal in headless pytest by
design, so the dialog's PIXELS live in the film). [Tables overview,
verbatim] "Each view require its own origin." - the page's grammar,
printed exactly - is the store keyed by view. The click COMMITS the
origin before the dialog asks (OURS-STAMP, named: cancel cannot
un-place what the page made real by clicking, and no page prints an
undo for it). The page names NO host restriction for the table, so the
iso ANSWERS - an honestly EMPTY table (m228 proves the rows), not a
refusal. The dialog's rows are the create page's printed set
(Title/Origin/Arrange/Style); Type is not a combo (the tool's entry
IS the selection the page says "make sure" of), and the rows the
page's own parentheses scope to OTHER types - Select, Reference,
Structure, Auto Balloon - are UNOFFERED BY NAME, as are Table
Direction and Columns (edit-dialog rows the create page never
prints). A typed coordinate in the Origin row is refused (OURS-STAMP:
the page's verbs there are SELECT and PLACE, never keystroke), and
"ANSI Origin" - the blog's word, never the help's - is refused by
name through the core.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt                      # noqa: E402
from PySide6.QtGui import QMouseEvent                       # noqa: E402
from PySide6.QtWidgets import QApplication                  # noqa: E402

from tracer.core import drawing                             # noqa: E402
from tracer.core.document import (Document, HoleFeature,    # noqa: E402
                                  PrimitiveFeature)
from tracer.ui import cmddialog                             # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    """m228's proven stage in Qt clothes: the twin M8-6H taps, the
    plain hole, the counterbore (three top rows) and the side bore
    (front's only row) - so every table ink gate below has REAL rows
    to seat, and the iso's emptiness is the core's, not a missing
    feature's."""
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
                           dims={"dx": 40, "dy": 24, "dz": 8}))
    for x in (12, 28):
        d.add(HoleFeature(name=f"h8@{x}", op="subtract",
                          center=(x, 12, 8), normal=(0, 0, -1),
                          radius=3.4, depth=8, cut_length=8, through=True,
                          thread_pitch=1.25, thread_len=8,
                          thread_size="M8", thread_class="6H"))
    d.add(HoleFeature(name="plain", op="subtract", center=(8, 6, 8),
                      normal=(0, 0, -1), radius=2.5, depth=4,
                      cut_length=4))
    d.add(HoleFeature(name="cb", op="subtract", center=(30, 6, 8),
                      normal=(0, 0, -1), radius=2.5, depth=4, cut_length=4,
                      cb_radius=4.5, cb_depth=3))
    d.add(HoleFeature(name="side", op="subtract", center=(20, 0, 4),
                      normal=(0, 1, 0), radius=2.0, depth=4, cut_length=4))
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


def _page_of(cv, name, model_pt):
    fr = cv.placed()[name]
    return tuple(float(q) for q in cv._m2p(fr, model_pt))


def _center_of(cv, name):
    fr = cv.placed()[name]
    return (fr["off"][0] + 0.5 * (fr["min"][0] + fr["max"][0]),
            fr["off"][1] + 0.5 * (fr["min"][1] + fr["max"][1]))


def _notes(cv):
    seen = []
    cv.tool_note.connect(lambda s: seen.append(s))
    return seen


def _spy(monkeypatch, overrides):
    """The dialog answered the way a drafter answers: every untouched
    row keeps its printed default, overrides carry the typed rows;
    overrides=None is CANCEL."""
    seen = {}

    def ask(parent, title, fields, **kw):
        seen["title"] = title
        seen["spec"] = {f["key"]: f for f in fields}
        if overrides is None:
            return None
        ans = {k: f.get("default", "") for k, f in seen["spec"].items()}
        ans.update(overrides)
        return ans

    monkeypatch.setattr(cmddialog, "ask", ask)
    return seen


def _beat1(cv, name, model):
    """Beat one: the click that selects the view AND places the
    origin (one gesture, exactly as the page writes the two)."""
    pt = _page_of(cv, name, model)
    _click(cv, pt)
    return pt


# ---- one tool in the seat -------------------------------------------------
def test_a_the_hole_table_shares_the_one_tool_seat(win, qapp):
    cv = win.drawing
    cv.set_detail_mode(True)
    cv.set_hole_table_mode(True)
    qapp.processEvents()
    assert cv._ho_mode and not cv._det_mode
    cv.set_breakout_mode(True)
    assert cv._bk_mode and not cv._ho_mode
    cv.set_hole_table_mode(True)
    cv.set_dim_mode(True)
    assert cv._dim_mode and not cv._ho_mode


# ---- the first click answers the page's associate sentence -----------------
def test_b_bare_paper_is_refused_by_name(win, qapp):
    cv = win.drawing
    seen = _notes(cv)
    cv.set_hole_table_mode(True)
    _click(cv, (5.0, 5.0))                       # the paper's far corner
    assert any("SELECT A DRAWING VIEW" in s for s in seen)
    assert cv.hole_origins() == {}


# ---- the click COMMITS the origin; the store is per-view, never a dupe -----
def test_c_the_click_keeps_the_origin_and_replaces_never_duplicates(
        win, qapp, monkeypatch):
    cv = win.drawing
    _spy(monkeypatch, None)                      # dialog: CANCEL each time
    cv.set_hole_table_mode(True)
    _beat1(cv, "top", (12.0, 12.0))
    qapp.processEvents()
    org1 = cv.hole_origins()
    assert "top" in org1                         # cancel cannot un-place:
    #   the page made the origin real AT THE CLICK (OURS-STAMP, printed
    #   in the tool's own note)
    fr = cv.placed()["top"]
    m = cv._p2m(fr, _page_of(cv, "top", (28.0, 6.0)))
    _beat1(cv, "top", (28.0, 6.0))
    qapp.processEvents()
    org2 = cv.hole_origins()
    assert list(org2) == ["top"]                 # replace, never a dupe
    assert org2["top"] == pytest.approx((float(m[0]), float(m[1])))


def test_d_each_view_keeps_its_own_origin(win, qapp, monkeypatch):
    cv = win.drawing
    _spy(monkeypatch, None)
    cv.set_hole_table_mode(True)
    _beat1(cv, "top", (12.0, 12.0))
    _beat1(cv, "front", (20.0, 4.0))
    qapp.processEvents()
    assert set(cv.hole_origins()) == {"top", "front"}


# ---- the door: exactly the create page's printed rows ----------------------
def test_e_the_dialog_rows_are_the_printed_set(win, qapp, monkeypatch):
    cv = win.drawing
    seen = _spy(monkeypatch, None)
    cv.set_hole_table_mode(True)
    fr = cv.placed()["top"]
    pt = _beat1(cv, "top", (12.0, 12.0))
    qapp.processEvents()
    m = cv._p2m(fr, pt)
    assert seen["title"] == "Table"              # "The Table dialog displays"
    assert list(seen["spec"]) == ["title", "origin", "arrange", "style"]
    assert seen["spec"]["arrange"]["choices"] == list(drawing.ARRANGE_MODES)
    assert seen["spec"]["style"]["choices"] == list(drawing.ORIGIN_STYLES)
    assert not any("ANSI" in c for c in seen["spec"]["style"]["choices"])
    assert seen["spec"]["title"]["default"] == ""
    assert seen["spec"]["origin"]["default"] == f"{m[0]:.2f}, {m[1]:.2f}"
    # UNOFFERED BY NAME - declared, each by the page's own parentheses
    # (Parts List / Bend Table rows), and Type is the tool's entry:
    assert not ({"select", "reference", "structure", "auto_balloon",
                 "type", "direction", "columns"} & set(seen["spec"]))


# ---- beat two seats the table; the rows stay DERIVED -----------------------
def test_f_the_second_click_seats_the_table(win, qapp, monkeypatch):
    cv = win.drawing
    _spy(monkeypatch, {"arrange": "by Size", "style": "ASME Origin",
                       "title": "Bores"})
    cv.set_hole_table_mode(True)
    fr = cv.placed()["top"]
    pt = _beat1(cv, "top", (12.0, 12.0))
    qapp.processEvents()
    assert cv._ho_pending is not None            # the empty table at cursor
    m = cv._p2m(fr, pt)
    _click(cv, (80.0, 200.0))                    # "Click to place the hole
    qapp.processEvents()                         #   table on the sheet"
    t = cv.sheet()["hole_tables"]["top"]
    assert set(t) == {"view", "origin", "at", "arrange", "style", "title"}
    assert t["view"] == "top"
    assert t["origin"] == pytest.approx((float(m[0]), float(m[1])))
    assert t["at"] == pytest.approx([80.0, 200.0])   # OURS-STAMP: the click
    #   is the table's TOP-LEFT (the page says place, prints no corner law)
    assert t["arrange"] == "by Size" and t["style"] == "ASME Origin"
    assert t["title"] == "Bores"
    assert cv._ho_pending is None
    assert "each view require" in win.status.currentMessage()   # verbatim grammar
    _beat1(cv, "top", (28.0, 6.0))                  # a fresh two-beat for the
    qapp.processEvents()                            #   SAME view: replace
    _click(cv, (90.0, 200.0))
    qapp.processEvents()
    assert len(cv.sheet()["hole_tables"]) == 1      # never two tables on one
    #   origin - the same never-duplicate reading the core prints
    assert cv.sheet()["hole_tables"]["top"]["at"] == pytest.approx([90.0, 200.0])


def test_g_the_esc_rung_cancels_the_table_and_keeps_the_origin(
        win, qapp, monkeypatch):
    cv = win.drawing
    _spy(monkeypatch, {})                        # accept with defaults
    win._ht_btn.setChecked(True)                 # the PRODUCTION door:
    assert cv._ho_mode                           #   button arms the tool
    _beat1(cv, "top", (12.0, 12.0))
    qapp.processEvents()
    assert cv._ho_pending is not None
    win._stand_down_drawing()                    # first Esc
    assert cv._ho_pending is None                # the ghost is gone
    assert "top" in cv.hole_origins()            # the origin STAYS
    assert cv._ho_mode                           # the tool keeps its seat
    win._stand_down_drawing()                    # next Esc: the rack
    assert not cv._ho_mode                       # unchecks the CHECKED
    assert not win._ht_btn.isChecked()           #   button (the law)


def test_h_the_iso_answers_an_empty_table_not_a_refusal(win, qapp,
                                                        monkeypatch):
    """Page silence on host views, resolved like the breakout (R37):
    every view associates; the iso's table is EMPTY because a tilted
    bore shows no true circle - m228 proved the rows, this gate proves
    the DOOR opens."""
    cv = win.drawing
    _spy(monkeypatch, {})
    cv.set_hole_table_mode(True)
    _beat1(cv, "iso", (20.0, 12.0))
    qapp.processEvents()
    assert "iso" in cv.hole_origins()
    _click(cv, (150.0, 210.0))
    qapp.processEvents()
    assert cv.sheet()["hole_tables"]["iso"]["view"] == "iso"


# ---- refusals, each by its printed name ------------------------------------
def test_i_a_typed_coordinate_is_refused_the_origin_comes_from_a_click(
        win, qapp, monkeypatch):
    cv = win.drawing
    _spy(monkeypatch, {"origin": "99.00, 99.00"})
    cv.set_hole_table_mode(True)
    _beat1(cv, "top", (12.0, 12.0))
    qapp.processEvents()
    assert "do not type coordinates" in win.status.currentMessage()
    assert cv._ho_pending is None                # the seat beat never comes
    assert "hole_tables" not in cv.sheet() or cv.sheet()["hole_tables"] == {}


def test_j_ansi_is_the_blog_s_word_and_is_refused(win, qapp, monkeypatch):
    cv = win.drawing
    _spy(monkeypatch, {"style": "ANSI Origin"})
    cv.set_hole_table_mode(True)
    _beat1(cv, "top", (12.0, 12.0))
    qapp.processEvents()
    assert "ORIGIN_STYLE_UNKNOWN" in win.status.currentMessage()
    assert cv._ho_pending is None


# ---- the painter walks origins, tables and the ghost without complaint -----
def test_k_paint_survives_glyphs_tables_and_the_ghost(win, qapp):
    cv = win.drawing
    g = cv.sheet()
    org = {}
    for name, model in (("top", (12.0, 12.0)), ("front", (20.0, 4.0)),
                        ("iso", (20.0, 12.0))):
        fr = cv.placed()[name]
        m = cv._p2m(fr, _page_of(cv, name, model))
        org[name] = (float(m[0]), float(m[1]))
    g["hole_origins"] = org
    styles = list(drawing.ORIGIN_STYLES)
    g["hole_tables"] = {name: {"view": name, "origin": list(pt),
                               "at": [60.0 + 30.0 * i, 200.0],
                               "arrange": ("by Size" if i else "by Position"),
                               "style": styles[i % 4],
                               "title": ("T" if name == "top" else "")}
                        for i, (name, pt) in enumerate(org.items())}
    cv.set_hole_table_mode(True)                 # the ghost rides too
    cv._ho_pending = {"view": "top", "origin": org["top"],
                      "arrange": "by Position", "style": "Datum Target",
                      "title": ""}
    cv._ho_hover = (120.0, 150.0)
    qapp.processEvents()
    img = cv.grab()                              # paintEvent through all
    assert img.width() > 0                       #   four glyphs + tables
