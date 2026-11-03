"""M192 - the Sketch Palette era.

R1 [GUID-4183A4B7]: "The top of the Sketch Palette shows sketch status
as Status: Under-Constrained or Status: Constrained" and "Show
Constraints: Shows or hides sketch constraints." - the vendor keeps a
standing panel beside the canvas. We grow ours from the SAME organs the
M191 R3 display law built: the eyes ride model.vis (per-sketch, file-
borne), every door - paint, right-click menu, palette - is ONE mouth
(set_show_layer, speaking vis_changed), and the head borrows the
vendor's EXACT words while our toolbar keeps its own voice. The fill
the "profile" eye governs is honest: it reads to_loops()+regions(), the
same topology finish() commits through, so the shaded skin can never
promise a profile the commit would refuse.
"""
import math

import pytest

pytest.importorskip("PySide6")

import numpy as np                                                   # noqa
from PySide6.QtGui import QImage                                     # noqa
from PySide6.QtWidgets import QApplication, QMessageBox              # noqa

from tracer.core.sketch.model import (SketchModel, model_from_dict,  # noqa
                                      model_to_dict)


def _grab(w):
    img = w.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(img.constBits().tobytes(), np.uint8).reshape(
        img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), :3].copy()


def _diff(a, b):
    """Pixels the two frames disagree on (the honest delta: theme
    paints dim, raw hexes never match - measure the CHANGE)."""
    return int((np.abs(a.astype(int) - b.astype(int)).max(axis=2) > 3)
               .sum())


@pytest.fixture
def qapp():
    yield QApplication.instance() or QApplication([])


_LIVE: list = []


@pytest.fixture(autouse=True)
def _close_live():
    """ROUTING LAW: every SHOWed canvas CLOSES with its test."""
    yield
    while _LIVE:
        w = _LIVE.pop()
        w.close()
        w.deleteLater()
    QApplication.processEvents()


def _stage(qapp):
    """The tested stage: a STANDALONE 600x400 canvas (the window-splitter
    law from M191 R5's film) plus its OWN palette, the pair the panel
    builder wires."""
    from tracer.ui.sketcheditor import SketchCanvas, SketchPalette
    cv = SketchCanvas()
    cv.set_model(SketchModel())
    cv.resize(600, 400)
    pal = SketchPalette(cv)
    cv.show()
    pal.show()              # M192 R2 lesson: the palette needs its OWN
    #   show(): a widget that never SAW the screen reports EVERY child
    #   invisible no matter what setVisible decides - the finder's rows
    #   answer isVisible() only from a shown panel.
    for _ in range(3):
        qapp.processEvents()
    _LIVE.append(cv)
    _LIVE.append(pal)
    return cv, pal


@pytest.fixture(scope="module")
def qapp2():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win2(qapp2):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
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


# ---- the per-sketch truth: two new eyes, old files unchanged ------------------

def test_vis_grows_two_honest_eyes_and_wakes_legacy(qapp):
    m = SketchModel()
    assert set(m.vis) == {"refs", "dims", "constraints", "points",
                          "profile"}, \
        "the sketch owns exactly the palette's five eyes"
    assert all(m.vis.values()), "every eye defaults OPEN: a pre-R1 "  \
        "sketch shows everything, exactly as it always did"
    m.vis["points"] = False
    m.vis["profile"] = False
    d = model_to_dict(m)
    assert d["vis"]["points"] is False and d["vis"]["profile"] is False
    back = model_from_dict(d)
    assert back.vis["points"] is False, "the eye closes IN THE FILE "  \
        "(M191 R3's per-sketch truth grows, it does not move)"
    legacy = dict(d, vis={"refs": True, "dims": False,
                          "constraints": True})   # a pre-R1 file
    w1 = model_from_dict(legacy)
    assert w1.vis["points"] and w1.vis["profile"], \
        "old files wake ALL eyes open - a missing key is not a verdict"
    assert w1.vis["dims"] is False, "and the keys the old file DID "    \
        "answer still ride"
    bare = {k: v for k, v in d.items() if k != "vis"}
    assert all(model_from_dict(bare).vis.values()), \
        "the pre-M191-R3 world (no vis at all) wakes wide open"


def test_display_layers_is_the_one_vocabulary(qapp):
    from tracer.ui.sketcheditor import DISPLAY_LAYERS
    keys = [k for k, _m, _p in DISPLAY_LAYERS]
    assert set(keys) == set(SketchModel().vis), \
        "paint, menu and palette share ONE list - no eye lives twice"
    words = {k: w for k, _m, w in DISPLAY_LAYERS}
    assert words["constraints"] == "Show Constraints"
    assert words["dims"] == "Show Dimensions"
    assert words["points"] == "Show Points"
    assert words["profile"] == "Show Profile", "the palette wears the "  \
        "vendor's words verbatim [GUID-4183A4B7]"
    menus = {k: m for k, m, _p in DISPLAY_LAYERS}
    assert menus["constraints"] == "Show constraint symbols"
    assert menus["dims"] == "Show dimension values"
    assert menus["refs"] == "Show projected geometry", \
        "M191 R3's menu wording stands untouched - new doors, old words"


# ---- the head: the vendor's two words, honestly spoken ------------------------

def test_the_head_speaks_the_vendor_words(qapp):
    cv, pal = _stage(qapp)
    m = cv.model
    m.add_line(m.point(-4.0, 0.0), m.point(4.0, 0.0))
    cv._solve()
    for _ in range(3):
        qapp.processEvents()
    assert pal.status.text() == "Status: Under-Constrained", \
        "free geometry wears the vendor's EXACT sentence"
    from tracer.core.sketch.constraints import Fixed
    l = m.sketch.lines[0]
    m.constrain(Fixed(l.a, x=l.a.x), Fixed(l.a, y=l.a.y),
                Fixed(l.b, x=l.b.x), Fixed(l.b, y=l.b.y))
    cv._solve()
    for _ in range(3):
        qapp.processEvents()
    assert pal.status.text() == "Status: Constrained", \
        "every degree tamed - the head flips to the vendor's word"


def test_an_empty_sketch_wears_no_verdict(qapp):
    cv, pal = _stage(qapp)
    for _ in range(3):
        qapp.processEvents()
    assert pal.status.text() == "Status: \u2014", \
        "HOUSE DECISION (docs SILENT): neither word is a truth about "  \
        "nothing - the empty sketch gets no verdict"


def test_the_head_never_calls_a_conflict_constrained(qapp):
    cv, pal = _stage(qapp)
    from tracer.core.sketch.constraints import Distance, Fixed
    m = cv.model
    p, q = m.point(0.0, 0.0), m.point(10.0, 0.0)
    m.constrain(Fixed(p, x=0.0), Fixed(p, y=0.0), Fixed(q, x=10.0),
                Fixed(q, y=0.0))
    m.sketch.constraints.append(Distance(p, q, 99.0))   # impossible law
    cv._solve()
    for _ in range(3):
        qapp.processEvents()
    res = cv._last_result
    assert getattr(res, "conflicting", []), \
        "the solver must SEE the lie (M87's diagnosis stands)"
    assert pal.status.text() == "Status: Under-Constrained", \
        "dof 0 is NOT enough: a lying law is never 'Constrained'"


# ---- the eyes: pixels answer ---------------------------------------------------

def test_the_points_eye_shuts_the_dots(qapp):
    cv, pal = _stage(qapp)
    m = cv.model
    free = m.point(0.0, 14.0)
    m.add_line(m.point(-2.0, 14.0), free)
    cv._solve()
    for _ in range(3):
        qapp.processEvents()
    box = (140, 149, 295, 306)          # the lonely point's dot home
    on = _grab(cv)[box[0]:box[1], box[2]:box[3]]
    pal.boxes["points"].setChecked(False)
    for _ in range(3):
        qapp.processEvents()
    off = _grab(cv)[box[0]:box[1], box[2]:box[3]]
    assert _diff(on, off) > 8, "Show Points OFF lifts the dots from "   \
        "the canvas - the white-dot law (M191 R1) hides with its eye"
    assert m.vis["points"] is False
    pal.boxes["points"].setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    assert _diff(_grab(cv)[box[0]:box[1], box[2]:box[3]], off) > 8, \
        "and the dots ARRIVE when the eye opens again"


def test_the_fill_lights_closed_regions_only(qapp):
    cv, pal = _stage(qapp)
    m = cv.model
    m.add_rect(m.point(-10.0, -6.0), m.point(10.0, 6.0))
    cv._solve()
    for _ in range(3):
        qapp.processEvents()
    win = (180, 220, 280, 320)          # inside the rectangle
    on = _grab(cv)[win[0]:win[1], win[2]:win[3]]
    pal.boxes["profile"].setChecked(False)
    for _ in range(3):
        qapp.processEvents()
    off = _grab(cv)[win[0]:win[1], win[2]:win[3]]
    assert _diff(on, off) > 400, "a CLOSED profile wears the fill - "   \
        "the canvas now shows what an extrude WOULD take"
    # the same eye over an OPEN chain: no fill, ever
    m2 = SketchModel()
    cv.set_model(m2)
    a, b, c = m2.point(-10.0, -6.0), m2.point(0.0, 6.0), m2.point(10.0, -6.0)
    m2.add_line(a, b)
    m2.add_line(b, c)
    cv._solve()
    pal.boxes["profile"].setChecked(False)
    for _ in range(3):
        qapp.processEvents()
    base = _grab(cv)[win[0]:win[1], win[2]:win[3]]
    pal.boxes["profile"].setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    assert _diff(_grab(cv)[win[0]:win[1], win[2]:win[3]], base) <= 4, \
        "the fill is HONEST: an open chain promises a profile the "     \
        "commit would refuse - so it paints nothing (same mouth as "    \
        "finish())"


