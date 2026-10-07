"""M116 — the topology classifier reads primitives EXACTLY.

Box = 6 faces / 12 edges / 8 corners; cylinder = 2 planes + 1 tube,
two circular loops, no corners; smooth bodies (sphere, torus) leave
with one group and no edges. The cone is the regression: the kernel's
apex slivers carry float-noise normals, and a naive fold test shreds
its side into hundreds of "faces".
"""
import numpy as np
import pytest

from tracer.core.geometry import Solid


def _box():
    return Solid.box(40.0, 20.0, 10.0).topology()


def test_box_is_six_twelve_eight():
    t = _box()
    assert t.n_groups == 6
    assert len(t.edges) == 12
    assert len(t.corners) == 8
    assert t.closed_loops() == []
    assert t.flat_groups() == [0, 1, 2, 3, 4, 5]
    lengths = np.array([e["length"] for e in t.edges])
    for dim, count in ((40.0, 4), (20.0, 4), (10.0, 4)):
        assert np.isclose(lengths, dim).sum() == count


def test_box_group_normals_are_the_six_axes():
    t = _box()
    ns = sorted(tuple(np.round(g["normal"], 6)) for g in t.groups)
    assert ns == sorted([(0, 0, -1.0), (0, 0, 1.0), (0, -1.0, 0),
                         (0, 1.0, 0), (-1.0, 0, 0), (1.0, 0, 0)])


def test_cylinder_two_planes_one_tube_two_loops():
    t = Solid.cylinder(5.0, 12.0).topology()
    assert t.n_groups == 3
    loops = t.closed_loops()
    assert len(loops) == 2 and len(t.corners) == 0
    assert len(t.flat_groups()) == 2                  # the two caps
    rim = 2.0 * np.pi * 5.0
    for e in loops:
        assert e["length"] == pytest.approx(rim, rel=0.01)
    tube = [g for g in t.groups if not g["planar"]]
    assert len(tube) == 1
    assert tube[0]["area"] == pytest.approx(rim * 12.0, rel=0.01)


def test_cone_side_survives_apex_slivers():
    t = Solid.cone(6.0, 0.0, 10.0).topology()   # the 256-group trap
    assert t.n_groups == 2                      # base + one smooth side
    assert len(t.closed_loops()) == 1
    assert len(t.corners) == 0
    fr = Solid.cone(6.0, 2.0, 10.0).topology()  # frustum
    assert fr.n_groups == 3 and len(fr.closed_loops()) == 2


def test_smooth_bodies_have_nothing_to_report():
    for solid in (Solid.sphere(5.0), Solid.torus(10.0, 3.0)):
        t = solid.topology()
        assert t.n_groups == 1 and t.edges == [] and len(t.corners) == 0


def test_step_block_is_a_consistent_polyhedron():
    big = Solid.box(40.0, 20.0, 5.0)
    boss = Solid.box(20.0, 20.0, 10.0).translated([10.0, 0.0, 5.0])
    t = big.union(boss).topology()
    assert t.n_groups == 10              # coplanar boss walls merged
    assert len(t.edges) == 24
    assert len(t.corners) == 16
    assert 16 - 24 + 10 == 2             # Euler holds: no lost seams


def test_every_crease_pair_resolves_to_one_semantic_edge():
    solid = Solid.cylinder(4.0, 9.0)
    t = solid.topology()
    tm = solid.to_trimesh()
    seen = set()
    for (f1, f2) in tm.face_adjacency:
        e = t.edge_of_faces(int(f1), int(f2))
        if e is not None:
            seen.add(id(e))
    assert len(seen) == 2                # exactly the two rim loops
    # a SMOOTH pair (two side facets) is not an edge at all
    side_pair = next((f1, f2) for (f1, f2) in tm.face_adjacency
                     if t.edge_of_faces(int(f1), int(f2)) is None)
    assert t.group_of_face(side_pair[0]) == t.group_of_face(side_pair[1])


def test_cache_is_per_solid_and_stable():
    s = Solid.box(5.0, 5.0, 5.0)
    assert s.topology() is s.topology()
    moved = s.translated([50.0, 0.0, 0.0])
    assert moved.topology() is not s.topology()
    assert moved.topology().n_groups == 6   # geometry moved, shape did not


def test_group_areas_sum_to_surface_area():
    s = Solid.cone(5.0, 1.5, 8.0)
    t = s.topology()
    assert sum(g["area"] for g in t.groups) == pytest.approx(
        s.surface_area, rel=1e-6)
