"""M201 R22 - the sketch Offset door wears the page's Direction trio.

[SKT-OFFSET, verbatim] "On the Sketch contextual tab, select Modify >
Offset." / "The Offset dialog displays." / "In the dialog, select a
Direction to offset and then specify the distance to offset:" -
"One Side: Offsets on one side of the selected curve." / "Two Sides:
Offsets a unique distance on each side of the selected curve." /
"Symmetric: Offsets symmetrically on both sides of the selected
curve.", each printing its Distance row NESTED (this dialog cannot
hide rows, so the Direction word names which number speaks).

The door was born titled "Offset Entities" - a word the SKT book
NEVER prints (diameter counts ZERO there too; the tool is Offset);
the misnomer is flagged, not cloned, down to the kernel docstring.
Two Sides and Symmetric are honest only on an all-or-nothing kernel:
the pair is COMPUTED before a single line is minted, so a collapsing
inner side refuses the OUTER one too - sequential add_offset calls
would have minted half a direction.  "Match Topology" stays unoffered
(no kernel of ours limits a distance to a parent's topology); the
page's curve/chain picks stay unoffered (closed outlines only); rest
One Side is a STAMP ("default" counts zero on the page) and exactly
what the door has always baked.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                            # noqa

from tracer.core.sketch.constraints import LineDistance, Parallel     # noqa
from tracer.core.sketch.entities import Point                         # noqa
from tracer.core.sketch.model import SketchModel                      # noqa


def _rect(m, w=40.0, h=30.0):
    m.add_rect(Point(0, 0), Point(w, h))


def _areas(m):
    loops, _w = m.to_loops()
    return sorted(round(r["area"], 6) for r in loops)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:                 # CI windows runners: no GL
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _sk(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    _rect(cv.model)
    cv.set_tool("select")
    qapp.processEvents()
    return cv


# ---- the dialog wears the page's rows ----------------------------------------

def test_the_dialog_wears_the_pages_direction_trio(win, qapp, monkeypatch):
    """Title, rows, choices and rests as the page prints them - and
    the born misnomer is GONE from the mouth."""
    from tracer.ui import cmddialog
    cv = _sk(win, qapp)
    seen = []

    def fake(parent, title, fields, *a, **k):
        seen.append((title, fields))
        return None                                    # cancel: nothing
    monkeypatch.setattr(cmddialog, "ask", fake)                        # born
    cv.act_offset()
    title, fields = seen[0]
    assert title == "Offset", title
    assert "Entities" not in title
    by = {f["key"]: f for f in fields}
    assert list(by) == ["dir", "d", "d1", "d2", "j"]
    assert by["dir"]["label"] == "Direction"
    assert list(by["dir"]["choices"]) == ["One Side", "Two Sides",
                                          "Symmetric"]
    assert by["dir"]["default"] == "One Side"          # the STAMP rest
    assert by["d"]["label"] == "Distance"
    assert by["d1"]["label"] == "Distance 1"
    assert by["d2"]["label"] == "Distance 2"
    labs = [f["label"] for f in fields]
    assert not any("Match Topology" in l for l in labs)  # unoffered
    assert len(cv.model.sketch.lines) == 4             # cancel born naught


def test_the_legacy_script_dict_lands_todays_one_side(win, qapp,
                                                      monkeypatch):
    """A remembered dict born before this rung speaks the classic
    pair - the rests answer One Side, the exact era number (R5's
    coin, zero rewrites)."""
    from tracer.ui import cmddialog
    cv = _sk(win, qapp)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"d": 5.0, "j": "mitre"})
    cv.act_offset()
    assert len(cv.model.sketch.lines) == 8
    assert _areas(cv.model) == [1200.0, 2000.0]


# ---- the trio really lands three different answers ---------------------------

def test_symmetric_lands_two_loops_measured():
    m = SketchModel()
    _rect(m)
    made = m.add_offset_sides([5.0, -5.0])
    assert len(made) == 8                              # both sides born
    assert _areas(m) == [600.0, 1200.0, 2000.0]        # 30x20, 40x30, 50x40


def test_two_sides_lands_unique_distances():
    m = SketchModel()
    _rect(m)
    made = m.add_offset_sides([2.0, -4.0])             # Distance 1 / 2
    assert len(made) == 8
    assert _areas(m) == [704.0, 1200.0, 1496.0]        # 32x22, 44x34


def test_both_sides_weld_each_to_its_own_distance():
    """M192's association law rides the pair: eight children, eight
    parallels, each LineDistance minted at its OWN side's number."""
    m = SketchModel()
    _rect(m)
    m.add_offset_sides([5.0, -5.0])
    sk = m.sketch
    par = [c for c in sk.constraints if isinstance(c, Parallel)]
    ld = [c for c in sk.constraints if isinstance(c, LineDistance)]
    assert len(par) == 8 and len(ld) == 8
    assert all(abs(abs(float(c.value)) - 5.0) < 1e-6 for c in ld)