def test_the_fill_knows_its_holes(qapp):
    cv, pal = _stage(qapp)
    m = cv.model
    m.add_rect(m.point(-10.0, -6.0), m.point(10.0, 6.0))
    m.add_circle(m.point(0.0, 0.0), 2.0)      # a hole at the centre
    cv._solve()
    for _ in range(3):
        qapp.processEvents()
    pal.boxes["profile"].setChecked(False)
    for _ in range(3):
        qapp.processEvents()
    off = _grab(cv)
    pal.boxes["profile"].setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    on = _grab(cv)
    body = _diff(on[180:184, 272:288], off[180:184, 272:288])
    core = _diff(on[198:203, 298:303], off[198:203, 298:303])
    assert body > 8, "the plate fills"
    assert core <= 2, "the hole stays a HOLE - even-odd through "      \
        "regions(), the vendor's own nesting law"


def test_a_construction_edge_frees_the_fill(qapp):
    cv, pal = _stage(qapp)
    m = cv.model
    rect = m.add_rect(m.point(-10.0, -6.0), m.point(10.0, 6.0))
    rect[0].construction = True          # open the profile by law
    cv._solve()
    for _ in range(3):
        qapp.processEvents()
    win = (180, 220, 280, 320)
    pal.boxes["profile"].setChecked(False)
    for _ in range(3):
        qapp.processEvents()
    off = _grab(cv)[win[0]:win[1], win[2]:win[3]]
    pal.boxes["profile"].setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    assert _diff(_grab(cv)[win[0]:win[1], win[2]:win[3]], off) <= 4, \
        "guide geometry never bounds a profile - the fill obeys the "   \
        "SAME construction law finish() obeys"


# ---- one mouth: menu == palette == vis -----------------------------------------

def test_menu_palette_and_vis_are_one_mouth(qapp):
    from tracer.ui.sketcheditor import DISPLAY_LAYERS
    cv, pal = _stage(qapp)
    m = cv.model
    m.add_line(m.point(-4.0, 0.0), m.point(4.0, 0.0))
    cv._solve()
    cv._sel = []
    menu_labels = [a.text() for a in cv._build_menu().actions()]
    for key, menu_lbl, _word in DISPLAY_LAYERS:
        assert menu_lbl in menu_labels, f"the eye {key} answers at the "  \
            "canvas menu (M191 R3's door grows, it does not fork)"
    acts = {a.text(): a for a in cv._build_menu().actions() if a.text()}
    # the MENU flips: the vis moves AND the palette hears it
    acts["Show sketch points"].toggle()
    assert m.vis["points"] is False
    assert pal.boxes["points"].isChecked() is False, \
        "the palette follows the menu WITHOUT a rebuild - vis_changed "  \
        "is the shared voice"
    # the PALETTE flips: the vis moves (and the next menu reads it)
    pal.boxes["profile"].setChecked(False)
    assert m.vis["profile"] is False
    again = {a.text(): a for a in cv._build_menu().actions() if a.text()}
    assert again["Show profile fill"].isChecked() is False, \
        "the menu rebuilt reads the palette's answer - ONE state"
    # EVERY door is set_show_layer - the raw check
    cv.set_show_layer("dims", False)
    assert pal.boxes["dims"].isChecked() is False
    cv.set_show_layer("nonsense", False)     # unknown layer: silent NO
    assert set(m.vis) == {"refs", "dims", "constraints", "points",
                          "profile"}


def test_the_palette_resyncs_on_a_model_swap(qapp):
    cv, pal = _stage(qapp)
    m = cv.model
    m.add_line(m.point(-4.0, 0.0), m.point(4.0, 0.0))
    cv._solve()
    pal.boxes["constraints"].setChecked(False)
    assert m.vis["constraints"] is False
    m2 = SketchModel()
    cv.set_model(m2)                        # edit_sketch's own door
    for _ in range(3):
        qapp.processEvents()
    assert pal.boxes["constraints"].isChecked() is True, \
        "the NEW sketch answers with its OWN flags - the palette does "  \
        "not smear one sketch's eyes onto another (per-sketch truth)"
    assert m.vis["constraints"] is False, "the OLD sketch keeps its "    \
        "closed eye for its next visit"


# ---- the window doors -----------------------------------------------------------

def test_the_palette_lives_beside_the_canvas(win2, qapp2):
    win2.new_document()
    win2._edit_park_on = False
    win2._edit_park = None
    win2.action_new_sketch("XY")
    qapp2.processEvents()
    pal = win2._sketch_palette
    assert pal is not None and pal.isVisible()
    assert sorted(pal.boxes) == ["constraints", "dims", "points",
                                 "profile", "refs"]
    assert pal.status.text() == "Status: \u2014", \
        "the fresh sheet carries no verdict yet"
    cv = win2.sketch
    cv._snap_grid = False
    m = cv.model
    m.add_line(m.point(-4.0, 0.0), m.point(4.0, 0.0))
    cv._solve()
    qapp2.processEvents()
    assert pal.status.text() == "Status: Under-Constrained", \
        "the head lives OFF state_changed - the window's own solve "     \
        "feeds it, no second solver"


def test_the_eyes_ride_the_commit_the_file_and_the_wake(win2, qapp2,
                                                        monkeypatch):
    from tracer.ui.cmddialog import Shell
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *a, **k: (5.0, True)))
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    win2.new_document()
    win2._edit_park_on = False
    win2._edit_park = None
    win2.action_new_sketch("XY")
    qapp2.processEvents()
    cv = win2.sketch
    pal = win2._sketch_palette
    cv._snap_grid = False
    m = cv.model
    m.add_rect(m.point(1.0, 1.0), m.point(9.0, 7.0))
    pal.boxes["dims"].setChecked(False)
    pal.boxes["profile"].setChecked(False)
    cv._solve()
    cv.finish()
    qapp2.processEvents()
    feats = [f for f in win2.doc.features if getattr(f, "sketch", None)]
    assert feats, "the sketch committed into a feature"
    assert feats[0].sketch["vis"]["dims"] is False
    assert feats[0].sketch["vis"]["profile"] is False, \
        "the closed eyes ride INTO THE FILE with the sketch"
    win2.edit_sketch(feats[0])
    qapp2.processEvents()
    assert win2.sketch.model.vis["dims"] is False, "the wake re-closes"
    assert pal.boxes["dims"].isChecked() is False, \
        "and the PALETTE re-syncs on the swap (model_changed) - the "    \
        "maker's eyes survived the whole round trip"


def test_a_legacy_file_wakes_all_eyes_open(win2, qapp2, monkeypatch):
    from tracer.core.document import PrimitiveFeature
    from tracer.core.sketch.model import model_to_dict
    win2.new_document()
    win2._edit_park_on = False
    win2._edit_park = None
    d = win2.doc
    d.add(PrimitiveFeature(name="Plate", kind="box", op="union",
                           dims={"dx": 40.0, "dy": 40.0, "dz": 4.0}))
    mm = SketchModel()
    mm.add_rect(mm.point(1.0, 1.0), mm.point(9.0, 7.0))
    payload = model_to_dict(mm)
    payload["vis"] = {"refs": True, "dims": False,
                      "constraints": True}    # the pre-R1 trio
    from tracer.core.document import ExtrudeFeature
    f = d.add(ExtrudeFeature(name="Ridge", height=3.0, sid=919201,
                             outer=np.array([[1, 1], [9, 1], [9, 7],
                                             [1, 7]], float),
                             sketch=payload))
    win2.edit_sketch(f)
    qapp2.processEvents()
    vis = win2.sketch.model.vis
    pal = win2._sketch_palette
    assert vis["dims"] is False, "the old file's OWN answer still rides"
    assert vis["points"] and vis["profile"], \
        "eyes the file never mention wake OPEN - a missing key is "      \
        "silence, not a closed lid"
    assert pal.boxes["points"].isChecked() and \
        pal.boxes["profile"].isChecked()
    assert not pal.boxes["dims"].isChecked()


# ================= R2: FIND UNDER-CONSTRAINED [SKT-FIND-UNDERCONSTRAINED] ======
# "Click Find Under-Constrained. A list of under-constrained sketch
# entities displays in the palette. In the list, select a sketch entity.
# The geometry highlights on the canvas and the view zooms to it.
# (Optional) Click X on a row in the list to delete that under-
# constrained sketch entity. X is not available for sketch points.
# (Optional) Hide fully constrained geometry... While Find Under-
# Constrained is active, add constraints or dimensions... The list and
# sketch status update... Click Compute Sketch." Three fidelity laws we
# honour: the WHO-IS-FREE oracle is the SAME witness the paint wears
# (_ent_locked); the highlight is the SAME selection glow; the focus
# eye is TRANSIENT - command-bound, never file-borne.

