"""M149 (sheet metal SM3): the parametric flange — the flat is FORMULA.

The detector path reads what a mesh confesses (SM1/SM2's oracle law);
the parametric path OWNS the bend: t, W, tangent-to-end legs and
signed (angle, ri, K) bends are INPUTS, so every flat float is `==`
the formula — association order included (float + is not associative;
the walk's x += leg, x += ba ORDER is law and every golden here
re-derives in that same written form, independently of the code).

G-gates per the banked contract (research/sm3_flange_feature.md §6):
law `==` (G2), the fuzz census BOTH directions (G3), params follow
edits (G4), relief notch law (G5), the ONE-number seam (G6), the K
sidecar staying loud and unstandardized (G7), and the file round
trip (G8). G1's prism and the refusal voices ride the document.
"""
import json
import math
import subprocess
from pathlib import Path

import pytest

from tracer.core import sheetmetal
from tracer.core import ksolver
from tracer.core.document import Document
from tracer.core.sheetmetal import SheetMetalError

T, RI, K, W = 2.0, 3.0, 0.44, 40.0
BA = math.radians(90.0) * (3.0 + 0.44 * 2.0)     # repr 6.094689747964199


# ---- G2: the law, `==`, not ~  ----------------------------------------

def test_flat_is_formula_association_order_is_law():
    pl = sheetmetal.param_flat([60.0, 40.0], [(90.0, RI, K)], T, W)
    assert pl["runs"][1]["ba"] == BA
    assert pl["flat_length"] == (60.0 + BA) + 40.0 == 106.0946897479642
    assert pl["bend_lines"][0]["x"] == 60.0 + BA / 2.0
    assert pl["outline"] == [(0.0, 0.0), (pl["flat_length"], 0.0),
                             (pl["flat_length"], 40.0), (0.0, 40.0),
                             (0.0, 0.0)]           # SM2's rect, twins
    assert pl["width"] == 40.0                     # W is an INPUT here


def test_last_leg_edit_moves_the_flat_not_the_fold():
    pl = sheetmetal.param_flat([60.0, 50.0], [(90.0, RI, K)], T, W)
    assert pl["flat_length"] == (60.0 + BA) + 50.0
    assert pl["bend_lines"][0]["x"] == 60.0 + BA / 2.0   # fold stands


# ---- G3: the fuzz census — detector ~, param == -------------------------

def test_detector_fuzz_is_real_and_param_path_dodges_it():
    """Same inputs: the folded twin measured the SM1 way drifts in
    (1e-9, 1e-3) — passes house totals, fails every identity; the
    param path IS the identity. Both inequalities pinned (weakness #1
    named and shut)."""
    sol = sheetmetal.sheet_solid([60.0, 40.0], [(90.0, RI, K)], T, W)
    det = sheetmetal.flat_outline(sol, K=K)
    pl = sheetmetal.param_flat([60.0, 40.0], [(90.0, RI, K)], T, W)
    for got, want in ((det["flat_length"], pl["flat_length"]),
                      (det["thickness"], T),
                      (det["bands"][0]["ri"], RI)):
        assert 1e-9 < abs(got - want) < 1e-3
    assert pl["flat_length"] == (60.0 + BA) + 40.0       # exact stands


# ---- G5: reliefs — the SM2 rectangle PLUS notch vertices ----------------

def test_no_relief_is_sm2_and_one_relief_is_thirteen_pts():
    plain = sheetmetal.param_flat([60.0, 40.0], [(90.0, RI, K)], T, W)
    assert len(plain["outline"]) == 5                    # SM2's count
    rel = [{"bend": 0, "gap": T, "depth": RI + T}]       # shop defaults
    pl = sheetmetal.param_flat([60.0, 40.0], [(90.0, RI, K)], T, W,
                               reliefs=rel)
    o = pl["outline"]
    assert len(o) == 13 and o[0] == o[-1]                # ONE chain
    xc = 60.0 + BA / 2.0
    assert (xc - T / 2.0, RI + T) in o and (xc + T / 2.0, RI + T) in o
    assert (xc + T / 2.0, W - (RI + T)) in o             # top row twin
    assert o.count((xc - T / 2.0, 0.0)) == 1


