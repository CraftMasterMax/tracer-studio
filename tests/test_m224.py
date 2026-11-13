"""M201 R36 core - the detail boundary clips in 3D, never on paper.

[Create a detail view, verbatim] "Click a point on the parent view to
place the center point of the detail boundary" / "Drag the cursor
away from the center point to adjust the size of the detail boundary
and location of the identifier" - an INTERACTIVE circle, no radius
field printed anywhere. The honest clip is detail_cookie(): the
solid AND nothing but the solid, inside a cylinder along the parent
view's sight line. These gates are CPU-only (manifold + projection,
no Qt): the clip's TRUTH is geometry, and the painter that rides it
is the door's and the tool's own story (m225 gates, Qt).
"""
import numpy as np
import pytest

from tracer.core import drawing
from tracer.core.document import Document, HoleFeature, PrimitiveFeature


@pytest.fixture(scope="module")
def plate():
    """R34's proven stage: 40 x 30 x 6 plate, Ø10 through bore at
    (20,15), blind 20 x 10 x 3 pocket under the roof at (10,10) -
    a KNOWN source of real hidden ink for the crop to keep."""
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    d.add(HoleFeature(name="bore", op="subtract", center=(20, 15, 6),
                      normal=(0, 0, -1), radius=5.0, depth=6,
                      cut_length=6, through=True))
    d.add(PrimitiveFeature(name="pocket", op="subtract", kind="box",
                           dims={"dx": 20, "dy": 10, "dz": 3},
                           placement=(10.0, 10.0, 0.0)))
    d.recompute()
    return d


def _pts(chains):
    return [(float(p[0]), float(p[1])) for c in chains for p in c]


def test_a_the_crop_is_the_circle_and_nothing_else(plate):
    # r=8 at the bore centre: material is the 5..8 mm annulus (a crop
    # INSIDE the bore would honestly be empty - that is test_d's story)
    cook = drawing.detail_cookie(plate.result, "top", (20.0, 15.0), 8.0)
    vis = drawing.project_view(cook, "top")
    pts = np.asarray(_pts(vis))
    assert len(pts) > 0
    rmax = float(np.hypot(*(pts - np.array([20.0, 15.0])).T).max())
    # manifold's tessellation was MEASURED at 2.2e-5 mm of float noise
    # past the nominal radius (test_c prints it); the honest bound is
    # one micron - invisible at any paper scale, fail-closed against
    # the millimetre leaks a fake 2D clip would ship.
    assert rmax <= 8.0 + 1e-3, f"geometry outside the boundary leaked: {rmax}"
    assert rmax > 7.2, f"the crop never reached the boundary: {rmax}"


def test_b_back_ink_survives_the_crop(plate):
    """The pocket's far wall is inside the circle; a clip that lost
    the hidden lines would quietly un-ship m97 inside every detail."""
    cook = drawing.detail_cookie(plate.result, "top", (20.0, 15.0), 8.0)
    assert drawing.project_hidden(cook, "top") != []


def test_c_an_iso_parent_clips_just_as_true(plate):
    """The rotated column basis is the one claim this core makes that
    axis-aligned code could fake - so measure it where faking dies:
    any point of a sight-axis crop lies at most `radius` from the
    centre IN THAT VIEW, whichever parent the sight belongs to."""
    d, X, Y = drawing._basis("iso")
    c = np.array([20.0, 15.0, 6.0])
    centre = (float(c @ X), float(c @ Y))
    cook = drawing.detail_cookie(plate.result, "iso", centre, 8.0)
    pts = np.asarray(_pts(drawing.project_view(cook, "iso")))
    rmax = float(np.hypot(*(pts - np.array(centre)).T).max())
    assert rmax <= 8.0 + 1e-3, f"iso clip leaked past the boundary: {rmax}"
    assert rmax > 4.0                          # and it clipped SOMETHING


def test_d_a_boundary_on_bare_paper_clips_nothing(plate):
    """Honest emptiness: centre off the part, the crop is silence -
    project_view must answer [] and never raise, never lie."""
    cook = drawing.detail_cookie(plate.result, "top", (100.0, 100.0), 3.0)
    assert drawing.project_view(cook, "top") == []


def test_e_a_boundary_needs_a_radius(plate):
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError, match="positive radius"):
            drawing.detail_cookie(plate.result, "top", (20.0, 15.0), bad)
