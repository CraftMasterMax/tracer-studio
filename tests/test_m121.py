"""M121 — the interlock family: Boss · Snap Fit · Rest · Lip.

Fusion gates all four behind the paid Plastic extension (verified: every
help page carries the extension banner). They are pure 2D-profile +
boolean geometry — our kernel's home turf — so Tracer ships them free
as parametric feature pairs, one grammar: a CARRY tool unions into the
body below the interface plane, a MATE tool subtracts the clearance from
the body above it.

The promises pinned here:
  * every tool's volume matches hand-worked analytic arithmetic
    (shoelace × width, cylinder, ring) — no silent fudge;
  * THE reason the family exists: a mated pair assembles with
    collision volume ≈ 0 (our first honest use of the interference
    measure the joint report handed us — (a & b).volume);
  * suppression breaks that promise LOUDLY (mate suppressed → real
    collision), proving the assembly tests are not vacuous;
  * nonsense parameters fail BEFORE touching a feature stream;
  * files round-trip: save, reload, recompute, identical volumes.
"""
import math

import pytest


def _stacked():
    """Two bodies meeting at z = 0: 60×40×6 below, 60×40×8 above."""
    from tracer.core.document import Document, PrimitiveFeature
    d = Document()
    d.add_body("Lower")
    d.add(PrimitiveFeature(name="base", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 6},
                           placement=(-30, -20, -6)))
    d.add_body("Upper")
    d.add(PrimitiveFeature(name="lid", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 8},
                           placement=(-30, -20, 0)))
    d.recompute()
    return d


def _vol(s):
    return s.volume


def _collision(d):
    a = d._body_solids["Lower"]
    b = d._body_solids["Upper"]
    return a.intersect(b).volume


def test_boss_tools_are_cylinder_arithmetic():
    from tracer.core.interlock import tools
    t = tools("boss", shaft_d=8.0, height1=6.0, height2=6.0,
              clearance=0.2)
    v = t["carry"].volume
    exp = math.pi * 4.0 ** 2 * 12.0            # r²·(h1+h2)
    assert abs(v - exp) / exp < 1e-3
    v = t["mate"].volume
    exp = math.pi * 4.2 ** 2 * 6.0             # (r+δ)²·h2
    assert abs(v - exp) / exp < 1e-3


def test_snapfit_hook_is_chamfered_block_plus_window():
    from tracer.core.interlock import tools
    t = tools("snapfit", length=10.0, width=6.0, height=2.0, lead=1.0,
              depth=2.2, clearance=0.2)
    hook = t["carry"]
    lo, hi = hook.bounding_box
    assert list(lo.round(6)) == [0.0, -3.0, 0.0]
    assert list(hi.round(6)) == [10.0, 3.0, 2.0]
    v = hook.volume
    exp = (10 * 2 - 0.5 * 1 * 1) * 6           # (L·h − c²/2)·w
    assert abs(v - exp) / exp < 1e-6
    v = t["mate"].volume
    exp = (10 + 0.4) * (6 + 0.4) * 2.2         # window with δ all round
    assert abs(v - exp) / exp < 1e-6


def test_rest_cutter_is_a_stepped_pair_of_cylinders():
    from tracer.core.interlock import tools
    t = tools("rest", seat_d=10.0, hole_d=6.0, depth=3.0, reach=12.0)
    assert t["carry"] is None                  # one-sided by design
    v = t["mate"].volume
    exp = math.pi * 5.0 ** 2 * 3.0 + math.pi * 3.0 ** 2 * 12.0
    assert abs(v - exp) / exp < 1e-3


def test_lip_bead_and_channel_are_rings():
    from tracer.core.interlock import tools
    t = tools("lip", outer_w=60.0, outer_d=40.0, thickness=2.0,
              height=5.0, depth=5.0, clearance=0.2)
    v = t["carry"].volume
    exp = (60 * 40 - 56 * 36) * 5              # rim ring × height
    assert abs(v - exp) / exp < 1e-6
    v = t["mate"].volume
    exp = (60.4 * 40.4 - 55.6 * 35.6) * 5      # ring grown by δ both sides
    assert abs(v - exp) / exp < 1e-6


