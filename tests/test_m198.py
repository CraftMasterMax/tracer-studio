"""M198: the Offset Face tool.

[SLD-OFFSET-FACES, verbatim] "Learn how to use the Offset Face tool
to shift faces on a solid body" - "Select a single face or multiple
faces and specify the Offset distance" and the note that makes it
more than a resize: "Adjoining curved tangent faces will offset when
geometrically possible."
Rung 1 cuts the SINGLE-face sentence on the straight-walled family
(the same detector Draft earned - one mouth, two tools): a cylinder
on its axis or an axis-aligned box.  The named face slides OUTWARD
by the typed distance (negative shrinks) along its own normal, and
the page's note falls out of the rebuild: a rod's cap going up takes
its wall with it; its wall going out takes both caps with it.

The laws these gates pin:
- The faces are spoken PLAINLY (the Draft law kept): "bottom", "top",
  "wall" (the cylinder's curved face) or "+x" "-x" "+y" "-y" (the
  box's four).  A name the body does not own is refused WITH ITS
  CURE - the body's real names ride in the words.
- Adjoining faces FOLLOW, measured at the vertices: the untouched
  caps/rectangles keep their exact z/extent while the moved one
  travels - and where the page says "when geometrically possible",
  an offset that squeezes the body out of existence is refused, not
  ground to a sliver.
- Fresh-against-fresh == in ONE environment (the R3b law); against
  analytic constants the house tolerances ride (the library rebuild
  sits ~1e-4 low; the float64 box path is bit-exact).
- The record (OffsetFaceFeature) rides the replacer route and the
  file; the lever speaks its own two rows with the distance WEARING
  MILLIMETRES (signed - the page's "positive or negative direction");
  the timeline row is a BODY OP (⇕), never a boolean plus.
"""
import json
import math

import numpy as np
import pytest

from tracer.core.document import (Document, OffsetFaceFeature,
                                  PrimitiveFeature)
from tracer.core.geometry import Solid
from tracer.core.offsetface import offset_face, offset_faces
from tracer.ui import cmddialog


def _rod(r=10.0, h=40.0):
    return Solid.cylinder(r, h)


def _blk(dx=20.0, dy=10.0, dz=5.0):
    return Solid.box(dx, dy, dz)


def _meas(solid):
    v = solid.to_trimesh().vertices
    rho = np.hypot(v[:, 0], v[:, 1])
    return v, rho


# ---- the page's note, measured --------------------------------------------

def test_a_cap_offset_takes_the_wall_with_it():
    """The top cap +5 on the r10 h40 rod: the rod stands h45 (exact,
    measured at the vertices), its ONE curved face followed to the
    new height (rho still ten on the new top ring), and the bottom
    cap did NOT move (zmin stays 0).  Fresh-against-fresh bit-exact;
    volume rides the true cylinder at mesh tolerance."""
    out = offset_face(_rod(), "top", 5.0)
    v, rho = _meas(out)
    assert v[:, 2].max() == pytest.approx(45.0, abs=1e-4)
    assert v[:, 2].min() == pytest.approx(0.0, abs=1e-4)   # the other end
    top = v[:, 2] > 45.0 - 1e-4
    assert rho[top].max() == pytest.approx(10.0, abs=1e-4)  # the wall moved
    exact = math.pi * 100.0 * 45.0
    assert out.volume == pytest.approx(exact, rel=1e-3)
    assert out.volume == offset_face(_rod(), "top", 5.0).volume


def test_the_bottom_faces_the_other_way():
    """A face's OUTWARD normal is its own: bottom +5 slides DOWN (the
    rod spans -5..40, grown to h45, the TOP staying put) - the
    positive direction is per face, not a world axis.  And the
    shrink mirror: top -3 lands h37, the bottom untouched."""
    out = offset_face(_rod(), "bottom", 5.0)
    v, _ = _meas(out)
    assert v[:, 2].min() == pytest.approx(-5.0, abs=1e-4)
    assert v[:, 2].max() == pytest.approx(40.0, abs=1e-4)  # top STAYS
    out = offset_face(_rod(), "top", -3.0)
    v, _ = _meas(out)
    assert v[:, 2].max() == pytest.approx(37.0, abs=1e-4)
    assert v[:, 2].min() == pytest.approx(0.0, abs=1e-4)


