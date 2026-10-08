"""M136 — section views on paper, rung 1: the cutting line you draw
ON a view.

The wave-10 probe's verdict was blunt and our own archaeology blunter:
M102 had already bought the hard geometry (half-solids, closed cut
loops, page-space hatch, letters), but it asked the user to type an
axis and a number into a dialog. Every drafting product since paper
draws the section WHERE IT IS USED — a line across the parent view —
and lets the child view fall out of it. So this rung is grammar, not
math: `plane_from_line` turns two parent-view points into the plane
that contains the line and stands perpendicular to the parent
(the classic: drag left→right across the TOP view and the arrow drops
toward the FRONT, keeping the near half — volume-exact 3364.4 here);
`section_on` cuts any such plane and hands the child a BASIS TUPLE
that the whole projection pipeline already carries (HLR, hidden ink,
place, hatch, nudge, scale, DXF — zero consumer changes); the canvas
grows a two-click tool beside the dim/balloon/fit modes; and letters
come from ONE registry (M102 dialog and M136 line share it) obeying
the standards' reserved-letter law: no I, O, Q, S, X, Z.

Depth modes, jogged lines and thread-crest hatch rules are rung 2/3,
banked in the queue doc; v1 parents are the three orthogonal views.
"""
import math

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from tracer.core import drawing as dr
from tracer.core.document import Document, HoleFeature, PrimitiveFeature


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def holed_plate():
    doc = Document()
    doc.add(PrimitiveFeature(name="plate", kind="box",
                             dims={"dx": 40, "dy": 30, "dz": 6}))
    doc.add(HoleFeature(name="bore", op="subtract", center=(20, 15, 6),
                        normal=(0, 0, -1), radius=5.0, depth=6,
                        cut_length=6, through=True))
    return doc


def shoelace(loop):
    P = np.asarray(loop, float)
    x, y = P[:, 0], P[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1))
                     - np.dot(y, np.roll(x, -1)))) / 2.0


# ---- the plane math ---------------------------------------------------------

def test_the_classic_line_on_the_top_view_makes_the_front_section():
    o, n, right = dr.plane_from_line("top", (5.0, 15.0), (35.0, 15.0))
    assert np.allclose(o, (5, 15, 0))
    assert np.allclose(n, (0, -1, 0))       # arrow drops to the front
    assert np.allclose(right, (1, 0, 0))    # the line lies flat: page-x
    o2, n2, _ = dr.plane_from_line("top", (5.0, 15.0), (35.0, 15.0),
                                   flip=True)
    assert np.allclose(n2, (0, 1, 0))       # flip picks the other half
    assert np.allclose(o2, o)


def test_a_vertical_line_on_the_front_view_is_a_side_cut_with_guards():
    o, n, right = dr.plane_from_line("front", (20.0, 0.0), (20.0, 12.0))
    assert np.allclose(n, (1, 0, 0))
    assert np.allclose(right, (0, 0, 1))    # up-the-page runs page-x
    assert np.allclose(o, (20, 0, 0))
    with pytest.raises(ValueError):         # iso tilts depth into the
        dr.plane_from_line("iso", (0, 0), (10, 0))    # line: not a
    with pytest.raises(ValueError):                    # section plane
        dr.plane_from_line("top", (1, 1), (1, 1))     # yet (v1)


