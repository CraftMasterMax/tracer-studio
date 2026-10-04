"""M13: fillet / chamfer of extrusion vertical edges (2D corner ops)."""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog     # noqa: E402

from forma.core.document import Document, ExtrudeFeature     # noqa: E402
from forma.core.geometry import round_corners, circle_contour  # noqa: E402

BOX = [(0, 0), (40, 0), (40, 25), (0, 25)]


# ---- geometry helper -------------------------------------------------------
def test_round_corners_area_math():
    r = round_corners(np.array(BOX, float), radius=5)
    area = abs(np.sum(r[:, 0] * np.roll(r[:, 1], -1)
                       - np.roll(r[:, 0], -1) * r[:, 1])) / 2
    ideal = 1000 - 4 * (25 - math.pi * 25 / 4)      # corners cut, arcs back
    assert area == pytest.approx(ideal, rel=5e-3)
    c = round_corners(np.array(BOX, float), chamfer=5)
    area = abs(np.sum(c[:, 0] * np.roll(c[:, 1], -1)
                       - np.roll(c[:, 0], -1) * c[:, 1])) / 2
    assert area == pytest.approx(1000 - 4 * 12.5, rel=1e-6)


def test_round_corners_skips_circles_and_concave():
    ring = circle_contour(10)
    assert len(round_corners(ring, radius=3)) == len(ring)
    L = np.array([(0, 0), (30, 0), (30, 10), (10, 10), (10, 30), (0, 30)],
                 float)
    out = round_corners(L, radius=4)
    concave_at = (10, 10)
    assert any(np.allclose(p, concave_at) for p in out), \
        "concave corner should be preserved sharp"


def test_round_corners_zero_is_identity():
    pts = np.array(BOX, float)
    assert np.array_equal(round_corners(pts), pts)


# ---- feature integration ---------------------------------------------------
def _box_feature(**kw):
    return ExtrudeFeature(name="b", outer=np.array(BOX, float),
                          height=10, **kw)


def test_extrude_fillet_volume():
    d = Document()
    d.features.append(_box_feature(fillet=5))
    sharp = 40 * 25 * 10
    assert d.result.volume == pytest.approx(
        sharp - 10 * 4 * (25 - math.pi * 25 / 4), rel=5e-3)


def test_extrude_chamfer_volume_exact():
    d = Document()
    d.features.append(_box_feature(chamfer=5))
    assert d.result.volume == pytest.approx(40 * 25 * 10 - 10 * 4 * 12.5,
                                            rel=1e-3)


def test_fillet_respects_holes():
    d = Document()
    d.features.append(ExtrudeFeature(
        name="plate", outer=np.array(BOX, float),
        holes=[np.array([(18, 10), (22, 10), (22, 15), (18, 15)], float)],
        height=10, fillet=2))
    v = d.result.volume
    # outer corners shrink 1000->996.6; hole corners GROW 20->23.4
    # (rounding is a cut against material, always):  (996.6-23.4)*10 = 9732
    assert 9600 < v < 9900


def test_fillet_serializes(tmp_path):
    from forma.core import io
    d = Document()
    d.features.append(_box_feature(fillet=3.5))
    p = tmp_path / "f.forma"
    io.save_document(d, p)
    d2 = io.load_document(p)
    assert d2.features[0].fillet == 3.5
    assert d2.result.volume == pytest.approx(d.result.volume, rel=1e-9)


# ---- UI --------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    from forma.ui.mainwindow import MainWindow
    from forma.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (10.0, True)))
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


def _drag_rect(cv, x1, y1):
    cv.set_tool("rect")
    p0 = cv.w2s(0, 0).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, p0, 10)
    p1 = cv.w2s(x1, y1).toPoint()
    QTest.mouseMove(cv, p1)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, p1, 10)
    QApplication.instance().processEvents()


def test_ui_fillet_then_undo(win, qapp):
    win.new_document()
    win.action_new_sketch()
    _drag_rect(win.sketch, 40, 25)
    win.sketch.finish()
    qapp.processEvents()
    f = win.doc.features[0]
    v_sharp = win.doc.result.volume
    win._set_corner(f, "fillet")          # getDouble patched -> 10 mm
    assert f.fillet == 10.0
    v_round = win.doc.result.volume
    assert v_round < v_sharp - 500
    win.undo()                            # document undo restores state
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(v_sharp, rel=1e-6)


def test_fillet_and_chamfer_are_exclusive(win):
    win.new_document()
    win.action_new_sketch()
    _drag_rect(win.sketch, 30, 30)
    win.sketch.finish()
    f = win.doc.features[0]
    win._set_corner(f, "fillet")
    assert f.fillet == 10 and f.chamfer == 0
    win._set_corner(f, "chamfer")
    assert f.chamfer == 10 and f.fillet == 0


def test_fillet_zero_restores_sharp(win):
    win.new_document()
    win.action_new_sketch()
    _drag_rect(win.sketch, 30, 30)
    win.sketch.finish()
    f = win.doc.features[0]
    v_sharp = win.doc.result.volume
    win._set_corner(f, "fillet")
    win.undo()
    from forma.ui.mainwindow import MainWindow  # noqa: F401
    # apply zero directly (dialog returns 0 when user clears)
    f.fillet = 0.0
    win.doc.dirty = True
    assert win.doc.result.volume == pytest.approx(v_sharp, rel=1e-6)
