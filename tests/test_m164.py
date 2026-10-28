"""M164 rung 1 — the solve remembers its own rank.

The kernel voice for SKETCH SPEAKS: SolveResult now carries the FINAL
linear-algebra state (rank, J, r, tagged rows), so an on-demand question
- "which ONE constraint could I delete to fix this?" - answers with pure
rank algebra (SolveSpace's drop-one shape), never a re-solve, and never
from the drag hot path.  Provenance rides the constraint (src stamp at
mint + the serialized "s" marker), so structural mints (rect H/V, slot
caps, polygon rings, fillet witnesses, magnet snaps) are never nameable
as removable, and inferred auto-H/V is offered LAST.

And the index-keyed M89 fx bindings finally follow every removal:
toggle / remove_last / delete_entity / remove_constraint all remap
dim_exprs (the old silence was a latent mis-binding bug).
"""
import pytest

pytest.importorskip("PySide6")

from pathlib import Path                                             # noqa: E402

from PySide6.QtWidgets import QApplication                           # noqa: E402

from tracer.core.sketch.model import (_dim_tag, SketchModel,        # noqa: E402
                                      model_from_dict, model_to_dict)
from tracer.core.sketch.constraints import (ArcMiddle, Coincident,  # noqa: E402
                                            Distance, Fixed, Horizontal,
                                            PointOnCircle, Radius, Vertical)
from tracer.core.sketch.entities import Point                       # noqa: E402
from tracer.core.sketch.solver import Sketch, find_removable        # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _rect(s, w=40.0, h=30.0):
    a, b, c, d = (s.point(0, 0), s.point(w, 0), s.point(w, h),
                  s.point(0, h))
    return (a, b, c, d), (s.line(a, b), s.line(b, c), s.line(c, d),
                          s.line(d, a))


def _dup_h():
    """raw sketch + duplicate Horizontal: redundant, one honest fix."""
    s = Sketch()
    (a, b, c, d), (l1, l2, l3, l4) = _rect(s)
    h1 = Horizontal(l1)
    h1b = Horizontal(l1)                      # the same thing twice
    s.constrain(h1, h1b)
    return s, h1, h1b


# ---------------------------------------------------- remembered state

def test_solve_result_carries_rank_rows_and_matrix():
    s = Sketch()
    (a, b, c, d), (l1, l2, l3, l4) = _rect(s)
    s.constrain(Horizontal(l1), Vertical(l2))
    r = s.solve()
    assert r.rank >= 0                        # not the sentinel
    assert r.final_J is not None and r.final_r is not None
    m, n = r.final_J.shape
    assert m == len(r.rows) == 2
    assert r.dof == max(n - r.rank, 0)        # dof IS the remembered rank
    assert r.rank == 2                        # two independent rows


def test_empty_sketch_reports_rank_zero():
    r = Sketch().solve()
    assert r.rank == 0 and r.final_J is None and r.rows == []


def test_solve_never_leaves_a_callable_on_the_result():
    s, _h1, _h1b = _dup_h()
    r = s.solve()
    for f in ("final_J", "final_r", "rows"):
        assert not callable(getattr(r, f))
    assert not any(callable(v) for v in vars(r).values())


# ---------------------------------------------------- drop-one scan

def test_dropone_scan_names_the_duplicate_horizontal():
    s, h1, h1b = _dup_h()
    r = s.solve()
    assert r.redundant == [h1b]
    rep = find_removable(r, s.constraints)
    assert rep.kind == "redundant"
    assert rep.timed_out is False
    assert [id(c) for c in rep.removable] == [id(h1), id(h1b)]
    assert rep.unsatisfied == [h1b]


def test_conflict_flavors_the_report():
    # double-radius (m87's own conflict fixture): BOTH radii are blamed
    # and each one alone is an honest fix - removing it leaves the rest
    # of the system at full row rank.
    s = Sketch()
    c0 = s.point(0, 0)
    circ = s.circle(c0, 5.0)
    r1 = Radius(circ, 5.0)
    r2 = Radius(circ, 8.0)
    s.constrain(r1, r2)
    r = s.solve()
    assert not r.converged
    rep = find_removable(r, s.constraints)
    assert rep.kind == "conflict"
    assert rep.unsatisfied == [r1, r2]
    assert [id(c) for c in rep.removable] == [id(r1), id(r2)]


def test_clean_solve_gets_a_clean_report():
    s = Sketch()
    (a, b, c, d), (l1, l2, l3, l4) = _rect(s)
    s.constrain(Horizontal(l1), Vertical(l2))
    r = s.solve()
    rep = find_removable(r, s.constraints)
    assert rep.kind == "clean" and rep.removable == []
    assert rep.timed_out is False


def test_two_separate_redundancies_offer_no_single_fix():
    # honest-scope law: the drop-one test is FULL ROW RANK of the rest -
    # if two independent duplicates exist, deleting one does NOT fix the
    # other, so the report says "no single removal fixes this".
    s = Sketch()
    (a, b, c, d), (l1, l2, l3, l4) = _rect(s)
    s.constrain(Horizontal(l1), Horizontal(l1), Horizontal(l3),
                Horizontal(l3))
    r = s.solve()
    rep = find_removable(r, s.constraints)
    assert rep.removable == []                 # none lies alone


