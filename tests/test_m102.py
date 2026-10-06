"""M102 — section views: cut the model, hatch the wound.

A drawing that can only show the outside is a box of secrets. Fusion
puts section lines across views and opens the body up; Tracer now
does the same on the sheet: a section is a stored cut (axis +
position) that removes the material between the viewer and the plane
— the surviving half is a LIVE view like every other (its chains
re-derive on repaint, its bubbles measure the model, M96 drags and
M100 scales apply), and the cut face itself gets the draughtsman's
universal mark: 45° hatching, in the PNG by Qt's diagonal brush and
in the DXF as clipped line geometry.

Naming follows the standard: the first cut is A-A, next B-B.
Which half survives is decided by the viewer: a Y-cut on a front
view removes the near (y < at) material and looks at the back
half's cut face; an X-cut reads in the right view; a Z-cut opens a
plan from above. (M84's Section analysis already clips the DISPLAY;
this is the stored, draughted one — it lives on the sheet, exports
with it and undoes with it.)

Honest scope: sections live on the sheet (not the viewport), one
letter per sheet index, and the hatching is decorative draughting
(45°, fixed spacing) — no material symbols, no offset/aligned
sections, no rotated cutting-plane arrows.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                   # noqa: E402

from tracer.core import drawing                              # noqa: E402
from tracer.core.document import (Document,                  # noqa: E402
                                  PrimitiveFeature)


def _plate():
    box = PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 40.0, "dy": 20.0, "dz": 10.0})
    cyl = PrimitiveFeature(name="c", kind="cylinder",
                           dims={"radius": 4.0, "height": 10.0},
                           placement=(20.0, 10.0, 0.0))
    return box.build().subtract(cyl.build())


# ---------------------------------------------------------------- core

def test_section_keeps_the_far_half_and_reads_in_the_right_view():
    s = _plate()
    sec = drawing.section(s, axis="Y", at=10.0)
    assert sec["view"] == "front"
    assert sec["half"].volume == pytest.approx(s.volume / 2, rel=1e-3)
    lo, hi = sec["half"].bounding_box
    assert lo[1] == pytest.approx(10.0, abs=1e-4)     # y >= at survives


def _area(L):
    P = np.asarray(L, float)
    x, y = P[:, 0], P[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def test_cut_loops_lie_flat_in_the_view_basis():
    sec = drawing.section(_plate(), axis="Y", at=10.0)
    # the cut rides through the bore axis: the slot splits the face
    # into two legs, each 16 wide x 10 tall
    assert len(sec["cut"]) == 2
    assert all(_area(L) == pytest.approx(160.0, rel=0.05)
               for L in sec["cut"])


def test_z_and_x_sections_read_top_and_right():
    s = _plate()
    assert drawing.section(s, axis="Z", at=5.0)["view"] == "top"
    assert drawing.section(s, axis="X", at=20.0)["view"] == "right"


def test_hatch_lines_fill_and_never_escape():
    from shapely.geometry import Point, Polygon
    loop = [(0.0, 0.0), (40.0, 0.0), (40.0, 10.0), (0.0, 10.0)]
    lines = drawing.hatch_lines(loop, spacing=2.0)
    assert len(lines) >= 15
    P = Polygon(loop)
    for a, b in lines:
        for p in (a, b):
            q = Point(p[0], p[1])
            assert P.buffer(1e-6).contains(q) or \
                P.exterior.distance(q) < 1e-6
    # the SAME loop shoved to a real sheet position must hatch the
    # same (the family x-y=c spans the bounds, not the width — a
    # c-range built for miny=0 silently hatched nothing on the sheet)
    off = [(x + 190.0, y + 143.5) for x, y in loop]
    assert len(drawing.hatch_lines(off, spacing=2.0)) == len(lines)


def test_hatch_region_leaves_the_air_unmarked():
    # a cut face with a void inside (Z-cut through a pocket): the hole
    # ring is AIR — hatching it would be a drafting lie
    from shapely.geometry import Point, Polygon
    outer = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]
    pocket = [(10.0, 6.0), (30.0, 6.0), (30.0, 14.0), (10.0, 14.0)]
    lines = drawing.hatch_region([outer, pocket], spacing=2.0)
    assert lines
    air = Polygon(pocket).buffer(-1e-9)
    for a, b in lines:
        for p in (a, b):
            assert not air.contains(Point(p[0], p[1]))
    # and the material really did get inked (not an empty answer)
    assert len(lines) >= 20


# ------------------------------------------------------------------ UI

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        from tracer.ui.renderer import SceneRenderer
        from tracer.ui.mainwindow import MainWindow
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
        w._discard_guard = lambda: True
        w.close()
        r.ctx.release()
    except Exception:
        raise


def _bore_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Plate", kind="box",
        dims={"dx": 40.0, "dy": 20.0, "dz": 10.0}))
    win.doc.features.append(PrimitiveFeature(
        name="Bore", kind="cylinder",
        dims={"radius": 4.0, "height": 10.0},
        placement=(20.0, 10.0, 0.0), op="subtract"))
    win.recompute()
    win.action_new_drawing()
    qapp.processEvents()
    return win.drawing


def _ask(action="New section", axis="Y (front cut)", at=5.0):
    return lambda *a, **k: {"action": action, "axis": axis, "at": at}


def test_section_verb_adds_a_live_view(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    cv = _bore_sheet(win, qapp)
    monkeypatch.setattr(cmddialog, "ask", _ask(at=5.0))
    win.action_section_view()
    qapp.processEvents()
    g = cv.sheet()
    assert g["sections"][0]["name"] == "A-A"
    assert g["sections"][0]["axis"] == "Y"
    assert "A-A" in cv.views()                 # the sheet gained a view
    p = cv.placed()["A-A"]
    # front half removed: what projects is y >= 5, half the depth
    span = p["max"][0] - p["min"][0]
    assert span == pytest.approx(40.0 * p["sc"], rel=1e-3)


def test_two_sections_letters_then_unlettered(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    cv = _bore_sheet(win, qapp)
    monkeypatch.setattr(cmddialog, "ask", _ask(at=5.0))
    win.action_section_view()
    monkeypatch.setattr(cmddialog, "ask", _ask(axis="Z (horizontal cut)",
                                               at=5.0))
    win.action_section_view()
    qapp.processEvents()
    assert [s["name"] for s in cv.sheet()["sections"]] == ["A-A", "B-B"]
    monkeypatch.setattr(cmddialog, "ask", _ask(action="Remove last section"))
    win.action_section_view()
    qapp.processEvents()
    assert [s["name"] for s in cv.sheet()["sections"]] == ["A-A"]
    assert "B-B" not in cv.views()


def test_sections_re_derive_live_and_travel_with_moves(win, qapp,
                                                       monkeypatch):
    from tracer.ui import cmddialog
    cv = _bore_sheet(win, qapp)
    cv.resize(800, 600)
    qapp.processEvents()
    monkeypatch.setattr(cmddialog, "ask", _ask(at=5.0))
    win.action_section_view()
    qapp.processEvents()
    before = cv.cuts_page()["A-A"][0]           # outer cut ring, page mm
    # stretch the plate 40 -> 60 wide: the wound opens wider, live
    win.doc.features[0].dims["dx"] = 60.0
    win.recompute()
    qapp.processEvents()
    after = cv.cuts_page()["A-A"][0]
    w_b = max(p[0] for p in before) - min(p[0] for p in before)
    w_a = max(p[0] for p in after) - min(p[0] for p in after)
    assert w_a > w_b + 1.0
    # and a stored M96 move carries the whole section aside
    cv.sheet().setdefault("move", {})["A-A"] = [12.0, 0.0]
    moved = cv.cuts_page()["A-A"][0]
    assert (max(p[0] for p in moved) - max(p[0] for p in after)) \
        == pytest.approx(12.0, abs=0.01)


def test_bubbles_measure_a_section_like_any_view(win, qapp,
                                                 monkeypatch):
    from tracer.ui import cmddialog
    cv = _bore_sheet(win, qapp)
    monkeypatch.setattr(cmddialog, "ask", _ask(at=5.0))
    win.action_section_view()
    qapp.processEvents()
    # cut the bore away and the half-section's widest run is the plate
    win._add_dim("A-A", (0.0, 0.0), (40.0, 0.0), {})
    qapp.processEvents()
    d = cv.sheet()["dims"][-1]
    assert d["text"] == "40.00"                 # measured in MODEL mm
    win.doc.features[0].dims["dx"] = 50.0
    win.recompute()
    cv.resolve_dims()
    assert cv.sheet()["dims"][-1]["text"] == "50.00"


def test_sections_round_trip_through_the_file(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    cv = _bore_sheet(win, qapp)
    monkeypatch.setattr(cmddialog, "ask", _ask(at=5.0))
    win.action_section_view()
    qapp.processEvents()
    back = Document.from_dict(win.doc.to_dict())
    assert back.drawings[-1]["sections"] == cv.sheet()["sections"]
    win.undo()                                  # un-make the section
    qapp.processEvents()
    assert not cv.sheet().get("sections")
    assert "A-A" not in cv.views()


def test_dxf_export_carries_sections_and_their_hatching(win, qapp,
                                                        monkeypatch,
                                                        tmp_path):
    from tracer.ui import cmddialog
    cv = _bore_sheet(win, qapp)
    plain = cv.layout()
    n_vis = sum(len(cs) for cs in plain.values())
    monkeypatch.setattr(cmddialog, "ask", _ask(at=5.0))
    win.action_section_view()
    qapp.processEvents()
    out = str(tmp_path / "sec.dxf")
    win.export_drawing(out)
    from tracer.core import import2d
    ops = [o for o in import2d.read(out) if o[0] in ("poly", "line")]
    # section view chains + hidden + its cut boundary AND hatch lines
    assert len(ops) >= n_vis + 20
    pts = [p for o in ops for p in (o[1:] if o[0] == "line" else o[1])]
    assert len(pts) > 200                        # the hatching is real
