"""M201 R40 - the balloon family's core arithmetic, page-law gates.

Anchors [verbatim]: "Select an edge of the component to identify in a
drawing view." / "For Patent type balloons, click to place the bend
point for the leader." / Type - "Standard: Creates a leader with a
straight line" / "Patent: Creates a leader with a curved spline"
[Balloon reference: the dialog is ONE row, two members] / "The
numbers in the balloons match the Item numbers for each component in
the parts list." / "Item numbers are assigned to components in the
order in which they were created." [hub - the numbering is the
DESIGN's law, not the table's: an item exists before any list seats]
/ "The balloon updates and the parts list sorts to reflect the new
number." / "The number will automatically increment as you select
balloons or bend identifiers" [Renumber reference, no terminal period
as published] / "The left edge of each balloon aligns along the line.
The balloons distribute equally between the two points." [Align]. The
family prints ZERO "cannot"/"must" (computed scan) - so every refusal
here is identity or the page's own words, and every unprinted geometry
(hit region, bubble radius, station inclusivity) is OURS, named.
"""
import numpy as np
import pytest

from tracer.core.balloon import (align_balloons, apply_renumber,
                                 balloon_entry, balloon_item_at,
                                 place_balloon, renumber_map,
                                 renumbered_rows, require_balloon_type)
from tracer.core.document import Document, PrimitiveFeature
from tracer.core.drawing import balloon_targets, parts_list


@pytest.fixture(scope="module")
def doc():
    """Three parts in three bodies - the merge law needs two IDENTICAL
    blocks (item 1 qty 2) and a plate (item 2) that COVERS both in the
    top view, so the overlap rule (smallest region wins) is load-bearing."""
    d = Document()
    for nm, dims in (("block 1", {"dx": 14, "dy": 10, "dz": 6}),
                     ("block 2", {"dx": 14, "dy": 10, "dz": 6}),
                     ("plate", {"dx": 40, "dy": 24, "dz": 2})):
        d.add_body(nm)
        d.add(PrimitiveFeature(name=nm, kind="box", dims=dims))
    d.recompute()
    return d


def _bs(d):
    return d.body_list(), d.body_solids()


# ---- the dialog's own door: ONE row, two members ---------------------------

def test_a_the_dialog_prints_exactly_two_types():
    assert require_balloon_type("Standard") == "Standard"
    assert require_balloon_type("Patent") == "Patent"
    with pytest.raises(ValueError) as e:
        require_balloon_type("Circle")
    assert "BALLOON_TYPE_UNKNOWN" in str(e.value)     # refused BY NAME;
    #   the Balloon reference page prints only Standard and Patent


def test_b_identity_is_shared_arithmetic(doc):
    """balloon_item_at must number parts with the SAME walk parts_list
    and balloon_targets use - three functions, one item law (an item
    the table shows and a balloon points at can never disagree)."""
    rows = parts_list(*_bs(doc))
    assert [(r["item"], r["description"], r["qty"]) for r in rows] == \
        [(1, "block", 2), (2, "plate", 1)]
    pins = balloon_targets(*_bs(doc), "top")
    assert sorted(p["item"] for p in pins) == [1, 2]


# ---- "Select an edge of the COMPONENT" --------------------------------------

def test_c_a_click_on_the_plate_answers_the_plate(doc):
    #   plate-only territory: (30, 10) is inside the 40x24 plate, outside
    #   both 14x10 blocks (which sit at the origin corner by dims)
    it = balloon_item_at(*_bs(doc), "top", (35.0, 15.0))
    assert it == 2


def test_d_the_overlap_goes_to_the_smaller_region(doc):
    """The blocks sit UNDER the plate in top view (all z>0 share the
    projected sheet); a click on their corner belongs to the tighter
    claim - the block, item 1 (OURS, named in the function)."""
    it = balloon_item_at(*_bs(doc), "top", (2.0, 2.0))
    assert it == 1


def test_e_bare_paper_is_no_component(doc):
    """[verbatim] "Select an edge of the component to identify" - paper
    answers None and the UI says no in the page's words. Not a printed
    prohibition (the family has none): the refusal IS the sentence."""
    assert balloon_item_at(*_bs(doc), "top", (60.0, 60.0)) is None


def test_f_a_hidden_component_holds_no_item(doc):
    """Hide the plate: its region vanishes AND the walk re-numbers the
    blocks' rows exactly like parts_list does (the item a balloon
    carries tracks the list, live, every click)."""
    doc.set_body_visible("plate", False)
    try:
        assert balloon_item_at(*_bs(doc), "top", (35.0, 15.0)) is None
        rows = parts_list(*_bs(doc))
        assert [r["item"] for r in rows] == [1] and rows[0]["qty"] == 2
    finally:
        doc.set_body_visible("plate", True)


# ---- the entry: anchor rides design, bubble rides paper ---------------------

def test_g_the_standard_drops_the_bend_it_was_never_offered():
    e = balloon_entry(1, (3.0, 4.0), (50.0, 20.0), "Standard",
                      bend=(9.0, 9.0))
    assert "bend" not in e                            # the page draws the
    #   bend point FOR PATENT TYPE BALLOONS - a Standard has no spline,
    #   so it carries no phantom control point (OURS, named)
    assert e["item"] == 1 and e["x"] == 3.0 and e["by"] == 20.0


def test_h_the_patent_keeps_its_bend_point():
    e = balloon_entry(2, (3.0, 4.0), (50.0, 20.0), "Patent",
                      bend=(30.5, 12.25))
    assert e["type"] == "Patent" and e["bend"] == pytest.approx(
        (30.5, 12.25))


