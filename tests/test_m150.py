"""M150 — GD&T rung 2: the frame becomes LANGUAGE (five new seats,
bound datum letters, the first computed tolerance, the projected
zone, the first rename-immune target). Contract: research/
gdt_rung2.md; every golden re-derives IN THE WRITTEN ORDER (float
association is law); the mesh rides only two-way BUDGET censuses,
never an identity (SM3's census pattern)."""
import json
import math

import pytest

from tracer.core import fits, gdt, gdtzones
from tracer.core import params
from tracer.core.document import (Document, HoleFeature,
                                  PrimitiveFeature)

# ---- G1: the table is eleven, lockstep, complete -------------------
def test_table_is_the_eleven():
    assert len(gdt.CONTROL_TABLE) == 11
    assert set(gdt.CONTROL_TABLE) >= {"parallelism", "angularity",
                                      "profile_line",
                                      "profile_surface",
                                      "circular_runout"}
    assert set(gdt.GLYPHS) == set(gdt.CONTROL_TABLE)
    for key in ("parallelism", "angularity", "profile_line",
                "profile_surface", "circular_runout"):
        row = gdt.CONTROL_TABLE[key]
        assert row["zone"] and row["name"]
        assert isinstance(row["mods"], tuple)
        assert row["datums"][0] <= row["datums"][1]
    assert not set(gdt.DEFERRED) & set(gdt.CONTROL_TABLE)  # deferred
    # names stay unique — the combo speaks English, entries keys
    names = [r["name"] for r in gdt.CONTROL_TABLE.values()]
    assert len(names) == len(set(names))


# ---- G2: the validator's grammar, new clauses + old voices ---------
def test_validator_grammar_new_and_old():
    assert gdt.gdt_validate(dict(sym="angularity", tol="0.1",
                                 datums=["A"], angle="60")) == []
    with pytest.raises(ValueError) as e:
        gdt.gdt_validate(dict(sym="angularity", tol="0.1",
                              datums=["A"]))
    assert "TRUE angle" in str(e.value)
    with pytest.raises(ValueError) as e:
        gdt.gdt_validate(dict(sym="flatness", tol="0.1", datums=[],
                              angle="60"))
    assert "angularity only" in str(e.value)
    with pytest.raises(ValueError) as e:      # runout: no M, no ⌀
        gdt.gdt_validate(dict(sym="circular_runout", tol="0.1",
                              datums=["A"], mod="M"))
    assert "not modified by (M)" in str(e.value)
    with pytest.raises(ValueError):
        gdt.gdt_validate(dict(sym="circular_runout", tol="\u2300 0.1",
                              datums=["A"]))
    warns = gdt.gdt_validate(dict(sym="profile_surface", tol="0.5",
                                  mod="", datums=[]))
    assert warns and "locates nothing" in warns[0]   # forces_TE warn
    assert gdt.gdt_validate(dict(sym="position", tol="\u2300 0.2",
                                 mod="", datums=["A"],
                                 proj="12")) == []
    with pytest.raises(ValueError) as e:      # proj needs an axis
        gdt.gdt_validate(dict(sym="flatness", tol="0.1", datums=[],
                              proj="12"))
    assert "projects an AXIS" in str(e.value)
    for bad in ("0", "abc", "-3"):
        with pytest.raises(ValueError):
            gdt.gdt_validate(dict(sym="position", tol="\u2300 0.2",
                                  mod="", datums=["A"], proj=bad))
    # the deferred refusals NAME themselves
    for key in gdt.DEFERRED:
        with pytest.raises(ValueError) as e:
            gdt.gdt_validate(dict(sym=key, tol="0.1", datums=["A"]))
        assert len(str(e.value)) > 30
    # rung 1's voices byte-identical:
    with pytest.raises(ValueError) as e:
        gdt.gdt_validate(dict(sym="flatness", tol="0.1",
                              datums=["A"]))
    assert str(e.value) == ("Flatness takes at most 0 datum "
                            "references, in precedence order")