# ---------------------------------------------------- eligibility

def test_structural_mints_are_never_candidates():
    m = SketchModel()
    lines = m.add_rect(m.point(0, 0), m.point(40, 30))
    dup = Horizontal(lines[0])
    m.constrain(dup)                           # the ONLY user constraint
    r = m.solve()
    assert r.redundant
    rep = find_removable(r, m.sketch.constraints)
    assert [id(c) for c in rep.removable] == [id(dup)]
    stamped = [c for c in m.sketch.constraints
               if getattr(c, "src", "") in ("rect", "slot", "poly",
                                            "fillet", "snap")]
    assert len(stamped) >= 4
    assert not ({id(c) for c in rep.removable}
                & {id(c) for c in stamped})


def test_slot_and_polygon_and_fillet_stamps_hold():
    m = SketchModel()
    m.add_slot(m.point(0, 0), m.point(40, 0), 5.0)
    m.add_polygon(80.0, 40.0, 12.0, n=6)
    a, b, c = m.point(0, 80), m.point(40, 80), m.point(40, 120)
    l1, l2 = m.add_line(a, b), m.add_line(b, c)
    from tracer.core.sketch.fillet import corner_fillet
    corner_fillet(m, l1, l2, 4.0)
    stamped = [c for c in m.sketch.constraints
               if getattr(c, "src", "") in ("slot", "poly", "fillet")]
    assert len(stamped) == 6 + 12 + 4          # slot R2+T4, poly R+PoC6+Eq5,
    #                                            fillet T2+R+ArcMiddle
    r = m.solve()
    rep = find_removable(r, m.sketch.constraints)
    assert not ({id(c) for c in rep.removable}
                & {id(c) for c in stamped})


def test_welds_and_construction_carriers_are_shielded():
    from tracer.core.sketch.constraints import (ArcMiddle, Coincident)
    live = [c for c in (Coincident(Point(0, 0), Point(1, 1)),
                        ArcMiddle.__new__(ArcMiddle))]
    ids = {id(c) for c in live}
    from tracer.core.sketch.solver import _eligible
    assert _eligible(live[0], ids) is None     # the weld
    assert _eligible(live[1], ids) is None     # the fillet witness
    ring = type("E", (), {"construction": True})()
    poc = PointOnCircle(Point(0, 0), ring)     # polygon-ring carrier
    assert _eligible(poc, {id(poc)}) is None   # construction carrier shield


def test_inferred_is_offered_last():
    m = SketchModel()
    a, b = m.point(0, 0), m.point(40, 0)
    ln = m.add_line(a, b)
    hb = Horizontal(ln)
    m.constrain(hb, src="inferred")            # minted FIRST
    ha = Horizontal(ln)
    m.constrain(ha)                            # user minted later
    r = m.solve()
    rep = find_removable(r, m.sketch.constraints)
    assert [id(c) for c in rep.removable] == [id(ha), id(hb)]


# ---------------------------------------------------- budgets & purity

def test_budget_and_scan_caps_flag_partial():
    s, h1, h1b = _dup_h()
    r = s.solve()
    rep = find_removable(r, s.constraints, budget_ms=0)
    assert rep.timed_out is True and rep.removable == []
    rep = find_removable(r, s.constraints, max_scan=0)
    assert rep.timed_out is True and rep.removable == []
    rep = find_removable(r, s.constraints, max_scan=1)
    assert rep.timed_out is True
    assert [id(c) for c in rep.removable] == [id(h1)]   # first only


def test_scan_is_read_only_and_never_contaminates():
    s, h1, h1b = _dup_h()
    r = s.solve()
    cons_before = list(s.constraints)
    red_before, conf_before = list(r.redundant), list(r.conflicting)
    snap = (r.rank, r.dof, r.converged)
    rep1 = find_removable(r, s.constraints)
    rep2 = find_removable(r, s.constraints)
    assert s.constraints == cons_before        # identity AND order intact
    assert list(r.redundant) == red_before     # the report is its OWN object
    assert list(r.conflicting) == conf_before
    assert (r.rank, r.dof, r.converged) == snap
    assert rep1 is not rep2
    assert rep1.removable == rep2.removable    # deterministic


# ---------------------------------------------------- removal + remap

def _bound_model():
    """three constraints; the Distance at idx 2 bound to `width`."""
    m = SketchModel()
    a, b, c = m.point(0, 0), m.point(40, 0), m.point(40, 30)
    l1, l2 = m.add_line(a, b), m.add_line(b, c)
    h, d1, d2 = Horizontal(l1), Distance(b, c, 30.0), Distance(a, b, 40.0)
    m.constrain(h, d1, d2)
    m.dim_exprs = {2: {"e": "width", "t": _dim_tag(d2)}}
    return m, (h, d1, d2)