def test_a_wall_offset_takes_both_caps():
    """The rod's curved FACE is one: wall +2 grows the radius to
    twelve (measured) while BOTH caps follow the wider circle - the
    z-span stays the typed forty, untouched - and the volume rides
    the true cylinder at mesh tolerance."""
    out = offset_face(_rod(), "wall", 2.0)
    v, rho = _meas(out)
    assert rho.max() == pytest.approx(12.0, abs=1e-4)
    assert v[:, 2].max() - v[:, 2].min() == pytest.approx(40.0, abs=1e-4)
    exact = math.pi * 144.0 * 40.0
    assert out.volume == pytest.approx(exact, rel=1e-3)


def test_the_box_moves_the_named_wall_only():
    """The box's six plain names: top +2 grows it to 20x10x7 (vol
    1400 EXACT - this mesh is float64, no tessellation slack), -x +2
    slides the x0 face to -2 (vol 1100), every OTHER extent stays
    where the primitive put it.  Watertight, winding-consistent, and
    zero distance rebuilds the SAME box bit-exactly (== source)."""
    out = offset_face(_blk(), "top", 2.0)
    tm = out.to_trimesh()
    assert tm.is_watertight and tm.is_winding_consistent
    v = tm.vertices
    assert v[:, 2].max() == pytest.approx(7.0, abs=1e-6)
    assert v[:, 2].min() == pytest.approx(0.0, abs=1e-6)
    assert out.volume == pytest.approx(1400.0, rel=1e-9)
    ox = offset_face(_blk(), "-x", 2.0)
    vx = ox.to_trimesh().vertices
    assert vx[:, 0].min() == pytest.approx(-2.0, abs=1e-6)
    assert vx[:, 0].max() == pytest.approx(20.0, abs=1e-6)  # the far wall
    assert ox.volume == pytest.approx(1100.0, rel=1e-9)
    assert offset_face(_blk(), "+y", 0.0).volume == _blk().volume


def test_the_kernel_refuses_what_is_not_a_face_or_a_body():
    """A name the body does not own is refused WITH ITS CURE - the
    cylinder hears its three real names, the box its six; an offset
    that squeezes the body out of existence ("when geometrically
    possible", read honestly as a refusal) never grinds to a sliver;
    and the sphere still has no faces this tool dares touch."""
    with pytest.raises(ValueError, match="cylinder's faces are"):
        offset_face(_rod(), "+x", 2.0)
    with pytest.raises(ValueError, match="'wall'"):
        offset_face(_rod(), "+x", 2.0)                    # the cure names
    with pytest.raises(ValueError, match="box's faces are"):
        offset_face(_blk(), "wall", 2.0)                  # box has none
    with pytest.raises(ValueError, match="collapse"):
        offset_face(_rod(), "top", -40.0)
    with pytest.raises(ValueError, match="collapse"):
        offset_face(_blk(), "+x", -20.0)
    import trimesh
    m = trimesh.creation.icosphere(subdivisions=3, radius=6.0)
    sph = Solid.from_mesh(m.vertices.astype(np.float64),
                          m.faces.astype(np.int32))
    with pytest.raises(ValueError, match="straight vertical walls"):
        offset_face(sph, "top", 1.0)


# ---- the record, the route, the file ---------------------------------------

def test_the_record_rides_the_route_and_the_file():
    """The Document route runs the replacer family (the offset
    REPLACES the body, never booleans with it): the wall +2 lands
    twelve on the rod's rho through the pipeline.  The record rides
    disk - face and SIGNED distance EXACT through json - and the
    reloaded body regrounds at mesh tolerance.  An offset with no
    body yet refuses with its own verb, information clothes."""
    d = Document("o")
    d.add(PrimitiveFeature(name="rod", kind="cylinder",
                           dims={"radius": 10.0, "height": 40.0}))
    d.add(OffsetFaceFeature(name="Offset1", face="wall", dist=2.0))
    v = d.recompute()
    _, rho = _meas(d.result)
    assert rho.max() == pytest.approx(12.0, abs=1e-4)
    raw = json.loads(json.dumps(d.to_dict()))
    fe = raw["features"][-1]
    assert fe["type"] == "OffsetFaceFeature"
    assert fe["face"] == "wall" and fe["dist"] == 2.0
    d2 = Document.from_dict(raw)
    assert d2.recompute().volume == pytest.approx(v.volume, rel=1e-6)
    e = Document("nb")
    e.add(OffsetFaceFeature(name="Offset1"))
    with pytest.raises(ValueError, match="offset"):
        e.recompute()