# ---- G3: orientation width — the sin law, repr-pinned -------------
def test_orientation_law_is_the_sin_expression():
    dev = gdtzones.orientation_dev(50.0, 0.5)
    assert dev == 50.0 * math.sin(math.radians(0.5))
    assert repr(dev) == "0.43632677491869676"
    assert gdtzones.orientation_dev(50.0, -0.5) == dev      # |delta|
    assert dev <= dev                                       # boundary
    assert gdtzones.orientation_dev(50.0, 0.0) == 0.0


# ---- G4: true position — the DIAMETRAL factor, no vendor rounding -
def test_true_position_is_diametral_and_exact():
    dev = gdtzones.true_position(0.003, 0.002)
    assert dev == 2.0 * math.sqrt(0.003 * 0.003 + 0.002 * 0.002)
    assert repr(dev) == "0.007211102550927979"
    assert dev != 0.007                          # their rounding dies
    assert gdtzones.true_position(0.0, 0.0) == 0.0    # coaxial exact


# ---- G5: the MMC ladder — association order IS the contract -------
def test_mmc_bonus_allowed_and_the_painted_warning():
    lo, hi = fits.limits(10.0, "H7")
    assert (lo, hi) == (10.0, 10.015)
    allowed = gdtzones.allowed(0.2, 10.010, lo)
    assert allowed == 0.2 + (10.010 - 10.0)
    assert repr(allowed) == "0.2099999999999998"   # pinned repr
    assert gdtzones.bonus_internal(10.010, lo) == 10.010 - 10.0
    assert gdtzones.bonus_external(9.995, 10.0) == 10.0 - 9.995
    assert gdtzones.bonus_lmc_internal(10.005, hi) == hi - 10.005
    assert gdtzones.bonus_lmc_external(10.005, hi) == 10.005 - hi
    warns = gdt.gdt_validate(dict(sym="position", tol="\u2300 0.2",
                                  mod="M", datums=["A"]))
    assert warns and "painted, not evaluated" in warns[0]


# ---- G6: the gage ladder, both kinds -------------------------------
def test_virtual_condition_both_ways():
    assert gdtzones.virtual_internal(10.0, 0.2) == 10.0 - 0.2
    assert gdtzones.virtual_external(10.0, 0.2) == 10.0 + 0.2


# ---- G7: the projected zone — cell, height law, refusals -----------
def test_projected_zone_cell_and_dev():
    cells = gdt.gdt_cells(dict(sym="position", tol="\u2300 0.2",
                               mod="M", datums=["A"], proj="12"))
    assert [c["kind"] for c in cells] == ["glyph", "text", "proj",
                                          "datum"]
    assert cells[2]["s"] == "P 12"
    dev = gdtzones.projected_dev(0.05, 12.0, 0.5)
    assert dev == 2.0 * (0.05 + 12.0 * math.tan(math.radians(0.5)))
    assert repr(dev) == "0.30944482697821096"
    assert gdtzones.projected_dev(0.0, 12.0, 0.0) == 0.0
    assert gdtzones.projected_dev(0.05, 12.0, 0.0) == 2.0 * 0.05


# ---- G8: circular runout — closed form + the mesh BUDGET -----------
def test_runout_closed_form_and_mesh_census():
    assert gdtzones.runout(0.05) == 2.0 * 0.05
    assert gdtzones.runout(-0.05) == 2.0 * 0.05
    assert gdtzones.runout(0.0) == 0.0
    from tracer.core.drawing import fit_circle, project_view
    from tracer.core.geometry import Solid
    rim = Solid.cylinder(5.0, 10.0, center=(0.05, 0.0))
    fit = None
    for c in project_view(rim, view="top"):
        f = fit_circle(c)
        if f is not None:
            fit = f
            break
    assert fit is not None
    # the centre of a SYMMETRIC facet ring is exact by construction
    # (spike finding): upper bound only ...
    assert abs(gdtzones.runout(fit[0][0]) - 0.1) < 1e-3
    # ... the census BOTH ways rides the radius, where facets lie:
    rad_delta = abs(fit[1] - 5.0)
    assert 1e-9 < rad_delta < 1e-3, rad_delta


