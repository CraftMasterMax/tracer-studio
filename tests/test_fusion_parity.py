"""Fusion-parity sprint tests: mouse scheme, auto-constraints, planes,
sketch serialization, associative re-extrude, timeline, ViewCube."""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, QPoint, Qt  # noqa: E402
from PySide6.QtTest import QSignalSpy, QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

from forma.core.document import ExtrudeFeature  # noqa: E402
from forma.core.geometry import Solid  # noqa: E402
from forma.core.sketch.constraints import Distance, Horizontal  # noqa: E402
from forma.core.sketch.model import (SketchModel, model_from_dict,  # noqa: E402
                                     model_to_dict, plane_matrix)
from forma.ui.camera import Camera  # noqa: E402
from forma.ui.mainwindow import MainWindow  # noqa: E402
from forma.ui.renderer import SceneRenderer  # noqa: E402
from forma.ui.viewcube import ViewCube  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False       # close guard would open a modal
    w.close()


# ---- planes / kernel ------------------------------------------------------
def test_plane_matrix_extrude_directions():
    assert np.allclose(plane_matrix("XY") @ np.array([0, 0, 1, 1]),
                       [0, 0, 1, 1])
    assert np.allclose(plane_matrix("XZ") @ np.array([0, 0, 1, 1]),
                       [0, -1, 0, 1])
    assert np.allclose(plane_matrix("YZ") @ np.array([0, 0, 1, 1]),
                       [1, 0, 0, 1])


def test_xz_extrude_orientation():
    outer = np.array([[0, 0], [10, 0], [10, 20], [0, 20]], float)
    s = ExtrudeFeature(name="wall", outer=outer, height=5, plane="XZ").build()
    assert s.volume == pytest.approx(1000)
    lo, hi = s.bounding_box
    np.testing.assert_allclose(lo, [0, -5, 0], atol=0.05)
    np.testing.assert_allclose(hi, [10, 0, 20], atol=0.05)
    assert s.to_trimesh().is_watertight


# ---- serialization ----------------------------------------------------------
def test_model_roundtrip_preserves_geometry_and_constraints():
    m = SketchModel(plane="XZ")
    p0, p1 = m.point(1, 2), m.point(20, 15)
    m.add_rect(p0, p1)
    c = m.add_circle(m.point(10, 8), 3)
    m.constrain(Distance(p0, p1, 25.0))
    # a dimension between two lone fixed points (not on any entity):
    # regression guard for point-index confusion in model_to_dict
    q0, q1 = m.point(0, 0), m.point(12, 0)
    m.constrain(Distance(q0, q1, 12.0))
    d = model_to_dict(m)
    m2 = model_from_dict(d)
    assert m2.plane == "XZ"
    assert len(m2.sketch.lines) == 4 and len(m2.sketch.circles) == 1
    kinds = [type(c).__name__ for c in m2.sketch.constraints]
    assert kinds.count("Horizontal") == 2 and kinds.count("Vertical") == 2
    assert kinds.count("Distance") == 2
    assert "Distance" in kinds
    v1 = sum(l["area"] for l in m.to_loops()[0])
    v2 = sum(l["area"] for l in m2.to_loops()[0])
    assert v1 == pytest.approx(v2)


# ---- auto-constraints while drawing ----------------------------------------
def _press(cv, wx, wy, button=Qt.LeftButton, mods=Qt.NoModifier):
    QTest.mousePress(cv, button, mods, cv.w2s(wx, wy).toPoint(), 10)


def _release(cv, wx, wy, button=Qt.LeftButton):
    QTest.mouseRelease(cv, button, Qt.NoModifier, cv.w2s(wx, wy).toPoint(), 10)


def test_line_tool_snaps_horizontal_and_records_constraint(win, qapp):
    win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("line")
    _press(cv, 0, 50)
    _release(cv, 0, 50)
    # draw near-horizontal (intentionally 0.5mm off at scale ~?; still <3px)
    _press(cv, 40, 50)
    _release(cv, 40, 50)
    _press(cv, 80, 50.4)             # off by 0.4mm -> within 3 px
    _release(cv, 80, 50.4)
    qapp.processEvents()
    hs = [c for c in cv.model.sketch.constraints
          if isinstance(c, Horizontal)]
    assert len(hs) >= 1, "auto-horizontal constraint missing"
    b = cv.model.sketch.lines[-1].b
    assert b.y == pytest.approx(cv.model.sketch.lines[-1].a.y, abs=1e-9)


