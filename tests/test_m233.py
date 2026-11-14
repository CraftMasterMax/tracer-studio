"""M201 R40 - the balloon family's UI leg: the door, the page's own
beats, the ghost, the Esc that COMPLETES.

The law (BALLOON-FAMILY dossier, verbatim): [Create a balloon] "1.
Select Tables > Balloon. The Balloon dialog displays. 2. In the
dialog, select a balloon Type... 3. Select an edge of the component to
identify in a drawing view. 4. For Patent type balloons, click to place
the bend point for the leader. 5. Click to place the balloon." - then
"Press Esc to complete the Balloon command." The dialog is ONE row
[Balloon reference]: "Type" - Standard / Patent, nothing else; the
look lives in Document Settings, not here. The M110 one-click next-
unused pin died with its page: "The numbers in the balloons match the
Item numbers for each component in the parts list" - a counter cannot
promise that, IDENTITY can (the core's balloon_item_at re-walks the
parts list, gates here prove the UI obeys it). The store law (OURS,
named in the writer): replace-by-Item WITHIN THE VIEW - the same
component may wear one balloon per view, and re-placing moves that
view's bubble while every unrelated pin rides untouched.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                       # noqa

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                       # noqa
from PySide6.QtTest import QTest                                    # noqa
from PySide6.QtWidgets import QApplication                          # noqa

from tracer.core import drawing                                     # noqa
from tracer.core.document import PrimitiveFeature                   # noqa
from tracer.ui import cmddialog                                     # noqa


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    from tracer.ui.mainwindow import MainWindow
    w = MainWindow()
    w.resize(1600, 900)
    w.show()
    qapp.processEvents()
    w._status_seen = []                       # STATUS-STREAM LAW: gates
    w.status.messageChanged.connect(w._status_seen.append)
    yield w
    w._unsaved = False
    w.close()


def _plate_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Block", kind="box",
        dims={"dx": 60.0, "dy": 30.0, "dz": 20.0}))
    win.recompute()
    win.action_new_drawing()
    win._show_page(win._drawing_page)
    qapp.processEvents()
    return win.drawing


def _two_sheet(win, qapp):
    """TWO bodies, two Items: [Create a balloon Note, verbatim] "The
    numbers in the balloons match the Item numbers for each component
    in the parts list" - the fixture hands the gate a parts list whose
    order (block 1 -> 1, plate -> 2) a counter could not know. The
    clicks live INSIDE the bodies' bounding boxes: Solid.box stands a
    corner at the origin, so block 1 claims 0..14 x 0..10 and the
    plate, shifted to x=30, claims 30..38 - centres at (7,5)/(34,4),
    the gap at x=18 is the paper between them."""
    win.new_document()
    d = win.doc
    for _nm, _dims, _pl in (("block 1", {"dx": 14.0, "dy": 10.0,
                                         "dz": 6.0}, (0.0, 0.0, 0.0)),
                            ("plate", {"dx": 8.0, "dy": 8.0,
                                       "dz": 8.0}, (30.0, 0.0, 0.0))):
        d.add_body(_nm)
        d.add(PrimitiveFeature(name=_nm, kind="box", dims=_dims,
                               placement=_pl))
    win.recompute()
    win.action_new_drawing()
    win._show_page(win._drawing_page)
    qapp.processEvents()
    return win.drawing


def _click_page(cv, qapp, sheet_mm):
    QTest.mouseClick(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                     cv.s2p(*sheet_mm).toPoint())
    qapp.processEvents()


def _click_model(cv, qapp, view, model_xy):
    _click_page(cv, qapp, cv.model_to_page(view, model_xy))


def _balloon(cv, qapp, view, edge_xy, bubble_off=(60.0, 60.0),
             bend_off=None):
    """One balloon, clicked the way the page draws its beats."""
    _click_model(cv, qapp, view, edge_xy)
    base = cv.model_to_page(view, edge_xy)
    if bend_off is not None:
        _click_page(cv, qapp, (base[0] + bend_off[0],
                               base[1] + bend_off[1]))
    _click_page(cv, qapp, (base[0] + bubble_off[0],
                           base[1] + bubble_off[1]))


def _answer(asked, value):
    """Spy the door: record what the page's dialog was ASKED, answer
    it without rendering a modal."""
    calls = []

    def fake(parent, title, fields, remember_key=None):
        calls.append((title, fields))
        return value
    return calls, fake


# ---- the door (the page puts it FIRST) --------------------------------
def test_the_door_is_the_pages_one_row(win, qapp, monkeypatch):
    cv = _plate_sheet(win, qapp)
    calls, fake = _answer(None, None)
    monkeypatch.setattr(cmddialog, "ask", fake)
    win._balloon_btn.setChecked(True)
    assert len(calls) == 1
    title, fields = calls[0]
    assert title == "Balloon"
    assert [f["label"] for f in fields] == ["Type"]      # ONE row
    assert fields[0]["choices"] == ["Standard", "Patent"]  # printed set


def test_a_cancelled_door_never_arms_the_tool(win, qapp, monkeypatch):
    cv = _plate_sheet(win, qapp)
    _, fake = _answer(None, None)
    monkeypatch.setattr(cmddialog, "ask", fake)
    win._balloon_btn.setChecked(True)
    assert not cv._balloon_mode
    assert not win._balloon_btn.isChecked()     # back in its rack


def test_the_answered_door_arms_with_the_type(win, qapp, monkeypatch):
    cv = _plate_sheet(win, qapp)
    _, fake = _answer(None, {"type": "Patent"})
    monkeypatch.setattr(cmddialog, "ask", fake)
    win._balloon_btn.setChecked(True)
    assert cv._balloon_mode and cv._bal_type == "Patent"
    #  the beat-one guidance rode the STATUS STREAM (not the bar):
    assert any("Select an edge of the component" in s
               for s in win._status_seen)                       # verbatim


# ---- the beats ---------------------------------------------------------
def test_standard_balloon_takes_two_beats(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_balloon_mode(True, "Standard")
    _balloon(cv, qapp, "top", (10.0, 5.0))
    bs = win.doc.drawings[-1]["balloons"]["top"]
    assert len(bs) == 1
    b = bs[0]
    assert b["item"] == 1 and b["type"] == "Standard"
    assert "bend" not in b                          # never offered
    assert "view" not in b                          # stripped writer
    assert b["x"] == pytest.approx(10.0, abs=0.6)   # anchor: MODEL mm
    assert b["y"] == pytest.approx(5.0, abs=0.6)
    base = cv.model_to_page("top", (10.0, 5.0))     # the bubble is the
    assert b["bx"] == pytest.approx(base[0] + 60.0, abs=0.4)   # SHEET
    assert b["by"] == pytest.approx(base[1] + 60.0, abs=0.4)   # click


def test_patent_balloon_takes_the_bend_beat(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_balloon_mode(True, "Patent")
    _balloon(cv, qapp, "top", (10.0, 5.0), bend_off=(20.0, -10.0))
    b = win.doc.drawings[-1]["balloons"]["top"][0]
    assert b["type"] == "Patent"
    base = cv.model_to_page("top", (10.0, 5.0))
    want = cv.page_to_model("top", (base[0] + 20.0, base[1] - 10.0))
    assert b["bend"] == pytest.approx(want, abs=0.6)  # MODEL mm of the
    #   bend click (OURS, named: the page prints a click for a thing
    #   with no printed unit - it rides the view like its anchor)
    assert any("bend point for the leader" in s for s in win._status_seen)


def test_the_number_is_the_parts_lists_own(win, qapp):
    cv = _two_sheet(win, qapp)
    rows = drawing.parts_list(win.doc.body_list(), win.doc.body_solids())
    assert [r["description"] for r in rows] == ["block 1", "plate"]
    cv.set_balloon_mode(True, "Standard")
    _balloon(cv, qapp, "top", (34.0, 4.0))     # the PLATE answers first
    bs = win.doc.drawings[-1]["balloons"]["top"]
    assert [b["item"] for b in bs] == [2]      # identity, never a 1st
    _balloon(cv, qapp, "top", (7.0, 5.0))      #   and the other part
    assert [b["item"] for b in sorted(win.doc.drawings[-1]
                                      ["balloons"]["top"],
                                      key=lambda x: x["item"])] == [1, 2]


# ---- refusals speak the page -------------------------------------------
def test_bare_paper_is_refused_in_the_pages_words(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_balloon_mode(True, "Standard")
    _click_page(cv, qapp, (5.0, 5.0))                     # far corner
    assert cv._bal_pending is None
    assert not (win.doc.drawings[-1].get("balloons") or {})
    assert any("SELECT AN EDGE OF THE COMPONENT" in s
               for s in win._status_seen)                 # page words


def test_view_paper_outside_the_design_is_also_refused(win, qapp):
    cv = _two_sheet(win, qapp)
    cv.set_balloon_mode(True, "Standard")
    _click_model(cv, qapp, "top", (18.0, 4.0))   # the GAP between the
    assert cv._bal_pending is None               #   parts: view paper,
    #   but no component's edge answers there - the page's beat one is
    #   "select an edge of the COMPONENT", and the number must match
    #   the parts list, so a bare gap between bodies is refused
    assert not (win.doc.drawings[-1].get("balloons") or {})
    assert any("COMPONENT" in s for s in win._status_seen)


# ---- the store law: replace-by-item, per view ---------------------------
def test_replacing_one_item_leaves_the_other_alone(win, qapp):
    cv = _two_sheet(win, qapp)
    cv.set_balloon_mode(True, "Standard")
    _balloon(cv, qapp, "top", (7.0, 5.0))
    _balloon(cv, qapp, "top", (34.0, 4.0))
    _balloon(cv, qapp, "top", (9.0, 6.0), bubble_off=(80.0, 80.0))
    bs = win.doc.drawings[-1]["balloons"]["top"]
    assert [b["item"] for b in sorted(bs, key=lambda x: x["item"])] \
        == [1, 2]                                   # 3 clicks, 2 items
    moved = [b for b in bs if b["item"] == 1][0]
    assert moved["x"] == pytest.approx(9.0, abs=0.6)    # the REPLACED one


def test_each_view_wears_its_own_balloons(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_balloon_mode(True, "Standard")
    _balloon(cv, qapp, "top", (10.0, 5.0))
    _balloon(cv, qapp, "front", (10.0, 5.0), bubble_off=(70.0, 20.0))
    #  SAME Item, two views: the numbers answer EACH VIEW's parts list
    assert [b["item"] for b in win.doc.drawings[-1]["balloons"]["top"]] \
        == [1]
    assert [b["item"] for b in
            win.doc.drawings[-1]["balloons"]["front"]] == [1]
    _balloon(cv, qapp, "top", (20.0, 10.0))         # replaces TOP only
    #  (RE-FETCH after every write: the writer replaces the OUTER dict
    #   - groups = dict(...) + g["balloons"] = groups - so a reference
    #   grabbed before a placement is honestly the PREVIOUS sheet state)
    g = win.doc.drawings[-1]["balloons"]
    assert len(g["top"]) == len(g["front"]) == 1
    assert g["top"][0]["x"] == pytest.approx(20.0, abs=0.6)
    assert g["front"][0]["x"] == pytest.approx(10.0, abs=0.6)


# ---- Esc: the completion verb (reference page form) ----------------------
def _arm(win, qapp, monkeypatch, type_):
    """Arm the tool the HONEST way: the button (door spy answers with
    the type). The stand-down rack only releases CHECKED buttons - a
    canvas-armed test would be a different machine."""
    from tracer.ui import cmddialog
    monkeypatch.setattr(cmddialog, "ask",
                        lambda parent, title, fields, remember_key=None:
                        {"type": type_})
    win._balloon_btn.setChecked(True)


def test_esc_completes_the_command_and_keeps_the_placements(win, qapp,
                                                            monkeypatch):
    cv = _plate_sheet(win, qapp)
    _arm(win, qapp, monkeypatch, "Standard")
    _balloon(cv, qapp, "top", (10.0, 5.0))
    assert cv._balloon_mode                     # the tool REPEATS
    win._stand_down_drawing()                   # bare Esc = COMPLETE
    assert not cv._balloon_mode and not win._balloon_btn.isChecked()
    assert len(win.doc.drawings[-1]["balloons"]["top"]) == 1


def test_the_first_esc_drops_only_the_balloon_in_flight(win, qapp,
                                                        monkeypatch):
    cv = _plate_sheet(win, qapp)
    _arm(win, qapp, monkeypatch, "Standard")
    _balloon(cv, qapp, "top", (10.0, 5.0))          # one committed
    _click_model(cv, qapp, "top", (20.0, 10.0))     # one in flight
    assert cv._bal_pending is not None
    win._stand_down_drawing()                       # Esc #1: drop it
    assert cv._bal_pending is None and cv._balloon_mode
    assert len(win.doc.drawings[-1]["balloons"]["top"]) == 1
    win._stand_down_drawing()                       # Esc #2: complete
    assert not cv._balloon_mode and not win._balloon_btn.isChecked()


# ---- the ghost and the ink ----------------------------------------------
def test_the_balloon_rides_the_cursor_between_beats(win, qapp):
    cv = _plate_sheet(win, qapp)

    def ink_at(sheet_mm):
        img = cv.grab().toImage()
        c = cv.s2p(*sheet_mm)
        n = 0
        for yy in range(int(c.y()) - 14, int(c.y()) + 15):
            for xx in range(int(c.x()) - 14, int(c.x()) + 15):
                if img.pixelColor(xx, yy).lightness() < 200:
                    n += 1
        return n

    cv.set_balloon_mode(True, "Standard")
    _click_model(cv, qapp, "top", (10.0, 5.0))
    ghost = cv.model_to_page("top", (10.0, 5.0))
    spot = (ghost[0] + 80.0, ghost[1] + 80.0)
    before = ink_at(spot)               # no hover yet: nothing draws here
    QTest.mouseMove(cv, cv.s2p(*spot).toPoint())
    qapp.processEvents()
    assert cv._bal_hover is not None
    assert ink_at(spot) > before        # the ghost bubble drew itself


def test_patent_and_standard_do_not_paint_alike(win, qapp):
    a = _plate_sheet(win, qapp)
    a.set_balloon_mode(True, "Standard")
    _balloon(a, qapp, "top", (10.0, 5.0), bubble_off=(100.0, 100.0))
    img_a = a.grab().toImage()
    win.undo()
    b = a                                   # same sheet, Patent now
    b.set_balloon_mode(True, "Patent")
    _balloon(b, qapp, "top", (10.0, 5.0), bubble_off=(100.0, 100.0),
             bend_off=(60.0, 0.0))
    img_b = b.grab().toImage()
    diff = 0
    for yy in range(0, min(img_a.height(), img_b.height()), 3):
        for xx in range(0, min(img_a.width(), img_b.width()), 3):
            if img_a.pixelColor(xx, yy) != img_b.pixelColor(xx, yy):
                diff += 1
    assert diff > 40        # the curved spline is not the straight line
