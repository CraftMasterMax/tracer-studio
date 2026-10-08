"""M144 — GD&T rung 1: the feature control frame, hosted by dims.

The probe (research/gdt_glyphs.md) de-risked every line of this
rung before a ship: SIX painted glyphs (the Unicode GDT block is
tofu on real paper fonts — machine-verified), the ISO 1101 /
ASME Y14.5-2018 validator rows (fetched text, not remembered),
the frame grammar [|sym][value+mods][A][B][C] with SEPARATE datum
cells (Y14.5 6.4.3 — the vendor's "|B C|" stack is NOT ASME), and
the TE-companion box (ISO 1101 cl.11 verbatim: "TED shall ... be
enclosed in a frame"). The frame rides an optional "gdt" key on
the existing dim entry — a LIST so rung-2 stacked frames need no
re-shape — so travel is free: model-space anchors already carry
the whole annotation through stretches, spins and saves. Values
are STRINGS (wave-11a law): resolve_dims never touches them, the
drafter's typed tolerance is the ink. Editing mirrors the fit
callout verbatim: tool click -> dim hit -> dialog -> validator
raises -> undo-pop + warning; "— none —" pops the key.
"""
import json

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tracer.core import drawing, gdt  # noqa: E402
from tracer.core.document import PrimitiveFeature  # noqa: E402


# ---- pure core: the table, the validator, the cells, the glyphs ----

def test_table_is_the_six():
    # M150 CITES THE MOVE (M141's law, contract gdt_rung2.md §1.4):
    # rung 1 pinned equality with six; rung 2 grows five seats, so
    # the law becomes SUPERSET + a byte-exact pin of the six rung-1
    # rows. The law bites BOTH ways: growth is legal, drift is not.
    assert set(gdt.CONTROL_TABLE) >= {"straightness", "flatness",
                                      "circularity", "cylindricity",
                                      "perpendicularity", "position"}
    import json
    six = {k: gdt.CONTROL_TABLE[k] for k in
           ("straightness", "flatness", "circularity", "cylindricity",
            "perpendicularity", "position")}
    assert json.dumps(six, sort_keys=True) == json.dumps({
        "straightness": dict(
            name="Straightness", mods=("M",), datums=(0, 0),
            diam="optional", forces_TE=False,
            zone="two parallel lines/planes; a cylinder iff ⌀ (18.1)"),
        "flatness": dict(
            name="Flatness", mods=(), datums=(0, 0),
            diam="forbidden", forces_TE=False,
            zone="two parallel planes t apart (18.2)"),
        "circularity": dict(
            name="Circularity", mods=(), datums=(0, 0),
            diam="forbidden", forces_TE=False,
            zone="two concentric circles, radial band (18.3)"),
        "cylindricity": dict(
            name="Cylindricity", mods=(), datums=(0, 0),
            diam="forbidden", forces_TE=False,
            zone="two coaxial cylinders, radial band (18.4)"),
        "perpendicularity": dict(
            name="Perpendicularity", mods=("M",), datums=(1, 3),
            diam="optional", forces_TE=True,
            zone="two parallel planes/lines (a cylinder iff ⌀) (18.6)"),
        "position": dict(
            name="Position", mods=("M", "L"), datums=(0, 3),
            diam="normal", forces_TE=True,
            zone="cylinder iff ⌀; two planes or sphere otherwise (18.8)"),
    }, sort_keys=True)
    for row in gdt.CONTROL_TABLE.values():
        assert row["zone"] and row["name"]
        assert isinstance(row["mods"], tuple)
        assert row["datums"][0] <= row["datums"][1]


@pytest.mark.parametrize("sym,tol,mod,datums", [
    ("flatness", "0.05", "", []),
    ("straightness", "⌀ 0.1", "", []),            # axis form: ⌀ legal
    ("position", "⌀ 0.2", "M", ["A"]),
    ("position", "S⌀ 0.3", "", ["A", "B", "C"]),  # spherical zone
    ("perpendicularity", "0.05", "", ["A-B"]),    # common datum ONE cell
    ("position", "0.2", "", []),                  # legal ISO (0 datum)
])
def test_validator_accepts_grammar(sym, tol, mod, datums):
    warns = gdt.gdt_validate({"sym": sym, "tol": tol, "mod": mod,
                              "datums": datums})
    assert isinstance(warns, list)


def test_position_without_datum_warns_but_stands():
    warns = gdt.gdt_validate({"sym": "position", "tol": "⌀ 0.2",
                              "mod": "", "datums": []})
    assert warns                       # shop-law nudge, never a refusal


