"""M197: the Draft tool.

[SLD-REF-DRAFT, verbatim] "The Draft tool applies a fixed plane or
parting line draft angle to rotate planar faces on a solid body."
Rung 1 cuts the page's FIXED PLANE type on straight vertical walls:
a cylinder on its axis or an axis-aligned box standing on the plane.
Every wall rotates about the line where it meets the fixed plane, so
the free end grows (positive angle) or shrinks (negative) by
height x tan(angle) - the house taper's sign law kept.

The laws these gates pin:
- The lean is MEASURED at the rings and corners, not just hoped for;
  the fresh-against-fresh identity is bit-exact IN ONE environment
  (the R3b lesson: the last digit vs a banked constant belongs to the
  library build - the banked-constant comparison rides rel 1e-6).
- A drafted box is a PRISMATOID: its exact volume is Simpson's
  h/6 (A0 + 4Am + A1), NOT the cone-like h/3 (A0 + A1 + sqrt(A0 A1))
  - a box whose walls tilt independently is not a similar frustum.
  (The formula is the check; it must be the right formula.)
- Refuse rather than lie: a round thing has no "walls" to lean, a
  polygon prism's cone rebuild would lie about its facet geometry, a
  lean through the wall is a collapse, and the fixed plane is the
  body's bottom or top, not anything else.
- The record (DraftFeature) rides the file; the lever speaks the
  draft angle WEARING DEGREES (the R1b unit law) plus the fixed-plane
  combo; the timeline row is a BODY OP (◺), never a boolean plus.
"""
import json
import math

import numpy as np
import pytest

from tracer.core.document import (Document, DraftFeature,
                                  PrimitiveFeature)
from tracer.core.geometry import Solid
from tracer.core.draft import draft_solid


def _rod(r=10.0, h=40.0, center=(0.0, 0.0)):
    return Solid.cylinder(r, h, center=center)


def _blk(dx=20.0, dy=10.0, dz=5.0):
    return Solid.box(dx, dy, dz)


def _rings(solid, cx=0.0, cy=0.0):
    v = solid.to_trimesh().vertices
    rho = np.hypot(v[:, 0] - cx, v[:, 1] - cy)
    lo = v[:, 2] < 1e-4
    hi = v[:, 2] > solid.to_trimesh().vertices[:, 2].max() - 1e-4
    return float(rho[lo].max()), float(rho[hi].max())


# ---- the lean, measured ------------------------------------------------

def test_the_rod_leans_measured_at_the_ring():
    """+10 deg, fixed bottom, on the r10 h40 rod: the fixed plane's
    ring keeps its EXACT size (that is what fixed means) and the free
    ring stands at r + h x tan(10).  Volume rides the true cone
    frustum at mesh tolerance; the rebuild is fresh-against-fresh
    bit-exact in one environment."""
    t = 40.0 * math.tan(math.radians(10.0))
    out, n = draft_solid(_rod(), 10.0)
    bot, top = _rings(out)
    assert bot == pytest.approx(10.0, abs=1e-4)        # fixed holds
    assert top == pytest.approx(10.0 + t, abs=1e-4)    # free end grew
    exact = math.pi * 40 / 3 * (100 + 10 * (10 + t) + (10 + t) ** 2)
    assert out.volume == pytest.approx(exact, rel=1e-3)
    out2, _ = draft_solid(_rod(), 10.0)
    assert out.volume == out2.volume                   # same env: ==
    assert n > 0


def test_the_fixed_plane_holds_from_either_side():
    """fixed="top" is the honest mirror: the top ring keeps the exact
    radius and the BOTTOM grows by the same tangent.  A positive
    angle widens AWAY from the fixed plane (house taper sign law) -
    and a negative one shrinks away: -10 lands the free ring at
    r - h x tan(10)."""
    t = 40.0 * math.tan(math.radians(10.0))
    out, _ = draft_solid(_rod(), 10.0, fixed="top")
    bot, top = _rings(out)
    assert top == pytest.approx(10.0, abs=1e-4)        # fixed holds
    assert bot == pytest.approx(10.0 + t, abs=1e-4)    # free end grew
    out, _ = draft_solid(_rod(), -10.0)
    bot, top = _rings(out)
    assert top == pytest.approx(10.0 - t, abs=1e-4)    # shrank away


