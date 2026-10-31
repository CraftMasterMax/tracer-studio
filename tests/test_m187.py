"""M187 rung 1 - THE MEASURED GAP: a point keeps its distance to a LINE.

LAW-59 [documented OFFSET ASSOCIATION]: an offset copy carries an auto
distance dimension bound parent<->child - delete the dimension and the
distance UNLOCKS. Our offset mints parallel geometry but binds
nothing: drag the parent and the child is simply left behind, and no
number anywhere says how far apart they are. The bind needs a part we
don't own yet: a SIGNED point-to-line distance constraint - the gap
keeper. PointOnLine is its zero case; this rung adds the family.

The residual is the signed cross form (same geometry PointOnLine
already speaks) with the value subtracted; the numerical Jacobian the
M87 machinery already runs does the rest. The constraint round-trips
through the payload as tag "ld" and drops exactly one degree of
freedom - the rank analysis finds it for free.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from tracer.core.sketch.constraints import Fixed, LineDistance        # noqa
from tracer.core.sketch.model import (SketchModel, model_from_dict,     # noqa
                                      model_to_dict)


def _gap(value=2.0, p_y=7.0):
    """A pinned horizontal line and one free point asked to keep a
    signed gap. Only the gap row moves the point."""
    m = SketchModel()
    m.name = "G"
    a = m.point(0.0, 0.0)
    b = m.point(10.0, 0.0)
    ln = m.add_line(a, b)
    p = m.point(5.0, p_y)
    m.constrain(Fixed(a, x=0.0, y=0.0))
    m.constrain(Fixed(b, x=10.0, y=0.0))
    m.constrain(LineDistance(p, ln, value))
    return m, p, ln, a, b


def test_the_gap_pulls_the_point_to_its_signed_distance():
    m, p, ln, a, b = _gap(value=2.0, p_y=7.0)
    r = m.solve()
    assert r.converged and p.y == pytest.approx(2.0, abs=1e-6), \
        "the point lands at the demanded gap from the LINE"
    assert p.x == pytest.approx(5.0, abs=1e-6), \
        "and the gap rules only across the line - it never drags" \
        " along it"


def test_the_gap_survives_a_moved_parent():
    m, p, ln, a, b = _gap(value=2.0, p_y=7.0)
    m.solve()
    for c in m.sketch.constraints:            # the parent is DRAGGED:
        if isinstance(c, Fixed) and c.p is a:   #  its pins re-target to
            c.x, c.y = 0.0, 1.0                 #  y = 1 (an edit like
        if isinstance(c, Fixed) and c.p is b:   #  any dim edit)
            c.x, c.y = 10.0, 1.0
    r = m.solve()
    assert r.converged, "the gap row keeps the system honest"
    assert a.y == pytest.approx(1.0, abs=1e-6) \
        and b.y == pytest.approx(1.0, abs=1e-6)
    assert p.y == pytest.approx(3.0, abs=1e-6), \
        "the child RODE the parent: the gap is kept, not remembered"


def test_a_negative_value_means_the_other_side():
    m, p, ln, a, b = _gap(value=-3.0, p_y=7.0)
    r = m.solve()
    assert r.converged and p.y == pytest.approx(-3.0, abs=1e-6), \
        "signed is SIGNED: -3 lands below the line"


def test_the_gap_round_trips_through_the_payload():
    m, p, ln, a, b = _gap(value=2.0, p_y=7.0)
    m.solve()
    before = (p.x, p.y)
    d = model_to_dict(m)
    ld = [c for c in d["constraints"] if c["t"] == "ld"]
    assert len(ld) == 1 and ld[0]["v"] == 2.0, \
        "the demanded GAP rides the book, not the incident"
    back = model_from_dict(d)
    r = back.solve()
    assert r.converged
    bp = back.sketch.points[2]
    assert (bp.x, bp.y) == pytest.approx(before, abs=1e-6), \
        "and the saved sketch stands where the living one stood"


def test_the_gap_buys_back_exactly_one_dof():
    m = SketchModel()
    m.name = "G"
    a = m.point(0.0, 0.0)
    b = m.point(10.0, 10.0)
    p = m.point(5.0, 7.0)
    ln = m.add_line(a, b)
    m.constrain(Fixed(a, x=0.0, y=0.0))
    m.constrain(Fixed(b, x=10.0, y=10.0))
    r0 = m.solve()
    m.constrain(LineDistance(p, ln, 2.0))
    r1 = m.solve()
    assert r0.dof - r1.dof == 1, \
        "one gap row, one degree returned - the rank says so itself"


# ---- R2: THE OFFSET WELDS ITSELF TO ITS PARENT [LAW-59] ---------------------
# The mitre copy is no longer dumb paste: every child edge keeps its
# parent PARALLEL and holds the signed gap AS MINTED. Editing a parent
# dimension makes the child RIDE; deleting the gap rows UNLOCKS the
# distance (parallel stays - the two halves of the association are
# separate promises, exactly like the documented glyph/dimension pair).

from tracer.core.sketch.constraints import (Distance, Horizontal,        # noqa
                                            Parallel, Vertical)


def _bound(d=5.0):
    """A fully pinned 40x20 rectangle, offset by d, solved."""
    m = SketchModel()
    m.name = "B"
    p0 = m.point(0.0, 0.0)
    p1 = m.point(40.0, 0.0)
    p2 = m.point(40.0, 20.0)
    p3 = m.point(0.0, 20.0)
    ls = [m.add_line(p0, p1), m.add_line(p1, p2),
          m.add_line(p2, p3), m.add_line(p3, p0)]
    m.constrain(Horizontal(ls[0]), Vertical(ls[1]),
                Horizontal(ls[2]), Vertical(ls[3]))
    m.constrain(Fixed(p0, x=0.0, y=0.0))
    w = Distance(p0, p1, 40.0)
    h = Distance(p0, p3, 20.0)
    m.constrain(w, h)
    r0 = m.solve()
    assert r0.converged and r0.dof == 0
    made = m.add_offset(d)
    return m, made, w


def _cons(m, kind):
    return [c for c in m.sketch.constraints if isinstance(c, kind)]


def _signed_gap(p, ln):
    dx, dy = ln.b.x - ln.a.x, ln.b.y - ln.a.y
    L = math.hypot(dx, dy)
    return (dx * (p.y - ln.a.y) - dy * (p.x - ln.a.x)) / L


def test_the_mitre_copy_welds_every_edge():
    m, made, w = _bound()
    assert len(made) == 4
    par = [c for c in _cons(m, Parallel)]
    ld = _cons(m, LineDistance)
    assert len(par) == 4 and len(ld) == 4, \
        "one parallel promise and one gap promise per child edge"
    for c in ld:
        assert abs(abs(c.value) - 5.0) < 1e-6, \
            "the stamped gap is the distance AS MINTED"
    r = m.solve()
    assert r.dof == 0, "the copy adds zero freedom - it is BOUND"


def test_a_fresh_bind_stands_where_it_was_born():
    m, made, w = _bound()
    before = [(c.a.x, c.a.y, c.b.x, c.b.y) for c in made]
    r = m.solve()
    assert r.converged
    for c, (ax, ay, bx, by) in zip(made, before):
        assert (c.a.x, c.a.y, c.b.x, c.b.y) == pytest.approx(
            (ax, ay, bx, by), abs=1e-6), \
            "residuals are zero at birth - the bind changes NOTHING"


def test_the_child_rides_a_moved_parent_dimension():
    m, made, w = _bound()
    m.solve()
    right_before = max(c.a.x for c in made)
    w.value = 60.0                        # the width dimension EDITED
    r = m.solve()
    assert r.converged and r.dof == 0
    for c in _cons(m, LineDistance):      # every gap KEPT
        assert abs(_signed_gap(c.p, c.line) - c.value) < 1e-4
    assert max(c.a.x for c in made) == pytest.approx(
        right_before + 20.0, abs=1e-4), \
        "the copy FOLLOWED its parent - association, not coincidence"


def test_deleting_the_gap_rows_unlocks_the_distance():
    m, made, w = _bound()
    m.solve()
    kept = [c for c in m.sketch.constraints if not isinstance(c,
                                                              LineDistance)]
    m.sketch.constraints[:] = kept        # the dimension is DELETED
    w.value = 60.0
    r = m.solve()
    assert r.converged
    gaps = [abs(_signed_gap(c.a, made[0])) for c in made]
    assert any(abs(g - 5.0) > 1e-2 for g in gaps), \
        "without the gap rows the distance is FREE - unlocked"


def test_the_bind_round_trips_through_the_payload():
    m, made, w = _bound()
    m.solve()
    d = model_to_dict(m)
    assert len([c for c in d["constraints"] if c["t"] == "ld"]) == 4
    assert len([c for c in d["constraints"] if c["t"] == "//"]) == 4
    back = model_from_dict(d)
    r = back.solve()
    assert r.converged and r.dof == 0, \
        "the association rides the book and re-opens fully bound"


# ---- R3: THE GAP GETS A FACE -------------------------------------------------
# LAW-59's second half needs a clickable distance: "delete the
   # dimension UNLOCKS the distance". A weld that lives only in the
   # book has no dimension to delete - the gap now wears a CHIP like
   # every other dimension (one mouth, paint == hit) with a witness
   # tick to the parent's foot, opens the editor on double-click, and
   # unlocks through the ordinary delete door.

from PySide6.QtCore import Qt                                        # noqa
from PySide6.QtGui import QImage                                     # noqa
from PySide6.QtTest import QTest                                     # noqa
from PySide6.QtWidgets import QApplication                           # noqa
from tracer.ui.sketcheditor import SketchCanvas                      # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _canvas(m):
    c = SketchCanvas()
    c.set_model(m)
    c.resize(600, 400)
    c._snap_grid = False
    c._scale = 5.0
    return c


def _painted(c):
    img = QImage(c.width(), c.height(), QImage.Format.Format_RGBA8888)
    img.fill(0)
    c.render(img)                          # paint populates _dim_hits
    return img


def test_the_gap_speaks_its_chip(qapp):
    m, made, w = _bound()
    c = _canvas(m)
    ld = _cons(m, LineDistance)[0]
    assert c._dim_text(ld) == "5.00", \
        "the chip says the MAGNITUDE - the sign is which side, not" \
        " the dimension"
    ld.driven = True
    assert c._dim_text(ld) == "(5.00)", \
        "and M178's parenthesised READER law rides the new family"
    c.deleteLater()


def test_the_gap_has_a_post_and_degenerate_lines_have_none(qapp):
    m, made, w = _bound()
    c = _canvas(m)
    ld = _cons(m, LineDistance)[0]
    pos = c._dim_anchor_screen(ld)
    assert pos is not None and 0 <= pos.x() <= 600 and \
        0 <= pos.y() <= 400
    z = m.point(0.0, 0.0)
    zl = m.add_line(z, m.point(0.0, 0.0))          # zero-length parent
    assert c._dim_anchor_screen(LineDistance(z, zl, 1.0)) is None, \
        "a degenerate line offers no post - the chip skips it (paint" \
        " == hit == None)"
    c.deleteLater()


def test_every_weld_chips_and_answers_the_hit(qapp):
    m, made, w = _bound()
    c = _canvas(m)
    _painted(c)
    gap_hits = [hc for hc in c._dim_hits
                if isinstance(hc[1], LineDistance)]
    assert len(gap_hits) == 4, \
        "four welds, four CHIPS - the association is now VISIBLE"
    for rect, cc in gap_hits:
        assert rect.isValid() and rect.right() <= 600 and \
            rect.bottom() <= 400
    c.deleteLater()


def test_double_click_opens_the_gaps_editor(qapp):
    m, made, w = _bound()
    c = _canvas(m)
    _painted(c)
    rect, ld = next(hc for hc in c._dim_hits
                    if isinstance(hc[1], LineDistance))
    QTest.mouseDClick(c, Qt.LeftButton, Qt.NoModifier,
                      rect.center().toPoint())   # chip rects are QRectF
    assert c._dim_edit is not None and c._dim_edit.constraint is ld, \
        "the M165 door opens on the gap chip like on any dimension"
    c._close_dim_editor()
    c.deleteLater()


def test_deleting_the_chip_unlocks_only_its_distance(qapp):
    m, made, w = _bound()
    c = _canvas(m)
    _painted(c)
    rect, ld0 = next(hc for hc in c._dim_hits
                     if isinstance(hc[1], LineDistance))
    c.act_remove_constraint(ld0)            # THE DIMENSION IS DELETED
    assert len(_cons(m, LineDistance)) == 3
    assert m.remove_constraint is not None
    w.value = 60.0                          # the parent RIDES...
    r = m.solve()
    assert r.converged
    kept = _cons(m, LineDistance)
    for kc in kept:                         # ...the other welds HOLD
        assert abs(_signed_gap(kc.p, kc.line) - kc.value) < 1e-3
    err0 = abs(_signed_gap(ld0.p, ld0.line) - 5.0)
    assert err0 > 0.5, \
        "but the UNCHIPPED edge fell behind - delete the dimension," \
        " the distance UNLOCKS (LAW-59, out loud)"
    c.deleteLater()


# ---- R4: THE GLYPH THAT REMEMBERS WHAT THE CHIP RELEASED --------------------
# LAW-59's last clause: "delete the dimension UNLOCKS the distance
# (right-click glyph -> Add Offset Dimension restores)". After the
# chip dies the weld still lives in the book - and now it wears a
# GLYPH (the parallel mark on the child edge) that speaks ONLY while
# the pair has no distance row: chip and glyph are one voice per
# pair, never two. The glyph's menu RESTORES - stamping the CURRENT
# gap (re-weld where the copy STANDS, not where it was born) - or
# dissociates outright (Remove Association kills the Parallel too).

from tracer.core.sketch.constraints import Parallel as _Par           # noqa


def _dangling(c, ld0):
    """Paint and hand back the dangling glyph's Parallel row for the
    pair that lost its dimension (None if the law broke)."""
    _painted(c)
    for rect, cc in c._constraint_hits:
        if isinstance(cc, _Par) and cc.l2 is ld0.line \
                and cc.l1 is ld0.p_line:
            return cc
    return None


def test_the_dangling_weld_wears_a_glyph_and_the_chipped_one_does_not(qapp):
    m, made, w = _bound()
    c = _canvas(m)
    _painted(c)
    pars = [cc for _, cc in c._constraint_hits if isinstance(cc, _Par)]
    assert pars == [], "a pair WITH its chip grows no second voice"
    ld0 = _cons(m, LineDistance)[0]
    # remember the child line before the row's witness point (ld0.p)
    ld0.p_line = next(ln for ln in (made) if ld0.p in (ln.a, ln.b))
    c.act_remove_constraint(ld0)
    g = _dangling(c, ld0)
    assert g is not None, \
        "delete the dimension and the WELD surfaces as a glyph"
    c.deleteLater()


def test_the_glyph_menu_offers_the_restore_and_the_cut(qapp):
    m, made, w = _bound()
    c = _canvas(m)
    ld0 = _cons(m, LineDistance)[0]
    ld0.p_line = next(ln for ln in made if ld0.p in (ln.a, ln.b))
    c.act_remove_constraint(ld0)
    par = _dangling(c, ld0)
    c._hover_c = par                          # right-click ON the glyph
    texts = [x.text() for x in c._build_menu().actions()]
    assert "Add Offset Dimension" in texts, \
        "the law's own door: right-click glyph -> Add Offset Dimension"
    assert "Remove Association" in texts, \
        "and delete-the-glyph dissociates - both halves of LAW-59"
    c._hover_c = None
    c.deleteLater()


def test_the_glyph_restores_at_the_gap_it_stands_in(qapp):
    m, made, w = _bound()
    c = _canvas(m)
    ld0 = _cons(m, LineDistance)[0]
    ld0.p_line = next(ln for ln in made if ld0.p in (ln.a, ln.b))
    c.act_remove_constraint(ld0)
    par = _dangling(c, ld0)
    w.value = 60.0
    m.solve()                                 # the copy falls behind
    now = _signed_gap(ld0.p, ld0.line)
    c._hover_c = par
    acts = {x.text(): x for x in c._build_menu().actions()}
    acts["Add Offset Dimension"].trigger()    # the restore, via the menu
    fresh = [cc for cc in _cons(m, LineDistance) if cc.p is ld0.p]
    assert len(fresh) == 1 and fresh[0].value == pytest.approx(now), \
        "RESTORE stamps the CURRENT gap - re-weld where it STANDS"
    assert fresh[0] is not ld0
    w.value = 80.0
    r = m.solve()
    assert r.converged and \
        abs(_signed_gap(fresh[0].p, fresh[0].line) - now) < 1e-3, \
        "and the restored promise RULES again: the copy rides"
    c.deleteLater()


def test_removing_the_association_dissolves_every_promise(qapp):
    m, made, w = _bound()
    c = _canvas(m)
    ld0 = _cons(m, LineDistance)[0]
    ld0.p_line = next(ln for ln in made if ld0.p in (ln.a, ln.b))
    c.act_remove_constraint(ld0)              # the dimension is gone
    par = _dangling(c, ld0)
    c._hover_c = par
    acts = {x.text(): x for x in c._build_menu().actions()}
    acts["Remove Association"].trigger()      # the glyph dies too
    assert not any(cc is par for cc in m.sketch.constraints), \
        "delete the offset glyph -> DISSOCIATES (LAW-59 first clause)"
    assert len(_cons(m, _Par)) == 3 and len(_cons(m, LineDistance)) == 3
    w.value = 60.0
    m.solve()
    assert abs(_signed_gap(ld0.p, ld0.line) - 5.0) > 0.5, \
        "no promise remains - nothing pulls that edge any more"
    c.deleteLater()
