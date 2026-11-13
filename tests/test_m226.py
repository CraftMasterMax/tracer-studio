"""M201 R37 - a BREAKOUT SECTION: a closed profile, material sunk to depth.

[Create breakout section views, verbatim] a breakout section "is part of an
existing drawing view, that is used to remove material to a specified depth
in order to expose inner details of a design" / "A closed profile defines the
breakout section" / "The depth is set to half of your design's depth by
default, but you can type in any depth value."  [reference dialog, verbatim]
the depth is measured "from the front of the design".  So the honest cut lives
in 3D, never on paper: breakout_solid() extrudes the drawn CLOSED LOOP (in the
parent's model-page (u,v) coords, the same dot-with-(X,Y) convention every
chain already speaks) into a prism and SUBTRACTS it - the detail cookie's
sight-basis transform (R36) with intersect swapped for subtract and a finite
sunk depth for all-depth. These gates are CPU-only (manifold + projection):
they prove the half-depth default formula, the strict LOCALITY of the cut,
that it re-derives live, the iso parent, and every page-printed refusal.
"""
import numpy as np
import pytest

from tracer.core import drawing
from tracer.core.document import Document, HoleFeature, PrimitiveFeature


@pytest.fixture(scope="module")
def slab():
    """A plain 40 x 30 x 6 box - a KNOWN volume and surface so the exact
    cubic millimetres a breakout removes are provable, not eyeballed."""
    d = Document()
    d.add(PrimitiveFeature(name="slab", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    d.recompute()
    return d


@pytest.fixture(scope="module")
def plate():
    """R34/R36's proven stage: 40x30x6, a through bore and a blind pocket -
    so a breakout over the bore shows the bore still stands uncut outside
    its own footprint."""
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    d.add(HoleFeature(name="bore", op="subtract", center=(20, 15, 6),
                      normal=(0, 0, -1), radius=5.0, depth=6,
                      cut_length=6, through=True))
    d.recompute()
    return d


def _sight_extent(solid, view):
    d, _, _ = drawing._basis(view)
    lo, hi = np.asarray(solid.bounding_box, float)
    cs = np.array([[a, b, c] for a in (lo[0], hi[0])
                   for b in (lo[1], hi[1]) for c in (lo[2], hi[2])])
    s = cs @ d
    return float(s.max()), float(s.min())      # front, back


# a rectangle centred on the bore/slab middle, wholly inside the material,
# 12 x 8 = 96 mm^2 footprint
RECT = [(14.0, 11.0), (26.0, 11.0), (26.0, 19.0), (14.0, 19.0)]


def test_a_half_depth_is_the_page_default_formula(slab):
    front, back = _sight_extent(slab.result, "top")
    cut, info = drawing.breakout_solid(slab.result, "top", RECT)   # no depth
    assert info["default"] is True
    assert info["depth_used"] == pytest.approx((front - back) / 2.0, abs=1e-9)
    assert info["front"] == pytest.approx(front, abs=1e-9)
    assert info["floor"] == pytest.approx(front - (front - back) / 2.0,
                                          abs=1e-9)


def test_b_explicit_depth_removes_exactly_the_prism(slab):
    v0 = slab.result.volume
    cut, info = drawing.breakout_solid(slab.result, "top", RECT, depth=5.0)
    assert info["depth_used"] == pytest.approx(5.0, abs=1e-9)
    area = 12.0 * 8.0                       # the 96 mm^2 profile footprint
    # the slab is solid under the whole loop, so exactly area*depth leaves
    assert v0 - cut.volume == pytest.approx(area * 5.0, rel=1e-6)


def test_c_the_cut_is_strictly_local(slab):
    """Everything OUTSIDE the profile keeps its full depth: the surface
    changed (a floor + four walls appeared inside), yet the bounding box -
    the outline the paper still draws - is untouched."""
    cut, info = drawing.breakout_solid(slab.result, "top", RECT, depth=2.0)
    assert cut.volume < slab.result.volume          # material really left
    assert cut.surface_area > slab.result.surface_area  # interior exposed
    a = np.asarray(slab.result.bounding_box, float)
    b = np.asarray(cut.bounding_box, float)
    assert np.allclose(a, b, atol=1e-6)             # strictly local: no leak


def test_d_cut_exposes_real_interior_ink(plate):
    """A breakout over the bore must re-project: the new floor is fresh
    visible geometry, so the cut projects MORE than a zero-area nothing -
    and it stays a live projection, never a stored picture."""
    vis = drawing.project_view(plate.result, "top")
    cut, _ = drawing.breakout_solid(plate.result, "top", RECT, depth=2.0)
    visc = drawing.project_view(cut, "top")
    n0 = sum(len(c) for c in vis)
    n1 = sum(len(c) for c in visc)
    assert n1 != n0                                 # the floor changed the ink
    assert n1 > 0


def test_e_iso_parent_breaks_as_true(slab):
    """The rotated column basis is the one claim axis-aligned code could
    fake - so test where faking dies: a loop centred on the ISO view's
    projection of the slab centre really removes material."""
    d, X, Y = drawing._basis("iso")
    c = np.array([20.0, 15.0, 3.0])
    u0, v0 = float(c @ X), float(c @ Y)
    loop = [(u0 - 4, v0 - 4), (u0 + 4, v0 - 4), (u0 + 4, v0 + 4),
            (u0 - 4, v0 + 4)]
    cut, info = drawing.breakout_solid(slab.result, "iso", loop, depth=2.0)
    assert cut.volume < slab.result.volume
    assert info["depth_used"] == pytest.approx(2.0, abs=1e-9)


def test_f_off_material_loop_removes_nothing_honest(slab):
    """A profile that touches no material is not an error - the caller
    paints the uncut parent, never a lie; volume is byte-identical."""
    far = [(200.0, 200.0), (240.0, 200.0), (240.0, 240.0), (200.0, 240.0)]
    cut, info = drawing.breakout_solid(slab.result, "top", far, depth=2.0)
    assert cut.volume == pytest.approx(slab.result.volume, abs=1e-6)


def test_g_the_cut_re_derives_when_the_model_grows(slab):
    """LIVE, the loop's whole point: grow the design along the sight and a
    DEFAULT-depth breakout's resolved depth follows it (half of the new
    depth), no stored number to go stale."""
    _, i6 = drawing.breakout_solid(slab.result, "top", RECT)     # dz = 6
    big = Document()
    big.add(PrimitiveFeature(name="slab", kind="box",
                             dims={"dx": 40, "dy": 30, "dz": 10}))
    big.recompute()
    _, i10 = drawing.breakout_solid(big.result, "top", RECT)     # dz = 10
    assert i10["depth_used"] == pytest.approx(i6["depth_used"] * 10.0 / 6.0,
                                              abs=1e-9)


def test_h_fixed_depth_hangs_from_the_front(slab):
    """[reference dialog, verbatim] depth is measured "from the front of the
    design": with an EXPLICIT depth the removed thickness stays put while the
    floor plane re-anchors as the front face moves."""
    _, i6 = drawing.breakout_solid(slab.result, "top", RECT, depth=2.0)
    big = Document()
    big.add(PrimitiveFeature(name="slab", kind="box",
                             dims={"dx": 40, "dy": 30, "dz": 10}))
    big.recompute()
    f10, _ = _sight_extent(big.result, "top")
    cut10, i10 = drawing.breakout_solid(big.result, "top", RECT, depth=2.0)
    assert i10["depth_used"] == pytest.approx(2.0, abs=1e-9)   # thickness fixed
    assert i10["floor"] == pytest.approx(f10 - 2.0, abs=1e-9)  # hangs from front


def test_i_a_profile_needs_at_least_three_points(slab):
    for bad in ([(0, 0), (5, 5)], [(0, 0)], []):
        with pytest.raises(ValueError):
            drawing.breakout_solid(slab.result, "top", bad)


def test_j_a_self_crossing_profile_is_refused(slab):
    bowtie = [(10.0, 10.0), (30.0, 10.0), (10.0, 20.0), (30.0, 20.0)]
    with pytest.raises(ValueError):
        drawing.breakout_solid(slab.result, "top", bowtie)


def test_k_a_depth_of_the_whole_design_is_a_section(slab):
    """The page's breakout is a PARTIAL removal; sink to the full sight-depth
    and it is really a section - refuse it by name rather than fake a lid."""
    _, back = _sight_extent(slab.result, "top")
    _, front = _sight_extent(slab.result, "top")
    with pytest.raises(ValueError):
        drawing.breakout_solid(slab.result, "top", RECT, depth=(front - back))
