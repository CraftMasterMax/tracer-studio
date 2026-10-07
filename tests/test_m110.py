"""M110 — the parts list (BOM) and balloons, per ISO 7573/6433.

A drawing that names no parts is decoration.  Fusion docks a parts
list against the title block and pins a numbered balloon to every
body; so does Tracer — built from what a mesh document TRULY knows:
body names, solid volumes, and a published-density table.

Core contract (this file's first half): parts_list() merges identical
bodies (same stem + same volume + same material) into one row with a
qty, keeps hidden bodies off the sheet, and never drops a body whose
mass is unknown — it prints "—" instead of lying.  masses are row
totals (unit mass × qty), the convention spreadsheets expect.
parts_list_table() resolves rows to the same rect/lines/cells shape as
the M108 title block, docked at its top edge and reading bottom-to-top
(ISO 7573's on-sheet sequence), with an honest overflow counter.
"""
import pytest

pytest.importorskip("PySide6")

from tracer.core import drawing                                 # noqa: E402
from tracer.core import materials                               # noqa: E402
from tracer.core.drawing import parts_list, parts_list_table, \
    title_block, _stem                                          # noqa: E402


class FakeSolid:
    def __init__(self, volume):
        self.volume = volume


# ---- materials: densities speak, never mutate --------------------------

def test_default_absent_material_yields_no_mass():
    assert materials.mass_g(1000.0, None) is None
    assert materials.mass_g(1000.0, "Unobtainium") is None


def test_pla_mass_one_cm3():
    assert materials.mass_g(1000.0, "PLA") == pytest.approx(1.24)


def test_steel_mass_scales_linearly():
    assert materials.mass_g(10_000.0, "Steel") == pytest.approx(78.5)


def test_unknown_names_print_em_dash():
    assert materials.mass_str(None) == "—"


def test_mass_speaks_grams_then_kg():
    assert materials.mass_str(12.34) == "12.3 g"
    assert materials.mass_str(1234.0) == "1.23 kg"
    assert materials.mass_str(2.5, unit="kg") == "0.00 kg"


def test_names_sorted_and_default_present():
    assert materials.NAMES == sorted(materials.NAMES)
    assert materials.DEFAULT in materials.MATERIALS


# ---- _stem: the auto-suffix convention, and its guards ------------------

@pytest.mark.parametrize("name,stem", [
    ("Bracket 12", "Bracket"),
    ("Leg-3", "Leg"),
    ("Body 2", "Body"),
    ("C3", "C3"),          # digit glued to a single letter is a NAME
    ("Body1", "Body1"),    # ditto
    ("Panel", "Panel"),
])
def test_stem(name, stem):
    assert _stem(name) == stem


# ---- parts_list: rows from truth ----------------------------------------

def test_rows_one_per_visible_body():
    bodies = [{"name": "Base 1", "visible": True},
              {"name": "Lid", "visible": True}]
    solids = {"Base 1": FakeSolid(5000.0), "Lid": FakeSolid(2000.0)}
    rows = parts_list(bodies, solids)
    assert [r["item"] for r in rows] == [1, 2]
    assert rows[0]["description"] == "Base 1"
    assert rows[0]["qty"] == 1
    assert rows[0]["material"] == "—"
    assert rows[0]["mass"] == "—"          # unknown material: no mass


def test_hidden_bodies_stay_off_the_list():
    bodies = [{"name": "Aid", "visible": False},
              {"name": "Part", "visible": True}]
    rows = parts_list(bodies, {"Part": FakeSolid(1000.0)})
    assert [r["description"] for r in rows] == ["Part"]


def test_identical_bodies_merge_with_qty():
    bodies = [{"name": "Leg 1", "visible": True},
              {"name": "Leg 2", "visible": True},
              {"name": "Top", "visible": True}]
    solids = {"Leg 1": FakeSolid(1500.0), "Leg 2": FakeSolid(1500.0),
              "Top": FakeSolid(9000.0)}
    rows = parts_list(bodies, solids, mass_unit="g")
    assert [(r["description"], r["qty"]) for r in rows] == \
        [("Leg", 2), ("Top", 1)]
    assert [r["item"] for r in rows] == [1, 2]


def test_same_stem_different_volume_stays_split():
    bodies = [{"name": "Leg 1", "visible": True},
              {"name": "Leg 2", "visible": True}]
    solids = {"Leg 1": FakeSolid(1500.0), "Leg 2": FakeSolid(1600.0)}
    rows = parts_list(bodies, solids)
    assert [r["description"] for r in rows] == ["Leg 1", "Leg 2"]


def test_material_and_row_mass_multiplies_qty():
    bodies = [{"name": "Pin 1", "visible": True, "material": "Brass"},
              {"name": "Pin 2", "visible": True, "material": "Brass"}]
    solids = {"Pin 1": FakeSolid(1000.0), "Pin 2": FakeSolid(1000.0)}
    rows = parts_list(bodies, solids)
    r = rows[0]
    assert r["material"] == "Brass"
    # 8.5 g/cm³ × 2 cm³ = 17.0 g (row mass, both pins)
    assert r["mass"] == "17.0 g"


