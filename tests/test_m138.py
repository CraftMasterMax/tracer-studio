"""M138 — section views on paper, rung three: the JOGGED line.

The wave-12 probe's decisive finding, LIVE-VERIFIED on this stack
before a line of the milestone shipped: for the jogged family the
standards actually admit — straight legs that turn SQUARE, which
every drafting product enforces by construction — the unfolding
rotation the "drawn as if the offsets were in one plane" law
suggests is the IDENTITY. Every cut plane stands perpendicular to
the parent, so an orthographic child along the shared eye flattens
the steps for free: cut each leg's OWN plane inside its lateral
slab (the slabs are disjoint — the law rejects doubling back),
union the kept halves into one solid and concatenate the caps, and
the whole existing pipeline — HLR, hidden ink, place, hatch, DXF,
PNG, undo — reads a jog exactly like a straight cut. The hinge
rotation is real machinery, but it belongs to the angular/aligned
rung this file defers (and whose open-source oracle stitches by
approximation). The tool grows one honest key: Alt sets a corner,
double-click finishes; two plain clicks still finish a straight
section exactly as rung one shipped, entry byte for byte. And the
4-cap jog flushed a latent M117 bug: section_properties' centroid
broadcast only survived one loop (it silently mixed weights at two
and crashed at four) — the fix ships with a golden here.
"""
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from tracer.core import drawing as dr
from tracer.core.document import Document, HoleFeature, PrimitiveFeature
from tracer.core.measure import section_properties


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def offset_bores():
    doc = Document()
    doc.add(PrimitiveFeature(name="plate", kind="box",
                             dims={"dx": 40, "dy": 30, "dz": 6}))
    doc.add(HoleFeature(name="boreA", op="subtract", center=(10, 15, 6),
                        normal=(0, 0, -1), radius=4.0, depth=6,
                        cut_length=6, through=True))
    doc.add(HoleFeature(name="boreB", op="subtract", center=(30, 25, 6),
                        normal=(0, 0, -1), radius=4.0, depth=6,
                        cut_length=6, through=True))
    return doc


def area(L):
    P = np.asarray(L, float)
    x, y = P[:, 0], P[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1))
                     - np.dot(y, np.roll(x, -1)))) / 2.0


# ---- the jog law ------------------------------------------------------------

def test_the_z_jog_stands_one_child_stepped_across_two_planes():
    doc = offset_bores()
    segs, basis = dr.plane_from_polyline(
        "top", [(0, 15), (20, 15), (20, 25), (40, 25)])
    assert len(segs) == 2                        # two cut-runs
    assert segs[0]["lo"] is None and segs[0]["hi"] == pytest.approx(20)
    assert segs[1]["lo"] == pytest.approx(20) and segs[1]["hi"] is None
    assert np.allclose(segs[0]["o"], (0, 15, 0))
    assert np.allclose(basis[0], (0, -1, 0))     # eye: 90 CW of leg 1
    res = dr.section_jogged(doc.result, segs, basis)
    assert res["half"].to_trimesh().is_watertight
    assert res["half"].volume == pytest.approx(4498.4, abs=0.5)
    assert len(res["cut"]) == 4                  # two wounds per step
    assert [round(area(L)) for L in res["cut"]] == [36, 36, 36, 36]
    xs = [(min(p[0] for p in L), max(p[0] for p in L))
          for L in res["cut"]]
    assert any(abs(hi - 20) < 1e-3 for _, hi in xs)   # caps ABUT at
    assert any(abs(lo - 20) < 1e-3 for lo, _ in xs)   # the hinge line
    P = np.vstack([np.asarray(c, float) for c in
                   dr.project_view(res["half"], view=res["view"])])
    assert P[:, 0].min() == pytest.approx(0, abs=1e-6)   # ONE child,
    assert P[:, 0].max() == pytest.approx(40, abs=1e-6)  # full span


def test_the_jog_law_refuses_the_illegal_lines():
    with pytest.raises(ValueError):              # a bend that is not
        dr.plane_from_polyline(                  # square is the
            "top",                               # angular rung,
            [(0, 15), (20, 15), (25, 25), (45, 25)])       # not v1
    with pytest.raises(ValueError):              # doubling back
        dr.plane_from_polyline(                  # overlaps lateral
            "top",                               # ownership: the
            [(0, 15), (30, 15), (30, 25), (10, 25)])       # union
    with pytest.raises(ValueError):              # a polyline that
        dr.plane_from_polyline("top",            # ends mid-jog: no
                               [(0, 15), (20, 15), (30, 15),
                                (30, 25)])                   # cut there
    with pytest.raises(ValueError):              # iso parents stay
        dr.plane_from_polyline("iso", [(0, 0), (10, 0), (10, 5)])