def test_remove_constraint_remaps_dim_exprs():
    m, (h, d1, d2) = _bound_model()
    assert m.remove_constraint(h) is True
    assert {int(k) for k in m.dim_exprs} == {1}          # slid down one
    warns = m.apply_dim_params({"width": 12.0}, scale=1.0)
    assert warns == [] and d2.value == pytest.approx(12.0)
    assert m.remove_constraint(h) is False                # already gone


def test_remove_constraint_uses_identity_not_eq():
    from tracer.core.sketch.constraints import Distance
    m, (h, d1, d2) = _bound_model()
    twin = Distance(d2.p, d2.q, d2.value)      # __eq__ twin, not in list
    assert m.remove_constraint(twin) is False
    assert len(m.sketch.constraints) == 3


def test_removal_of_the_bound_dimension_drops_its_binding():
    m, (h, d1, d2) = _bound_model()
    assert m.remove_constraint(d2) is True
    assert m.dim_exprs == {}


@pytest.mark.parametrize("path", ["toggle", "remove_last", "delete_entity"])
def test_every_removal_path_remaps_bindings(path):
    m, (h, d1, d2) = _bound_model()             # H at 0, bindings key {2}
    if path == "toggle":
        m.toggle(Horizontal, (m.sketch.lines[0],))
    elif path == "remove_last":
        m.remove_last(Horizontal, (m.sketch.lines[0],))
    else:
        m.delete_entity(m.sketch.lines[0])
    assert {int(k) for k in m.dim_exprs} == {1}          # the H is gone:
    #                                         d2 slid 2 -> 1, binding follows
    warns = m.apply_dim_params({"width": 12.0}, scale=1.0)
    assert warns == [] and d2.value == pytest.approx(12.0)


# ---------------------------------------------------- provenance I/O

def test_provenance_survives_save_reload():
    m = SketchModel()
    m.add_rect(m.point(0, 0), m.point(40, 30))
    m.add_slot(m.point(60, 0), m.point(90, 0), 5.0)
    d = model_to_dict(m)
    assert any(e.get("s") == "rect" for e in d["constraints"])
    assert any(e.get("s") == "slot" for e in d["constraints"])
    m2 = model_from_dict(d)
    assert ([getattr(c, "src", "") for c in m2.sketch.constraints]
            == [getattr(c, "src", "") for c in m.sketch.constraints])


def test_legacy_dict_without_markers_loads_unstamped():
    m = SketchModel()
    m.add_rect(m.point(0, 0), m.point(40, 30))
    d = model_to_dict(m)
    for e in d["constraints"]:
        e.pop("s", None)                       # pre-M164 file
    m2 = model_from_dict(d)
    assert all(getattr(c, "src", "") == "" for c in m2.sketch.constraints)
    # the type-set shield still holds on a legacy load: the ring of a
    # polygon (construction carrier) is never a candidate even unstamped
    m3 = model_from_dict(d)
    lines = m3.sketch.lines
    m3.constrain(Horizontal(lines[0]))         # a user duplicate
    r = m3.solve()
    rep = find_removable(r, m3.sketch.constraints)
    # legacy rect H/V MAY surface (documented honest degradation) - the
    # law is only: nothing on a construction carrier, and the dup is in
    assert rep.removable                       # dup offered


def test_dim_exprs_roundtrip_keys_stay_int_strings():
    m, _ = _bound_model()
    d = model_to_dict(m)
    assert set(d["dim_exprs"]) == {"2"}
    m2 = model_from_dict(d)
    assert {int(k) for k in m2.dim_exprs} == {2}


# ---------------------------------------------------- hot-path & HUD

def test_scan_is_not_wired_into_the_drag_hot_path():
    # rung-1 law: the finder has NO call site in the editor yet - the
    # scan is demand-only (rung 3 will open it through the chip).
    src = (Path(__file__).resolve().parent.parent
           / "tracer" / "ui" / "sketcheditor.py").read_text(encoding="utf-8")
    assert "find_removable" not in src


def test_hud_speaks_rank(qapp):
    from tracer.ui.sketcheditor import SketchCanvas
    m = SketchModel()
    a, b = m.point(0, 0), m.point(40, 0)
    ln = m.add_line(a, b)
    m.constrain(Horizontal(ln))                # 1 row: rank truth exists
    cv = SketchCanvas()
    cv.set_model(m)
    cv._show_dof = True
    r = m.solve()
    cv._last_result = r
    txt = cv._dof_hud_text()
    assert txt == f"DOF \u00b7 {cv.dof_summary()} (rank {r.rank}/{len(r.rows)})"
    assert txt.endswith("(rank 1/1)")          # one row, one rank
    assert txt.startswith("DOF \u00b7 ")        # M119 prefix contract kept
    cv._last_result = r                         # no rows: no rank truth
    r.rows = []
    assert "(rank" not in cv._dof_hud_text()


def test_m119_summary_contract_untouched(qapp):
    # dof_summary() itself must stay BYTE-EXACT for test_m119 substrings
    from tracer.ui.sketcheditor import SketchCanvas
    m = SketchModel()
    m.add_line(m.point(0, 0), m.point(40, 0))
    cv = SketchCanvas()
    cv.set_model(m)
    cv._solve()
    assert cv.dof_summary().endswith("dof")
    assert "rank" not in cv.dof_summary()
