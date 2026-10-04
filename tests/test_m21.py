"""M21: Press-Pull — drag a planar face to add/remove material.

The viewport turns an LMB press+drag on a face into a signed mm offset
along the face normal; MainWindow expresses the edit as a regular
FACE-plane ExtrudeFeature (union when pulling out, subtract when pushing
in), so it is parametric, undoable, suppressible and serialized for free.
face_region validates the selection is one flat disc-with-holes patch and
returns its boundary polygons in the face's own basis.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

import trimesh                                        # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt        # noqa: E402
from PySide6.QtGui import QMouseEvent                 # noqa: E402
from PySide6.QtWidgets import QApplication            # noqa: E402

from tracer.core.document import (Document, ExtrudeFeature)   # noqa: E402
from tracer.core.io import load_document, save_document       # noqa: E402
from tracer.core.presspull import face_region                 # noqa: E402
from tracer.ui.mainwindow import MainWindow                   # noqa: E402
from tracer.ui.renderer import SceneRenderer                  # noqa: E402
from tracer.ui.viewport import _coplanar_groups               # noqa: E402


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
    w._unsaved = False
    r.ctx.release()
    w.close()


def box_doc():
    d = Document()
    d.add(ExtrudeFeature(name="Base",
                         outer=np.array([[0, 0], [40, 0], [40, 20], [0, 20]],
                                        float),
                         height=8.0))
    return d


def plane_group(solid, z, n_axis=2):
    """The coplanar group covering the +z plane of `solid` at height z,
    in the same index space the viewport uses (to_render_arrays)."""
    v, _n, f = solid.to_render_arrays()
    tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
    gid = _coplanar_groups(tm)
    fn = np.asarray(tm.face_normals)
    tc = np.asarray(tm.triangles_center)
    key = fn[:, n_axis]
    hi = 0.999 if n_axis == 2 else -0.999
    cand = np.flatnonzero((key > hi) & (np.abs(tc[:, 2] - z) < 1e-6))
    return tm, np.flatnonzero(gid == gid[cand[0]])


def payload(faces, point, normal, offset):
    return dict(faces=list(map(int, faces)), point=np.asarray(point, float),
                normal=np.asarray(normal, float), offset=float(offset),
                live=False)


# ---- face_region (pure kernel) ---------------------------------------------
def test_face_region_flat_square_patch():
    s = box_doc().recompute()
    tm, grp = plane_group(s, 8.0)
    reg = face_region(tm, grp)
    assert reg is not None
    assert np.allclose(reg["normal"], [0, 0, 1])
    assert len(reg["outer"]) == 4 and reg["holes"] == []
    x, y = reg["outer"][:, 0], reg["outer"][:, 1]
    area = abs((x * np.roll(y, -1) - np.roll(x, -1) * y).sum()) / 2
    assert area == pytest.approx(40 * 20, rel=1e-6)


def test_face_region_keeps_bore_as_hole_loop():
    from tracer.core.geometry import Solid
    s = (Solid.box(40, 40, 10)
         .subtract(Solid.cylinder(3, 10, center=(20, 20))))
    tm, grp = plane_group(s, 10.0)
    reg = face_region(tm, grp)
    assert reg is not None and len(reg["holes"]) == 1
    assert len(reg["holes"][0]) > 16           # tessellated circle


def test_face_region_rejects_curved_wall():
    from tracer.core.geometry import Solid
    s = Solid.cylinder(7, 12, center=(30, 20))
    tm = s.to_trimesh()
    tc = np.asarray(tm.triangles_center)
    rad = np.hypot(tc[:, 0] - 30, tc[:, 1] - 20)
    wall = np.flatnonzero((np.abs(rad - 7) < 0.02) & (tc[:, 2] > 2)
                          & (tc[:, 2] < 10))
    assert face_region(tm, wall) is None


# ---- the feature itself ------------------------------------------------------
def test_press_pull_adds_then_removes_material(win, qapp):
    win.doc = box_doc()
    win.recompute()
    _tm, grp = plane_group(win.doc.result, 8.0)
    win._press_pull(payload(grp, (20, 10, 8), (0, 0, 1), +6.0))
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(6400 + 800 * 6, rel=1e-6)
    feat = win.doc.features[-1]
    assert isinstance(feat, ExtrudeFeature) and feat.op == "union"
    assert feat.plane == "FACE" and feat.height == pytest.approx(6.0)

    _tm, grp2 = plane_group(win.doc.result, 14.0)
    win._press_pull(payload(grp2, (20, 10, 14), (0, 0, 1), -3.0))
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(11200 - 800 * 3, rel=1e-6)
    assert win.doc.features[-1].op == "subtract"
    assert win.doc.result.to_trimesh().is_watertight


def test_press_pull_hole_survives_pull(win, qapp):
    t = np.linspace(0, 2 * math.pi, 64, endpoint=False)
    bore = np.column_stack([20 + 3 * np.cos(t), 20 + 3 * np.sin(t)])
    win.doc = Document()
    win.doc.add(ExtrudeFeature(
        name="Plate",
        outer=np.array([[0, 0], [40, 0], [40, 40], [0, 40]], float),
        holes=[bore], height=10.0))
    win.recompute()
    base = win.doc.result.volume
    _tm, grp = plane_group(win.doc.result, 10.0)
    win._press_pull(payload(grp, (20, 20, 10), (0, 0, 1), +2.0))
    qapp.processEvents()
    ring = 40 * 40 - math.pi * 9
    assert win.doc.result.volume == pytest.approx(base + 2 * ring, rel=2e-3)
    assert win.doc.result.to_trimesh().is_watertight


def test_press_pull_curved_face_is_refused(win, qapp):
    from tracer.ui.mainwindow import demo_document
    win.doc = demo_document()
    win.recompute()
    n_before = len(win.doc.features)
    v, _n, f = win.doc.result.to_render_arrays()
    tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
    tc = np.asarray(tm.triangles_center)
    gid = _coplanar_groups(tm)
    rad = np.hypot(tc[:, 0] - 30, tc[:, 1] - 20)
    wall = np.flatnonzero((np.abs(rad - 7) < 0.02) & (tc[:, 2] > 10)
                          & (tc[:, 2] < 18))
    grp = np.flatnonzero(gid == gid[wall[0]])
    win._press_pull(payload(grp, (37, 20, 14), (1, 0, 0), +4.0))
    assert len(win.doc.features) == n_before
    assert "flat" in win.status.currentMessage()


def test_press_pull_tiny_offset_is_a_noop(win, qapp):
    win.doc = box_doc()
    win.recompute()
    _tm, grp = plane_group(win.doc.result, 8.0)
    win._press_pull(payload(grp, (20, 10, 8), (0, 0, 1), 0.01))
    assert len(win.doc.features) == 1


def test_press_pull_roundtrip_and_suppress(tmp_path, win, qapp):
    win.doc = box_doc()
    win.recompute()
    _tm, grp = plane_group(win.doc.result, 8.0)
    win._press_pull(payload(grp, (20, 10, 8), (0, 0, 1), +5.0))
    qapp.processEvents()
    vol = win.doc.result.volume
    path = tmp_path / "pp.tracer"
    save_document(win.doc, path)
    back = load_document(path)
    assert back.recompute().volume == pytest.approx(vol, rel=1e-9)
    assert back.features[-1].name.startswith("PressPull")
    back.features[-1].suppressed = True
    assert back.recompute().volume == pytest.approx(6400, rel=1e-9)


# ---- the gesture itself ------------------------------------------------------
def _px_of(vp, world):
    cam = vp.camera()
    vp_m = cam.proj_matrix(vp.width() / vp.height()) @ cam.view_matrix()
    clip = vp_m @ np.append(np.asarray(world, float), 1.0)
    ndc = clip[:3] / clip[3]
    return QPointF((ndc[0] * 0.5 + 0.5) * vp.width(),
                   (0.5 - ndc[1] * 0.5) * vp.height())


def _send(vp, kind, pos, button, buttons):
    g = QPointF(vp.mapToGlobal(pos.toPoint()))
    ev = QMouseEvent(kind, pos, g, button, buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, ev)


def test_press_pull_drag_with_mouse(win, qapp):
    win.doc = box_doc()
    win.recompute()
    vp = win.viewport
    vp.set_document(win.doc)
    vp.refresh(fit=True)
    qapp.processEvents()
    p0 = _px_of(vp, (20, 10, 8))                  # middle of the top face
    p1 = _px_of(vp, (20, 10, 14))                 # 6 mm up along +z
    _send(vp, QEvent.Type.MouseButtonPress, p0, Qt.MouseButton.LeftButton,
          Qt.MouseButtons.LeftButton)
    _send(vp, QEvent.Type.MouseMove, QPointF(p1.x(), p1.y()),
          Qt.MouseButton.NoButton, Qt.MouseButtons.LeftButton)
    _send(vp, QEvent.Type.MouseButtonRelease, QPointF(p1.x(), p1.y()),
          Qt.MouseButton.LeftButton, Qt.MouseButtons.NoButton)
    qapp.processEvents()
    names = [f.name for f in win.doc.features]
    assert any(n.startswith("PressPull") for n in names), names
    # sign depends on camera orientation; magnitude must be ~6 mm
    feat = win.doc.features[-1]
    assert feat.height == pytest.approx(6.0, abs=0.8)


def test_short_drag_is_a_click_not_a_pull(win, qapp):
    win.doc = box_doc()
    win.recompute()
    vp = win.viewport
    vp.set_document(win.doc)
    vp.refresh(fit=True)
    qapp.processEvents()
    p0 = _px_of(vp, (20, 10, 8))                  # middle of the top face
    _send(vp, QEvent.Type.MouseButtonPress, p0, Qt.MouseButton.LeftButton,
          Qt.MouseButtons.LeftButton)
    _send(vp, QEvent.Type.MouseButtonRelease, p0, Qt.MouseButton.LeftButton,
          Qt.MouseButtons.NoButton)
    qapp.processEvents()
    assert not any(f.name.startswith("PressPull") for f in win.doc.features)
    assert vp._sel, "plain click should have selected the face"


def _press_drag(vp, qapp, world_from, world_to):
    """Full press + one live move; returns (n_tri_base, n_tri_live)."""
    p0 = _px_of(vp, world_from)
    p1 = _px_of(vp, world_to)
    base_n = vp._r._solid_ntri
    _send(vp, QEvent.Type.MouseButtonPress, p0, Qt.MouseButton.LeftButton,
          Qt.MouseButtons.LeftButton)
    _send(vp, QEvent.Type.MouseMove, p1, Qt.MouseButton.NoButton,
          Qt.MouseButtons.LeftButton)
    qapp.processEvents()
    return base_n, vp._r._solid_ntri


def test_press_pull_shows_live_preview(win, qapp):
    win.doc = box_doc()
    win.recompute()
    vp = win.viewport
    vp.set_document(win.doc)
    vp.refresh(fit=True)
    qapp.processEvents()
    base_n, live_n = _press_drag(vp, qapp, (20, 10, 8), (20, 10, 14))
    assert live_n != base_n, "no live preview mesh during the drag"
    assert not any(f.name.startswith("PressPull") for f in win.doc.features), \
        "live move must not commit anything yet"
    _send(vp, QEvent.Type.MouseButtonRelease, _px_of(vp, (20, 10, 14)),
          Qt.MouseButton.LeftButton, Qt.MouseButtons.NoButton)
    qapp.processEvents()
    assert win.doc.features[-1].name.startswith("PressPull")


def test_press_pull_cancel_restores_preview(win, qapp):
    from PySide6.QtGui import QKeyEvent
    win.doc = box_doc()
    win.recompute()
    vp = win.viewport
    vp.set_document(win.doc)
    vp.refresh(fit=True)
    qapp.processEvents()
    base_n, live_n = _press_drag(vp, qapp, (20, 10, 8), (20, 10, 13))
    assert live_n != base_n
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                   Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, ev)
    qapp.processEvents()
    assert vp._r._solid_ntri == base_n, "Esc must restore the committed mesh"
    assert not any(f.name.startswith("PressPull") for f in win.doc.features)
    assert "cancel" in win.status.currentMessage().lower()
