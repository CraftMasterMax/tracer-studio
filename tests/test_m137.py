"""M137 — section views on paper, rung two: the section's own props.

Rung one made the vendor's dominant grammar work — draw the line, get
the view. Rung two is what the vendor's child dialog holds: the
tri-modal DEPTH (Full — everything behind the line; Slice — the wound
alone; Distance — a named slab of material from the line), the kept
side, and the ASME law that a section view reads WITHOUT hidden lines
(the interior is already exposed; back ink only muddies it — an entry
can opt back in, but the default is honesty about what a section is
FOR). All of it lands on the same stored entry the two-click tool
made: mode/dist/flip/hidden ride the sheet dict, round-trip through
the file, and undo as one step. The thread-crest hatch rule the
probe flagged (ISO 6410-1 3.2.4) needs no code: our bores are
GEOMETRIC, so the hatch already stops at the hole's real wall — the
rule only bites products that fake threads as decals.

Reach for it the way you reach for a scale: double-click the section
child, and its props answer instead of the Scale dialog.
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


# ---- the depth modes 

def test_distance_keeps_exactly_the_named_slab():
    doc = holed_plate()
    o, n, dl = dr.plane_from_line("top", (5.0, 15.0), (35.0, 15.0))
    half = (40 * 5 * 6 - math.pi * 25 * 6 / 2)       # y 10..15 of the
    sec = dr.section_on(doc.result, o, n, right=dl,  # plate, half a
                        mode="distance", dist=5.0)   # bore inside
    assert sec["half"].volume == pytest.approx(half, rel=1e-3)
    bb = np.asarray(sec["half"].bounding_box, float)
    assert bb[0][1] == pytest.approx(10.0, abs=1e-6)   # slab y 10..15
    assert bb[1][1] == pytest.approx(15.0, abs=1e-6)
    full = dr.section_on(doc.result, o, n, right=dl)
    assert sec["half"].volume < full["half"].volume   # a slab IS less
    assert sec["mode"] == "distance"                  # tells the truth


def test_slice_hands_back_the_wound_alone():
    doc = holed_plate()
    o, n, dl = dr.plane_from_line("top", (5.0, 15.0), (35.0, 15.0))
    sec = dr.section_on(doc.result, o, n, right=dl, mode="slice")
    assert sec["half"] is None                        # nothing behind
    assert len(sec["cut"]) == 2                       # the wound alone
    assert np.allclose(sec["view"][0], (0, -1, 0))    # eye unchanged:
    assert np.allclose(sec["view"][1], (1, 0, 0))     # same page rules


def test_the_modes_cache_apart():
    doc = holed_plate()
    o, n, dl = dr.plane_from_line("top", (5.0, 15.0), (35.0, 15.0))
    a = dr.section_on(doc.result, o, n, right=dl, mode="distance",
                      dist=5.0)
    b = dr.section_on(doc.result, o, n, right=dl, mode="distance",
                      dist=6.0)
    c = dr.section_on(doc.result, o, n, right=dl, mode="distance",
                      dist=5.0)
    assert a is c                                     # same slab: cached
    assert a is not b                                 # depth is IN the
    assert b["half"].volume > a["half"].volume        # key, honestly
    assert a["cut"] == c["cut"]                       # loops identical


def test_the_axis_form_stays_full_depth():               # legacy guard
    doc = holed_plate()
    sec = dr.section(doc.result, "Y", 15.0)
    assert sec["half"].volume == pytest.approx(
        (7200 - math.pi * 25 * 6) / 2, rel=1e-3)
    assert sec["view"] == "front"


# ---- the canvas and the dialog 

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
    w._on_section_line({"parent": "top", "p0": (5.0, 15.0),
                        "p1": (35.0, 15.0), "flip": False})
    qapp.processEvents()
    yield w
    w._unsaved = False
    w._discard_guard = lambda: True
    w.close()
    r.ctx.release()


def _sec(win):
    return win.drawing.sections()[0]


def test_a_section_reads_without_back_ink_and_can_opt_back(win, qapp):
    cv = win.drawing
    assert cv.hidden_page("A-A") == []               # ASME: sections
    assert cv.hidden_page("front") != []             # standards do not
    _sec(win)["hidden"] = True                       # opt back in...
    assert cv.hidden_page("A-A") != []               # ...the ink is
    _sec(win)["hidden"] = False                      # honestly gated
    assert cv.hidden_page("A-A") == []


def test_slice_mode_paints_the_wound(win, qapp):
    cv = win.drawing
    _sec(win)["mode"] = "slice"
    ch = cv.views()["A-A"]
    assert ch == [list(L) for L in cv._sec_cut(_sec(win))["cut"]]
    assert len(ch) == 2                               # the two wound
    assert not cv.grab().isNull()                     # rects, and it
    _sec(win)["mode"] = "full"                        # paints clean
    assert cv.views()["A-A"] != ch                    # full differs


def test_the_double_click_forks_between_scale_and_props(win, qapp):
    cv = win.drawing
    props, scales = [], []
    cv.section_edit_requested.connect(props.append)
    cv.view_scale_requested.connect(scales.append)

    def dbl(view):
        fr = cv.placed()[view]
        c = np.asarray(fr["ctr"], float)
        wp = cv.s2p(*c)
        ev = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(wp),
                         QPointF(wp), QPointF(wp), Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        cv.mouseDoubleClickEvent(ev)

    dbl("front")
    assert scales == ["front"] and props == []       # M100 law holds
    dbl("A-A")
    assert props == ["A-A"] and scales == ["front"]  # the child owns


def test_the_dialog_carries_the_triad_and_cancels_clean(win,
                                                        qapp,
                                                        monkeypatch):
    from tracer.ui import cmddialog
    seen = {}

    def cancel(parent, title, fields):
        seen["title"] = title
        seen["keys"] = [f["key"] for f in fields]
        seen["modes"] = next(f["choices"] for f in fields
                             if f["key"] == "mode")
        return None
    monkeypatch.setattr(cmddialog, "ask", cancel)
    before = {k: v for k, v in _sec(win).items()}
    win._on_section_edit("A-A")
    assert seen["title"] == "Section A-A"
    assert {"mode", "dist", "flip", "hidden", "scale"} <= set(
        seen["keys"])
    assert len(seen["modes"]) == 3                   # Full|Slice|
    assert _sec(win) == before                       # Cancel: nothing


def test_distance_and_scale_edits_land_and_undo(win, qapp,
                                                monkeypatch):
    from tracer.ui import cmddialog
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda *a, **k: {"mode": "Distance (a slab from the line)",
                         "dist": 4.0, "flip": False,
                         "hidden": True, "scale": "1:2"})
    v_before = win.drawing._sec_cut(_sec(win))["half"].volume
    win._on_section_edit("A-A")
    s = _sec(win)
    assert s["mode"] == "distance" and s["dist"] == 4.0
    assert s["hidden"] is True
    assert win.drawing.sheet()["vscale"]["A-A"] == 0.5
    assert win.drawing._sec_cut(s)["half"].volume < v_before
    assert "slab 4 mm" in win.status.currentMessage()
    win.undo()                                       # one capture, one
    s = _sec(win)                                    # undo
    assert "mode" not in s and "hidden" not in s
    assert "A-A" not in (win.drawing.sheet().get("vscale") or {})


def test_going_back_to_full_forgets_the_slab(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"mode": "Slice (the cut face "
                                                "alone)",
                                         "dist": 7.0, "flip": False,
                                         "hidden": False, "scale": ""})
    win._on_section_edit("A-A")
    assert _sec(win).get("mode") == "slice" and "dist" not in _sec(win)
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda *a, **k: {"mode": "Full (everything behind the line)",
                         "dist": 7.0, "flip": False,
                         "hidden": False, "scale": ""})
    win._on_section_edit("A-A")
    assert "mode" not in _sec(win) and "dist" not in _sec(win)


def test_the_props_round_trip_through_the_file(win, qapp):
    _sec(win).update({"mode": "distance", "dist": 5.0, "hidden": True})
    blob = win.doc.to_dict()
    s = blob["drawings"][-1]["sections"][0]
    assert s["mode"] == "distance" and s["hidden"] is True
    d2 = Document.from_dict(blob)
    s2 = d2.drawings[-1]["sections"][0]
    assert s2["mode"] == "distance" and s2["dist"] == 5.0