def test_zero_angle_is_nothing_at_all():
    """Draft 0 must not touch the body: the box path rebuilds through
    the SAME corners, so it is bit-exact; the rod path asks the
    library for a cone and lands at tessellation slack (float32
    vertices), so the constant-comparison rides rel 1e-6 - the house
    law against banked/library numbers, never a fake bit promise."""
    blk = _blk()
    o, _ = draft_solid(blk, 0.0)
    assert o.volume == blk.volume                      # same path: ==
    rod = _rod()
    o, _ = draft_solid(rod, 0.0)
    assert o.volume == pytest.approx(rod.volume, rel=1e-6)


def test_a_draft_box_is_a_prismatoid():
    """The page rotates EACH wall about its own line, so a drafted
    rectangle is a prismatoid: V = h/6 (A0 + 4Am + A1), NOT the
    similar-frustum h/3 (A0 + A1 + sqrt(A0 A1)) - the wall tilts are
    independent and the shape is not a frustum of a rectangular
    pyramid.  Corners measured: every wall moved out by h x tan(10);
    the mesh is watertight and winding-consistent; the box leans
    FOUR walls and says so."""
    t = 5.0 * math.tan(math.radians(10.0))
    out, n = draft_solid(_blk(), 10.0)
    tm = out.to_trimesh()
    assert tm.is_watertight and tm.is_winding_consistent
    v = tm.vertices
    top = v[v[:, 2] > 5.0 - 1e-6]
    assert top[:, 0].min() == pytest.approx(-t, abs=1e-4)
    assert top[:, 0].max() == pytest.approx(20.0 + t, abs=1e-4)
    assert top[:, 1].min() == pytest.approx(-t, abs=1e-4)
    assert top[:, 1].max() == pytest.approx(10.0 + t, abs=1e-4)
    A0 = 20 * 10
    A1 = (20 + 2 * t) * (10 + 2 * t)
    Am = (20 + t) * (10 + t)
    simp = 5.0 / 6 * (A0 + 4 * Am + A1)
    assert out.volume == pytest.approx(simp, rel=1e-6)
    wrong = 5.0 / 3 * (A0 + A1 + math.sqrt(A0 * A1))
    assert abs(out.volume - wrong) > abs(out.volume - simp) * 100
    assert n == 4


def test_the_axis_is_the_bodys_own():
    """A cylinder standing off-centre drafts about ITS axis: the ring
    centres measure (3, -2) before and after - the world's origin
    owes the body nothing."""
    rod = _rod(r=6.0, h=12.0, center=(3.0, -2.0))
    out, _ = draft_solid(rod, 8.0)
    bot, top = _rings(out, cx=3.0, cy=-2.0)
    assert bot == pytest.approx(6.0, abs=1e-4)
    assert top == pytest.approx(6.0 + 12.0
                                * math.tan(math.radians(8.0)), abs=1e-4)


# ---- refuse rather than lie ---------------------------------------------

def test_the_kernel_refuses_what_it_cannot_lean():
    """Round things have no straight walls; a SIX-sided prism does
    have walls but rebuilding it as a round cone would LIE about the
    facet geometry, so prisms are refused too; a lean that squeezes a
    wall through the axis is a collapse, not a draft; and the fixed
    plane is the body's bottom or top."""
    import trimesh
    m = trimesh.creation.icosphere(subdivisions=3, radius=6.0)
    sph = Solid.from_mesh(m.vertices.astype(np.float64),
                          m.faces.astype(np.int32))
    with pytest.raises(ValueError, match="straight vertical walls"):
        draft_solid(sph, 10.0)
    h = trimesh.creation.cylinder(radius=5.0, height=8.0, sections=6)
    hexs = Solid.from_mesh(h.vertices.astype(np.float64),
                           h.faces.astype(np.int32))
    with pytest.raises(ValueError, match="straight vertical walls"):
        draft_solid(hexs, 10.0)
    with pytest.raises(ValueError, match="collapse"):
        draft_solid(_rod(), -30.0)                    # r - h x tan30 < 0
    with pytest.raises(ValueError, match="collapse"):
        draft_solid(_blk(4.0, 10.0, 40.0), -20.0)     # walls through
    with pytest.raises(ValueError, match="bottom or top"):
        draft_solid(_rod(), 5.0, fixed="middle")


