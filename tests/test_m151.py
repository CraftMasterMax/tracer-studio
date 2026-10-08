"""M151 (sheet metal SM4): the flange hangs on a CHOSEN edge.

SM3 (M149) owned the bend but attached by CHAIN ORDER. SM4 makes the
edge the host: a flange names its host leg's UID and which end
("start"/"end"), so the strip grows at BOTH ends in any creation
order. The tree is UNREPRESENTABLY a path (one fold per edge, degree
<= 2), so the flat stays SM2's rectangle and every float stays `==`
the formula — the only new choice is the LINEARISATION, and that
choice is the association order, pinned to the spike's dumped floats
(contract research/sm4_flange_from_edge.md §3.5, §8). Refusals ride
BY NAME with the vendor's own reasons in the sentence (§2.2).

Gates mirror the contract plan: attach-at-start (G1), the both-ends
sheet (G2), the order IS a value (G3), sign invariance (G4), the
volume census (G5), interior reliefs (G6), the refusal names (G7),
the fold identity without a fold command (G8), io (G9), the lever
through the tree (G10), the dialog law (G12), the paper association
(G13), uid identity (G14). G11 is the build-time census (test_m149
untouched and green, collect-only grows by this file only).
"""
import json
import math

import numpy as np
import pytest

from tracer.core import sheetmetal
from tracer.core.document import Document, FlangeFeature
from tracer.core.sheetmetal import SheetMetalError

T, RI, K, W = 2.0, 3.0, 0.44, 40.0
BA = math.radians(90.0) * (3.0 + 0.44 * 2.0)     # repr 6.094689747964199


def _nd(name, uid, leg, host="", side="end", bend=None, relief=None,
        witness=None):
    return dict(name=name, uid=uid, leg=leg, host=host, side=side,
                bend=bend, relief=relief, witness=witness)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


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
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    qapp.processEvents()


# ---- G1: attach at START — the walk PREPENDS runs ----------------------

def test_attach_at_start_prepends_the_leg_and_the_band():
    w = sheetmetal.attach_walk([
        _nd("base", "b", 60.0),
        _nd("f30", "s", 30.0, host="b", side="start",
            bend=(90.0, RI, K))])
    assert w["legs"] == [30.0, 60.0]              # the walk prepends
    assert w["bands"] == {"s": 0}
    pl = sheetmetal.param_flat(w["legs"], w["bends"], T, W,
                               reliefs=w["reliefs"])
    assert pl["flat_length"] == (30.0 + BA) + 60.0
    assert pl["bend_lines"][0]["x"] == 30.0 + BA / 2.0
    assert pl["outline"] == [(0.0, 0.0), (pl["flat_length"], 0.0),
                             (pl["flat_length"], 40.0), (0.0, 40.0),
                             (0.0, 0.0)]          # SM2's rect, twin
    _sec, frames = sheetmetal.fold_section(w["legs"], w["bends"], T)
    assert frames[0]["x0"] == 30.0                # float-exact offset


# ---- G2: the both-ends sheet — the spike's repr, `==` ------------------

def test_both_ends_sheet_grows_at_start_and_end():
    d = Document("sm4")
    b, base = d.add_sheet(t=T, width=W, leg=60.0)
    fe = d.add_flange(b["name"], 40.0, -90.0, ri=RI, k_factor=K,
                      host=base.uid, side="end", witness=60.0)
    d.recompute()
    old_centre = d.sheet_states()[b["name"]]["flat"]["bend_lines"][0]["x"]
    fs = d.add_flange(b["name"], 30.0, 90.0, ri=RI, k_factor=K,
                      host=base.uid, side="start", witness=0.0)
    st = d.sheet_states()[b["name"]]
    assert st["flat"]["flat_length"] == ((30.0 + BA) + 60.0) + BA + 40.0
    assert st["flat"]["flat_length"] == 142.1893794959284  # spike repr
    bl = st["flat"]["bend_lines"]
    assert bl[0]["x"] == 30.0 + BA / 2.0
    assert bl[1]["x"] == ((30.0 + BA) + 60.0) + BA / 2.0
    assert bl[1]["x"] - old_centre == 30.0 + BA   # the OLD fold shifted
    assert st["order"] == [fs.name, base.name, fe.name]
    assert st["bands"] == {fs.uid: 0, fe.uid: 1}  # association, keyed
    assert d.result.to_trimesh().is_watertight


# ---- G3: the ORDER is a value; reliefs re-key to flat bands ------------

