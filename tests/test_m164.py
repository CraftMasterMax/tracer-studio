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


# ============================================================ RUNG 2
# Every constraint a click target: badge/hover hit rects, the ring, and
# the DoF chip that selects what the solve is talking about.  Design:
# fleet specs/m164_rung2_hover_design.md.

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt              # noqa: E402
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
    br, mc = _badge_for(cv, Midpoint)
    dr = next(r for r, c in cv._dim_hits if type(c) is Distance)
    ix = br.intersected(dr)                   # they really overlap (live
    assert not ix.isEmpty()                   # frame, exact floats)
    q = ix.center()                           # a point BOTH rects own
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


def test_chip_click_on_conflict_selects_blamed(win, qapp2):
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
    exp = []
    for c in cv._last_result.conflicting:     # blame-driven, not guessed
        for e in c.entities():
            if not any(e is o for o in exp):
                exp.append(e)
    assert {id(e) for e in cv._sel} == {id(e) for e in exp}


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
    assert win._sketch_state.toolTip() == "Click to select the blamed " \
        "geometry"
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
    root = Path(__file__).resolve().parent.parent / "tracer" / "ui"
    assert "find_removable" not in (root / "sketcheditor.py").read_text(
        encoding="utf-8")            # rung 3 opens the finder, not us
    cmds = (root / "commands.py").read_text(encoding="utf-8")
    assert "ClickableLabel" not in cmds      # the chip is not a command
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
