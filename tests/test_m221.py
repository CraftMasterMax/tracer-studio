"""M201 R33 - the section child's double-click answers the PAGE's dialog.

[DWG-REF-DRAWING-VIEW-DLG, verbatim; live-verified lanes D+E 2026-11-13]
The reference page's access line prints "Double-click a base view,
projected view, SECTION VIEW, detail view, or perspective view" - and
the creation page's own grammar closes the loop: pick a parent and
"The Drawing View dialog displays". A section's door IS the Drawing
View dialog, so M137's props door wears it now: title PAGE-PRINTED,
rows in the page's groups and order - Appearance (Style, Scale),
Section Depth (Depth, Distance, Set Distance), Objects to Cut. The
Depth members are the page's BARE words ("Full", "Slice",
"Distance"); their glosses stayed in the kernel's behavior, not pasted
into the combo. Distance's unit suffix, its range and its rest value
are OURS and say so: the book prints " mm" zero times and no numeric
example on any section page (lane E, 7 pages). "Set Distance: Click
to reset Distance." is the family's only UNSHIPPED row - it ships as
a real BUTTON (cmddialog grows kind "button"; where the page says
CLICK the door is a button, never a checkbox pretending; a button
contributes no answer value). The hidden-lines CHECK retires: the
PAGE controls back ink with STYLE, so the Style pair now answers the
entry's tested "hidden" flag - one knob, storage law untouched (M137
keeps its kernel gates exactly as they lived). The section's Style
REST is OURS-declared, echoing the entry's own answer: no back lines
is "Visible Edges" (M137/ASME truth). DEFERRED BY NAME, not hidden: "Name" (the page softens: "if needed";
our A-A scheme is declared, renaming is identity surgery),
Orientation/Reference/Representation (the page's own Notes call them
creation-only), the Edge-Visibility and Center-Mark rows (no kernel
records), "Shaded" (the line-art law - and refused by name in a
scripted answer, leaving not even an undo dent). "From Parent" -
deferred when this file was written - SHIPPED the next rung (its
gates live in test_m222). Cancel rides the book-wide silence."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (QApplication, QPushButton)     # noqa: E402

from tracer.core.document import (Document, HoleFeature,       # noqa: E402
                                  PrimitiveFeature)
from tracer.ui import cmddialog                                # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    """M137's own stage: the holed plate, section A-A across the
    bore centre - the half-plate carries REAL back ink (the bore's
    far rim), so "hidden lines on" is a fact, not a wish."""
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


def _spy(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda p, t, fl, **k: (calls.append((t, fl)), None)[1])
    return calls


# ---- the door --------------------------------------------------------------------

def test_the_section_door_wears_the_page_title_groups_and_order(win,
                                                                monkeypatch):
    calls = _spy(monkeypatch)
    win._on_section_edit("A-A")
    (title, fields), = calls                   # ONE ask, page words
    assert title == "Drawing View"             # PAGE-PRINTED (the
    #   creation page shows THIS dialog for a section child)
    keys = [f["key"] for f in fields]
    assert keys == ["style", "scale", "mode", "dist", "setdist",
                    "flip"]                    # Appearance first,
    #   then Section Depth - the page's group order
    groups = {f["key"]: f.get("group", "") for f in fields}
    assert groups["style"] == "Appearance" and groups["scale"] == \
        "Appearance"
    assert all(groups[k] == "Section Depth"
               for k in ("mode", "dist", "setdist", "flip"))


def test_the_depth_rows_speak_the_page_s_bare_words(win, monkeypatch):
    calls = _spy(monkeypatch)
    win._on_section_edit("A-A")
    (_, fields), = calls
    specs = {f["key"]: f for f in fields}
    assert specs["mode"]["choices"] == ["Full", "Slice", "Distance"]
    assert specs["dist"]["label"] == "Distance"          # page row
    assert specs["setdist"]["kind"] == "button"          # CLICK verb
    assert specs["setdist"]["target"] == "dist"
    assert specs["setdist"]["value"] == 10.0             # OURS rest
    #   (the book prints " mm" and any number ZERO times - declared)


def test_the_style_row_echoes_the_entry_s_own_answer(win, qapp,
                                                     monkeypatch):
    cv = win.drawing
    calls = _spy(monkeypatch)
    win._on_section_edit("A-A")
    (_, fields), = calls
    specs = {f["key"]: f for f in fields}
    assert specs["style"]["choices"] == [             # R34: the page
        "From Parent", "Visible Edges",               # prints From
        "Visible Edges and Hidden Edges"]             # Parent FIRST
    assert specs["style"]["default"] == "Visible Edges"   # unrest:
    #   M137 truth - a section reads without back ink
    _sec(win)["hidden"] = True
    calls.clear()
    win._on_section_edit("A-A")
    (_, fields), = calls
    specs = {f["key"]: f for f in fields}
    assert specs["style"]["default"] == "Visible Edges and Hidden Edges"
    _sec(win)["hidden"] = False


# ---- the Style pair drives the tested flag ----------------------------------------

def test_the_style_pair_lights_the_back_ink_and_extinguishes_it(
        win, qapp, monkeypatch):
    cv = win.drawing
    assert cv.hidden_page("A-A") == []          # M137 rest (ASME)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": "Visible Edges and Hidden Edges", "scale": "",
        "mode": "Full", "dist": 10.0, "flip": False})
    win._on_section_edit("A-A")
    qapp.processEvents()
    assert _sec(win)["hidden"] is True          # the page's member
    assert cv.hidden_page("A-A") != []          # answers the flag
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": "Visible Edges", "scale": "",
        "mode": "Full", "dist": 10.0, "flip": False})
    win._on_section_edit("A-A")
    qapp.processEvents()
    assert _sec(win)["hidden"] is False
    assert cv.hidden_page("A-A") == []


# ---- the button is a BUTTON ---------------------------------------------------------

def test_the_set_distance_button_resets_the_field(qapp):
    d = cmddialog.CommandDialog("Drawing View", None, None)
    d.add_double("dist", "Distance", 3.0)
    d.add_button("Set Distance", "dist", 10.0)
    qapp.processEvents()
    btns = d.findChildren(QPushButton)
    hits = [b for b in btns if b.text() == "Set Distance"]
    assert len(hits) == 1
    d._fields["dist"].setValue(37.5)
    hits[0].click()
    assert d._fields["dist"].value() == pytest.approx(10.0)
    assert "setdist" not in d.values()          # a button answers
    d.deleteLater()                             #   NOTHING


# ---- what the door does NOT wear ------------------------------------------------------

def test_the_deferred_rows_are_named_not_worn(win, monkeypatch):
    calls = _spy(monkeypatch)
    win._on_section_edit("A-A")
    (_, fields), = calls
    labels = [f["label"] for f in fields]
    assert "Name" not in labels                          # deferred
    #   by name: the page softens ("if needed"); A-A is our declared
    #   scheme, renaming is identity surgery
    assert "Set Start Point" not in labels
    # R34 SHIPPED "From Parent" on THIS door (the page scopes it to
    # section/projected/detail - it rides first); what stays deferred
    # by name: Name, Shaded (below) - and on the BASE door (m220)
    # From Parent remains page-refused.
    assert all("Shaded" not in f["label"] for f in fields)   # line art
    assert not any(f["kind"] == "check" and "hidden" in  # the check
                   f["label"].lower() for f in fields)   # retired


# ---- refusals ---------------------------------------------------------------------------------

def test_an_unoffered_style_answer_refused_by_name_changes_nothing(
        win, qapp, monkeypatch):
    before = win.doc.to_dict()                 # the whole document's
    #   word - a refused door may not even dent the undo stack
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": "Shaded", "scale": "1:2",       # combo cannot answer
        "mode": "Full", "dist": 10.0, "flip": False})   # this; script
    win._on_section_edit("A-A")                 # it anyway
    qapp.processEvents()
    assert "unoffered by name" in win.status.currentMessage()
    assert win.doc.to_dict() == before
    assert "hidden" not in _sec(win)


def test_the_style_edit_rides_the_file_and_one_undo(win, qapp,
                                                    monkeypatch):
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": "Visible Edges and Hidden Edges", "scale": "",
        "mode": "Full", "dist": 10.0, "flip": False})
    win._on_section_edit("A-A")
    qapp.processEvents()
    assert _sec(win)["hidden"] is True
    back = Document.from_dict(win.doc.to_dict())     # the file's word
    assert back.drawings[-1]["sections"][0]["hidden"] is True
    win.undo()                                       # one press back
    qapp.processEvents()
    assert "hidden" not in _sec(win)
