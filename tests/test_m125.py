"""M125 — construction geometry: named datums become first-class.

A datum is a frame and nothing more: planes carry (origin, u, v, n),
axes carry (origin, dir), and creation is pure frame algebra — every
method here works without any B-rep face identity, which is what a
mesh-timeline kernel can honour forever. These tests pin the frame
math, the honest refusals (collinear points, non-parallel midplanes,
coincident points), the shared name pool, persistence, and the UI
paths that create and delete datums.
"""
import math

import numpy as np
import pytest

from tracer.core import params
from tracer.core.document import Document


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
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
    qapp.processEvents()
    w._discard_guard = lambda: True
    yield w
    w._unsaved = False
    w.close()
    r.close()


# ---- core: plane creation methods --------------------------------------

def test_offset_plane_unchanged_plus_method_stamp():
    d = Document()
    p = d.add_plane("XY", 4.0)
    assert p["method"] == "offset" and p["base"] == "XY"
    assert p["origin"] == [0.0, 0.0, 4.0]          # legacy shape intact


def test_angle_plane_tips_and_pivots_about_its_hinge():
    d = Document()
    p = d.add_plane_angle("XY", 30.0)              # about u (the X axis)
    n = np.array(p["n"])
    assert abs(n[2] - math.cos(math.radians(30))) < 1e-12
    assert np.allclose(np.cross(p["u"], p["v"]), n, atol=1e-12)
    # 90° about v hinged at (5,0,0): the base origin swings to (5,0,5)
    q = d.add_plane_angle("XY", 90.0, hinge="v", through=(5, 0, 0))
    assert np.allclose(q["origin"], [5, 0, 5], atol=1e-9)
    with pytest.raises(params.ParamError):
        d.add_plane_angle("XY", 10.0, hinge="n")   # can't hinge on itself


def test_three_point_plane_and_collinear_refusal():
    d = Document()
    p = d.add_plane_3pt((1, 0, 0), (0, 1, 0), (0, 0, 1))
    assert np.allclose(p["origin"], [1 / 3, 1 / 3, 1 / 3])
    assert np.allclose(p["n"], np.array([1.0, 1, 1]) / math.sqrt(3),
                       atol=1e-12)
    assert np.allclose(np.cross(p["u"], p["v"]), p["n"], atol=1e-12)
    with pytest.raises(params.ParamError):
        d.add_plane_3pt((0, 0, 0), (1, 1, 1), (2, 2, 2))


def test_midplane_splits_and_refuses_nonparallel():
    d = Document()
    a = d.add_plane("XY", 2.0)
    b = d.add_plane("XY", 8.0)
    m = d.add_plane_mid("XY", a["name"])
    assert np.allclose(m["origin"], [0, 0, 1]), m["origin"]
    m2 = d.add_plane_mid(a["name"], b["name"])
    assert np.allclose(m2["origin"], [0, 0, 5])
    with pytest.raises(params.ParamError):
        d.add_plane_mid("XY", "XZ")


# ---- core: work axes ----------------------------------------------------

def test_axis_two_points_and_degenerate_refusal():
    d = Document()
    a = d.add_axis_2pt((1, 2, 3), (1, 2, 7))
    assert np.allclose(a["dir"], [0, 0, 1]) and a["origin"] == [1.0, 2.0, 3.0]
    with pytest.raises(params.ParamError):
        d.add_axis_2pt((0, 0, 0), (0, 0, 0))


def test_axis_two_planes_is_the_intersection_line():
    d = Document()
    z4 = d.add_plane("XY", 4.0)
    x5 = d.add_plane("YZ", 5.0)
    a = d.add_axis_2planes(z4["name"], x5["name"])
    assert abs(abs(a["dir"][1]) - 1.0) < 1e-12          # runs along ±Y
    assert np.allclose(a["origin"], [5, 0, 4], atol=1e-9)
    with pytest.raises(params.ParamError):
        d.add_axis_2planes("XY", z4["name"])            # parallel: no line


# ---- core: resolution, naming, persistence ------------------------------

def test_frames_resolve_by_origin_or_stored_name():
    d = Document()
    p = d.add_plane("XY", 6.0)
    a = d.add_axis_2pt((0, 0, 0), (2, 2, 0))
    assert d.plane_frame("YZ")[3] == [1.0, 0.0, 0.0]
    assert d.plane_frame(p["name"])[0] == [0.0, 0.0, 6.0]
    assert d.axis_frame("Z")[1] == [0.0, 0.0, 1.0]
    assert np.allclose(d.axis_frame(a["name"])[1],
                       [1 / math.sqrt(2), 1 / math.sqrt(2), 0])
    with pytest.raises(params.ParamError):
        d.plane_frame("Plane 77")
    with pytest.raises(params.ParamError):
        d.axis_frame("Axis 77")


