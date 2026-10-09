"""M105 — exports speak per body.

M104 made bodies real inside the app but the file still saw one fused
lump: STL/OBJ/3MF all went through ``doc.result`` (the boolean union),
so a bracket modelled as Body 1 + a handle as Body 2 printed as a single
merged mesh with no way to select the handle in the slicer.

Here the part exports as its BODIES, each its own object:

* 3MF / OBJ keep every body as a separate, NAMED object — a slicer
  opens "Body 1", "Body 2"; CAD reads distinct solids;
* STL / PLY (single-container formats) get all the shells concatenated,
  so a disjoint two-body part still lands as two watertight islands;
* ONE body writes exactly the mesh it always did — the single-body file
  is byte-for-byte what Tracer produced before per-body export;
* the whole part goes regardless of the viewport bulb (a hidden row is a
  view fact, not a decision to lose geometry from the file).

Honest scope: STEP still exports the fused part — a named STEP compound
needs the compiled OCCT bridge to accept many solids at once, which is a
later increment (and untestable where OpenCascade isn't installed).
"""
import math

import pytest

pytest.importorskip("PySide6")

import trimesh                                          # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from tracer.core import io as fio                        # noqa: E402
from tracer.core.document import (Document,              # noqa: E402
                                  PrimitiveFeature)


def _box(d=10.0, at=(0.0, 0.0, 0.0)):
    return PrimitiveFeature(name="b", kind="box",
                            dims={"dx": d, "dy": d, "dz": d}, placement=at)


def _two_bodies():
    doc = Document("mb")
    doc.add(_box(10.0))                                  # Body 1 (1000)
    doc.add_body()                                       # Body 2 active
    doc.add(_box(6.0, (30.0, 0.0, 0.0)))                 # Body 2 (216)
    return doc


# ---------------------------------------------------------------- core

def test_export_solids_lists_bodies_in_order():
    doc = _two_bodies()
    got = doc.export_solids()
    assert [name for name, _ in got] == ["Body 1", "Body 2"]
    vols = {name: s.volume for name, s in got}
    assert vols["Body 1"] == pytest.approx(1000.0)
    assert vols["Body 2"] == pytest.approx(216.0)


def test_export_solids_skips_an_empty_body():
    doc = _two_bodies()
    doc.add_body()                                    # Body 3, empty inside
    assert [n for n, _ in doc.export_solids()] == ["Body 1", "Body 2"]


def test_visibility_does_not_gate_export():
    doc = _two_bodies()
    doc.set_body_visible("Body 2", False)                # hide in the viewport
    assert [n for n, _ in doc.export_solids()] == ["Body 1", "Body 2"]


def test_three_mf_keeps_each_body_as_a_named_object(tmp_path):
    doc = _two_bodies()
    path = fio.export_solids(doc.export_solids(), tmp_path / "two.3mf")
    scene = trimesh.load(str(path), process=False)
    assert len(scene.geometry) == 2
    assert set(scene.geometry) == {"Body 1", "Body 2"}
    by_name = {n: m.volume for n, m in scene.geometry.items()}
    assert by_name["Body 1"] == pytest.approx(1000.0, rel=0.02)
    assert by_name["Body 2"] == pytest.approx(216.0, rel=0.02)


def test_obj_groups_each_body(tmp_path):
    doc = _two_bodies()
    path = fio.export_solids(doc.export_solids(), tmp_path / "two.obj")
    text = path.read_text()
    groups = [ln for ln in text.splitlines() if ln.startswith("o ")]
    assert "o Body 1" in groups and "o Body 2" in groups


def test_stl_carries_both_shells(tmp_path):
    doc = _two_bodies()
    path = fio.export_solids(doc.export_solids(), tmp_path / "two.stl")
    mesh = trimesh.load(str(path), process=True, force="mesh")
    comps = mesh.split(only_watertight=False)
    assert len(comps) == 2
    assert sum(c.volume for c in comps) == pytest.approx(1216.0, rel=0.02)


def test_single_body_is_one_plain_object(tmp_path):
    doc = Document("one")
    doc.add(_box(10.0))
    assert len(doc.export_solids()) == 1
    path = fio.export_solids(doc.export_solids(), tmp_path / "one.3mf")
    scene = trimesh.load(str(path), process=False)
    assert len(scene.geometry) == 1
    assert next(iter(scene.geometry.values())).volume == pytest.approx(
        1000.0, rel=0.02)


def test_export_solids_rejects_unknown_ext_and_nothing(tmp_path):
    doc = _two_bodies()
    with pytest.raises(ValueError, match="unsupported export format"):
        fio.export_solids(doc.export_solids(), tmp_path / "x.step")
    empty = Document("empty")
    with pytest.raises(ValueError, match="nothing to export"):
        fio.export_solids(empty.export_solids(), tmp_path / "x.stl")


def test_export_mesh_still_writes_a_single_solid(tmp_path):
    doc = _two_bodies()
    solid = doc.result                                   # the fused part
    path = fio.export_mesh(solid, tmp_path / "u.3mf")
    scene = trimesh.load(str(path), process=False)
    assert len(scene.geometry) >= 1
    assert sum(g.volume for g in scene.geometry.values()) == pytest.approx(
        1216.0, rel=0.02)


# ------------------------------------------------------------------ UI

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
        except Exception as e:
            pytest.skip(f"no headless GL available: {e}")
        w = MainWindow(renderer=r)
        w.resize(1000, 700)
        w.show()
        qapp.processEvents()
        yield w
        w._unsaved = False
        w._discard_guard = lambda: True
        w.close()
        r.close()
    except Exception:
        raise


def test_action_export_writes_per_body(qapp, win, tmp_path, monkeypatch):
    win.new_document()
    win._discard_guard = lambda: True
    win.doc.add(_box(10.0))
    win.action_new_body()
    win.doc.add(_box(6.0, (30.0, 0.0, 0.0)))
    win.recompute()
    out = str(tmp_path / "exported.3mf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (out, ""))
    win.action_export(".3mf")
    qapp.processEvents()
    scene = trimesh.load(out, process=False)
    assert set(scene.geometry) == {"Body 1", "Body 2"}