@pytest.mark.parametrize("sym,tol,mod,datums", [
    ("flatness", "⌀ 0.05", "", []),               # ⌀ forbidden x3
    ("circularity", "⌀ 0.05", "", []),
    ("cylindricity", "⌀ 0.05", "", []),
    ("straightness", "0.05", "", ["A"]),          # form: NO datums
    ("flatness", "0.05", "M", []),                # Ⓜ not for flatness
    ("perpendicularity", "0.05", "", []),         # needs >=1 datum
    ("position", "0.2", "P", ["A"]),              # projected: deferred
    ("position", "0.2", "", ["A", "B", "C", "D"]),  # max 3 (6.4.3)
    ("position", "0.2", "", ["I"]),               # reserved letters
    ("position", "0.2", "", ["O", "Q", "S", "X", "Z"]),
    ("position", "0.2", "", ["B C"]),             # two letters need a dash
    ("position", "-1", "", ["A"]),                # positive numbers only
    ("position", "fast", "", ["A"]),              # and a number at all
    ("waviness", "0.1", "", []),                  # not a control here
])
def test_validator_refuses_illegal(sym, tol, mod, datums):
    with pytest.raises(ValueError):
        gdt.gdt_validate({"sym": sym, "tol": tol, "mod": mod,
                          "datums": datums})


def test_datum_alphabet_is_the_sections_alphabet():
    # ONE registry (the probe's §2): the datum letters ARE the
    # section letters — same reserved family, one source of truth.
    assert gdt.RESERVED_LETTERS is drawing.RESERVED_LETTERS
    assert drawing.section_letter(0) == "A"


def test_glyphs_are_unit_boxed_polylines():
    assert set(gdt.GLYPHS) == set(gdt.CONTROL_TABLE)
    for key, ops in gdt.GLYPHS.items():
        assert ops, key
        for op in ops:
            if op[0] == "poly":
                for x, y in op[1]:
                    assert -1e-9 <= x <= 1 + 1e-9, (key, x)
                    assert -1e-9 <= y <= 1 + 1e-9, (key, y)
            elif op[0] == "circle":
                (_, (cx, cy), r) = op
                assert 0 <= cx - r and cx + r <= 1
                assert 0 <= cy - r and cy + r <= 1
            elif op[0] == "arc":            # M150: profile seats
                (_, (cx, cy), r, a0, a1) = op
                # the DRAWN extent, not the full circle: Qt arcs take
                # y = cy - r*sin(t), so an upper seat (180->0 through
                # 90) reaches cy - r at its apex and never below cy.
                assert 0 <= cx - r and cx + r <= 1
                assert 0 <= cy - r and cy <= 1
                assert -360 <= a0 <= 360 and -360 <= a1 <= 360
            else:                           # M150: runout arrow
                assert op[0] == "arrow", (key, op)
                for (x, y) in op[1:]:
                    assert -1e-9 <= x <= 1 + 1e-9, (key, x)
                    assert -1e-9 <= y <= 1 + 1e-9, (key, y)


def test_datum_cells_are_separate_grammar():
    # ASME Y14.5-2018 6.4.3: SEPARATE compartments per datum...
    cells = gdt.gdt_cells({"sym": "position", "tol": "⌀ 0.2",
                           "mod": "M", "datums": ["A", "B"]})
    kinds = [c["kind"] for c in cells]
    assert kinds == ["glyph", "text", "datum", "datum"]
    assert cells[1]["s"].startswith("Ø")           # printable Ø letter
    assert "M" in cells[1]["s"]                    # modifier shares value
    # ...the ONLY shared cell is the ISO common datum A-B:
    cells2 = gdt.gdt_cells({"sym": "perpendicularity", "tol": "0.05",
                            "mod": "", "datums": ["A-B"]})
    assert [c["kind"] for c in cells2][-1:] == ["datum"]
    assert cells2[-1]["s"] == "A-B"


def test_tol_prefix_normalises_to_the_paper_letter():
    cells = gdt.gdt_cells({"sym": "straightness", "tol": "⌀ 0.1",
                           "mod": "", "datums": []})
    assert cells[1]["s"] == "Ø 0.1"          # U+2300 is tofu on real


# ---- the canvas: real ink, honest stacking, paper-only --------------

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
    w.resize(1200, 800)
    w.show()
    qapp.processEvents()
    w.new_document()
    w.doc.add(PrimitiveFeature(name="plate", kind="box",
                               dims={"dx": 40, "dy": 20, "dz": 10}))
    w.recompute()
    qapp.processEvents()
    w.action_new_drawing()
    w._add_dim("top", (0.0, 0.0), (40.0, 0.0), {})
    qapp.processEvents()
    yield w
    w._unsaved = False          # m56/m63 law: leave no mapped window
    w.close()
    r.ctx.release()
    qapp.processEvents()


def _red_px(cv):
    """Blend-tolerant red counter (M144 CI lesson): a 1 px red line on
    paper anti-aliases into fringes whose red-minus-green can fall to
    ~27 at 20% coverage, and the runner's font family decides where
    the box edges land. A paper->#c33c3c blend has red-green = 135t,
    so >25 counts EVERY visible red pixel (>=20% coverage) whatever
    the font — deltas then measure ink, not font luck."""
    img = cv.grab().toImage()
    n = 0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = img.pixelColor(x, y)
            if c.red() > 150 and c.red() - c.green() > 25:
                n += 1
    return n