def test_association_order_survives_the_walk_as_a_value():
    bends = [(90.0, RI, K), (90.0, RI, K)]
    f1 = sheetmetal.param_flat([24.918, 89.63, 44.972], bends, T, W)
    f2 = sheetmetal.param_flat([24.918, 44.972, 89.63], bends, T, W)
    assert f1["flat_length"] == 171.7093794959284     # §3.5 dumped
    assert f2["flat_length"] == 171.70937949592837    # swapped
    assert f1["flat_length"] != f2["flat_length"]     # THE reason law


def test_second_created_first_placed_relief_notches_band_zero():
    d = Document("sm4")
    b, base = d.add_sheet(t=T, width=W, leg=60.0)
    d.add_flange(b["name"], 40.0, 90.0, ri=RI, k_factor=K,
                 host=base.uid, side="end")
    d.add_flange(b["name"], 30.0, 90.0, ri=RI, k_factor=K,
                 host=base.uid, side="start",
                 relief_gap=4.0, relief_depth=5.0)
    st = d.sheet_states()[b["name"]]
    (r,) = st["reliefs"]
    assert r == dict(bend=0, gap=4.0, depth=5.0)  # re-keyed to FLAT
    xc = st["flat"]["bend_lines"][0]["x"]
    xs = {p[0] for p in st["flat"]["outline"]}
    assert (xc - 2.0 in xs) and (xc + 2.0 in xs)  # notches band 0
    assert len(st["flat"]["outline"]) == 13       # rect + one relief


# ---- G4: the flat ignores signs; the body does not ---------------------

def test_flat_ignores_angle_signs_the_section_does_not():
    legs = [30.0, 60.0, 40.0]
    pa = sheetmetal.param_flat(legs, [(90.0, RI, K), (-90.0, RI, K)],
                               T, W)
    pb = sheetmetal.param_flat(legs, [(90.0, RI, K), (90.0, RI, K)],
                               T, W)
    assert pa["flat_length"] == pb["flat_length"]
    assert [bl["x"] for bl in pa["bend_lines"]] == \
        [bl["x"] for bl in pb["bend_lines"]]      # one flat, many folds
    a = np.asarray(sheetmetal.fold_section(
        legs, [(90.0, RI, K), (-90.0, RI, K)], T)[0])
    b = np.asarray(sheetmetal.fold_section(
        legs, [(90.0, RI, K), (90.0, RI, K)], T)[0])
    bb_a = (a[:, 0].min(), a[:, 0].max())
    bb_b = (b[:, 0].min(), b[:, 0].max())
    assert bb_a == pytest.approx((0.0, 78.0))     # hand-derived walk
    assert bb_a != pytest.approx(bb_b)            # the 3-D says NO


# ---- G5: the one volume law worth banking (§3.7) -----------------------

def test_volume_rides_the_true_annulus_not_t_ba():
    legs, bends = [30.0, 60.0, 40.0], [(90.0, RI, K), (-90.0, RI, K)]
    sol = sheetmetal.sheet_solid(legs, bends, T, W, n=240)
    law = W * (T * sum(legs)
               + 2 * (math.pi / 2) * (RI * T + T * T / 2.0))
    assert abs(sol.volume - law) < 1e-2           # measured 7.18e-3
    flat = sheetmetal.param_flat(legs, bends, T, W)["flat_length"]
    assert abs(sol.volume - W * T * flat) > 25    # K-law is NOT volume


# ---- G6: interior reliefs reach; the two size guards stay armed --------

def test_interior_band_relief_lands_where_the_band_lives():
    legs, bends = [30.0, 60.0, 40.0], [(90.0, RI, K), (-90.0, RI, K)]
    pl1 = sheetmetal.param_flat(legs, bends, T, W,
                                reliefs=[dict(bend=1, gap=4.0,
                                              depth=5.0)])
    assert len(pl1["outline"]) == 13
    xc = pl1["bend_lines"][1]["x"]
    xs = {p[0] for p in pl1["outline"]}
    assert (xc - 2.0 in xs) and (xc + 2.0 in xs)   # coords, exact ==
    pl2 = sheetmetal.param_flat(legs, bends, T, W,
                                reliefs=[dict(bend=0, gap=4.0,
                                              depth=5.0),
                                         dict(bend=1, gap=4.0,
                                              depth=5.0)])
    assert len(pl2["outline"]) == 21              # 5 + 8 + 8 shared
    s2 = sheetmetal.sheet_solid(legs, bends, T, W, n=120,
                                reliefs=[dict(bend=1, gap=4.0,
                                              depth=5.0)])
    s0 = sheetmetal.sheet_solid(legs, bends, T, W, n=120)
    rm, rc = RI + T / 2.0, RI + K * T
    law = 2 * 4.0 * (rm / rc) * T * 5.0
    assert abs((s0.volume - s2.volume) - law) < 1e-2
    assert s2.to_trimesh().is_watertight


