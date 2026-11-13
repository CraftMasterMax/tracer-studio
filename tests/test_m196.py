"""M196 rung 1 - THE BEVEL LEARNS AN ANGLE.

[SLD-REF-CHAMFER, verbatim] "Distance And Angle : Bevels edges based
on a single distance and an angle." + "Angle (Distance And Angle
chamfer type only) Specify the angle value for the chamfer."

Tracer's chamfer was the vendor's EQUAL DISTANCE kind only: the rim
kernel cut the same triangle P(R,0),P(0,R) on every circular rim and
the Change Parameters door asked one number. The record gains
angle_deg and the kernel now cuts a right triangle whose CAP leg is
the distance and whose WALL leg is D*tan(theta) - the convention
pinned at opening: the distance is measured along the cap, the angle
opens FROM the cap.

- None is the LEGACY record: the symmetric branch never moved, so old
  files recompute byte-identically (and their pre-M196 five-term cache
  keys mismatch by SHAPE, forcing exactly one honest recompute).
- 45.0 typed is the same GEOMETRY but a different RECORD:
  tan(45 deg) is 0.9999999999999999, and identity is not approximation.
- The distance is the constant across angles (cap leg measures the
  same at 30, 45 and 60); only the wall travels - the vendor's
  "single distance and an angle" in vertices.
- The angle rides the file, the lever speaks it (the row opens ONLY
  for a bevel record - the page's "(Distance And Angle chamfer type
  only)"), and the door writes what is typed.

Rung 3 lands the page's MIDDLE type: "Two Distance: Bevels edges
based on a different distance to each side" - both legs TYPED
millimetres, no tangent, no trigonometry.  The door's combo now
carries all three page types in the page's own order (the R2 pin
moved with the vendor as its comment promised); the record gains
dist2; and a typed 5 AND 5 is the equal bevel EXACTLY - identity
when nothing is approximated, the honest mirror of the 45-degree
lesson.  A record may not wear two types: the kernel refuses both
terms on one record.
"""
import json

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                        # noqa

from tracer.core.document import (BodyFilletFeature, Document,    # noqa
                                  PrimitiveFeature)
from tracer.ui.mainwindow import MainWindow                       # noqa
from tracer.ui.renderer import SceneRenderer                      # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
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


LEGACY_VOL = 11256.243453480622    # r10 h40 rod, D=5 equal bevel: the
                                   # number the symmetric branch has
                                   # always ground out (M19 era) - full
                                   # precision, since the gate trusts it
                                   # at rel 1e-9


def _rod(angle=None, dist=5.0):
    d = Document("bevel")
    d.add(PrimitiveFeature(name="rod", kind="cylinder",
                           dims={"radius": 10.0, "height": 40.0}))
    d.add(BodyFilletFeature(name="Chamfer1", radius=dist, chamfer=True,
                            angle_deg=angle))
    return d


def _mouths(solid):
    """Vertices that SIT on the cap plane and on the wall - the two
    legs read straight off the mesh, not off the volume cloud."""
    v = solid.to_trimesh().vertices
    rho = np.hypot(v[:, 0], v[:, 1])
    cap = rho[v[:, 2] > 39.99].max()          # how far the bevel ate
    wall = v[rho > 9.99][:, 2].max()          # how far it dropped
    return cap, wall


# ---- the legs, measured ---------------------------------------------------
def test_cap_leg_is_the_single_distance_at_every_angle():
    """\"a single distance and an angle\": the angle may open, the
    cap leg is the distance and STAYS it - 5.000 mm at 30, 45, 60."""
    for th in (30.0, 45.0, 60.0):
        cap, _ = _mouths(_rod(th).recompute())
        assert cap == pytest.approx(5.0, abs=1e-6), f"angle {th}"


def test_wall_leg_opens_by_the_tangent():
    """The wall leg is D*tan(theta) - measured at the vertices (the
    house skirt shows at ~5e-4, so the tolerance is honest)."""
    for th in (30.0, 60.0):
        import math
        H = 5.0 * math.tan(math.radians(th))
        _, wall = _mouths(_rod(th).recompute())
        assert wall == pytest.approx(40.0 - H, abs=0.02), f"angle {th}"


