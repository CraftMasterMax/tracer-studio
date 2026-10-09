"""M82 — Project model edges into sketches (Fusion's Project/Include).

The workflow Fusion users lean on constantly: sketch on a face (or a
plane through the part) and PROJECT the solid's outline underneath, so
new geometry can snap to real material edges.  On a mesh kernel the
honest translation is a plane cross-section: slice the current solid
with the sketch plane and lay the contour under the cursor.

The projection lands as REFERENCE geometry (SketchModel.refs), never
solver entities: a projected circle is a 64-gon of the actual mesh,
and minting a solver Point per vertex would explode the DOF count and
turn every click into a phantom magnet.  Refs are drawn, persisted,
undoable and SNAP-TO (the drawing magnet grabs their vertices), but
they never enter loops, constraints or the profile stitcher — exactly
how Fusion treats projected edges as reference construction.

Honest limits: the section rides the SKETCH's own plane (origin planes
through the world origin; FACE sketches through their origin) and a
plane that grazes the solid's boundary falls back to a hair (±1 µm)
into the material, because a coplanar cut is undefined.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QPointF, Qt                       # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from tracer.core.document import Document, PrimitiveFeature          # noqa: E402
from tracer.core.geometry import Solid                               # noqa: E402
from tracer.core.sketch.model import SketchModel                     # noqa: E402


def _mesh(solid: Solid):
    tm = solid.to_trimesh()
    return np.asarray(tm.vertices, float), np.asarray(tm.faces, np.int64)


def _ring_area(pts):
    x, y = pts[:, 0], pts[:, 1]
    return abs(float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))) / 2


# ------------------------------------------------------------ core project

def test_box_section_becomes_one_welded_square():
    # the box sits ON the XY plane (coplanar bottom!) — the ε fallback
    # must find material a hair above it and land one 100 × 100 ring
    s = Solid.box(100.0, 100.0, 10.0)
    m = SketchModel(plane="XY")
    n = m.project(*_mesh(s))
    assert n == 1 and len(m.refs) == 1
    ring = m.refs[0]
    assert ring["closed"] and len(ring["pts"]) == 4      # corners only
    assert _ring_area(ring["pts"]) == pytest.approx(10000.0, rel=1e-3)


def test_cylinder_section_becomes_round_ring():
    s = Solid.cylinder(20.0, 10.0)
    m = SketchModel(plane="XY")
    assert m.project(*_mesh(s)) == 1
    pts = m.refs[0]["pts"]
    assert len(pts) >= 32                                # faceted truth
    assert _ring_area(pts) == pytest.approx(math.pi * 400.0, rel=0.02)


def test_holed_plate_sections_into_three_rings():
    plate = Solid.box(60.0, 40.0, 8.0)
    for cx in (20.0, 40.0):
        plate = plate.subtract(Solid.cylinder(5.0, 8.0, (cx, 20.0)))
    m = SketchModel(plane="XY")
    assert m.project(*_mesh(plate)) == 3                 # outer + 2 holes
    areas = sorted(_ring_area(r["pts"]) for r in m.refs)
    assert areas[-1] == pytest.approx(2400.0, rel=1e-2)
    assert areas[0] == pytest.approx(math.pi * 25.0, rel=0.03)
    assert areas[1] == pytest.approx(math.pi * 25.0, rel=0.03)


def test_face_sketch_projects_in_its_own_frame():
    # a FACE sketch on the box top: u,v basis, origin at the corner
    s = Solid.box(100.0, 100.0, 10.0)
    m = SketchModel(plane="FACE")
    m.axes = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    m.origin = (0.0, 0.0, 10.0)
    assert m.project(*_mesh(s)) == 1
    pts = m.refs[0]["pts"]
    assert _ring_area(pts) == pytest.approx(10000.0, rel=1e-3)
    assert pts[:, 0].min() == pytest.approx(0.0, abs=0.01)


def test_a_plane_offset_IN_PLANE_still_cuts_the_solid():
    # the sketch plane is INFINITE: shifting the frame origin sideways
    # only shifts the rings in frame coords, it never "misses"
    s = Solid.box(10.0, 10.0, 10.0)
    m2 = SketchModel(plane="FACE")
    m2.axes = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    m2.origin = (500.0, 500.0, 5.0)          # far sideways, still z=5
    assert m2.project(*_mesh(s)) == 1
    pts = m2.refs[0]["pts"]
    assert _ring_area(pts) == pytest.approx(100.0, rel=1e-6)
    # but a plane moved ALONG ITS NORMAL past the solid is honest-empty
    m3 = SketchModel(plane="XY")
    m3.origin = (0.0, 0.0, 500.0)            # 500 mm above everything
    assert m3.project(*_mesh(s)) == 0 and m3.refs == []


# ------------------------------------------------------- refs as data

def test_refs_round_trip_through_serialization():
    m = SketchModel(plane="XY")
    m.project(*_mesh(Solid.box(100.0, 100.0, 10.0)))
    back = None
    from tracer.core.sketch.model import model_from_dict, model_to_dict
    back = model_from_dict(model_to_dict(m))
    assert len(back.refs) == 1
    assert np.allclose(np.asarray(back.refs[0]["pts"], float),
                       m.refs[0]["pts"])


def test_refs_are_not_entities():
    m = SketchModel(plane="XY")
    m.project(*_mesh(Solid.box(100.0, 100.0, 10.0)))
    p0, p1 = m.point(-5, -5), m.point(5, 5)
    m.add_rect(p0, p1)
    loops, _warns = m.to_loops()
    assert len(loops) == 1                       # the rect only
    assert _ring_area(np.asarray(loops[0]["points"], float)) == \
        pytest.approx(100.0, rel=1e-6)


# -------------------------------------------------------------------- UI

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
        w.close()
        r.close()
    except Exception:
        raise


def _plate_sketch(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Plate", kind="box",
        dims={"dx": 100.0, "dy": 100.0, "dz": 10.0}))
    win.recompute()
    win.action_new_sketch("XY")
    qapp.processEvents()
    cv = win.sketch
    cv.set_grid_snap(False)
    cv._scale = 3.0
    cv._center = np.array([50.0, 50.0])
    qapp.processEvents()
    return cv


def _screen(cv, x, y) -> QPoint:
    return QPoint(int(cv.width() / 2 + (x - cv._center[0]) * cv._scale),
                  int(cv.height() / 2 - (y - cv._center[1]) * cv._scale))


def test_project_button_lands_refs_on_the_editing_sketch(win, qapp):
    cv = _plate_sketch(win, qapp)
    win._sketch_project_btn.click()
    qapp.processEvents()
    assert len(cv.model.refs) == 1
    assert "Projected" in win.status.currentMessage()


def test_project_replaces_instead_of_doubling(win, qapp):
    cv = _plate_sketch(win, qapp)
    win._sketch_project_btn.click()
    win._sketch_project_btn.click()
    qapp.processEvents()
    assert len(cv.model.refs) == 1                 # idempotent, not stacked


def test_drawing_magnet_snaps_to_projected_corners(win, qapp):
    cv = _plate_sketch(win, qapp)
    win._sketch_project_btn.click()
    corner = np.asarray(cv.model.refs[0]["pts"], float)
    cx, cy = float(corner[0][0]), float(corner[0][1])
    cv.set_tool("line")
    QTest.mouseClick(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     _screen(cv, cx + 1.2, cy + 1.2))      # near, not on
    QTest.mouseClick(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     _screen(cv, 50.0, 90.0))
    qapp.processEvents()
    ln = cv.model.sketch.lines[0]
    assert (ln.a.x, ln.a.y) == pytest.approx((cx, cy), abs=1e-9)


def test_undo_undoes_the_projection(win, qapp):
    cv = _plate_sketch(win, qapp)
    win._sketch_project_btn.click()
    qapp.processEvents()
    assert len(cv.model.refs) == 1
    assert cv.undo_op()
    assert cv.model.refs == []


def test_nothing_to_project_on_an_empty_document(win, qapp):
    win.new_document()
    win.action_new_sketch("XY")
    qapp.processEvents()
    win._sketch_project_btn.click()
    qapp.processEvents()
    assert win.sketch.model.refs == []
    assert "Nothing" in win.status.currentMessage()
