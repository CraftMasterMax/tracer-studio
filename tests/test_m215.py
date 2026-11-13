"""M201 R27 - the plane door wears the Construction Geometry dialog.

[SLD-CONSTRUCT-* pages, verbatim] every plane AND axis task prints
"The Construction Geometry dialog displays, Type is set to Plane|Axis
and Method is set to <METHOD>." - no Construct page is a reference
page, so this sentence (banked constr26) IS the dialog architecture:
title + Type + Method.  BOTH of the kernel's construct mouths wear it
- the plane door ("Type" = {Plane}) and the axis door ("Type" =
{Axis}; the page's Point member is UNOFFERED - no construction point
in this kernel).  Method wears the page members this kernel bakes,
page casing: Offset / At Angle / Through Three Points / Midplane, and
Through Two Points / Through Two Planes.  "Tangent", "Through Two
Edges", "Perpendicular Plane", "Along Path", "Through Cylinder/Cone/
Torus", "Through Edge", "Perpendicular To Face" UNOFFERED (every page
opens "In the canvas, select ..." - these doors ask nothing of the
canvas); Axis/Point Type members UNOFFERED (no construction axis or
point in this kernel).  The Offset page's "Select an Extent option:"
rides as {Distance} alone - "To Object" wants a picked vertex.  The
number row wears the page phrase "Offset value".  RESIZE - the ONLY
page-printed rest default in the set - stays UNOFFERED because
neither member bakes (planes wear the house size): honored by
citation, never by decoration that lies.  gtype and extent are
UI-only: legacy-shaped answers (their keys absent - and the rung-era
method words "Midplane between two") still drive, and the record is
planes as it always was.  The menu mouth is a house shape (the
vendor menu is per tool) and stays "Construction plane..." - m40
owns that pin."""
import inspect
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                          # noqa: E402

from tracer.ui import cmddialog                                     # noqa: E402
from tracer.ui.mainwindow import MainWindow                         # noqa: E402
from tracer.ui.renderer import SceneRenderer                        # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(cmddialog, "_REMEMBERED", {})   # process-global
    monkeypatch.setattr(cmddialog, "_REMEMBER_ON", {})
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _capture(win, monkeypatch):
    calls = []
    monkeypatch.setattr(cmddialog, "ask",
                        lambda p, t, fl, **k: (calls.append(
                            (t, [(f["key"], f["label"],
                                  f.get("choices")) for f in fl])),
                            None)[1])
    return calls


# ---- the dialog the pages name --------------------------------------------------

def test_the_door_wears_the_pages_title(win, monkeypatch):
    calls = _capture(win, monkeypatch)
    win.new_document()
    win.action_construction_plane()
    (title, rows), = calls
    assert title == "Construction Geometry"
    assert rows[0][:2] == ("gtype", "Type")           # the page's first row
    assert rows[0][2] == ["Plane"]                    # its ONE honest member
    assert rows[1][:2] == ("how", "Method")
    assert rows[1][2] == ("Offset", "At Angle", "Through Three Points",
                          "Midplane")                 # page members, page casing
    assert rows[2][:2] == ("extent", "Extent")
    assert rows[2][2] == ["Distance"]                 # To Object UNOFFERED
    # the born rows stand behind, in the born order, keys byte-true:
    assert [k for k, _l, _c in rows][3:] == ["base", "dist", "angle", "hinge",
                                             "p1", "p2", "p3", "pa", "pb"]
    assert [l for k, l, _c in rows if k == "dist"] == ["Offset value"]


# ---- the record law: UI rows ride, records stay planes ---------------------------

def test_legacy_shaped_answer_still_bakes_the_plane(win, qapp, monkeypatch):
    """An answer shaped like EVERY born reply - no gtype, no extent,
    and even the rung-era method word - must bake exactly what it
    baked before.  The page words ride the UI; the file keeps its
    slots (planes list, name, origin).  Midplane law: the kernel
    refuses NON-parallel planes (no silent best-fit lie), so the pair
    is XY and its own offset - the born law, untouched by the rename."""
    win.new_document()
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "how": "Offset", "base": "XY", "dist": 12.0,
        "angle": 45.0, "hinge": "u — plane's own X",
        "p1": "0,0,0", "p2": "10,0,0", "p3": "0,10,10",
        "pa": "XY", "pb": "XZ"})
    win.action_construction_plane()
    qapp.processEvents()
    assert win.doc.planes[0]["origin"] == [0.0, 0.0, 12.0]
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "how": "Midplane between two", "base": "XY", "dist": 12.0,
        "angle": 45.0, "hinge": "u — plane's own X",
        "p1": "0,0,0", "p2": "10,0,0", "p3": "0,10,10",
        "pa": "XY", "pb": "Plane 1"})
    win.action_construction_plane()
    qapp.processEvents()
    assert len(win.doc.planes) == 2
    p = win.doc.planes[1]
    assert "gtype" not in p and "extent" not in p     # no record pollution
    assert p["origin"] == [0.0, 0.0, 6.0]             # midway XY..Plane 1


