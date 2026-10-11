"""M158 — SM5 rung 1: the fold is a STATION OPERATOR on the strip.
Every law here was frozen on executed receipts first: the contract
(fleet/research/sm5_fold_contract.md §1 L1-L10, §2 spike-2 S1-S6)
promised this file its gates, and every literal below is a GOLDEN
the kernel itself spoke (GOLDEN LAW) — measured, not hand-derived.
The spine is ADDITIVITY (M157's doctrine, kept): attach_walk without
a fold never passes t, never enters the fold branch, and walks
byte-identical — the whole older suite riding green IS gate G10.
Flat preservation is measured BYTE-EXACT at the pinned stations
(L1: Onshape's "the bend does not affect the flat" made law); the
witness chooses the SPLIT, the preserved BA fixes the TOTAL (L3).
0-deg folds REFUSE (L5 — free per S2, zero citations owed); the
feared self-intersection was MEASURED DOWN (S6) — rung 1 ships no
collision predicate, the numeric overflow refusal IS the law (L10).
Corner/miter lane is rung 2, banked by name in §5, not built here."""
import math
import random
import time

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from tracer.core import sheetmetal as sm
from tracer.core.document import (Document, FoldFeature, FlangeFeature,
                                  _feat_sig)
from tracer.core.io import load_document, save_document

T, R, K = 2.0, 1.6, 0.44
BA = sm.bend_allowance(T, R, 90.0, K)      # 3.8955748904513436 (S3)
B90 = (90.0, R, K)

# GOLDENS — the kernel's own measured words, byte-for-byte.
FLAT_PRE = 73.89557489045134               # [40,30] + one 90 bend
AXIS_LEGS = [18.05221255477433, 18.05221255477433, 30.0]
BTL_LEGS = [20.0, 16.104425109548657, 30.0]
IML_LEGS = [18.4, 17.70442510954866, 30.0]
OML_LEGS = [16.4, 19.70442510954866, 30.0]
TWO_LEGS = [18.05221255477433, 6.104425109548657,
            8.052212554774329, 30.0]


def node(name, uid, leg, host, side, bend=None, witness=None,
         wkind=None, relief=None):
    return dict(name=name, uid=uid, leg=leg, bend=bend, relief=relief,
                host=host, side=side, witness=witness, wkind=wkind)


def strip(fold_spec=None, extra=()):
    """Base 40 + Flange1 30 on the end edge; optionally one fold node
    (name, w, wkind[, bend][, host]) spliced second, extras AFTER the
    flange (stream order is the uid registry's owner)."""
    nodes = [node("Base", "b", 40.0, "", "start"),
             node("Flange1", "l", 30.0, "b", "end", bend=B90)]
    out = [nodes[0]]
    if fold_spec is not None:
        out.append(fold(*fold_spec))
    out.append(nodes[1])
    out.extend(extra)
    return out


def fold(name, w, wkind="axis", bend=B90, host="b"):
    return node(name, name.lower(), None, host, "fold", bend=bend,
                witness=w, wkind=wkind)


def flat_of(nodes):
    o = sm.attach_walk(nodes, t=T)
    return sm.param_flat(o["legs"], o["bends"], T, 10.0)["flat_length"]


# ---------------------------------------------------------------- G1
def test_g1_fold_preserves_flat_byte_exact():
    """L1: a fold is STATION ARITHMETIC, not material. axis/btl/oml
    and the two-fold stack all land the SAME flat, byte for byte."""
    assert flat_of(strip()) == FLAT_PRE
    for spec in (("F", 20.0), ("F", 20.0, "btl"), ("F", 20.0, "iml"),
                 ("F", 20.0, "oml")):
        assert flat_of(strip(spec)) == FLAT_PRE, spec
    assert flat_of(strip(extra=(fold("F1", 20.0),
                                fold("F2", 30.0)))) == FLAT_PRE