def test_datums_share_one_name_pool_and_recycle_gaps():
    d = Document()
    p1 = d.add_plane("XY", 1.0)
    a1 = d.add_axis_2pt((0, 0, 0), (0, 0, 1))
    assert (p1["name"], a1["name"]) == ("Plane 1", "Axis 1")
    d.remove_plane("Plane 1")
    assert d.add_plane("XY", 2.0)["name"] == "Plane 1"   # gap recycled


def test_io_roundtrip_keeps_method_payloads_and_loads_legacy():
    from tracer.core.io import save_document, load_document
    import tempfile
    from pathlib import Path
    d = Document()
    d.add_plane("XY", 3.0)
    d.add_plane_angle("XY", 42.0, hinge="v", through=(1, 2, 3))
    d.add_plane_3pt((1, 0, 0), (0, 1, 0), (0, 0, 1))
    d.add_axis_2pt((0, 0, 0), (1, 2, 3))
    d.add_axis_2planes("XY", "XZ")
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "d.tracer"
        save_document(d, path)
        r = load_document(path)
    assert [p["name"] for p in r.planes] == [p["name"] for p in d.planes]
    assert r.planes[1] == d.planes[1]                   # angle payload
    assert r.axes == d.axes                             # every axis, exact
    legacy = d.to_dict()
    legacy.pop("axes")                                  # pre-M125 file
    r2 = Document.from_dict(legacy)
    assert r2.axes == [] and len(r2.planes) == len(d.planes)


# ---- UI: browser + creation dialogs --------------------------------------

def test_browser_lists_datums_under_one_construction_bulb(win, qapp):
    win.doc.add_plane("XY", 3.0)
    win.doc.add_axis_2pt((0, 0, 0), (0, 0, 5))
    win.rail.tree.reload()
    qapp.processEvents()
    root = win.rail.tree.topLevelItem(0)
    constr = None
    for i in range(root.childCount()):
        it = root.child(i)
        if it.text(0).startswith("Construction"):
            constr = it
    assert constr is not None and constr.text(0) == "Construction (2)"
    from PySide6.QtCore import Qt
    roles = [constr.child(i).data(0, Qt.UserRole)
             for i in range(constr.childCount())]
    assert ("cplane", "Plane 1") in roles and ("caxis", "Axis 1") in roles


def _dialog_answers(monkeypatch, values):
    from tracer.ui import cmddialog
    monkeypatch.setattr(cmddialog, "ask",
                        lambda parent, title, fields, remember_key=None:
                        dict(values))


def test_plane_dialog_creates_each_method(win, monkeypatch):
    _dialog_answers(monkeypatch, {"how": "Offset from origin plane",
                                  "base": "XY", "dist": 10.0})
    win.action_construction_plane()
    assert win.doc.planes[0]["method"] == "offset"
    _dialog_answers(monkeypatch, {"how": "At angle about hinge",
                                  "base": "XY", "angle": 45.0,
                                  "hinge": "v — plane's own Y"})
    win.action_construction_plane()
    assert win.doc.planes[1]["method"] == "angle"
    _dialog_answers(monkeypatch, {"how": "Through three points",
                                  "p1": "1,0,0", "p2": "0,1,0",
                                  "p3": "0,0,1"})
    win.action_construction_plane()
    assert win.doc.planes[2]["method"] == "three-points"
    _dialog_answers(monkeypatch, {"how": "Midplane between two",
                                  "pa": "XY", "pb": "Plane 1"})   # parallel
    win.action_construction_plane()
    assert win.doc.planes[3]["method"] == "midplane"
    assert np.allclose(win.doc.planes[3]["origin"], [0, 0, 5.0])
    assert len(win.doc.planes) == 4


def test_plane_dialog_refuses_garbage_points_loudly_not_by_crash(
        win, monkeypatch):
    _dialog_answers(monkeypatch, {"how": "Through three points",
                                  "p1": "left,0,0", "p2": "0,1,0",
                                  "p3": "0,0,1"})
    win.action_construction_plane()                # must not raise
    assert win.doc.planes == []
    assert "refused" in win.status.currentMessage().lower()


