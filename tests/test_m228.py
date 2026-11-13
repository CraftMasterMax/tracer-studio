"""M201 R38 - the hole table's ORIGIN (core): the page's measuring stick.

[Create a hole table, verbatim] "In the canvas, select a drawing view to
associate with the hole table and click to place the origin." / [Tables
overview, verbatim] "Hole tables require an origin." / "Each view require
its own origin." - the second sentence's grammar is the page's, printed
exactly, and it is OWNERSHIP made physical: the store is keyed by view, so
a table cannot borrow a neighbour's stick and cannot measure from a silent
(0, 0). [Table reference, verbatim] the Origin row "Specifies the origin
used to measure hole X and Y coordinates" - so the rows answer xy measured
FROM the placed point. Arrange has exactly the two page members, lower-case
"by" and all: "by Position: Holes are located and labeled according to
their physical location to the origin" / "by Size: ... from the smallest to
largest". The origin Style prints FOUR members and the help NEVER prints
"ANSI" - a request for it is refused by name, never quietly mapped. The
reading order, the group anchor rule and every refusal NAME are TRACER
STAMPS: the pages name the orders but print no detail and no error text.
CPU-only (metadata maths, no GL, no Qt) - deliberately not a bomb file.
"""
import pytest

from tracer.core import drawing
from tracer.core.document import Document, HoleFeature, PrimitiveFeature


@pytest.fixture(scope="module")
def doc():
    """m129's proven stage: two identical M8-6H through-taps across the
    top, one plain blind hole, one counterbored - plus a SIDE bore whose
    axis lies across the top sight and must never take a top row."""
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 24, "dz": 8}))
    for x in (12, 28):
        d.add(HoleFeature(name=f"h8@{x}", op="subtract",
                          center=(x, 12, 8), normal=(0, 0, -1),
                          radius=3.4, depth=8, cut_length=8, through=True,
                          thread_pitch=1.25, thread_len=8,
                          thread_size="M8", thread_class="6H"))
    d.add(HoleFeature(name="plain", op="subtract", center=(8, 6, 8),
                      normal=(0, 0, -1), radius=2.5, depth=4, cut_length=4))
    d.add(HoleFeature(name="cb", op="subtract", center=(30, 6, 8),
                      normal=(0, 0, -1), radius=2.5, depth=4, cut_length=4,
                      cb_radius=4.5, cb_depth=3))
    d.add(HoleFeature(name="side", op="subtract", center=(20, 0, 4),
                      normal=(0, 1, 0), radius=2.0, depth=4, cut_length=4))
    d.recompute()
    return d


# ---- the origin: required, per-view, never duplicated ----------------------

def test_a_table_without_an_origin_is_refused_by_the_pages_words():
    with pytest.raises(ValueError) as e:
        drawing.require_origin({}, "top")
    msg = str(e.value)
    assert msg.startswith("HOLE_TABLE_NO_ORIGIN")
    assert "Hole tables require an origin" in msg       # verbatim


def test_each_view_keeps_its_own_origin_verbatim_law():
    shop = {}
    drawing.place_origin(shop, "top", (20.0, 12.0))
    with pytest.raises(ValueError) as e:
        drawing.require_origin(shop, "front")
    assert str(e.value).startswith("HOLE_TABLE_NO_ORIGIN")
    drawing.place_origin(shop, "front", (5.0, 1.0))
    assert drawing.require_origin(shop, "top") == (20.0, 12.0)
    assert drawing.require_origin(shop, "front") == (5.0, 1.0)


def test_a_second_placement_replaces_it_never_duplicates():
    """OURS-STAMP read from the reuse sentence ("...utilizes the Ordinate
    Dimensions origin if available"): with no ordinate family to share
    with yet, reuse can only mean never-duplicate."""
    shop = {}
    drawing.place_origin(shop, "top", (20.0, 12.0))
    drawing.place_origin(shop, "top", (21.0, 13.0))
    assert list(shop) == ["top"]
    assert shop["top"] == (21.0, 13.0)


# ---- the page's vocabularies, verbatim and closed --------------------------

