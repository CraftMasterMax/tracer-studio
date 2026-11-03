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