def test_axis_dialog_two_points_and_two_planes(win, monkeypatch):
    _dialog_answers(monkeypatch, {"how": "Through two points",
                                  "p1": "0,0,0", "p2": "1,0,1"})
    win.action_work_axis()
    assert np.allclose(win.doc.axes[0]["dir"],
                       [1 / math.sqrt(2), 0, 1 / math.sqrt(2)])
    _dialog_answers(monkeypatch, {"how": "Intersection of two planes",
                                  "pa": "XY", "pb": "XZ"})
    win.action_work_axis()
    assert abs(abs(win.doc.axes[1]["dir"][0]) - 1.0) < 1e-12  # the X line


def test_axis_delete_via_handler(win, qapp):
    win.doc.add_axis_2pt((0, 0, 0), (0, 0, 4))
    win._delete_axis("Axis 1")
    assert win.doc.axes == []
    win.rail.tree.reload()
    qapp.processEvents()


# ---- M125 part 2: named datums drive transforms --------------------------

def _source_box(d, at=(10.0, 5.0, 0.0)):
    from tracer.core.document import PrimitiveFeature
    f = PrimitiveFeature(name="lug", kind="box",
                         dims={"dx": 2, "dy": 2, "dz": 2},
                         placement=at)
    d.add(f)
    d.recompute()
    return f


def test_circular_pattern_about_named_work_axis():
    d = Document()
    src = _source_box(d)
    a = d.add_axis_2pt((5, 5, 0), (5, 5, 10))      # vertical line at (5,5)
    d.add_circular_pattern("ring", src, axis=a["name"],
                           angle=360.0, count=4)
    d.recompute()
    assert d.result.volume == pytest.approx(4 * 8, rel=1e-6)
    bb = np.asarray(d.result.bounding_box, float)
    assert np.allclose(bb[0], [-2, -2, 0], atol=1e-6)   # 4-fold symmetric
    assert np.allclose(bb[1], [12, 12, 2], atol=1e-6)


def test_named_Z_axis_pattern_matches_the_legacy_center_pattern():
    d = Document()
    src = _source_box(d)
    d.add_circular_pattern("legacy", src, center=(0, 0), angle=360.0,
                           count=4)
    d.recompute()
    v_legacy = d.result.volume
    bb_legacy = np.asarray(d.result.bounding_box, float)
    d2 = Document()
    src2 = _source_box(d2)
    d2.add_circular_pattern("named", src2, angle=360.0, count=4, axis="Z")
    d2.recompute()
    assert d2.result.volume == pytest.approx(v_legacy, rel=1e-9)
    assert np.allclose(d2.result.bounding_box, bb_legacy, atol=1e-6)


def test_mirror_across_named_offset_plane():
    d = Document()
    src = _source_box(d, at=(0.0, 0.0, 0.0))       # z in [0, 2]
    p = d.add_plane("XY", 10.0)                    # z = 10
    d.add_mirror("twin", src, plane=p["name"])
    d.recompute()
    bb = np.asarray(d.result.bounding_box, float)
    assert np.allclose(bb[0], [0, 0, 0], atol=1e-6)
    assert np.allclose(bb[1], [2, 2, 20], atol=1e-6)  # twin at z in [18,20]
    assert d.result.volume == pytest.approx(16, rel=1e-6)


def test_mirror_across_tilted_three_point_plane():
    d = Document()
    src = _source_box(d, at=(0.0, 0.0, 0.0))       # x in [0, 2]
    p = d.add_plane_3pt((10, 0, 0), (10, 10, 0), (10, 0, 10))
    d.add_mirror("twin", src, plane=p["name"])
    d.recompute()
    bb = np.asarray(d.result.bounding_box, float)
    assert abs(bb[1][0] - 20.0) < 1e-6              # twin x in [18, 20]
    assert abs(bb[0][0]) < 1e-6


def test_pattern_and_mirror_datum_names_survive_io():
    import tempfile
    from pathlib import Path
    from tracer.core.io import save_document, load_document
    d = Document()
    src = _source_box(d)
    a = d.add_axis_2pt((0, 0, 0), (0, 0, 9))
    d.add_circular_pattern("ring", src, axis=a["name"], angle=180.0,
                           count=3)
    d.add_mirror("twin", src, plane="XY", offset=7.0)
    with tempfile.TemporaryDirectory() as t:
        pth = Path(t) / "p.tracer"
        save_document(d, pth)
        r = load_document(pth)
    from tracer.core.document import CircularPatternFeature, MirrorFeature
    cp = next(f for f in r.features if isinstance(f, CircularPatternFeature))
    assert cp.axis == "Axis 1"
    mf = next(f for f in r.features if isinstance(f, MirrorFeature))
    assert mf.plane == "XY" and mf.offset == 7.0
    r.recompute()                                # resolves against reloaded
    assert r.result.volume > 0