def test_volume_ordering_and_pappus():
    """Wider angle, deeper bite: vol(30) > vol(45) > vol(60); the 30
    volume against Pappus' centroid theorem (triangle area D*H/2,
    centroid radius (5+10+10)/3, two rims) holds to mesh tolerance."""
    import math
    v = {th: _rod(th).recompute().volume for th in (30.0, 45.0, 60.0)}
    assert v[30.0] > v[45.0] > v[60.0]
    H = 5.0 * math.tan(math.radians(30.0))
    cut = 2 * 2 * math.pi * (0.5 * 5.0 * H) * (25.0 / 3.0)
    assert v[30.0] == pytest.approx(math.pi * 100.0 * 40.0 - cut,
                                    rel=2e-3)


# ---- the legacy branch, untouched ------------------------------------------
def test_legacy_record_keeps_the_symmetric_branch():
    """No angle in the record = the M19 triangle, byte for byte - and
    a PRE-M196 file (five-term src_key ending in 2, no angle field at
    all) recomputes ONCE through that same branch to the same number.
    45.0 typed agrees GEOMETRICALLY (approx) but is a different
    record: it stores a number the legacy does not."""
    s = _rod(None).recompute()
    assert s.volume == pytest.approx(LEGACY_VOL, rel=1e-9)
    assert _rod(None).features[-1].angle_deg is None
    d = _rod(None)
    d.recompute()
    raw = d.to_dict()
    raw["features"][-1]["src_key"] = [1.0, 2, 5.0, True, 2]   # old shape
    raw["features"][-1].pop("angle_deg", None)                # pre-M196
    d3 = Document.from_dict(json.loads(json.dumps(raw)))
    assert d3.features[-1].angle_deg is None
    assert d3.recompute().volume == pytest.approx(LEGACY_VOL, rel=1e-9)
    assert d3.features[-1].src_key[-2:] == [0.0, 4]           # re-keyed
    # (R1 raised 2 -> 3; R3 raised 3 -> 4 with the second-distance term)
    assert _rod(45.0).recompute().volume == pytest.approx(LEGACY_VOL,
                                                          rel=1e-6)


def test_the_angle_rides_the_file():
    """20 degrees through to_dict/from_dict: the NUMBER (exact, not
    the baked float32 mesh) and the ground result both survive."""
    d = _rod(20.0)
    d.recompute()
    d2 = Document.from_dict(json.loads(json.dumps(d.to_dict())))
    assert d2.features[-1].angle_deg == 20.0
    assert d2.recompute().volume == pytest.approx(d.result.volume,
                                                  rel=1e-5)


# ---- the lever and the door -------------------------------------------------
def test_the_lever_asks_an_angle_only_of_a_bevel(win, qapp):
    """\"Angle (Distance And Angle chamfer type only)\": the row opens
    on a chamfer record and NOT on a fillet one. A legacy chamfer
    shows 45.0 - equal bevel IS forty-five degrees, geometrically."""
    win.new_document()
    win.doc.add(PrimitiveFeature(name="rod", kind="cylinder",
                                 dims={"radius": 10.0, "height": 40.0}))
    win.recompute()
    ch = BodyFilletFeature(name="Ch", radius=5.0, chamfer=True)
    fl = BodyFilletFeature(name="Fl", radius=5.0, chamfer=False)
    keys_c = [f["key"] for f in win._feature_params(ch)]
    keys_f = [f["key"] for f in win._feature_params(fl)]
    assert "angle_deg" in keys_c and "angle_deg" not in keys_f
    row = [f for f in win._feature_params(ch) if f["key"] == "angle_deg"][0]
    assert row["default"] == 45.0 and row["max"] == 89.9


def test_the_door_writes_what_is_typed(win, qapp, monkeypatch):
    """Change Parameters on the chamfer feature with 30 typed: the
    record stores 30.0 exactly and the mesh follows at the mouths -
    cap leg still the 5 the dialog shows, wall leg dropped by
    5*tan(30)."""
    import math
    from tracer.ui import cmddialog
    win.new_document()
    win.doc.add(PrimitiveFeature(name="rod", kind="cylinder",
                                 dims={"radius": 10.0, "height": 40.0}))
    win.recompute()
    ch = BodyFilletFeature(name="Ch", radius=5.0, chamfer=True)
    win.doc.add(ch)
    win.recompute()
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"radius": 5.0, "chamfer": True,
                                         "angle_deg": 30.0})
    win.action_change_params(ch)
    qapp.processEvents()
    assert ch.angle_deg == 30.0
    cap, wall = _mouths(win.doc.result)
    assert cap == pytest.approx(5.0, abs=1e-6)
    assert wall == pytest.approx(40.0 - 5.0 * math.tan(
        math.radians(30.0)), abs=0.02)