def test_the_two_relief_size_guards_fire_by_name():
    legs, bends = [30.0, 3.0, 40.0], [(90.0, RI, K), (90.0, RI, K)]
    with pytest.raises(SheetMetalError, match="bend slot"):
        sheetmetal.param_flat(legs, bends, T, W,
                              reliefs=[dict(bend=0, gap=7.0,
                                            depth=5.0)])
    # The contract's two-SEPARATE-bands overlap case is UNREACHABLE:
    # overlap needs gap >= BA + leg, the slot guard refuses gap >= BA
    # first — the sweep is the duplicate-entry belt, and it bites:
    with pytest.raises(SheetMetalError, match="two reliefs overlap"):
        sheetmetal.param_flat(legs, bends, T, W,
                              reliefs=[dict(bend=0, gap=4.0, depth=5.0),
                                       dict(bend=0, gap=4.0, depth=5.0)])


# ---- G7: the refusal table, BY NAME (contract §2.2) --------------------

def test_every_sm4_refusal_speaks_its_own_name():
    d = Document("sm4")
    b, base = d.add_sheet(t=T, width=W, leg=60.0)
    with pytest.raises(SheetMetalError, match="ACROSS the sheet"):
        d.add_flange(b["name"], 10.0, 90.0, k_factor=K,
                     host=base.uid, side="side")
    d.add_flange(b["name"], 10.0, 90.0, k_factor=K,
                 host=base.uid, side="start")
    with pytest.raises(SheetMetalError, match="ONE fold per edge"):
        d.add_flange(b["name"], 12.0, 90.0, k_factor=K,
                     host=base.uid, side="start")
    with pytest.raises(SheetMetalError, match="hangs on leg"):
        d.add_flange(b["name"], 10.0, 90.0, k_factor=K,
                     host="deadbeef", side="end")
    with pytest.raises(SheetMetalError, match="FULL EDGE"):
        d.add_flange(b["name"], 10.0, 90.0, k_factor=K,
                     width_type="symmetric")
    with pytest.raises(SheetMetalError, match="extending to a face"):
        d.add_flange(b["name"], 10.0, 90.0, k_factor=K,
                     extent="to_object")
    with pytest.raises(SheetMetalError, match="that is a FOLD"):
        d.add_flange(b["name"], 10.0, 90.0, k_factor=K, station=25.0)
    with pytest.raises(SheetMetalError, match="shrank below"):
        d.add_flange(b["name"], 8.0, 90.0, k_factor=K,
                     host=base.uid, side="end", witness=999.0)
    assert len(d.features) == 2                   # one stood, eight fell


def test_sm3_voices_stand_repinned_here():
    d = Document("sm4")
    b, base = d.add_sheet(t=T, width=W, leg=60.0)
    base2 = FlangeFeature(name="second base", body=b["name"], t=3.0,
                          width=W, leg=20.0)
    d.features.append(base2)
    with pytest.raises(SheetMetalError, match="moves t"):
        d.recompute()
    d.features.remove(base2)
    d.add_flange(b["name"], 40.0, 90.0, k_factor=K, relief_gap=4.0)
    with pytest.raises(SheetMetalError,
                       match="BOTH gap and depth"):
        d.recompute()                             # the add-time law
    d.features.pop()                              # reliefless add gone
    with pytest.raises(SheetMetalError, match="zero is not a leg"):
        d.add_flange(b["name"], 0.0, 90.0, k_factor=K)
    rogue = FlangeFeature(name="base with relief", body="Ghost",
                          relief_gap=2.0, relief_depth=3.0)
    d.features.append(rogue)
    with pytest.raises(SheetMetalError, match="no bend"):
        d.recompute()


# ---- G8: fold identity — the RECEIPT that station is a bad input -------

def test_fold_identity_is_a_law_not_a_command():
    L0 = 60.0
    b1 = BA
    neq = 0
    wf = wc = 0.0
    for i in range(200):                           # ~200 stations
        s = 4.0 + i * (52.0 / 200.0)
        pf = sheetmetal.param_flat([s - b1 / 2.0, L0 - s - b1 / 2.0],
                                   [(90.0, RI, K)], T, W)
        if pf["flat_length"] != L0:
            neq += 1                               # contract census:
        wf = max(wf, abs(pf["flat_length"] - L0))  # 277/3000 lose ==
        wc = max(wc, abs(pf["bend_lines"][0]["x"] - s))
    assert neq > 0                                 # == is NOT the law
    assert wf < 1e-12 and wc < 1e-12               # 1e-12 IS the budget


