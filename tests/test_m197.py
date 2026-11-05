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
from tracer.core.draft import draft_parting, draft_solid


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


# ---- R2: the command door ---------------------------------------------------
from tracer.ui import cmddialog                                        # noqa


def _rod_win(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="rod", kind="cylinder",
                                 dims={"radius": 10.0, "height": 40.0}))
    win.recompute()
    qapp.processEvents()


def test_the_draft_door_asks_the_pages_rows(win, qapp, monkeypatch):
    """SLD-REF-DRAFT's dialog rows for the tool the kernel honors, IN
    THE PAGE'S ORDER: "Type Select the draft type." (Fixed Plane /
    Parting Line, the page's two names), "Fixed Plane Select a fixed
    plane to draft from" and the Parting Tool spoken plainly as a
    height above the body's own bottom, then "Angle Specify the draft
    angle".  R2 pinned this door at TWO rows; the pin MOVED with the
    vendor when rung three grew the kernel (M196-R3 precedent: pins
    move, laws survive) - the law holds: no Angle Mode, no face list,
    no Tangent Chain, nothing that cannot bake.  Typed 15 from the
    bottom lands exactly and the parting row is NOTED AND NEVER
    WRITTEN for a fixed-plane record (one record one voice); the
    sentence speaks the lean AND the honest wall count, and the angle
    row wears degrees (the R1b law)."""
    calls = []

    def fake(parent, title, fields, **k):
        calls.append((title, fields))
        return {"type": "Fixed Plane", "fixed": "bottom",
                "parting": 99.0, "angle_deg": 15.0}

    monkeypatch.setattr(cmddialog, "ask", fake)
    _rod_win(win, qapp)
    win._body_draft()
    assert len(calls) == 1 and calls[0][0] == "Draft body walls"
    by = {f["key"]: f for f in calls[0][1]}
    assert list(by) == ["type", "fixed", "parting", "angle_deg"]
    assert by["type"]["choices"] == ["Fixed Plane", "Parting Line"]
    assert by["angle_deg"]["suffix"] == "\u00b0"
    assert by["angle_deg"]["min"] == -89.9 and by["angle_deg"]["max"] == 89.9
    assert by["fixed"]["choices"] == ["bottom", "top"]
    assert by["parting"]["kind"] == "double"
    f = win.doc.features[-1]
    assert isinstance(f, DraftFeature)
    assert f.angle_deg == 15.0 and f.fixed == "bottom"      # as typed
    assert f.parting is None                    # row noticed, not written
    msg = win.status.currentMessage()
    assert "at 15" in msg and "from the bottom" in msg \
        and "wall(s) leaned" in msg, msg


def test_the_draft_door_writes_the_fixed_top_mirror(win, qapp,
                                                    monkeypatch):
    """Choose the TOP plane and the cone grows from the other end: the
    top ring keeps its exact size, the bottom ring stands at
    r + h x tan(angle) - the same law the lever path proves, now
    walked through the door."""
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"type": "Fixed Plane",
                                         "fixed": "top",
                                         "parting": 15.0,
                                         "angle_deg": 20.0})
    _rod_win(win, qapp)
    win._body_draft()
    f = win.doc.features[-1]
    assert f.angle_deg == 20.0 and f.fixed == "top"
    assert f.parting is None                    # fixed-plane voice
    bot, top = _rings(win.doc.result)
    t = 40.0 * math.tan(math.radians(20.0))
    assert top == pytest.approx(10.0, abs=1e-4)             # fixed holds
    assert bot == pytest.approx(10.0 + t, abs=1e-3)         # free end
    assert "from the top" in win.status.currentMessage()


def test_the_draft_door_refuses_a_round_body_in_words(win, qapp,
                                                      monkeypatch):
    """The kernel's refusal rides the status line VERBATIM (its cure -
    "a cylinder on its axis or a box standing on the fixed plane" - is
    the teaching) and the refusal unwinds its own undo step: a refusal
    may not leave a step that undoes nothing, and no record is left
    either.  The body is unchanged to the last digit (fresh-against-
    fresh unrounded - the R3b law)."""
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"type": "Fixed Plane",
                                         "fixed": "bottom",
                                         "parting": 15.0,
                                         "angle_deg": 20.0})
    win.new_document()
    win.doc.add(PrimitiveFeature(name="sp", kind="sphere",
                                 dims={"radius": 6.0}))
    win.recompute()
    n = len(win.doc.features)
    u = len(win._undo)
    vol = win.doc.result.volume
    win._body_draft()
    msg = win.status.currentMessage()
    assert msg.startswith("Draft refused:")
    assert "straight vertical walls" in msg, msg
    assert len(win.doc.features) == n and len(win._undo) == u
    assert win.doc.result.volume == vol                     # bit-exact


