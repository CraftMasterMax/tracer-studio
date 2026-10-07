"""M129 — holes speak on the drawing (rung b): table + marks, from
metadata.

The lesson this milestone refuses to learn from the mesh: a hole table
that measures its circles off the projected silhouette would under-read
every thread (a 24-gon is not a diameter) and go stale the moment a
view spins. So the table and the bubbles come straight out of HoleFeature
fields — the M123 sizes and the M128 designations — counted and grouped
in first-appearance order, and a hole is marked ONLY in the view you
look down its bore from (axis parallel to the sight), anchored in model
millimetres like a balloon so the notes ride a dragged view. It shares
the BOM's contract (rect/lines/cells, the M108 cell painter) and the
BOM's fate: paper furniture, never in the DXF line stream."""
import json

import pytest
from PySide6.QtWidgets import QApplication

from tracer.core import drawing
from tracer.core.document import Document, HoleFeature, PrimitiveFeature


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
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


def _holed_plate(win, qapp):
    """A 40x24x8 plate: two identical M8-6H through-taps, one plain
    blind hole, one counterbored — then a live drawing sheet off it."""
    win.new_document()
    d = win.doc
    d.features.append(PrimitiveFeature(name="plate", kind="box",
                                       dims={"dx": 40, "dy": 24, "dz": 8}))
    for x in (12.0, 28.0):
        d.features.append(HoleFeature(
            name=f"tap{x}", op="subtract", center=(x, 12, 8),
            normal=(0, 0, -1), radius=3.4, depth=8, cut_length=8,
            through=True, thread_pitch=1.25, thread_len=8,
            thread_size="M8", thread_class="6H"))
    d.features.append(HoleFeature(
        name="plain", op="subtract", center=(8, 6, 8), normal=(0, 0, -1),
        radius=2.5, depth=4, cut_length=4))
    d.features.append(HoleFeature(
        name="cb", op="subtract", center=(30, 6, 8), normal=(0, 0, -1),
        radius=2.5, depth=4, cut_length=4, cb_radius=4.5, cb_depth=3))
    win.recompute()
    win.action_new_drawing()
    win._show_page(win._drawing_page)
    qapp.processEvents()
    return win.drawing


def _doc():
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
    d.recompute()
    return d


# ---- rows: counted, grouped, first-appearance -----------------------------

def test_identical_taps_collapse_to_one_counted_row():
    rows = drawing.hole_rows(_doc())
    m8 = [r for r in rows if r["hole"] == "M8-6H"]
    assert len(m8) == 1 and m8[0]["qty"] == 2
    assert m8[0]["depth"] == "THRU"                # through reads THRU
    assert m8[0]["drill"] == "Ø 6.8"               # tap-drill, not major


def test_plain_and_cbore_get_their_own_rows():
    rows = drawing.hole_rows(_doc())
    plain = next(r for r in rows if r["hole"] == "Ø 5")
    assert plain["qty"] == 1 and plain["depth"] == "4"
    assert plain["drill"] == ""                     # a plain hole IS its Ø
    cb = next(r for r in rows if "cbore" in r["hole"])
    assert "Ø 9" in cb["hole"] and cb["qty"] == 1
    assert [r["item"] for r in rows] == [1, 2, 3]   # first-appearance order


def test_suppressed_holes_stay_off_the_table():
    d = _doc()
    d.features[-1].suppressed = True
    d.recompute()
    assert not any("cbore" in r["hole"]
                   for r in drawing.hole_rows(d))


# ---- marks: look down the bore, tag at true major -------------------------

def test_marks_only_where_you_look_down_the_bore():
    mk = drawing.hole_marks(_doc())
    assert set(mk) == {"top"}                       # all face +z
    assert len(mk["top"]) == 4
    m8 = [m for m in mk["top"] if m["r"] > 3.9]
    assert len(m8) == 2
    assert all(abs(m["r"] - 4.0) < 1e-9 for m in m8)   # true ISO major
    assert {m["item"] for m in m8} == {1}              # shared row/item


