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


# ---- display sanitiser (M21) ---------------------------------------------
def test_render_arrays_keep_clean_primitives_intact():
    """The needle filter must never eat legitimate geometry."""
    for s in (Solid.box(20, 20, 10), Solid.cylinder(5, 12, center=(2, 3))):
        v, n, f = s.to_render_arrays()
        assert len(f) == len(s.to_trimesh().faces)
        assert v.dtype == np.float32 and f.dtype == np.int32
        np.testing.assert_allclose(np.linalg.norm(n, axis=1), 1.0, atol=1e-3)


def test_render_arrays_smooth_boolean_welds():
    """Rim-fillet booleans leave zero-area needles and vertex duplicates a
    few microns apart on the boss wall; unfiltered they hatch the shading
    (smooth normals tilt >25 deg off the surface). The display arrays drop
    the garbage and weld the duplicates; the mesh data stays watertight.
    """
    import trimesh

    from tracer.core.rimfillet import rim_fillet
    plate = (Solid.box(60, 40, 8)
             .union(Solid.cylinder(7, 12, center=(30, 20)).translated((0, 0, 8))))
    out, n_rims = rim_fillet(plate, 2.0)
    assert n_rims >= 2
    assert out.to_trimesh().is_watertight

    v, nrm, f = out.to_render_arrays()
    assert len(f) < len(out.to_trimesh().faces)     # needles removed
    tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
    tc = np.asarray(tm.triangles_center)
    rad = np.hypot(tc[:, 0] - 30, tc[:, 1] - 20)
    wt = (np.abs(rad - 7) < 0.05) & (tc[:, 2] > 11) & (tc[:, 2] < 17)
    assert wt.sum() > 200                            # wall still covered
    ideal = np.stack([(tc[wt, 0] - 30) / rad[wt],
                      (tc[wt, 1] - 20) / rad[wt],
                      np.zeros(int(wt.sum()))], 1)
    vn = np.asarray(tm.vertex_normals)
    dev = np.degrees(np.arccos(np.clip(
        (vn[f[wt].reshape(-1)] * np.repeat(ideal, 3, 0)).sum(1), -1, 1)))
    assert np.percentile(dev, 99) < 10.0             # was >25 deg (stripes)
