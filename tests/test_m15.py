"""M15: STEP import/export via the on-demand OpenCascade bridge, and
imported bodies as first-class document features."""
import ctypes
import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (QApplication, QFileDialog,           # noqa: E402
                               QMessageBox)

from tracer.core import io as fio                                    # noqa: E402
from tracer.core import step                                         # noqa: E402
from tracer.core.document import (Document, ImportedFeature,         # noqa: E402
                                 PrimitiveFeature)
from tracer.core.geometry import Solid                               # noqa: E402

need_occt = pytest.mark.skipif(not step.available(),
                               reason="no system OCCT + g++")


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
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


# ---- core: bridge round-trips ----------------------------------------------
@need_occt
def test_backend_reports_occt():
    assert step.available()
    assert "OpenCascade" in step.backend_info()


@need_occt
def test_box_step_roundtrip_exact(tmp_path):
    p = step.export_step(Solid.box(30, 20, 10), tmp_path / "box.step")
    head = p.read_text(errors="replace")[:40]
    assert "ISO-10303-21" in head                       # real STEP file
    back = step.import_step(p)
    assert back.volume == pytest.approx(6000.0, rel=1e-6)


@need_occt
def test_boolean_document_roundtrip(tmp_path):
    d = Document()
    d.add(PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 40, "dy": 40, "dz": 40}))
    d.add(PrimitiveFeature(name="h", kind="cylinder",
                           dims={"radius": 8, "height": 60},
                           placement=(20, 20, -10), op="subtract"))
    solid = d.recompute()
    before = solid.volume
    step.export_step(solid, tmp_path / "doc.step")
    back = step.import_step(tmp_path / "doc.step")
    # faceted B-rep re-tessellates at 0.25 mm sag → small deviation allowed
    assert back.volume == pytest.approx(before, rel=0.01)
    assert back.to_trimesh().is_watertight
    assert back.volume < 64000.0 - 7000.0     # the through-hole survived


@need_occt
def test_step_import_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.step"
    bad.write_text("this is not a STEP file")
    with pytest.raises(RuntimeError):
        step.import_step(bad)


@need_occt
def test_export_open_mesh_fails_gracefully(tmp_path):
    """Non-closed triangle soup must raise a clear error, not crash."""
    lib = step._bridge()
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], float)
    tris = np.array([[0, 1, 2], [1, 3, 2]], np.int32)   # an open book fold
    dp = ctypes.POINTER(ctypes.c_double)
    ip = ctypes.POINTER(ctypes.c_int)
    ok = lib.step_export(os.fsencode(tmp_path / "open.step"),
                         verts.ctypes.data_as(dp), len(verts),
                         tris.ctypes.data_as(ip), len(tris))
    err = lib.occt_last_error().decode()
    assert ok == 0 and "closed" in err


# ---- core: ImportedFeature ---------------------------------------------------
def _box_arrays(dx=5, dy=6, dz=7):
    t = Solid.box(dx, dy, dz).to_trimesh()
    return t.vertices.tolist(), t.faces.astype(int).tolist()


def test_imported_feature_build_and_boolean():
    v, f = _box_arrays()
    d = Document()
    d.add(ImportedFeature(name="part", verts=v, faces=f))
    # 1x1 column, z from -5..15, overlapping the solid only over z 0..7
    d.add(PrimitiveFeature(name="cut", kind="box",
                           dims={"dx": 1, "dy": 1, "dz": 20},
                           placement=(2, 3, -5), op="subtract"))
    solid = d.recompute()
    assert solid.volume == pytest.approx(5 * 6 * 7 - 1 * 1 * 7, rel=1e-6)


def test_imported_feature_placement_and_serialization(tmp_path):
    v, f = _box_arrays()
    d = Document()
    d.add(ImportedFeature(name="shifted", verts=v, faces=f,
                          placement=(100, 0, 0)))
    p = tmp_path / "imp.tracer"
    fio.save_document(d, p)
    d2 = fio.load_document(p)
    feat = d2.features[0]
    assert isinstance(feat, ImportedFeature)
    assert feat.build().bounding_box[0][0] == pytest.approx(100.0)
    assert d2.recompute().volume == pytest.approx(210.0, rel=1e-6)


# ---- UI ----------------------------------------------------------------------
@need_occt
def test_import_step_becomes_feature(win, monkeypatch, tmp_path):
    step.export_step(Solid.box(10, 10, 10), tmp_path / "in.step")
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k:
                                     (str(tmp_path / "in.step"), "")))
    win.new_document()                                   # empty for exact math
    before = len(win.doc.features)
    win.action_import()
    assert len(win.doc.features) == before + 1
    feat = win.doc.features[-1]
    assert isinstance(feat, ImportedFeature) and feat.name == "in"
    assert win.doc.result.volume == pytest.approx(1000.0, rel=1e-6)
    # browser detail must show the true triangle count (12 for a box)
    win.rail.props.show_feature(feat)
    assert "12 triangles" in win.rail.props._body.text()
    # and it survives a save/open cycle
    p = tmp_path / "with_imp.tracer"
    win.file_path = None
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(p), "")))
    win.action_save()
    win.new_document()
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(p), "")))
    win.action_open()
    assert any(isinstance(f, ImportedFeature) for f in win.doc.features)
    assert win.doc.result.volume == pytest.approx(1000.0, rel=1e-6)


def test_import_stl_becomes_feature(win, monkeypatch, tmp_path):
    fio.export_mesh(Solid.box(5, 6, 7), tmp_path / "m.stl")
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k:
                                     (str(tmp_path / "m.stl"), "")))
    win.new_document()                                   # empty doc for math
    base_v = win.doc.result.volume if win.doc.result else 0.0
    win.action_import()
    assert isinstance(win.doc.features[-1], ImportedFeature)
    assert win.doc.result.volume - base_v == pytest.approx(210.0, rel=1e-6)


@need_occt
def test_export_step_action(win, monkeypatch, tmp_path):
    out = tmp_path / "ui.step"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    win.action_export_step()
    assert "ISO-10303-21" in out.read_text(errors="replace")[:40]


def test_export_step_without_occt(monkeypatch, qapp):
    shown = {}
    monkeypatch.setattr(step, "available", lambda: False)
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, title, text, *a, **k:
                     shown.update(title=title, text=text)))
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(900, 600)
    w.show()
    qapp.processEvents()
    w.action_export_step()
    assert shown.get("title") == "STEP export"
    assert "OpenCascade" in shown["text"]
    w._unsaved = False
    w.close()


def test_file_menu_layout(win):
    """New/Open/Save/Save As come first; then Import, mesh export, STEP."""
    m_file = win.menuBar().actions()[0].menu()
    labels = [a.text().replace("&", "").rstrip("…")
              for a in m_file.actions() if not a.isSeparator()]
    order = ["New", "Open", "Save", "Save As", "Import body",
             "Export mesh", "Export STEP (.step)", "Export render (PNG)",
             "Exit"]
    assert labels == order
