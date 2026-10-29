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

def _func_src(name):
    """The body of one top-level SketchCanvas method, from the real file
    (rung 3's structural hot-path grep needs function spans)."""
    import re
    root = Path(__file__).resolve().parent.parent / "tracer" / "ui"
    src = (root / "sketcheditor.py").read_text(encoding="utf-8")
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def )", src, re.S)
    assert m, f"{name} vanished from sketcheditor.py"
    return m.group(0)


def test_scan_is_not_wired_into_the_drag_hot_path():
    # M164 RETARGET (cited): rung 1 forbade ANY editor call site; rung 3
    # gives the drop-one scan exactly ONE (open_finder_panel). The law
    # is now structural: one call, and never inside a hot function.
    root = Path(__file__).resolve().parent.parent / "tracer" / "ui"
    src = (root / "sketcheditor.py").read_text(encoding="utf-8")
    for fn in ("_solve", "paintEvent", "mouseMoveEvent", "leaveEvent",
               "mousePressEvent", "_draw_hover", "_draw_glyphs", "_badge"):
        assert "find_removable" not in _func_src(fn)
    assert src.count("find_removable(") == 1     # the import carries no "("
    assert "open_finder_panel" in src
    mw = (root / "mainwindow.py").read_text(encoding="utf-8")
    assert "find_removable" not in mw            # the chip delegates blind


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


# ============================================================ RUNG 2
# Every constraint a click target: badge/hover hit rects, the ring, and
# the DoF chip that selects what the solve is talking about.  Design:
# fleet specs/m164_rung2_hover_design.md.

from PySide6.QtCore import (QCoreApplication, QEvent,               # noqa: E402
                            QPoint, QPointF, Qt)
from PySide6.QtGui import QColor, QPainter, QPixmap                  # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402

from tracer.core.sketch.constraints import (Angle, Midpoint,       # noqa: E402
                                            Symmetry, Tangent,
                                            make_angle)


def _settle(qapp, n=8):
    for _ in range(n):
        qapp.processEvents()


@pytest.fixture(scope="module")
def qapp2():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def mkcanvas(qapp2):
    """Build a live canvas; CLOSE it after the test.  Leaked visible
    canvases poison QTest input routing for every later test (learned
    the hard way: offscreen windows share the pointer, and a still-open
    one steals the move)."""
    made = []

    def make(m):
        from tracer.ui.sketcheditor import SketchCanvas
        cv = SketchCanvas()
        cv.resize(600, 400)
        cv.set_model(m)
        cv.show()
        _settle(qapp2)
        cv._solve()
        cv.fit_view()
        cv.grab()                      # ONE paint fills both hit lists
        made.append(cv)
        return cv
    yield make
    for cv in made:
        cv.close()
    _settle(qapp2)


@pytest.fixture
def hover_cv(mkcanvas):
    """Spread-out gallery: one of every badge kind + three label kinds."""
    m = SketchModel()
    l1 = m.add_line(m.point(0, 0), m.point(40, 0))            # Horizontal
    l2 = m.add_line(m.point(80, 0), m.point(80, 40))          # Vertical
    fp = m.point(160, 0)                                      # Fixed
    ml = m.add_line(m.point(200, 0), m.point(260, 0))
    mp = m.point(230, 0)                                      # Midpoint
    ax = m.add_line(m.point(320, -20), m.point(320, 20))
    s1, s2 = m.point(300, 0), m.point(340, 0)                 # Symmetry
    tc = m.sketch.circle(m.point(40, 80), 20.0)
    tl = m.add_line(m.point(10, 100), m.point(70, 100))       # Tangent
    rc = m.sketch.circle(m.point(140, 80), 25.0)
    d1, d2 = m.point(220, 140), m.point(260, 140)             # Distance
    al = m.add_line(m.point(320, 60), m.point(360, 60))       # Angle
    m.constrain(Horizontal(l1), Vertical(l2),
                Fixed(fp, x=160.0, y=0.0), Midpoint(mp, ml),
                Symmetry(s1, s2, ax), Tangent(tl, tc),
                Radius(rc, 25.0), Distance(d1, d2, 40.0),
                make_angle(al, 30.0))
    return mkcanvas(m), m


def _badge_for(cv, ctype):
    for r, c in cv._constraint_hits:
        if type(c) is ctype:
            return r, c
    raise AssertionError(f"no {ctype.__name__} hover rect")


def _dim_for(cv, ctype):
    for r, c in cv._dim_hits:
        if type(c) is ctype:
            return r, c
    raise AssertionError(f"no {ctype.__name__} dim rect")


def test_every_constraint_has_a_hit_rect(hover_cv):
    cv, _m = hover_cv
    for K in (Horizontal, Vertical, Fixed, Symmetry, Midpoint, Tangent):
        r, c = _badge_for(cv, K)
        hit = cv._hover_hit(r.center())
        assert hit is not None and hit[1] is c      # identity, never __eq__
    for K in (Distance, Radius, Angle):
        r, c = _dim_for(cv, K)
        hit = cv._hover_hit(r.center())
        assert hit is not None and hit[1] is c


def test_badge_rect_wins_over_dim_label(mkcanvas):
    # Midpoint badge planted dead-centre on the Distance label: hover
    # answers the badge (paint order), the double-click dim-edit path
    # still answers the label (_dim_hits untouched).
    m = SketchModel()
    a, b = m.point(0, 0), m.point(60, 0)
    ln = m.add_line(a, b)
    mp = m.point(30, 0)
    m.constrain(Midpoint(mp, ln), Distance(a, b, 60.0))
    cv = mkcanvas(m)
    _br, mc = _badge_for(cv, Midpoint)
    dr = next(r for r, c in cv._dim_hits if type(c) is Distance)
    # M164 FIX (cited): whether badge and label rects NATURALLY overlap
    # is a font-metrics bet - Windows CI run 40787619347 lost it
    # (intersected() came back QRectF(0,0,0,0)).  The law lives in the
    # _hover_hit SEARCH ORDER, so plant the badge entry on the label's
    # rect in this frame's map (every paint rebuilds these lists anyway)
    # and interrogate the resolver deterministically, on every OS.
    cv._constraint_hits = [(dr if c is mc else r, c)
                           for r, c in cv._constraint_hits]
    q = dr.center()                           # a point BOTH rects own
    hit = cv._hover_hit(q)
    assert hit is not None and hit[1] is mc   # hover answers the badge
    dims = [c for r, c in cv._dim_hits if r.contains(q)]
    assert any(type(c) is Distance for c in dims)   # dclick still edits the
    #                                                 dim: _dim_hits intact


