"""M201 R39 - the parts list on the sheet: the tool, its dialog, its
seat, the balloons that ARRIVE with it, and the double-click door.

Dialect is m229's law (conftest fails REAL modals headless by design,
so the dialog's pixels live in the film; the ask() spy drives the
beats). Binding sentences, verbatim:
[Create a parts list] "In the canvas, select a drawing view to
associate with the parts list." / "The Table dialog displays." /
"Click to place the parts list on the sheet." / "Note: Balloons are
automatically added to the sheet to label the associated drawing
view."
[Tables overview] "When you place a table on the bottom half of the
sheet, the column labels flip to the bottom of the table. For parts
lists and bend tables, the numbered rows are ordered from bottom to
top. To lock or unlock the table flipping feature, press the Shift
key." - direction is the SHEET's law at the seat, so unlike the R38
origin a beat-one view pick commits NOTHING (a parts list measures
nothing; the page makes the placement, not the pick, real - OURS,
named). Cancel answers None and the sheet stays clean.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt                     # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent                   # noqa: E402
from PySide6.QtWidgets import QApplication                         # noqa: E402

from tracer.core import drawing                                    # noqa: E402
from tracer.core.document import PrimitiveFeature                  # noqa: E402
from tracer.ui import cmddialog                                    # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    """A three-part assembly in Qt clothes: two identical blocks (the
    merge law gives ONE row, qty 2) and a plate - two rows, two
    balloons, with creation order as the numbering law. The stage is
    the SAME size as m229's so the view frames are proven geometry."""
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
    # THREE BODIES, not one union: a feature with no body reads as the
    # implicit "Body 1" (document.py), and the parts list walks BODIES
    # - add_body is Fusion's New Body made real, so the fixture uses
    # it once per part (m230's rows law needs three bodies to merge
    # two identical ones into item 1 qty 2).
    for _nm, _dims in (("block 1", {"dx": 14, "dy": 10, "dz": 6}),
                       ("block 2", {"dx": 14, "dy": 10, "dz": 6}),
                       ("plate", {"dx": 40, "dy": 24, "dz": 2})):
        d.add_body(_nm)
        d.add(PrimitiveFeature(name=_nm, kind="box", dims=_dims))
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