def test_the_angle_row_wears_degrees(win, qapp):
    """R1b, caught by the film: ask() hands every double row the
    default ' mm' suffix, so the bevel's angle lever photographed as
    '15.0 mm' UNDER its own degree label - one door, two mouths, two
    units.  The dbl helper now says otherwise for angle rows; the
    millimetre rows ride the default untouched."""
    ch = BodyFilletFeature(name="Ch", radius=5.0, chamfer=True)
    rows = {f["key"]: f for f in win._feature_params(ch)}
    assert rows["angle_deg"].get("suffix") == "\u00b0"
    assert "suffix" not in rows["radius"]      # the mm rows ride ask()'s
    # and the label still speaks the unit in words - both mouths agree
    assert "\u00b0" in rows["angle_deg"]["label"]


# ---- R2: the chamfer door speaks the vendor's three rows ------------------
from tracer.ui import cmddialog                                        # noqa


def _rod_win(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="rod", kind="cylinder",
                                 dims={"radius": 10.0, "height": 40.0}))
    win.recompute()
    qapp.processEvents()


def test_the_chamfer_door_asks_the_vendor_three_rows(win, qapp,
                                                     monkeypatch):
    """SLD-REF-CHAMFER's dialog rows for the tool: \"Chamfer Type\",
    \"Distance\" and \"Angle (Distance And Angle chamfer type only)\".
    The command door asks all three through the house dialog - and
    offers ONLY the two types the kernel actually cuts (Two Distance
    is not promised until it exists; this list moves with the vendor).
    Choosing Distance And Angle at 5 x 30 lands a record with exactly
    those numbers, and the success sentence SPEAKS the angle."""
    calls = []

    def fake(parent, title, fields, **k):
        calls.append((title, fields))
        return {"type": "Distance And Angle", "distance": 5.0,
                "angle": 30.0}

    monkeypatch.setattr(cmddialog, "ask", fake)
    _rod_win(win, qapp)
    win._body_fillet(chamfer=True)
    qapp.processEvents()
    assert len(calls) == 1 and calls[0][0] == "Chamfer body edges"
    flds = {f["key"]: f for f in calls[0][1]}
    # R3 moved this pin: Two Distance LANDED, so the list grew to the
    # page's full three and the second-distance row joined - exactly as
    # the R2 comment promised ("it moves with the vendor when that cut
    # lands").  The page's own order rules.
    assert list(flds) == ["type", "distance", "dist2", "angle"]
    assert flds["type"]["choices"] == ["Equal Distance", "Two Distance",
                                       "Distance And Angle"]
    assert flds["angle"]["suffix"] == "\u00b0"          # R1b law rides
    assert flds["angle"]["min"] == 0.1 and flds["angle"]["max"] == 89.9
    assert flds["distance"]["min"] == 0.05
    f = win.doc.features[-1]
    assert isinstance(f, BodyFilletFeature) and f.chamfer
    assert f.radius == 5.0 and f.angle_deg == 30.0
    assert f.dist2 is None                     # ONE type per record
    assert "x 30" in win.status.currentMessage(), \
        "the sentence tells the truth about the bevel it cut"


def test_the_equal_choice_writes_no_angle(win, qapp, monkeypatch):
    """The page's parenthetical is law: the angle belongs to Distance
    And Angle ONLY. Choose Equal Distance - the typed 70 is NOTED and
    NOT written: the record stays the legacy symmetric branch, and
    the mesh drops its wall by exactly the distance."""
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"type": "Equal Distance",
                                         "distance": 2.0, "angle": 70.0})
    _rod_win(win, qapp)
    win._body_fillet(chamfer=True)
    f = win.doc.features[-1]
    assert f.chamfer and f.radius == 2.0 and f.angle_deg is None
    v = win.doc.result.to_trimesh().vertices
    rho = np.hypot(v[:, 0], v[:, 1])
    wall = v[rho > 9.99][:, 2].max()
    assert abs(wall - 38.0) < 0.05            # 40 - D*tan(45) - the skirt


