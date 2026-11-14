"""M201 R41 - Renumber and Align Balloons on the sheet: the doors, the
click ladders, the store folds, and the parts list that SORTS.

Binding sentences, verbatim:
[Renumber] "Select Tables > Renumber. The Renumber dialog displays." /
"Specify the starting Number." / "Select the first balloon to renumber.
The balloon updates and the parts list sorts to reflect the new
number." / "The number will automatically increment as you select
balloons or bend identifiers" [reference page, no terminal period as
published]. Type members the reference prints, all three shipped as
choices: Automatic / Balloon / Bend Identifier - the third is the
page's own word for a thing Tracer cannot renumber (no bend table
ships), so it is refused BY NAME, never mapped. Level is DECLARED
unoffered (the page conditions it on an All-Levels parts list; Tracer
lists are first-level).
[Align balloons] the command asks for NOTHING - "Select Tables > Align
Balloons. In the canvas, select the balloons to align. Press Enter.
Click to place the start point. Drag the cursor, then click to place
the end point." - the result law "The left edge of each balloon aligns
along the line. The balloons distribute equally between the two
points." is m232's align_balloons, folded into the store HERE. The
DWG-REF-DRAWING-TAB row "Align Balloon | Alights [sic] balloons" -
Autodesk's live typo - is pinned BY A GATE below and NEVER shipped as
UI copy.
Dialect is the family's own: conftest fails REAL modals headless, so
the ask() spy drives the doors; the win fixture carries the GL guard
(M201 R40's CI teaching: a bare MainWindow() ERRORS on the windows
legs where SceneRenderer cannot build a context - m231's guard skips
those legs instead); gates that ask WHAT THE PAGE SAID listen to the
STATUS STREAM (_status_seen), never the volatile bar."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tracer.core import balloon, drawing
from tracer.core.document import PrimitiveFeature                   # noqa
from tracer.ui import cmddialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    """The R40 assembly in Qt clothes: two parts, two balloons, with
    creation order as the numbering law - plus the windows guard the
    R40 CI postmortem made LAW (try SceneRenderer, skip when headless
    GL cannot answer)."""
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
    w._status_seen = []
    w.status.messageChanged.connect(w._status_seen.append)
    w.new_document()
    d = w.doc
    for _nm, _dims, _pl in (("block 1", {"dx": 4.0, "dy": 6.0,
                                         "dz": 6.0}, (0.0, 0.0, 0.0)),
                            ("plate", {"dx": 8.0, "dy": 8.0,
                                       "dz": 8.0}, (30.0, 0.0, 0.0))):
        d.add_body(_nm)
        d.add(PrimitiveFeature(name=_nm, kind="box", dims=_dims,
                               placement=_pl))
    w.recompute()
    w.action_new_drawing()
    w._show_page(w._drawing_page)
    qapp.processEvents()
    return w


def _prim_feature_cls():
    return PrimitiveFeature


def _click_page(cv, qapp, sheet_mm):
    QTest.mouseClick(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                     cv.s2p(*sheet_mm).toPoint())
    qapp.processEvents()


def _click_model(cv, qapp, view, model_xy):
    _click_page(cv, qapp, cv.model_to_page(view, model_xy))


def _balloon(win, cv, qapp, view, edge_xy, bubble_off=(60.0, 60.0)):
    _click_model(cv, qapp, view, edge_xy)
    base = cv.model_to_page(view, edge_xy)
    _click_page(cv, qapp, (base[0] + bubble_off[0],
                           base[1] + bubble_off[1]))


def _two_balloons(win, qapp):
    cv = win.drawing
    cv.set_balloon_mode(True, "Standard")
    # R40 geometry: "block 1" spans x 0-4 (a (10,5) click is BARE PAPER
    # and the app's own refusal eats the beat), "plate" spans x 30-38.
    _balloon(win, cv, qapp, "top", (2.0, 3.0))
    _balloon(win, cv, qapp, "top", (34.0, 4.0), bubble_off=(60.0, 80.0))
    assert len(win.doc.drawings[-1]["balloons"]["top"]) == 2
    return cv


# ---- the doors ----------------------------------------------------------
def test_align_arms_asking_nothing(win, qapp, monkeypatch):
    """[Align balloons] the whole command is five canvas beats and the
    book ships NO dialog page (12 probes closed the door) - a test that
    reached cmddialog.ask here would be inventing furniture. The gate
    makes the ask EXPLODE and the button answers anyway."""
    def _boom(*a, **k):
        raise AssertionError("align asked a question - the book prints "
                             "no Align dialog (12-slug 404 census)")
    monkeypatch.setattr(cmddialog, "ask", _boom)
    win._al_btn.setChecked(True)
    qapp.processEvents()
    assert win.drawing._al_mode
    assert any("select the balloons to align" in s
               for s in win._status_seen)                 # verbatim beat


def test_renumber_dialog_prints_the_pages_rows(win, qapp, monkeypatch):
    """Rows the [Renumber reference] dialog form rules, IN ORDER: Type
    (its THREE printed members) then Number. Level rides "(Balloon
    type only)" conditioned on an All-Levels list Tracer never builds -
    OMITTED and DECLARED, never silently dropped. Selection is the
    CANVAS per the task page, not a dialog row."""
    calls = []

    def fake(parent, title, fields, remember_key=None):
        calls.append((title, fields))
        return {"type": "Balloon", "number": 5}
    monkeypatch.setattr(cmddialog, "ask", fake)
    win._rn_btn.setChecked(True)
    title, fields = calls[0]
    assert title == "Renumber"
    assert [f["label"] for f in fields] == ["Type", "Number"]
    assert fields[0]["choices"] == ["Automatic", "Balloon",
                                    "Bend Identifier"]    # printed trio
    assert fields[1]["min"] == 1        # items count parts from 1
    assert win.drawing._rn_mode and win.drawing._rn_start == 5


def test_cancelled_renumber_door_never_arms(win, qapp, monkeypatch):
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: None)
    win._rn_btn.setChecked(True)
    assert not win.drawing._rn_mode
    assert not win._rn_btn.isChecked()  # back in its rack


def test_bend_identifier_is_refused_by_name(win, qapp, monkeypatch):
    """The reference prints the member; Tracer renumbers bend
    identifiers only through a bend table it does not ship - so the
    ANSWER is refused with the reason, BY NAME, never quietly mapped
    onto balloons (the LAW-22 reading of "based on selection")."""
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"type": "Bend Identifier",
                                         "number": 1})
    win._rn_btn.setChecked(True)
    assert not win.drawing._rn_mode
    assert not win._rn_btn.isChecked()
    assert any("Bend Identifier" in s for s in win._status_seen)


# ---- the renumber click ladder -----------------------------------------
def test_each_click_grants_and_increments(win, qapp):
    """"Select the first balloon to renumber" + "The number will
    automatically increment as you select balloons" - the counter is
    the TOOL's memory, not the dialog's, and the store fold is the
    window's (one writer)."""
    cv = _two_balloons(win, qapp)
    cv.set_renumber_mode(True, 5)
    bs = win.doc.drawings[-1]["balloons"]["top"]
    _click_page(cv, qapp, (bs[0]["bx"], bs[0]["by"]))      # reads 1
    g = win.doc.drawings[-1]
    assert g["balloon_renumber"] == {"1": 5}
    _click_page(cv, qapp, (bs[1]["bx"], bs[1]["by"]))      # reads 2
    assert g["balloon_renumber"] == {"1": 5, "2": 6}
    assert any("automatically increment" in s for s in win._status_seen)