def test_section_on_the_line_plane_keeps_volume_caps_and_basis():
    doc = holed_plate()
    o, n, right = dr.plane_from_line("top", (5.0, 15.0), (35.0, 15.0))
    sec = dr.section_on(doc.result, o, n, right=right)
    assert sec["half"].to_trimesh().is_watertight
    assert sec["half"].volume == pytest.approx(
        (7200 - math.pi * 25 * 6) / 2, rel=1e-3)
    # the bore axis lies IN the plane: the cap splits into two rects
    assert len(sec["cut"]) == 2
    assert sum(shoelace(L) for L in sec["cut"]) == pytest.approx(
        180.0, rel=1e-3)
    eye, X, Y = sec["view"]                 # the child reads as front
    assert np.allclose(eye, (0, -1, 0)) and np.allclose(X, (1, 0, 0))
    ch = dr.project_view(sec["half"], view=sec["view"])
    pts = np.vstack([np.asarray(c, float) for c in ch])
    assert pts[:, 0].min() == pytest.approx(0.0, abs=1e-6)
    assert pts[:, 0].max() == pytest.approx(40.0, abs=1e-6)
    assert pts[:, 1].min() == pytest.approx(0.0, abs=1e-6)
    assert pts[:, 1].max() == pytest.approx(6.0, abs=1e-6)


def test_letters_come_from_the_reserved_letter_free_alphabet():
    got = [dr.section_letter(i) for i in range(24)]
    for bad in "IOQSXZ":
        assert bad not in got[:20]
    assert got[:3] == ["A", "B", "C"]
    assert got[7] == "H" and got[8] == "J"   # I is skipped, never used
    assert got[19] == "Y"
    assert got[20] == "AA" and got[21] == "BB"    # double up, no reuse


def test_the_m102_axis_dialog_form_still_cuts():
    doc = holed_plate()                       # regression guard: the
    sec = dr.section(doc.result, "Y", 15.0)   # new sibling must not
    assert sec["half"].volume == pytest.approx(             # disturb it
        (7200 - math.pi * 25 * 6) / 2, rel=1e-3)
    assert sec["view"] == "front"             # named key, as ever


# ---- the canvas seam --------------------------------------------------------

@pytest.fixture
def win(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    w.new_document()
    d = w.doc
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    d.add(HoleFeature(name="bore", op="subtract", center=(20, 15, 6),
                      normal=(0, 0, -1), radius=5.0, depth=6,
                      cut_length=6, through=True))
    w.recompute()
    w.action_new_drawing()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w._discard_guard = lambda: True
    w.close()
    r.ctx.release()


def _click(canvas, page_pt,
           modifiers=Qt.KeyboardModifier.NoModifier):
    wp = canvas.s2p(*page_pt)                 # canonical page -> widget
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(wp),
                     QPointF(wp), QPointF(wp), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, modifiers)
    canvas.mousePressEvent(ev)


def _pts_in(view_frame):
    lo = np.asarray(view_frame["min"], float) \
        + np.asarray(view_frame["off"], float)
    hi = np.asarray(view_frame["max"], float) \
        + np.asarray(view_frame["off"], float)
    return (tuple(float(v) for v in lo + (hi - lo) * 0.25),
            tuple(float(v) for v in lo + (hi - lo) * 0.65))


def test_two_clicks_on_the_parent_stand_a_lettered_section(win, qapp):
    cv = win.drawing
    a, b = _pts_in(cv.placed()["top"])
    notes, fired = [], []
    cv.tool_note.connect(lambda t: notes.append(t))
    cv.section_added.connect(lambda e: fired.append(e))
    win._sec_btn.click()                      # arm via the real button
    assert cv._sec_mode
    _click(cv, a)
    assert len(cv._sec_pts) == 1
    _click(cv, b)
    assert len(fired) == 1
    secs = cv.sheet()["sections"]
    assert secs[0]["name"] == "A-A" and secs[0]["parent"] == "top"
    assert "p0" in secs[0] and "p1" in secs[0]
    qapp.processEvents()
    assert "A-A" in cv.placed()               # the child view stands
    assert any("click where the cut ENDS" in t for t in notes)