# ---- G9: the datum registry, renames, io ---------------------------
def test_datum_letters_resolve_relink_and_round_trip():
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40.0, "dy": 20.0, "dz": 4.0}))
    h = d.add(HoleFeature(name="bore", center=(10.0, 5.0, 0.0),
                          normal=(0.0, 0.0, -1.0), radius=5.0))
    pl = d.add_plane("XY", 5.0)
    d.datum_register("A", "plane", "XY")
    d.datum_register("B", "plane", pl["name"])
    d.datum_register("C", "hole-axis", h.uid)
    for bad in [lambda: d.datum_register("A", "axis", "X"),
                lambda: d.datum_register("O", "plane", "XY"),
                lambda: d.datum_register("D", "plane", "Ghost")]:
        with pytest.raises(params.ParamError):
            bad()
    assert d.datum_frame("A")[3] == [0.0, 0.0, 1.0]
    assert d.datum_frame("C") == ([10.0, 5.0, 0.0], [0.0, 0.0, -1.0])
    n = d.rename_datum(pl["name"], "Spine")
    assert n >= 1 and d.datums[1]["ref"] == "Spine"
    assert d.datum_frame("B")[0] == [0.0, 0.0, 5.0]
    # the uid-bound target survives a rename BYTE-IDENTICALLY
    # (M146's law for joints, copied): the entry never embeds the
    # name, so there is nothing for a rename to touch.
    entry = {"sym": "position", "tol": "\u2300 0.2", "mod": "M",
             "datums": ["A"], "target": {"uid": h.uid,
                                         "role": "axis"}}
    assert gdt.gdt_validate(entry) == []
    dump = json.dumps(entry, sort_keys=True)
    h.name = "bore-renamed"
    assert json.dumps(entry, sort_keys=True) == dump
    # io: datums ride the file; a legacy snapshot WITHOUT the key
    # loads byte-identical (M142's law)
    raw = json.dumps(d.to_dict(), sort_keys=True)
    back = Document.from_dict(json.loads(raw))
    assert [(x["letter"], x["kind"], x["ref"])
            for x in back.datums] == [("A", "plane", "XY"),
                                      ("B", "plane", "Spine"),
                                      ("C", "hole-axis", h.uid)]
    legacy = json.loads(raw)
    legacy.pop("datums")
    assert Document.from_dict(legacy).datums == []


# ---- G10: the dialog seam (guard-first, new grammar, arithmetic) --

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
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
    w.doc.add(HoleFeature(name="bore", center=(10.0, 5.0, 5.0),
                          normal=(0.0, 0.0, -1.0), radius=5.0,
                          depth=10.0, through=True))
    w.recompute()
    qapp.processEvents()
    w.action_new_drawing()
    w._add_dim("top", (0.0, 0.0), (40.0, 0.0), {})
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()
    qapp.processEvents()


def _fill(win):
    return win.doc.drawings[0]["dims"][0]


def test_target_combo_lists_exactly_the_publishing_features(win):
    labels = [n for n, _ in win._gdt_targets()]
    assert len(labels) == 1 and labels[0].startswith("bore")
    assert "\u00d810" in labels[0]                 # parametric size
    win.doc.add(PrimitiveFeature(name="boss", kind="cylinder",
                                 dims={"radius": 4.0,
                                       "height": 6.0}))
    labels = [n for n, _ in win._gdt_targets()]
    assert len(labels) == 2 and any(l.startswith("boss")
                                    for l in labels)
    # the box (wall family) is NOT offered — named continuation
    assert not any(l.startswith("plate") for l in labels)


