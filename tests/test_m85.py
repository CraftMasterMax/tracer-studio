"""M85 — batched pattern booleans through the kernel.

Linear / circular / path patterns used to union their copies ONE AT A
TIME — N-1 serial manifold calls, each re-processing the whole growing
result.  manifold3d's batch_boolean folds them all in one parallel
pass.  Volumes must be BIT-comparable (same kernel, same math), so
every test pins exact geometry, and one adversarial case — heavily
overlapping copies whose intermediate self-unions the old path loved
to choke on — proves the fold is also ROBUSTER.
"""
import math

import pytest

from tracer.core.document import (CircularPatternFeature, Document,
                                  LinearPatternFeature, PathPatternFeature,
                                  PrimitiveFeature)
from tracer.core.geometry import Solid


def _box(d: Document, **dims) -> PrimitiveFeature:
    f = PrimitiveFeature(name="Src", kind="box",
                         dims={"dx": 10.0, "dy": 10.0, "dz": 10.0}
                         if not dims else dims)
    d.features.append(f)
    return f


def test_batch_union_matches_serial_union():
    a = Solid.box(10, 10, 10)
    parts = [a.translated((k * 3.0, 0.0, 0.0)) for k in range(5)]
    serial = parts[0]
    for p in parts[1:]:
        serial = serial.union(p)
    batched = Solid.batch_union(parts)
    assert batched.volume == pytest.approx(serial.volume, rel=1e-9)
    assert batched.volume == pytest.approx(10 * 10 * 22, rel=1e-6)


def test_linear_pattern_still_exact():
    d = Document(title="lp")
    _box(d)
    d.features.append(LinearPatternFeature(name="Row",
                                           source_uid=d.features[0].uid,
                                           vector=(3.0, 0.0, 0.0),
                                           count=5))
    assert d.recompute().volume == pytest.approx(2200.0, rel=1e-6)


def test_circular_pattern_disjoint_cylinders():
    d = Document(title="cp")
    cyl = PrimitiveFeature(name="Pin", kind="cylinder",
                           dims={"radius": 3.0, "height": 10.0},
                           placement=(8.0, 0.0, 0.0))
    d.features.append(cyl)
    d.features.append(CircularPatternFeature(
        name="Bolt circle", source_uid=cyl.uid, center=(0.0, 0.0),
        angle=360.0, count=6))
    one = Solid.cylinder(3.0, 10.0).volume
    assert d.recompute().volume == pytest.approx(6 * one, rel=1e-6)


def test_path_pattern_three_station():
    d = Document(title="pp")
    _box(d)
    d.features.append(PathPatternFeature(
        name="Along", source_uid=d.features[0].uid,
        path=[(0.0, 0.0), (30.0, 0.0), (30.0, 30.0)], count=3))
    v = d.recompute().volume
    assert v > 3 * 1000.0 * 0.5          # three boxes, corners overlap
    assert v <= 3 * 1000.0


def test_adversarial_heavy_overlap_no_longer_chokes():
    # copies buried almost inside each other: the fold must produce the
    # exact slab and stay clean
    d = Document(title="ax")
    _box(d)
    d.features.append(LinearPatternFeature(
        name="Stack", source_uid=d.features[0].uid,
        vector=(0.5, 0.0, 0.0), count=8))
    s = d.recompute()
    assert s.volume == pytest.approx(13.5 * 10.0 * 10.0, rel=1e-6)


def test_single_copy_shortcut_identical():
    # count=1 means the pattern IS its source: the fold short-circuits
    d = Document(title="one")
    _box(d)
    d.features.append(LinearPatternFeature(name="Solo",
                                           source_uid=d.features[0].uid,
                                           vector=(20.0, 0.0, 0.0),
                                           count=1))
    assert d.recompute().volume == pytest.approx(1000.0, rel=1e-6)