def test_depth_modes_ride_every_leg():
    doc = offset_bores()
    segs, basis = dr.plane_from_polyline(
        "top", [(0, 15), (20, 15), (20, 25), (40, 25)])
    slab = dr.section_jogged(doc.result, segs, basis, mode="distance",
                             dist=4.0)
    # every leg keeps its OWN 4 mm slab: two 20x4x6 strips minus the
    # half-bore each leg's plane swallows (pi*4^2*6/2 each):
    assert slab["half"].volume == pytest.approx(  # 2*(480 - 150.80)
        658.4, abs=1.0)
    sl = dr.section_jogged(doc.result, segs, basis, mode="slice")
    assert sl["half"] is None and len(sl["cut"]) == 4


def test_two_points_are_the_straight_law_exactly():
    doc = offset_bores()
    s2, b2 = dr.plane_from_polyline("top", [(5, 15), (35, 15)])
    o, n, X = dr.plane_from_line("top", (5, 15), (35, 15))
    assert len(s2) == 1 and s2[0]["lo"] is None and s2[0]["hi"] is None
    assert np.allclose(s2[0]["o"], o)
    assert np.allclose(b2[0], n) and np.allclose(b2[1], X)
    res = dr.section_jogged(doc.result, s2, b2)
    plain = dr.section_on(doc.result, o, n, right=X)
    assert res["half"].volume == pytest.approx(plain["half"].volume)


def test_jogged_cuts_cache_by_their_geometry():
    doc = offset_bores()
    sg = dr.plane_from_polyline(
        "top", [(0, 15), (20, 15), (20, 25), (40, 25)])
    a = dr.section_jogged(doc.result, *sg)
    b = dr.section_jogged(doc.result, *sg)
    c = dr.section_jogged(doc.result, *dr.plane_from_polyline(
        "top", [(0, 15), (19, 15), (19, 25), (39, 25)]))   # hinge 19
    assert a is b and a is not c


def test_the_multi_loop_centroid_is_weighted_rowwise():
    # the M117 broadcast bug a 4-cap jog flushed: a hole at +3 must
    # pull the centroid NEGATIVE, weighted per loop not per column.
    outer = [(-5, -5), (5, -5), (5, 5), (-5, 5)]
    hole = [(2, 2), (4, 2), (4, 4), (2, 4)]
    sp = section_properties([outer, hole])
    assert sp["area_mm2"] == pytest.approx(96.0)
    assert sp["holes"] == 1
    assert sp["centroid"][0] == pytest.approx(-12 / 96, abs=1e-9)
    assert sp["centroid"][1] == pytest.approx(-12 / 96, abs=1e-9)


# ---- the tool and the sheet -------------------------------------------------

@pytest.fixture
def win(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1200, 800)
    w.show()
    qapp.processEvents()
    w.new_document()
    d = w.doc
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    d.add(HoleFeature(name="boreA", op="subtract", center=(10, 15, 6),
                      normal=(0, 0, -1), radius=4.0, depth=6,
                      cut_length=6, through=True))
    d.add(HoleFeature(name="boreB", op="subtract", center=(30, 25, 6),
                      normal=(0, 0, -1), radius=4.0, depth=6,
                      cut_length=6, through=True))
    w.recompute()
    w.action_new_drawing()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w._discard_guard = lambda: True
    w.close()
    r.close()


def _ev(canvas, page_pt, kind, modifiers=Qt.KeyboardModifier.NoModifier):
    wp = canvas.s2p(*page_pt)
    ev = QMouseEvent(kind, QPointF(wp), QPointF(wp), QPointF(wp),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     modifiers)
    if kind == QEvent.Type.MouseButtonDblClick:
        canvas.mouseDoubleClickEvent(ev)
    else:
        canvas.mousePressEvent(ev)


def _frac(canvas, view, *ts):
    fr = canvas.placed()[view]
    lo = np.asarray(fr["min"], float) + np.asarray(fr["off"], float)
    hi = np.asarray(fr["max"], float) + np.asarray(fr["off"], float)
    return [tuple(float(v) for v in lo + (hi - lo) * np.array(t))
            for t in ts]