def test_only_the_three_orthogonal_parents_are_legal(win, qapp):
    cv = win.drawing
    notes = []
    cv.tool_note.connect(lambda t: notes.append(t))
    win._sec_btn.click()
    a, _ = _pts_in(cv.placed()["iso"])
    _click(cv, a)
    assert cv._sec_pts == []                  # iso refused with a word
    assert any("not a legal parent" in t for t in notes)
    W, H = dr.PAGES[cv.page]
    _click(cv, (W + 40.0, H + 40.0))          # off any view: a hint
    assert cv._sec_pts == []
    assert notes[-1].endswith("(click inside one)")


def test_one_letter_registry_serves_both_cutters(win, qapp):
    g = win.drawing.sheet()
    g["sections"] = [{"name": "A-A", "axis": "Y", "at": 15.0}]
    win._on_section_line({"parent": "front", "p0": (20.0, 0.0),
                          "p1": (20.0, 12.0), "flip": False})
    names = [s["name"] for s in win.drawing.sheet()["sections"]]
    assert names == ["A-A", "B-B"]            # the line inherits the
    assert "B-B" in win.drawing.placed()      # registry, and projects


def test_the_line_round_trips_and_undoes(win, qapp):
    cv = win.drawing
    a, b = _pts_in(cv.placed()["top"])
    win._on_section_line({"parent": "top", "p0": a, "p1": b})
    blob = win.doc.to_dict()
    secs = blob["drawings"][-1].get("sections") or []
    assert secs and secs[0]["parent"] == "top"
    d2 = Document.from_dict(blob)
    s2 = d2.drawings[-1]["sections"][0]
    assert s2["name"] == "A-A"
    assert np.allclose(s2["p0"], a, atol=1e-9)
    win.undo()                                # the capture inside the
    assert not (cv.sheet().get("sections") or [])   # slot really undoes


def test_the_line_travels_with_its_parent_view(win, qapp):
    cv = win.drawing
    fr0 = cv.placed()["top"]
    win._on_section_line({"parent": "top", "p0": (10.0, 12.0),
                          "p1": (30.0, 18.0)})
    before = cv._sec_cut(cv.sections()[0])["cut"]
    g = cv.sheet()
    g["move"] = {"top": [12.0, 8.0]}          # M96's drafter nudge
    fr1 = cv.placed()["top"]
    assert np.allclose(np.asarray(fr1["off"], float)
                       - np.asarray(fr0["off"], float),
                       (12.0, 8.0), atol=1e-6)
    after = cv._sec_cut(cv.sections()[0])["cut"]
    assert len(before) == len(after)          # the model never moved —
    for Lb, La in zip(before, after):         # only its paper position
        assert np.allclose(np.asarray(Lb), np.asarray(La))


def test_esc_ladder_erases_the_line_before_standing_the_tool_down(
        win, qapp):
    cv = win.drawing
    a, _ = _pts_in(cv.placed()["top"])
    win._sec_btn.click()
    _click(cv, a)
    win._stand_down_drawing()                 # rung one: the half-line
    assert cv._sec_pts == []                  # is erased...
    assert cv._sec_mode and win._sec_btn.isChecked()   # tool stays put
    _click(cv, a)                             # restarting works
    assert len(cv._sec_pts) == 1
    win._stand_down_drawing()                 # rung one again...
    win._stand_down_drawing()                 # ...rung two: stand down
    assert not cv._sec_mode and not win._sec_btn.isChecked()


def test_the_sheet_paints_its_cutting_line(win, qapp):
    cv = win.drawing
    cv.resize(900, 620)
    a, b = _pts_in(cv.placed()["top"])
    win._on_section_line({"parent": "top", "p0": a, "p1": b,
                          "flip": True})
    qapp.processEvents()
    pix = cv.grab()                           # the whole ink pass: line
    assert not pix.isNull()                   # + child + hatch, no crash
    W, H = dr.PAGES[cv.page]
    win._sec_btn.click()                      # armed with a half-line
    _click(cv, _pts_in(cv.placed()["right"])[0])   # and a rubber tip
    cv._sec_hover = (W / 2.0, H / 2.0)
    assert not cv.grab().isNull()