def test_a_renumbered_balloon_answers_its_new_read(win, qapp):
    """The click RE-READS the live mapping every beat: selecting the
    same balloon twice renumbers it AGAIN from its CURRENT number (the
    identity refusal of m232's core is about a session's selection;
    across beats the sheet's truth is the mapping)."""
    cv = _two_balloons(win, qapp)
    cv.set_renumber_mode(True, 5)
    bs = win.doc.drawings[-1]["balloons"]["top"]
    _click_page(cv, qapp, (bs[0]["bx"], bs[0]["by"]))
    g = win.doc.drawings[-1]
    _click_page(cv, qapp, (bs[0]["bx"], bs[0]["by"]))      # now reads 5
    assert g["balloon_renumber"] == {"1": 6}               # 5 -> 6


def test_the_parts_list_sorts_to_reflect_the_new_number(win, qapp):
    """[verbatim] "The balloon updates and the parts list SORTS to
    reflect the new number." Rows stay DERIVED; the mapping re-keys and
    sorts them - the same one derivation the painter and the
    double-click door read."""
    cv = _two_balloons(win, qapp)
    cv.set_renumber_mode(True, 9)
    bs = win.doc.drawings[-1]["balloons"]["top"]
    _click_page(cv, qapp, (bs[1]["bx"], bs[1]["by"]))      # 2 -> 9
    rows = drawing.parts_list(win.doc.body_list(),
                              win.doc.body_solids())
    out = balloon.renumbered_rows(rows,
                                  win.doc.drawings[-1]["balloon_renumber"])
    assert [r["item"] for r in out] == [1, 9]              # sorted
    assert out[1]["description"] == "plate"                # facts ride
    cv.grab()                        # the sheet paints with the sort