# ---------------------------------------------------------------- G2
def test_g2_split_sum_exact_and_walk_identity_holds():
    """L2: pieces + band telescope back to the host leg EXACT at the
    pinned station (byte), and the runs-walk identity holds at EVERY
    station of a 1000-fold random sweep — association is law, and
    each station is the kernel's own byte-exact accumulation."""
    o = sm.attach_walk(strip(("F", 20.0)), t=T)
    assert o["legs"][0] + o["legs"][1] == 40.0 - BA          # byte
    random.seed(11)                                          # pinned
    for _ in range(1000):
        L = random.uniform(30.0, 300.0)
        phi = random.uniform(-175.0, 175.0)
        while abs(phi) < 15.0:
            phi = random.uniform(-175.0, 175.0)
        wk = random.choice(("axis", "btl", "iml", "oml"))
        ba = sm.bend_allowance(T, R, phi, K)
        cl = {"axis": ba / 2.0, "btl": 0.0,
              "iml": math.tan(math.radians(abs(phi)) / 2.0) * R,
              "oml": sm.outside_setback(T, R, phi)}[wk]
        w = random.uniform(cl + 1e-6, L - (ba - cl) - 1e-6)
        nodes = [node("Base", "b", L, "", "start"),
                 fold("F", w, wk, bend=(phi, R, K)),
                 node("Flange1", "l", 30.0, "b", "end", bend=B90)]
        o = sm.attach_walk(nodes, t=T)
        f = sm.param_flat(o["legs"], o["bends"], T, 10.0)
        runs = f["runs"]
        for i in range(len(runs) - 1):                       # L2 law
            step = runs[i + 1]["x0"] - runs[i]["x0"]
            want = (runs[i]["extent"] if runs[i]["kind"] == "leg"
                    else runs[i]["ba"])
            assert abs(step - want) <= 1e-12, (wk, phi, w, i)
        last = runs[-1]
        assert abs(last["x0"] + last["extent"]
                   - f["flat_length"]) <= 1e-12
        assert abs(o["legs"][0] + ba + o["legs"][1] - L) <= 1e-12


# ---------------------------------------------------------------- G3
def test_g3_flange_grows_the_fold_does_not():
    """L1's two halves in one gate: a FLANGE grows the flat by its
    leg + BA (SM4 receipt byte-stands); a FOLD grows it by ZERO."""
    pre = flat_of(strip())
    post = flat_of(strip(extra=(node("Flange2", "m", 25.0, "l", "end",
                                     bend=B90),)))
    assert post - pre == pytest.approx(25.0 + BA, abs=1e-12)
    assert flat_of(strip(("F", 20.0))) - pre == 0.0           # byte


# ---------------------------------------------------------------- G4
def test_g4_domain_refusals_numeric_voices():
    """L5/L9: 0-deg REFUSES with the numeric voice (free per S2);
    +-180 keeps the SHIPPED voice's class; 179.999 still rides; and
    the ri/t/K refusals speak the EXACT text _param_check would have
    spoken — the fold rides the SHIPPED choke, untouched, only
    earlier (SheetMetalError is a ValueError, same family)."""
    with pytest.raises(sm.SheetMetalError) as e:
        sm.attach_walk(strip(("F", 20.0, "axis", (0.0, R, K))), t=T)
    assert "0-degree" in str(e.value) and "seam" in str(e.value)
    for phi in (180.0, -180.0):
        with pytest.raises(sm.SheetMetalError) as e:
            sm.attach_walk(strip(("F", 20.0, "axis", (phi, R, K))), t=T)
        assert "180 degrees" in str(e.value)
    assert flat_of(strip(("F", 20.0, "axis", (179.999, R, K)))) > 0.0
    for bad, want in (((90.0, 0.0, K), "positive thickness"),
                      ((90.0, R, 1.5), "0 < K <= 1"),
                      ((90.0, R, 0.0), "0 < K <= 1")):
        with pytest.raises(ValueError) as e:                  # choke
            sm.attach_walk(strip(("F", 20.0, "axis", bad)), t=T)
        fl_bad = [node("Base", "b", 40.0, "", "start"),
                  node("Flange1", "l", 30.0, "b", "end", bend=bad)]
        ordered = sm.attach_walk(fl_bad)                      # flanges
        with pytest.raises(ValueError) as ref:                # arrive
            sm._param_check(T, 10.0, ordered["legs"],
                            ordered["bends"])                 # LATE
        assert want in str(e.value) and str(e.value) == str(ref.value)
    with pytest.raises(sm.SheetMetalError) as e:              # t gate
        sm.attach_walk(strip(("F", 20.0)), t=None)
    assert "thickness" in str(e.value)


