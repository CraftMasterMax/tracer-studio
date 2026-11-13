"""M201 R36 - a detail view: a boundary you DRAW, a crop that re-derives.

[Create a detail view, verbatim] "Click a point on the parent view to
place the center point of the detail boundary" / "Drag the cursor away
from the center point to adjust the size of the detail boundary and
location of the identifier, then click to place them" / "Click to place
the detail view on the sheet" - the page's THREE BEATS, driven here
with real mouse events. [Detail views, verbatim] "A detail view is a
drawing view that shows a portion of another drawing view at an
enlarged scale" - so the crop is a live PROJECTION (detail_cookie ->
project_view, the untouched pipeline), not a picture: it inherits
every law a view already obeys (style, hidden ink, the drafter's drag,
the layout assistant's slots). [Select a parent view, verbatim] the
parent list is "a base view, a projected view, or a section view" -
so iso (on no true plane) and a slice (no depth left) and a detail
itself are refused BY NAME, never silently. The boundary is
INTERACTIVE (the page prints no radius field), so a radius lives in
no dialog: the Size story is the mouse. The door is the page's second
verb - double-click carries Style (From Parent FIRST, the page's own
order), a Scale combo with NO "Fit (auto)" member an ENLARGED crop
cannot honestly answer, and the Name row the page scopes "section view
and detail view only"; the IDENTIFIER (the letter) is the tool's, not
the keyboard's, and a stored Name never eats it. Deviations only: the
entry carries {parent, c, r, a, name}, the 2:1 birth scale is the
page's word "enlarged" made concrete (ours - the page prints no
number), and a cleared Name pops the key back to letter-alone."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF                          # noqa: E402
from PySide6.QtGui import QImage, QMouseEvent               # noqa: E402
from PySide6.QtWidgets import QApplication                  # noqa: E402
import numpy as np                                          # noqa: E402

from tracer.core.document import (Document, HoleFeature,     # noqa: E402
                                  PrimitiveFeature)
from tracer.ui import cmddialog                              # noqa: E402
from tracer.ui.drawingview import VIEW_STYLE_INHERIT         # noqa: E402

VE = "Visible Edges"
PAIR = "Visible Edges and Hidden Edges"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    """The R34/R35 plate: 40x30x6 with a through bore at (20,15) and a
    blind pocket - real visible AND hidden ink for a crop to keep.
    Section A-A cuts through the bore and is stood beside its parent
    (a legal PARENT the page grants: a section view)."""
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


# ---- the page's beats, driven with real mouse events ------------------------------
def _p2c(cv, mm):
    z = cv._zoom
    return QPointF((mm[0] - cv._center.x()) * z + cv.width() / 2.0,
                   (cv._center.y() - mm[1]) * z + cv.height() / 2.0)


def _click(cv, mm):
    c = _p2c(cv, mm)
    for t in (QMouseEvent.Type.MouseButtonPress,
              QMouseEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(t, c, c, Qt_left(), Qt_left(),
                         Qt_NoModifier())
        (cv.mousePressEvent if t == QMouseEvent.Type.MouseButtonPress
         else cv.mouseReleaseEvent)(ev)


def _move(cv, mm):
    c = _p2c(cv, mm)
    cv.mouseMoveEvent(QMouseEvent(QMouseEvent.Type.MouseMove, c, c,
                                  Qt_left(), Qt_left(), Qt_NoModifier()))


def Qt_left():
    from PySide6.QtCore import Qt
    return Qt.MouseButton.LeftButton


def Qt_NoModifier():
    from PySide6.QtCore import Qt
    return Qt.KeyboardModifier.NoModifier


def _center_of(cv, name):
    fr = cv.placed()[name]
    return (fr["off"][0] + 0.5 * (fr["min"][0] + fr["max"][0]),
            fr["off"][1] + 0.5 * (fr["min"][1] + fr["max"][1]))


def _add_section(win, qapp, name="A-A"):
    win._on_section_line({"parent": "top", "p0": (20.0, 0.0),
                          "p1": (20.0, 30.0), "flip": False})
    qapp.processEvents()
    return name


def _arm(cv):
    notes = []
    cv.tool_note.connect(lambda t: notes.append(t))
    cv.set_detail_mode(True)
    return notes


def test_three_beats_place_a_live_enlarged_detail(win, qapp):
    cv = win.drawing
    _add_section(win, qapp)
    notes = _arm(cv)
    ctr = _center_of(cv, "A-A")
    _click(cv, ctr)                                    # beat 1: centre
    assert "drag the radius" in notes[-1].lower()
    _move(cv, (ctr[0] + 5.0, ctr[1] + 5.0))            # rubber drag
    _click(cv, (ctr[0] + 5.0, ctr[1] + 5.0))           # beat 2: radius
    assert "bare paper" in notes[-1].lower()
    _click(cv, (ctr[0] + 10.0, ctr[1] - 14.0))         # beat 3: place
    qapp.processEvents()
    dets = cv.details()
    assert len(dets) == 1
    det = dets[0]
    assert det["parent"] == "A-A"
    assert set(det) == {"parent", "c", "r", "a", "name"}   # deviations only
    letter = det["name"]
    assert letter == "B"                               # first free after A-A's A
    assert letter in cv.views()                        # a REAL projected source
    assert cv.views()[letter] != []                    # ...with ink
    assert cv.sheet()["vscale"][letter] == 2.0         # enlarged (ours: 2:1)
    assert "Detail" in win.status.currentMessage()


def test_iso_and_detail_and_slice_parents_are_refused_by_name(win, qapp):
    cv = win.drawing
    _add_section(win, qapp)
    notes = _arm(cv)
    # a base view ACCEPTS (the page's list): click top's centre
    _click(cv, _center_of(cv, "top"))
    assert "drag the radius" in notes[-1].lower()
    cv.set_detail_mode(False)
    # iso REFUSES by name
    notes = _arm(cv)
    _click(cv, _center_of(cv, "iso"))
    assert "cannot host a detail" in notes[-1] or "on no true plane" in notes[-1]
    assert len(cv.details()) == 0
    cv.set_detail_mode(False)
    # a SLICE (no depth) REFUSES by name - and the slice rides the
    # LINE form (the axis path has no slice: _sec_cut's else-branch
    # ignores mode, so an axis entry is always a full half)
    cv.sheet().setdefault("sections", []).append(
        {"name": "S-S", "parent": "top", "p0": (32.0, 0.0),
         "p1": (32.0, 30.0), "flip": False, "mode": "slice"})
    qapp.processEvents()
    if "S-S" in cv.placed():
        notes = _arm(cv)
        _click(cv, _center_of(cv, "S-S"))
        assert "slice" in notes[-1].lower() or "no depth" in notes[-1].lower()
        cv.set_detail_mode(False)
    cv.sheet()["sections"] = [s for s in cv.sections() if s["name"] != "S-S"]
    qapp.processEvents()


def test_a_detail_cannot_parent_another_detail(win, qapp):
    cv = win.drawing
    _add_section(win, qapp)
    _arm(cv)
    ctr = _center_of(cv, "A-A")
    _click(cv, ctr)
    _click(cv, (ctr[0] + 5.0, ctr[1] + 5.0))
    _click(cv, (ctr[0] + 10.0, ctr[1] - 14.0))         # B exists, tool stays armed
    qapp.processEvents()
    letter = cv.details()[0]["name"]
    notes = []
    cv.tool_note.connect(lambda t: notes.append(t))
    _click(cv, _center_of(cv, letter))                 # click ON the detail
    assert "detail of a detail" in notes[-1].lower() or "unoffered" in notes[-1]
    assert len(cv.details()) == 1
    cv.set_detail_mode(False)


def test_the_boundary_and_label_are_real_ink(win, qapp):
    cv = win.drawing
    _add_section(win, qapp)

    def dark():
        img = cv.grab().toImage().convertToFormat(
            QImage.Format.Format_RGBA8888)
        a = np.frombuffer(img.constBits().tobytes(), np.uint8).reshape(
            img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), :3]
        return int((a.max(axis=2) < 140).sum())

    _arm(cv)
    ctr = _center_of(cv, "A-A")
    before = dark()
    _click(cv, ctr)
    _click(cv, (ctr[0] + 6.0, ctr[1] + 6.0))
    _click(cv, (ctr[0] + 11.0, ctr[1] - 15.0))
    qapp.processEvents()
    after = dark()
    assert after > before, "the boundary circle, bubble and label add ink"


def test_the_boundary_rides_the_parent_move(win, qapp):
    cv = win.drawing
    _add_section(win, qapp)
    _arm(cv)
    ctr = _center_of(cv, "A-A")
    _click(cv, ctr)
    _click(cv, (ctr[0] + 5.0, ctr[1] + 5.0))
    _click(cv, (ctr[0] + 10.0, ctr[1] - 14.0))
    qapp.processEvents()
    det = cv.details()[0]
    fr0 = cv.placed()["A-A"]
    p0 = cv._m2p(fr0, det["c"])
    base = list(cv.sheet().get("move", {}).get("A-A", [0.0, 0.0]))
    cv.sheet().setdefault("move", {})["A-A"] = [base[0] + 5.0, base[1] + 3.0]
    qapp.processEvents()
    fr1 = cv.placed()["A-A"]
    p1 = cv._m2p(fr1, det["c"])
    assert abs((p1[0] - p0[0]) - 5.0) < 1e-6          # boundary travels
    assert abs((p1[1] - p0[1]) - 3.0) < 1e-6          #   with the cut
    assert len(cv.details()) == 1                     # and re-derives, not redrawn


def test_the_door_is_style_scale_name_no_fit(win, qapp, monkeypatch):
    """The door's COMPOSITION is its fields spec - what ask() renders.
    Reading the spec is stricter than peeking at widgets (there is no
    rendering choice left to hide in) and honest: the page's order,
    the page's members, and the two refusals are all printed there.
    (The real dialog's PIXELS are the film's beat, F4 - the conftest
    guard keeps a live modal out of headless pytest by design.)"""
    cv = win.drawing
    _add_section(win, qapp)
    _arm(cv)
    ctr = _center_of(cv, "A-A")
    _click(cv, ctr)
    _click(cv, (ctr[0] + 5.0, ctr[1] + 5.0))
    _click(cv, (ctr[0] + 10.0, ctr[1] - 14.0))
    qapp.processEvents()
    letter = cv.details()[0]["name"]
    spec = {}
    seen = {}

    def spy(parent, title, fields, remember_key=None):
        seen["title"] = title
        for f in fields:
            spec[f["key"]] = f
        return None                              # reject: nothing lands

    monkeypatch.setattr(cmddialog, "ask", spy)
    cv.view_scale_requested.emit(letter)
    qapp.processEvents()
    assert seen["title"] == "Detail View"
    assert list(spec) == ["style", "scale", "name"]      # the page's ORDER
    assert spec["style"]["choices"][0] == VIEW_STYLE_INHERIT   # printed FIRST
    assert list(spec["style"]["choices"][1:]) == [VE, PAIR]
    assert "Fit (auto)" not in spec["scale"]["choices"]  # no auto for an
    #   enlarged crop (the assistant fit would fight the boundary radius)
    assert spec["name"]["kind"] == "text"
    assert spec["name"]["default"] == ""                 # letter alone at rest
    assert "hmarks" not in spec                          # the R35 row is not here
    assert "label" not in cv.details()[0]                # rejected: nothing lands


def test_from_parent_walks_from_the_detail(win, qapp, monkeypatch):
    cv = win.drawing
    _add_section(win, qapp)
    _arm(cv)
    ctr = _center_of(cv, "A-A")
    _click(cv, ctr)
    _click(cv, (ctr[0] + 5.0, ctr[1] + 5.0))
    _click(cv, (ctr[0] + 10.0, ctr[1] - 14.0))
    qapp.processEvents()
    letter = cv.details()[0]["name"]
    (cv.sheet().setdefault("vstyle", {}))["top"] = VE  # parent's own answer
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"style": VIEW_STYLE_INHERIT,
                                         "scale": "2:1", "name": ""})
    cv.view_scale_requested.emit(letter)
    qapp.processEvents()
    assert cv.sheet()["vstyle"][letter] == VIEW_STYLE_INHERIT
    assert cv.effective_style(letter) == VE            # the walk knows detail parents
    assert cv.hidden_page(letter) == []                #   and honours it


def test_the_name_row_is_deviations_only(win, qapp, monkeypatch):
    cv = win.drawing
    _add_section(win, qapp)
    _arm(cv)
    ctr = _center_of(cv, "A-A")
    _click(cv, ctr)
    _click(cv, (ctr[0] + 5.0, ctr[1] + 5.0))
    _click(cv, (ctr[0] + 10.0, ctr[1] - 14.0))
    qapp.processEvents()
    det = cv.details()[0]
    letter = det["name"]
    assert "label" not in det                          # no word yet (letter alone)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"style": cv.view_style(letter),
                                         "scale": "2:1", "name": "Rim"})
    cv.view_scale_requested.emit(letter)
    qapp.processEvents()
    det = cv.details()[0]
    assert det["label"] == "Rim"                       # the word is stored
    assert det["name"] == letter                       #   without eating the id
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"style": cv.view_style(letter),
                                         "scale": "2:1", "name": "  "})
    cv.view_scale_requested.emit(letter)
    qapp.processEvents()
    det = cv.details()[0]
    assert "label" not in det                          # cleared -> key pops
    assert det["name"] == letter                       #   the letter stands