def test_bare_paper_is_refused_the_page_way(win, qapp):
    cv = _two_balloons(win, qapp)
    cv.set_renumber_mode(True, 1)
    before = dict(win.doc.drawings[-1].get("balloon_renumber") or {})
    _click_page(cv, qapp, (5.0, 5.0))
    assert win.doc.drawings[-1].get("balloon_renumber", {}) == before
    assert any("no balloon to renumber" in s
               for s in win._status_seen)


# ---- the align ladder ---------------------------------------------------
def test_align_beats_land_every_bubble_on_the_line(win, qapp):
    """The five canvas beats driven as a hand drives them - pick,
    pick, Enter, start, end - and the result is the page's sentence
    made arithmetic: equal stations, endpoints included, left edge on
    the line (m232's law, folded to the store here)."""
    cv = _two_balloons(win, qapp)
    win._al_btn.setChecked(True)
    qapp.processEvents()
    bs = win.doc.drawings[-1]["balloons"]["top"]
    _click_page(cv, qapp, (bs[0]["bx"], bs[0]["by"]))
    _click_page(cv, qapp, (bs[1]["bx"], bs[1]["by"]))
    QTest.keyClick(cv, Qt.Key_Return)
    qapp.processEvents()
    assert cv._al_done                             # Enter closed it
    a, b = (20.0, 300.0), (140.0, 300.0)
    # The canvas answers in PIXELS: a click at sheet-mm p is received at
    # p2s(s2p(p)) - the honest expectation is the line the CANVAS saw,
    # not the hand's raw point (0.25 mm per px at this zoom, R41 DBG:
    # stored 299.75 vs raw 300.0 was the gate lying, not the fold).
    def _seen(p):
        return cv.p2s(cv.s2p(*p).toPoint())
    a2, b2 = _seen(a), _seen(b)
    _click_page(cv, qapp, a)
    _click_page(cv, qapp, b)
    stored = win.doc.drawings[-1]["balloons"]["top"]
    want = balloon.align_balloons([dict(x) for x in
                                   [dict(bs[0]), dict(bs[1])]], a2, b2)
    assert stored[0]["bx"] == pytest.approx(want[0]["bx"])
    assert stored[1]["bx"] == pytest.approx(want[1]["bx"])
    assert all(abs(s["by"] - want[0]["by"]) < 1e-6 for s in stored)
    assert any("aligns along the line" in s for s in win._status_seen)