def test_the_draft_door_cancel_and_precondition(win, qapp,
                                                monkeypatch):
    """Cancel at the door writes nothing (no record, no undo step -
    the capture waits for the dialog's commit); and a window with no
    body yet says so in information clothes, not a traceback."""
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: None)
    _rod_win(win, qapp)
    n, u = len(win.doc.features), len(win._undo)
    win._body_draft()
    assert len(win.doc.features) == n and len(win._undo) == u
    win.new_document()
    win._body_draft()
    assert "No body to draft" in win.status.currentMessage()


def test_the_draft_row_lives_in_the_modify_menu(win, qapp):
    """The page's home is Design > Solid > Modify > Draft; the row
    stands in the house's Modify menu beside fillet and chamfer."""
    menus = [m.menu() for m in win.menuBar().actions()]
    modify = [m for m in menus if m and "dify" in m.title()]
    assert modify, "the Modify menu exists"
    assert win.act_draft in modify[0].actions()


# ---- R3: Parting Line -------------------------------------------------------

def test_the_parting_line_holds_its_own_ring():
    """Rung three, page verbatim: "Parting Line Select a parting tool
    to define a line to draft from" - the tool spoken plainly as a
    horizontal plane a typed height above the body's OWN bottom.
    Fix Parting Line: the ring AT the line keeps its EXACT size (that
    is what fix means) and BOTH free ends move away by their own
    distance x tan(angle) - measured at the vertices.  One angle both
    sides (the page's Symmetric); volume rides the two stacked true
    frustums at mesh tolerance, and the rebuild is fresh-against-fresh
    bit-exact in ONE environment (the R3b law)."""
    t = math.tan(math.radians(10.0))
    out, n = draft_parting(_rod(), 10.0, 15.0)
    v = out.to_trimesh().vertices
    rho = np.hypot(v[:, 0], v[:, 1])
    mid = np.abs(v[:, 2] - 15.0) < 1e-4
    assert rho[mid].max() == pytest.approx(10.0, abs=1e-4)   # waist holds
    assert rho[v[:, 2] < 1e-4].max() == pytest.approx(10.0 + 15.0 * t,
                                                      abs=1e-4)
    assert rho[v[:, 2] > 39.999].max() == pytest.approx(10.0 + 25.0 * t,
                                                        abs=1e-4)

    def frus(hh, r0, r1):
        return math.pi * hh / 3 * (r0 * r0 + r0 * r1 + r1 * r1)
    exact = (frus(15.0, 10.0, 10.0 + 15.0 * t)
             + frus(25.0, 10.0, 10.0 + 25.0 * t))
    assert out.volume == pytest.approx(exact, rel=1e-3)
    out2, _ = draft_parting(_rod(), 10.0, 15.0)
    assert out.volume == out2.volume                    # same env: ==
    assert n > 0


def test_the_parting_line_shrinks_away_symmetrically():
    """A NEGATIVE angle pulls BOTH free ends inward by their own
    distance x tan - the sign law's mirror, now two-sided.  At five
    degrees under, twenty up of a forty-high rod, both rings stand at
    r - 20 x tan(5), measured - symmetric by construction."""
    t = math.tan(math.radians(5.0))
    out, _ = draft_parting(_rod(), -5.0, 20.0)
    v = out.to_trimesh().vertices
    rho = np.hypot(v[:, 0], v[:, 1])
    want = 10.0 - 20.0 * t
    assert rho[v[:, 2] < 1e-4].max() == pytest.approx(want, abs=1e-4)
    assert rho[v[:, 2] > 39.999].max() == pytest.approx(want, abs=1e-4)


def test_a_parting_box_is_two_prismatoids():
    """The box's four walls rotate about their lines AT the parting
    plane: THREE levels, the middle rectangle held EXACT, each end
    grown by its own distance x tan (walls still independent).  The
    exact volume is the SUM OF TWO SIMPSON SEGMENTS - each slice is
    its own prismatoid; watertight and winding-consistent, the
    zero-angle rebuild lands the plain box, and the count says FOUR
    walls."""
    t = math.tan(math.radians(10.0))
    blk = _blk(20.0, 10.0, 40.0)
    out, n = draft_parting(blk, 10.0, 15.0)
    tm = out.to_trimesh()
    assert tm.is_watertight and tm.is_winding_consistent
    v = tm.vertices
    mid = np.abs(v[:, 2] - 15.0) < 1e-6
    assert v[mid][:, 0].min() == pytest.approx(0.0, abs=1e-6)
    assert v[mid][:, 0].max() == pytest.approx(20.0, abs=1e-6)
    W, H = 20.0, 10.0

    def seg(s):
        g = s * t
        return s / 6.0 * (W * H + 4 * (W + g) * (H + g)
                          + (W + 2 * g) * (H + 2 * g))
    assert out.volume == pytest.approx(seg(15.0) + seg(25.0), rel=1e-6)
    o0, _ = draft_parting(blk, 0.0, 15.0)
    assert o0.volume == pytest.approx(8000.0, rel=1e-9)   # the plain box
    assert n == 4


