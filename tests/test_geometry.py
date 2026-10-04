"""Kernel correctness: volumes vs analytic truth, watertightness, booleans."""
import math

import numpy as np
import pytest

from tracer.core.geometry import Solid, circle_contour


def approx_ratio(actual, truth, rel=2e-3):
    assert abs(actual - truth) <= abs(truth) * rel, f"{actual} vs {truth}"


def test_box_exact():
    b = Solid.box(10, 20, 30)
    assert b.volume == pytest.approx(6000, rel=1e-9)
    assert b.to_trimesh().is_watertight
    lo, hi = b.bounding_box
    np.testing.assert_allclose(lo, [0, 0, 0], atol=1e-6)
    np.testing.assert_allclose(hi, [10, 20, 30], atol=1e-6)


def test_cylinder_volume_and_watertight():
    c = Solid.cylinder(5, 12)
    approx_ratio(c.volume, math.pi * 25 * 12)
    assert c.to_trimesh().is_watertight


def test_plate_with_hole():
    outer = np.array([[0, 0], [40, 0], [40, 20], [0, 20]], float)
    holes = [circle_contour(2, (5, 5)), circle_contour(2, (35, 5)),
             circle_contour(2, (5, 15)), circle_contour(2, (35, 15))]
    p = Solid.extrude(outer, holes, 3)
    truth = (40 * 20 - 4 * math.pi * 4) * 3
    approx_ratio(p.volume, truth)
    assert p.to_trimesh().is_watertight


def test_boolean_union_subtract_volumes():
    big = Solid.box(10, 10, 10)
    small = Solid.box(4, 4, 20).translated((3, 3, -5))
    u = big.union(small)
    # overlap = 4*4*10 = 160 ; union = 1000 + 320 - 160
    approx_ratio(u.volume, 1000 + 320 - 160)
    assert u.to_trimesh().is_watertight
    d = big.subtract(small)
    approx_ratio(d.volume, 1000 - 160)
    assert d.to_trimesh().is_watertight
    inter = big.intersect(small)
    approx_ratio(inter.volume, 160)


def test_touching_solids_union_stays_watertight():
    a = Solid.box(10, 10, 10)
    b = Solid.box(10, 10, 10).translated((10, 0, 0))  # coincident face
    u = a.union(b)
    approx_ratio(u.volume, 2000)
    assert u.to_trimesh().is_watertight


def test_from_mesh_roundtrip():
    mesh = Solid.cylinder(3, 7).to_trimesh()
    s = Solid.from_mesh(mesh.vertices, mesh.faces)
    approx_ratio(s.volume, mesh.volume)
