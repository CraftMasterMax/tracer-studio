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
from tracer.core.offsetface import offset_face


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