# ---------------------------------------------------------------- G5
def test_g5_witness_table_and_interior_only():
    """L3/L8/L9: the four witnesses split the preserved BA the four
    documented ways (GOLDENS byte-pinned); an unknown role refuses by
    name; and the band's two ends may never touch a leg END — the
    edge slots belong to flanges (L8), the interior to folds."""
    o = sm.attach_walk(strip(("F", 20.0)), t=T)
    assert o["legs"] == AXIS_LEGS                              # byte
    assert o["order"] == ["Base[0]", "Base[1]", "Flange1"]
    assert o["bands"] == {"f": 0, "l": 1}
    assert [(f["name"], f["side"]) for f in o["free"]] == \
        [("Base", "start"), ("Flange1", "end")]
    for wk, gold in (("btl", BTL_LEGS), ("iml", IML_LEGS),
                     ("oml", OML_LEGS)):
        assert sm.attach_walk(strip(("F", 20.0, wk)), t=T)["legs"] \
            == gold, wk                                        # byte
    with pytest.raises(sm.SheetMetalError) as e:
        sm.attach_walk(strip(("F", 20.0, "xyz")), t=T)
    assert "axis, btl, iml or oml" in str(e.value)
    for w, wk in ((0.0, "btl"), (40.0, "btl"), (-1.0, "axis"),
                  (2.0, "oml")):                               # overflow
        with pytest.raises(sm.SheetMetalError):
            sm.attach_walk(strip(("F", w, wk)), t=T)
    # a fold may NOT live on an edge: w=0 btl speaks the fit voice
    with pytest.raises(sm.SheetMetalError) as e:
        sm.attach_walk(strip(("F", 0.0, "btl")), t=T)
    assert "does not fit" in str(e.value)


# ---------------------------------------------------------------- G6
def test_g6_held_is_blind_to_the_walk():
    """L6 (S5's theorem): attach_walk takes NO held argument — the
    station walk is held-invariant BY CONSTRUCTION. Injected held
    keys must perturb nothing, byte for byte."""
    plain = sm.attach_walk(strip(("F", 20.0)), t=T)
    for flip in ("b", "l", None):
        nodes = strip(("F", 20.0))
        nodes[0]["held"] = flip
        nodes[1]["held"] = "l" if flip != "l" else "b"
        o = sm.attach_walk(nodes, t=T)
        assert o["legs"] == plain["legs"] and o["order"] == \
            plain["order"] and o["bends"] == plain["bends"]


# ---------------------------------------------------------------- G7
def test_g7_mid_insert_never_permutes_tags():
    """L7: the fold is pure re-projection — its STREAM position (and
    even two folds' stream order) never perturbs the walk: legs,
    orders and band tickets are byte-equal across permutations."""
    a = sm.attach_walk(strip(("F", 20.0)), t=T)
    late = [node("Base", "b", 40.0, "", "start"),
            node("Flange1", "l", 30.0, "b", "end", bend=B90),
            fold("F", 20.0)]
    b = sm.attach_walk(late, t=T)
    assert (a["legs"], a["order"], a["bends"], a["bands"]) == \
        (b["legs"], b["order"], b["bends"], b["bands"])        # byte
    fwd = [node("Base", "b", 40.0, "", "start"), fold("F1", 20.0),
           fold("F2", 30.0),
           node("Flange1", "l", 30.0, "b", "end", bend=B90)]
    rev = [fwd[0], fwd[2], fwd[1], fwd[3]]
    o1, o2 = sm.attach_walk(fwd, t=T), sm.attach_walk(rev, t=T)
    assert o1["legs"] == TWO_LEGS                              # byte
    assert o1["legs"] == o2["legs"] and o1["order"] == o2["order"]
    assert o1["bands"] == {"f1": 0, "f2": 1, "l": 2}
    assert o1["bands"] == o2["bands"]