# ---- G9: io — three keys ride, legacy files stand ----------------------

def test_io_carries_the_three_keys_and_legacy_stays_sm3():
    d = Document("sm4")
    b, base = d.add_sheet(t=T, width=W, leg=60.0)
    d.add_flange(b["name"], 30.0, 90.0, ri=RI, k_factor=K,
                 host=base.uid, side="start", witness=0.0)
    d.recompute()
    raw = json.dumps(d.to_dict())
    d2 = Document.from_dict(json.loads(raw))
    assert json.dumps(d2.to_dict()) == raw         # byte-identical
    fd = d2.to_dict()["features"][-1]
    assert (fd["host"], fd["side"], fd["witness"]) == (base.uid,
                                                       "start", 0.0)
    raw3 = json.loads(raw)
    for f in raw3["features"]:
        f.pop("host"), f.pop("side"), f.pop("witness")
    d3 = Document.from_dict(raw3)
    st = d3.sheet_states()[b["name"]]
    assert st["flat"]["flat_length"] == (60.0 + BA) + 30.0
    assert st["order"] == [base.name, "Flange 1 of Body 1"]
    assert d3.to_dict()["version"] == 2            # no bump: additive
    legacy = Document("sm3")
    lb, lbase = legacy.add_sheet(t=T, width=W, leg=60.0)
    legacy.add_flange(lb["name"], 40.0, 90.0, ri=RI)   # SM3, table K
    for f in legacy.to_dict()["features"]:
        f.pop("host"), f.pop("side"), f.pop("witness")
    l2 = Document.from_dict(legacy.to_dict())
    ba_t = math.radians(90.0) * (RI + 0.33 * T)
    assert l2.sheet_states()[lb["name"]]["flat"]["flat_length"] \
        == (60.0 + ba_t) + 40.0


# ---- G10: the lever through the TREE — upstream stands =-exact ---------

def test_middle_leg_lever_moves_downstream_not_upstream():
    d = Document("sm4")
    b, base = d.add_sheet(t=T, width=W, leg=60.0)
    d.add_flange(b["name"], 40.0, 90.0, ri=RI, k_factor=K,
                 host=base.uid, side="end")
    d.add_flange(b["name"], 30.0, 90.0, ri=RI, k_factor=K,
                 host=base.uid, side="start")
    st = d.sheet_states()[b["name"]]
    before = [bl["x"] for bl in st["flat"]["bend_lines"]]
    d.params["L1"] = "65"
    base.bindings["leg"] = "L1"                    # the MIDDLE leg now
    d.recompute()
    st = d.sheet_states()[b["name"]]
    after = [bl["x"] for bl in st["flat"]["bend_lines"]]
    assert after[0] == before[0] == 30.0 + BA / 2.0    # upstream `==`
    assert after[1] != before[1]
    assert after[1] == ((30.0 + BA) + 65.0) + BA / 2.0  # derived move
    assert st["flat"]["flat_length"] == ((30.0 + BA) + 65.0) + BA + 40.0


# ---- G12: the dialog law — guard first, choices[0] IS SM3 --------------

def _answers(monkeypatch, calls):
    from tracer.ui import cmddialog

    def fake_ask(parent, title, fields, remember_key=None):
        calls.append(title)
        v = {}
        for f in fields:
            if "default" in f:
                v[f["key"]] = f["default"]
            elif "choices" in f:
                v[f["key"]] = f["choices"][0]      # combo opens first
            else:
                v[f["key"]] = False
        return v
    monkeypatch.setattr(cmddialog, "ask", fake_ask)


def test_guard_first_no_dialog_for_non_sheets_or_full_sheets(
        qapp, win, monkeypatch):
    from tracer.core.document import PrimitiveFeature
    calls = []
    _answers(monkeypatch, calls)
    d = win.doc
    d.add_body("Solid")
    d.add(PrimitiveFeature(name="box", kind="box",
                           dims={"dx": 30, "dy": 20, "dz": 5}))
    d.recompute()
    win.action_add_flange()
    assert calls == []                             # guard, not gate
    assert "not a parametric sheet" in win.status.currentMessage()
    calls.clear()
    b2, base = d.add_sheet(t=2.0, width=40.0, leg=60.0)
    d.active_body = b2["name"]
    d.add_flange(b2["name"], 10.0, 90.0, k_factor=K,
                 host=base.uid, side="start")
    d.add_flange(b2["name"], 12.0, 90.0, k_factor=K,
                 host=base.uid, side="end")
    # A PATH always keeps its two far ends free (G12's census truth:
    # every edge claimed is UNREPRESENTABLE without a ring), so the
    # guard is state-driven: a walk that says NO free edge gets the
    # status line, never a dialog.
    d.sheet_states()[b2["name"]]["free"] = []
    calls.clear()
    win.action_add_flange()
    assert calls == []                             # guard, not gate
    assert "fold per edge" in win.status.currentMessage()