def test_unknown_datum_names_raise_not_silently():
    d = Document()
    src = _source_box(d)
    f = d.add_circular_pattern("ghost", src, axis="Axis 99")
    with pytest.raises(params.ParamError):
        d.recompute()
    f.axis = ""                                   # back to legacy: fine
    d.recompute()
    d2 = Document()
    s2 = _source_box(d2)
    d2.add_mirror("ghost", s2, plane="Plane 77")
    with pytest.raises(params.ParamError):
        d2.recompute()


def test_circular_dialog_passes_named_axis(win, monkeypatch):
    from tracer.core.document import PrimitiveFeature, \
        CircularPatternFeature
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2, "dy": 2, "dz": 2},
                                 placement=(10, 5, 0)))
    win.recompute()
    win.doc.add_axis_2pt((5, 5, 0), (5, 5, 9))
    _dialog_answers(monkeypatch, {"src": "lug", "axis": "Axis 1",
                                  "cx": 0.0, "cy": 0.0, "ang": 360.0,
                                  "count": 4})
    win.action_circular_pattern()
    cp = [f for f in win.doc.features
          if isinstance(f, CircularPatternFeature)][0]
    assert cp.axis == "Axis 1"


def test_circular_dialog_default_is_the_legacy_plus_z(win, monkeypatch):
    from tracer.core.document import PrimitiveFeature, \
        CircularPatternFeature
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2, "dy": 2, "dz": 2},
                                 placement=(10, 5, 0)))
    win.recompute()
    _dialog_answers(monkeypatch, {"src": "lug",
                                  "axis": "+Z (through center)",
                                  "cx": 0.0, "cy": 0.0, "ang": 360.0,
                                  "count": 6})
    win.action_circular_pattern()
    cp = [f for f in win.doc.features
          if isinstance(f, CircularPatternFeature)][0]
    assert cp.axis == ""


# ---- M125 part 3: datum-aware errors ------------------------------------

def test_datum_references_names_only_real_name_bindings():
    d = Document()
    src = _source_box(d)
    a = d.add_axis_2pt((0, 0, 0), (0, 0, 5))
    p = d.add_plane("XY", 8.0)
    d.add_circular_pattern("ring", src, axis=a["name"], angle=360.0,
                           count=4)
    d.add_circular_pattern("plain", src, center=(0, 0), count=3)
    d.add_mirror("twin", src, plane=p["name"])
    assert d.datum_references(a["name"]) == ["ring"]      # named pivot
    assert d.datum_references(p["name"]) == ["twin"]      # named plane
    assert d.datum_references("XY") == []     # legacy paths bind nothing
    assert d.datum_references("Plane 77") == []


def test_resolver_errors_teach_the_cure():
    d = Document()
    with pytest.raises(params.ParamError, match=r"Ctrl\+Shift\+O"):
        d.axis_frame("Axis 42")
    with pytest.raises(params.ParamError, match=r"Ctrl\+Shift\+P"):
        d.plane_frame("Plane 42")


def test_delete_datum_with_a_dependent_asks_first(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.core.document import PrimitiveFeature
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2, "dy": 2, "dz": 2}))
    p = win.doc.add_plane("XY", 6.0)
    win.doc.add_mirror("twin", win.doc.features[-1], plane=p["name"])
    asked = []

    def fake_question(*a, **k):
        asked.append(a[2])                      # the informative text
        return QMessageBox.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    win._delete_plane(p["name"])
    assert asked and "twin" in asked[0]         # warning named the feature
    assert len(win.doc.planes) == 1             # NO kept the datum alive
    assert "kept" in win.status.currentMessage()
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda parent, title, text, *a, **k:
                     warned.append(text) or QMessageBox.Ok))
    win._delete_plane(p["name"])
    assert win.doc.planes == []                 # YES deleted it
    assert warned and "Plane 1" in warned[0]    # M118 modal told the user
    assert getattr(win.doc, "failed_feature", None) is not None  # badged


def test_delete_unreferenced_datum_never_asks(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    called = []
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: called.append(1) or QMessageBox.Yes))
    win.doc.add_axis_2pt((0, 0, 0), (0, 0, 4))
    win._delete_axis("Axis 1")
    assert win.doc.axes == [] and not called    # no references, no ceremony


# ---- renderer: axes flow to the line mesh (GL-gated) ---------------------

def test_renderer_draws_axes_without_any_plane(qapp):
    try:
        from tracer.ui.renderer import SceneRenderer
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    r.set_planes([])
    assert r._plane_count == 0
    r.set_planes([], [{"name": "Axis 1", "origin": [0, 0, 5],
                       "dir": [0, 0, 1]}])
    assert r._plane_count == 2                     # one line, two verts
    r.close()