def test_the_fillet_half_grew_its_rung_at_last(win, qapp,
                                               monkeypatch):
    """M196's honesty gate, kept honest as it aged: it pinned the
    fillet half at ONE row until the rung that wears SLD-REF-FILLET
    arrived (M201 R23).  The rows, in the page's printed order, all
    rest at the ONE member the kernel bakes - and the record lands
    byte-for-byte the feature the one-number lever used to birth."""
    calls = []

    def fake(parent, title, fields, **k):
        calls.append((title, fields))
        return {"radius": 3.0}

    monkeypatch.setattr(cmddialog, "ask", fake)
    _rod_win(win, qapp)
    win._body_fillet(chamfer=False)
    assert len(calls) == 1 and calls[0][0] == "Fillet"
    assert [f["key"] for f in calls[0][1]] == ["type", "radius",
                                               "rtype", "cont",
                                               "corner", "rule", "rf"]
    feat = win.doc.features[-1]
    assert isinstance(feat, BodyFilletFeature) and not feat.chamfer
    assert feat.radius == 3.0 and feat.angle_deg is None


def test_the_chamfer_door_cancel_writes_nothing(win, qapp, monkeypatch):
    """Cancel at the door leaves no record and no undo step: the
    capture happens only AFTER the dialog commits."""
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: None)
    _rod_win(win, qapp)
    before = len(win.doc.features)
    undo_n = len(win._undo)
    win._body_fillet(chamfer=True)
    assert len(win.doc.features) == before
    assert len(win._undo) == undo_n


# ---- R3: Two Distance - the page's middle type ----------------------------
def _two(d1, d2):
    d = Document("two")
    d.add(PrimitiveFeature(name="rod", kind="cylinder",
                           dims={"radius": 10.0, "height": 40.0}))
    d.add(BodyFilletFeature(name="Chamfer1", radius=d1, chamfer=True,
                            dist2=d2))
    return d


def test_two_distance_legs_measured_directly():
    """"Bevels edges based on a different distance to each side" -
    BOTH legs typed millimetres, no tangent, no trigonometry: on the
    r10 h40 rod the cap keeps a flat ring at rho 10 - d1 and the wall
    drops to 40 - d2, read straight off the vertices.  And the sides
    ARE different: 5-and-2 and 2-and-5 are different bevels."""
    cap, wall = _mouths(_two(5.0, 2.0).recompute())
    assert cap == pytest.approx(5.0, abs=1e-4)          # 10 - 5
    assert wall == pytest.approx(38.0, abs=0.05)        # 40 - 2
    cap2, wall2 = _mouths(_two(2.0, 5.0).recompute())
    assert cap2 == pytest.approx(8.0, abs=1e-4)
    assert wall2 == pytest.approx(35.0, abs=0.05)
    assert _two(5.0, 2.0).recompute().volume != \
        _two(2.0, 5.0).recompute().volume


def test_the_first_value_starts_on_both_sides():
    """The note verbatim: "The first distance value you specify applies
    to both sides of the chamfer."  Typed 5 AND 5, the second leg
    equals the first and the cut IS the legacy cut - the very same
    three points (P(0, dist2) is literally P(0, R)), the same tool,
    the same boolean.  So the comparison rides fresh-against-fresh in
    ONE environment, where it is bit-exact.  Against the banked
    constant the house tolerance rules: the last digit of a volume
    sum belongs to the library build, not to the geometry - CI's
    python 3.12 grinds this same mesh to ...618 where 3.13 lands on
    ...622 (R3b, the paid lesson).  Identity when nothing is
    approximated, the honest mirror of rung one's tan(45) lesson.
    The RECORD still differs: it stores the second value and says
    which type it is."""
    assert _two(5.0, 5.0).recompute().volume == _rod(None).recompute().volume
    assert _two(5.0, 5.0).recompute().volume == pytest.approx(LEGACY_VOL,
                                                              rel=1e-9)
    f = _two(5.0, 5.0).features[-1]
    assert f.dist2 == 5.0 and f.angle_deg is None


