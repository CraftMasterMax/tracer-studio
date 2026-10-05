"""M12: Revolve — profile swept about the sketch's vertical axis."""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog     # noqa: E402
from conftest import tree_texts                              # noqa: E402

from tracer.core.document import (Document, ExtrudeFeature,      # noqa: E402
                                 RevolveFeature)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")

    def fake_getdouble(parent, title, label, *a, **k):
        return (360.0, True) if "Revolve" in title else (10.0, True)

    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(fake_getdouble))
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


def _drag_rect(cv, u0, v0, u1, v1):
    cv.set_tool("rect")
    p0 = cv.w2s(u0, v0).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, p0, 10)
    p1 = cv.w2s(u1, v1).toPoint()
    QTest.mouseMove(cv, p1)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, p1, 10)
    QApplication.instance().processEvents()


# ---- core ------------------------------------------------------------------
def _tube_profile():
    return np.array([(5, 0), (10, 0), (10, 4), (5, 4)], float)


def test_revolve_tube_volume():
    d = Document()
    d.features.append(RevolveFeature(name="tube", outer=_tube_profile()))
    assert d.result.volume == pytest.approx(math.pi * 75 * 4, rel=2e-3)


def test_revolve_partial_angle():
    d = Document()
    d.features.append(RevolveFeature(name="wedge", outer=_tube_profile(),
                                     angle=90))
    assert d.result.volume == pytest.approx(math.pi * 75 * 4 / 4, rel=2e-3)


def test_revolve_axis_v_world_direction():
    """On XZ the sketch v-axis IS world Z: classic upright lathe."""
    d = Document()
    d.features.append(RevolveFeature(name="vase", outer=_tube_profile(),
                                     plane="XZ"))
    bb = d.result.bounding_box
    assert np.allclose(bb[0], [-10, -10, 0], atol=0.05)
    assert np.allclose(bb[1], [10, 10, 4], atol=0.05)


def test_revolve_negative_profile_mirrors():
    d = Document()
    neg = np.array([(-10, 0), (-5, 0), (-5, 4), (-10, 4)], float)
    d.features.append(RevolveFeature(name="mirr", outer=neg, plane="XZ"))
    assert d.result.volume == pytest.approx(math.pi * 75 * 4, rel=2e-3)


def test_revolve_crossing_axis_raises():
    d = Document()
    cross = np.array([(-5, 0), (5, 0), (5, 4), (-5, 4)], float)
    d.features.append(RevolveFeature(name="bad", outer=cross, plane="XZ"))
    with pytest.raises(ValueError, match="crosses"):
        d.recompute()


def test_revolve_with_hole_and_cut_op():
    outer = np.array([(3, 0), (12, 0), (12, 10), (3, 10)], float)
    hole = np.array([(8, 4), (10, 4), (10, 8), (8, 8)], float)
    d = Document()
    d.features.append(RevolveFeature(name="full", outer=outer,
                                     holes=[hole], plane="XZ"))
    v_full = d.result.volume                       # spool ring, r<=12, z<=10
    d2 = Document()                                # block fully contains it
    d2.features.append(ExtrudeFeature(
        name="block", outer=[(-20, -20), (20, -20), (20, 20), (-20, 20)],
        height=30))
    d2.features.append(RevolveFeature(name="bore", outer=outer,
                                      holes=[hole], plane="XZ",
                                      op="subtract"))
    assert d2.result.volume == pytest.approx(40 * 40 * 30 - v_full,
                                             rel=5e-3)


def test_revolve_save_roundtrip(tmp_path):
    from tracer.core import io
    d = Document()
    d.features.append(RevolveFeature(name="r", outer=_tube_profile(),
                                     plane="XZ", angle=200))
    p = tmp_path / "rev.tracer"
    io.save_document(d, p)
    d2 = io.load_document(p)
    f = d2.features[0]
    assert isinstance(f, RevolveFeature) and f.angle == 200
    assert d2.result.volume == pytest.approx(math.pi * 75 * 4 * 200 / 360,
                                             rel=2e-3)


# ---- UI --------------------------------------------------------------------
def test_shift_r_revolves_sketch(win, qapp):
    win.new_document()
    win.action_new_sketch("XZ")
    cv = win.sketch
    _drag_rect(cv, 5, 0, 10, 4)
    QTest.keyPress(cv, Qt.Key_R, Qt.ShiftModifier)
    qapp.processEvents()
    assert win.stack.currentWidget() is win.viewport
    assert len(win.doc.features) == 1
    f = win.doc.features[0]
    assert isinstance(f, RevolveFeature)
    assert f.angle == 360.0
    assert win.doc.result.volume == pytest.approx(math.pi * 75 * 4, rel=2e-2)
    # associative payload survived: chip is re-editable
    assert f.sketch and f.sid is not None


def test_revolve_reedit_keeps_type(win, qapp):
    win.new_document()
    win.action_new_sketch("XZ")
    _drag_rect(win.sketch, 5, 0, 10, 4)
    QTest.keyPress(win.sketch, Qt.Key_R, Qt.ShiftModifier)
    qapp.processEvents()
    sid = win.doc.features[0].sid
    win.edit_sketch(win.doc.features[0])
    assert win.stack.currentWidget() is win._sketch_page
    # stretch the profile: add a second rect higher (v to 8)
    QTest.keyPress(win.sketch, Qt.Key_Escape)      # select mode
    _drag_rect(win.sketch, 11, 0, 13, 8)
    QTest.keyPress(win.sketch, Qt.Key_X)           # plain finish -> UPDATE
    qapp.processEvents()
    assert win.doc.features[0].sid == sid
    assert isinstance(win.doc.features[0], RevolveFeature)
    # both regions revolve now: tube r5-10 h4 + tube r11-13 h8
    assert len(win.doc.features) == 2
    v = win.doc.result.volume
    assert v == pytest.approx(math.pi * (75 * 4 + 48 * 8), abs=200)


def test_set_angle_updates_solid(win, qapp, monkeypatch):
    win.new_document()
    win.action_new_sketch("XZ")
    _drag_rect(win.sketch, 5, 0, 10, 4)
    QTest.keyPress(win.sketch, Qt.Key_R, Qt.ShiftModifier)
    qapp.processEvents()
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (90.0, True)))
    win._set_angle(win.doc.features[0])
    assert win.doc.features[0].angle == 90
    assert win.doc.result.volume == pytest.approx(
        math.pi * 75 * 4 / 4, rel=2e-2)


def test_crossing_profile_warns_and_aborts(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(1)))
    win.new_document()
    win.action_new_sketch("XZ")
    _drag_rect(win.sketch, -5, 0, 5, 4)            # straddles v-axis
    QTest.keyPress(win.sketch, Qt.Key_R, Qt.ShiftModifier)
    qapp.processEvents()
    assert len(warned) == 1
    assert len(win.doc.features) == 0              # nothing created
    assert win.stack.currentWidget() is win._sketch_page  # still editing


def test_browser_shows_revolve_glyph(win, qapp):
    win.new_document()
    win.action_new_sketch("XZ")
    _drag_rect(win.sketch, 5, 0, 10, 4)
    QTest.keyPress(win.sketch, Qt.Key_R, Qt.ShiftModifier)
    qapp.processEvents()
    win.rail.tree.reload()
    assert any("\u21bb" in t for t in tree_texts(win))   # ↻ revolve node
