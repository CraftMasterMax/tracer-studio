"""Placement ≠ Feature — the architecture boundary the research pinned.

Fusion's own manual (AU CP124896 p.31, joint report §1): moving a
component "is a change in the kinematic state of the assembly, NOT a
parametric change, so NO FEATURE WILL BE CREATED in the timeline".
Tracer encodes that as body STATE: `placement` (vector) + `rot`
(4x4) applied by recompute AFTER each body's feature stream — the
timeline never sees a feature, and Capture Position is the explicit
promotion to parametric (Rotate+Move), because Fusion only bakes
placement into the design when the user says so.

A MoveFeature (M53) still exists and stays the PARAMETRIC path —
Fusion's own body Move command creates one; components are the ones
that move state-fully. Both paths are pinned here, and old files
(bodies without the fields) must keep recomputing.
"""
import pytest


def _two_box_doc():
    from tracer.core.document import Document, PrimitiveFeature
    d = Document()
    d.add_body("A")
    d.add(PrimitiveFeature(name="boxA", kind="box",
                           dims={"dx": 10, "dy": 20, "dz": 30}))
    d.add_body("B")
    d.add(PrimitiveFeature(name="boxB", kind="box",
                           dims={"dx": 5, "dy": 5, "dz": 5}))
    d.recompute()
    return d


def _bounds(sol):
    bb = sol.bounding_box
    return [round(v, 6) for v in (list(bb[0]) + list(bb[1]))]


def test_move_is_state_not_timeline():
    d = _two_box_doc()
    n0 = len(d.features)
    d.move_body("A", 100, 0, 0)
    d.recompute()
    assert len(d.features) == n0                 # NO feature was created
    a = d._body_solids["A"]
    b = d._body_solids["B"]
    assert _bounds(a)[0] == pytest.approx(100.0)
    assert _bounds(b)[0] == pytest.approx(0.0)   # B never moved: per-body


def test_state_is_per_body_independent():
    d = _two_box_doc()
    d.move_body("A", 0, 5, 0)
    d.move_body("B", 0, 0, 9)
    d.recompute()
    assert _bounds(d._body_solids["A"])[1] == pytest.approx(5.0)
    assert _bounds(d._body_solids["B"])[5] == pytest.approx(14.0)


def test_rotation_state_spins_without_features():
    d = _two_box_doc()                           # A is 10 x 20 x 30
    d.rotate_body("A", 90.0, axis=(0, 0, 1))
    d.recompute()
    bb = d._body_solids["A"].bounding_box
    assert bb[0][0] == pytest.approx(-20.0, abs=1e-4)   # x<->y, centred
    assert bb[1][0] == pytest.approx(0.0, abs=1e-4)
    assert bb[0][1] == pytest.approx(0.0, abs=1e-4)
    assert bb[1][1] == pytest.approx(10.0, abs=1e-4)
    assert len(d.features) == 2                  # still state, not timeline


def test_capture_promotes_state_to_parametric_features():
    d = _two_box_doc()
    d.rotate_body("A", 90.0, axis=(0, 0, 1))
    d.move_body("A", 40, 0, 0)
    d.recompute()
    before = _bounds(d._body_solids["A"])
    made = d.capture_body_placement("A")
    d.recompute()
    after = _bounds(d._body_solids["A"])
    assert [f.name for f in made] == ["Capture Rot", "Capture Move"]
    assert before == pytest.approx(after, abs=1e-4)   # identical geometry…
    a_body = next(b for b in d.bodies if b["name"] == "A")
    assert a_body["placement"] == [0.0, 0.0, 0.0]
    assert a_body["rot"] is None                 # …zero state, real feats
    mv = made[1]
    mv.vec = (40, 10, 0)                         # parametric means EDITABLE
    d.recompute()
    assert _bounds(d._body_solids["A"])[1] == pytest.approx(10.0, abs=1e-4)


def test_placement_survives_save_and_load(tmp_path):
    from tracer.core import io
    d = _two_box_doc()
    d.move_body("A", 7, 0, 3)
    d.recompute()
    p = tmp_path / "x.tracer"
    io.save_document(d, p)
    d2 = io.load_document(p)
    d2.recompute()
    lo = d2._body_solids["A"].bounding_box[0]
    assert lo[0] == pytest.approx(7.0)
    assert lo[2] == pytest.approx(3.0)


def test_legacy_body_dicts_without_state_fields_recompute():
    d = _two_box_doc()
    for b in d.bodies:                           # pre-placement file shape
        b.pop("placement", None)
        b.pop("rot", None)
    d.recompute()                                # must not raise
    assert _bounds(d._body_solids["A"])[5] == pytest.approx(30.0)


def test_result_union_reflects_placement():
    d = _two_box_doc()
    d.move_body("B", 500, 0, 0)
    d.recompute()
    bb = d.result.bounding_box
    assert bb[1][0] == pytest.approx(505.0, abs=1e-4)   # the PART sees it
