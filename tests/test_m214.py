"""M201 R26 - the pattern/mirror doors open with the pages' first rows.

[SLD-REF-PATTERN, verbatim] "Object Type: Select the type of object to
pattern." + "Objects: Select objects to pattern." - the shared pattern
reference's OPENING PAIR, now worn by all three pattern mouths
(circular, rectangular, path).  Of the page's five members this
kernel bakes exactly ONE - "Features: Duplicates features in the
timeline and distributes them according to the pattern settings." -
so the row carries that member alone; Faces/Bodies/Components/
Construction Geometry stay UNOFFERED.
[SLD-REF-MIRROR-DIALOG, verbatim] "Object Type: Select the object
type you want to mirror." (member "Features: Mirrors timeline
features across a plane.") + "Objects: Select objects to mirror." +
"Mirror Plane: Select a plane or planar face to mirror objects
across." - page CASING worn, at both mirror mouths.  DEFECT H16
(Operation gated "If Object Type is set to Bodies" on the task,
"(Parametric Modeling mode only)" on the reference) is flagged at the
door, never cloned.  Tolerance (Surfaces only) and Compute Option
(Features type only) UNOFFERED.
[R15 adjudication KEPT] "Occurrences" stays the stamped house word
(page row "Quantity") - the m203 gate owns that declaration; the
Geometric door stays declared house-wholesale (no page owns it).
The file law again: new ROWS, never new RECORDS - the otype row rides
unasked-by-legacy answers, and every born key keeps its slot.
"""
import inspect
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                          # noqa: E402

from tracer.ui import cmddialog, cmdpanel                           # noqa: E402
from tracer.core.document import CircularPatternFeature             # noqa: E402
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


def _plate_hole(win):
    win.new_document()
    win.doc.add_plate("plate", 60, 10, 2)
    win.doc.add_cylinder("h", 1.5, 10, center=(30, 5), z=-4,
                         op="subtract")
    win.recompute()


def _capture(win, monkeypatch):
    """Replace ask; capture every (title, rows, fields), REJECT all."""
    calls = []
    monkeypatch.setattr(cmddialog, "ask",
                        lambda p, t, fl, **k: (calls.append(
                            (t, [(f["key"], f["label"]) for f in fl],
                             [dict(f) for f in fl])), None)[1])
    return calls


def _rows(fields):
    return [(f["key"], f["label"]) for f in fields]


def _choices(fields, key):
    return [f.get("choices") for f in fields if f["key"] == key][0]


# ---- the dialog doors ---------------------------------------------------------

def test_the_circular_door_opens_with_the_pages_pair(win, monkeypatch):
    calls = _capture(win, monkeypatch)
    _plate_hole(win)
    win.action_circular_pattern()
    (title, rows, _fl), = calls
    assert title == "Circular Pattern"
    assert rows[:2] == [("otype", "Object Type"), ("src", "Objects")]
    assert _choices(calls[0][2], "otype") == ["Features"]
    assert not any(lbl == "Feature to pattern" for _k, lbl in rows)


def test_the_rectangular_door_opens_with_the_pages_pair(win, monkeypatch):
    calls = _capture(win, monkeypatch)
    _plate_hole(win)
    win.action_linear_pattern()
    title, rows, _fl = calls[0]
    assert title == "Rectangular Pattern"
    assert rows[:2] == [("otype", "Object Type"), ("src", "Objects")]
    assert _choices(calls[0][2], "otype") == ["Features"]
    # the born rows stand behind the pair, keys byte-true:
    assert [k for k, _l in rows][2:] == ["dx", "dy", "dz", "count",
                                         "dist", "dir", "count2",
                                         "dx2", "dy2", "dz2",
                                         "dist2", "dir2"]


def test_the_path_door_opens_with_the_pages_pair(win, qapp, monkeypatch):
    from test_m200 import _walk_sketch_m200
    calls = _capture(win, monkeypatch)
    _walk_sketch_m200(win, qapp, ((10, 10), (30, 10), (50, 10)))
    win.action_path_pattern()
    qapp.processEvents()
    title, rows, _fl = calls[0]
    assert title == "Pattern on Path"
    assert rows[:2] == [("otype", "Object Type"), ("src", "Objects")]
    assert _choices(calls[0][2], "otype") == ["Features"]


