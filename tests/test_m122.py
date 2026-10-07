"""M122 (assembly phase 1) — interference as geometry, not a dialog.

The joint report's verdict: Fusion's Interference command computes a
clash and THROWS THE GEOMETRY AWAY (InterferenceResults carries volumes,
never a solid). Tracer's collision layer keeps both halves of the
promise from the same report: honest numbers (core/interference.pairs)
AND the clash as a live body (InterferenceFeature) that re-solves on
recompute — including when a body moves by pure kinematic PLACEMENT
STATE, no timeline feature involved.

Touching is not clashing: two bodies sharing only a face interfere
zero — the same sane default Fusion picked.
"""


def _two_overlapping(shift=5.0):
    from tracer.core.document import Document, PrimitiveFeature
    d = Document()
    d.add_body("A")
    d.add(PrimitiveFeature(name="a", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10}))
    d.add_body("B")
    d.add(PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10},
                           placement=(shift, 0, 0)))
    d.recompute()
    return d


def test_pairs_reports_the_exact_overlap():
    from tracer.core import interference
    d = _two_overlapping()
    hits = interference.pairs(d.body_solids())
    assert len(hits) == 1
    assert hits[0]["a"] == "A" and hits[0]["b"] == "B"
    assert abs(hits[0]["volume"] - 500.0) < 1e-6      # 5×10×10


def test_touching_is_not_clashing():
    from tracer.core import interference
    d = _two_overlapping(shift=10.0)                  # face to face
    assert interference.pairs(d.body_solids()) == []


def test_far_apart_bodies_never_reach_the_boolean():
    from tracer.core import interference
    d = _two_overlapping(shift=40.0)
    assert interference.pairs(d.body_solids()) == []


def test_the_clash_is_a_live_body():
    d = _two_overlapping()
    b, _f = d.add_interference("A", "B")
    d.recompute()
    clash = d.body_solids()[b["name"]]
    assert abs(clash.volume - 500.0) < 1e-3
    assert clash.bounding_box[0].round(6).tolist() == [5.0, 0.0, 0.0]


def test_the_clash_follows_kinematic_motion():
    """The beat: move B by PLACEMENT STATE (no feature) and the clash
    body re-solves to the new overlap — Fusion has nothing like it."""
    d = _two_overlapping()
    b, _f = d.add_interference("A", "B")
    d.recompute()
    d.move_body("B", 3, 0, 0)                         # overlap now 2×10×10
    d.recompute()
    assert abs(d.body_solids()[b["name"]].volume - 200.0) < 1e-3
    d.move_body("B", 5, 0, 0)                         # apart: empty body
    d.recompute()
    assert d.body_solids()[b["name"]].volume < 1e-9   # not an error


def test_clash_bodies_round_trip_through_a_file(tmp_path):
    from tracer.core import io as fio
    d = _two_overlapping()
    b, _f = d.add_interference("A", "B")
    d.recompute()
    v0 = d.body_solids()[b["name"]].volume
    p = fio.save_document(d, tmp_path / "m122.tracer")
    e = fio.load_document(p)
    e.recompute()
    names = [x["name"] for x in e.body_list()]
    assert b["name"] in names
    assert abs(e.body_solids()[b["name"]].volume - v0) < 1e-9


def test_repeat_runs_get_numbered_bodies():
    d = _two_overlapping()
    b1, _ = d.add_interference("A", "B")
    b2, _ = d.add_interference("A", "B")
    assert b1["name"] != b2["name"]
    assert b2["name"] == b1["name"] + " 2"


def test_source_names_are_checked_early():
    d = _two_overlapping()
    import pytest
    with pytest.raises(KeyError):
        d.add_interference("A", "Ghost")