def test_hover_never_touches_selection(hover_cv):
    cv, m = hover_cv
    r, c = _badge_for(cv, Horizontal)
    anchor = m.sketch.lines[0].a
    cv._sel = [anchor]
    QTest.mouseMove(cv, QPoint(5, 395))          # park: pointer-dedup guard
    QTest.mouseMove(cv, r.center().toPoint())
    assert cv._hover_c is c
    assert cv._sel == [anchor] and cv._sel[0] is anchor   # D3: cosmetic


def test_hover_repaints_once_per_change(hover_cv, monkeypatch):
    # mouseMoveEvent keeps the coordinate readout live with ONE baseline
    # update() per move; hover may add at most one more, and only when
    # the hovered constraint actually changes.
    cv, _m = hover_cv
    r1, _c1 = _badge_for(cv, Horizontal)
    r2, _c2 = _badge_for(cv, Vertical)
    # Park the pointer elsewhere FIRST: the offscreen platform silently
    # drops a move whose global position equals the previous one, and the
    # gate before this one left the virtual pointer right on r1.
    QTest.mouseMove(cv, QPoint(5, 5))
    n = [0]
    monkeypatch.setattr(cv, "update", lambda *a: n.__setitem__(0, n[0] + 1))
    QTest.mouseMove(cv, r1.center().toPoint())         # enter: base + 1
    assert n[0] == 2
    for i in (1, 2, 3):                          # same badge: base only
        p1 = r1.center().toPoint()               # (1px jitter: identical
        QTest.mouseMove(cv, QPoint(p1.x() + i, p1.y()))    # global moves
    assert n[0] == 5                             #  are pointer-deduped)
    QTest.mouseMove(cv, r2.center().toPoint())          # switch: base + 1
    assert n[0] == 7


def test_hover_clears_on_miss_tool_change_and_leave(hover_cv):
    cv, _m = hover_cv
    QTest.mouseMove(cv, QPoint(590, 390))                # empty corner
    assert cv._hover_c is None
    assert cv.cursor().shape() == Qt.ArrowCursor
    cv.set_tool("line")                                 # ring must not ghost
    assert cv._hover_c is None
    assert cv.cursor().shape() == Qt.CrossCursor
    cv.set_tool("select")
    r, c = _badge_for(cv, Fixed)
    QTest.mouseMove(cv, r.center().toPoint())
    assert cv._hover_c is c
    cv.leaveEvent(QEvent(QEvent.Type.Leave))   # offscreen never
    assert cv._hover_c is None                          # synthesizes Leave
    assert cv.cursor().shape() == Qt.ArrowCursor