def test_relief_dv_is_formula_predicted_not_measured():
    """The K-mismatch made VISIBLE: the blade is radial in FOLDED
    space, so each side loses g*(rm/rc)*t*d — rm the PART's mid
    surface (ri+t/2), rc the LAW's neutral radius (ri+K*t)."""
    rel = [{"bend": 0, "gap": T, "depth": RI + T}]
    plain = sheetmetal.sheet_solid([60.0, 40.0], [(90.0, RI, K)],
                                   T, W, n=60)
    cut = sheetmetal.sheet_solid([60.0, 40.0], [(90.0, RI, K)],
                                 T, W, reliefs=rel, n=60)
    rm, rc = RI + T / 2.0, RI + K * T
    law = 2 * T * (rm / rc) * T * (RI + T)
    assert abs((plain.volume - cut.volume) - law) < 1e-2
    assert cut.to_trimesh().is_watertight


def test_relief_refusals_keep_one_loud_voice():
    with pytest.raises(SheetMetalError, match="positive gap"):
        sheetmetal.param_flat([60.0, 40.0], [(90.0, RI, K)], T, W,
                              reliefs=[{"bend": 0, "gap": 0.0,
                                        "depth": 1.0}])
    with pytest.raises(SheetMetalError, match="bend slot"):
        sheetmetal.param_flat([60.0, 40.0], [(90.0, RI, K)], T, W,
                              reliefs=[{"bend": 0, "gap": BA,
                                        "depth": 1.0}])
    with pytest.raises(SheetMetalError, match="meets across"):
        sheetmetal.param_flat([60.0, 40.0], [(90.0, RI, K)], T, W,
                              reliefs=[{"bend": 0, "gap": T,
                                        "depth": W / 2.0}])


# ---- G6: the seam — ONE number, kerf 0, the rect is sacred --------------

def test_closed_cycle_unwraps_by_one_seam_number():
    x = 0.0
    x += 20.0
    starts = [x]
    for leg in (30.0, 20.0, 30.0):
        x += BA
        x += leg
        starts.append(x)
    x += BA                                    # the fourth band closes
    Lc = x
    assert Lc == ((20.0 + BA) + 30.0 + BA) + 20.0 + BA + 30.0 + BA
    cyc = sheetmetal.param_flat([20.0, 30.0, 20.0, 30.0],
                                [(90.0, RI, K)] * 4, T, W, seam=10.0)
    assert cyc["flat_length"] == Lc
    assert cyc["outline"] == [(0.0, 0.0), (Lc, 0.0), (Lc, 40.0),
                              (0.0, 40.0), (0.0, 0.0)]   # kerf 0: THE rect
    assert [bl["x"] for bl in cyc["bend_lines"]] == sorted(
        (s + BA / 2.0 - 10.0) % Lc for s in starts)
    assert all(0.0 <= bl["x"] < Lc for bl in cyc["bend_lines"])


def test_seam_refusals_are_named():
    cyc = dict(legs=[20.0, 30.0, 20.0, 30.0],
               bends=[(90.0, RI, K)] * 4)
    with pytest.raises(SheetMetalError, match="FLAT LEG"):
        sheetmetal.param_flat(cyc["legs"], cyc["bends"], T, W,
                              seam=20.5)       # 20.5 sits IN band 0
    with pytest.raises(SheetMetalError, match="CLOSED SECTION"):
        sheetmetal.param_flat(cyc["legs"], cyc["bends"], T, W)
    with pytest.raises(SheetMetalError, match="folded ring"):
        sheetmetal.sheet_solid(cyc["legs"], cyc["bends"], T, W,
                               seam=10.0)     # named seam still folds


# ---- G7: the K sidecar stays folklore, stays loud ------------------------

def test_ksheet_bins_are_half_open_and_the_json_is_provenanced():
    assert ksolver.k_for("mild-steel", 3.0, T) == 0.33     # r/t = 1.5
    assert ksolver.k_for("mild-steel", 6.0, T) == 0.40     # r/t = 3.0
    assert ksolver.k_for("mild-steel", 12.0, T) == 0.44    # r/t = 6.0
    assert ksolver.k_for("unobtainium", 3.0, T) is None
    doc = json.loads((Path(sheetmetal.__file__).resolve().parent
                      / "data" / "ksheet.json")
                     .read_text(encoding="utf-8"))
    assert doc["provenance"] and doc["verified"] and doc["license"]
    grep = subprocess.run(
        ["grep", "-l", "12195",
         str(Path(sheetmetal.__file__).resolve().parent
             / "data" / "ksheet.json"),
         str(Path(sheetmetal.__file__).resolve().parent
             / "ksolver.py")], capture_output=True, text=True)
    assert grep.stdout == ""               # the phantom stays uncited