# ---- the lever and the row --------------------------------------------------

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


def test_the_lever_speaks_a_face_and_signed_millimetres(win, qapp):
    """Change Parameters on an offset record: the face combo opens at
    the record's OWN plain name and carries the union of both
    families' names (the kernel refuses what the body does not own,
    cure in the words - rung one's honesty); the distance WEARS
    MILLIMETRES and takes the negative: typed -2.5 rides the lever as
    typed, and the apply mouth writes face and distance back
    unchanged."""
    rows = {f["key"]: f for f in
            win._feature_params(OffsetFaceFeature(name="O", face="-x",
                                                  dist=-2.5))}
    assert list(rows) == ["face", "dist"]
    assert rows["face"]["kind"] == "combo"
    assert rows["face"]["default"] == "-x"
    assert set(["wall", "+x", "-y"]).issubset(set(rows["face"]["choices"]))
    assert "mm" in rows["dist"]["label"]
    assert rows["dist"]["default"] == -2.5         # signed, as stored
    assert rows["dist"]["min"] == -1000.0          # negative room
    f = OffsetFaceFeature(name="O")
    win._apply_feature_params(f, {"face": "bottom", "dist": -1.25})
    assert f.face == "bottom" and f.dist == -1.25  # as typed


def test_the_timeline_row_is_a_slide_not_a_plus(win, qapp):
    """An offset REPLACES the body, so its row must not wear a
    boolean glyph: the body-op family shows its own mark (⇕), like
    the draft's ◺ before it."""
    win.new_document()
    win.doc.add(PrimitiveFeature(name="rod", kind="cylinder",
                                 dims={"radius": 10.0, "height": 40.0}))
    win.doc.add(OffsetFaceFeature(name="Offset1", face="top", dist=5.0))
    win.recompute()
    bar = win.timeline.bar
    feat = win.doc.features[-1]
    assert bar._label(feat) == "\u21d5 Offset1"
    assert "+" not in bar._label(feat)
    v = win.doc.result.to_trimesh().vertices
    assert v[:, 2].max() == pytest.approx(45.0, abs=1e-4)


# ---- R2: the door -----------------------------------------------------------

def _rod_win(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="rod", kind="cylinder",
                                 dims={"radius": 10.0, "height": 40.0}))
    win.recompute()
    qapp.processEvents()


def test_the_door_asks_the_pages_plural(win, qapp, monkeypatch):
    """SLD-OFFSET-FACES' dialog, the page's OWN plural: "Select a
    single face OR MULTIPLE FACES and specify THE Offset DISTANCE" -
    a Faces checks row (the plain names, default ticked top) and THE
    one distance wearing millimetres, signed.  R2 pinned this door
    at a Face COMBO; the pin MOVED with the vendor when rung three
    grew the kernel (M196-R3 precedent: pins move, laws survive) -
    the law holds: no manipulator, no curved bodies, nothing that
    cannot bake.  ONE ticked face still rides rung one's single
    rebuild and the singular sentence (measured below)."""
    calls = []

    def fake(parent, title, fields, **k):
        calls.append((title, fields))
        return {"faces": ["wall"], "dist": 2.0}

    monkeypatch.setattr(cmddialog, "ask", fake)
    _rod_win(win, qapp)
    win._body_offset()
    assert len(calls) == 1 and calls[0][0] == "Offset a face"
    by = {f["key"]: f for f in calls[0][1]}
    assert list(by) == ["faces", "dist"]
    assert by["faces"]["kind"] == "checks"
    assert by["faces"]["choices"] == ["bottom", "top", "wall", "+x",
                                      "-x", "+y", "-y"]
    assert by["faces"]["checked"] == ["top"]
    assert by["dist"]["kind"] == "double"
    assert by["dist"]["suffix"] == " mm"
    assert by["dist"]["min"] == -1000.0            # the negative speaks
    assert by["dist"]["decimals"] == 3
    f = win.doc.features[-1]
    assert isinstance(f, OffsetFaceFeature) and f.name == "Offset1"
    assert f.faces == ("wall",) and f.dist == 2.0  # as typed
    assert f.face == "top"                 # noticed, NEVER written
    _, rho = _meas(win.doc.result)
    assert rho.max() == pytest.approx(12.0, abs=1e-4)
    msg = win.status.currentMessage()
    assert "Offset face 'wall' by +2 mm" in msg and "volume" in msg, msg