# ---------------------------------------------------------------- G8
def test_g8_sign_the_flat_blinds_itself_the_body_keeps_it():
    """L4 (S1/S3 pinned): BA is |theta| currency and the WALK cannot
    see sign — legs/order byte-equal under +-phi; the band tuples
    carry the sign, and fold_section WALKS it: +90 sweeps y -1..32.6,
    -90 lands the mirror -32.6..1, byte-exact goldens."""
    assert sm.bend_allowance(T, R, 90.0, K) == \
        sm.bend_allowance(T, R, -90.0, K)                      # byte
    up = sm.attach_walk(strip(("F", 20.0)), t=T)
    dn = sm.attach_walk(strip(("F", 20.0, "axis", (-90.0, R, K))), t=T)
    assert up["legs"] == dn["legs"] and up["order"] == dn["order"]
    assert up["bends"][0] == B90 and dn["bends"][0] == (-90.0, R, K)
    sp = sm.fold_section([40.0, 30.0], [(90.0, R, K)], T)[0]
    sq = sm.fold_section([40.0, 30.0], [(-90.0, R, K)], T)[0]
    assert sp.shape == sq.shape
    assert float(sp[:, 1].min()) == -1.0 and float(sp[:, 1].max()) == 32.6
    assert float(sq[:, 1].min()) == -32.6 and float(sq[:, 1].max()) == 1.0


# ---------------------------------------------------------------- G9
def test_g9_overflow_prints_the_deficit_and_names_the_fixes():
    """L10 (measured down, S6): NO collision predicate ships — the
    numeric overflow refusal IS the user-facing law. Both edges of
    the leg must print numbers and name BOTH fixes."""
    with pytest.raises(sm.SheetMetalError) as e:               # head
        sm.attach_walk(strip(("F", 3.0, "oml")), t=T)          # band
    msg = str(e.value)                                         # starts
    assert "does not fit" in msg and "shrink the angle" in msg \
        and "lengthen the leg" in msg and "0.600" in msg       # at -0.6
    with pytest.raises(sm.SheetMetalError) as e:               # tail
        sm.attach_walk(strip(("F", 39.0, "axis")), t=T)
    msg = str(e.value)
    assert "does not fit" in msg and "short by" in msg \
        and "move" in msg and "0.948" in msg
    # and the S6 receipt itself: the 170-deg horror lands CLEAN —
    # no self-intersection predicate, the section just walks.
    pts = sm.fold_section([40.0, 4.0], [(170.0, R, K)], T)[0]
    assert pts.shape[0] > 4                                    # valid


# ------------------------------------------------------- structure
def test_fold_growth_is_additive_the_m157_doctrine():
    """The no-fold walk must not even SEE the new code: without t it
    refuses folds, with folds absent t is never needed, and the
    flange-only output is byte-equal whether or not t was offered."""
    plain = sm.attach_walk(strip())
    offered = sm.attach_walk(strip(), t=T)
    assert plain["legs"] == offered["legs"] == [40.0, 30.0]
    assert plain["order"] == ["Base", "Flange1"]
    for bad, why in ((dict(fold("F", 20.0), leg=5.0), "adds NO wall"),
                     (dict(fold("F", 20.0), host=""), "named host"),
                     (dict(fold("F", 20.0),
                           relief=dict(gap=1.0, depth=1.0)), "corner"),
                     (dict(fold("F", 20.0), witness=None), "position")):
        nodes = [node("Base", "b", 40.0, "", "start"), bad,
                 node("Flange1", "l", 30.0, "b", "end", bend=B90)]
        with pytest.raises(sm.SheetMetalError) as e:
            sm.attach_walk(nodes, t=T)
        assert why in str(e.value)
    # walls hang on LEGS, not on folds (host-uid guard)
    with pytest.raises(sm.SheetMetalError) as e:
        sm.attach_walk([node("Base", "b", 40.0, "", "start"),
                        fold("F", 20.0),
                        node("Wall", "w", 10.0, "f", "end", bend=B90)],
                       t=T)
    assert "which is a fold" in str(e.value)
    # ...but a fold on a FLANGE's leg is legal and names its pieces
    o = sm.attach_walk([node("Base", "b", 40.0, "", "start"),
                        fold("F", 20.0),
                        node("Flange1", "l", 30.0, "b", "end", bend=B90),
                        fold("F2", 15.0, host="l")], t=T)
    assert o["order"] == ["Base[0]", "Base[1]", "Flange1[0]",
                          "Flange1[1]"]
    assert o["bands"] == {"f": 0, "l": 1, "f2": 2}