@pytest.mark.parametrize("kind,geo", [
    ("boss", dict(shaft_d=8.0, height1=5.0, height2=7.0)),
    ("snapfit", dict(length=10.0, width=6.0, height=2.0, lead=1.0,
                     depth=2.2)),
    ("lip", dict(outer_w=30.0, outer_d=20.0, thickness=2.0, height=4.0,
                 depth=4.2)),
])
def test_every_pair_assembles_without_collision(kind, geo):
    """The promise the family exists for: printed, pressed together,
    ZERO interference — the clearance actually clears."""
    d = _stacked()
    v0 = _vol(d._body_solids["Lower"]), _vol(d._body_solids["Upper"])
    d.add_interlock(kind, "Lower", "Upper", clearance=0.2, **geo)
    d.recompute()
    assert _collision(d) < 0.5
    # and both bodies changed: the pair really is two-sided
    v1 = _vol(d._body_solids["Lower"]), _vol(d._body_solids["Upper"])
    assert v1[0] != v0[0] and v1[1] != v0[1]


def test_suppressed_mate_makes_the_collision_real():
    """Honesty guard: if the clearance is switched off, the interference
    measure must FIND the interference — the zero above is geometry,
    not a broken detector."""
    d = _stacked()
    feats = d.add_interlock("boss", "Lower", "Upper", shaft_d=8.0,
                            height1=5.0, height2=6.0, clearance=0.2)
    d.recompute()
    assert _collision(d) < 0.5
    [f for f in feats if f.role == "mate"][0].suppressed = True
    d.dirty = True
    d.recompute()
    pinned = math.pi * 4.0 ** 2 * 6.0          # the full post inside lid
    assert _collision(d) > pinned * 0.9


def test_rest_shelf_removes_exactly_the_stepped_volume():
    from tracer.core.document import Document, PrimitiveFeature
    d = Document()
    d.add_body("Base")
    d.add(PrimitiveFeature(name="wall", kind="box",
                           dims={"dx": 40, "dy": 40, "dz": 10},
                           placement=(-20, -20, -10)))
    d.recompute()
    v0 = _vol(d._body_solids["Base"])
    d.add_interlock("rest", "Base", seat_d=10.0, hole_d=6.0, depth=3.0,
                    reach=12.0)
    d.recompute()
    removed = v0 - _vol(d._body_solids["Base"])
    # seat ring 3 deep + pilot only 7 more deep (body is 10 thick)
    exp = math.pi * 25 * 3 + math.pi * 9 * 7
    assert abs(removed - exp) / exp < 1e-3


def test_nonsense_never_touches_a_feature_stream():
    d = _stacked()
    n0 = len(d.features)
    with pytest.raises(ValueError):
        d.add_interlock("boss", "Lower", "Upper", shaft_d=0.3,
                        height1=5.0, height2=7.0, clearance=0.2)
    with pytest.raises(ValueError):
        d.add_interlock("snapfit", "Lower", "Upper", length=10.0,
                        width=6.0, height=2.0, lead=3.0, depth=2.2)
    with pytest.raises(ValueError):
        d.add_interlock("wormhole", "Lower", "Upper")
    assert len(d.features) == n0


def test_flip_exchanges_the_bodies_and_still_assembles():
    d = _stacked()
    d.add_interlock("boss", "Lower", "Upper", z0=0.0, flip=True,
                    shaft_d=8.0, height1=5.0, height2=7.0,
                    clearance=0.2)
    d.recompute()
    # carried from ABOVE now: the lid grows, the base only loses the
    # clearance cut
    assert _collision(d) < 0.5
    carried = [f for f in d.features if getattr(f, "role", "") == "carry"]
    assert carried[0].body == "Upper"


def test_interlocks_round_trip_through_a_file(tmp_path):
    from tracer.core import io as fio
    d = _stacked()
    d.add_interlock("lip", "Lower", "Upper", outer_w=30.0, outer_d=20.0,
                    thickness=2.0, height=4.0, depth=4.2, clearance=0.2)
    d.recompute()
    before = [_vol(s) for s in d.body_solids().values()]
    p = fio.save_document(d, tmp_path / "m121.tracer")
    e = fio.load_document(p)
    e.recompute()
    after = [_vol(s) for s in e.body_solids().values()]
    assert len(e.features) == len(d.features)
    for b, a in zip(before, after):
        assert abs(a - b) / b < 1e-9