from PySide6.QtCore import Qt                                        # noqa
from PySide6.QtWidgets import QToolButton                            # noqa


def _row_ents(pal):
    return [pal.rows.item(i).data(Qt.UserRole)
            for i in range(pal.rows.count())]


def _fix_pt(cv, p):
    from tracer.core.sketch.constraints import Fixed
    cv.model.constrain(Fixed(p, x=p.x), Fixed(p, y=p.y))


def _r2_scene(qapp):
    """A pinned (DEFINED) line beside a FREE line with one lone point."""
    cv, pal = _stage(qapp)
    m = cv.model
    tamed = m.add_line(m.point(-10.0, 8.0), m.point(10.0, 8.0))
    for p_ in (tamed.a, tamed.b):
        _fix_pt(cv, p_)
    free = m.add_line(m.point(-4.0, -6.0), m.point(4.0, -6.0))
    lone = m.point(9.0, -6.0)
    cv._solve()
    for _ in range(3):
        qapp.processEvents()
    return cv, pal, m, tamed, free, lone


def test_the_finder_lists_exactly_the_free_entities(qapp):
    cv, pal, m, tamed, free, lone = _r2_scene(qapp)
    rows = cv.finder_rows()
    labels = [lbl for lbl, _ in rows]
    ents = [e for _, e in rows]
    assert free in ents and lone in ents, \
        "the free line and the lone point answer the list"
    assert tamed not in ents, "DEFINED geometry is NOT under-constrained "  \
        "- the list reads the SAME witness the paint wears (LAW-55): no "   \
        "row can contradict the canvas"
    assert labels == ["Line 2", "Point 3", "Point 4", "Point 5"], \
        "the vendor's list speaks in entity names - and the numbering "  \
        "is the MODEL's truth: every point lives in the sketch's point "\
        "table (tamed endpoints are Points 1-2 and drop; the free line "\
        "carries 3-4, the lone point is 5 - an endpoint with no law on "\
        "it IS free geometry, and the finder says so)"


def test_the_rows_only_dance_when_the_finder_is_open(qapp):
    cv, pal, m, tamed, free, lone = _r2_scene(qapp)
    assert not pal.rows.isVisible(), "the list is the COMMAND's, not a "  \
        "permanent crowd in the panel"
    pal.find_btn.setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    assert pal.rows.isVisible() and pal.hide_fc.isVisible() \
        and pal.compute_btn.isVisible()
    assert pal.rows.count() == len(cv.finder_rows())


def test_selecting_a_row_highlights_and_zooms(qapp):
    cv, pal, m, tamed, free, lone = _r2_scene(qapp)
    pal.find_btn.setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    ents = _row_ents(pal)
    pal.rows.setCurrentRow(ents.index(free))
    for _ in range(3):
        qapp.processEvents()
    assert cv._sel == [free], "the row's highlight is the SELECTION glow "  \
        "- one highlight dialect on this canvas"
    assert tuple(cv._center) == pytest.approx((0.0, -6.0)), \
        "the view ZOOMS TO IT: the line's midpoint owns the centre"
    assert cv._scale > 4.0 and cv._scale <= 24.0, "zoomed in, capped in"


def test_the_row_X_deletes_that_entity(qapp):
    cv, pal, m, tamed, free, lone = _r2_scene(qapp)
    pal.find_btn.setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    i = _row_ents(pal).index(free)
    row_w = pal.rows.itemWidget(pal.rows.item(i))
    xs = row_w.findChildren(QToolButton)
    assert len(xs) == 1, "one row, one X"
    xs[0].click()
    for _ in range(3):
        qapp.processEvents()
    assert free not in m.sketch.lines, "X deletes THAT under-constrained "  \
        "entity - through the history door (undoable, like Del)"
    assert free not in _row_ents(pal), "and the row LEAVES with it: the "   \
        "list updates as you work"


def test_point_rows_carry_no_X(qapp):
    cv, pal, m, tamed, free, lone = _r2_scene(qapp)
    pal.find_btn.setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    i = _row_ents(pal).index(lone)
    row_w = pal.rows.itemWidget(pal.rows.item(i))
    assert not row_w.findChildren(QToolButton), \
        "X is not available for sketch points - the vendor's rule, ours"


def test_the_list_and_head_update_as_you_work(qapp):
    cv, pal, m, tamed, free, lone = _r2_scene(qapp)
    pal.find_btn.setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    n0 = pal.rows.count()
    _fix_pt(cv, free.a)
    _fix_pt(cv, free.b)
    cv.model.delete_entity(lone)          # the lone point leaves too
    cv._solve()
    for _ in range(3):
        qapp.processEvents()
    assert pal.rows.count() < n0, "every solve refreshes the list - the "  \
        "vendor's sentence, our wiring (state_changed feeds it, no timer)"
    assert pal.rows.count() == 0 and \
        pal.status.text() == "Status: Constrained", \
        "the last freedom tamed: EMPTY list, Constrained head - the "      \
        "command ends where the law begins"


def test_the_selected_row_survives_the_live_refresh(qapp):
    cv, pal, m, tamed, free, lone = _r2_scene(qapp)
    pal.find_btn.setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    pal.rows.setCurrentRow(_row_ents(pal).index(free))
    cv.remove_entity(lone)                # any other edit re-solves...
    for _ in range(3):
        qapp.processEvents()
    it = pal.rows.currentItem()
    assert it is not None and it.data(Qt.UserRole) is free, \
        "the maker's picked row rides the refresh - the list may rebuild, "  \
        "but the command keeps their selection"


