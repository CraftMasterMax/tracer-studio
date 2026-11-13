"""M201 R34 - "From Parent" arrives with the chain it can honestly walk.

[DWG-REF-DRAWING-VIEW-DLG, verbatim] "From Parent: Inherits the view
style from the parent view. (Projected view, section view, and detail
view only.)" - the page PRINTS the member first and scopes it AWAY
from base views, so it enters this kernel on the SECTION door (the
base door's pair stays m220's page law).  The style it inherits is
the PARENT'S EFFECTIVE member, resolved recursively: a stored member
answers itself; a stored "From Parent" walks to the parent; no stored
style is the OURS-declared rest - the pair for a base view (dashed
back ink today), the M137 flag for a section, and a SLICE's mode
outranks any style (no depth, nothing to hide).  Inheritance is
CHOSEN, never silently defaulted: the combo echoes the view's current
answer (an explicit "From Parent" if stored, else the flag's member).
Storage stays deviations-only: From Parent is a section's sole stored
vstyle entry; pair answers replace the inheritance and drive the
entry's tested flag exactly as R33 shipped; the file and one undo
carry all of it.  HONEST BOUNDARY, MEASURED LIVE before this rung
promised anything: plane_from_line REFUSES non-orthogonal parents
("section line needs an orthogonal parent view, not 'A-A'" - raised,
caught), so a SECTION parent cannot yet receive a section line: the
recursive walk is written for the day the nested door opens, and
until then From Parent rides one true hop to its base view.  Detail
and perspective views are not doors we own (declared). Cancel rides
the book-wide silence."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                   # noqa: E402

from tracer.core.document import (Document, HoleFeature,      # noqa: E402
                                  PrimitiveFeature)
from tracer.ui import cmddialog                              # noqa: E402
from tracer.ui.drawingview import VIEW_STYLE_INHERIT         # noqa: E402

PAIR = "Visible Edges and Hidden Edges"
VE = "Visible Edges"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    """M137's holed plate, section A-A across the bore: the parent of
    A-A is the base view "top"."""
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
    r.close()


def _sec(win):
    return win.drawing.sections()[0]


def _answer(monkeypatch, style, mode="Full", dist=10.0, flip=False,
            scale=""):
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": style, "scale": scale, "mode": mode, "dist": dist,
        "flip": flip})


def test_from_parent_stores_the_inheritance_and_leaves_the_flag_alone(
        win, qapp, monkeypatch):
    _answer(monkeypatch, VIEW_STYLE_INHERIT)
    win._on_section_edit("A-A")
    qapp.processEvents()
    assert win.drawing.sheet()["vstyle"]["A-A"] == VIEW_STYLE_INHERIT
    assert "hidden" not in _sec(win)           # the flag is NOT how
    #   inheritance rides - the parent answers instead
    assert "from parent" in win.status.currentMessage().lower()


def test_one_hop_off_inherited_visible_edges_overrides_the_flag_on(
        win, qapp, monkeypatch):
    cv = win.drawing
    (cv.sheet().setdefault("vstyle", {}))["top"] = VE   # parent's own
    _sec(win)["hidden"] = True                   # R33's flag says ON
    cv.sheet()["vstyle"]["A-A"] = VIEW_STYLE_INHERIT
    assert cv.effective_style("A-A") == VE       # inheritance wins
    assert cv.hidden_page("A-A") == []


def test_one_hop_on_inherited_pair_gives_the_section_its_ink_back(
        win, qapp):
    cv = win.drawing
    cv.sheet().pop("vstyle", None)               # parent at rest =
    #   the OURS-declared pair (base views show back ink today)
    assert "hidden" not in _sec(win)             # the section's own
    assert cv.hidden_page("A-A") == []           #   rest: no ink
    cv.sheet().setdefault("vstyle", {})["A-A"] = VIEW_STYLE_INHERIT
    assert cv.effective_style("A-A") == PAIR
    assert cv.hidden_page("A-A") != []           # inheritance GIVES
    #   ink back - overriding the flag is what inheriting MEANS


def test_a_slice_mode_outranks_any_inheritance(win, qapp):
    cv = win.drawing
    _sec(win)["mode"] = "slice"
    cv.sheet().setdefault("vstyle", {})["A-A"] = VIEW_STYLE_INHERIT
    assert cv.effective_style("A-A") == PAIR     # the member is
    #   inherited... but there is no depth left to hide behind:
    assert cv.hidden_page("A-A") == []           # the mode outranks
    _sec(win).pop("mode", None)


def test_the_combo_echoes_a_stored_inheritance(win, qapp, monkeypatch):
    cv = win.drawing
    cv.sheet().setdefault("vstyle", {})["A-A"] = VIEW_STYLE_INHERIT
    calls = []
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda p, t, fl, **k: (calls.append(
            {f["key"]: f.get("default") for f in fl}), None)[1])
    win._on_section_edit("A-A")
    qapp.processEvents()
    rests, = calls                  # ONE ask; the {key: default} dict
    assert rests["style"] == VIEW_STYLE_INHERIT  # echo law: chosen,
    #   never silently defaulted
    cv.sheet().pop("vstyle", None)


def test_a_pair_answer_replaces_the_inheritance_and_drives_the_flag(
        win, qapp, monkeypatch):
    cv = win.drawing
    cv.sheet().setdefault("vstyle", {})["A-A"] = VIEW_STYLE_INHERIT
    _answer(monkeypatch, PAIR)
    win._on_section_edit("A-A")
    qapp.processEvents()
    assert "vstyle" not in cv.sheet()            # inheritance gone
    assert _sec(win)["hidden"] is True           # flag law (R33)
    assert cv.hidden_page("A-A") != []


def test_the_base_door_still_refuses_from_parent_by_name(win, qapp,
                                                         monkeypatch):
    """The page scopes From Parent to section/projected/detail views:
    the BASE dialog never wears it - not even by scripted answer."""
    cv = win.drawing
    monkeypatch.setattr(cv, "_view_dialog",
                        lambda cur: {"style": VIEW_STYLE_INHERIT,
                                     "scale": "1:2"})
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert "unoffered by name" in win.status.currentMessage()
    assert "vstyle" not in cv.sheet()            # NOTHING landed
    assert "vscale" not in cv.sheet()


def test_from_parent_is_a_choosable_member_never_a_silent_rest(
        win, qapp, monkeypatch):
    cv = win.drawing
    calls = []
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda p, t, fl, **k: (calls.append(
            {f["key"]: f.get("default") for f in fl}), None)[1])
    win._on_section_edit("A-A")                  # unrest section:
    qapp.processEvents()                          #   the flag's own
    rests, = calls                                #   member rests
    assert rests["style"] == VE
    assert "vstyle" not in cv.sheet()             # and nothing is


def test_the_nesting_door_opens_on_refusal_named_by_the_kernel(win):
    """The honest boundary, PROVEN not assumed: the kernel refuses a
    section parent for a new section line - so From Parent rides one
    true hop until the nested door opens (the recursive walk is
    already written for it)."""
    from tracer.core import drawing as dr
    from tracer.core.drawing import plane_from_line
    with pytest.raises(ValueError, match="orthogonal parent view"):
        plane_from_line("A-A", (10.0, 2.0), (30.0, 2.0))
    # and the walk itself resolves chains of ANY length, even hand-
    # edited ones creation cannot make:
    cv = win.drawing
    vs = cv.sheet().setdefault("vstyle", {})
    vs["A-A"] = VIEW_STYLE_INHERIT
    vs["top"] = VE
    assert cv.effective_style("A-A") == VE       # one hop, real
    cv.sheet().setdefault("sections", []).append(
        {"name": "C-C", "parent": "A-A"})        # hand-edited chain
    vs["C-C"] = VIEW_STYLE_INHERIT               # (sections() hands
    #   back a COPY - the live list rides the sheet dict)
    assert cv.effective_style("C-C") == VE       # two hops: walks


def test_the_inheritance_rides_the_file_and_one_undo(win, qapp,
                                                     monkeypatch):
    _answer(monkeypatch, VIEW_STYLE_INHERIT)
    win._on_section_edit("A-A")
    qapp.processEvents()
    assert win.drawing.sheet()["vstyle"]["A-A"] == VIEW_STYLE_INHERIT
    back = Document.from_dict(win.doc.to_dict())      # file's word
    assert back.drawings[-1]["vstyle"]["A-A"] == VIEW_STYLE_INHERIT
    win.undo()
    qapp.processEvents()
    assert "A-A" not in (win.drawing.sheet().get("vstyle") or {})
