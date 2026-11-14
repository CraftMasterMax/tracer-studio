"""M201 R39 — the parts list on the sheet: derivation law, association,
placement, direction, balloons that arrive WITH the list.  Every binding
sentence is page-printed (DWG-CREATE-PARTS-LIST, DWG-REF-TABLE-DIALOG,
DWG-REF-PARTS-LIST-DIALOG, tables section root, all fetched 2026-11-14);
the silences are OURS and NAMED in the core docstrings.

[row law, verbatim] "Item numbers are assigned to components in the
order in which they were created."  — creation order, not alphabetical,
not placement order.
[identity, verbatim] "The numbers in the balloons match the Item
numbers for each component in the parts list."
[arrival, verbatim] "Note: Balloons are automatically added to the
sheet to label the associated drawing view."
[association, verbatim] "select a drawing view to associate with the
parts list" / "Click to place the parts list on the sheet."
[direction, verbatim] "Up: Displays the header and column labels along
the bottom and orders components from the bottom up."  Down mirrors it.
"""
import numpy as np

from tracer.core.drawing import (associate_parts_list, balloon_targets,
                                 parts_list, parts_sheet_table,
                                 require_parts_column,
                                 require_parts_direction,
                                 require_structure)


class Solid:
    """Just what the core reads: a volume and a bounding box."""

    def __init__(self, volume, centre=(0.0, 0.0, 0.0), half=1.0):
        self.volume = float(volume)
        c = np.asarray(centre, float)
        self.bounding_box = (c - half, c + half)


def body(name, visible=True, material=""):
    return {"name": name, "visible": visible, "material": material}


def two_rows():
    return parts_list([body("Aard"), body("Bolt")],
                      {"Aard": Solid(1.0), "Bolt": Solid(2.0)})


def item_ys(tbl):
    """Every data-row cell of the Item column, bottom-to-top by y —
    the sheet's own geometry, read back."""
    return sorted(c["y"] for c in tbl["cells"]
                  if not c["bold"] and c["col"] == "item")


def head_y(tbl):
    return max(c["y"] for c in tbl["cells"] if c["bold"])


# ---- the creation-order law ------------------------------------------

def test_items_follow_creation_order_not_names():
    # Created Zeta first: IT is item 1 — the browser walk numbers the
    # list, the alphabet never does.
    bodies = [body("Zeta"), body("Alpha")]
    solids = {"Zeta": Solid(10.0), "Alpha": Solid(20.0)}
    rows = parts_list(bodies, solids)
    assert [r["item"] for r in rows] == [1, 2]
    assert rows[0]["description"] == "Zeta"
    assert rows[1]["description"] == "Alpha"


def test_dupes_merge_and_later_part_keeps_next_item():
    bodies = [body("Bracket 1"), body("Bracket 2"), body("Plate")]
    solids = {"Bracket 1": Solid(10.0), "Bracket 2": Solid(10.0),
              "Plate": Solid(30.0)}
    rows = parts_list(bodies, solids)
    assert [(r["item"], r["description"], r["qty"]) for r in rows] == \
        [(1, "Bracket", 2), (2, "Plate", 1)]


def test_hidden_body_off_rows_and_off_balloons():
    # The printed suppression path: "hidden from the associated views
    # and removed from the parts list."
    bodies = [body("Keep"), body("Gone", visible=False)]
    solids = {"Keep": Solid(10.0), "Gone": Solid(99.0)}
    rows = parts_list(bodies, solids)
    assert [r["description"] for r in rows] == ["Keep"]
    pins = balloon_targets(bodies, solids, "top")
    assert [p["item"] for p in pins] == [1]


# ---- balloons: identity, anchors, honesty ------------------------------

def test_balloon_items_match_row_items_exactly():
    bodies = [body("Bracket 1"), body("Bracket 2"), body("Plate"),
              body("Knob", material="ALU")]
    solids = {"Bracket 1": Solid(10.0), "Bracket 2": Solid(10.0),
              "Plate": Solid(30.0), "Knob": Solid(5.0)}
    rows = parts_list(bodies, solids)
    pins = balloon_targets(bodies, solids, "top")
    assert sorted(p["item"] for p in pins) == \
        sorted(r["item"] for r in rows)