def test_the_focus_eye_steps_defined_geometry_aside(qapp):
    cv, pal, m, tamed, free, lone = _r2_scene(qapp)
    pal.find_btn.setChecked(True)          # NO row click here: clicking
    for _ in range(3):                     #   one ZOOMS (its own gate),
        qapp.processEvents()               #   and a zoomed-away line is
    before = _grab(cv)                     #   no witness about the eye
    sx = before.shape[1] / cv.width()      # DPR-proof: map the canvas's
    sy = before.shape[0] / cv.height()     #   own answer into grab px

    def white(cell, y0, y1, x0, x1):
        b = cell[y0:y1, x0:x1].astype(int)
        return int(((b > 190).all(axis=2)).sum())

    def blue(cell, y0, y1, x0, x1):
        b = cell[y0:y1, x0:x1].astype(int)
        return int(((b[:, :, 2] - b[:, :, 0]) > 40).sum())

    def band(ent):
        """the entity's stroke, in GRAB px: the canvas itself (w2s)
        says where the paint lands - no hardcoded world->pixel math.
        The inset is PROPORTIONAL (a fixed px trim devours a short
        line at fit scale: 8 world units here are only 32 px)."""
        pa = cv.w2s(ent.a.x, ent.a.y)
        pb = cv.w2s(ent.b.x, ent.b.y)
        x0, x1 = sorted((int(pa.x() * sx), int(pb.x() * sx)))
        inset = max(2, (x1 - x0) // 10)
        y = int((pa.y() + pb.y()) / 2 * sy)
        return y - 6, y + 7, x0 + inset, x1 - inset

    ty0, ty1, tx0, tx1 = band(tamed)
    fy0, fy1, fx0, fx1 = band(free)
    w0 = white(before, ty0, ty1, tx0, tx1)
    b0 = blue(before, fy0, fy1, fx0, fx1)
    pal.hide_fc.setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    after = _grab(cv)
    w1 = white(after, ty0, ty1, tx0, tx1)
    b1 = blue(after, fy0, fy1, fx0, fx1)
    assert w0 > 20 and w1 < w0 // 3, \
        "hide fully constrained: the DEFINED line LIFTS off the canvas "    \
        f"({w0} -> {w1} white px) - the focus the vendor sells"
    assert b0 > 20 and b1 > 20, "the FREE line's blue keeps its ink - "    \
        "the eye steps the tamed aside, it never blinds the rest"
    assert m.vis == {"refs": True, "dims": True, "constraints": True,
                     "points": True, "profile": True}, \
        "the focus eye is TRANSIENT (command-bound): the FILE's eyes "      \
        "are untouched - it never rides model.vis"


def test_the_eye_releases_when_the_command_closes(qapp):
    cv, pal, m, tamed, free, lone = _r2_scene(qapp)
    pal.find_btn.setChecked(True)
    pal.hide_fc.setChecked(True)
    assert cv._hide_fc is True
    pal.find_btn.setChecked(False)
    for _ in range(3):
        qapp.processEvents()
    assert not pal.rows.isVisible() and not pal.hide_fc.isChecked() \
        and cv._hide_fc is False, \
        "walking away from the command closes its eye - transient means "  \
        "transient"


def test_compute_sketch_re_derives_the_whole_sheet(qapp):
    cv, pal, m, tamed, free, lone = _r2_scene(qapp)
    pal.find_btn.setChecked(True)
    for _ in range(3):
        qapp.processEvents()
    n0 = pal.rows.count()
    sneak = m.add_line(m.point(-2.0, -12.0), m.point(2.0, -12.0))
    # NO solve: the palette holds the stale read until asked
    assert sneak not in _row_ents(pal), "stale by construction (the "       \
        "probe's own honesty)"
    pal.compute_btn.click()
    for _ in range(3):
        qapp.processEvents()
    assert sneak in _row_ents(pal) and pal.rows.count() > n0, \
        "Compute Sketch: 'Fusion analyzes all geometry in the sketch and "  \
        "updates the constraint status for each sketch entity' - our "      \
        "answer is the ONE solve every other door already rides"


def test_the_finder_lives_in_the_real_page(win2, qapp2):
    win2.new_document()
    win2._edit_park_on = False
    win2._edit_park = None
    win2.action_new_sketch("XY")
    qapp2.processEvents()
    cv = win2.sketch
    pal = win2._sketch_palette
    cv._snap_grid = False
    m = cv.model
    free = m.add_line(m.point(-4.0, 0.0), m.point(4.0, 0.0))
    cv._solve()
    qapp2.processEvents()
    pal.find_btn.setChecked(True)
    qapp2.processEvents()
    assert free in _row_ents(pal)
    pal.rows.setCurrentRow(_row_ents(pal).index(free))
    qapp2.processEvents()
    assert cv._sel == [free], "in the REAL window the row commands the "   \
        "SAME canvas the toolbar drives"
    i = _row_ents(pal).index(free)
    xs = pal.rows.itemWidget(pal.rows.item(i)).findChildren(QToolButton)
    xs[0].click()
    qapp2.processEvents()
    assert free not in m.sketch.lines and free not in _row_ents(pal)


# ================= R4: THE NEWBORN'S MARKING MENU [SKT-CREATE-DIMENSIONS] ======
# "Before you place a dimension in the canvas, right-click to access
# contextual options for it. Examples: Radius or Diameter; Driven or
# Driving; Pick Circle/Arc Center or Pick Circle/Arc Tangent." The menu
# is CONTEXTUAL (the radial newborn hears all three pairs; a linear one
# answers Driven/Driving), every item PLACES through one mouth, and
# dismissing it places NOTHING - the command stays active. M178 R2's
# land-as-driven survives as the 'Driven' item: the law moved from the
# bare mouse to the documented menu (its own helper in test_m178 now
# triggers the item - the ONE legitimate door-evolution).

from PySide6.QtCore import QPointF                                   # noqa


def _mark_acts(cv):
    return [a.text() for a in
            cv._build_dim_marking_menu(QPointF(10, 10)).actions()
            if a.text()]


def _fire(cv, text, x, y):
    p = cv.w2s(x, y).toPoint()
    menu = cv._build_dim_marking_menu(QPointF(p))
    acts = {a.text(): a for a in menu.actions() if a.text()}
    acts[text].trigger()


def _linear_newborn(cv, m):
    ln = m.add_line(m.point(0.0, 0.0), m.point(8.0, 0.0))
    cv._sel = [ln]
    cv._solve()
    cv.act_dim()
    return cv._dim_place


def _radial_newborn(cv, m):
    c = m.add_circle(m.point(20.0, 10.0), 5.0)
    cv._sel = [c]
    cv._solve()
    cv.act_dim()
    return cv._dim_place, c


def test_a_linear_newborn_hears_driven_or_driving(qapp):
    cv, pal = _stage(qapp)
    d = _linear_newborn(cv, cv.model)
    assert d is not None
    assert _mark_acts(cv) == ["Driven", "Driving"], \
        "the vendor's pair, in the vendor's order - a linear ghost has "\
        "no radius to rename and no circle centre to pick"


def test_a_radial_newborn_hears_the_full_marking_menu(qapp):
    from tracer.core.sketch.model import speaks_dia
    cv, pal = _stage(qapp)
    r, _c = _radial_newborn(cv, cv.model)
    assert _mark_acts(cv) == ["Radius", "Diameter", "Driven", "Driving",
                              "Pick Circle/Arc Center",
                              "Pick Circle/Arc Tangent"], \
        "all three documented pairs for the radial ghost"
    assert speaks_dia(r) and r.value == pytest.approx(5.0), \
        "'Circles create diameter dimensions' - the birth already speaks "\
        "diameter while the stored value stays the radius (M98's law)"


def test_the_driven_item_is_the_old_landing(qapp):
    cv, pal = _stage(qapp)
    d = _linear_newborn(cv, cv.model)
    _fire(cv, "Driven", 4.0, -6.0)
    for _ in range(3):
        qapp.processEvents()
    assert cv._dim_place is None and d.driven, \
        "M178 R2's law VERBATIM, now through the documented item: the "\
        "newborn lands where the menu was called, DRIVEN from birth"
    assert cv._dim_edit is None, "a READER cannot be commanded - the "\
        "editor stays SHUT (M178 R3's law rides the item)"


def test_the_driving_item_places_like_the_left_press(qapp):
    cv, pal = _stage(qapp)
    d = _linear_newborn(cv, cv.model)
    _fire(cv, "Driving", 4.0, 6.0)
    for _ in range(3):
        qapp.processEvents()
    assert cv._dim_place is None and not d.driven, "driving dialect"
    assert cv._dim_edit is not None, "and M175's own door: a placed "\
        "driving newborn opens the value field exactly as a left click "\
        "would - one placement law, not a private one"
    cv._close_dim_editor()


def test_the_voice_items_change_dialect_never_magnitude(qapp):
    cv, pal = _stage(qapp)
    r, _c = _radial_newborn(cv, cv.model)
    _fire(cv, "Radius", 20.0, 2.0)
    for _ in range(3):
        qapp.processEvents()
    assert r.dia is False and r.value == pytest.approx(5.0), \
        "'Radius or Diameter' is act_dia's OWN flag - dialect, never "\
        "magnitude (M174 R3): the stored radius does not stir"
    cv._close_dim_editor()
    r2, _c2 = _radial_newborn(cv, cv.model)
    _fire(cv, "Diameter", 26.0, 16.0)
    assert r2.dia is True and r2.value == pytest.approx(5.0)
    cv._close_dim_editor()


def test_the_anchor_pair_seats_the_chip(qapp):
    cv, pal = _stage(qapp)
    r, _c = _radial_newborn(cv, cv.model)
    _fire(cv, "Pick Circle/Arc Center", 26.0, 16.0)
    assert r.label_off == (0.0, 0.0), "PICK CENTER: the chip seats at "\
        "the anchor - the documented seat choice, not a random snap"
    cv._close_dim_editor()
    r2, _c2 = _radial_newborn(cv, cv.model)
    _fire(cv, "Pick Circle/Arc Tangent", 26.0, 16.0)
    assert max(abs(r2.label_off[0]), abs(r2.label_off[1])) > 1.0, \
        "PICK TANGENT: the chip seats where the hand called the menu "\
        "(M178's cursor seat, M175's near-snap included)"
    cv._close_dim_editor()


def test_dismissing_the_menu_places_nothing(qapp):
    cv, pal = _stage(qapp)
    d = _linear_newborn(cv, cv.model)
    cv._build_dim_marking_menu(QPointF(10, 10))   # building changes
    for _ in range(3):                           #   NOTHING
        qapp.processEvents()
    assert cv._dim_place is d, "the ghost survives a dismissed menu - "\
        "the command stays active, the newborn keeps following the "\
        "cursor (the vendor's options are CONTEXTUAL, not a placement)"
    cv._cancel_dim_place()


def test_the_menu_needs_a_newborn(qapp):
    cv, pal = _stage(qapp)
    assert _mark_acts(cv) == [], "no ghost, no options - the menu is "\
        "the newborn's voice, not a general canvas menu"


def test_a_stale_item_is_silent(qapp):
    cv, pal = _stage(qapp)
    from PySide6.QtWidgets import QMenu
    d = _linear_newborn(cv, cv.model)
    p = cv.w2s(4.0, -6.0).toPoint()
    menu = cv._build_dim_marking_menu(QPointF(p))
    acts = {a.text(): a for a in menu.actions() if a.text()}
    acts["Driven"].trigger()                     # d placed, driven
    e = _linear_newborn(cv, cv.model)            # a NEW ghost is alive
    acts["Driving"].trigger()                    # the OLD item fires
    for _ in range(3):
        qapp.processEvents()
    assert cv._dim_place is e and cv._dim_edit is None, \
        "a stale menu item commands NOTHING (m164's law): the live "\
        "ghost and the editor are untouched"
    cv._cancel_dim_place()


def test_a_marking_driven_birth_reports_the_walking_geometry(qapp):
    cv, pal = _stage(qapp)
    m = cv.model
    ln = m.add_line(m.point(0.0, 0.0), m.point(8.0, 0.0))
    cv._sel = [ln]
    cv._solve()
    cv.act_dim()
    _fire(cv, "Driven", 4.0, -6.0)
    assert cv._dim_place is None
    d = [c for c in m.sketch.constraints
         if getattr(c, "driven", False) and c.p is ln.a][-1]
    ln.b.x = 20.0
    m.solve()
    assert ln.b.x == pytest.approx(20.0), "the reader never yanks the "\
        "geometry back"
    assert d.value == pytest.approx(20.0), "and the quote FOLLOWED - "\
        "through the marking menu or the bare mouse, the driven dialect "\
        "is the SAME law (M178): one mouth, one truth"


def test_the_marking_menu_lives_on_the_real_page(win2, qapp2):
    from tracer.core.sketch.constraints import Distance
    win2.new_document()
    win2._edit_park_on = False
    win2._edit_park = None
    win2.action_new_sketch("XY")
    qapp2.processEvents()
    cv = win2.sketch
    cv._snap_grid = False
    m = cv.model
    ln = m.add_line(m.point(-4.0, 0.0), m.point(4.0, 0.0))
    cv._sel = [ln]
    cv._solve()
    cv.act_dim()
    assert [a.text() for a in cv._build_dim_marking_menu(
        QPointF(5, 5)).actions() if a.text()] == ["Driven", "Driving"], \
        "in the REAL window the newborn answers the SAME documented "\
        "menu the standalone stage plays"
    cv._cancel_dim_place()
    qapp2.processEvents()
    assert not [c for c in m.sketch.constraints
                if isinstance(c, Distance)], "and the unbirth is clean"


# ================= R5: THE OFFSET ASSOCIATION ON EVERY CURVE ===================
# [SKT-SKETCH-MODIFY-TOOLS, verbatim] "When you offset sketch curves, an
# offset constraint glyph is displayed on the original geometry and the
# offset geometry... To remove this association, select the offset glyph
# in the canvas, right-click, then select Delete." M187 gave the STRAIGHT
# paths this law (parallel weld + gap chip + dangling glyph). The vendor
# says "sketch curves" - so the lone circle now welds too (fresh centre
# Point + Concentric + the new RadialDistance row: r_child - r_parent =
# d), and the kernel path welds every child edge whose parent its own
# fingerprint can name uniquely. A welded twin sharing the centre POINT
# would be a FACT, not a PROMISE - and promises are what Delete frees.

from tracer.core.sketch.constraints import (Concentric, Fixed,          # noqa
                                            LineDistance, Parallel,
                                            Radius, RadialDistance)     # noqa


def _welded(qapp, d=3.0):
    """One circle, offset - the ring weld born. The paint is FORCED:
    hit lists are PER-PAINT (M192 R2's law banked in blood) - a bare
    processEvents may replay yesterday's frame and an empty _dim_hits
    then reads like a missing chip."""
    cv, pal = _stage(qapp)
    m = cv.model
    c = m.add_circle(m.point(0.0, 0.0), 5.0)
    cv._solve()
    made = m.add_offset(d)
    cv._solve()
    cv.update()
    for _ in range(4):
        qapp.processEvents()
    return cv, pal, m, c, made[0]


def _rows_of(m, cls):
    return [x for x in m.sketch.constraints if isinstance(x, cls)]


def test_the_lone_circle_offset_welds_its_copy(qapp):
    cv, pal, m, c, nc = _welded(qapp)
    assert nc.c is not c.c, "the copy is FRESH geometry, not a twin "   \
        "sharing the centre - identity is not a promise, and promises "  \
        "are what the vendor's Delete frees"
    assert nc.r == pytest.approx(8.0)
    assert _rows_of(m, Concentric) and _rows_of(m, RadialDistance), \
        "the association is minted AS LAWS: concentricity + the signed "\
        "ring gap (SKT-SKETCH-MODIFY-TOOLS: the glyph means a law)"
    res = cv._last_result
    assert res.converged and res.dof == 3, \
        "the weld drops EXACTLY the three degrees a free twin would "\
        "have (centre x/y, radius): the copy keeps nothing free of its "\
        "parent, and the ring pair floats as one"


def test_the_ring_gap_speaks_a_chip(qapp):
    cv, pal, m, c, nc = _welded(qapp)
    rd = _rows_of(m, RadialDistance)[0]
    hits = [cc for _rect, cc in cv._dim_hits if cc is rd]
    assert hits, "the gap wears a chip like any dimension - the witness "\
        "tick and the seat live on the +x ray between the rings"
    assert cv._dim_text(rd) == "3.00", "the chip speaks MAGNITUDE (the "\
        "sign says inward/outward, the number says how far: M187 R3's "\
        "law moved to rings)"
    cv2, _p2 = _stage(qapp)
    mm = cv2.model
    cc2 = mm.add_circle(mm.point(0.0, 0.0), 5.0)
    cv2._solve()
    mm.add_offset(-1.5)
    cv2._solve()
    inward = _rows_of(mm, RadialDistance)[0]
    assert inward.value == pytest.approx(-1.5) and \
        cv2._dim_text(inward) == "1.50", "an INWARD offset speaks "\
        "negative law, positive number - the copy ring inside, honest"


def test_the_chipped_pair_shows_the_chip_and_never_the_glyph(qapp):
    cv, pal, m, c, nc = _welded(qapp)
    conc = _rows_of(m, Concentric)[0]
    rd = _rows_of(m, RadialDistance)[0]
    assert any(cc is rd for _r, cc in cv._dim_hits), \
        "POSITIVE CONTROL first: the chip is on THIS frame's hit list "  \
        "- a negative on a stale frame would pass vacuously"
    assert not any(cc is conc for _r, cc in cv._constraint_hits), \
        "one voice per promise: the chipped pair shows the number, "     \
        "never a colliding glyph (M187 R4's law, ring-faithful)"


def test_the_welded_ring_reads_defined_when_the_parent_is_tamed(qapp):
    cv, pal, m, c, nc = _welded(qapp)
    m.constrain(Fixed(c.c, x=0.0), Fixed(c.c, y=0.0), Radius(c, 5.0))
    cv._solve()
    for _ in range(3):
        qapp.processEvents()
    assert cv._ent_locked(c) and cv._ent_locked(nc), \
        "LAW-55 rides the weld: tame the parent and the child ring "\
        "reads DEFINED - concentricity and the gap feed the SAME "\
        "witness the paint and the finder wear"
    assert cv.finder_rows() == [], "nothing free, no rows - the "\
        "association carries the truth through every door"


def test_dragging_the_parent_pulls_the_child_ring(qapp):
    cv, pal, m, c, nc = _welded(qapp)
    c.c.x = 6.0
    c.c.y = 2.0
    cv._solve(pins=[c.c])                # the CANVAS's drag law: the
    #   hand holds the grabbed centre. A raw model.solve() relaxes BOTH
    #   centres to consensus ((3,1) - the pair floats and the test
    #   measures nothing); pins is exactly what a real drag answers to.
    assert (nc.c.x, nc.c.y) == pytest.approx((6.0, 2.0), abs=1e-6), \
        "the association HOLDS: drag the parent and the copy swims "\
        "with it"
    assert nc.r - c.r == pytest.approx(3.0, abs=1e-6), "and the ring "\
        "gap is kept - a promise, not a coincidence"


def test_the_gap_chip_door_unlocks_the_ring(qapp):
    cv, pal, m, c, nc = _welded(qapp)
    rd = _rows_of(m, RadialDistance)[0]
    cv.act_remove_constraint(rd)             # the chip's OWN door
    for _ in range(3):
        qapp.processEvents()
    conc = _rows_of(m, Concentric)[0]
    assert not _rows_of(m, RadialDistance)
    cv.update()
    for _ in range(3):
        qapp.processEvents()
    assert any(cc is conc for _r, cc in cv._constraint_hits), \
        "delete the dimension and the distance UNLOCKS - the dangling "\
        "weld wears the offset GLYPH: the handle the vendor names"
    cv._hover_c = conc
    acts = {a.text() for a in cv._build_menu().actions() if a.text()}
    assert {"Add Offset Dimension", "Remove Association"} <= acts, \
        "right-clicking the glyph answers BOTH documented doors"


def test_the_glyph_restores_where_the_ring_stands(qapp):
    cv, pal, m, c, nc = _welded(qapp)
    rd = _rows_of(m, RadialDistance)[0]
    cv.act_remove_constraint(rd)
    nc.r = 12.0                               # the copy drifts free...
    m.solve()
    conc = _rows_of(m, Concentric)[0]
    cv.act_add_offset_dim(conc)
    back = _rows_of(m, RadialDistance)
    assert len(back) == 1 and back[0].value == pytest.approx(7.0), \
        "RESTORE stamps the gap AS IT STANDS (7.0 = 12-5), not the one "\
        "it was born with - the book's latest truth wins (LAW-59)"


def test_the_glyph_deletes_the_whole_association(qapp):
    cv, pal, m, c, nc = _welded(qapp)
    rd = _rows_of(m, RadialDistance)[0]
    cv.act_remove_constraint(rd)             # dangling (UI-reachable)
    conc = _rows_of(m, Concentric)[0]
    cv.act_remove_association(conc)          # the glyph's Delete door
    for _ in range(3):
        qapp.processEvents()
    assert not _rows_of(m, Concentric), \
        "'select the offset glyph, right-click, Delete' FREES the "\
        "association - the copy is now independent geometry (centre "\
        "floats, radius floats), nothing half-promises"
    res = m.solve()
    assert res.converged and res.dof == 6, "the twin degrees return: "\
        "3 for each ring, exactly as if the weld had never been"


def test_the_kernel_path_welds_what_it_can_name(qapp):
    cv, pal = _stage(qapp)
    m = cv.model
    m.add_rect(m.point(-10.0, -6.0), m.point(10.0, 6.0))
    m.add_circle(m.point(0.0, 0.0), 2.0)     # a hole: the round path
    cv._solve()
    made = m.add_offset(2.0, join="round")
    cv._solve()
    for _ in range(3):
        qapp.processEvents()
    welds = _rows_of(m, RadialDistance)
    par = _rows_of(m, Parallel)
    ld = _rows_of(m, LineDistance)
    assert par and ld, "the kernel polygon welds every straight child "\
        "whose parent the fingerprint names uniquely (receipt 6 says "\
        "'sketch curves', not 'the straight-loop shortcut')"
    res = cv._last_result
    assert res.converged, "twelve weld rows on a tessellated crowd "\
        "still solve"
    assert len(made) > 4, "and the arc fragments whose parents cannot "\
        "be named stay FREE - no fake promise"
    assert not welds, "ring laws belong to the lone-circle path; the "\
        "crowded one is honest line work only"


def test_the_ring_gap_rides_the_file(qapp):
    cv, pal, m, c, nc = _welded(qapp)
    d = model_to_dict(m)
    assert any(rec.get("t") == "rd" for rec in d["constraints"]), \
        "the association is IN THE FILE - a ring gap is geometry's "\
        "word, not a canvas cosmetic"
    back = model_from_dict(d)
    rds = [x for x in back.sketch.constraints
           if isinstance(x, RadialDistance)]
    assert len(rds) == 1 and rds[0].value == pytest.approx(3.0) \
        and rds[0].parent is back.sketch.circles[0] \
        and rds[0].child is back.sketch.circles[1], \
        "and the wake hands it the SAME two rings it was born between"


def test_undo_lifts_the_whole_weld(qapp, monkeypatch):
    # the gate walks the REAL door: act_offset pushes the ledger row
    # BEFORE it mints (M84's law), so one undo owes the whole weld.
    # Calling model.add_offset directly would leave NOTHING to undo -
    # the history belongs to the COMMAND, not the kernel (R5 lesson).
    from tracer.ui import cmddialog
    cv, pal = _stage(qapp)
    m = cv.model
    m.add_circle(m.point(0.0, 0.0), 5.0)
    cv._solve()
    monkeypatch.setattr(cmddialog, "ask",
                        staticmethod(lambda *a, **k: {"d": 3.0,
                                                      "j": "mitre"}))
    cv.act_offset()
    for _ in range(3):
        qapp.processEvents()
    assert _rows_of(m, RadialDistance) and len(m.sketch.circles) == 2, \
        "the toolbar's door welds exactly like the model's own"
    assert cv.undo_op()
    cv._solve()
    assert not _rows_of(cv.model, RadialDistance) \
        and not _rows_of(cv.model, Concentric) \
        and len(cv.model.sketch.circles) == 1, \
        "one gesture, one ledger row: undo takes the copy AND its "\
        "laws back together"


# ================= R6: DIMENSION PARAMETERS [SKT-CREATE-DIMENSIONS] =============
# "Enter a specific value. Click an existing dimension to reference it
# as a parameter." + "If the expression only references Driving
# dimensions, it is converted to a static value, and cannot be
# recovered by toggling ... back to Driving." + the chip menu's item
# word, verbatim: "Select Toggle Driven". M89 grew the sheet half
# (parameters into dimensions); this rung grows the SKETCH half: the
# dimension TABLE (d0, d1... by constraint order over length dims -
# angles stay out: what cannot bind cannot be borrowed), the click
# that borrows a name, dependency-ordered rebuilds, the cycle that
# idles LOUD, and the conversion the vendor says is permanent.

from PySide6.QtTest import QTest                                     # noqa
from tracer.core.sketch.constraints import (Angle, Distance,         # noqa
                                            LineDistance)
from tracer.ui import dimedit                                        # noqa


def _r6_scene(qapp):
    """Line 8 + circle r5 (bought diameter at birth) + a dangling-
    signed weld gap: three chips, three table seats, plus an ANGLE
    that must never join the table."""
    cv, pal = _stage(qapp)
    m = cv.model
    ln = m.add_line(m.point(0.0, 0.0), m.point(8.0, 0.0))
    ci = m.add_circle(m.point(0.0, 14.0), 5.0)
    cv._solve()
    cv._sel = [ln]
    cv.act_dim()
    d0 = cv._dim_place
    cv._dim_place = None                       # placed, no editor yet
    cv._sel = [ci]
    cv.act_dim()
    d1 = cv._dim_place
    cv._dim_place = None
    far = m.add_line(m.point(-20.0, 0.0), m.point(-20.0, 20.0))
    ld = LineDistance(ln.b, far, -28.0)          # signed gap AS IT
    m.constrain(ld)                              #  STANDS (right of an
    #                                            #   upward line reads
    #                                            #   negative: -28)
    an = Angle(far, math.pi / 2)                 # inclination the line
    m.constrain(an)                              #  ALREADY speaks: the
    #                                            #   rows must not fight
    #                                            #   the measured scene
    cv._solve()
    cv.update()
    for _ in range(4):
        qapp.processEvents()
    return cv, m, d0, d1, ld, an


def _chip_of(cv, c):
    return next(r for r, cc in cv._dim_hits if cc is c)


def test_the_table_names_every_length_dimension(qapp):
    from tracer.core.sketch.model import dim_table
    cv, m, d0, d1, ld, an = _r6_scene(qapp)
    tbl = dim_table(m.sketch)
    assert tbl == [d0, d1, ld] or [type(x).__name__ for x in tbl] == \
        ["Distance", "Radius", "LineDistance"], \
        "the table is LENGTH dimensions in constraint order (M89's "   \
        "lengths-only law survives: an angle cannot bind, so an angle " \
        "cannot be borrowed either)"
    assert cv._dim_token(d0) == "d0" and cv._dim_token(d1) == "d1" \
        and cv._dim_token(ld) == "d2", "the name is the TABLE seat"
    assert cv._dim_token(an) is None, "the angle chip has NO name - "   \
        "clicking it borrows nothing"


def test_a_borrowed_name_speaks_what_the_chip_speaks(qapp):
    cv, m, d0, d1, ld, _an = _r6_scene(qapp)
    vals, sc = cv._fx_env()
    assert vals["d0"] == pytest.approx(8.0), "the line's number"
    assert vals["d1"] == pytest.approx(10.0), "the circle's chip reads " \
        "DIAMETER - the name buys the Ø the maker sees, not the secret " \
        "radius (one voice, no second truth)"
    assert vals["d2"] == pytest.approx(28.0), "the weld gap reads "      \
        "MAGNITUDE - the sign is dialect, the name says how far"


def test_clicking_a_chip_borrows_its_name(qapp):
    cv, m, d0, d1, _ld, _an = _r6_scene(qapp)
    cv._open_dim_editor(d0)
    for _ in range(3):
        qapp.processEvents()
    ed = cv._dim_edit
    held = cv.focusWidget() is ed.edit           # POSITIVE CONTROL: the
    #   pen was in the field BEFORE the boundary. The test reads the
    #   WINDOW's focus chain, not edit.hasFocus(): _stage shows a palette
    #   as a SECOND top-level (M192 R2's law) and under offscreen the
    #   palette keeps app activation - hasFocus() then reads False even
    #   while nothing stole the pen. The law is about the CANVAS's own
    #   focusWidget surviving the reference click.
    QTest.mousePress(cv, Qt.LeftButton, pos=_chip_of(cv, d1).center().toPoint())
    QTest.mouseRelease(cv, Qt.LeftButton, pos=_chip_of(cv, d1).center().toPoint())
    for _ in range(3):
        qapp.processEvents()
    assert ed.edit.text() == "=d1", "the vendor's clause LITERALLY: "   \
        "click an existing dimension -> its name rides the field (the "  \
        "selected prefill YIELDS: the fx prefix is the whole door)"
    assert held and cv._dim_edit is ed \
        and cv.focusWidget() is ed.edit, \
        "the field SURVIVES the click (the focus-out farewell defers - " \
        "a reference is not a goodbye) and KEEPS THE PEN: the canvas' "   \
        "focus chain still ends in the field it started in"
    assert cv._dim_drag is None and cv._chip_defer is False \
        and cv._chip_pending is None, \
        "no label-drag race, no swallowed farewell left riding"


def test_reference_clicks_compose(qapp):
    cv, m, d0, d1, ld, _an = _r6_scene(qapp)
    cv._open_dim_editor(d0)
    for _ in range(3):
        qapp.processEvents()
    ed = cv._dim_edit
    for tgt in (d1, ld):
        QTest.mousePress(cv, Qt.LeftButton, pos=_chip_of(cv, tgt).center().toPoint())
        QTest.mouseRelease(cv, Qt.LeftButton, pos=_chip_of(cv, tgt).center().toPoint())
        for _ in range(2):
            qapp.processEvents()
    assert ed.edit.text() == "=d1 + d2", "a second reference click "     \
        "COMPOSES (glues through +, never welds 'd1d2' into an "         \
        "invalid word - house law where the docs are silent)"
    QTest.keyClick(ed.edit, Qt.Key_Return)
    for _ in range(3):
        qapp.processEvents()
    assert m.dim_exprs.get(0) == {"e": "d1 + d2", "t": "D"}, \
        "and the whole chain commits as ONE binding"
    assert d0.value == pytest.approx(38.0), "10 (the circle's SPOKEN "  \
        "diameter) + 28 (the gap's magnitude): the commit evaluates "    \
        "exactly what the chips read"


def test_the_rebuild_follows_the_borrowed_line_in_any_order(qapp):
    from tracer.core.sketch.model import dim_speech
    cv, m, d0, d1, _ld, _an = _r6_scene(qapp)
    m.dim_exprs[0] = {"e": "d1*2", "t": "D"}      # consumer FIRST in
    m.dim_exprs[1] = {"e": "width", "t": "DIA"}   #  the table too
    warns = m.apply_dim_params({"width": 30.0})
    assert warns == []
    assert d1.value == pytest.approx(15.0), "the producer ran: r=15 "\
        "speaks a 30.00 diameter"
    assert d0.value == pytest.approx(60.0), \
        "the consumer saw the FRESH 30 (not yesterday's 10): bound "    \
        "rows evaluate in DEPENDENCY order in ONE rebuild"
    assert dim_speech(m.sketch, d1) == pytest.approx(30.0)


def test_a_circular_formula_idles_loudly(qapp):
    cv, m, d0, d1, _ld, _an = _r6_scene(qapp)
    m.dim_exprs[0] = {"e": "d1 + d2", "t": "D"}
    m.dim_exprs[1] = {"e": "d0", "t": "DIA"}
    before = (d0.value, d1.value)
    warns = m.apply_dim_params({})
    assert any("circular" in w for w in warns), \
        "a ring of borrowers warns - it never spins, never half-"        \
        "computes, never silently picks a winner"
    assert (d0.value, d1.value) == pytest.approx(before), \
        "and the numbers STAND where they were"


def test_toggle_driven_staticizes_a_dim_only_formula(qapp):
    cv, m, d0, d1, ld, _an = _r6_scene(qapp)
    m.dim_exprs[0] = {"e": "d1 + d2", "t": "D"}
    cv.act_driven(d0)
    assert m.dim_exprs == {}, "the vendor's clause: an expression that " \
        "only references Driving dimensions is converted to a STATIC "   \
        "value AT THE TOGGLE - the formula is gone"
    cv.act_remove_constraint(ld)                 # clear the row that
    cv.act_remove_constraint([x for x in m.sketch.constraints
                              if isinstance(x, Angle)][0])
    #  would fight the walk (bindings keyed BELOW idx 2 do not shift)
    d0.q.x = 20.0                                # walk the geometry
    #   (Distance endpoints are .p/.q - and they ARE the line's Points)
    cv._solve()
    assert d0.value == pytest.approx(20.0), "driven means READING: the " \
        "chip quotes the walking line"
    cv.act_driven(d0)                              # back to driving
    assert m.dim_exprs == {}, "and it CANNOT BE RECOVERED by toggling " \
        "back - static means static"
    assert d0.value == pytest.approx(20.0), "making it driving again "  \
        "PINS WHERE IT READS (M178's round-trip law rides the static)"


def test_parameter_formulas_ride_the_toggle(qapp):
    cv, m, d0, _d1, _ld, _an = _r6_scene(qapp)
    m.dim_exprs[0] = {"e": "width", "t": "D"}
    cv.act_driven(d0)
    assert 0 in m.dim_exprs, "the clause names ONLY Driving dimensions " \
        "- a formula that borrows the SHEET keeps its fx (a law quoted " \
        "wider than its words was never a law)"
    cv.act_driven(d0)
    assert 0 in m.dim_exprs


def test_a_mixed_formula_rides_the_toggle(qapp):
    cv, m, d0, d1, _ld, _an = _r6_scene(qapp)
    m.dim_exprs[0] = {"e": "d1 + width", "t": "D"}
    cv.act_driven(d0)
    assert 0 in m.dim_exprs, "dimension AND parameter: not ONLY "       \
        "dimensions - the binding survives the conversion"


def test_undo_is_not_a_toggle(qapp):
    cv, m, d0, d1, ld, _an = _r6_scene(qapp)
    m.dim_exprs[0] = {"e": "d1 + d2", "t": "D"}
    cv.act_driven(d0)
    assert m.dim_exprs == {}
    assert cv.undo_op()
    got = cv.model.dim_exprs.get(0)
    assert got == {"e": "d1 + d2", "t": "D"}, \
        "'cannot be recovered by TOGGLING' - and undo is not a toggle, " \
        "it is the maker's time machine (the ledger row was pushed "    \
        "BEFORE the conversion died)"
    fresh = cv.model.sketch.constraints[0]
    assert not getattr(fresh, "driven", False)


def test_the_chip_menu_wears_the_vendors_word(qapp):
    cv, m, d0, d1, _ld, _an = _r6_scene(qapp)
    cv._hover_c = d0
    texts = [a.text() for a in cv._build_menu().actions() if a.text()]
    assert "Toggle Driven" in texts, "the item word VERBATIM from the "  \
        "doc ('Select Toggle Driven') - one item, and it answers at "    \
        "BOTH ends (M178's Make Driven/Driving pair was the same flip "  \
        "in house clothes)"
    cv.act_driven(d0)
    cv._hover_c = d0
    texts = [a.text() for a in cv._build_menu().actions() if a.text()]
    assert "Toggle Driven" in texts and "Make Driven" not in texts \
        and "Make Driving" not in texts


def test_the_real_page_borrows_names_too(win2, qapp2):
    win2.new_document()
    win2._edit_park_on = False
    win2._edit_park = None
    win2.action_new_sketch("XY")
    qapp2.processEvents()
    cv = win2.sketch
    cv._snap_grid = False
    m = cv.model
    la = m.add_line(m.point(-8.0, 0.0), m.point(0.0, 0.0))
    lb = m.add_line(m.point(2.0, 0.0), m.point(9.0, 0.0))
    cv._solve()
    cv._sel = [la]
    cv.act_dim()
    fa = cv._dim_place
    cv._dim_place = None
    cv._sel = [lb]
    cv.act_dim()
    fb = cv._dim_place
    cv._dim_place = None
    cv._solve()
    cv.update()
    for _ in range(4):
        qapp2.processEvents()
    cv._open_dim_editor(fa)
    for _ in range(3):
        qapp2.processEvents()
    QTest.mousePress(cv, Qt.LeftButton, pos=_chip_of(cv, fb).center().toPoint())
    QTest.mouseRelease(cv, Qt.LeftButton, pos=_chip_of(cv, fb).center().toPoint())
    for _ in range(3):
        qapp2.processEvents()
    assert cv._dim_edit is not None and cv._dim_edit.edit.text() == "=d1", \
        "on the REAL window the documented click borrows the name the "  \
        "same way the standalone stage plays it"
    cv._close_dim_editor()


# =========== R7: BROWSER SHOW DIMENSIONS + THE REFERENCE LIMITS ==============
# [SKT-CREATE-DIMENSIONS, Tips, verbatim]: "From the Browser, right-click
# a sketch and select Show Dimensions so you can easily reference
# dimensions in another sketch." + the same page's two limits, verbatim:
# "You cannot reference Driven dimensions in Tangent or Offset
# dimensions" + "If a Tangent or Offset dimension is Driven, you cannot
# reference it in other dimensions." Our offset family is the weld gap
# (LineDistance) and the ring gap (RadialDistance); Tangent is a bare
# CONSTRAINT - no chip, no number, nothing to reference. The Browser row
# is the FOURTH door on the ONE vis mouth (paint, the canvas menu and
# the palette eyes own the other three): an OPEN sketch flips through
# set_show_layer so every door hears; a CLOSED one flips the stored dict
# the file already carries (M191 R3) - that IS its truth while closed,
# woken faithfully on open. Eyes are not design (M162): no history row.
# The builder seam (_feature_menu_build) copies the canvas _build_menu
# pattern: the modal exec belongs to the CALLER - and that modality is
# why no gate ever executed this menu before: since M150 an in-function
# re-import of HoleFeature shadowed the name throughout, and EVERY
# browser right-click died UnboundLocalError (PySide swallows slot
# exceptions headless). The seam makes the invisible fatal.

from tracer.core.document import ExtrudeFeature, PrimitiveFeature      # noqa


def _boss_doc(win):
    """Plate + Boss (a REAL sid-carrying sketched extrude): the M191 R3
    recipe - the display-sync finds the open sketch BY sid."""
    win.new_document()
    win._edit_park_on = False
    win._edit_park = None
    d = win.doc
    d.add(PrimitiveFeature(name="Plate", kind="box", op="union",
                           dims={"dx": 40.0, "dy": 40.0, "dz": 4.0}))
    boss = d.add(ExtrudeFeature(
        name="Boss", outer=np.array([[0, 0], [10, 0], [10, 5]], float),
        height=4.0, sid=777900,
        sketch={"name": "SketchBoss", "lines": [], "circles": [],
                "arcs": [], "points": [], "constraints": [],
                "dims": []}))
    win.recompute()
    qapp2 = QApplication.instance()
    for _ in range(3):
        qapp2.processEvents()
    return d, boss


def _door(menu):
    acts = {a.text(): a for a in menu.actions() if a.text()}
    return acts.get("Show Dimensions")


def test_the_browser_row_wears_the_vendors_word(win2, qapp2):
    d, boss = _boss_doc(win2)
    da = _door(win2._feature_menu_build(boss))
    assert da is not None, \
        "the Browser tip LITERALLY (right-click a sketch, select Show "  \
        "Dimensions) - and the menu BUILDS AT ALL: the HoleFeature "     \
        "shadow-killed it on every right-click since M150; a modal exec " \
        "hid the death from every gate (PySide swallows slot exceptions)"
    assert da.isCheckable() and da.isChecked(), \
        "a checkable door reflecting the sketch's CURRENT truth: a "     \
        "fresh sketch shows its dimensions"


def test_a_closed_sketch_flips_its_stored_eyes(win2, qapp2):
    d, boss = _boss_doc(win2)
    _door(win2._feature_menu_build(boss)).trigger()
    assert boss.sketch["vis"]["dims"] is False, \
        "a CLOSED sketch has no canvas to command - the stored dict IS " \
        "its truth while closed (the same key M191 R3 made file-borne)"
    assert d.dirty, "a look still dirties the FILE: the flag rides it"


def test_the_file_wakes_and_the_hidden_chips_keep_no_hit(win2, qapp2):
    d, boss = _boss_doc(win2)
    _door(win2._feature_menu_build(boss)).trigger()          # CLOSED
    win2.edit_sketch(boss)
    qapp2.processEvents()
    cv = win2.sketch
    assert cv.model.vis["dims"] is False, \
        "model_from_dict WAKES the flag: right-click hide in one "       \
        "session, quiet chips in the next"
    cv._snap_grid = False
    ln = cv.model.add_line(cv.model.point(0.0, 0.0),
                           cv.model.point(8.0, 0.0))
    cv._solve()
    cv._sel = [ln]
    cv.act_dim()
    cv._dim_place = None
    cv._solve()
    cv.update()
    for _ in range(4):
        qapp2.processEvents()
    assert not cv._dim_hits, \
        "hidden dims keep NO hit (M191 R3's law re-pinned from the "     \
        "Browser side: paint == seat, an invisible chip cannot be "      \
        "clicked by an invisible cursor)"
    cv.set_show_layer("dims", True)                        # POSITIVE
    cv.update()                                            #  CONTROL
    for _ in range(4):
        qapp2.processEvents()
    assert len(cv._dim_hits) == 1, \
        "the OFF state was the story: one flip and the chip returns "    \
        "to the SAME post"


def test_the_open_sketch_flips_through_the_one_mouth(win2, qapp2):
    from tracer.ui.sketcheditor import SketchPalette
    d, boss = _boss_doc(win2)
    win2.edit_sketch(boss)
    qapp2.processEvents()
    cv = win2.sketch
    pal = win2.findChild(SketchPalette)
    assert pal is not None and pal.boxes["dims"].isChecked()
    da = _door(win2._feature_menu_build(boss))
    assert da.isChecked(), \
        "the row asks the OPEN sketch's canvas first: the live model "   \
        "is the truth while the sketch is on the page"
    n_hist = len(cv._hist)
    da.trigger()
    for _ in range(3):
        qapp2.processEvents()
    assert cv.model.vis["dims"] is False, \
        "the flip RODE set_show_layer - the ONE mouth, not a private "   \
        "dict poke"
    assert boss.sketch["vis"]["dims"] is False, \
        "and the file debt is paid by the SAME gesture (M191 R3 sync)"
    assert not pal.boxes["dims"].isChecked(), \
        "the palette EYE heard a signal it did not start: every door "   \
        "speaks, every door hears"
    assert len(cv._hist) == n_hist, \
        "eyes are not design (M162): the flip costs NO undo row"
    da.trigger()                               # vendor word TOGGLES
    for _ in range(3):
        qapp2.processEvents()
    assert cv.model.vis["dims"] and boss.sketch["vis"]["dims"] \
        and pal.boxes["dims"].isChecked(), \
        "the same item flips BOTH ways (Show / hide): one door, a "      \
        "switch, not a ratchet"


def test_a_driven_offset_earns_no_name(qapp):
    cv, m, d0, d1, ld, _an = _r6_scene(qapp)
    assert cv._dim_token(ld) == "d2", \
        "POSITIVE CONTROL first: a DRIVING weld gap sits in the table"
    ld.driven = True
    cv.update()
    for _ in range(3):
        qapp.processEvents()
    assert cv._dim_token(ld) is None, \
        "verbatim: 'If a Tangent or Offset dimension is Driven, you "    \
        "cannot reference it in other dimensions' - the click borrows "  \
        "NOTHING. The SEATS stay (re-seating names on every flag flip "  \
        "would silently rewrite every existing formula): d0 and d1 "     \
        "keep their words."
    assert cv._dim_token(d0) == "d0" and cv._dim_token(d1) == "d1"
    r = _chip_of(cv, ld)
    cv._open_dim_editor(d0)
    cv.window().activateWindow()               # REAL production posture:
    for _ in range(4):                         #  the farewell is a
        qapp.processEvents()                    #   FOCUS-OUT law, and
    #   offscreen a never-activated window means the field never truly
    #   HAD the app focus to lose (probe: activateWindow is the switch).
    #   Without it the editor simply stays open - honest, but it tests
    #   Qt's activation lottery, not the nameless-chip law.
    assert cv._dim_edit is not None             # the field is open
    QTest.mousePress(cv, Qt.LeftButton, pos=r.center().toPoint())
    QTest.mouseRelease(cv, Qt.LeftButton, pos=r.center().toPoint())
    for _ in range(3):
        qapp.processEvents()
    assert cv._dim_edit is None, \
        "a press on a NAMELESS chip is an ordinary press: the field's "  \
        "farewell LANDS (unchanged - close quietly); a reference was "   \
        "impossible, so the boundary stays M165's"


def test_an_offset_refusing_a_driven_number_is_loud_everywhere(qapp):
    cv, m, d0, d1, ld, _an = _r6_scene(qapp)
    d0.driven = True                       # clause 2: offsets may not
    before = ld.value                      #  read ANY driven number
    ok = cv._apply_dim_edit(ld, "=d0")
    assert ok is False and ld.value == before \
        and 2 not in m.dim_exprs, \
        "commit DOOR: refused, no binding, the number stands honest"
    assert "driven" in cv._warn_text and "offset" in cv._warn_text, \
        "and the refusal NAMES itself (the idle law: loud, never silent)"
    ed = dimedit.open(cv, ld)              # the FIELD door: red + retry
    for _ in range(3):
        qapp.processEvents()
    ed.edit.setText("=d0")
    QTest.keyClick(ed.edit, Qt.Key_Return)
    for _ in range(3):
        qapp.processEvents()
    assert cv._dim_edit is ed and ed._bad and 2 not in m.dim_exprs, \
        "the illegal reference is INVALID GRAMMAR: red border, field "   \
        "stays open for a retry (M165's law, no new dialect)"
    cv._close_dim_editor()
    d0.driven = False
    warns = m.apply_dim_params({})         # the ENGINE door (clause 1
    assert warns == [], "clean sheet, clean silence"


def test_the_stale_illegal_binding_idles_loudly_on_rebuild(qapp):
    cv, m, d0, d1, ld, _an = _r6_scene(qapp)
    cv._apply_dim_edit(ld, "=d0")          # legal while d0 DRIVES
    assert 2 in m.dim_exprs
    d0.driven = True                       # the world moved under it
    before = ld.value                      #  (toggle d0 later...)
    warns = m.apply_dim_params({})
    assert any("driven" in w and "idle" in w for w in warns), \
        "a binding the vendor would never mint idles WITH a warning at " \
        "rebuild - the engine never quietly re-mints an illegal promise"
    assert ld.value == before, "and the number STANDS where it was"


def test_the_weld_gap_keeps_its_side_through_the_formula(qapp):
    cv, m, d0, d1, ld, _an = _r6_scene(qapp)
    assert ld.value == pytest.approx(-28.0), "the scene's gap is INWARD"
    ok = cv._apply_dim_edit(ld, "=d0")     # d0 speaks 8.00
    assert ok and ld.value == pytest.approx(-8.0), \
        "the formula commands HOW FAR (the chip speaks magnitude) - "    \
        "which SIDE is the constraint's OWN sign: '=d0' on an inward "   \
        "gap lands at -8, never flipping the weld across the line"
    d0.value = 11.0
    warns = m.apply_dim_params({})
    assert warns == [] and ld.value == pytest.approx(-11.0), \
        "and the rebuild engine keeps the SAME law (twin, not drift)"
    cv._close_dim_editor() if cv._dim_edit else None
    assert cv._dim_text(ld) == "11.00", "the chip still SPEAKS "     \
        "magnitude while the store keeps the side (one voice, two jobs)"


def test_a_driven_offset_referenced_by_anyone_is_refused(qapp):
    from tracer.core.sketch.model import fx_refusable
    cv, m, d0, d1, ld, _an = _r6_scene(qapp)
    ld.driven = True
    reason = fx_refusable(m.sketch, d0, "d2 + 1")
    assert reason is not None and "driven offset" in reason, \
        "clause 1 bites EVERYWHERE: even a plain dimension may not "     \
        "quote a driven weld gap - the seat exists, the words do not"
    ok = cv._apply_dim_edit(d0, "=d2 + 1")
    assert ok is False and "driven offset" in cv._warn_text, \
        "the commit door enforces the SAME helper (one law, no "        \
        "per-mouth dialects)"
    assert 0 not in m.dim_exprs and d0.value == pytest.approx(8.0)