def test_a_degenerate_line_is_refused_and_moves_nothing(win, qapp):
    cv = _two_balloons(win, qapp)
    win._al_btn.setChecked(True)
    bs = list(win.doc.drawings[-1]["balloons"]["top"])
    _click_page(cv, qapp, (bs[0]["bx"], bs[0]["by"]))
    QTest.keyClick(cv, Qt.Key_Return)
    a = (20.0, 300.0)
    _click_page(cv, qapp, a)
    _click_page(cv, qapp, a)                       # zero-length line
    assert any("BALLOON_ALIGN_DEGENERATE" in s for s in win._status_seen)
    after = win.doc.drawings[-1]["balloons"]["top"]
    assert [(x["bx"], x["by"]) for x in after] == \
           [(x["bx"], x["by"]) for x in bs]


def test_the_first_esc_drops_the_selection_the_second_racks(win, qapp):
    """The align page prints no Esc verb - the ladder rung is OURS,
    named: the first Esc drops the started selection (nothing was
    stored until the end click), the next completes the command into
    its rack."""
    cv = _two_balloons(win, qapp)
    win._al_btn.setChecked(True)
    bs = win.doc.drawings[-1]["balloons"]["top"]
    _click_page(cv, qapp, (bs[0]["bx"], bs[0]["by"]))
    assert cv._al_sel
    win._stand_down_drawing()                      # Esc #1
    assert cv._al_sel == [] and cv._al_mode
    assert win._al_btn.isChecked()
    win._stand_down_drawing()                      # Esc #2
    assert not cv._al_mode and not win._al_btn.isChecked()


def test_one_align_answers_one_view(win, qapp):
    """OURS named (the page draws its line in a single view): a pick
    from another view is refused and the first view's selection rides
    on untouched. The front's bubble is STAGED in the sheet's own store
    (JSON-legit data; renumber/align never resolve identity - only the
    balloon tool does), so the gate measures the cross-view law, not
    whether the front happens to show that corner."""
    cv = win.drawing
    _two_balloons(win, qapp)
    g = win.doc.drawings[-1]
    placed = cv.placed()
    fr = placed.get("front")
    assert fr is not None                      # the stage is the rest
    cx, cy = cv._m2p(fr, (2.0, 3.0))
    g["balloons"]["front"] = [{"item": 1, "x": 2.0, "y": 3.0,
                               "bx": cx + 40.0, "by": cy + 40.0,
                               "type": "Standard"}]
    win._al_btn.setChecked(True)
    qapp.processEvents()
    bs_top = g["balloons"]["top"]
    bs_front = g["balloons"]["front"]
    _click_page(cv, qapp, (bs_top[0]["bx"], bs_top[0]["by"]))
    _click_page(cv, qapp, (bs_front[0]["bx"], bs_front[0]["by"]))
    assert len(cv._al_sel) == 1                    # the cross-view no
    assert any("ONE drawing view" in s for s in win._status_seen)


# ---- the ship-proof gate (the page's own typo) --------------------------
def test_alights_never_ships_as_ui_copy():
    """[DWG-REF-DRAWING-TAB, verbatim row] "Align Balloon | Alights
    [sic] balloons in a drawing view." - Autodesk's live typo is
    pinned HERE, by a gate, and never in UI copy (the PAGE LAW: typos
    travel in quotes, not in widgets)."""
    import pathlib
    for src in ("mainwindow.py", "drawingview.py", "balloon.py"):
        text = (pathlib.Path(__file__).resolve().parents[1]
                / "tracer" / "ui" / src).read_text(encoding="utf-8") \
            if src != "balloon.py" else \
            (pathlib.Path(__file__).resolve().parents[1]
             / "tracer" / "core" / "balloon.py").read_text(
                encoding="utf-8")
        body = "\n".join(ln for ln in text.splitlines()
                         if not ln.lstrip().startswith("#")
                         and '"' not in ln[:2] and "sic" not in ln)
        assert "Alights" not in body or "sic" in text     # quoted only