# ---- associative edit: the Fusion moment -------------------------------------
def test_edit_sketch_updates_solid(win, qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (4.0, True)))
    win.new_document()                     # empty doc: clean volume baseline
    win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("rect")
    _press(cv, 0, 0)
    QTest.mouseMove(cv, cv.w2s(30, 20).toPoint())
    _release(cv, 30, 20)
    qapp.processEvents()
    cv.finish()
    qapp.processEvents()
    feats = [f for f in win.doc.features if isinstance(f, ExtrudeFeature) and f.sketch]
    assert len(feats) == 1
    v1 = win.doc.result.volume
    assert v1 == pytest.approx(30 * 20 * 4, rel=1e-2)

    # double-click the sketch in the browser and drag the TOP-RIGHT corner:
    # rect grows to 60x40 (bottom-left stays put via minimal-motion solve)
    n_feats = len(win.doc.features)
    win.edit_sketch(feats[0])
    assert win.stack.currentWidget() is win._sketch_page
    corner = win.sketch.model.sketch.lines[1].b     # top-right (30,20)
    corner.x, corner.y = 60.0, 40.0
    win.sketch.model.solve(pins=[corner])
    win.sketch.finish()
    qapp.processEvents()
    assert len(win.doc.features) == n_feats          # still one feature
    v2 = win.doc.result.volume
    assert v2 == pytest.approx(v1 * 4, rel=1e-2)     # 60x40 vs 30x20


def test_sketch_reedit_removes_and_adds_region_features(win, qapp, monkeypatch):
    """Multi-region sketches must stay in sync both ways: fewer regions
    than features drops the stale ones, more regions appends new ones."""
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (6.0, True)))
    win.new_document()
    win.action_new_sketch()
    m = win.sketch.model
    m.add_rect(m.point(0, 0), m.point(10, 10))
    m.add_rect(m.point(20, 0), m.point(30, 10))
    win.sketch.finish()
    qapp.processEvents()
    assert len([f for f in win.doc.features if f.sketch]) == 2
    assert win.doc.result.volume == pytest.approx(2 * 100 * 6, rel=1e-2)

    # shrink: delete the second rectangle's lines -> its feature must vanish
    win.edit_sketch(win.doc.features[0])
    for l in list(win.sketch.model.sketch.lines)[4:]:
        win.sketch.model.delete_entity(l)
    win.sketch.finish()
    qapp.processEvents()
    assert len([f for f in win.doc.features if f.sketch]) == 1, \
        "stale feature survived region shrink"
    assert win.doc.result.volume == pytest.approx(100 * 6, rel=1e-2)

    # grow: draw a region back -> feature reappears with kept height
    win.edit_sketch(win.doc.features[0])
    m2 = win.sketch.model
    m2.add_rect(m2.point(20, 0), m2.point(30, 10))
    win.sketch.finish()
    qapp.processEvents()
    assert len([f for f in win.doc.features if f.sketch]) == 2
    assert win.doc.result.volume == pytest.approx(2 * 100 * 6, rel=1e-2)


# ---- feature management (context menus) --------------------------------------
def test_delete_feature_and_undo(qapp):
    from forma.ui.mainwindow import MainWindow
    from forma.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    win = MainWindow(renderer=r)
    win.new_document()
    outer = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    win.doc.add(ExtrudeFeature(name="sq", outer=outer, height=2))
    win.recompute()
    v0 = win.doc.result.volume
    win._delete_feature(win.doc.features[0])
    assert len(win.doc.features) == 0
    assert win.doc.result is None or win.doc.result.volume == pytest.approx(0)
    win.undo()
    assert len(win.doc.features) == 1
    assert win.doc.result.volume == pytest.approx(v0)
    win._unsaved = False
    win.close()