def test_missing_solid_keeps_row_with_dash_mass():
    bodies = [{"name": "Ghost", "visible": True, "material": "PLA"}]
    rows = parts_list(bodies, {})
    assert rows[0]["mass"] == "—"


# ---- parts_list_table: geometry with the M108 contract ------------------

def _table(rows, page="A3"):
    tb = title_block({"name": "x"}, page=page)
    return parts_list_table(rows, tb["rect"], page=page), tb


def test_table_docks_on_the_title_block_right_edge():
    rows = [{"item": i, "description": f"D{i}", "qty": 1,
             "material": "—", "mass": "—"} for i in range(1, 4)]
    t, tb = _table(rows)
    bx, by, bw, bh = tb["rect"]
    x0, y0, w, h = t["rect"]
    assert (x0, w) == (bx, bw)          # same column, same 180 mm
    assert y0 == pytest.approx(by + bh)  # flush on the block's top
    assert h == pytest.approx(4 * 5.0)   # 3 rows + heading


def test_table_reads_bottom_to_top():
    rows = [{"item": i, "description": f"D{i}", "qty": 1,
             "material": "—", "mass": "—"} for i in range(1, 4)]
    t, _ = _table(rows)
    ys = {c["text"]: c["y"] for c in t["cells"] if c["col"] == "item"}
    # item 1 nearest the title block (lowest y); item 3 highest
    assert ys["1"] < ys["2"] < ys["3"]


def test_heading_row_is_bold_and_topmost():
    rows = [{"item": 1, "description": "D", "qty": 1, "material": "—",
             "mass": "—"}]
    t, _ = _table(rows)
    heads = [c for c in t["cells"] if c.get("bold")]
    assert {c["text"] for c in heads} == \
        {"It.", "Description", "Qty", "Material", "Mass"}
    assert all(c["y"] >= t["rect"][1] + t["rect"][3] - 5.0 for c in heads)


def test_grid_line_counts():
    rows = [{"item": 1, "description": "D", "qty": 1, "material": "—",
             "mass": "—"}]
    t, _ = _table(rows)
    n = len(rows)
    assert len(t["lines"]) == (n + 2) + (len(drawing.BOM_COLUMNS) + 1)


def test_overflow_is_counted_not_silently_truncated():
    rows = [{"item": i, "description": f"D{i}", "qty": 1,
             "material": "—", "mass": "—"} for i in range(1, 41)]
    t, _ = _table(rows, page="A4")
    assert t["overflow"] > 0
    shown = t["rect"][3] / 5.0 - 1
    assert shown + t["overflow"] == 40


def test_columns_carry_alignments():
    rows = [{"item": 7, "description": "Widget", "qty": 3,
             "material": "PLA", "mass": "9.1 g"}]
    t, _ = _table(rows)
    got = {c["col"]: c["align"] for c in t["cells"]
           if c["text"] == "7" or c["text"] == "3"
           or c["text"] == "Widget"}
    assert got["item"] == "c" and got["qty"] == "r" \
        and got["description"] == "l"


# ------------------------------------------------------------------ UI

import json                                                   # noqa: E402
import math                                                   # noqa: E402

from PySide6.QtCore import Qt                                 # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402
from PySide6.QtTest import QTest                              # noqa: E402

from tracer.core.document import Document, PrimitiveFeature   # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        from tracer.ui.renderer import SceneRenderer
        from tracer.ui.mainwindow import MainWindow
        try:
            r = SceneRenderer()
        except Exception as e:                 # CI windows: no GL
            pytest.skip(f"no headless GL available: {e}")
        w = MainWindow(renderer=r)
        w.resize(1000, 700)
        w.show()
        qapp.processEvents()
        yield w
        w._unsaved = False
        w._discard_guard = lambda: True
        w.close()
        r.ctx.release()
    except Exception:
        raise


def _plate_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Block", kind="box",
        dims={"dx": 60.0, "dy": 30.0, "dz": 20.0}))
    win.recompute()
    win.action_new_drawing()
    win._show_page(win._drawing_page)
    qapp.processEvents()
    return win.drawing


def _pin(cv, qapp, view, model_xy):
    """A draughtsman's click AT a model-space spot of a view."""
    sp = cv.s2p(*cv.model_to_page(view, model_xy)).toPoint()
    QTest.mouseClick(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                     sp)
    qapp.processEvents()


