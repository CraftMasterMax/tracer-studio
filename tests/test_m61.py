"""M61 — Change Parameters: edit the numbers a feature is built from.

Fusion's Modify ▸ Change Parameters, cloned: right-click a feature
(or Modify menu) and a dialog of its real levers opens in DOCUMENT
measures; OK re-runs the kernel and the body follows.  Box dims, move
vectors, rotate axis+angle all retarget the solid exactly; cancel
changes nothing; captured geometry (loft/sweep) honestly has no plain
numbers; and an inch document takes inch inputs.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from conftest import script_cmd, script_cmd_cancel                     # noqa: E402
from tracer.core.document import (LoftFeature, MoveFeature,            # noqa: E402
                                  PrimitiveFeature, RotateFeature,
                                  SweepFeature)


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
        r.ctx.release()
    except Exception:
        raise


def _block(win, qapp, dims=(40.0, 20.0, 10.0)):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="block", kind="box",
                                 dims={"dx": dims[0], "dy": dims[1],
                                       "dz": dims[2]}))
    win.recompute()
    qapp.processEvents()
    return win.doc.features[0]


def _dims(solid):
    lo, hi = solid.bounding_box
    return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])


def test_modify_menu_offers_change_parameters(win):
    menus = {a.text().replace("&", ""): a.menu()
             for a in win.menuBar().actions()}
    assert "Change Parameters…" in [
        x.text().replace("&", "") for x in menus["Modify"].actions()]


def test_box_dimensions_change_rebuilds(win, qapp, monkeypatch):
    feat = _block(win, qapp)
    assert win.doc.result.volume == pytest.approx(8000, rel=1e-6)
    script_cmd(monkeypatch, {"dx": 60.0, "dy": 20.0, "dz": 10.0})
    win.action_change_params(feat)
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(12000, rel=1e-3)
    assert feat.dims["dx"] == pytest.approx(60.0)
    assert "Parameters changed" in win.status.currentMessage()


def test_move_vector_change_slides_body(win, qapp, monkeypatch):
    _block(win, qapp, (20, 20, 20))
    mv = MoveFeature(name="Move", vec=(10.0, 0.0, 0.0))
    win.doc.add(mv)
    win.recompute()
    qapp.processEvents()
    script_cmd(monkeypatch, {"v0": 0.0, "v1": 0.0, "v2": 5.0,
                             "copy": False})
    win.action_change_params(mv)
    qapp.processEvents()
    lo, _ = win.doc.result.bounding_box
    assert float(lo[2]) == pytest.approx(5.0, abs=1e-6)
    assert float(lo[0]) == pytest.approx(0.0, abs=1e-6)


def test_rotate_axis_and_angle_change(win, qapp, monkeypatch):
    _block(win, qapp)
    rt = RotateFeature(name="Rotate", center=(20, 10, 5),
                       axis=(0, 0, 1), angle_deg=90.0)
    win.doc.add(rt)
    win.recompute()
    qapp.processEvents()
    d = _dims(win.doc.result)
    assert d[0] == pytest.approx(20, abs=0.5)      # was Z-spin: 20x40
    assert d[1] == pytest.approx(40, abs=0.5)
    script_cmd(monkeypatch, {"axis": "Y", "angle": 90.0, "copy": False})
    win.action_change_params(rt)
    qapp.processEvents()
    d = _dims(win.doc.result)
    assert d[0] == pytest.approx(10, abs=0.5)      # Y-spin: x<->z
    assert d[2] == pytest.approx(40, abs=0.5)
    assert np.allclose(rt.axis, (0, 1, 0))


def test_cancel_changes_nothing(win, qapp, monkeypatch):
    feat = _block(win, qapp)
    script_cmd_cancel(monkeypatch)
    win.action_change_params(feat)
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(8000, rel=1e-6)
    assert feat.dims["dx"] == pytest.approx(40.0)


def test_captured_geometry_has_no_numbers(win, qapp):
    _block(win, qapp)
    sweep = SweepFeature(name="s", path=[[0, 0], [10, 0]], radius=2.0)
    loft = LoftFeature(name="l", sections=[{"outer": [(0, 0), (1, 0),
                                                       (1, 1), (0, 1)]},
                                           {"outer": [(0, 0), (2, 0),
                                                       (2, 2), (0, 2)]}])
    assert win._feature_params(sweep) == []
    assert win._feature_params(loft) == []
    assert set(f["key"] for f in win._feature_params(
        win.doc.features[0])) == {"dx", "dy", "dz"}


def test_inch_document_takes_inch_numbers(win, qapp, monkeypatch):
    feat = _block(win, qapp)
    win.doc.units = "inch"
    win._apply_units()
    script_cmd(monkeypatch, {"dx": 2.0, "dy": 1.0, "dz": 0.5})
    win.action_change_params(feat)
    qapp.processEvents()
    # 2 x 1 x 0.5 in = 1 in^3 = 16387.064 mm^3, stored in millimetres
    assert win.doc.result.volume == pytest.approx(16387.064, rel=1e-3)
    assert feat.dims["dx"] == pytest.approx(50.8, abs=1e-6)
    win.doc.units = "mm"
    win._apply_units()
