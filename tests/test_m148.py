"""M148 — assembly rung 2a: the derived frame, RIGID-ONLY carry.

LAW R grows its second half (research/body_frames.md): a joint has
always followed where a body is PLACED (rung 1's state layer); 2a
adds that it also follows the parent's RIGID STREAM MOTION — a
terminal Move/Rotate edit or a single primitive's placement carries
the welded child EXACTLY, because those edits ARE a rigid map the
kernel can read off the stream:

    D = g_now @ inv(g_bake)    (structural frames — never a bbox:
                               an asymmetric growth lies by (0,10,0))
    P'_child = P'_parent @ D @ m

which reduces BIT-EXACTLY to rung 1 when D = I (t7 pins it; the
whole 1592-gate legacy of LAW R is the real pin). Everything else —
the honest half — REFUSES and SAYS SO: growth (dims, pattern counts,
any class-none stream edit) leaves the child at the jointed pose and
appends a "grew, it did not move" line to joint_warnings. The
frame baseline (b["frame0"] = {"k": stream fingerprint minus the
rigid levers, "g": the rigid map at bake}) rides the FILE; the
derived frame itself is runtime-only and never persisted (a live
pose saved across sessions would lie). Legacy files bake silently
on first jointed recompute, byte-equal (t9) — no version bump.
Capture of a jointed body refuses guard-first (t11): capture sets
P := I and appends a Move — the child pose would JUMP by the
captured vector, and re-baking frame0 does not fix a stale m.
"""
import numpy as np
import pytest

from tracer.core import params
from tracer.core.document import (Document, MoveFeature, PrimitiveFeature,
                                  RotateFeature)
from tracer.core.geometry import Solid


def _bounds(sol):
    bb = sol.bounding_box
    return [round(v, 6) for v in (list(bb[0]) + list(bb[1]))]


def _shifted(bounds, dv):
    return [v + dv[i % 3] for i, v in enumerate(bounds)]


def _T(x, y, z):
    m = np.eye(4)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m


def _two_box_doc():
    """test_m146's builder, verbatim."""
    d = Document()
    d.add_body("A")
    d.add(PrimitiveFeature(name="boxA", kind="box",
                           dims={"dx": 10, "dy": 20, "dz": 30}))
    d.add_body("B")
    d.add(PrimitiveFeature(name="boxB", kind="box",
                           dims={"dx": 5, "dy": 5, "dz": 5}))
    d.recompute()
    return d


def _tall_doc(vec=(0.0, 0.0, 0.0)):
    """A = one box + a TERMINAL Move (R1's shape); B jointed child."""
    d = _two_box_doc()
    d.active_body = "A"
    d.add(MoveFeature(name="slideA", vec=vec))
    d.recompute()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    return d


def _m(j):
    return np.asarray(j["m"], float).reshape(4, 4)


# ---- t1: the terminal Move tail carries -------------------------------
def test_terminal_move_edit_carries_the_child():
    d = _tall_doc()
    d.recompute()
    b0 = _bounds(d._body_solids["B"])
    d.features[2].vec = (8.0, 0.0, 0.0)         # A's tail slides +8x
    d.recompute()
    assert _bounds(d._body_solids["B"]) == _shifted(b0, [8.0, 0.0, 0.0])
    d.recompute()                               # idempotent: the
    assert _bounds(d._body_solids["B"]) == _shifted(b0, [8.0, 0.0,
                                                         0.0])
    assert d.joint_warnings == []               # carried in silence


# ---- t2: the single-primitive placement carries (R2) ------------------
def test_single_primitive_placement_carries():
    d = _two_box_doc()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    b0 = _bounds(d._body_solids["B"])
    d.features[0].placement = (0.0, 6.0, 0.0)   # A's ONE primitive
    d.recompute()                               # is re-placed
    assert _bounds(d._body_solids["B"]) == _shifted(b0, [0.0, 6.0, 0.0])
    assert d.joint_warnings == []