def test_balloon_anchor_is_the_projected_centre():
    # top: page axes are model (x, y); front: (x, z) — the shared
    # _basis arithmetic, not a copy.
    bodies = [body("Stud")]
    solids = {"Stud": Solid(8.0, centre=(10.0, 20.0, 5.0))}
    (p,) = balloon_targets(bodies, solids, "top")
    assert (p["item"], round(p["x"], 9), round(p["y"], 9)) == (1, 10.0, 20.0)
    (p,) = balloon_targets(bodies, solids, "front")
    assert (round(p["x"], 9), round(p["y"], 9)) == (10.0, 5.0)


def test_unknown_solid_keeps_its_row_and_answers_no_balloon():
    # The list must never silently drop a part; a bubble cannot point
    # at a centre the document does not know (OURS, named).
    bodies = [body("Known"), body("Ghost")]
    rows = parts_list(bodies, {"Known": Solid(10.0)})
    assert [r["description"] for r in rows] == ["Known", "Ghost"]
    assert rows[1]["mass"] == "—"
    pins = balloon_targets(bodies, {"Known": Solid(10.0)}, "top")
    assert [p["item"] for p in pins] == [1]


# ---- the dialog's rows, refused by name --------------------------------

def test_structure_members_are_exactly_the_pages_two():
    assert require_structure("First Level") == "First Level"
    assert require_structure("All Levels") == "All Levels"
    try:
        require_structure("Second Level")
        raise AssertionError("unknown member must be refused")
    except ValueError as e:
        assert "PARTS_STRUCTURE_UNKNOWN" in str(e)


def test_flat_document_derives_the_same_rows_under_either_member():
    # OURS-STAMP: Tracer documents are FLAT BY CONSTRUCTION; the page
    # never prints what First Level drops for a flat design, so BOTH
    # members derive the SAME rows — gated, not assumed.
    bodies = [body("A"), body("B")]
    solids = {"A": Solid(1.0), "B": Solid(2.0)}
    assert parts_list(bodies, solids, structure="First Level") == \
        parts_list(bodies, solids, structure="All Levels")


def test_direction_members_only_up_and_down():
    assert require_parts_direction("up") == "up"
    assert require_parts_direction("down") == "down"
    try:
        require_parts_direction("sideways")
        raise AssertionError("unknown direction must be refused")
    except ValueError as e:
        assert "PARTS_DIRECTION_UNKNOWN" in str(e)


def test_columns_the_page_prints_and_the_design_can_derive():
    assert require_parts_column("Item") == "Item"
    assert require_parts_column("Mass") == "Mass"
    try:                            # printed, but no honest source
        require_parts_column("Part Number")
        raise AssertionError("unsourced column must be refused")
    except ValueError as e:
        assert "PARTS_COLUMN_NO_SOURCE" in str(e)
    try:                            # never printed at all
        require_parts_column("Finish")
        raise AssertionError("unprinted column must be refused")
    except ValueError as e:
        assert "PARTS_COLUMN_UNKNOWN" in str(e)


# ---- association and the click seat -------------------------------------

def test_association_is_one_per_view_and_replacement_is_by_law():
    # The mapping key IS the association: a second placement for the
    # SAME view replaces (the R38 origin construction), two views
    # coexist; a top-half seat answers "down" under the sheet's own
    # flip law (below), never a guessed default.
    sheet = {}
    associate_parts_list(sheet, "top", (150.0, 200.0))          # top half
    associate_parts_list(sheet, "front", (150.0, 100.0), direction="down")
    associate_parts_list(sheet, "top", (200.0, 210.0))
    assert sorted(sheet["parts_tables"]) == ["front", "top"]
    assert sheet["parts_tables"]["top"]["x"] == 200.0
    assert sheet["parts_tables"]["top"]["direction"] == "down"
    assert sheet["parts_tables"]["front"]["direction"] == "down"