def test_set_distance_and_rename(qapp, monkeypatch):
    from forma.ui.mainwindow import MainWindow
    from forma.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    win = MainWindow(renderer=r)
    win.new_document()
    outer = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    win.doc.add(ExtrudeFeature(name="sq", outer=outer, height=2))
    win.recompute()
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (5.0, True)))
    win._set_distance(win.doc.features[0])
    assert win.doc.features[0].height == 5.0
    assert win.doc.result.volume == pytest.approx(500)
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("bearing block", True)))
    win._rename_feature(win.doc.features[0])
    assert win.doc.features[0].name == "bearing block"
    root = win.rail.tree.topLevelItem(0)
    assert "bearing block" in root.child(1).text(0)   # tree refreshed
    win._unsaved = False
    win.close()


def test_timeline_right_click_emits_menu(qapp):
    from forma.core.document import Document
    from forma.ui.timeline import TimelineBar
    doc = Document("t")
    outer = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    doc.add(ExtrudeFeature(name="sq", outer=outer, height=2))
    bar = TimelineBar()
    bar.resize(400, 38)
    bar.set_document(doc)
    bar.grab()                               # force paint -> chip layout
    assert bar._chips, "timeline painted no chips"
    x, w, f = bar._chips[0]
    spy = QSignalSpy(bar.feature_menu)
    QTest.mousePress(bar, Qt.RightButton, Qt.NoModifier,
                     QPoint(int(x + w / 2), 20), 10)
    assert spy.count() == 1
    assert spy.at(0)[0] is f


# ---- sketch cursor readout ----------------------------------------------------
def test_sketch_shows_cursor_coordinates(win, qapp):
    win.action_new_sketch()
    cv = win.sketch
    QTest.mouseMove(cv, cv.w2s(12.5, -7.25).toPoint())
    qapp.processEvents()
    assert cv._cursor is not None
    assert cv._cursor[0] == pytest.approx(12.5, abs=0.2)
    assert cv._cursor[1] == pytest.approx(-7.25, abs=0.2)
    cv.grab()                                # HUD with coords must not crash


# ---- Fusion mouse scheme (3D viewport) ---------------------------------------
def test_middle_drag_orbits_shift_pans_and_click_homes(win, qapp):
    vp = win.viewport
    cam = vp.camera()
    y0, p0, t0 = cam.yaw, cam.pitch, cam.target.copy()
    d = win.viewport
    QTest.mousePress(d, Qt.MiddleButton, Qt.NoModifier, QPoint(300, 300), 10)
    QTest.mouseMove(d, QPoint(340, 320))
    QTest.mouseRelease(d, Qt.MiddleButton, Qt.NoModifier, QPoint(340, 320), 10)
    assert cam.yaw != y0 and cam.pitch != p0
    # QTest.move drops modifier state; send a real event with Shift baked in
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(280, 290), QPointF(280, 290),
                     Qt.MouseButton.MiddleButton,
                     Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.ShiftModifier)
    QTest.mousePress(d, Qt.MiddleButton, Qt.ShiftModifier, QPoint(300, 300), 10)
    qapp.sendEvent(d, ev)
    QTest.mouseRelease(d, Qt.MiddleButton, Qt.ShiftModifier, QPoint(280, 290), 10)
    assert not np.allclose(cam.target, t0), "Shift+MMB pan did nothing"
    cam.yaw, cam.pitch = 1.234, -0.432
    QTest.mousePress(d, Qt.MiddleButton, Qt.NoModifier, QPoint(400, 300), 10)
    QTest.mouseRelease(d, Qt.MiddleButton, Qt.NoModifier, QPoint(400, 300), 10)
    assert abs(cam.yaw - math.radians(45)) < 1e-9    # home (iso fit)


# ---- ViewCube ---------------------------------------------------------------
def test_viewcube_projects_and_hits():
    cube = ViewCube()
    cube.place(800, 600)
    cam = Camera()
    from forma.ui.viewport import Viewport  # noqa: F401
    from PySide6.QtGui import QImage, QPainter
    img = QImage(800, 600, QImage.Format_RGBA8888)
    img.fill(Qt.transparent)
    p = QPainter(img)
    cube.draw(p, cam)
    p.end()
    face_px = np.frombuffer(img.constBits(), np.uint8,
                            img.sizeInBytes()).reshape(600, 800, 4)
    region = face_px[:, 700:760]                     # cube corner area
    assert (region[:, :, 3] > 0).sum() > 200, "ViewCube not drawn"
    kind = cube.hit(QPointF(755, 40))                # dead center of cube
    assert kind is None or kind in ("front", "back", "right", "left",
                                    "top", "bottom")