# ---- the live-panel door ------------------------------------------------------

def test_the_mirror_panel_opens_with_the_pages_trio(win, monkeypatch):
    seen = {}

    def fake(parent, command_id, title, fields, **kw):
        seen["title"] = title
        seen["rows"] = [(f["key"], f["label"]) for f in fields]
        seen["choices"] = {f["key"]: f.get("choices") for f in fields}
    monkeypatch.setattr(cmdpanel, "run", fake)
    _plate_hole(win)
    win.action_mirror()
    assert seen["title"] == "Mirror"
    assert seen["rows"][:3] == [("otype", "Object Type"),
                                ("src", "Objects"),
                                ("plane", "Mirror Plane")]
    assert seen["choices"]["otype"] == ["Features"]
    assert seen["choices"]["op"] == ["Join", "New Body"]   # born pair


def test_the_fallback_mirror_mouth_wears_page_casing():
    """The browser-menu mirror asks only plane + offset when nothing
    was pre-known - even that second mouth wears the page's
    "Mirror Plane" casing now (one word, one voice)."""
    src = inspect.getsource(MainWindow._mirror_feature)
    assert 'label="Mirror Plane"' in src
    assert 'label="Mirror plane"' not in src


# ---- the settled naming stays settled ------------------------------------------

def test_the_geometric_door_stays_house_wholesale(win, monkeypatch):
    """R15 declared the ENTIRE Geometric door ours (no reference page
    prints its rows); R26's page-pair does NOT invade it - a house
    door keeps its house word."""
    calls = _capture(win, monkeypatch)
    _plate_hole(win)
    win.action_geometric_pattern()
    _title, rows, _fl = calls[0]
    assert rows[0] == ("src", "Feature to pattern")
    assert not any(k == "otype" for k, _l in rows)


# ---- the record law: new rows, never new records --------------------------------

def test_legacy_answers_still_drive_the_circular_door(win, qapp,
                                                      monkeypatch):
    """A reply dict shaped like EVERY born answer (no otype key - the
    row is decoration the door never reads) must still bake exactly
    what it baked before: the page word rides the UI, the file keeps
    its slots."""
    _plate_hole(win)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "src": "h", "axis": "+Z (through center)", "cx": 0.0, "cy": 0.0,
        "dist": "Partial", "ang": 120.0, "count": 3})
    n0 = len(win.doc.features)
    win.action_circular_pattern()
    qapp.processEvents()
    f = win.doc.features[-1]
    assert isinstance(f, CircularPatternFeature)
    assert len(win.doc.features) == n0 + 1
    assert "otype" not in f.__dict__            # no record pollution


# ---- the doors cite their pages --------------------------------------------------

def _mouth(fn):
    src = inspect.getsource(fn)
    return " ".join(line.split("#", 1)[1] if line.lstrip().startswith("#")
                    else line for line in src.splitlines())


@pytest.mark.parametrize("fn, quotes", [
    (MainWindow.action_circular_pattern,
     ("Object Type: Select the type of object to pattern.",
      "Objects: Select objects to pattern.",
      "Features: Duplicates features in the timeline and distributes "
      "them according to the pattern settings.")),
    (MainWindow.action_linear_pattern,
     ("Object Type: Select the type of object to pattern.",
      "Objects: Select objects to pattern.")),
    (MainWindow.action_mirror,
     ("Object Type: Select the object type you want to mirror.",
      "Objects: Select objects to mirror.",
      "Mirror Plane: Select a plane or planar face to mirror objects "
      "across.",
      "Mirrors timeline features across a plane.",
      "H16", "Tolerance (Surfaces only)", "Compute Option (Features "
      "type only)")),
])
def test_the_doors_quote_their_pages(qapp, fn, quotes):
    mouth = " ".join(_mouth(fn).split())
    for q in quotes:
        assert q in mouth, (fn.__name__, q)


def test_the_path_door_comment_cites_the_shared_page():
    mouth = " ".join(_mouth(MainWindow.action_path_pattern).split())
    assert "Object Type: Select the type of object to pattern." in mouth
    assert "Objects: Select objects to pattern." in mouth
