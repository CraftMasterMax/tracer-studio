import math

import numpy as np
import pytest

from forma.core.document import Document, ExtrudeFeature, PrimitiveFeature
from forma.ui.mainwindow import demo_document


def test_demo_doc_volume():
    doc = demo_document()
    solid = doc.recompute()
    plate = 60 * 40 * 8 - 4 * math.pi * 1.6 ** 2 * 8
    boss = math.pi * 7 ** 2 * 12          # sits on plate, z 8..20
    bore = math.pi * 3 ** 2 * 20          # through plate + boss column
    truth = plate + boss - bore
    assert solid.volume == pytest.approx(truth, rel=5e-3)


def test_recompute_lazy_cache():
    doc = demo_document()
    a = doc.result
    b = doc.result
    assert a is b
    doc.add_cylinder("extra", radius=2, height=1, center=(0, 0))
    c = doc.result
    assert c.volume > a.volume


def test_first_feature_subtract_raises():
    doc = Document("bad")
    doc.features.append(PrimitiveFeature(name="x", op="subtract", kind="box",
                                         dims={"dx": 1, "dy": 1, "dz": 1}))
    with pytest.raises(ValueError):
        doc.recompute()


def test_serialize_roundtrip(tmp_path):
    doc = demo_document()
    data = doc.to_dict()
    doc2 = Document.from_dict(data)
    assert [f.name for f in doc2.features] == [f.name for f in doc.features]
    v1, v2 = doc.recompute().volume, doc2.recompute().volume
    assert v1 == pytest.approx(v2)