def test_a_side_hole_marks_the_side_view_not_the_top():
    d = Document()
    d.add(PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10}))
    d.add(HoleFeature(name="side", op="subtract", center=(0, 5, 5),
                      normal=(1, 0, 0), radius=2.0, depth=8, cut_length=8))
    mk = drawing.hole_marks(d)
    assert set(mk) == {"right"}                     # sight is +x
    assert not mk.get("top")
    assert "iso" not in mk                          # a slanted bore lies


def test_no_holes_no_rows_no_marks():
    d = Document()
    d.add(PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10}))
    d.recompute()
    assert drawing.hole_rows(d) == [] and drawing.hole_marks(d) == {}


# ---- table geometry: the free upper-left corner ---------------------------

def test_table_docks_upper_left_on_the_margin():
    t = drawing.hole_table(drawing.hole_rows(_doc()), page="A3")
    W, H = drawing.PAGES["A3"]
    x0, yb, bw, bh = t["rect"]
    assert x0 == 10.0                               # left margin
    assert abs((yb + bh) - (H - 10.0)) < 1e-9       # top edge on top margin
    assert bw <= 0.5 * W                            # never hog the sheet
    assert t["overflow"] == 0
    assert len(t["cells"]) == 5 * 4                 # header + 3 rows


# ---- canvas: real ink, opt-out flag, round-trip ---------------------------

def _ink_in_table(win, cv):
    img = cv.grab().toImage()
    t = drawing.hole_table(drawing.hole_rows(win.doc), page=cv.page)
    x0, yb, bw, bh = t["rect"]
    p0, p1 = cv.s2p(x0 + 1, yb + 1), cv.s2p(x0 + bw - 1, yb + bh - 1)
    n = 0
    for yy in range(int(min(p0.y(), p1.y())), int(max(p0.y(), p1.y())) + 1):
        for xx in range(int(min(p0.x(), p1.x())),
                        int(max(p0.x(), p1.x())) + 1):
            if img.pixelColor(xx, yy).lightness() < 200:
                n += 1
    return n


def test_hole_notes_default_on_and_paint_the_table(win, qapp):
    cv = _holed_plate(win, qapp)
    assert win._hole_btn.isChecked()                # default ON
    qapp.processEvents()
    win._hole_btn.setChecked(False)                 # hide…
    qapp.processEvents()
    off_ink = _ink_in_table(win, cv)
    win._hole_btn.setChecked(True)                  # …show: table is ink
    qapp.processEvents()
    on_ink = _ink_in_table(win, cv)
    assert win.doc.drawings[-1]["hole_notes"] is True
    assert on_ink > off_ink + 60


def test_hole_notes_round_trip_and_track_the_button(win, qapp):
    _holed_plate(win, qapp)
    win._hole_btn.setChecked(False)
    assert win.doc.drawings[-1]["hole_notes"] is False
    back = Document.from_dict(json.loads(json.dumps(win.doc.to_dict())))
    assert back.drawings[-1]["hole_notes"] is False
    win.doc = back
    win._adopt_doc()
    qapp.processEvents()
    assert not win._hole_btn.isChecked()            # the button obeys disk


def test_hole_notes_never_enter_the_dxf(win, qapp):
    import os
    import re
    import tempfile
    cv = _holed_plate(win, qapp)

    def entities(path):
        raw = open(path).read()
        raw = re.sub(r"\{[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}\}", "",
                     raw)
        raw = re.sub(r"@ \d{4}-\d{2}-\d{2}T[\d:.]+\+00:00", "@ STAMP", raw)
        return raw[raw.index("  0\nSECTION\n  2\nENTIT"):]

    with tempfile.TemporaryDirectory() as td:
        a = os.path.join(td, "a.dxf")
        b = os.path.join(td, "b.dxf")
        win._hole_btn.setChecked(False)
        win.export_drawing(a, ext=".dxf")
        win._hole_btn.setChecked(True)
        win.export_drawing(b, ext=".dxf")
        assert entities(a) == entities(b)
        assert "M8-6H" not in open(b).read()        # notes are paper-only
