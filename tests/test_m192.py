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