def _dbl(cv, mm):
    c = _p2c(cv, mm)
    ev = QMouseEvent(QEvent.Type.MouseButtonDblClick, c, c,
                     Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    cv.mouseDoubleClickEvent(ev)


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
    row keeps its printed default; overrides=None is CANCEL."""
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


def _beat1(cv, name):
    """The associate click: inside a placed view's frame (the page's
    "select a drawing view", one click)."""
    pt = _center_of(cv, name)
    _click(cv, pt)
    return pt


# ---- one tool in the seat -------------------------------------------------
def test_a_the_parts_list_shares_the_one_tool_seat(win, qapp):
    cv = win.drawing
    cv.set_dim_mode(True)
    cv.set_parts_list_mode(True)
    qapp.processEvents()
    assert cv._pl_mode and not cv._dim_mode
    cv.set_hole_table_mode(True)
    assert cv._ho_mode and not cv._pl_mode          # BOTH directions
    cv.set_parts_list_mode(True)
    cv.set_breakout_mode(True)
    assert cv._bk_mode and not cv._pl_mode


# ---- the associate sentence, refused on bare paper ------------------------
def test_b_bare_paper_is_refused_by_name(win, qapp):
    cv = win.drawing
    seen = _notes(cv)
    cv.set_parts_list_mode(True)
    _click(cv, (5.0, 5.0))                           # the paper's corner
    assert any("SELECT A DRAWING VIEW" in s for s in seen)
    assert "parts_tables" not in cv.sheet()


# ---- the door: exactly the create page's printed rows ---------------------
def test_c_the_dialog_rows_are_the_printed_set(win, qapp, monkeypatch):
    cv = win.drawing
    seen = _spy(monkeypatch, None)
    cv.set_parts_list_mode(True)
    _beat1(cv, "top")
    qapp.processEvents()
    assert seen["title"] == "Table"                  # "The Table dialog
    #   displays." - the dialog is the MIDDLE beat, and the view pick
    #   already happened: dialog-first is this tool's page grammar
    assert list(seen["spec"]) == ["type", "structure", "auto_balloon",
                                  "title"]
    assert seen["spec"]["type"]["choices"] == list(drawing.PARTS_TYPE_MEMBERS)
    assert seen["spec"]["structure"]["choices"] == \
        list(drawing.PARTS_STRUCTURES)
    assert seen["spec"]["auto_balloon"]["default"] is True   # the Note
    #   ("Balloons are automatically added...") rules the default
    # UNOFFERED BY NAME, declared: Direction and Columns are the EDIT
    # dialog's rows; Origin/Arrange/Style are the HOLE table's.
    assert not ({"direction", "columns", "origin", "arrange", "style",
                 "select", "reference"} & set(seen["spec"]))


# ---- cancel commits NOTHING (the R38 origin's law does NOT ride) ---------
def test_d_cancel_commits_nothing_and_the_seat_stays(win, qapp,
                                                     monkeypatch):
    cv = win.drawing
    _spy(monkeypatch, None)
    cv.set_parts_list_mode(True)
    _beat1(cv, "top")
    qapp.processEvents()
    assert cv._pl_pending is None
    assert "parts_tables" not in cv.sheet()      # the page makes only
    #   the PLACEMENT real - a cancelled dialog leaves no ghost list
    assert cv._pl_mode                           # the tool keeps its seat


# ---- the seat, the flip law, and the balloons that ARRIVE -----------------
def test_e_the_seat_resolves_the_flip_and_balloons_arrive(win, qapp,
                                                          monkeypatch):
    cv = win.drawing
    _spy(monkeypatch, {})
    cv.set_parts_list_mode(True)
    _beat1(cv, "top")
    qapp.processEvents()
    assert cv._pl_pending is not None            # "The empty parts list
    #   displays at the cursor."
    _click(cv, (80.0, 60.0))                      # bottom half
    qapp.processEvents()
    ent = cv.sheet()["parts_tables"]["top"]
    assert ent["direction"] == "up"              # the flip: labels to
    #   the bottom, rows bottom-up - the SHEET decided, not the dialog
    assert ent["x"] == pytest.approx(80.0) and ent["y"] == pytest.approx(60.0)
    #   (the click round-trips screen->page floats - the seat IS the
    #   click, measured with the tolerance the arithmetic owes)
    pins = cv.sheet().get("balloons", {}).get("top", [])
    rows = drawing.parts_list(cv.doc.body_list(), cv.doc.body_solids())
    assert sorted(p["item"] for p in pins) == sorted(r["item"]
                                                     for r in rows) == [1, 2]
    # replace-by-construction: seat again - one key, one list
    _beat1(cv, "top")
    qapp.processEvents()
    _click(cv, (300.0, 250.0))                    # top half
    qapp.processEvents()
    assert list(cv.sheet()["parts_tables"]) == ["top"]
    assert cv.sheet()["parts_tables"]["top"]["direction"] == "down"


# ---- the Shift key IS the lock (the page prints the KEY, not a menu) -----
def test_f_shift_locks_the_flip(win, qapp, monkeypatch):
    cv = win.drawing
    seen = _notes(cv)
    _spy(monkeypatch, {})
    cv.set_parts_list_mode(True)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key_Shift,
                   Qt.KeyboardModifier.NoModifier)
    cv.keyPressEvent(ev)
    qapp.processEvents()
    assert cv.sheet().get("flip_locked") is True
    assert any("locked" in s for s in seen)
    _beat1(cv, "top")
    qapp.processEvents()
    _click(cv, (80.0, 60.0))                      # bottom half, LOCKED
    qapp.processEvents()
    assert cv.sheet()["parts_tables"]["top"]["direction"] == "down"
    cv.keyPressEvent(ev)
    assert cv.sheet().get("flip_locked") is False


# ---- double-click the list: the EDIT dialog prints all seven names -------
def test_g_the_double_click_door_prints_seven_and_refurses_two(
        win, qapp, monkeypatch):
    cv = win.drawing
    _spy(monkeypatch, {})
    cv.set_parts_list_mode(True)
    _beat1(cv, "top")
    qapp.processEvents()
    _click(cv, (80.0, 60.0))
    qapp.processEvents()
    ent = cv.sheet()["parts_tables"]["top"]
    seen = _spy(monkeypatch, {"columns": ["Item", "Part Name"]})
    _dbl(cv, (90.0, 62.0))                        # inside the seated rect
    qapp.processEvents()
    assert seen["title"] == "Edit Parts List"
    assert seen["spec"]["columns"]["choices"] == \
        list(drawing.PARTS_PAGE_COLUMNS)          # ALL SEVEN, printed
    assert cv.sheet()["parts_tables"]["top"]["columns"] == \
        ["Item", "Part Name"]
    # the unsourced pair is REFUSED by name - the store keeps the truth
    _spy(monkeypatch, {"columns": ["Item", "Part Number"]})
    _dbl(cv, (90.0, 62.0))
    qapp.processEvents()
    assert cv.sheet()["parts_tables"]["top"]["columns"] == \
        ["Item", "Part Name"]
    assert ent is cv.sheet()["parts_tables"]["top"]


# ---- the double-click of BARE SHEET keeps the view's own door ------------
def test_h_double_click_off_the_list_is_not_the_edit_door(win, qapp,
                                                          monkeypatch):
    cv = win.drawing
    fired = []
    cv.parts_edit_requested.connect(lambda v: fired.append(v))
    _dbl(cv, (5.0, 5.0))                           # bare paper, no list
    qapp.processEvents()
    assert fired == []


# ---- Esc: the ghost goes, the seat stays, nothing was stored -------------
def test_i_esc_erases_the_ghost_only(win, qapp, monkeypatch):
    cv = win.drawing
    _spy(monkeypatch, {})
    cv.set_parts_list_mode(True)
    _beat1(cv, "top")
    qapp.processEvents()
    assert cv._pl_pending is not None
    assert cv.restart_parts_placement() is True    # first Esc: the ghost
    assert cv._pl_pending is None and cv._pl_mode
    assert "parts_tables" not in cv.sheet()
    assert cv.restart_parts_placement() is False   # second: the ladder
    #   moves on (the button stands the tool down, not Esc's ghost rung)


# ---- rows LIVE: a body born AFTER the seat joins the table ---------------
def test_j_the_seated_list_reads_the_design_live(win, qapp, monkeypatch):
    cv = win.drawing
    _spy(monkeypatch, {})
    cv.set_parts_list_mode(True)
    _beat1(cv, "top")
    qapp.processEvents()
    _click(cv, (80.0, 60.0))
    qapp.processEvents()
    store = cv.sheet()["parts_tables"]["top"]
    assert not any(k in store for k in ("rows", "items", "cells"))
    #   the store holds the ASSOCIATION and the seat - never numbers
    win.doc.add_body("lug")
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 4, "dy": 4, "dz": 4}))
    win.recompute()
    qapp.processEvents()
    rows = drawing.parts_list(cv.doc.body_list(), cv.doc.body_solids())
    assert [r["description"] for r in rows][-1] == "lug"
    # the next paint derives it (no stored rows CAN'T disagree - the
    # identity law is structural, gated by m230's shared arithmetic)
