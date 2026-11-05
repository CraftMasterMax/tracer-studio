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
    assert d3.features[-1].src_key[-2:] == [0.0, 3]           # re-keyed
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
    assert list(flds) == ["type", "distance", "angle"]
    assert flds["type"]["choices"] == ["Equal Distance",
                                       "Distance And Angle"]
    assert flds["angle"]["suffix"] == "\u00b0"          # R1b law rides
    assert flds["angle"]["min"] == 0.1 and flds["angle"]["max"] == 89.9
    assert flds["distance"]["min"] == 0.05
    f = win.doc.features[-1]
    assert isinstance(f, BodyFilletFeature) and f.chamfer
    assert f.radius == 5.0 and f.angle_deg == 30.0
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


def test_the_fillet_half_still_asks_its_one_radius(win, qapp,
                                                   monkeypatch):
    """Honesty gate: only the CHAMFER branch moved. The fillet half of
    the same command still asks ONE number (Shell.getDouble - which is
    itself one row of the same house dialog, key \"v\") - no Type, no
    Angle, no invented rows."""
    calls = []

    def fake(parent, title, fields, **k):
        calls.append((title, fields))
        return {"v": 3.0}

    monkeypatch.setattr(cmddialog, "ask", fake)
    _rod_win(win, qapp)
    win._body_fillet(chamfer=False)
    assert len(calls) == 1 and calls[0][0] == "Fillet body edges"
    assert [f["key"] for f in calls[0][1]] == ["v"]
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