def test_arrange_members_are_exactly_the_pages_two_lowercase_by():
    assert drawing.ARRANGE_MODES == ("by Position", "by Size")


def test_an_unprinted_arrange_is_refused_by_name(doc):
    with pytest.raises(ValueError) as e:
        drawing.view_hole_rows(doc, "top", (0, 0), "by Weight")
    assert str(e.value).startswith("ARRANGE_UNKNOWN")


def test_origin_style_is_the_four_page_members_and_never_ansi():
    assert drawing.ORIGIN_STYLES == ("Datum Target", "ISO Origin",
                                     "ASME Origin", "Alternate Origin")
    for s in drawing.ORIGIN_STYLES:
        assert drawing.require_style(s) == s
    with pytest.raises(ValueError) as e:
        drawing.require_style("ANSI Origin")     # the blog's word, not the
    assert str(e.value).startswith("ORIGIN_STYLE_UNKNOWN")   # help's


# ---- arrange: the two orders, the X/Y measurement ---------------------------

def test_by_position_reads_down_from_the_origin_then_right(doc):
    rows, xy = drawing.view_hole_rows(doc, "top", (20.0, 12.0),
                                      "by Position")
    assert [r["hole"] for r in rows] == ["M8-6H", "Ø 5",
                                         "Ø 5 cbore Ø 9×3"]
    assert [r["item"] for r in rows] == [1, 2, 3]      # labels follow the
    #   ORDER, not first appearance (page: "located and labeled")
    p = {r["item"]: q for r, q in zip(rows, xy)}
    assert (p[1]["x"], p[1]["y"]) == (-8.0, 0.0)       # measured FROM the
    assert (p[2]["x"], p[2]["y"]) == (-12.0, -6.0)     # origin (verbatim)
    assert (p[3]["x"], p[3]["y"]) == (10.0, -6.0)


def test_a_group_anchors_on_its_top_then_left_member(doc):
    """The twin taps sit at (12,12) and (28,12): the SAME row, so the row's
    coordinates can only come from one member - the stamp says top first,
    then left."""
    _rows, xy = drawing.view_hole_rows(doc, "top", (20.0, 12.0),
                                       "by Position")
    m8 = xy[0]
    assert (m8["x"], m8["y"]) == (-8.0, 0.0)           # (12,12), not (28,12)


def test_by_size_orders_from_smallest_to_largest(doc):
    rows, _xy = drawing.view_hole_rows(doc, "top", (20.0, 12.0), "by Size")
    assert [r["hole"] for r in rows] == ["Ø 5", "Ø 5 cbore Ø 9×3", "M8-6H"]
    assert [r["item"] for r in rows] == [1, 2, 3]


# ---- per-view population: holes IN THE VIEW, nothing else -------------------

def test_a_bore_across_the_sight_takes_no_row(doc):
    """The side bore is front-view material: hole_marks answers nothing for
    it on top, so the top table cannot print it."""
    rows, _ = drawing.view_hole_rows(doc, "top", (0, 0), "by Position")
    assert not any("Ø 4" == r["hole"] for r in rows)
    front, _xy = drawing.view_hole_rows(doc, "front", (0, 0), "by Position")
    assert [r["hole"] for r in front] == ["Ø 4"]


def test_the_iso_answers_an_empty_table_not_a_refusal(doc):
    """Page silence on host views resolved like the breakout (R37): any
    view answers; a tilted bore shows no true circle, so the iso table is
    EMPTY - emptiness is the honest projection, not an error."""
    rows, xy = drawing.view_hole_rows(doc, "iso", (0.0, 0.0), "by Position")
    assert rows == [] and xy == []


def test_qty_groups_survive_both_orders(doc):
    pos, _ = drawing.view_hole_rows(doc, "top", (20.0, 12.0), "by Position")
    size, _ = drawing.view_hole_rows(doc, "top", (20.0, 12.0), "by Size")
    assert len(pos) == len(size) == 3                  # same rows, new labels
    assert next(r for r in pos if r["hole"] == "M8-6H")["qty"] == 2
