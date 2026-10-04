import numpy as np
import pytest

from tracer.core import io as fio
from tracer.core.document import Document
from tracer.core.geometry import Solid


@pytest.fixture
def solid():
    return Solid.box(12, 9, 4)


@pytest.mark.parametrize("ext", [".stl", ".obj", ".3mf", ".ply"])
def test_export_import_roundtrip(tmp_path, solid, ext):
    path = tmp_path / f"part{ext}"
    fio.export_mesh(solid, path)
    assert path.stat().st_size > 0
    back = fio.import_mesh(path)
    assert back.volume == pytest.approx(solid.volume, rel=1e-3)
    assert back.to_trimesh().is_watertight


def test_export_rejects_unknown_ext(tmp_path, solid):
    with pytest.raises(ValueError):
        fio.export_mesh(solid, tmp_path / "x.step")  # STEP comes with the OCCT bridge


def test_document_save_load(tmp_path):
    from tracer.ui.mainwindow import demo_document
    doc = demo_document()
    p = tmp_path / "model.tracer"
    fio.save_document(doc, p)
    doc2 = fio.load_document(p)
    assert doc2.title == doc.title
    assert doc2.recompute().volume == pytest.approx(doc.recompute().volume)