def test_head_choice_of_the_edge_combo_is_still_sm3(qapp, win,
                                                    monkeypatch):
    calls = []
    _answers(monkeypatch, calls)
    win.action_new_sheet()
    d = win.doc
    body = d.active_body
    base = d.features[0]
    win.action_add_flange()                        # fake: choices[0]
    assert calls == ["New Sheet", "Add Flange"]
    feat = d.features[-1]
    assert isinstance(feat, FlangeFeature)
    assert (feat.host, feat.side) == (base.uid, "end")   # SM3's spot
    ba_t = math.radians(90.0) * (3.0 + 0.33 * 2.0)  # table K rides
    assert d.sheet_states()[body]["flat"]["flat_length"] \
        == (60.0 + ba_t) + 40.0
    msg = win.status.currentMessage()
    assert "Flange:" in msg and "K 0.33 (table)" in msg
    assert "end edge @ 60.00 mm" in msg            # the station speaks


# ---- G13: the paper — label TEXT rides its OWN band (zero new code) ----

def test_three_leg_paper_labels_match_their_own_bands(qapp, win,
                                                      tmp_path):
    d = win.doc
    b, base = d.add_sheet(t=T, width=W, leg=60.0)
    d.add_flange(b["name"], 40.0, -90.0, ri=RI, k_factor=K,
                 host=base.uid, side="end")
    d.add_flange(b["name"], 30.0, 90.0, ri=RI, k_factor=K,
                 host=base.uid, side="start")
    d.recompute()
    win.action_new_drawing()
    qapp.processEvents()
    st = d.sheet_states()[b["name"]]
    segs = win.drawing.bends_page("Flat")
    labels = win.drawing.bend_labels("Flat")
    assert len(segs) == len(st["bends"]) == len(labels) == 2
    for (at, txt), (a, r, k) in zip(labels, st["bends"]):
        arrow = "\u2191" if a >= 0 else "\u2193"
        assert txt == f"{abs(a):g}\u00b0 {arrow} R{r:.2f} K={k:g}"
    dxf = tmp_path / "sm4.dxf"
    win.export_drawing(str(dxf))
    ink = dxf.read_text(encoding="utf-8")
    assert sum(t in ink for (_a, t) in labels) == 2  # both labels ride
    n = win.drawing.publish_pdf(str(tmp_path / "sm4.pdf"))
    assert n >= 1
    slab = d.flat_slab(b["name"]).to_trimesh().vertices
    assert np.asarray(slab)[:, 2].max() == pytest.approx(0.01)


# ---- G14: identity survives — uid hosts, named orphans -----------------

def test_rename_of_the_host_moves_nothing_delete_names_the_children(
        qapp, win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.ui import mainwindow as mw
    d = win.doc
    b, base = d.add_sheet(t=T, width=W, leg=60.0)
    d.add_flange(b["name"], 40.0, 90.0, ri=RI, k_factor=K,
                 host=base.uid, side="end")
    d.add_flange(b["name"], 30.0, 90.0, ri=RI, k_factor=K,
                 host=base.uid, side="start")
    st = d.sheet_states()[b["name"]]
    f_before = st["flat"]["flat_length"]
    monkeypatch.setattr(mw.Shell, "getText",
                        classmethod(lambda cls, *a, **k:
                                    ("Root leg", True)))
    win._rename_feature(base)                      # the raw-write path
    st = d.sheet_states()[b["name"]]
    assert st["flat"]["flat_length"] == f_before   # uid: rename-immune
    assert base.name == "Root leg"
    assert "Root leg" in st["order"]               # audit trail follows
    assert len(d.flange_references(base.uid)) == 2
    kept = []
    monkeypatch.setattr(QMessageBox, "question", classmethod(
        lambda cls, parent, title, text, *a, **k:
        kept.append((title, text)) or cls.No))
    win._delete_feature(base)
    assert kept and "hang here" in kept[0][0]
    assert "Root leg" in kept[0][1] or base.name in kept[0][1]
    assert "kept" in win.status.currentMessage()
    assert base in d.features                      # refused, undone
    monkeypatch.setattr(QMessageBox, "question", classmethod(
        lambda cls, *a, **k: cls.Yes))
    d.features.remove(base)                        # the forceful path
    with pytest.raises(SheetMetalError, match="hangs on leg"):
        d.recompute()