def test_the_door_slides_inward_with_a_negative(win, qapp, monkeypatch):
    """The sign law walked through the real door: bottom minus three
    pulls the bottom cap UP to z3 while the top STANDS at forty -
    inward along the face's own normal, the typed sign stored
    untouched, the sentence honest about the minus."""
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"faces": ["bottom"],
                                         "dist": -3.0})
    _rod_win(win, qapp)
    win._body_offset()
    v = win.doc.result.to_trimesh().vertices
    assert v[:, 2].min() == pytest.approx(3.0, abs=1e-4)
    assert v[:, 2].max() == pytest.approx(40.0, abs=1e-4)   # top STANDS
    f = win.doc.features[-1]
    assert f.dist == -3.0                          # signed, as typed
    assert "by -3 mm" in win.status.currentMessage()


def test_the_door_refuses_with_the_cure_verbatim(win, qapp, monkeypatch):
    """'+x' asked of a rod: the kernel's cure ("this cylinder's faces
    are 'bottom', 'top', 'wall' - not '+x'") rides the status
    VERBATIM; the refusal pops its own undo step (one that undoes
    nothing is a lie, the M197 R2 law), writes no record, and the
    body is untouched TO THE LAST DIGIT - fresh unrounded == (the
    R3b law)."""
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"faces": ["+x"], "dist": 2.0})
    _rod_win(win, qapp)
    vol = win.doc.result.volume                    # UNROUNDED
    n, u = len(win.doc.features), len(win._undo)
    win._body_offset()
    msg = win.status.currentMessage()
    assert msg.startswith("Offset refused:"), msg
    assert "this cylinder's faces are" in msg and "not '+x'" in msg, msg
    assert len(win.doc.features) == n and len(win._undo) == u
    assert win.doc.result.volume == vol


def test_the_door_refuses_a_wall_squeezed_through_the_axis(win, qapp,
                                                           monkeypatch):
    """The page's "when geometrically possible", read honestly: wall
    minus ten on a FRESH r10 rod leaves no material - refused, not
    shaved.  (The R2 probe met this call behind a ring already at
    twelve, where minus ten lands honest at r2 and 502.6 mm³ =
    pi x 4 x 40 - the kernel right, the probe's shadow wrong.  The
    gate runs FRESH.)"""
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"faces": ["wall"], "dist": -10.0})
    _rod_win(win, qapp)
    vol = win.doc.result.volume
    win._body_offset()
    msg = win.status.currentMessage()
    assert msg.startswith("Offset refused:") and "must still leave" \
        in msg, msg
    assert len(win.doc.features) == 1              # rod only
    assert win.doc.result.volume == vol


def test_the_doors_cancel_and_precondition(win, qapp, monkeypatch):
    """Cancel at the door writes NOTHING (no record, no undo step -
    the capture waits for the dialog's commit, the M197 R2 law); a
    window with no body yet says so in information clothes."""
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: None)
    _rod_win(win, qapp)
    n, u = len(win.doc.features), len(win._undo)
    win._body_offset()
    assert len(win.doc.features) == n and len(win._undo) == u
    win.new_document()
    win._body_offset()
    assert "No body to offset" in win.status.currentMessage()