def test_alt_corner_and_double_click_stand_a_jog(win, qapp):
    cv = win.drawing
    fired = []
    cv.section_added.connect(lambda e: fired.append(e))
    a, b, c, d = _frac(cv, "top", (0.1, 0.3), (0.5, 0.3), (0.5, 0.7),
                       (0.9, 0.7))
    win._sec_btn.click()
    _ev(cv, a, QEvent.Type.MouseButtonPress)
    _ev(cv, b, QEvent.Type.MouseButtonPress, Qt.AltModifier)
    assert len(cv._sec_pts) == 2 and fired == []     # corner: armed
    _ev(cv, c, QEvent.Type.MouseButtonPress)         # plain leg 3:
    assert len(cv._sec_pts) == 3                     # still armed
    _ev(cv, d, QEvent.Type.MouseButtonPress)         # plain leg 4
    assert len(cv._sec_pts) == 4                     # (the dbl-click
    _ev(cv, d, QEvent.Type.MouseButtonDblClick)      #  press was
    assert len(fired) == 1                           #  the short)
    e = fired[0]
    assert e["parent"] == "top" and len(e["pts"]) == 4
    secs = cv.sheet()["sections"]
    assert secs[0]["name"] == "A-A" and "pts" in secs[0]
    qapp.processEvents()
    assert "A-A" in cv.placed()                      # child stands


def test_two_plain_clicks_still_finish_a_straight_section(win, qapp):
    cv = win.drawing
    fired = []
    cv.section_added.connect(lambda e: fired.append(e))
    a, b = _frac(cv, "top", (0.2, 0.4), (0.8, 0.4))
    win._sec_btn.click()
    _ev(cv, a, QEvent.Type.MouseButtonPress)
    _ev(cv, b, QEvent.Type.MouseButtonPress)         # rung one law:
    assert len(fired) == 1                           # click 2 ends it
    assert "pts" not in fired[0]                     # entry byte for
    assert not cv._sec_pts                           #  byte unchanged


def test_a_bent_leg_is_refused_at_the_click(win, qapp):
    cv = win.drawing
    notes = []
    cv.tool_note.connect(notes.append)
    a, b = _frac(cv, "top", (0.2, 0.3), (0.5, 0.6))  # 45 deg leg
    win._sec_btn.click()
    _ev(cv, a, QEvent.Type.MouseButtonPress)
    _ev(cv, b, QEvent.Type.MouseButtonPress, Qt.AltModifier)
    assert len(cv._sec_pts) == 2
    _ev(cv, b, QEvent.Type.MouseButtonPress, Qt.AltModifier)  # too
    assert len(cv._sec_pts) == 2                     # short: refused
    c = _frac(cv, "top", (0.8, 0.62))[0]             # near-diagonal
    _ev(cv, c, QEvent.Type.MouseButtonPress, Qt.AltModifier)
    assert any("SQUARE" in t for t in notes)         # diagonal: also
    assert len(cv._sec_pts) == 2                     # refused at click


def test_the_jogged_child_hatches_paints_saves_and_exports(win,
                                                           qapp,
                                                           tmp_path):
    cv = win.drawing
    win._on_section_line({"parent": "top",
                          "pts": [(2, 15), (20, 15), (20, 25),
                                  (38, 25)],
                          "p0": (2, 15), "p1": (38, 25),
                          "flip": False})
    qapp.processEvents()
    assert len(cv.cuts_page()["A-A"]) == 4
    cv.resize(900, 620)
    assert not cv.grab().isNull()                    # stepped ink,
    blob = win.doc.to_dict()                         # caps, file and
    s = blob["drawings"][-1]["sections"][0]          # DXF all read
    want = [(2, 15), (20, 15), (20, 25), (38, 25)]   # the jog points
    assert [tuple(map(float, p)) for p in s["pts"]] == [           # survive
        tuple(map(float, w)) for w in want]          # the file shape
    from tracer.core.document import Document as D
    rt = D.from_dict(blob).drawings[-1]["sections"][0]["pts"][2]
    assert tuple(map(float, rt)) == (20.0, 25.0)
    out = str(tmp_path / "jog.dxf")
    win.export_drawing(out)
    from tracer.core import import2d
    ops = [o for o in import2d.read(out) if o[0] in ("poly", "line")]
    assert len(ops) > 20                             # geometry lives


def test_the_props_dialog_speaks_to_a_jogged_child(win, qapp,
                                                   monkeypatch):
    from tracer.ui import cmddialog
    cv = win.drawing
    win._on_section_line({"parent": "top",
                          "pts": [(2, 15), (20, 15), (20, 25),
                                  (38, 25)],
                          "p0": (2, 15), "p1": (38, 25)})
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda *a, **k: {"mode": "Slice (the cut face alone)",
                         "dist": 10.0, "flip": True,
                         "hidden": False, "scale": "1:2"})
    win._on_section_edit("A-A")
    qapp.processEvents()
    s = cv.sections()[0]
    assert s["mode"] == "slice" and s["flip"] is True
    assert cv.sheet()["vscale"]["A-A"] == 0.5
    assert len(cv.views()["A-A"]) == 4               # wound alone
    assert "flipped" in win.status.currentMessage()
    win.undo()                                       # one capture
    s = cv.sections()[0]
    assert "mode" not in s and not s.get("flip")