def test_a_record_may_not_wear_two_types():
    """The page's Type is ONE choice per selection set.  A hand-crafted
    record carrying BOTH an angle AND a second distance is a
    contradiction, and the kernel REFUSES it rather than guessing which
    leg the file meant."""
    d = Document("bad")
    d.add(PrimitiveFeature(name="rod", kind="cylinder",
                           dims={"radius": 10.0, "height": 40.0}))
    d.add(BodyFilletFeature(name="Chamfer1", radius=5.0, chamfer=True,
                            angle_deg=30.0, dist2=2.0))
    with pytest.raises(ValueError, match="not both"):
        d.recompute()


def test_the_door_offers_three_types_and_writes_the_chosen_leg(win, qapp,
                                                               monkeypatch):
    """R3 moved the R2 pin EXACTLY as that gate's comment promised:
    the combo now carries the page's full list in the page's own order
    and a second-distance row joins it.  Choose Two Distance, type 5
    AND 2 (and a 70 the type has no use for): the record carries dist2
    2.0 and NO angle - the parenthetical law mirrored - and the success
    sentence speaks both millimetres."""
    calls = []

    def fake(parent, title, fields, **k):
        calls.append(fields)
        return {"type": "Two Distance", "distance": 5.0,
                "dist2": 2.0, "angle": 70.0}

    monkeypatch.setattr(cmddialog, "ask", fake)
    _rod_win(win, qapp)
    win._body_fillet(chamfer=True)
    flds = {f["key"]: f for f in calls[0]}
    assert list(flds) == ["type", "distance", "dist2", "angle"]
    assert flds["type"]["choices"] == ["Equal Distance", "Two Distance",
                                       "Distance And Angle"]
    f = win.doc.features[-1]
    assert f.radius == 5.0 and f.dist2 == 2.0 and f.angle_deg is None
    msg = win.status.currentMessage()
    assert "at 5 mm x 2 mm" in msg, msg


def test_the_lever_opens_the_second_leg_not_the_angle(win, qapp):
    """One record, one voice: the Two Distance record's Change
    Parameters shows the second distance (a MILLIMETRE row - the R1b
    override belongs to angle rows, and mm is the truth here) and NOT
    the angle row.  A legacy bevel record still shows the angle row
    (rung one's law stands beside this one)."""
    two = BodyFilletFeature(name="Two1", radius=5.0, chamfer=True,
                            dist2=2.0)
    keys = [f["key"] for f in win._feature_params(two)]
    assert "dist2" in keys and "angle_deg" not in keys
    row = [f for f in win._feature_params(two) if f["key"] == "dist2"][0]
    assert "suffix" not in row                # rides ask()'s " mm"
    legacy = BodyFilletFeature(name="Ch", radius=5.0, chamfer=True)
    assert "angle_deg" in [f["key"] for f in win._feature_params(legacy)]


def test_the_second_distance_rides_the_file_and_the_key_grew():
    """dist2 through disk: the NUMBER is exact and the result regrounds
    at mesh tolerance; the stamp is the seven-term version-4 key.  An
    R1-ERA six-term key still mismatches by SHAPE (the version term and
    the dist2 term both differ) and recomputes ONCE through the
    untouched branch to the very same number."""
    d = _two(5.0, 1.5)
    d.recompute()
    raw = json.loads(json.dumps(d.to_dict()))
    assert raw["features"][-1]["dist2"] == 1.5
    d2 = Document.from_dict(raw)
    assert d2.features[-1].dist2 == 1.5
    assert d2.recompute().volume == pytest.approx(d.result.volume,
                                                  rel=1e-5)
    assert d.features[-1].src_key[-2:] == [1.5, 4]
    fe = raw["features"][-1]
    fe["src_key"] = fe["src_key"][:5] + [0.0, 3]        # R1-era shape
    d3 = Document.from_dict(json.loads(json.dumps(raw)))
    assert d3.recompute().volume == pytest.approx(d.result.volume,
                                                  rel=1e-9)
    assert d3.features[-1].src_key[-2:] == [1.5, 4]