# ---- t3: the rotate tail welds the child, orientation included --------
def test_rotate_tail_carries_welded_including_orientation():
    d = _two_box_doc()
    d.active_body = "A"
    d.add(RotateFeature(name="spinA", center=(0.0, 0.0, 0.0),
                        axis=(0.0, 0.0, 1.0), angle_deg=0.0))
    d.recompute()
    d.move_body("B", 10.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    d.features[2].angle_deg = 90.0              # A turns 90 deg CCW
    d.recompute()                               # about z: B rides
    # golden RE-DERIVED (corner-anchored 5-box at +10x, corner-
    # anchored rotation about origin): (x,y)->(-y,x) on [10..15]x[0..5]
    # -> x in [-5..0], y in [10..15], z [0..5] unchanged
    assert _bounds(d._body_solids["B"]) == [-5.0, 10.0, 0.0,
                                            0.0, 15.0, 5.0]
    assert d.joint_warnings == []


# ---- t4: growth refuses and SAYS SO (the loud half of the law) --------
def test_growth_refuses_to_carry_and_says_why():
    d = _two_box_doc()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    b0 = _bounds(d._body_solids["B"])
    d.features[0].dims["dy"] = 40.0             # A grows: NOT a move
    d.recompute()
    assert _bounds(d._body_solids["B"]) == b0   # child stays home
    assert d.joint_warnings and "grew" in d.joint_warnings[0]
    assert "A" in d.joint_warnings[0]           # names the parent


def test_class_none_stream_edits_refuse_with_the_same_voice():
    """The g9 twin (pattern count 3->5 in the spike): any edit the
    classifier cannot read as rigid refuses the same way."""
    d = _two_box_doc()
    d.active_body = "A"
    d.add(PrimitiveFeature(name="notch", kind="box",
                           dims={"dx": 2.0, "dy": 2.0, "dz": 2.0},
                           op="subtract"))
    d.recompute()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    b0 = _bounds(d._body_solids["B"])
    d.features[2].dims["dx"] = 4.0              # class-none stream
    d.recompute()                               # (two-feature base)
    assert _bounds(d._body_solids["B"]) == b0
    assert d.joint_warnings and "grew" in d.joint_warnings[0]


# ---- t5: chains fold the deltas by depth, not list order --------------
def test_chain_folds_stream_deltas():
    d = _two_box_doc()
    d.active_body = "A"
    d.add(MoveFeature(name="slideA", vec=(0.0, 0.0, 0.0)))
    d.add_body("C")
    d.add(PrimitiveFeature(name="boxC", kind="box",
                           dims={"dx": 2.0, "dy": 2.0, "dz": 2.0}))
    d.active_body = "B"
    d.add(MoveFeature(name="slideB", vec=(0.0, 0.0, 0.0)))
    d.recompute()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.move_body("C", 0.0, 7.0, 0.0)
    d.recompute()
    d.add_joint("B", "C")                       # child-before-parent
    d.add_joint("A", "B")                       # list order: DEPTH
    m_bc, m_ab = _m(d.joints[0]), _m(d.joints[1])
    d.features[2].vec = (8.0, 0.0, 0.0)         # A's tail +8x
    d.features[4].vec = (0.0, 5.0, 0.0)         # B's tail +5y
    d.recompute()
    # E_C = (P_A @ D_A @ m_AB) @ D_B @ m_BC applied to C's raw
    # stream (a corner-anchored 2-box); P_A = I here.
    expected = Solid.box(2.0, 2.0, 2.0).transformed(
        _T(8.0, 0.0, 0.0) @ m_ab @ _T(0.0, 5.0, 0.0) @ m_bc)
    assert _bounds(d._body_solids["C"]) == _bounds(expected)
    assert d.joint_warnings == []


# ---- t6: joint-free docs pay NOTHING (rung-1's identity pin, re-pinned)
def test_joint_free_doc_zero_new_calls(monkeypatch):
    d = _two_box_doc()                          # no joints at all
    calls = []
    orig = Solid.transformed
    monkeypatch.setattr(Solid, "transformed",
                        lambda self, m, *a, **k: (calls.append(m),
                                                  orig(self, m, *a,
                                                       **k))[1])
    d.recompute()
    assert calls == []                          # not one multiply
    for b in d.bodies:                          # and no frame0 key
        assert set(b) == {"name", "visible", "placement", "rot",
                          "id", "grounded"}


# ---- t7: jointed, unedited docs ride the EXACT shipped path -----------
def test_jointed_doc_call_count_and_bytes_unchanged(monkeypatch):
    d = _two_box_doc()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    calls = []
    orig = Solid.transformed
    monkeypatch.setattr(Solid, "transformed",
                        lambda self, m, *a, **k: (calls.append(m),
                                                  orig(self, m, *a,
                                                       **k))[1])
    d.recompute()
    assert len(calls) == 1                      # the shipped count:
    #                                           # one child, one call
    a = d._body_solids["B"].to_trimesh()
    d.recompute()                               # second pass
    b = d._body_solids["B"].to_trimesh()
    assert np.array_equal(a.vertices, b.vertices)   # byte-idempotent
    assert np.array_equal(a.faces, b.faces)
    assert d.joint_warnings == []


# ---- t8: carry survives save/load, int/float drift and NET deltas -----
def test_carry_survives_save_load_and_int_float_drift():
    d = Document()
    d.add_body("A")
    d.add(PrimitiveFeature(name="boxA", kind="box",
                           dims={"dx": 10, "dy": 20, "dz": 30},
                           placement=(1, 2, 3)))   # INT placement:
    d.add(MoveFeature(name="slideA", vec=(0, 0, 0)))  # int vec too
    d.add_body("B")
    d.add(PrimitiveFeature(name="boxB", kind="box", dims={"dx": 5,
                          "dy": 5, "dz": 5}))
    d.recompute()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")                       # bakes frame0 (ints)
    d.features[2].vec = (8.0, 0.0, 0.0)         # float edit, carry
    d.recompute()
    pose = _bounds(d._body_solids["B"])
    assert d.joint_warnings == []
    e = Document.from_dict(d.to_dict())         # json: ints -> floats
    e.recompute()
    assert _bounds(e._body_solids["B"]) == pose  # bake re-read clean
    e.features[0].placement = (1.0, 2.0, 13.0)  # edit AGAIN: NET vs
    e.recompute()                                # the baked baseline
    assert _bounds(e._body_solids["B"]) == _shifted(pose, [0.0, 0.0,
                                                           10.0])
    assert e.joint_warnings == []                # drift = carry, not
    #                                             # a phantom "grew"


# ---- t9: a legacy jointed file (no frame0) bakes SILENTLY -------------
def test_legacy_jointed_file_bakes_silently():
    d = _tall_doc()
    d.recompute()
    pose = _bounds(d._body_solids["B"])
    raw = d.to_dict()
    for brec in raw["bodies"]:
        brec.pop("frame0", None)                 # a pre-2a file
    e = Document.from_dict(raw)
    e.recompute()
    assert _bounds(e._body_solids["B"]) == pose  # byte-equal carry
    assert e.joint_warnings == []                # and NO warning
    e.features[2].vec = (0.0, 0.0, 6.0)          # the lazy bake is
    e.recompute()                                # a REAL baseline
    assert _bounds(e._body_solids["B"]) == _shifted(pose, [0.0, 0.0,
                                                           6.0])


# ---- t10: growth warns, the REVERT re-arms silently --------------------
def test_revert_of_growth_rearms_carry():
    d = _two_box_doc()
    d.active_body = "A"
    d.add(MoveFeature(name="slideA", vec=(0.0, 0.0, 0.0)))
    d.recompute()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    b0 = _bounds(d._body_solids["B"])
    d.features[0].dims["dy"] = 40.0              # grow: warn + hold
    d.recompute()
    assert d.joint_warnings and "grew" in d.joint_warnings[0]
    d.features[0].dims["dy"] = 20.0              # revert: SILENT
    d.recompute()
    assert d.joint_warnings == []
    d.features[2].vec = (0.0, 3.0, 0.0)          # carry re-armed
    d.recompute()
    assert _bounds(d._body_solids["B"]) == _shifted(b0, [0.0, 3.0,
                                                         0.0])
    assert d.joint_warnings == []


# ---- t11: capture of a JOINTED body refuses guard-first ----------------
def test_capture_of_jointed_body_refuses_guard_first():
    d = _two_box_doc()
    d.add_body("Free")
    d.add(PrimitiveFeature(name="boxF", kind="box",
                           dims={"dx": 1.0, "dy": 1.0, "dz": 1.0}))
    d.recompute()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    d.move_body("Free", 3.0, 0.0, 0.0)        # a placed free body:
    d.recompute()                              # capture has work to do
    n = len(d.features)
    with pytest.raises(params.ParamError):
        d.capture_body_placement("A")            # the base: refuses
    with pytest.raises(params.ParamError):
        d.capture_body_placement("B")            # the child: refuses
    assert len(d.features) == n                  # guard-FIRST: the
    #                                             # stream never moved
    d.capture_body_placement("Free")             # an unjointed body
    assert len(d.features) == n + 1              # captures normally


# ---- t12: rename rides ids; the undo file-snapshot restores the pose ---
def test_rename_and_undo_legs():
    d = _tall_doc()
    d.recompute()
    b0 = _bounds(d._body_solids["B"])
    snapshot = d.to_dict()                        # the _capture law:
    d.rename_body("A", "Atlas")                   # undo is a file
    d.features[2].vec = (8.0, 0.0, 0.0)           # class keys stream
    d.recompute()                                 # by name, joints
    assert _bounds(d._body_solids["B"]) == _shifted(b0, [8.0, 0.0,  # by id
                                                         0.0])
    assert d.joint_warnings == []
    e = Document.from_dict(snapshot)              # the UNDO leg
    e.recompute()
    assert _bounds(e._body_solids["B"]) == b0     # pose restored