# ---- the record, the file, the route ------------------------------------

def _draft_doc(angle=10.0, fixed="bottom"):
    d = Document("d")
    d.add(PrimitiveFeature(name="rod", kind="cylinder",
                           dims={"radius": 10.0, "height": 40.0}))
    d.add(DraftFeature(name="Draft1", angle_deg=angle, fixed=fixed))
    return d


def test_the_record_rides_the_route_and_the_file():
    """The Document route runs the replacer family: the draft REPLACES
    the body (it never booleans with it) and counts its walls.  The
    record rides disk: the ANGLE AND THE FIXED PLANE are exact through
    json and the reloaded body regrounds at mesh tolerance.  A draft
    with no body yet refuses with its own verb - information clothes,
    not a traceback."""
    d = _draft_doc(angle=12.5, fixed="top")
    v = d.recompute()
    f = d.features[-1]
    assert isinstance(f, DraftFeature) and f.n_walls > 0
    t = 40 * math.tan(math.radians(12.5))
    _, top = _rings(d.result)
    assert top == pytest.approx(10.0, abs=1e-4)       # fixed = top
    raw = json.loads(json.dumps(d.to_dict()))
    fe = raw["features"][-1]
    assert fe["type"] == "DraftFeature"
    assert fe["angle_deg"] == 12.5 and fe["fixed"] == "top"
    d2 = Document.from_dict(raw)
    assert d2.recompute().volume == pytest.approx(v.volume, rel=1e-6)
    e = Document("nb")
    e.add(DraftFeature(name="Draft1"))
    with pytest.raises(ValueError, match="draft"):
        e.recompute()


# ---- the lever and the row ----------------------------------------------

@pytest.fixture()
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:                     # CI windows runners: no GL
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def test_the_lever_speaks_degrees_and_a_fixed_plane(win, qapp):
    """Change Parameters on a draft record: the angle row WEARS
    DEGREES (the R1b law - no millimetre suffix on an angle, anywhere)
    and takes both signs (+/-89.9: shrink and widen are both drafts);
    the fixed-plane combo opens at the record's own value.  And the
    apply mouth writes what was typed, AS typed."""
    rows = {f["key"]: f for f in
            win._feature_params(DraftFeature(name="D", angle_deg=7.5,
                                             fixed="top"))}
    assert list(rows) == ["angle_deg", "fixed"]
    assert rows["angle_deg"]["suffix"] == "\u00b0"
    assert "\u00b0" in rows["angle_deg"]["label"]      # both mouths agree
    assert rows["angle_deg"]["min"] == -89.9
    assert rows["angle_deg"]["max"] == 89.9
    assert rows["fixed"]["kind"] == "combo"
    assert rows["fixed"]["choices"] == ["bottom", "top"]
    assert rows["fixed"]["default"] == "top"
    f = DraftFeature(name="D")
    win._apply_feature_params(f, {"angle_deg": -4.25, "fixed": "top"})
    assert f.angle_deg == -4.25 and f.fixed == "top"  # as typed


def test_the_timeline_row_is_a_lean_not_a_plus(win, qapp):
    """A draft REPLACES the body, so its row must not wear a boolean
    glyph: the body-op family shows its own mark (◺), like the
    fillet's ⌒ before it."""
    win.new_document()
    win.doc.add(PrimitiveFeature(name="rod", kind="cylinder",
                                 dims={"radius": 10.0, "height": 40.0}))
    win.doc.add(DraftFeature(name="Draft1", angle_deg=10.0))
    win.recompute()
    bar = win.timeline.bar
    feat = win.doc.features[-1]
    assert bar._label(feat) == "\u25fa Draft1"
    assert "+" not in bar._label(feat)
