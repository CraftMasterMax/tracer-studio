"""M8: double-click a planar face -> associative sketch on that face."""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt                  # noqa: E402
from PySide6.QtTest import QTest                        # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402

from forma.core.document import Document, ExtrudeFeature  # noqa: E402
from forma.core.sketch.model import face_basis, frame_matrix  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from forma.ui.mainwindow import MainWindow
    from forma.ui.renderer import SceneRenderer
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


def _plate_win(win):
    win.new_document()
    win.doc.add_plate("plate", 20, 20, 5)      # 2000 mm^3, top at z=5
    win.recompute()
    return win


def _px_of(vp, world):
    cam = vp.camera()
    vp_m = cam.proj_matrix(vp.width() / vp.height()) @ cam.view_matrix()
    clip = vp_m @ np.append(np.asarray(world, float), 1.0)
    ndc = clip[:3] / clip[3]
    return QPointF((ndc[0] * 0.5 + 0.5) * vp.width(),
                   (0.5 - ndc[1] * 0.5) * vp.height())


# ---- basis math ---------------------------------------------------------
@pytest.mark.parametrize("n", [(0, 0, 1), (0, 0, -1), (1, 0, 0),
                               (0.577, 0.577, 0.577)])
def test_face_basis_is_right_handed(n):
    u, v = face_basis(n)
    n = np.array(n, float) / np.linalg.norm(n)
    assert np.linalg.norm(u) == pytest.approx(1.0, abs=1e-9)
    assert u @ v == pytest.approx(0.0, abs=1e-9)
    assert np.cross(u, v) == pytest.approx(n, abs=1e-9)


def test_frame_matrix_maps_local_extrude_to_normal():
    u, v = face_basis((1, 0, 0))
    n = np.cross(u, v)
    m = frame_matrix(u, v, (2, 3, 4))
    assert m @ np.array([0, 0, 0, 1]) == pytest.approx([2, 3, 4, 1])
    assert m @ np.array([0, 0, 1, 1]) == pytest.approx(
        np.append(np.array([2, 3, 4]) + n, 1.0))     # extrude along +normal
    assert m @ np.array([1, 0, 0, 1]) == pytest.approx(
        np.append(np.array([2, 3, 4]) + u, 1.0))     # local x = u


# ---- picking --------------------------------------------------------------
def test_planar_pick_on_top_face(win, qapp):
    _plate_win(win)
    qapp.processEvents()
    vp = win.viewport
    hit = vp._pick_planar(_px_of(vp, (10, 10, 5)))
    assert hit is not None
    point, normal = hit
    assert normal[2] == pytest.approx(1.0, abs=1e-3)
    assert point[2] == pytest.approx(5.0, abs=0.2)


def test_curved_faces_are_rejected(win, qapp):
    win.new_document()
    win.doc.add_cylinder("column", radius=10, height=20, center=(0, 0))
    win.recompute()
    qapp.processEvents()
    vp = win.viewport
    assert vp._pick_planar(_px_of(vp, (10, 0, 10))) is None


# ---- end-to-end: double-click -> sketch -> extrude --------------------------
def test_sketch_on_face_flow_and_volume(win, qapp, monkeypatch):
    _plate_win(win)
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (3.0, True)))
    qapp.processEvents()
    vp = win.viewport
    QTest.mouseDClick(vp, Qt.LeftButton, Qt.NoModifier,
                      _px_of(vp, (10, 10, 5)).toPoint(), 10)
    qapp.processEvents()
    assert win.stack.currentWidget() is win._sketch_page
    m = win.sketch.model
    assert m.plane == "FACE"
    r0 = m.point(0, 0)
    m.add_rect(r0, m.point(8, 8))
    win.sketch.finish()
    qapp.processEvents()
    feats = [f for f in win.doc.features if isinstance(f, ExtrudeFeature)]
    assert len(feats) == 2
    ff = feats[1]
    assert ff.plane == "FACE" and ff.axes is not None
    assert abs(ff.placement[2] - 5.0) < 0.25          # sits on the face
    assert win.doc.result.volume == pytest.approx(2000 + 8 * 8 * 3, rel=1e-2)
    lo, hi = win.doc.result.bounding_box
    assert hi[2] == pytest.approx(8.0, abs=0.3)       # grew outward


def test_face_feature_serializes_and_reedits(win, qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (3.0, True)))
    test_sketch_on_face_flow_and_volume(win, qapp, monkeypatch)
    doc2 = Document.from_dict(win.doc.to_dict())
    ff = [f for f in doc2.features
          if isinstance(f, ExtrudeFeature) and f.plane == "FACE"][0]
    assert ff.axes is not None and len(ff.axes) == 2
    v1 = doc2.recompute().volume
    assert v1 == pytest.approx(win.doc.result.volume, rel=1e-9)

    # re-editing the face sketch updates the same feature, no duplicates
    feats = [f for f in win.doc.features if isinstance(f, ExtrudeFeature)]
    win.edit_sketch(feats[1])
    assert win.sketch.model.plane == "FACE"
    corner = win.sketch.model.sketch.lines[1].b
    corner.x, corner.y = 16.0, 16.0
    win.sketch.model.solve(pins=[corner])
    win.sketch.finish()
    qapp.processEvents()
    assert len([f for f in win.doc.features
                if isinstance(f, ExtrudeFeature)]) == 2
    assert win.doc.result.volume == pytest.approx(2000 + 16 * 16 * 3,
                                                  rel=1e-2)