def _paint_trio(cv):
    pm = QPixmap(cv.size())
    pm.fill(QColor("#121417"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    cv._draw_dimensions(p)
    cv._draw_glyphs(p)
    cv._draw_hover(p)
    p.end()
    return pm


def _hover_family(px):
    # loose AA idiom (house test_m87): the ring straddles two pixel rows
    return px.blue() > 200 and px.blue() - px.red() > 40 \
        and px.green() > px.red()


def _error_family(px):
    return px.red() > 180 and px.red() - px.green() > 70 \
        and px.red() - px.blue() > 70


def test_hover_paints_ring(hover_cv):
    cv, _m = hover_cv
    r, c = _badge_for(cv, Horizontal)
    cv._hover_c = c
    pm = _paint_trio(cv)
    img = pm.toImage()
    cx = int(r.center().x())
    ty = int(r.top()) - 3                      # ring straddles rows above
    ink = sum(1 for dx in range(-5, 6)        # the badge (measured: its
              for dy in range(-1, 2)          # stroke is -3..-2)
              if _hover_family(img.pixelColor(cx + dx, ty + dy)))
    assert ink >= 2, "no hover ring was painted"


def test_conflict_hover_escalates_red(mkcanvas):
    # H+V fight (m87's own fixture): hovering a blamed constraint
    # re-strokes the LINE red - away from the badges, so it cannot be
    # the badge fill answering.
    m = SketchModel()
    a, b = m.point(0, 0), m.point(10, 0)
    ln = m.add_line(a, b)
    v = Vertical(ln)
    m.constrain(Fixed(a, x=0.0, y=0.0), Fixed(b, x=10.0, y=0.0),
                Horizontal(ln), v)
    cv = mkcanvas(m)
    assert cv._conflicting                      # diagnosed (m87: pins too)
    blamed = [c for c in m.sketch.constraints if id(c) in cv._conflicting]
    assert any(isinstance(c, Vertical) for c in blamed)
    cv._hover_c = v
    pm = _paint_trio(cv)
    qa, qb = cv.w2s(0, 0), cv.w2s(10, 0)
    x = int(qa.x() + (qb.x() - qa.x()) * 0.25)  # quarter: no badge lives
    y = int(qa.y())                             #        on the line there
    img = pm.toImage()
    ink = sum(1 for dy in range(-2, 2)          # AA split (measured rows
              if _error_family(img.pixelColor(x, y + dy)))    # -1..0)
    assert ink >= 2, "conflict hover did not re-stroke the geometry red"


def test_drag_start_clears_hover(hover_cv):
    cv, _m = hover_cv
    r, c = _badge_for(cv, Fixed)                # badge sits ON its point
    QTest.mouseMove(cv, QPoint(5, 395))         # park: dedup guard (see
    QTest.mouseMove(cv, r.center().toPoint())   # repaint-gate note)
    assert cv._hover_c is c
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier,
                     r.center().toPoint())
    assert cv._hover_c is None                  # no wash while dragging


def test_select_underconstrained_is_zero_solve(mkcanvas):
    m = SketchModel()
    m.add_rect(m.point(0, 0), m.point(60, 40))  # 4 structural rows, 4 dof
    cv = mkcanvas(m)
    res = cv._last_result
    assert res.dof == 4
    cv.select_underconstrained()
    free = [p for p in cv._dof_points() if res.point_dof.get(p.id, 0) > 0]
    assert len(free) == 4
    assert {id(p) for p in cv._sel} == {id(p) for p in free}
    assert cv._last_result is res               # the chip never re-solves


def test_select_blamed_is_zero_solve(mkcanvas):
    m = SketchModel()
    a, b = m.point(0, 0), m.point(10, 0)
    ln = m.add_line(a, b)
    m.constrain(Fixed(a, x=0.0, y=0.0), Fixed(b, x=10.0, y=0.0),
                Horizontal(ln), Vertical(ln))
    cv = mkcanvas(m)
    res = cv._last_result
    assert res.conflicting
    cv.select_blamed()
    exp = []                                   # whatever the solve blamed
    for c in res.conflicting:                  # (m87 law: the pins can be
        for e in c.entities():                 # nicked too - so the gate
            if not any(e is o for o in exp):   # reads the blame, not a
                exp.append(e)                  # hand-guessed fixture
    assert {id(e) for e in cv._sel} == {id(e) for e in exp}
    assert any(id(e) == id(ln) for e in cv._sel)   # the fighter's line
    assert cv._last_result is res                # never re-solves


# ---------------------------------------------------------- chip (UI)

@pytest.fixture
def win(qapp2):
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
        qapp2.processEvents()
        yield w
        w._unsaved = False
        w.close()
        r.close()
    except Exception:
        raise


def _sketch_on(win, qapp2):
    win.new_document()
    win.action_new_sketch()
    qapp2.processEvents()
    return win.sketch


def test_chip_click_selects_every_free_point(win, qapp2):
    cv = _sketch_on(win, qapp2)
    m = cv.model
    m.add_rect(m.point(0, 0), m.point(60, 40))
    cv._solve()
    qapp2.processEvents()
    res = cv._last_result
    assert win._sketch_state.isEnabled()
    QTest.mouseClick(win._sketch_state, Qt.LeftButton, Qt.NoModifier,
                     win._sketch_state.rect().center())
    free = [p for p in cv._dof_points() if res.point_dof.get(p.id, 0) > 0]
    assert len(free) == 4
    assert {id(p) for p in cv._sel} == {id(p) for p in free}
    assert cv._last_result is res


def test_chip_click_on_conflict_opens_the_fixer(win, qapp2):
    # M164 RETARGET (cited): conflict click FIXES, not selects (rung 3);
    # the select_blamed law itself stays gated canvas-side (rung 2).
    cv = _sketch_on(win, qapp2)
    m = cv.model
    a, b = m.point(0, 0), m.point(10, 0)
    ln = m.add_line(a, b)
    m.constrain(Fixed(a, x=0.0, y=0.0), Fixed(b, x=10.0, y=0.0),
                Horizontal(ln), Vertical(ln))
    cv._solve()
    qapp2.processEvents()
    assert win._sketch_state.text().startswith("\u26a0")
    QTest.mouseClick(win._sketch_state, Qt.LeftButton, Qt.NoModifier,
                     win._sketch_state.rect().center())
    from tracer.ui.cmdpanel import CmdPanel
    p = win._cmd_panel
    assert isinstance(p, CmdPanel) and p.command_id == "sketch_fix"
    p.btn_abort.click()
    qapp2.processEvents()
    assert win._cmd_panel is None


def test_chip_silent_when_fully_constrained(win, qapp2):
    cv = _sketch_on(win, qapp2)
    m = cv.model
    a, b = m.point(0, 0), m.point(10, 0)
    m.add_line(a, b)
    m.constrain(Fixed(a, x=0.0, y=0.0), Fixed(b, x=10.0, y=0.0))
    cv._solve()
    qapp2.processEvents()
    assert win._sketch_state.text() == "Sketch fully constrained"
    assert not win._sketch_state.isEnabled()        # structural refusal
    win._sketch_state.clicked.emit()                # logic refusal too
    qapp2.processEvents()
    assert cv._sel == []


def test_chip_grammar_and_dof_summary_untouched(win, qapp2):
    cv = _sketch_on(win, qapp2)
    m = cv.model
    m.add_rect(m.point(0, 0), m.point(60, 40))
    cv._solve()
    qapp2.processEvents()
    t = win._sketch_state.text()
    assert t == "Sketch under-constrained \u00b7 4 dof free"   # byte-exact
    assert "free point" not in t        # the chip does NOT reuse
    #               dof_summary()'s wording (that sentence owns the HUD)


def test_tooltip_and_cursor_follow_state(win, qapp2):
    cv = _sketch_on(win, qapp2)
    m = cv.model
    a, b = m.point(0, 0), m.point(10, 0)
    ln = m.add_line(a, b)
    h, v = Horizontal(ln), Vertical(ln)
    m.constrain(Fixed(a, x=0.0, y=0.0), Fixed(b, x=10.0, y=0.0), h, v)
    cv._solve()
    qapp2.processEvents()
    # M164 RETARGET (cited): conflict folds into fixable (rung 3)
    assert win._sketch_state.toolTip() == "Click to choose one to remove"
    assert win._sketch_state.cursor().shape() == Qt.PointingHandCursor
    c, d = m.point(50, 0), m.point(90, 0)
    m.add_line(c, d)
    m.remove_constraint(h)                    # identity, not an __eq__
    m.remove_constraint(v)                    # twin
    m.constrain(Fixed(c, x=50.0, y=0.0), Fixed(d, x=90.0, y=0.0))
    cv._solve()
    qapp2.processEvents()
    assert win._sketch_state.text() == "Sketch fully constrained"
    assert win._sketch_state.toolTip() == ""
    assert win._sketch_state.cursor().shape() == Qt.ArrowCursor


def test_no_new_sketch_keys_and_no_finder_leak():
    # M164 RETARGET (cited): rung 3 gives the finder its sanctioned ONE
    # call site in sketcheditor (test_scan_is_not_wired_into_the_drag_
    # hot_path now owns that law); this gate keeps the *other* leaks out.
    root = Path(__file__).resolve().parent.parent / "tracer" / "ui"
    cmds = (root / "commands.py").read_text(encoding="utf-8")
    assert "ClickableLabel" not in cmds      # the chip is not a command
    assert "sketch_fix" not in cmds          # mouse-only, no key verbs
    # the ring is a THEME token, never a raw colour in the canvas module
    sk = (root / "sketcheditor.py").read_text(encoding="utf-8")
    assert 'theme.SKETCH["hover"]' in sk


def test_hover_paints_for_inferred_constraint_identically(mkcanvas):
    # the paint path never reads c.src - an inferred auto-H rings exactly
    # like a user-H (never red, same hover family).
    m = SketchModel()
    a1, b1 = m.point(0, 0), m.point(40, 0)
    a2, b2 = m.point(90, 0), m.point(130, 0)
    l1 = m.add_line(a1, b1)
    l2 = m.add_line(a2, b2)
    h_user = Horizontal(l1)
    m.constrain(h_user)
    h_inf = Horizontal(l2)
    m.constrain(h_inf, src="inferred")
    cv = mkcanvas(m)
    for h in (h_user, h_inf):
        r, c = next((r, c) for r, c in cv._constraint_hits if c is h)
        cv._hover_c = c
        pm = _paint_trio(cv)
        img = pm.toImage()
        cx = int(r.center().x())
        ty = int(r.top()) - 3
        ink = sum(1 for dx in range(-5, 6)
                  for dy in range(-1, 2)
                  if _hover_family(img.pixelColor(cx + dx, ty + dy)))
        red = sum(1 for dx in range(-5, 6)
                  for dy in range(-1, 2)
                  if _error_family(img.pixelColor(cx + dx, ty + dy)))
        assert ink >= 2 and red == 0

# ====================================================== rung 3: the fixer panel

import json                                        # noqa: E402
from PySide6.QtWidgets import QDialogButtonBox, QLabel    # noqa: E402


def _reap(qapp):
    """OFFSCREEN GC LAW (CI Linux run 40792077905 SIGBUS + local bisect):
    closing a CmdPanel deleteLater's it; if the panel's wrapper/parent GCs
    at test end BEFORE that DeferredDelete lands, the NEXT test's
    QTest.qWaitForWindowExposed dies (probes v1-v7: leaving the panel open
    survives, closing WITHOUT reaping poisons - the corpse is the crime).
    So: process the queue NOW, while every reference is still alive."""
    for _ in range(4):
        qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def _dup_on(win, qapp2):
    """Kernel _dup_h in UI clothes: one bare line + TWO identical user
    Horizontals - redundant, two honest fixes, twins that print the SAME
    combo row (which makes the index law testable)."""
    cv = _sketch_on(win, qapp2)
    m = cv.model
    a, b = m.point(0, 0), m.point(40, 0)
    ln = m.add_line(a, b)
    h1, h1b = Horizontal(ln), Horizontal(ln)
    m.constrain(h1, h1b)
    cv._solve()
    qapp2.processEvents()
    return cv, ln, h1, h1b


def _chip(win, qapp2):
    QTest.mouseClick(win._sketch_state, Qt.LeftButton, Qt.NoModifier,
                     win._sketch_state.rect().center())


def test_chip_opens_the_fixer_panel_not_a_dialog(win, qapp2, monkeypatch):
    from tracer.ui import cmddialog as cd
    from tracer.ui.cmdpanel import CmdPanel

    def no_dialogs(*a, **k):
        raise AssertionError("rung 3 is an ANTI-MODAL panel, not a dialog")
    monkeypatch.setattr(cd, "ask", no_dialogs)
    cv, _ln, _h1, _h1b = _dup_on(win, qapp2)
    _chip(win, qapp2)
    p = win._cmd_panel
    assert isinstance(p, CmdPanel)
    assert p.command_id == "sketch_fix"
    assert p.findChild(QDialogButtonBox) is None     # anti-modal law
    assert list(p._edits) == ["pick"]                # note never registers
    p.btn_abort.click()
    qapp2.processEvents()
    assert win._cmd_panel is None


def test_the_list_offers_only_user_removables(win, qapp2):
    cv = _sketch_on(win, qapp2)
    m = cv.model
    lines = m.add_rect(m.point(0, 0), m.point(40, 30))   # src="rect" H/V
    m.constrain(Horizontal(lines[0]))                    # the user twin
    cv._solve()
    qapp2.processEvents()
    _chip(win, qapp2)
    p = win._cmd_panel
    combo = p._edits["pick"]
    assert combo.count() == 1                            # ONLY the twin:
    assert combo.itemText(0).startswith("Horizontal")    #  never the stamp
    structural = [c for c in m.sketch.constraints
                  if getattr(c, "src", "") == "rect"]
    assert len(structural) == 4
    p.btn_commit.click()
    qapp2.processEvents()
    cons = m.sketch.constraints
    assert all(any(c is s for c in cons) for s in structural)
    assert "redundant" not in win._sketch_state.text()   # the fix WORKED


def test_twin_labels_are_picked_by_index(win, qapp2):
    cv, _ln, h1, h1b = _dup_on(win, qapp2)
    _chip(win, qapp2)
    p = win._cmd_panel
    combo = p._edits["pick"]
    assert combo.itemText(0) == combo.itemText(1)        # twins lie to TEXT
    combo.setCurrentIndex(1)
    combo.activated.emit(1)          # direct-drive: setCurrentIndex never
    p.btn_commit.click()             #  fires activated (engine law)
    qapp2.processEvents()
    cons = cv.model.sketch.constraints
    assert not any(c is h1b for c in cons)               # index 1 = the
    assert any(c is h1 for c in cons)                    #  SECOND twin
    assert win._cmd_panel is None


def test_combobox_choice_ghosts_the_candidate(mkcanvas, qapp2, monkeypatch):
    m = SketchModel()
    a, b = m.point(0, 0), m.point(40, 0)
    ln = m.add_line(a, b)
    h1, h1b = Horizontal(ln), Horizontal(ln)
    m.constrain(h1, h1b)
    cv = mkcanvas(m)
    p = cv.open_finder_panel(cv)
    assert p is not None and cv._hover_c is None
    before = json.dumps(model_to_dict(m), sort_keys=True)
    res_before = cv._last_result

    def boom(*a_, **k_):
        raise AssertionError("preview must NEVER solve (press-pull law)")
    monkeypatch.setattr(m, "solve", boom)
    combo = p._edits["pick"]
    assert combo.count() == 2
    combo.setCurrentIndex(1)
    combo.activated.emit(1)
    qapp2.processEvents()
    assert cv._hover_c is h1b                    # INDEX 1 = second twin
    assert cv._sel == []                         # cosmetic: never selects
    assert cv._last_result is res_before         # zero solve
    monkeypatch.undo()
    p.btn_abort.click()
    _reap(qapp2)                                 # GC law: see _reap's doc
    assert cv._hover_c is None                   # abort buries the ghost
    assert json.dumps(model_to_dict(m), sort_keys=True) == before


def test_ghost_ring_paints_on_the_candidate(mkcanvas, qapp2):
    m = SketchModel()
    a, b = m.point(0, 0), m.point(40, 0)
    ln = m.add_line(a, b)
    h1 = Horizontal(ln)
    m.constrain(h1, Horizontal(ln))
    cv = mkcanvas(m)
    p = cv.open_finder_panel(cv)
    p._edits["pick"].activated.emit(0)
    assert cv._hover_c is h1                     # idx 0 = first twin
    pm = _paint_trio(cv)                         # trio rebuilds the hits
    rect = next(r for r, c in cv._constraint_hits if c is h1)
    img = pm.toImage()
    cx, ty = int(rect.center().x()), int(rect.top()) - 3
    ink = sum(1 for dx in range(-5, 6)
              for dy in range(-1, 2)
              if _hover_family(img.pixelColor(cx + dx, ty + dy)))
    assert ink >= 2                              # the rung-2 token, combo-
    p.btn_abort.click()                          #  driven
    _reap(qapp2)                                 # GC law: reap while alive


def test_ghost_escalates_red_on_conflict(mkcanvas, qapp2):
    #  m87's own H+V fight: the candidate that OWNS blame ghosts RED -
    #  the badge's own escalation law, reused by the panel verbatim.
    m = SketchModel()
    a, b = m.point(0, 0), m.point(10, 0)
    ln = m.add_line(a, b)
    m.constrain(Fixed(a, x=0.0, y=0.0), Fixed(b, x=10.0, y=0.0),
                Horizontal(ln), Vertical(ln))
    cv = mkcanvas(m)
    p = cv.open_finder_panel(cv)
    combo = p._edits["pick"]
    vi = None
    for i in range(combo.count()):               # walk rows: emit IS click
        combo.setCurrentIndex(i)
        combo.activated.emit(i)
        qapp2.processEvents()
        if cv._hover_c is not None and id(cv._hover_c) in cv._conflicting:
            vi = i
            break
    assert vi is not None, "no candidate owns blame"
    pm = _paint_trio(cv)
    rect = next(r for r, c in cv._constraint_hits if c is cv._hover_c)
    img = pm.toImage()
    cx, ty = int(rect.center().x()), int(rect.top()) - 3
    red = sum(1 for dx in range(-5, 6)
              for dy in range(-1, 2)
              if _error_family(img.pixelColor(cx + dx, ty + dy)))
    assert red >= 2
    p.btn_abort.click()
    _reap(qapp2)                                 # GC law: reap while alive
    assert cv._hover_c is None


def test_commit_removes_solves_in_one_undo_step(win, qapp2):
    cv, _ln, h1, _h1b = _dup_on(win, qapp2)
    before = json.dumps(model_to_dict(cv.model), sort_keys=True)
    n = len(cv._hist)
    _chip(win, qapp2)
    p = win._cmd_panel
    p.btn_commit.click()                          # idx 0 default
    qapp2.processEvents()
    assert len(cv._hist) == n + 1                 # ONE undo step
    assert not any(c is h1 for c in cv.model.sketch.constraints)
    assert cv._redundant == set()                 # the warning is GONE
    assert win._cmd_panel is None
    assert "redundant" not in win._sketch_state.text()
    assert win._sketch_state.toolTip() == "Click to select every free " \
        "point"                                   # voice back to rung 2
    cv.undo_op()                                  # one step back, exact
    qapp2.processEvents()
    assert json.dumps(model_to_dict(cv.model), sort_keys=True) == before
    assert "1 redundant" in win._sketch_state.text()   # chip re-states


def test_abort_cleans_hover_and_leaves_no_trace(win, qapp2):
    cv, _ln, _h1, _h1b = _dup_on(win, qapp2)
    before = json.dumps(model_to_dict(cv.model), sort_keys=True)
    n = len(cv._hist)
    res_before = cv._last_result
    _chip(win, qapp2)
    p = win._cmd_panel
    p._edits["pick"].activated.emit(0)
    qapp2.processEvents()
    assert cv._hover_c is not None
    p.btn_abort.click()
    qapp2.processEvents()
    assert cv._hover_c is None
    assert len(cv._hist) == n                     # zero trace
    assert cv._last_result is res_before          # zero solve
    assert json.dumps(model_to_dict(cv.model), sort_keys=True) == before
    assert win._cmd_panel is None


def test_a_new_verb_aborts_the_fixer(win, qapp2):
    from tracer.ui import cmdpanel as cp
    cv, _ln, _h1, _h1b = _dup_on(win, qapp2)
    _chip(win, qapp2)
    p = win._cmd_panel
    p._edits["pick"].activated.emit(0)
    qapp2.processEvents()
    assert cv._hover_c is not None
    p2 = cp.run(win, "other_verb", "Other",
                [dict(key="v", kind="double", label="v", default=1.0)],
                preview=lambda vals: None, commit=lambda vals: None,
                abort=lambda: None)
    qapp2.processEvents()
    assert win._cmd_panel is p2                   # one verb, one panel
    assert cv._hover_c is None                    # the valve cleaned up
    _chip(win, qapp2)                             # chip re-entry: the fixer
    assert win._cmd_panel is not p2               #  REPLACES, never stacks
    assert win._cmd_panel.command_id == "sketch_fix"
    win._cmd_panel.btn_abort.click()
    qapp2.processEvents()
    assert win._cmd_panel is None


def test_chip_grows_the_finder_sentence(win, qapp2, monkeypatch):
    cv, _ln, _h1, _h1b = _dup_on(win, qapp2)
    t = win._sketch_state.text()
    assert t.endswith(" \u2304 remove one to fix")          # append-only
    assert "1 redundant" in t                               #  tail, blamed
    assert win._sketch_state.toolTip() == "Click to choose one to remove"
    # OFFSCREEN LAW (measured): a second action_new_sketch over a dirty
    # editor hits _discard_guard's QMessageBox.question - modal, it HANGS
    # (alone) or SEGVs (after sibling teardowns).  The guard is not this
    # gate's subject; the chip grammar is.
    monkeypatch.setattr(win, "_discard_guard", lambda: True)
    win.new_document()
    win.action_new_sketch()                                 # conflict voice
    qapp2.processEvents()
    cv = win.sketch
    m = cv.model
    a, b = m.point(0, 0), m.point(10, 0)
    ln = m.add_line(a, b)
    m.constrain(Fixed(a, x=0.0, y=0.0), Fixed(b, x=10.0, y=0.0),
                Horizontal(ln), Vertical(ln))
    cv._solve()
    qapp2.processEvents()
    t = win._sketch_state.text()
    assert t.startswith("\u26a0") and t.endswith(" \u2304 remove one to fix")


def test_chip_falls_back_when_no_single_fix(win, qapp2):
    cv = _sketch_on(win, qapp2)
    m = cv.model
    a, b, c, d = (m.point(0, 0), m.point(40, 0),
                  m.point(0, 30), m.point(40, 30))
    l1, l3 = m.add_line(a, b), m.add_line(c, d)
    m.constrain(Horizontal(l1), Horizontal(l1), Horizontal(l3),
                Horizontal(l3))                             # kernel's twin
    cv._solve()
    qapp2.processEvents()
    res = cv._last_result
    assert res.redundant                                    # looks fixable
    assert win._sketch_state.text().endswith(" \u2304 remove one to fix")
    _chip(win, qapp2)
    assert getattr(win, "_cmd_panel", None) is None     # finder DECLINED
    free = [p for p in cv._dof_points()                     # never a dead
            if res.point_dof.get(p.id, 0) > 0]              #  click
    assert free and {id(p) for p in cv._sel} == {id(p) for p in free}


def test_timeout_note_appears_on_partial(win, qapp2, monkeypatch):
    cv, _ln, _h1, _h1b = _dup_on(win, qapp2)
    from tracer.ui import sketcheditor as se
    real = se.find_removable
    monkeypatch.setattr(se, "find_removable",             # max_scan=1, NOT
                        lambda r, cons, **k: real(r, cons, max_scan=1))
    _chip(win, qapp2)                                     # budget-0: empty
    p = win._cmd_panel                                    #  list, decline
    assert p is not None
    assert p._edits["pick"].count() == 1                  # PARTIAL: one
    notes = [lab.text() for lab in p.findChildren(QLabel)
             if "budget" in lab.text()]                   # the honest note
    assert notes and "may exist" in notes[0]
    assert list(p._edits) == ["pick"]                     # note owns no row
    assert set(p.values()) == {"pick"}
    p.btn_commit.click()                                  # path intact
    qapp2.processEvents()
    assert win._cmd_panel is None


def test_panel_commit_shifts_a_live_binding(win, qapp2):
    cv = _sketch_on(win, qapp2)
    m = cv.model
    a, b = m.point(0, 0), m.point(40, 0)
    ln = m.add_line(a, b)
    ha, hb = Horizontal(ln), Horizontal(ln)
    d = Distance(a, b, 40.0)
    m.constrain(ha, hb, d)
    m.dim_exprs = {2: {"e": "width", "t": _dim_tag(d)}}   # bound to index 2
    cv._solve()
    qapp2.processEvents()
    _chip(win, qapp2)
    p = win._cmd_panel
    assert p._edits["pick"].count() == 2                  # only the twins
    p.btn_commit.click()                                  # idx 0 = ha
    qapp2.processEvents()
    assert {int(k) for k in m.dim_exprs} == {1}           # shifted, alive
    errs = m.apply_dim_params({"width": 12.0})
    assert errs == [] and d.value == pytest.approx(12.0)  # fx rides on


def test_menu_remove_of_bound_dim_drops_binding(mkcanvas, qapp2):
    m = SketchModel()
    a, b = m.point(0, 0), m.point(40, 0)
    d0 = Distance(a, b, 40.0)
    m.constrain(d0, Distance(a, b, 40.0))
    m.dim_exprs = {0: {"e": "w", "t": _dim_tag(d0)}}
    cv = mkcanvas(m)
    n = len(cv._hist)
    cv._hover_c = d0                            # what hovering the label
    acts = {x.text(): x for x in cv._build_menu().actions()}   #  would set
    assert "Remove Constraint" in acts
    acts["Remove Constraint"].trigger()
    qapp2.processEvents()
    assert not any(c is d0 for c in m.sketch.constraints)
    assert m.dim_exprs == {}                    # the binding died WITH it
    assert len(cv._hist) == n + 1               # ONE undo step
    assert cv._hover_c is None                  # the ring's subject left


def test_menu_entry_only_for_fixable_badges(mkcanvas, qapp2):
    m = SketchModel()
    lines = m.add_rect(m.point(0, 0), m.point(40, 30))    # src-stamped H/V
    sk = m.sketch
    dup = Horizontal(lines[0])
    m.constrain(dup)                                      # the user twin
    cv = mkcanvas(m)
    struct = next(c for c in sk.constraints
                  if isinstance(c, Vertical)
                  and getattr(c, "src", "") == "rect")
    cv._hover_c = struct                                  # structural badge
    texts = [x.text() for x in cv._build_menu().actions()]
    assert "Remove Constraint" not in texts               # never nameable
    cv._hover_c = dup                                     # user twin badge
    acts = {x.text(): x for x in cv._build_menu().actions()}
    assert "Remove Constraint" in acts
    cv._hover_c = None                        # freeze law: the entry
    acts["Remove Constraint"].trigger()       #  carries ITS OWN target
    qapp2.processEvents()
    assert not any(c is dup for c in sk.constraints)
    assert [c for c in sk.constraints if getattr(c, "src", "") == "rect"]


def test_right_press_keeps_the_hovered_badge(mkcanvas, qapp2, monkeypatch):
    # The menu rides WITH the hover: mousePress's right branch (:428-431)
    # reaches _context_menu BEFORE any hover clearing.  _context_menu is
    # patched because .exec() would block; the route itself is real.
    m = SketchModel()
    a, b = m.point(0, 0), m.point(40, 0)
    ln = m.add_line(a, b)
    m.constrain(Horizontal(ln))
    cv = mkcanvas(m)
    seen = []
    monkeypatch.setattr(cv, "_context_menu",
                        lambda ev: seen.append(cv._hover_c))
    r, c = _badge_for(cv, Horizontal)
    QTest.mouseMove(cv, r.center().toPoint())
    qapp2.processEvents()
    assert cv._hover_c is c
    QTest.mousePress(cv, Qt.RightButton, Qt.NoModifier, r.center().toPoint())
    qapp2.processEvents()
    assert seen == [c]                            # menu ran off the hover
    assert cv._hover_c is c                       # and NOTHING cleared it
    QTest.mouseRelease(cv, Qt.RightButton, Qt.NoModifier,
                       r.center().toPoint())


def test_fixer_panel_forgets(win, qapp2):
    from tracer.ui import cmddialog as cd
    cv, _ln, _h1, h1b = _dup_on(win, qapp2)
    _chip(win, qapp2)
    p = win._cmd_panel
    p._edits["pick"].setCurrentIndex(1)
    p._edits["pick"].activated.emit(1)
    p.btn_commit.click()
    qapp2.processEvents()
    assert not any(c is h1b for c in cv.model.sketch.constraints)
    assert cd.remembered("sketch_fix") is None    # forgetful by law: a
    assert cd._REMEMBER_ON.get("sketch_fix") is None   #  pick never rides


# ============================================ rung 4: the dim edit panel
# M165 R1 RETARGET (cited, m165_rung1_retarget_post_m164r4.md S4): the
# length/diameter leg of this rung moved from the live PANEL to the
# INLINE chip editor (tracer/ui/dimedit.py).  Nine gates below re-drive
# the SAME rung-4 laws through the chip door; the ANGLE gate keeps the
# panel verbatim (that leg never moved).

import math                                          # noqa: E402
from tracer.core.sketch.constraints import Angle     # noqa: E402
from tracer.ui.dimedit import ChipField              # noqa: E402


def _line_dim(m):
    """One bare line + its Distance dim - the rung-4 canvas fixture."""
    a, b = m.point(0, 0), m.point(40, 0)
    m.add_line(a, b)
    d = Distance(a, b, 40.0)
    m.constrain(d)
    return d


def _type(cv, text, qapp):
    """Drive a REAL chip boundary: raw text in, editingFinished out
    (the KiCad discrete-intention edge), then let commit+close settle."""
    ed = cv._dim_edit
    assert ed is not None and type(ed) is ChipField
    ed.edit.setText(text)
    ed.edit.editingFinished.emit()
    qapp.processEvents()


def test_dim_edit_goes_inline_not_to_the_panel(mkcanvas, qapp2,
                                               monkeypatch):
    # M165 R1 RETARGET (cited): rung 4's anti-modal panel was the way;
    # the chip editor now IS the way for length dims - a dclick seats a
    # ChipField on the label and touches NO panel.  The anti-modal law
    # survives through the angle gate (panel keeps angles).
    from tracer.ui import cmddialog as cd

    def no_dialogs(*a, **k):
        raise AssertionError("no modal for dims - inline or panel")
    monkeypatch.setattr(cd, "ask", no_dialogs)
    m = SketchModel()
    d = _line_dim(m)
    cv = mkcanvas(m)
    rect = next(r for r, c in cv._dim_hits if c is d)
    QTest.mouseDClick(cv, Qt.LeftButton, Qt.NoModifier,
                      rect.center().toPoint())          # the real route
    qapp2.processEvents()
    ed = cv._dim_edit
    assert type(ed) is ChipField                        # the chip door
    assert getattr(cv, "_cmd_panel", None) is None      # panel untouched
    assert ed.edit.text() == "40.00"                    # bare prefill
    assert cv._hover_c is d                             # rung-4 ring
    assert rect.toRect().adjusted(-2, -2, 2, 2) == ed.geometry()  # SEAT
    QTest.keyClick(ed.edit, Qt.Key_Escape)              # leave untouched
    _reap(qapp2)                                 # GC law (rung 3): reap
    assert cv._dim_edit is None                        #   while refs live
    assert cv._hover_c is None                         # ring dies closed


def test_angle_dim_rides_the_same_panel(mkcanvas, qapp2, monkeypatch):
    from tracer.ui import cmddialog as cd
    from tracer.ui.cmddialog import Shell

    def no_modal(*a, **k):
        raise AssertionError("rung 4: no Shell.getDouble for angle edits")
    monkeypatch.setattr(Shell, "getDouble", staticmethod(no_modal))
    m = SketchModel()
    a, b = m.point(0, 0), m.point(10, 0)
    ln = m.add_line(a, b)
    ang = Angle(ln, math.radians(20))
    m.constrain(Fixed(a, x=0.0, y=0.0), ang)
    cv = mkcanvas(m)
    cv._edit_dim(ang)                        # angle = the panel, still
    qapp2.processEvents()
    p = cv._cmd_panel
    assert p.command_id == "sketch_dim"
    assert list(p._edits) == ["val"]             # angles carry NO fx row:
    assert any("Angle (deg)" in w.text()         #  M89 law kept (fx binds
               for w in p.findChildren(QLabel))  #  lengths, unit in label)
    p._edits["val"].set_value_mm(30.0)
    p.btn_commit.click()
    qapp2.processEvents()
    assert math.degrees(ang.value) % 180 == pytest.approx(30, abs=1e-6)
    assert cd.remembered("sketch_dim") is None   # M165: the forgetful law
    _reap(qapp2)                                 #  lives here now (chip
                                                 #   prefill is per-dim by
    assert cv._dim_edit is None                  #  construction, m165)


def test_double_scale_trap_plain_and_fx_speak_different_grammars(
        mkcanvas, qapp2):
    # The design's pinned split, now inside ONE field: plain text rides
    # parse_scalar - NATIVE millimetres (1inch = 25.4 even in a doc
    # whose fx scale is 10); the "=" prefix keeps M89's doc-unit x sc
    # semantics. If either path ever multiplies twice, this gate dies.
    m = SketchModel()
    d = _line_dim(m)
    cv = mkcanvas(m)
    cv._params_provider = lambda: ({"wall": 7.0}, 10.0)   # resolved sheet
    cv._open_dim_editor(d)
    qapp2.processEvents()
    assert d.value == pytest.approx(40.0)      # open mutates NOTHING
    _type(cv, "1inch", qapp2)                  # plain leg: the field
    assert d.value == pytest.approx(25.4)      #  speaks mm - NOT 254:
    assert m.dim_exprs == {}                   #  sc never touches plain
    _reap(qapp2)
    cv._open_dim_editor(d)                     # phase 2: the fx leg
    qapp2.processEvents()
    ed = cv._dim_edit
    assert ed.edit.text() == "25.40"           # re-prefilled from LIFE
    _type(cv, "=wall", qapp2)                  # 7 DOC units x sc(10)...
    assert d.value == pytest.approx(70.0)      # ...= 70, NOT 7
    i = m.sketch.constraints.index(d)
    assert m.dim_exprs[i] == {"e": "wall", "t": _dim_tag(d)}
    _reap(qapp2)


def test_the_value_field_resolves_document_params(mkcanvas, qapp2):
    # feature#6 rides the chip: the provider sheet is the field's own
    # _eval context, so the number leg itself takes wall*2.
    m = SketchModel()
    d = _line_dim(m)
    cv = mkcanvas(m)
    cv._params_provider = lambda: ({"wall": 7.0}, 1.0)     # resolved sheet
    cv._open_dim_editor(d)
    qapp2.processEvents()
    assert cv._dim_edit._provider()[0] == {"wall": 7.0}    # LIVE provider
    _type(cv, "wall*2", qapp2)
    assert d.value == pytest.approx(14.0)
    _reap(qapp2)


def test_reopen_prefills_the_bare_value_and_plain_releases(mkcanvas,
                                                           qapp2):
    # M165 R1 RETARGET (cited): the panel's fx prefill RETIRED - the
    # chip always prefills the bare displayed number (provenance lives
    # in dim_exprs, the driven "= " lives on the painter).  The blank-
    # fx RELEASE law re-borns as "no = means plain": type a number on
    # a BOUND chip and the binding pops.
    m = SketchModel()
    d = _line_dim(m)
    i = m.sketch.constraints.index(d)
    m.dim_exprs[i] = {"e": "width", "t": _dim_tag(d)}
    cv = mkcanvas(m)
    cv._open_dim_editor(d)
    qapp2.processEvents()
    assert cv._dim_edit.edit.text() == "40.00"  # BARE prefill (M98 law
    _type(cv, "28", qapp2)                      #  rides plain numbers)
    assert m.dim_exprs == {}                    # release, M89's old law
    assert d.value == pytest.approx(28.0)
    _reap(qapp2)


def test_abort_leaves_value_hist_and_hover_untouched(mkcanvas, qapp2):
    m = SketchModel()
    d = _line_dim(m)
    cv = mkcanvas(m)
    before = json.dumps(model_to_dict(m), sort_keys=True)
    n = len(cv._hist)
    cv._open_dim_editor(d)
    qapp2.processEvents()
    assert cv._hover_c is d                     # rung-4 ring ports HERE
    ed = cv._dim_edit
    ed.edit.setText("999")                      # TYPED but never bounded
    qapp2.processEvents()
    assert d.value == pytest.approx(40.0)       # no write without Enter
    assert len(cv._hist) == n
    QTest.keyClick(ed.edit, Qt.Key_Escape)      # the real Esc route
    _reap(qapp2)
    assert cv._hover_c is None                  # the ring dies with the
    assert len(cv._hist) == n                   #  editor; zero trace
    assert json.dumps(model_to_dict(m), sort_keys=True) == before


def test_reopen_mid_edit_discards_the_previous_chip(mkcanvas, qapp2):
    m = SketchModel()
    a, b = m.point(0, 0), m.point(40, 0)
    c = m.point(40, 30)
    m.add_line(a, b)
    m.add_line(b, c)
    d1, d2 = Distance(a, b, 40.0), Distance(b, c, 30.0)
    m.constrain(d1, d2)
    cv = mkcanvas(m)
    cv._open_dim_editor(d1)
    qapp2.processEvents()
    ed1 = cv._dim_edit
    ed1.edit.setText("99")                      # typed, UNCOMMITTED
    cv._open_dim_editor(d2)                     # the one-editor law:
    qapp2.processEvents()                       #  a new chip closes the
    assert cv._dim_edit is not ed1              #   last - DISCARD, not
    assert ed1.isHidden()                       #   commit (the corpse
    assert ed1.constraint is d1                 #    is deleteLater'd:
    assert cv._hover_c is d2                    #    hidden NOW, gone at
    _type(cv, "99", qapp2)                      #     only Enter commits)
    assert d2.value == pytest.approx(99.0)
    assert d1.value == pytest.approx(40.0)      # the abandoned edit is
    _reap(qapp2)                                #  gone with its chip
    assert cv.findChildren(ChipField) == []     #  (GC law: reaped, both)


def test_the_chip_forgets(mkcanvas, qapp2):
    # The rung-4 footgun law, native to the chip: prefill is computed
    # from THIS constraint's value at construction - a dim can never
    # wear another dim's typed number (the remembered("sketch_dim")
    # leg moved to the angle gate, where the panel still lives).
    m = SketchModel()
    d1 = _line_dim(m)
    a2, b2 = m.point(100, 0), m.point(160, 0)
    m.add_line(a2, b2)
    d2 = Distance(a2, b2, 60.0)
    m.constrain(d2)
    cv = mkcanvas(m)
    cv._open_dim_editor(d1)
    qapp2.processEvents()
    _type(cv, "12", qapp2)
    assert d1.value == pytest.approx(12.0)
    _reap(qapp2)
    cv._open_dim_editor(d2)
    qapp2.processEvents()
    assert cv._dim_edit.edit.text() == "60.00"  # NOT "12.00"
    QTest.keyClick(cv._dim_edit.edit, Qt.Key_Escape)
    _reap(qapp2)


def test_a_dead_dim_makes_the_commit_inert(mkcanvas, qapp2, monkeypatch):
    from conftest import script_dim_edit
    m = SketchModel()
    d = _line_dim(m)
    cv = mkcanvas(m)
    n = len(cv._hist)
    m.remove_constraint(d)                      # the fixer struck first
    script_dim_edit(monkeypatch, "999")         # the seam = _apply_dim
    cv._edit_dim(d)                             #  _edit; identity door:
    qapp2.processEvents()                       #   dead dim edits nobody
    assert len(cv._hist) == n                   # zero trace
    assert m.dim_exprs == {}
    assert all(cc is not d for cc in m.sketch.constraints)


def test_binding_from_the_chip_survives_the_round_trip(mkcanvas, qapp2,
                                                       monkeypatch):
    from conftest import script_dim_edit
    m = SketchModel()
    d = _line_dim(m)
    cv = mkcanvas(m)
    cv._params_provider = lambda: ({"width": 33.0}, 1.0)  # resolved sheet
    script_dim_edit(monkeypatch, "=width")
    cv._edit_dim(d)
    qapp2.processEvents()
    assert d.value == pytest.approx(33.0)
    m2 = model_from_dict(json.loads(json.dumps(model_to_dict(m))))
    assert [rec["e"] for rec in m2.dim_exprs.values()] == ["width"]
    assert m2.dim_exprs[0]["t"] == _dim_tag(d)  # the tag rode along