def test_the_page_method_words_all_land(win, qapp, monkeypatch):
    """Every page word must DISPATCH, not just decorate: four answers
    in the pages' casing mint four planes, and the Offset member
    proves its meaning where the page states it - "Offsets the face
    or plane to a distance that you specify" - origin +12 mm off XY."""
    win.new_document()
    base = {"base": "XY", "dist": 12.0, "angle": 30.0,
            "hinge": "u — plane's own X", "p1": "0,0,0", "p2": "10,0,0",
            "p3": "0,10,10", "pa": "XY", "pb": "Plane 1",
            "gtype": "Plane", "extent": "Distance"}
    # Midplane walks LAST: its pair (XY + Plane 1, the offset this same
    # loop just baked) is parallel - the kernel's own refusal law.
    for how in ("Offset", "At Angle", "Through Three Points", "Midplane"):
        monkeypatch.setattr(cmddialog, "ask",
                            lambda *a, _h=how, **k: dict(base, how=_h))
        win.action_construction_plane()
        qapp.processEvents()
        assert "refused" not in win.status.currentMessage().lower()
    assert len(win.doc.planes) == 4
    assert len({p["name"] for p in win.doc.planes}) == 4
    off = [p for p in win.doc.planes if p["origin"] == [0.0, 0.0, 12.0]]
    assert len(off) == 1                              # the Offset member


# ---- the doors cite their pages, and their refusals --------------------------------

def _mouth(fn):
    src = inspect.getsource(fn)
    return " ".join(line.split("#", 1)[1] if line.lstrip().startswith("#")
                    else line for line in src.splitlines())


def test_the_door_quotes_the_pages_it_wears_and_refuses():
    mouth = " ".join(_mouth(MainWindow.action_construction_plane).split())
    for q in ("The Construction Geometry dialog displays, Type is set to "
              "Plane and Method is set to",
              "Select an Extent option:",
              "Offsets the face or plane to a sketch point or vertex "
              "that you select.",
              "Optional: Enter an Offset value to offset the plane from "
              "its computed position.",
              "Size the plane to fit the selected geometry.",
              "Size the plane to fill the current view.",
              "UNOFFERED"):
        assert q in mouth, q
    # the four refused method pages are NAMED, not silently dropped:
    for m in ("Tangent", "Through Two Edges", "Perpendicular Plane",
              "Along Path"):
        assert m in mouth, m


def test_the_menu_mouth_stays_house():
    """The vendor menu is PER TOOL; both doors are ONE-mouth houses,
    so their NAMES stay house facts.  And the page dialog title now
    rides TWO mouths (plane door + axis door) - two entrances to the
    one dialog the pages name - nowhere else (m40 pins the ribbon
    twins)."""
    src = open(inspect.getsourcefile(MainWindow), encoding="utf-8").read()
    assert "Construction plane" in src                 # menu/ribbon word lives
    assert "Work axis" in src                          # ditto the axis twin
    n_page = src.count('"Construction Geometry"')
    assert n_page == 2                                 # exactly the two doors
    for fn in (MainWindow.action_construction_plane,
               MainWindow.action_work_axis):
        assert "Construction Geometry" in _mouth(fn), fn.__name__


def test_the_axis_mouth_wears_the_other_type_member(win, monkeypatch):
    calls = _capture(win, monkeypatch)
    win.new_document()
    win.action_work_axis()
    (title, rows), = calls
    assert title == "Construction Geometry"
    assert rows[0][:2] == ("gtype", "Type")
    assert rows[0][2] == ["Axis"]                      # honest member here
    assert rows[1][:2] == ("how", "Method")
    assert rows[1][2] == ("Through Two Points", "Through Two Planes")
    assert [k for k, _l, _c in rows][2:] == ["p1", "p2", "pa", "pb"]


def test_both_through_words_dispatch_to_their_own_methods(win, qapp,
                                                          monkeypatch):
    """PAGE-CASING TRAP (the reason this door word-matches): in the
    pages' own casing BOTH members begin "Through" - a prefix test
    would send the plane seam into the point builder.  Each page word
    must reach its own kernel seam, and the rung-era voice
    "Intersection of two planes" rides on as the legacy belt."""
    win.new_document()
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "gtype": "Axis", "how": "Through Two Points",
        "p1": "0,0,0", "p2": "0,0,10", "pa": "XY", "pb": "XZ"})
    win.action_work_axis()
    qapp.processEvents()
    assert len(win.doc.axes) == 1 and win.doc.axes[0]["method"] == "two-points"
    z = win.doc.add_plane("XY", 4.0)                   # parallel partner
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "gtype": "Axis", "how": "Through Two Planes",
        "p1": "0,0,0", "p2": "0,0,10", "pa": "XY", "pb": z["name"]})
    win.action_work_axis()
    qapp.processEvents()
    assert len(win.doc.axes) == 2 and win.doc.axes[1]["method"] == "two-planes"
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "how": "Intersection of two planes",                            # belt
        "p1": "0,0,0", "p2": "0,0,10", "pa": "XY", "pb": z["name"]})
    win.action_work_axis()
    qapp.processEvents()
    assert len(win.doc.axes) == 3 and win.doc.axes[2]["method"] == "two-planes"
    assert "refused" not in win.status.currentMessage().lower()


def test_the_axis_door_names_its_refusals():
    mouth = " ".join(_mouth(MainWindow.action_work_axis).split())
    for q in ("The Construction Geometry dialog displays, Type is set "
              "to Axis and Method is set to Through Two Points.",
              "Through Two Planes",
              "Through Cylinder/Cone/Torus", "Through Edge",
              "Perpendicular To Face",
              "Select an Extent Type option to establish the end point",
              "Size the axis to fit the selected geometry.",
              "UNOFFERED"):
        assert q in mouth, q