def test_dialog_walks_the_new_grammar_and_speaks_the_arithmetic(
        win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.ui import cmddialog
    target = win._gdt_targets()[0][0]
    monkeypatch.setattr(
        cmddialog, "ask", lambda *a, **k: {
            "sym": "Position", "tol": "\u2300 0.2", "mod": "M",
            "angle": "", "datums": "A", "size": "H7", "proj": "",
            "target": target, "stack": False, "basic": False})
    win._annotate_gdt("top", 0)
    d = _fill(win)
    assert d["gdt"][0]["size"] == "H7"
    assert d["gdt"][0]["target"]["role"] == "axis"
    uid = win._gdt_targets()[0][1]
    assert d["gdt"][0]["target"]["uid"] == uid
    msg = win.status.currentMessage()
    assert "allowed on \u00d810" in msg and "bonus" in msg
    assert "VC \u00d89.8000" in msg                 # 10.0 - 0.2
    # the second frame stacks by index
    monkeypatch.setattr(
        cmddialog, "ask", lambda *a, **k: {
            "sym": "Perpendicularity", "tol": "0.05", "mod": "",
            "angle": "", "datums": "A", "size": "", "proj": "",
            "target": "\u2014 none \u2014", "stack": True,
            "basic": False})
    win._annotate_gdt("top", 0)
    assert len(_fill(win)["gdt"]) == 2
    assert _fill(win)["gdt"][1]["sym"] == "perpendicularity"


def test_illegal_new_grammar_pops_undo_and_names_the_law(
        win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.ui import cmddialog
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", classmethod(
        lambda cls, *a, **k: seen.append(str(a[2]))))
    monkeypatch.setattr(
        cmddialog, "ask", lambda *a, **k: {
            "sym": "Angularity", "tol": "0.1", "mod": "",
            "angle": "", "datums": "A", "size": "", "proj": "",
            "target": "\u2014 none \u2014", "stack": False,
            "basic": False})
    before = json.dumps(_fill(win), sort_keys=True)
    win._annotate_gdt("top", 0)
    assert json.dumps(_fill(win), sort_keys=True) == before
    assert seen and "TRUE angle" in seen[-1]
    # stacking without a first frame refuses by name
    seen.clear()
    _fill(win).pop("gdt", None)
    monkeypatch.setattr(
        cmddialog, "ask", lambda *a, **k: {
            "sym": "Parallelism", "tol": "0.1", "mod": "",
            "angle": "", "datums": "A", "size": "", "proj": "",
            "target": "\u2014 none \u2014", "stack": True,
            "basic": False})
    win._annotate_gdt("top", 0)
    assert "gdt" not in _fill(win) and seen and "FIRST frame" in \
        seen[-1]


def test_datum_registration_and_identifier_guard_first(
        win, qapp, monkeypatch):
    # no letters yet: the place action briefs, it never dialogs
    win.action_datum_identifier()
    assert "No datum letters yet" in win.status.currentMessage()
    from tracer.ui import cmddialog
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k:
                        {"letter": "A"})
    win._register_datum("plane", "XY", "plane XY")
    assert [d["letter"] for d in win.doc.datums] == ["A"]
    seen = []
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k:
                        {"letter": "A"})               # collide
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", classmethod(
        lambda cls, *a, **k: seen.append(str(a[2]))))
    win._register_datum("axis", "X", "work axis X")
    assert seen and "already names" in seen[-1]
    # now placement works
    monkeypatch.setattr(
        cmddialog, "ask", lambda *a, **k: {
            "letter": "A", "view": "top", "x": 12.0, "y": 6.0,
            "lead": True})
    win.action_datum_identifier()
    assert win.doc.drawings[0]["datums"][0]["letter"] == "A"
    ids = win.drawing.datum_ids_page()
    assert len(ids) == 1 and ids[0][0] == "A"
    assert ids[0][2] is not None                 # leader rides


# ---- G11: the paper ink — glyphs, proj cell, stack, identifiers ----