# ------------------------------------------------------- K2: document
def sheet_doc():
    d = Document("fold-doc")
    b, base = d.add_sheet(t=2.0, width=10.0, leg=40.0,
                          material="mild-steel", name="Sheet")
    fl = d.add_flange(b["name"], leg=30.0, angle=90.0, ri=1.6,
                      k_factor=0.44, host=base.uid, side="end")
    d.recompute()
    return d, b, base, fl


def test_k2_fold_is_document_truth():
    """The whole ladder end-to-end: the flat rides BYTE-EXACT
    (G1's document twin) while the folded BODY grows by the band's
    sector — the two currencies of L1 in one receipt (goldens
    measured, GOLDEN LAW)."""
    d, b, base, fl = sheet_doc()
    vol_pre = d._body_solids[b["name"]].volume
    f = d.add_fold(b["name"], host=base.uid, position=20.0,
                   angle=90.0, ri=1.6, k_factor=0.44)
    d.recompute()
    st = d.sheet_states()[b["name"]]
    assert st["legs"] == AXIS_LEGS                        # byte
    assert st["flat"]["flat_length"] == FLAT_PRE          # byte
    assert st["order"] == ["Base flange of Sheet[0]",
                           "Base flange of Sheet[1]",
                           "Flange 1 of Sheet"]
    assert st["bands"][f.uid] == 0
    assert [(x["name"], x["side"]) for x in st["free"]] == [
        ("Base flange of Sheet", "start"),
        ("Flange 1 of Sheet", "end")]
    assert vol_pre == 1481.532201335718                   # golden
    assert d._body_solids[b["name"]].volume == 1485.1529050128856


def test_k2_refusals_are_fail_first_and_speak_the_kernel():
    """add_fold walks the TRIAL stream; every refusal is the
    kernel's own voice and the document is UNTOUCHED after."""
    d, b, base, fl = sheet_doc()
    kinds = [type(f).__name__ for f in d.features]
    for pos, ang, host, wk in [(50.0, 90.0, base.uid, "axis"),
                               (20.0, 0.0, base.uid, "axis"),
                               (20.0, 90.0, "nope", "axis"),
                               (3.0, 90.0, base.uid, "oml"),
                               (20.0, 180.0, base.uid, "axis"),
                               (20.0, 90.0, base.uid, "xyz")]:
        with pytest.raises(Exception) as e:
            d.add_fold(b["name"], host=host, position=pos,
                       angle=ang, ri=1.6, k_factor=0.44,
                       wkind=wk)
        msg = str(e.value)
        assert any(w in msg for w in ("does not fit", "seam",
                                      "not a leg", "180 degrees",
                                      "axis, btl, iml")), msg
    assert [type(f).__name__ for f in d.features] == kinds


def test_k2_round_trips_carry_every_lever():
    """to_dict/from_dict and the FILE both rebuild the fold with
    uid, host, wkind and numbers intact — the flat arrives
    byte-equal on both roads."""
    d, b, base, fl = sheet_doc()
    f = d.add_fold(b["name"], host=base.uid, position=20.0,
                   angle=-90.0, ri=1.6, k_factor=0.44,
                   wkind="iml", held=fl.uid)
    d.recompute()
    want = d.sheet_states()[b["name"]]["flat"]["flat_length"]
    d2 = Document.from_dict(d.to_dict())
    d2.recompute()
    got = d2.sheet_states()[b["name"]]["flat"]["flat_length"]
    assert got == want                                    # byte
    f2 = next(x for x in d2.features
              if isinstance(x, FoldFeature))
    assert (f2.uid, f2.host, f2.wkind, f2.held, f2.position,
            f2.angle) == (f.uid, f.host, f.wkind, f.held,
                          f.position, f.angle)
    from pathlib import Path
    out = Path(__file__).parent / "_k2_rt.trz"
    try:
        save_document(d, out)
        d3 = load_document(out)
        d3.recompute()
        assert d3.sheet_states()[b["name"]]["flat"]["flat_length"] \
            == want                                        # byte
    finally:
        out.unlink(missing_ok=True)