def test_the_offset_door_lives_in_the_modify_menu_and_the_dock(win, qapp):
    """The page's home: Solid tab, Modify > Offset Face - the row
    stands in the house's Modify menu beside draft (a mnemonic-free
    row riding its bare-key shortcut, the "Change Parameters…"
    precedent, every letter in its name already taken).  The dock
    button stands AFTER Draft in the design panel (the m42 pin paid
    with the vendor IN THIS COMMIT - no R2b debt) and its glyph is
    drawn, registered as "offsetface" - the sketch family's Offset
    Curve already owns the plain "offset" mouth."""
    menus = [m.menu() for m in win.menuBar().actions()]
    modify = [m for m in menus if m and "dify" in m.title()]
    assert modify, "the Modify menu exists"
    assert win.act_offset in modify[0].actions()
    from PySide6.QtWidgets import QToolButton
    tips = []
    lay = win.ribbon.dl
    for i in range(lay.count()):
        it = lay.itemAt(i).widget()
        if isinstance(it, QToolButton):
            tips.append(it.toolTip().split(" \u2014 ")[0].split(" (")[0])
    assert tips[tips.index("Draft") + 1] == "Offset face"
    from tracer.ui import icons
    assert callable(icons._DRAW["offsetface"])


# ---- R3: the page's plural ---------------------------------------------------

def test_multiple_faces_slide_with_the_one_distance():
    """The page's OWN plural with its OWN singular: "a single face or
    MULTIPLE FACES and specify THE Offset DISTANCE" - one typed
    distance, EVERY named face slides outward along its own normal.
    The straight-walled body's bounds are INDEPENDENT per face, so
    the rebuild is as exact as the single slide: the rod with all
    three ticks stands r15 z-5..45 (measured, true cylinder at mesh
    tolerance), the box subset lands 1848 EXACT (float64 mesh) and
    both caps together 1800 EXACT.  ORDER NEVER MATTERS (==), and a
    plural of ONE rebuilds IDENTICAL to rung one's single (==, fresh
    against fresh in one environment - the R3b law)."""
    rod = _rod()
    out = offset_faces(rod, ["bottom", "top", "wall"], 5.0)
    v, rho = _meas(out)
    assert rho.max() == pytest.approx(15.0, abs=1e-4)
    assert v[:, 2].min() == pytest.approx(-5.0, abs=1e-4)
    assert v[:, 2].max() == pytest.approx(45.0, abs=1e-4)
    exact = math.pi * 225.0 * 50.0
    assert out.volume == pytest.approx(exact, rel=1e-3)
    assert offset_faces(rod, ["wall"], 2.0).volume \
        == offset_face(rod, "wall", 2.0).volume          # == fresh-fresh
    assert offset_faces(rod, ["wall", "top"], 5.0).volume \
        == offset_faces(rod, ["top", "wall"], 5.0).volume  # order never
    box = _blk(20.0, 10.0, 5.0)
    b = offset_faces(box, ["top", "+x", "-y"], 2.0)      # 22 x 12 x 7
    assert b.volume == 1848.0                            # float64 EXACT
    assert offset_faces(box, ["top", "bottom"], 2.0).volume == 1800.0


def test_the_plural_refuses_in_one_message():
    """One request, one answer: TWO names the rod lacks come back in
    ONE cure carrying ALL the missing names and the body's real ones
    (not the first refusal only); the box's ticked "wall" refuses its
    own way; ZERO names refuses ("name at least one face") - and the
    squeeze guard reads the FINAL extents on a FRESH body (the R2
    shadow law): wall minus ten on r10 leaves nothing and is
    refused, caps minus three on h5 likewise."""
    with pytest.raises(ValueError, match=r"not '\+x', '-y'"):
        offset_faces(_rod(), ["wall", "+x", "-y"], 2.0)
    with pytest.raises(ValueError, match="box's faces are"):
        offset_faces(_blk(), ["wall", "top"], 2.0)
    with pytest.raises(ValueError, match="at least one face"):
        offset_faces(_rod(), [], 2.0)
    with pytest.raises(ValueError, match="collapse"):
        offset_faces(_rod(), ["wall"], -10.0)            # FRESH r10
    with pytest.raises(ValueError, match="collapse"):
        offset_faces(_blk(), ["top", "bottom"], -3.0)    # h5 - 6