def test_the_flip_law_is_decided_at_the_seat():
    # [Tables overview, verbatim] "When you place a table on the
    # bottom half of the sheet, the column labels flip to the bottom
    # of the table. For parts lists and bend tables, the numbered rows
    # are ordered from bottom to top."  A3 H = 297, mid = 148.5.
    sheet = {}
    associate_parts_list(sheet, "top", (10.0, 100.0))           # bottom half
    assert sheet["parts_tables"]["top"]["direction"] == "up"
    associate_parts_list(sheet, "front", (10.0, 200.0))         # top half
    assert sheet["parts_tables"]["front"]["direction"] == "down"
    # Locked (the Shift rung): "To lock or unlock the table flipping
    # feature, press the Shift key." - while locked, never flip:
    sheet2 = {"flip_locked": True}
    associate_parts_list(sheet2, "top", (10.0, 100.0))
    assert sheet2["parts_tables"]["top"]["direction"] == "down"
    # An EXPLICIT member (the edit dialog prints Up/Down rows) beats
    # the sheet law:
    sheet3 = {"flip_locked": True}
    associate_parts_list(sheet3, "top", (10.0, 200.0), direction="up")
    assert sheet3["parts_tables"]["top"]["direction"] == "up"


def test_shift_lock_is_one_flag_toggled():
    from tracer.core.drawing import flip_locked, toggle_flip_lock
    sheet = {}
    assert flip_locked(sheet) is False
    assert toggle_flip_lock(sheet) is True
    assert flip_locked(sheet) is True
    assert toggle_flip_lock(sheet) is False


def test_down_table_header_on_top_rows_descend_from_the_click():
    t = parts_sheet_table(two_rows(), (10.0, 100.0))
    x0, ybot, bw, h = t["rect"]
    assert round(x0, 9) == 10.0 and round(ybot + h, 9) == 100.0
    ys = item_ys(t)
    assert len(ys) == 2
    assert head_y(t) > ys[0]                    # header above EVERY row
    cells = {c["y"]: c["text"] for c in t["cells"]
             if not c["bold"] and c["col"] == "item"}
    assert cells[max(ys)] == "1"                # item 1 hangs just below it
    assert cells[min(ys)] == "2"


def test_up_table_header_along_the_bottom_first_row_just_above():
    # [verbatim] "Up: Displays the header and column labels along the
    # bottom and orders components from the bottom up."
    t = parts_sheet_table(two_rows(), (10.0, 40.0), direction="up")
    x0, ybot, bw, h = t["rect"]
    assert round(ybot, 9) == 40.0                # the click seats the bottom
    hy = head_y(t)
    assert abs(hy - 42.5) < 1e-9                 # header band is the bottom
    ys = item_ys(t)                              # bottom-to-top by y
    assert ys[0] > hy                            # first row sits ON the header
    rows_by_y = sorted(ys)                       # rising y = later items
    cells = {c["y"]: c["text"] for c in t["cells"]
             if not c["bold"] and c["col"] == "item"}
    assert cells[rows_by_y[0]] == "1"            # item 1 LOWEST [verbatim]
    assert cells[rows_by_y[1]] == "2"


def test_overflow_is_counted_in_both_directions_never_silent():
    rows = parts_list([body(f"P {i}") for i in range(30)],
                      {f"P {i}": Solid(1.0 + i) for i in range(30)})
    assert len(rows) == 30
    tight = parts_sheet_table(rows, (10.0, 60.0))       # 50 mm of room
    open_up = parts_sheet_table(rows, (10.0, 60.0), direction="up")
    n_tight = int(50 // 5) - 1                           # minus the header
    assert tight["overflow"] == 30 - n_tight > 0
    assert open_up["overflow"] == 0                      # 227 mm fits 30
    shown = len({c["y"] for c in tight["cells"] if not c["bold"]})
    assert shown + tight["overflow"] == len(rows)        # nothing vanished