def test_fcf_inks_below_the_dim(win, qapp):
    cv = win.drawing
    qapp.processEvents()
    base = _red_px(cv)
    win.doc.drawings[0]["dims"][0]["gdt"] = [
        {"sym": "position", "tol": "⌀ 0.2", "mod": "M",
         "datums": ["A", "B"]}]
    cv.update()
    qapp.processEvents()
    with_frame = _red_px(cv)
    assert with_frame > base + 30            # frame + glyph + cells


def test_frame_stacks_below_the_text_at_honest_width(win, qapp):
    cv = win.drawing
    win.doc.drawings[0]["dims"][0]["gdt"] = [
        {"sym": "flatness", "tol": "0.05", "mod": "", "datums": []}]
    seen = []
    orig = cv._draw_gdt_frame

    def spy(p, frame, gap):
        rect = orig(p, frame, gap)
        seen.append((gap, rect, frame))
        return rect

    cv._draw_gdt_frame = spy
    try:
        cv.update()
        qapp.processEvents()
    finally:
        del cv._draw_gdt_frame
    assert len(seen) == 1
    gap, rect, frame = seen[0]
    assert rect.top() > gap.bottom()                  # BELOW the text
    widths = cv._gdt_cells_widths(gap, frame)
    assert rect.width() == pytest.approx(sum(widths), abs=1.0)
    assert rect.height() == pytest.approx(1.5 * (gap.height() - 4.0),
                                          abs=0.6)      # 1.5 h_text law


def test_basic_dim_gets_the_iso_box(win, qapp):
    cv = win.drawing
    base = _red_px(cv)
    win.doc.drawings[0]["dims"][0]["basic"] = True
    cv.update()
    qapp.processEvents()
    assert _red_px(cv) > base + 8        # cl.11: "enclosed in a frame"
    win.doc.drawings[0]["dims"][0].pop("basic")


def test_frames_are_paper_only_never_dxf_line_art(win, qapp,
                                                  tmp_path):
    from tracer.core import import2d
    plain = str(tmp_path / "plain.dxf")
    win.export_drawing(plain)
    n0 = len(import2d.read(plain))
    win.doc.drawings[0]["dims"][0]["gdt"] = [
        {"sym": "position", "tol": "⌀ 0.2", "mod": "", "datums": ["A"]}]
    win.doc.drawings[0]["dims"][0]["basic"] = True
    rich = str(tmp_path / "rich.dxf")
    win.export_drawing(rich)
    assert len(import2d.read(rich)) == n0        # the BOM law again:
    #                                       paper furniture stays put


def test_gdt_rides_save_and_load(win, qapp):
    win.doc.drawings[0]["dims"][0]["gdt"] = [
        {"sym": "perpendicularity", "tol": "0.05", "mod": "",
         "datums": ["A"]}]
    back = type(win.doc).from_dict(json.loads(json.dumps(
        win.doc.to_dict())))
    d = back.drawings[0]["dims"][0]
    assert d["gdt"][0]["sym"] == "perpendicularity"


# ---- the dialog seam: store, refuse by name, pop on none ------------

def _fill(win):
    return win.doc.drawings[0]["dims"][0]


def test_annotate_gdt_stores_and_the_button_joins_the_exclusion(
        win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    monkeypatch.setattr(
        cmddialog, "ask", lambda *a, **k: {
            "sym": "Position", "tol": "⌀ 0.2", "mod": "M",
            "datums": "A", "basic": True})
    win._annotate_gdt("top", 0)
    d = _fill(win)
    assert d["gdt"] == [{"sym": "position", "tol": "⌀ 0.2",
                         "mod": "M", "datums": ["A"]}]
    assert d["basic"] is True
    # five-way exclusion: arming GD&T stands the fit tool down
    win._gdt_btn.setChecked(True)
    assert not win._fit_btn.isChecked()
    assert not win._dim_btn.isChecked()
    win._gdt_btn.setChecked(False)


def test_annotate_gdt_refuses_illegal_with_a_named_warning(
        win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    from tracer.ui.mainwindow import QMessageBox
    shots = []
    monkeypatch.setattr(
        cmddialog, "ask", lambda *a, **k: {
            "sym": "Flatness", "tol": "⌀ 0.05", "mod": "",
            "datums": "", "basic": False})
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: shots.append(a[2])))
    win._annotate_gdt("top", 0)
    assert "gdt" not in _fill(win)               # refused cleanly
    assert shots and "flatness" in shots[0].lower()   # names the law


def test_annotate_gdt_none_pops_like_a_fit_strip(win, qapp,
                                                 monkeypatch):
    from tracer.ui import cmddialog
    monkeypatch.setattr(
        cmddialog, "ask", lambda *a, **k: {
            "sym": "Position", "tol": "⌀ 0.2", "mod": "",
            "datums": "A", "basic": False})
    win._annotate_gdt("top", 0)
    monkeypatch.setattr(
        cmddialog, "ask", lambda *a, **k: {
            "sym": "— none —", "tol": "", "mod": "", "datums": "",
            "basic": False})
    win._annotate_gdt("top", 0)
    assert "gdt" not in _fill(win)