def test_the_parting_line_refuses_where_the_page_agrees():
    """Refuse rather than lie, parting edition: an END is not a
    parting line - at the bottom, at the top, or over it the kernel
    refuses WITH THE CURE ("at an end it is the fixed plane
    instead"); a lean that squeezes the ends through the axis is a
    collapse; and the sphere still has no walls to rotate."""
    for bad in (0.0, 40.0, 45.0):
        with pytest.raises(ValueError, match="between the body's"):
            draft_parting(_rod(), 10.0, bad)
    with pytest.raises(ValueError, match="fixed plane"):
        draft_parting(_rod(), 10.0, 45.0)               # cure in the words
    with pytest.raises(ValueError, match="collapse"):
        draft_parting(_rod(), -40.0, 20.0)
    import trimesh
    m = trimesh.creation.icosphere(subdivisions=3, radius=6.0)
    sph = Solid.from_mesh(m.vertices.astype(np.float64),
                          m.faces.astype(np.int32))
    with pytest.raises(ValueError, match="straight vertical walls"):
        draft_parting(sph, 10.0, 3.0)


def test_the_parting_record_rides_the_file_and_old_files_stay_put():
    """The typed parting height is EXACT through json and the reloaded
    body regrounds at mesh tolerance.  A record written BEFORE rung
    three carries no parting key at all: from_dict reads None and the
    LEGACY fixed-plane route runs untouched - the free ring measured
    where rung one always put it.  Old files replay byte-honest."""
    d = Document("p")
    d.add(PrimitiveFeature(name="rod", kind="cylinder",
                           dims={"radius": 10.0, "height": 40.0}))
    d.add(DraftFeature(name="Draft1", angle_deg=15.0, parting=12.5))
    v = d.recompute()
    raw = json.loads(json.dumps(d.to_dict()))
    fe = raw["features"][-1]
    assert fe["parting"] == 12.5 and fe["angle_deg"] == 15.0
    d2 = Document.from_dict(raw)
    assert d2.recompute().volume == pytest.approx(v.volume, rel=1e-6)
    del fe["parting"]                                   # a legacy record
    d3 = Document.from_dict(raw)
    f3 = d3.features[-1]
    assert f3.parting is None and f3.fixed == "bottom"  # rung one's route
    t = 40.0 * math.tan(math.radians(15.0))
    vv = d3.recompute().to_trimesh().vertices
    rho = np.hypot(vv[:, 0], vv[:, 1])
    assert rho[vv[:, 2] > 39.999].max() == pytest.approx(10.0 + t,
                                                         abs=1e-4)


def test_the_parting_lever_speaks_its_own_two_rows(win, qapp):
    """A parting record's lever opens the angle (degrees, R1b) and the
    parting height WEARING MILLIMETRES, and CLOSES the fixed-plane
    combo - one record one voice (the M196 law; the R1 gate pins the
    fixed record's rows, untouched).  The apply mouth writes what was
    typed, AS TYPED, and never invents a fixed-plane change."""
    rows = {f["key"]: f for f in
            win._feature_params(DraftFeature(name="D", angle_deg=12.5,
                                             parting=12.5))}
    assert list(rows) == ["angle_deg", "parting"]
    assert rows["angle_deg"]["suffix"] == "\u00b0"
    assert "mm" in rows["parting"]["label"]             # the unit rides
    assert rows["parting"]["default"] == 12.5
    f = DraftFeature(name="D", parting=10.0)
    win._apply_feature_params(f, {"angle_deg": 7.5, "parting": 18.0})
    assert f.angle_deg == 7.5 and f.parting == 18.0     # as typed
    assert f.fixed == "bottom"                          # not touched


def test_the_door_drafts_from_a_parting_line(win, qapp, monkeypatch):
    """The page's second type, walked through the real door: choose
    Parting Line, type twenty degrees fifteen above the bottom - the
    waist holds ten EXACT, both ends grew by their OWN distance x tan
    twenty, and the sentence speaks the parting line and the height.
    The fixed-plane row, left at "top", is NOTICED AND NEVER WRITTEN
    (one record one voice)."""
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"type": "Parting Line",
                                         "fixed": "top",         # ignored
                                         "parting": 15.0,
                                         "angle_deg": 20.0})
    _rod_win(win, qapp)
    win._body_draft()
    f = win.doc.features[-1]
    assert f.parting == 15.0 and f.angle_deg == 20.0
    v = win.doc.result.to_trimesh().vertices
    rho = np.hypot(v[:, 0], v[:, 1])
    t = math.tan(math.radians(20.0))
    mid = np.abs(v[:, 2] - 15.0) < 1e-4
    assert rho[mid].max() == pytest.approx(10.0, abs=1e-4)
    assert rho[v[:, 2] < 1e-4].max() == pytest.approx(10.0 + 15.0 * t,
                                                      abs=1e-3)
    assert rho[v[:, 2] > 39.999].max() == pytest.approx(10.0 + 25.0 * t,
                                                        abs=1e-3)
    assert "from the parting line at 15 mm" in win.status.currentMessage()