def test_unknown_material_keeps_k_default_out_loud():
    d = Document("sm3")
    b, _ = d.add_sheet(material="unobtainium")
    d.add_flange(b["name"], 40.0, 90.0)
    d.recompute()
    assert d.sheet_warnings and "unobtainium" in d.sheet_warnings[0]
    assert d.sheet_states()[b["name"]]["bends"][0][2] == 0.44
    pinned = d.sheet_states()[b["name"]]["flat"]["flat_length"]
    assert pinned == (60.0 + BA) + 40.0          # K_DEFAULT's own BA


# ---- G1 + document law ---------------------------------------------------

def test_base_sheet_is_an_exact_prism_and_the_chain_folds():
    d = Document("sm3")
    b, base = d.add_sheet(t=T, width=W, leg=60.0)
    d.recompute()
    sol = d.body_solids()[b["name"]]
    assert sol.volume == 60.0 * T * W            # rect extrude is exact
    assert d.active_body == b["name"]
    d.add_flange(b["name"], 40.0, 90.0, ri=RI)
    d.recompute()
    st = d.sheet_states()[b["name"]]
    assert st["bends"] == [(90.0, RI, 0.33)]     # table: r/t 1.5
    k_used = 0.33
    ba_t = math.radians(90.0) * (RI + k_used * T)
    assert st["flat"]["flat_length"] == (60.0 + ba_t) + 40.0


def test_lever_edit_follows_the_formula_not_a_rerun():
    d = Document("sm3")
    b, _ = d.add_sheet(t=T, width=W, leg=60.0)
    d.add_flange(b["name"], 40.0, 90.0, ri=RI)
    d.recompute()
    d.params["L1"] = "65"
    d.features[-1].bindings["leg"] = "L1"
    d.recompute()
    st = d.sheet_states()[b["name"]]
    ba_t = math.radians(90.0) * (RI + 0.33 * T)
    assert st["flat"]["flat_length"] == (60.0 + ba_t) + 65.0
    assert st["flat"]["bend_lines"][0]["x"] == 60.0 + ba_t / 2.0


def test_sheet_owns_its_numbers_and_reliefs_need_both_ends():
    d = Document("sm3")
    b, base = d.add_sheet(t=T, width=W, leg=60.0)
    d.add_flange(b["name"], 40.0, 90.0)
    d.features[-1].t = 3.0                       # sneak a second t in
    with pytest.raises(SheetMetalError, match="ONE t"):
        d.recompute()
    d.features[-1].t = T
    d.features[-1].relief_gap = 1.0              # gap without depth
    with pytest.raises(SheetMetalError, match="BOTH gap and depth"):
        d.recompute()
    with pytest.raises(SheetMetalError, match="no bend"):
        d2 = Document("x")
        d2.add_sheet()
        d2.features[-1].relief_gap = 1.0
        d2.features[-1].relief_depth = 2.0
        d2.recompute()


def test_file_round_trip_bytes_and_built_flat():
    d = Document("sm3")
    b, _ = d.add_sheet(t=T, width=W, leg=60.0, material="stainless")
    d.add_flange(b["name"], 40.0, 90.0, ri=RI, relief_gap=T,
                 relief_depth=RI + T)
    d.recompute()
    d.features[-1].k_factor = 0.5                # pin an override
    d.recompute()
    raw = json.dumps(d.to_dict(), sort_keys=True)
    back = Document.from_dict(json.loads(raw))
    assert json.dumps(back.to_dict(), sort_keys=True) == raw
    back.recompute()
    st = back.sheet_states()[b["name"]]
    assert st["bends"][0][2] == 0.5              # pinned, table not read
    assert st["reliefs"] == [dict(bend=0, gap=T, depth=RI + T)]
    ba_t = math.radians(90.0) * (RI + 0.5 * T)
    assert st["flat"]["flat_length"] == (60.0 + ba_t) + 40.0