def test_the_plural_record_rides_the_file_and_old_files_stay_put():
    """The ticked NAMES ride json EXACT and the reloaded body
    regrounds BIT-EQUAL (fresh against fresh, one environment); the
    singular `face` rides alongside as the noticed-never-written
    default.  A record written BEFORE rung three carries no faces
    key at all: from_dict reads () and the LEGACY single route runs
    untouched - the top+5 rebuild measured at zmax 45 with the ring
    still ten.  Old files replay byte-honest."""
    d = Document("pf")
    d.add(PrimitiveFeature(name="rod", kind="cylinder",
                           dims={"radius": 10.0, "height": 40.0}))
    d.add(OffsetFaceFeature(name="Offset1", faces=("top", "wall"),
                            dist=5.0))
    v = d.recompute()
    raw = json.loads(json.dumps(d.to_dict()))
    fe = raw["features"][-1]
    assert fe["faces"] == ["top", "wall"] and fe["dist"] == 5.0
    d2 = Document.from_dict(raw)
    assert d2.features[-1].faces == ("top", "wall")
    assert d2.recompute().volume == v.volume            # ==, one env
    del fe["faces"]                                      # a legacy record
    d3 = Document.from_dict(raw)
    f3 = d3.features[-1]
    assert f3.faces == () and f3.face == "top"           # rung one's route
    vv = d3.recompute().to_trimesh().vertices
    rho = np.hypot(vv[:, 0], vv[:, 1])
    assert vv[:, 2].max() == pytest.approx(45.0, abs=1e-4)
    assert rho[vv[:, 2] > 44.999].max() == pytest.approx(10.0, abs=1e-4)


def test_the_lever_speaks_each_records_own_voice(win, qapp):
    """One record one voice (the M196 law): a PLURAL record opens
    the checks row with its OWN names ticked and never the combo; a
    legacy record opens the combo (rung one's gate pins it,
    untouched) and never the checks.  The apply mouth writes faces
    and distance AS TYPED and never invents a single-face change;
    the plural apply leaves `face` where it stood."""
    rows = {f["key"]: f for f in
            win._feature_params(OffsetFaceFeature(name="P",
                                                  faces=("top", "wall"),
                                                  dist=5.0))}
    assert list(rows) == ["faces", "dist"]
    assert rows["faces"]["kind"] == "checks"
    assert rows["faces"]["checked"] == ["top", "wall"]   # the record's own
    assert rows["dist"]["default"] == 5.0
    g = OffsetFaceFeature(name="G", faces=("wall",), dist=1.0)
    win._apply_feature_params(g, {"faces": ["top", "bottom"],
                                  "dist": -2.0})
    assert g.faces == ("top", "bottom") and g.dist == -2.0   # as typed
    assert g.face == "top"                             # not touched


def test_the_door_offsets_every_ticked_face_and_refuses_none(win, qapp,
                                                             monkeypatch):
    """The plural walked through the real door on a FRESH rod:
    bottom, top AND wall ticked with five - the rod stands r15
    z-5..45 (measured: ten plus the one five, NOT the shadowed
    seventeen a second offset would stack), the volume rides the
    true cylinder at mesh tolerance, and the SENTENCE speaks EVERY
    name in its own voice.  Zero ticks is no request: refused
    BEFORE the capture (no record, NO undo step, the body untouched
    to the last digit) - under this door a faces-empty record would
    BE the legacy single route, so writing one would slide a face
    nobody named."""
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"faces": ["bottom", "top",
                                                   "wall"],
                                         "dist": 5.0})
    _rod_win(win, qapp)
    win._body_offset()
    f = win.doc.features[-1]
    assert f.faces == ("bottom", "top", "wall") and f.dist == 5.0
    v, rho = _meas(win.doc.result)
    assert rho.max() == pytest.approx(15.0, abs=1e-4)
    assert v[:, 2].min() == pytest.approx(-5.0, abs=1e-4)
    assert v[:, 2].max() == pytest.approx(45.0, abs=1e-4)
    assert v[:, 2].max() - v[:, 2].min() == pytest.approx(50.0, abs=1e-4)
    assert win.doc.result.volume == pytest.approx(math.pi * 225.0 * 50.0,
                                                  rel=1e-3)
    msg = win.status.currentMessage()
    assert "Offset faces 'bottom', 'top', 'wall' by +5 mm" in msg, msg
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"faces": [], "dist": 2.0})
    n, u, vol = len(win.doc.features), len(win._undo), \
        win.doc.result.volume
    win._body_offset()
    assert win.status.currentMessage().startswith("Offset refused:")
    assert "at least one face" in win.status.currentMessage()
    assert len(win.doc.features) == n and len(win._undo) == u
    assert win.doc.result.volume == vol


