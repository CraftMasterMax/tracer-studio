"""M108 — the drawing title block.

A sheet without a title block is a nice picture with no provenance: no
one knows what it is, who drew it, when, or what it's made of.  Fusion
puts an ISO block bottom-right; so does Tracer.  The block's human
fields (drawing number, title, drawn-by, date, material) are stored on
the sheet; scale, page size and the sheet position in the set are DERIVED
at draw time from the drawing itself, so a block can never carry a stale
scale after the model grows.

The whole thing is pure geometry + text in drawing.title_block(): the
canvas paints it through the same sheet→pixel map as every view, the DXF
writer emits the frame as line art (text, like the bubbles', is the
PNG's job), and the field dict rides the document's undo stack and JSON
save untouched — no new serialisation.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                    # noqa: E402

from tracer.core import drawing                                # noqa: E402
from tracer.core.document import Document, PrimitiveFeature   # noqa: E402


# ---- core: the resolver is geometry-only and self-consistent --------------------

def test_block_rect_sits_bottom_right_inside_the_sheet():
    tb = drawing.title_block({"name": "S1"}, meta={}, page="A3")
    x, y, w, h = tb["rect"]
    W, H = drawing.PAGES["A3"]
    assert 0 < x and x + w <= W                 # within the width
    assert y >= 10.0 and y + h <= H             # bottom band, on the sheet


def test_every_text_cell_lives_inside_its_block():
    tb = drawing.title_block(
        {"name": "S1", "block": {"title": "Bracket", "author": "Pat",
                                 "material": "Aluminium", "number": "DWG-7"}},
        meta={"scale": "1:2", "sheet": "1 / 1"}, page="A3")
    x, y, w, h = tb["rect"]
    for c in tb["cells"]:
        assert x <= c["xa"] < c["xb"] <= x + w
        assert y <= c["y"] <= y + h
    # a long title must not be allowed to wander outside its own column
    tb2 = drawing.title_block(
        {"name": "S", "block": {"title": "X" * 200}}, meta={}, page="A3")
    tcell = tb2["cells"][0]
    assert tcell["xb"] - tcell["xa"] <= tb2["rect"][2]


def test_block_text_reflects_the_typed_fields_and_derived_meta():
    tb = drawing.title_block(
        {"name": "S1", "block": {"author": "Pat", "date": "2026-10-07",
                                 "material": "Brass", "number": "DWG-1"}},
        meta={"scale": "1:4", "sheet": "2 / 3"}, page="A3")
    blob = " ".join(c["text"] for c in tb["cells"])
    for needle in ("Pat", "2026-10-07", "Brass", "DWG-1", "1:4", "2 / 3"):
        assert needle in blob


def test_untouched_sheet_still_shows_a_populated_block():
    tb = drawing.title_block({"name": "Bracket"},
                             meta={"scale": "1:2", "sheet": "1 / 1"},
                             page="A3")
    blob = " ".join(c["text"] for c in tb["cells"])
    assert "Bracket" in blob and "1:2" in blob        # name + scale appear
    assert "Drawn:" in blob                            # empty field labelled


def test_frame_has_the_three_rows_and_the_column_dividers():
    tb = drawing.title_block({"name": "S"}, meta={}, page="A3")
    assert len(tb["lines"]) >= 7                      # border + 2 rows + cols


# ---- document: the field dict rides save / undo for free ------------------------

def test_block_survives_the_json_round_trip():
    doc = Document("t")
    doc.drawings.append({"name": "D1", "page": "A3",
                         "block": {"title": "Widget", "author": "Pat"}})
    back = Document.from_dict(doc.to_dict())
    assert back.drawings[0]["block"]["title"] == "Widget"
    assert back.drawings[0]["block"]["author"] == "Pat"


def test_a_sheet_without_a_block_is_fine():
    src = Document("t")
    src.drawings.append({"name": "D", "page": "A3"})
    back = Document.from_dict(src.to_dict())
    assert "block" not in back.drawings[0]
    # the resolver still paints a populated block for a sheet that never had one
    tb = drawing.title_block(back.drawings[0], meta={}, page="A3")
    assert any(c["text"] == "D" for c in tb["cells"])


# ------------------------------------------------------------------ UI

from conftest import script_cmd, script_cmd_cancel             # noqa: E402


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
        except Exception as e:                 # CI windows runners: no GL
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


def _box_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Block", kind="box", dims={"dx": 40.0, "dy": 20.0, "dz": 10.0}))
    win.recompute()
    win.action_new_drawing()
    win._show_page(win._drawing_page)
    qapp.processEvents()
    return win.drawing


def test_action_title_block_stores_the_human_fields(win, qapp, monkeypatch):
    _box_sheet(win, qapp)
    script_cmd(monkeypatch, {"number": "DWG-42", "title": "Flange",
                             "author": "Pat", "date": "2026-10-07",
                             "material": "Aluminium"})
    win.action_title_block()
    qapp.processEvents()
    blk = win.doc.drawings[-1]["block"]
    assert blk == {"number": "DWG-42", "title": "Flange", "author": "Pat",
                   "date": "2026-10-07", "material": "Aluminium"}


def test_action_title_block_strips_blanks(win, qapp, monkeypatch):
    _box_sheet(win, qapp)
    script_cmd(monkeypatch, {"number": "", "title": "  Widget  ",
                             "author": "", "date": "", "material": ""})
    win.action_title_block()
    assert win.doc.drawings[-1]["block"] == {"title": "Widget"}


def test_action_title_block_cancels_clean(win, qapp, monkeypatch):
    cv = _box_sheet(win, qapp)
    script_cmd_cancel(monkeypatch)
    win.action_title_block()
    assert "block" not in win.doc.drawings[-1]


def test_title_block_undoes(win, qapp, monkeypatch):
    _box_sheet(win, qapp)
    script_cmd(monkeypatch, {"number": "A", "title": "B", "author": "C",
                             "date": "D", "material": "E"})
    win.action_title_block()
    assert win.doc.drawings[-1]["block"]["title"] == "B"
    win.undo()
    assert "block" not in win.doc.drawings[-1]


def test_canvas_paints_the_block_without_crashing(win, qapp, monkeypatch):
    cv = _box_sheet(win, qapp)
    script_cmd(monkeypatch, {"number": "DWG-9", "title": "Cover",
                             "author": "Pat", "date": "2026", "material": "PLA"})
    win.action_title_block()
    qapp.processEvents()
    cv.resize(800, 600)
    cv.grab()                                   # paints the block; no exception
    assert win.doc.drawings[-1]["block"]["material"] == "PLA"


def test_title_block_is_paper_only_dxf_stays_view_line_art(win, qapp,
                                                           monkeypatch,
                                                           tmp_path):
    # The block is sheet furniture: it lives in the canvas/PNG, but must NOT
    # pollute the DXF view-geometry stream (that would corrupt CAD re-import).
    import ezdxf
    cv = _box_sheet(win, qapp)
    # baseline: DXF with no title block
    out0 = str(tmp_path / "plain.dxf")
    win.export_drawing(path=out0, ext=".dxf")
    n0 = len(list(ezdxf.readfile(out0).modelspace().query("LWPOLYLINE")))
    # add the block, re-export: the polyline stream must be identical
    script_cmd(monkeypatch, {"number": "", "title": "Frame", "author": "",
                             "date": "", "material": ""})
    win.action_title_block()
    qapp.processEvents()
    out = str(tmp_path / "sheet.dxf")
    win.export_drawing(path=out, ext=".dxf")
    n1 = len(list(ezdxf.readfile(out).modelspace().query("LWPOLYLINE")))
    assert n1 == n0                            # block contributed zero geometry


def test_png_export_carries_the_block_text(win, qapp, monkeypatch, tmp_path):
    from PySide6.QtGui import QImage
    cv = _box_sheet(win, qapp)
    script_cmd(monkeypatch, {"number": "", "title": "ZZTITLE", "author": "",
                             "date": "", "material": ""})
    win.action_title_block()
    qapp.processEvents()
    out = str(tmp_path / "sheet.png")
    win.export_drawing(path=out, ext=".png")
    img = QImage(out)
    ink = sum(1 for x in range(0, img.width(), 3)
              for y in range(int(img.height() * 0.6), img.height(), 3)
              if img.pixelColor(x, y).lightness() < 120)
    assert ink > 0                             # block ink painted bottom-right