def test_i_a_place_replaces_by_item_moves_the_balloon(doc):
    """[verbatim Note] "You can add, delete, move, or re-associate
    balloons" - a re-place of the SAME item is the move: one pin per
    item per view (identity law), every UNRELATED pin survives (R39's
    replace-by-Item, the hand-placed pin and the auto pin alike)."""
    pins = [{"item": 1, "x": 1.0, "y": 1.0, "bx": 20.0, "by": 20.0,
             "type": "Standard"},
            {"item": 2, "x": 2.0, "y": 2.0, "bx": 30.0, "by": 30.0,
             "type": "Standard"}]
    moved = place_balloon(pins, balloon_entry(1, (1.5, 1.5), (25.0, 22.0)))
    assert len(moved) == 2
    got = {p["item"]: p for p in moved}
    assert got[1]["bx"] == 25.0 and got[2]["bx"] == 30.0   # 2 rode untouched


# ---- Renumber: the page's arithmetic, nothing invented ----------------------

def test_j_the_number_increments_as_you_select():
    """[verbatim] "The number will automatically increment as you select
    balloons or bend identifiers" - selection order + start + step 1,
    exactly."""
    assert renumber_map([3, 1, 2], 5) == {3: 5, 1: 6, 2: 7}
    assert renumber_map([2], 1) == {2: 1}


def test_k_a_number_below_one_and_a_double_pick_refuse():
    with pytest.raises(ValueError) as e:
        renumber_map([1], 0)
    assert "BALLOON_RENUMBER_START" in str(e.value)   # identity: the
    #   balloon IS the table's Item, and items count parts from 1
    with pytest.raises(ValueError) as e:
        renumber_map([1, 1], 1)
    assert "BALLOON_RENUMBER_DUPLICATE" in str(e.value)


def test_l_the_balloons_renumber_and_the_list_sorts():
    """"The balloons renumber on the sheet as you select them." +
    "The balloon updates and the parts list sorts to reflect the new
    number." - renumber WRITES BACK: rows stay derived, wear the new
    number, and RE-ORDER by it. Identity travels with the row."""
    pins = [{"item": 1, "x": 0, "y": 0}, {"item": 2, "x": 0, "y": 0}]
    m = renumber_map([1, 2], 4)                       # 1->4, 2->5
    assert apply_renumber(pins, m) == [{"item": 4, "x": 0, "y": 0},
                                       {"item": 5, "x": 0, "y": 0}]
    rows = [{"item": 1, "description": "block", "qty": 2},
            {"item": 2, "description": "plate", "qty": 1},
            {"item": 3, "description": "lug", "qty": 1}]
    out = renumbered_rows(rows, {3: 1, 1: 3})         # lug leads now
    assert [(r["item"], r["description"]) for r in out] == \
        [(1, "lug"), (2, "plate"), (3, "block")]
    untouched = apply_renumber([{"item": 9}], m)
    assert untouched[0]["item"] == 9                  # unlisted keeps its own


# ---- Align: left edge on the line, equal stations between -------------------

def test_m_align_is_left_edge_plus_equal_distribution():
    """[verbatim] "The left edge of each balloon aligns along the line.
    The balloons distribute equally between the two points." Three
    pins, a horizontal line 0..10: stations 0/5/10, each centre pushed
    one radius ALONG the line so the left edge lands ON it (OURS named:
    r is the painter's). Anchors ride untouched - only the bubbles move."""
    entries = [{"item": 1, "x": 1.0, "y": 1.0, "bx": 99.0, "by": 99.0},
               {"item": 2, "x": 2.0, "y": 2.0, "bx": 77.0, "by": 77.0},
               {"item": 3, "x": 3.0, "y": 3.0, "bx": 55.0, "by": 55.0}]
    out = align_balloons(entries, (0.0, 0.0), (10.0, 0.0), r=3.4)
    assert [round(p["bx"], 4) for p in out] == [3.4, 8.4, 13.4]
    assert [round(p["by"], 4) for p in out] == [0.0, 0.0, 0.0]
    assert [(p["x"], p["y"]) for p in out] == [(1.0, 1.0), (2.0, 2.0),
                                               (3.0, 3.0)]
    assert [p["item"] for p in out] == [1, 2, 3]


def test_n_align_grammar_one_two_and_degenerate():
    assert align_balloons([], (0, 0), (5, 5)) == []    # nothing selected:
    #   nothing moved (the page selects balloons first, then Enter)
    solo = align_balloons([{"item": 1, "x": 0, "y": 0}], (2.0, 1.0),
                          (8.0, 1.0), r=2.0)           # one balloon: the
    assert solo[0]["bx"] == pytest.approx(4.0)         #   START station
    assert solo[0]["by"] == pytest.approx(1.0)
    with pytest.raises(ValueError) as e:
        align_balloons([{"item": 1}], (4.0, 4.0), (4.0, 4.0))
    assert "BALLOON_ALIGN_DEGENERATE" in str(e.value)  # "place the start
    #   point ... click to place the END point" - two clicks, one line


def test_o_the_pages_typo_and_the_printed_period():
    """SHIP PROOF of verbatim work: the task page prints "a curves
    spline" (typo) and the reference page prints "a curved spline"; the
    increment sentence ships WITHOUT its terminal period. Our storage
    follows the reference page's SPELLED-CORRECT member names, which is
    the dialog's own door ruling its own vocabulary."""
    from tracer.core.balloon import BALLOON_TYPES
    assert BALLOON_TYPES == ("Standard", "Patent")
    e = balloon_entry(1, (0, 0), (0, 0), "Patent", bend=(1, 1))
    assert e["type"] == "Patent" and isinstance(
        np.asarray(e["bend"], float), np.ndarray)