# ---- R4: the page's double-clicked icon --------------------------------------

def test_the_plural_chip_double_click_opens_its_lever(win, qapp,
                                                      monkeypatch):
    """The page's promise, verbatim: "a new Offset Face feature is
    created within the Timeline, which gives you an opportunity to
    COME BACK AND EDIT IT LATER BY DOUBLE-CLICKING ITS ICON."  The
    edit door (test_m18's timeline double-click path, called here
    exactly as that gate calls it) opens the PLURAL record's OWN
    lever - faces + the one distance, fx column riding - the typed
    edit lands (fresh rod back from all-three to wall-only: ring
    thirteen, bottom HOME at zero, top at the typed forty) and the
    status says Parameters changed, NOT the shrug.  R4's audit fact:
    before this rung the ⇕ chip SHRUGGED ("no editable sketch") -
    the promise unkept; no gate pinned the shrug, so the pin grows
    in the honest direction."""
    win.new_document()
    win.doc.add(PrimitiveFeature(name="rod", kind="cylinder",
                                 dims={"radius": 10.0, "height": 40.0}))
    win.doc.add(OffsetFaceFeature(name="Offset1",
                                  faces=("bottom", "top", "wall"),
                                  dist=5.0))
    win.recompute()
    calls = []

    def fake(parent, title, fields, **k):
        calls.append((title, [f["key"] for f in fields]))
        return {"faces": ["wall"], "dist": 3.0, "fx_dist": ""}

    monkeypatch.setattr(cmddialog, "ask", fake)
    win._feature_activated(win.doc.features[-1])
    qapp.processEvents()
    assert calls[0][0] == "Change Parameters \u2014 Offset1"
    assert calls[0][1] == ["faces", "dist", "fx_dist"]   # plural voice
    rec = win.doc.features[-1]
    assert rec.faces == ("wall",) and rec.dist == 3.0    # as typed
    v, rho = _meas(win.doc.result)
    assert rho.max() == pytest.approx(13.0, abs=1e-4)
    assert v[:, 2].min() == pytest.approx(0.0, abs=1e-4)   # bottom HOME
    assert v[:, 2].max() == pytest.approx(40.0, abs=1e-4)  # typed forty
    assert "Parameters changed on Offset1" in win.status.currentMessage()
    assert "no editable sketch" not in win.status.currentMessage()


def test_the_legacy_chip_opens_the_combo_voice(win, qapp, monkeypatch):
    """One record one voice, now through the TIMELINE door: a legacy
    record's chip opens the COMBO lever (never the checks row) and
    the edit runs rung one's single route - bottom+2 rewritten to
    top+5 puts the bottom back at zero and stands zmax 45, faces
    still empty.  The marker law rides untouched: a PARKED marker
    rolls before the edit opens (LAW-10, pinned by m161 for every
    edit door - here it just must not block the lever)."""
    win.new_document()
    win.doc.add(PrimitiveFeature(name="rod", kind="cylinder",
                                 dims={"radius": 10.0, "height": 40.0}))
    win.doc.add(OffsetFaceFeature(name="Offset1", face="bottom",
                                  dist=2.0))
    win.recompute()
    keys = []
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda p, t, fields, **k: (keys.append([f["key"]
                                                for f in fields]),
                                   {"face": "top", "dist": 5.0,
                                    "fx_dist": ""})[1])
    win._feature_activated(win.doc.features[-1])
    qapp.processEvents()
    assert keys[0] == ["face", "dist", "fx_dist"]          # combo voice
    rec = win.doc.features[-1]
    assert rec.face == "top" and rec.faces == () and rec.dist == 5.0
    v = win.doc.result.to_trimesh().vertices
    assert v[:, 2].min() == pytest.approx(0.0, abs=1e-4)   # bottom HOME
    assert v[:, 2].max() == pytest.approx(45.0, abs=1e-4)
    win.doc.rollback_to = 1                                # PARKED
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"face": "top", "dist": 7.0,
                                         "fx_dist": ""})
    win._feature_activated(win.doc.features[-1])           # must still open
    qapp.processEvents()
    assert win.doc.features[-1].dist == 7.0
    assert "Parameters changed on Offset1" in win.status.currentMessage()