def test_one_undo_lifts_the_whole_pair(win, qapp, monkeypatch):
    """The history belongs to the COMMAND (M192 R5's lesson): one
    undo owes BOTH sides of a Symmetric - no orphan child survives."""
    from tracer.ui import cmddialog
    cv = _sk(win, qapp)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"dir": "Symmetric", "d": 5.0,
                                         "j": "mitre"})
    cv.act_offset()
    assert len(cv.model.sketch.lines) == 12
    assert cv.undo_op()
    assert len(cv.model.sketch.lines) == 4


# ---- the guards, from the outside ---------------------------------------------

def test_a_junk_direction_refuses_before_any_mutation(win, qapp,
                                                      monkeypatch):
    from tracer.ui import cmddialog
    cv = _sk(win, qapp)
    depth = len(cv._hist)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"dir": "Both Sides", "d": 5.0,
                                         "j": "mitre"})
    cv.act_offset()
    assert len(cv.model.sketch.lines) == 4
    assert len(cv._hist) == depth                      # no undo step paid
    assert "the Direction is 'One Side', 'Two Sides' or " \
           "'Symmetric'" in cv._warn_text


def test_two_sides_demands_its_own_positive_numbers(win, qapp,
                                                    monkeypatch):
    from tracer.ui import cmddialog
    cv = _sk(win, qapp)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"dir": "Two Sides", "d": 5.0,
                                         "d1": 0.0, "d2": 4.0,
                                         "j": "mitre"})
    cv.act_offset()
    assert len(cv.model.sketch.lines) == 4
    assert "positive Distance 1 and Distance 2" in cv._warn_text


def test_symmetric_refuses_a_zero_distance(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    cv = _sk(win, qapp)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"dir": "Symmetric", "d": 0.0,
                                         "j": "mitre"})
    cv.act_offset()
    assert len(cv.model.sketch.lines) == 4
    assert "nonzero Distance" in cv._warn_text


# ---- the kernel's all-or-nothing truth -----------------------------------------

def test_the_pair_is_all_or_nothing_on_a_circle():
    """The composition the DOOR could not do honestly: an outer ring
    that would land and an inner that would collapse must NOT leave
    the outer minted.  Sequential calls would have; the pair does
    not - the circle count proves the refusal was total."""
    m = SketchModel()
    c = m.sketch.circle(m.point(0.0, 0.0), 5.0)        # lone circle
    with pytest.raises(ValueError, match="collapses or flips"):
        m.add_offset_sides([2.0, -6.0])
    assert len(m.sketch.circles) == 1                  # NOT two: no half
    assert len(m.sketch.constraints) == 0


def test_a_lone_curve_still_names_its_fate():
    """The page's "sketch curve" and "chain" picks are NOT offered:
    this kernel copies closed outlines - the refusal says so."""
    m = SketchModel()
    a, b = m.point(0.0, 0.0), m.point(10.0, 0.0)
    m.add_line(a, b)
    with pytest.raises(ValueError, match="no closed outline"):
        m.add_offset_sides([3.0])
    assert len(m.sketch.lines) == 1


def test_add_offset_still_rides_the_identical_road():
    """The era mouth delegates: single distance, byte-identical
    answer, including the classic silent zero."""
    m = SketchModel()
    _rect(m)
    assert m.add_offset(0.0) == []
    made = m.add_offset(5.0)
    assert len(made) == 4
    assert _areas(m) == [1200.0, 2000.0]


# ---- the door quotes its law ------------------------------------------------

def test_the_door_quotes_its_law():
    from tracer.ui.sketcheditor import SketchCanvas
    doc = " ".join(SketchCanvas.act_offset.__doc__.split())
    assert "Offsets on one side of the selected curve." in doc
    assert "Offsets a unique distance on each side of the selected " \
           "curve." in doc
    assert "Offsets symmetrically on both sides of the selected " \
           "curve." in doc
    assert "Use Match Topology to limit the offset distance so the " \
           "child offset matches the topology of its parent curve." \
           in doc
    assert "You can only create one selection to offset at a time." \
        in doc
    assert "Offset Entities" in doc                   # flagged, not cloned
    assert "STAMP" in doc                             # One Side's rest
    # and the kernel docstring wears the same honesty
    from tracer.core.sketch.model import SketchModel as SM
    kdoc = " ".join(SM.add_offset.__doc__.split())
    assert "Offset Entities" in kdoc and "never" in kdoc