def test_balloon_clicks_pin_next_items(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_balloon_mode(True)
    _pin(cv, qapp, "top", (10.0, 5.0))
    _pin(cv, qapp, "top", (30.0, 20.0))
    bs = win.doc.drawings[-1]["balloons"]["top"]
    assert [b["item"] for b in bs] == [1, 2]
    assert bs[0]["x"] == pytest.approx(10.0, abs=0.6)
    assert bs[0]["y"] == pytest.approx(5.0, abs=0.6)


def test_balloon_anchor_survives_a_view_spin(win, qapp):
    # the M109 contract extended: pins store MODEL millimetres, so a
    # display spin moves the bubble but never the truth it marks
    cv = _plate_sheet(win, qapp)
    cv.set_balloon_mode(True)
    _pin(cv, qapp, "front", (12.0, 8.0))
    b = win.doc.drawings[-1]["balloons"]["front"][0]
    upright = cv.model_to_page("front", (b["x"], b["y"]))
    win.doc.drawings[-1].setdefault("rot", {})["front"] = 90.0
    spun = cv.model_to_page("front", (b["x"], b["y"]))
    assert b["x"] == pytest.approx(12.0, abs=0.6)
    assert math.dist(upright, spun) > 1.0            # display rotated
    assert cv.page_to_model("front", spun) == pytest.approx(
        (b["x"], b["y"]), abs=1e-6)                  # truth survived


def test_balloon_and_dim_modes_are_exclusive(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_dim_mode(True)
    cv.set_balloon_mode(True)
    assert cv._balloon_mode and not cv._dim_mode
    cv.set_dim_mode(True)
    assert cv._dim_mode and not cv._balloon_mode


def test_bar_buttons_wire_modes_and_sheet_state(win, qapp):
    cv = _plate_sheet(win, qapp)
    win._bom_btn.setChecked(True)
    assert win.doc.drawings[-1]["bom"] is True
    win._balloon_btn.setChecked(True)
    assert cv._balloon_mode
    win._dim_btn.setChecked(True)                    # the other tool…
    assert not cv._balloon_mode and not win._balloon_btn.isChecked()


def test_parts_list_paints_its_grid(win, qapp):
    cv = _plate_sheet(win, qapp)

    def ink_in_band():
        img = cv.grab().toImage()
        tb = drawing.title_block(cv.sheet(), page=cv.page)
        bx, by, bw, bh = tb["rect"]
        a = cv.s2p(bx + 1, by + bh + 0.85 * 5.0)   # band just above
        b = cv.s2p(bx + bw - 1, by + bh + 0.25 * 5.0)  # the block top
        n = 0
        for yy in range(int(a.y()), int(b.y()) + 1):
            for xx in range(int(a.x()), int(b.x()) + 1):
                if img.pixelColor(xx, yy).lightness() < 200:
                    n += 1
        return n

    win._bom_btn.setChecked(False)
    off = ink_in_band()
    win._bom_btn.setChecked(True)
    on = ink_in_band()
    assert on > off + 80               # the table drew real ink


def test_parts_list_and_balloons_never_enter_the_dxf(win, qapp):
    # the sheet's DXF is the VIEW line work; paper furniture (block M108,
    # parts list + balloons M110) is PNG-only. ezdxf stamps a fresh GUID
    # per file, so compare the entity bodies, not the envelopes.
    import re
    import tempfile
    import os

    def entities(path):
        raw = open(path).read()
        raw = re.sub(r"\{[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}\}",
                     "", raw)
        raw = re.sub(r"@ \d{4}-\d{2}-\d{2}T[\d:.]+\+00:00", "@ STAMP",
                     raw)                      # ezdxf write timestamp
        start = raw.index("  0\nSECTION\n  2\nENTIT")
        return raw[start:]

    cv = _plate_sheet(win, qapp)
    with tempfile.TemporaryDirectory() as td:
        a = os.path.join(td, "a.dxf")
        b = os.path.join(td, "b.dxf")
        win.export_drawing(a, ext=".dxf")
        win._bom_btn.setChecked(True)
        cv.set_balloon_mode(True)
        _pin(cv, qapp, "top", (20.0, 10.0))
        win.export_drawing(b, ext=".dxf")
        assert entities(a) == entities(b)
        assert "Body" not in open(b).read()   # no BOM words in the file


def test_bom_state_and_balloons_round_trip_through_save(win, qapp):
    cv = _plate_sheet(win, qapp)
    win._bom_btn.setChecked(True)
    cv.set_balloon_mode(True)
    _pin(cv, qapp, "right", (5.0, 12.0))
    payload = json.dumps(win.doc.to_dict())
    back = Document.from_dict(json.loads(payload))
    g = back.drawings[-1]
    assert g["bom"] is True
    assert g["balloons"]["right"][0]["item"] == 1


def test_balloon_pin_is_undoable(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_balloon_mode(True)
    _pin(cv, qapp, "top", (10.0, 5.0))
    win.undo()
    assert not win.doc.drawings[-1].get("balloons")


def test_material_assigns_weighs_and_undoes(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Slab", kind="box",
        dims={"dx": 20.0, "dy": 10.0, "dz": 10.0}))
    win.recompute()
    win._set_body_material(win.doc.body_list()[0]["name"], "Steel")
    assert win.doc.body_list()[0]["material"] == "Steel"
    rows = drawing.parts_list(win.doc.body_list(),
                              win.doc.body_solids())
    assert rows[0]["mass"] == "15.7 g"        # 2000 mm3 steel
    win.undo()                                # undo returns a NEW doc
    assert "material" not in win.doc.body_list()[0]
    name = win.doc.body_list()[0]["name"]
    win._set_body_material(name, "Steel")
    win._set_body_material(name, None)
    assert "material" not in win.doc.body_list()[0]
