"""M201 R24 - the sketch corner menu wears the page's three chamfer doors.

[SKT-ADD-CHAMFERS, verbatim] the page prints THREE tools under
"Modify > Chamfer >": "Equal Distance Chamfer", "Distance And Angle
Chamfer", "Two Distance Chamfer" - and the page prints NO dialog of
its own (values are "specified" at the tool), so the clone wears the
TOOL WORDS at the corner menu and each door asks exactly its page's
numbers: one distance; a distance and an angle; a first and a second
distance. The born single door ("Chamfer corner") was the Equal door
guessing at the whole family; it now wears its own name, and the two
siblings land measured cuts: the driven-equality law ("The second
distance dimension is driven by the first distance dimension... so
that the two distances remain equal.") stays the Equal door's alone -
"Each distance dimension is independent." is the Two Distance kernel,
and the angle door's meaning is OURS, DECLARED (the page never
glosses its angle manipulator - silence names the choice ours, not a
cloned guess): the chamfer line's angle with the first picked leg,
which makes the dialog's 45-degree rest the ISOSCELES truth on a
square corner - byte-identical to the Equal door there.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                                # noqa

from tracer.core.sketch.fillet import (corner_chamfer,                     # noqa
                                       corner_chamfer_angle,
                                       corner_chamfer_sides)
from tracer.core.sketch.model import SketchModel                          # noqa
from tracer.ui import cmddialog                                           # noqa
from tracer.ui.cmddialog import Shell                                     # noqa
from tracer.ui.mainwindow import MainWindow                               # noqa
from tracer.ui.renderer import SceneRenderer                              # noqa
from tracer.ui.sketcheditor import _corner_default                        # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _corner_canvas(win, qapp):
    """A 40 x 20 rect, its corner lines PICKED in order - the menu's
    own hand hands the doors exactly this."""
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    m = cv.model
    lines = m.add_rect(m.point(0, 0), m.point(40, 20))
    cv._sel = [lines[1], lines[2]]
    qapp.processEvents()
    return cv, m, lines


def _area(m):
    loops, _w = m.to_loops()
    return loops[0]["area"]


# ---- the menu wears the trio ----------------------------------------------------

def test_the_corner_menu_wears_the_three_tool_words(win, qapp):
    cv = _corner_canvas(win, qapp)[0]
    texts = [a.text() for a in cv._build_menu().actions()]
    assert "Equal Distance Chamfer…" in texts
    assert "Distance And Angle Chamfer…" in texts
    assert "Two Distance Chamfer…" in texts
    assert "Chamfer corner…" not in texts        # the born guess is gone


# ---- the Equal door: the page's first tool, the classic lever --------------------

def test_the_equal_door_rides_its_lever_titled_by_the_page(win, qapp,
                                                           monkeypatch):
    seen = {}

    def fake(parent, title, label, value, *a, **k):
        seen["title"], seen["label"] = title, label
        return (5.0, True)
    monkeypatch.setattr(Shell, "getDouble", staticmethod(fake))
    cv, m, _L = _corner_canvas(win, qapp)
    cv.act_chamfer()
    assert seen["title"] == "Equal Distance Chamfer", seen
    assert seen["label"] == "Distance (mm):", seen
    assert _area(m) == pytest.approx(787.5)      # the m24b-era number:
    assert cv.undo_op()                          #   equal d=5 on 40x20
    assert _area(m) == pytest.approx(800.0)


# ---- the Distance And Angle door ----------------------------------------------

def test_the_angle_door_asks_its_pages_two_numbers(win, qapp,
                                                   monkeypatch):
    calls = []

    def fake(parent, title, fields, **k):
        calls.append((title, fields))
        return None                              # cancel: nothing born
    monkeypatch.setattr(cmddialog, "ask", fake)
    cv, m, L = _corner_canvas(win, qapp)
    cv.act_chamfer_dist_angle()
    title, fields = calls[0]
    assert title == "Distance And Angle Chamfer", title
    by = {f["key"]: f for f in fields}
    assert list(by) == ["d", "ang"]
    assert by["d"]["label"] == "Distance (mm)"
    assert by["ang"]["label"] == "Angle (degrees)"
    # degrees wear DEGREES (m201 R7's law, re-earned: the R24 film's
    # first take caught an Angle row printing "45.00 mm" - a double
    # field without a suffix rides cmddialog's default " mm", so BOTH
    # suffixes are now spoken EXPLICITLY at the door):
    assert by["ang"].get("suffix") == "°", by["ang"]
    assert by["d"].get("suffix") == " mm", by["d"]
    # the LAW-58 preview law IS the page's: "The initial chamfer
    # preview displays a distance value that is proportional to the
    # smaller of the selected objects."  The 45.0 rest is a STAMP.
    assert by["d"]["default"] == pytest.approx(_corner_default(20.0))
    assert by["ang"]["default"] == 45.0
    assert len(m.sketch.lines) == 4


def test_the_angle_door_lands_the_measured_cut(win, qapp, monkeypatch):
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"d": 5.0, "ang": 60.0})
    cv, m, _L = _corner_canvas(win, qapp)
    cv.act_chamfer_dist_angle()
    # right corner (theta=90), phi=60: d2 = 5*sin60/sin150 = 8.660254
    assert len(m.sketch.lines) == 5
    assert _area(m) == pytest.approx(800.0 - 5 * 8.660254038 / 2, abs=1e-5)
    assert cv.undo_op()
    assert len(m.sketch.lines) == 4


def test_the_angle_that_runs_parallel_refuses_uncharged(win, qapp,
                                                        monkeypatch):
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"d": 5.0, "ang": 90.0})
    cv, m, _L = _corner_canvas(win, qapp)
    depth = len(cv._hist)
    cv.act_chamfer_dist_angle()
    assert len(m.sketch.lines) == 4
    assert len(cv._hist) == depth, "a refused angle paid an undo step"
    assert "parallel to a leg" in cv._warn_text, cv._warn_text


# ---- the Two Distance door ------------------------------------------------------

def test_the_two_distance_door_lands_the_independent_pair(win, qapp,
                                                          monkeypatch):
    calls = []

    def fake(parent, title, fields, **k):
        calls.append(fields)
        return {"d1": 3.0, "d2": 6.0}
    monkeypatch.setattr(cmddialog, "ask", fake)
    cv, m, L = _corner_canvas(win, qapp)
    l1, l2 = L[1], L[2]
    P = next(p for p in (l1.a, l1.b) if p in (l2.a, l2.b))
    corner = (P.x, P.y)                          # the ORIGINAL seat
    cv.act_chamfer_two()
    by = {f["key"]: f for f in calls[0]}         # both numbers wear
    assert by["d1"].get("suffix") == " mm"       #  millimeters, as
    assert by["d2"].get("suffix") == " mm"       #  their labels say
    assert len(m.sketch.lines) == 5
    assert _area(m) == pytest.approx(791.0)      # 800 - 3*6/2
    # leg naming, declared law: Distance 1 rides the FIRST picked
    # line (its shared point slid 3), Distance 2 the second (its new
    # endpoint sits 6 out):
    assert math.dist((P.x, P.y), corner) == pytest.approx(3.0)
    Q = next(p for p in (l2.a, l2.b) if p is not P)
    assert math.dist((Q.x, Q.y), corner) == pytest.approx(6.0)
    assert cv.undo_op()
    assert len(m.sketch.lines) == 4


def test_two_distance_negative_refuses_before_mutation(win, qapp,
                                                       monkeypatch):
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"d1": -2.0, "d2": 3.0})
    cv, m, _L = _corner_canvas(win, qapp)
    depth = len(cv._hist)
    cv.act_chamfer_two()
    assert len(m.sketch.lines) == 4
    assert len(cv._hist) == depth
    assert "must be positive" in cv._warn_text, cv._warn_text


# ---- the kernel laws, measured straight ------------------------------------------

def test_the_kernel_doors_agree_on_the_isosceles_truth():
    """The angle dialog's 45 rest on a SQUARE corner must BE the
    Equal door - the stamp is honest because it lands what the first
    door has always baked."""
    m1 = SketchModel()
    a1 = m1.add_rect(m1.point(0, 0), m1.point(40, 20))
    corner_chamfer(m1, a1[1], a1[2], 5.0)
    m2 = SketchModel()
    a2 = m2.add_rect(m2.point(0, 0), m2.point(40, 20))
    corner_chamfer_angle(m2, a2[1], a2[2], 5.0, 45.0)
    assert _area(m1) == pytest.approx(_area(m2))
    # and Equal delegates to the sides mouth with ONE truth:
    m3 = SketchModel()
    a3 = m3.add_rect(m3.point(0, 0), m3.point(40, 20))
    corner_chamfer_sides(m3, a3[1], a3[2], 5.0, 5.0)
    assert _area(m3) == pytest.approx(_area(m1))


# ---- the doors and kernels quote their pages --------------------------------------

def test_the_doors_and_kernels_quote_their_page():
    from tracer.ui.sketcheditor import SketchCanvas
    from tracer.core.sketch import fillet
    eq = " ".join(SketchCanvas.act_chamfer.__doc__.split())
    da = " ".join(SketchCanvas.act_chamfer_dist_angle.__doc__.split())
    td = " ".join(SketchCanvas.act_chamfer_two.__doc__.split())
    assert "Modify > Chamfer > Equal Distance Chamfer" in eq
    assert "Modify > Chamfer > Distance And Angle Chamfer" in da
    assert "Modify > Chamfer > Two Distance Chamfer" in td
    assert "so that the two distances remain equal." in eq
    assert "proportional to the smaller of the selected objects." in eq
    assert "Each distance dimension is independent." in td
    assert "never glosses" in da                # the declared angle
    k1 = " ".join(fillet.corner_chamfer.__doc__.split())
    k2 = " ".join(fillet.corner_chamfer_sides.__doc__.split())
    assert "driven by the first distance dimension" in k1
    assert "The first distance value you specify applies to both sides" \
        in k2
    assert "Two Distance" in k1                # the ONE truth, named