def test_k2_delete_guard_lists_folds_and_fingerprint_sees_them():
    """The leg cannot vanish under a fold: flange_references names
    the fold beside its flanges (uid-bound, M151 law), and the M148
    stream fingerprint reads every fold lever — wkind is growth."""
    d, b, base, fl = sheet_doc()
    f = d.add_fold(b["name"], host=base.uid, position=20.0,
                   angle=90.0, ri=1.6, k_factor=0.44)
    refs = d.flange_references(base.uid)
    assert f.name in refs and fl.name in refs
    assert d.flange_references(fl.uid) == []
    sig = _feat_sig(f)
    f.wkind = "oml"
    assert _feat_sig(f) != sig                             # growth
    f.wkind = "axis"
    f.position = 21.0
    assert _feat_sig(f) != sig


def test_k2_held_is_view_state_the_stream_never_reads():
    """L6 at the document door: flipping held re-derives the SAME
    legs, bends and flat, byte for byte."""
    d, b, base, fl = sheet_doc()
    f = d.add_fold(b["name"], host=base.uid, position=20.0,
                   angle=90.0, ri=1.6, k_factor=0.44)
    d.recompute()
    st0 = d.sheet_states()[b["name"]]
    snap = (list(st0["legs"]), list(st0["bends"]),
            st0["flat"]["flat_length"])
    f.held = fl.uid
    d.recompute()
    st1 = d.sheet_states()[b["name"]]
    assert (list(st1["legs"]), list(st1["bends"]),
            st1["flat"]["flat_length"]) == snap            # byte


# ------------------------------------------------------- K3: the door
@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_k3_the_fold_door_opens_and_prints_the_law(qapp, monkeypatch):
    """Tools ▸ Add Fold end-to-end: the dialog answers the table,
    the fold lands in the stream, the status line carries the SPLIT
    and the word UNCHANGED — the law on the user's tongue. The
    refusal route keeps the stream untouched behind a warning."""
    from tracer.ui import cmddialog
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    w.new_document()
    d = Document("door")
    b, base = d.add_sheet(t=2.0, width=10.0, leg=40.0,
                          material="mild-steel", name="Sheet")
    d.add_flange(b["name"], leg=30.0, angle=90.0, ri=1.6,
                 k_factor=0.44, host=base.uid, side="end")
    w.doc = d
    w.recompute()
    for _ in range(8):
        qapp.processEvents()
        time.sleep(0.02)
    answers = dict(leg=f"Base flange of Sheet \u00b7 leg 40 mm",
                   pos=20.0,
                   wkind="band axis (line centred on the pick)",
                   angle=90.0, ri=1.6, pin=True, k=0.44)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: dict(answers))
    w.action_add_fold()
    for _ in range(8):
        qapp.processEvents()
        time.sleep(0.02)
    folds = [x for x in w.doc.features
             if isinstance(x, FoldFeature)]
    assert len(folds) == 1 and folds[0].wkind == "axis"
    msg = w.status.currentMessage()
    assert "UNCHANGED" in msg and "18.052 + 18.052" in msg
    st = w.doc.sheet_states()["Sheet"]
    assert st["flat"]["flat_length"] == FLAT_PRE           # byte
    # the refusal route: the kernel's mouth reaches the box, the
    # stream stays exactly as it was
    answers.update(pos=50.0)
    boxes = []
    import tracer.ui.mainwindow as mw
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        classmethod(lambda cls, *a, **k:
                                    boxes.append(a[2])))
    w.action_add_fold()
    assert len(boxes) == 1 and "does not fit" in boxes[0]
    assert len([x for x in w.doc.features
                if isinstance(x, FoldFeature)]) == 1
    w._unsaved = False
    w.close()
    qapp.processEvents()