def _px(widget, qapp):
    import io

    import numpy as np
    from PIL import Image
    from PySide6.QtCore import QBuffer, QIODevice
    qapp.processEvents()
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    widget.grab().save(buf, "PNG")
    buf.close()
    return np.asarray(Image.open(io.BytesIO(bytes(buf.data())))
                      .convert("RGB")).astype(int)


def test_rung2_inks_the_sheet_and_stacks_honestly(win, qapp):
    cv = win.drawing
    base = _px(cv, qapp)
    red0 = int(((base[..., 0] - base[..., 1] > 25)
                & (base[..., 0] > 150)).sum())
    win.doc.drawings[0]["dims"][0]["gdt"] = [
        {"sym": "angularity", "tol": "0.1", "mod": "",
         "datums": ["A"], "angle": "60", "proj": "12"},
        {"sym": "circular_runout", "tol": "0.05", "mod": "",
         "datums": ["A"]}]
    red1 = int((lambda im: ((im[..., 0] - im[..., 1] > 25)
                            & (im[..., 0] > 150)).sum())(
        _px(cv, qapp)))
    assert red1 > red0 + 30                      # arc+arrow+proj ink
    # the stack chains: frame 2 hangs off frame 1's own rect
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
    assert len(seen) == 2
    (_, r1, f1), (g2, r2, f2) = seen
    box2 = 1.5 * max(8.0, r1.height() - 4.0)   # the painter's OWN
    assert r2.top() == pytest.approx(r1.bottom() + 0.25
                                     * box2, abs=1.0)   # box law
    widths = cv._gdt_cells_widths(g2, f2)
    assert r2.width() == pytest.approx(sum(widths), abs=1.0)
    # datum identifiers: the FIRST non-dim paper ink (sheet black).
    # The stamp's square KNOCKS OUT (paper fill), so anchor OUTSIDE
    # the silhouette and diff against the immediately prior paint.
    before = _px(cv, qapp)
    win.doc.drawings[0]["datums"] = [
        {"letter": "A", "view": "top", "anchor": [40.0, 25.0],
         "leader": [52.0, 37.0]}]
    dark0 = int((before.sum(axis=2) < 500).sum())
    after = _px(cv, qapp)
    dark1 = int((after.sum(axis=2) < 500).sum())
    assert dark1 > dark0 + 15                    # square+leader land


# ---- G12: travel — paper-only DXF counts, PDF, save/load -----------
def test_rung2_ink_never_enters_the_dxf_and_pdf_ships(win, qapp,
                                                      tmp_path):
    from tracer.core import import2d
    plain = str(tmp_path / "plain.dxf")
    win.export_drawing(plain)
    n0 = len(import2d.read(plain))
    win.doc.drawings[0]["dims"][0]["gdt"] = [
        {"sym": "angularity", "tol": "0.1", "mod": "M",
         "datums": ["A", "B"], "angle": "60", "proj": "12",
         "size": "H7"},
        {"sym": "profile_surface", "tol": "0.5", "mod": "",
         "datums": []}]
    win.doc.drawings[0]["dims"][0]["basic"] = True
    win.doc.drawings[0]["datums"] = [
        {"letter": "A", "view": "top", "anchor": [0.0, 0.0],
         "leader": [12.0, 12.0]}]
    rich = str(tmp_path / "rich.dxf")
    win.export_drawing(rich)
    assert len(import2d.read(rich)) == n0        # paper furniture
    n = win.drawing.publish_pdf(str(tmp_path / "gdt.pdf"))
    assert n >= 1                                # PDF ships the ink
    back = Document.from_dict(json.loads(json.dumps(
        win.doc.to_dict())))
    d = back.drawings[0]["dims"][0]
    assert d["gdt"][1]["sym"] == "profile_surface"
    assert d["gdt"][0]["proj"] == "12"
    assert back.drawings[0]["datums"][0]["letter"] == "A"

