"""M165 rung 1 - the value AT THE CURSOR: the inline ChipField.

Double-clicking a Distance/Radius/Diameter chip seats a real child
ExprField ON the chip rect (paint-derived seat: chip_rect is the same
math the painter ran, so seat == paint by construction), pre-selects the
bare number, and commits ONE boundary on Enter/focus-out: plain text
speaks native millimetres through parse_scalar (expressions, units,
params), the "=" prefix carries M89's binding (doc units x scale), and a
plain number on a bound chip releases it.  Esc rewinds and closes; an
untouched Enter closes without a trace; invalid input paints the danger
TOKEN (never a hex literal) and stays open to retry.  The editor tracks
the chip through pan/zoom/solve via the paint post-hook (move-only-if-
moved), and a discard-close (undo mid-type, model swap, chip death) can
NEVER commit - the signals are disconnected before Qt's focus-out-on-
hide can fire.  Rung 2 brought the angle chips in (bare degrees,
[0,180), no units, no binding) and the KEYBOARD door: F2.

Design law adopted from test_m164: mkcanvas CLOSES its canvases (leaked
visible windows poison QTest routing), _reap processes the DeferredDelete
queue while references are alive (the rung-3 offscreen GC law - chip
corpses are exactly that poison), every dclick is the full-signature
QTest.mouseDClick, and pixel probes read the SAME paint frame that
filled the hit lists.
"""
import json
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt                         # noqa: E402
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPixmap  # noqa: E402
from PySide6.QtTest import QTest                                 # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402

from tracer.core.sketch.constraints import (Angle, Distance,     # noqa: E402
                                            Fixed, Midpoint, Radius)
from tracer.core.sketch.model import SketchModel, model_to_dict  # noqa: E402
from tracer.ui import dimedit, theme                             # noqa: E402
from tracer.ui.dimedit import ChipField, chip_rect               # noqa: E402


# conftest forces QT_QPA_PLATFORM=offscreen at ITS import (line 12),
# which precedes every test module - safe to bind the app right here,
# and helpers need the INSTANCE, not a fixture definition.
qapp2 = QApplication.instance() or QApplication([])


def _settle(qapp, n=8):
    for _ in range(n):
        qapp.processEvents()


def _reap(qapp):
    """The rung-3 offscreen GC law (test_m164): a deleteLater'd widget
    whose wrapper GCs before the DeferredDelete lands poisons the NEXT
    test's window expose.  Chips die on every close - reap while refs
    are alive."""
    from PySide6.QtCore import QCoreApplication, QEvent
    for _ in range(4):
        qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


@pytest.fixture
def mkcanvas():
    """Live canvas, CLOSED after the test (the m164 routing law)."""
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
def dim_cv(mkcanvas):
    """A gallery: Distance line, circle with a Diameter chip, arc with
    an R chip, one 30 deg angle chip on the panel's side."""
    m = SketchModel()
    a, b = m.point(0, 0), m.point(40, 0)
    m.add_line(a, b)
    m.constrain(Distance(a, b, 40.0))              # [0] the Distance chip
    cen = m.point(90, 25)
    circ = m.add_circle(cen, 4.0)
    m.constrain(Radius(circ, 4.0))
    p1, pm, p2 = m.point(0, -40), m.point(10, -30), m.point(20, -40)
    ar = m.sketch.arc(p1, pm, p2)
    m.constrain(Radius(ar, 10.0))                   # [2] the arc R chip
    c1 = m.point(90, -20)
    c2 = m.point(90 + 10 * math.cos(math.radians(30)),
                 -20 + 10 * math.sin(math.radians(30)))
    ln2 = m.add_line(c1, c2)
    m.constrain(Angle(ln2, math.radians(30)))       # [3] the angle chip
    cv = mkcanvas(m)
    return cv, m


def _chip_on(cv, c):
    """Open the editor through the dclick-door side door (the routing
    itself is gate 1's job) and settle."""
    cv._open_dim_editor(c)
    _settle(qapp2)
    return cv._dim_edit


def _type(ed, text, commit=True):
    ed.edit.setText(text)
    if commit:
        ed.edit.editingFinished.emit()


# ------------------------------------------------- the widget door ----

def test_dclick_opens_chipfield_on_distance(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    before = json.dumps(model_to_dict(m), sort_keys=True)
    n = len(cv._hist)
    rect = next(r for r, c in cv._dim_hits if c is dist)
    QTest.mouseDClick(cv, Qt.LeftButton, Qt.NoModifier,
                      rect.center().toPoint(), 10)
    _settle(qapp2)
    ed = cv._dim_edit
    assert type(ed) is ChipField                        # the chip door
    assert ed.constraint is dist
    assert ed.edit.text() == "40.00"                    # bare prefill
    assert ed.edit.placeholderText() == "mm"
    assert ed.geometry() == rect.toRect().adjusted(-2, -2, 2, 2)   # SEAT:
    #                                                 the SAME frame's
    #                                                 paint built both
    assert len(cv._hist) == n                           # opening mutates
    assert json.dumps(model_to_dict(m), sort_keys=True) == before   # nada
    QTest.keyClick(ed.edit, Qt.Key_Escape)
    _reap(qapp2)


def test_type_enter_commits_and_renders(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    ed = _chip_on(cv, dist)
    n = len(cv._hist)
    QTest.keyClicks(ed.edit, "60")                  # selectAll is LIVE:
    assert ed.edit.text() == "60"                   #  typing replaced it
    QTest.keyClick(ed.edit, Qt.Key_Return)
    _settle(qapp2)
    assert dist.value == pytest.approx(60.0)
    assert len(cv._hist) == n + 1                   # ONE undo step
    assert cv._dim_edit is None
    cv.grab()
    fm = QFontMetrics(cv._font)
    r60 = next(r for r, c in cv._dim_hits if c is dist)
    assert r60.width() == pytest.approx(
        chip_rect(fm, QPointF(0, 0), "60.00").width())   # chip re-rendered
    ed = _chip_on(cv, dist)
    _type(ed, "5")                                   # the narrow case:
    _settle(qapp2)                                   #  text truth drove
    assert dist.value == pytest.approx(5.0)          #   a real write
    cv.grab()
    r5 = next(r for r, c in cv._dim_hits if c is dist)
    assert r5.width() == pytest.approx(
        chip_rect(fm, QPointF(0, 0), "5.00").width())
    assert r5.width() < r60.width()                # strictly narrower
    assert cv.undo_op()                            # hist rides: back
    # _restore swaps the whole sketch (m5 law) - interrogate the LIVE
    # object, the gate's pre-undo reference is intentionally stale:
    assert m.sketch.constraints[0].value == pytest.approx(60.0)
    #   to 60, not 5
    assert cv._dim_edit is None                    # undo never revives
    _reap(qapp2)


def test_focus_returns_to_canvas_after_close(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    ed = _chip_on(cv, dist)
    QTest.keyClick(ed.edit, Qt.Key_Escape)
    _settle(qapp2)
    app = QApplication.instance()
    assert app.focusWidget() is cv or cv.hasFocus()  # the Esc ladder
    QTest.keyClick(cv, Qt.Key_L)                     #  resumes HERE, on
    assert cv._tool == "line"                        #  the canvas again
    _reap(qapp2)


def test_esc_cancels_byte_identical(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    before = json.dumps(model_to_dict(m), sort_keys=True)
    n = len(cv._hist)
    ed = _chip_on(cv, dist)
    QTest.keyClicks(ed.edit, "999")                  # typed, unbounded
    QTest.keyClick(ed.edit, Qt.Key_Escape)           #  real Esc key
    _settle(qapp2)
    assert cv._dim_edit is None
    _reap(qapp2)                                     # chip corpse: the
    assert cv.findChildren(ChipField) == []          #  GC law pins []
    assert len(cv._hist) == n                        #  only AFTER reap
    assert json.dumps(model_to_dict(m), sort_keys=True) == before


def test_untouched_enter_leaves_no_trace(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    before = json.dumps(model_to_dict(m), sort_keys=True)
    n = len(cv._hist)
    ed = _chip_on(cv, dist)
    QTest.keyClick(ed.edit, Qt.Key_Return)           # Enter, no typing
    _settle(qapp2)
    assert cv._dim_edit is None                      # closes, Fusion-
    assert len(cv._hist) == n                        #  like; NO dangling
    assert json.dumps(model_to_dict(m), sort_keys=True) == before
    _reap(qapp2)


def test_garbage_refuses_red_and_stays_open(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    before = json.dumps(model_to_dict(m), sort_keys=True)
    ed = _chip_on(cv, dist)
    _type(ed, "abc")                                 # Enter on garbage:
    _settle(qapp2)                                   #  red TOKEN +
    assert ed.is_invalid()                           #  rewind + STAYS
    assert theme.DARK["danger"] in ed.edit.styleSheet()   #  open (old
    assert ed.edit.toolTip()                         #   dialog law)
    sheet = ed.edit.styleSheet()                     # the TOKEN must
    assert "}" not in sheet.split("border")[0]       #  live INSIDE the
    #          selector - a dangling declaration parses to nothing and
    #          never paints (the rung-1 proof shot caught this for real)
    assert ed.edit.text() == "40.00"                 # honest rewind
    assert json.dumps(model_to_dict(m), sort_keys=True) == before
    QTest.keyClick(ed.edit, Qt.Key_Escape)
    _settle(qapp2)
    assert cv._dim_edit is None
    assert json.dumps(model_to_dict(m), sort_keys=True) == before
    ed = _chip_on(cv, dist)                          # the grammar win:
    _type(ed, "1inch")                               #  units land now
    _settle(qapp2)
    assert dist.value == pytest.approx(25.4)         #  (mm-native)
    _reap(qapp2)


def test_circle_chip_prefills_diameter_and_halves(dim_cv):
    # M165 RETARGET (cited): the m98 "Diameter (mm)"/default capture had
    # no chip successor in the panel dict sense - the chip carries that
    # truth as prefill text + placeholder.
    cv, m = dim_cv
    rad_c = m.sketch.constraints[1]                 # the circle chip
    ed = _chip_on(cv, rad_c)
    assert ed.edit.text() == "8.00"                  # r 4 shows D 8
    assert ed.edit.placeholderText() == "\u00d8 mm"
    _type(ed, "18")
    _settle(qapp2)
    assert rad_c.value == pytest.approx(9.0)         # M98 halving lives
    _reap(qapp2)
    rad_a = m.sketch.constraints[2]                  # the arc chip:
    ed = _chip_on(cv, rad_a)                         #  speaks its r
    assert ed.edit.text() == "10.00"
    assert ed.edit.placeholderText() == "R mm"
    _type(ed, "9")
    _settle(qapp2)
    assert rad_a.value == pytest.approx(9.0)         # arc: NO halving
    _reap(qapp2)


def test_plain_number_releases_binding(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    i = m.sketch.constraints.index(dist)
    m.dim_exprs[i] = {"e": "width", "t": "D"}
    ed = _chip_on(cv, dist)
    assert ed.edit.text() == "40.00"                 # bare, even bound
    _type(ed, "28")                                  # no "=" IS plain:
    _settle(qapp2)                                   #  the release law
    assert i not in m.dim_exprs
    assert dist.value == pytest.approx(28.0)
    _reap(qapp2)


def test_fx_binds_through_the_field(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    cv._params_provider = lambda: ({"width": 42.0}, 1.0)
    i = m.sketch.constraints.index(dist)
    ed = _chip_on(cv, dist)
    QTest.keyClicks(ed.edit, "=width")               # selectAll -> replace
    QTest.keyClick(ed.edit, Qt.Key_Return)
    _settle(qapp2)
    assert m.dim_exprs[i] == {"e": "width", "t": "D"}
    assert dist.value == pytest.approx(42.0)
    # D7's bug class: value ALREADY 42, re-type "=width" - a numeric
    # change-check would silently eat this re-bind; TEXT truth must not.
    n = len(cv._hist)
    ed = _chip_on(cv, dist)
    assert ed.edit.text() == "42.00"
    QTest.keyClicks(ed.edit, "=width")
    QTest.keyClick(ed.edit, Qt.Key_Return)
    _settle(qapp2)
    assert m.dim_exprs[i]["e"] == "width"            # re-bind LANDED
    assert len(cv._hist) == n + 1                    #  and cost a step
    _reap(qapp2)


def test_reseat_tracks_pan_and_zoom(dim_cv):
    import numpy as np
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    ed = _chip_on(cv, dist)
    cv._scale *= 2.0                                 # the m89 mutate
    cv._center = cv._center + np.array([3.0, -2.0])  #  technique
    cv.update()
    _settle(qapp2)                                   # paint -> re-seat
    rect = next(r for r, c in cv._dim_hits if c is dist)
    assert ed.geometry() == rect.toRect().adjusted(-2, -2, 2, 2)
    hits = []                                        # move-only-if-moved:
    real = ed.setGeometry                            #  a settled frame
    ed.setGeometry = lambda g: (hits.append(g), real(g))   # moves NOTHING
    cv.update()
    _settle(qapp2)
    assert hits == []                                # no setGeometry churn
    del ed.setGeometry
    QTest.keyClick(ed.edit, Qt.Key_Escape)
    _reap(qapp2)


def test_reseat_closes_on_constraint_death(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    _chip_on(cv, dist)
    m.remove_constraint(dist)                        # die WITHOUT painting
    after = json.dumps(model_to_dict(m), sort_keys=True)
    cv.update()
    _settle(qapp2)                                   # paint -> reseat:
    assert cv._dim_edit is None                      #  gone-chip closes
    assert json.dumps(model_to_dict(m), sort_keys=True) == after
    _reap(qapp2)


def test_discard_close_never_commits(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    ed = _chip_on(cv, dist)
    _type(ed, "60")                                  # a REAL step first
    _settle(qapp2)
    assert dist.value == pytest.approx(60.0)
    ed = _chip_on(cv, dist)                          # mid-60, type more:
    QTest.keyClicks(ed.edit, "55")                   #  NO Enter...
    assert cv.undo_op()                              #  ...history JUMPS
    _settle(qapp2)
    assert cv._dim_edit is None                      # discard-close: the
    #   typed 55 dies with the field - focus-out on hide may NOT commit
    assert m.sketch.constraints[0].value == pytest.approx(40.0)
    #                               ^ live object (_restore swaps the
    #                                 sketch): the UNDO wins, not the 55
    dist2 = next(c for c in m.sketch.constraints     # the LIVE distance
                 if isinstance(c, Distance))         #  (_restore swapped)
    ed = _chip_on(cv, dist2)                         # model swap mid-edit
    cv.set_model(SketchModel())                      #  must not crash,
    _reap(qapp2)                                     #   commit, or leak
    assert cv.findChildren(ChipField) == []          # (chip corpses ride
    #                                    the rung-3 GC law: reap FIRST)


def test_typein_chips_never_coexist(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    ln = m.sketch.lines[0]
    cv._pending = ("line", ln)                       # M90 half-line...
    cv._num_buf = "5"
    rect = next(r for r, c in cv._dim_hits if c is dist)
    QTest.mouseDClick(cv, Qt.LeftButton, Qt.NoModifier,
                      rect.center().toPoint(), 10)   # ...dies at open
    _settle(qapp2)
    assert cv._dim_edit is not None
    assert cv._pending is None and cv._num_buf == ""
    QTest.keyClick(cv._dim_edit.edit, Qt.Key_Escape)
    _reap(qapp2)


def test_angle_chip_goes_inline_too(dim_cv):
    # M165 RUNG 2 (m165_build_plan): angles left the panel - the chip's
    # BARE-DEGREES grammar took over (this gate inverted the rung-1
    # "stays on the panel" pin, cited).  Range refusals paint red and
    # STAY OPEN; a valid Enter commits through the branch re-snap.
    cv, m = dim_cv
    ang = m.sketch.constraints[3]
    rect = next(r for r, c in cv._dim_hits if c is ang)
    QTest.mouseDClick(cv, Qt.LeftButton, Qt.NoModifier,
                      rect.center().toPoint(), 10)
    _settle(qapp2)
    ed = cv._dim_edit
    assert type(ed) is ChipField and ed.constraint is ang
    assert ed.edit.text() == "30.00"                   # bare degrees...
    assert ed.edit.placeholderText() == "\u00b0"       #  unit in the PH
    _type(ed, "200")                                   # the old spin's
    _settle(qapp2)                                     #  0..179.99: red,
    assert ed.is_invalid()                             #   OPEN, honest
    assert cv._dim_edit is ed                          #   rewind
    _type(ed, "45")
    _settle(qapp2)
    assert math.degrees(ang.value) % 180 == pytest.approx(45, abs=1e-6)
    assert m.dim_exprs == {}                           # angles NEVER bind
    _reap(qapp2)


def test_badge_on_label_dclick_still_opens_the_dim_chip(dim_cv):
    # M164 gate-2's asymmetry law survives the routing change: hover
    # answers the badge, the DOUBLE-CLICK answers the DIM (it scans
    # _dim_hits only).  Badge planted on the label per the M164 FIX.
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    mp = m.point(20, 0)
    m.constrain(Midpoint(mp, m.sketch.lines[0]))
    cv.grab()
    dr = next(r for r, c in cv._dim_hits if c is dist)
    mc = next(c for _r, c in cv._constraint_hits
              if isinstance(c, Midpoint))
    cv._constraint_hits = [(dr if c is mc else r, c)
                           for r, c in cv._constraint_hits]
    QTest.mouseDClick(cv, Qt.LeftButton, Qt.NoModifier,
                      dr.center().toPoint(), 10)
    _settle(qapp2)
    assert cv._dim_edit is not None
    assert cv._dim_edit.constraint is dist           # the DIM, not the
    QTest.keyClick(cv._dim_edit.edit, Qt.Key_Escape) #  badge under it
    _reap(qapp2)


def test_chip_ink_suppressed_while_hits_survive(dim_cv):
    # The painter trio idiom (test_m89): children cannot leak into a
    # pixmap paint - so the suppressed chip is provably GONE from the
    # canvas's own output while the field sits there live.
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    rect = next(r for r, c in cv._dim_hits if c is dist)

    def chip_paint():
        pm = QPixmap(cv.width(), cv.height())
        pm.fill(QColor(theme.DARK["bg0"]))
        p = QPainter(pm)
        cv._draw_dimensions(p)
        p.end()
        img = pm.toImage()
        bg2 = QColor(theme.DARK["bg2"])
        x0, y0 = int(rect.left()), int(rect.top())
        x1, y1 = int(rect.right()), int(rect.bottom())
        n = 0
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                c = QColor(img.pixel(x, y))
                if (abs(c.red() - bg2.red()) <= 12
                        and abs(c.green() - bg2.green()) <= 12
                        and abs(c.blue() - bg2.blue()) <= 12):
                    n += 1
        return n

    assert chip_paint() > 0                          # closed: the chip's
    #                                                   bg2 fill is THERE
    ed = _chip_on(cv, dist)                          # open: ink gone...
    assert chip_paint() == 0                         #   (field is NOT a
    #                                                   pixmap child)
    assert any(c is dist for _r, c in cv._dim_hits)  # hits SURVIVE: the
    #                                                   re-seat rides them
    QTest.keyClick(ed.edit, Qt.Key_Escape)
    _reap(qapp2)


# ---------------------------------------------------- the seam door ----

def test_script_seam_one_liners(dim_cv, monkeypatch):
    from conftest import script_dim_edit
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    before = json.dumps(model_to_dict(m), sort_keys=True)
    script_dim_edit(monkeypatch, "60")               # plain, legacy door
    cv._edit_dim(dist)
    assert dist.value == pytest.approx(60.0)
    monkeypatch.undo()
    script_dim_edit(monkeypatch, "  =width ")       # padded fx: trim law
    cv._params_provider = lambda: ({"width": 42.0}, 1.0)
    cv._edit_dim(dist)
    i = m.sketch.constraints.index(dist)
    assert m.dim_exprs[i]["e"] == "width"
    assert dist.value == pytest.approx(42.0)
    monkeypatch.undo()
    n = len(cv._hist)
    script_dim_edit(monkeypatch, "=bogus * 2")      # loud refusal: the
    cv._edit_dim(dist)                               #  dialog-era promise
    assert cv._warn_text.startswith("Binding refused:")
    assert len(cv._hist) == n                        #  rides the seam:
    assert m.dim_exprs.get(i, {}).get("e") == "width"  #   nothing moved
    script_dim_edit(monkeypatch, "0")                # the restored spin
    assert len(cv._hist) == n                        #  range: 0 refused
    assert dist.value == pytest.approx(42.0)
    monkeypatch.undo()
    script_dim_edit(monkeypatch, "40")               # unbind back + value
    cv._edit_dim(dist)                               #  home for the bytes
    assert m.dim_exprs == {}
    assert dist.value == pytest.approx(40.0)
    # LM is not exact arithmetic: after 60->42->40 the endpoint rides
    # ~40.0000000001 - the LAW is plain-value-homes-the-dim, so probe
    # the value + the empty binding store, not serialized float noise.
    assert m.sketch.lines[0].b.x == pytest.approx(40.0, abs=1e-6)


# ------------------------------------------------ rung 2: angles + F2 ----

def test_angle_grammar_refuses_units_and_bindings(dim_cv, monkeypatch):
    cv, m = dim_cv
    ang = m.sketch.constraints[3]
    before = json.dumps(model_to_dict(m), sort_keys=True)
    n = len(cv._hist)
    ed = _chip_on(cv, ang)
    _type(ed, "45mm")                                  # the oss doc's
    _settle(qapp2)                                     #  "2mm + 4"
    assert ed.is_invalid()                             #  class: units
    assert ed.edit.toolTip()                           #   die red
    _type(ed, "=width")                                # M89 lengths-only
    _settle(qapp2)                                     #  is now RED-
    assert ed.is_invalid()                             #  enforced
    assert cv._dim_edit is ed                          #  stays OPEN
    QTest.keyClick(ed.edit, Qt.Key_Escape)
    _settle(qapp2)
    assert len(cv._hist) == n                          # zero trace
    assert json.dumps(model_to_dict(m), sort_keys=True) == before
    from conftest import script_dim_edit               # the seam speaks
    script_dim_edit(monkeypatch, "90")                 #  the SAME
    cv._edit_dim(ang)                                  #   grammar: ...
    assert math.degrees(ang.value) % 180 == pytest.approx(90, abs=1e-6)
    n2 = len(cv._hist)
    script_dim_edit(monkeypatch, "200")                # range refusal
    cv._edit_dim(ang)                                  #  rides it too
    assert cv._warn_text.startswith("angle out of range")
    assert len(cv._hist) == n2                         #  zero write
    _reap(qapp2)


def test_f2_opens_the_chip_then_the_last_dim(dim_cv):
    cv, m = dim_cv
    dist = m.sketch.constraints[0]
    rect = next(r for r, c in cv._dim_hits if c is dist)
    cv._cursor = cv._world(rect.center())              # hover the chip
    QTest.keyClick(cv, Qt.Key_F2)
    _settle(qapp2)
    ed = cv._dim_edit                                  # door 1: the
    assert type(ed) is ChipField and ed.constraint is dist   #  hovered
    QTest.keyClick(ed.edit, Qt.Key_Escape)             #   chip
    _settle(qapp2)
    assert cv._last_dim is None                        # EDITED nothing
    cv._cursor = None                                  #  yet
    QTest.keyClick(cv, Qt.Key_F2)                      # no chip, no
    _settle(qapp2)                                     #  last dim:
    assert cv._dim_edit is None                        #   F2 stays inert
    ed = _chip_on(cv, dist)                            # NOW edit once:
    _type(ed, "55")                                    #  the rung-1
    _settle(qapp2)                                     #  _last_dim seed
    assert cv._last_dim is dist                        #  finally lives
    cv._cursor = None                                  # fallback door:
    QTest.keyClick(cv, Qt.Key_F2)                      #  last dim wins
    _settle(qapp2)
    assert cv._dim_edit is not None
    assert cv._dim_edit.constraint is dist
    QTest.keyClick(cv._dim_edit.edit, Qt.Key_Escape)
    _reap(qapp2)


def test_angle_chip_death_mid_edit_closes_cleanly(dim_cv):
    # Plan risk 5, made real the way the PAINTER actually drops an
    # angle chip: an AngleBetween whose lines go unshared mid-edit
    # (_angle_pivot -> None -> arc None -> continue: no chip). A
    # single-line Angle survives zero-length (atan2(0,0)=0 still
    # draws) - measured, not assumed. The re-seat death guard closes
    # the field and the orphaned constraint is NEVER written.
    cv, m = dim_cv
    from tracer.core.sketch.constraints import AngleBetween
    ln2 = m.sketch.lines[-1]                           # the 30 deg line
    l3 = m.add_line(m.point(120, 30), m.point(130, 35))
    ab = AngleBetween(ln2, l3, math.radians(20))
    m.constrain(ab)
    cv.grab()                                          # chip appears
    ed = _chip_on(cv, ab)
    assert ed.constraint is ab
    dx, dy = ln2.b.x - ln2.a.x, ln2.b.y - ln2.a.y      # EXACT parallel:
    l3.a.x, l3.a.y = 200.0, 200.0                      #  den = 0.0 to
    l3.b.x, l3.b.y = 200.0 + dx, 200.0 + dy            #   the bit
    cv.update()
    _settle(qapp2)
    assert cv._dim_edit is None                        # death guard
    assert math.degrees(ab.value) % 180 == pytest.approx(20, abs=1e-9)
    _reap(qapp2)


# ------------------------------------------------------- the win door ----

@pytest.fixture
def win():
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp2.processEvents()
    yield w
    w._unsaved = False
    w.close()


def test_mw_guard_swallows_model_layer_while_editing(win, monkeypatch):
    from tracer.core.document import ExtrudeFeature
    from tracer.ui.cmddialog import Shell
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *a, **k: (5.0, True)))
    win.new_document()
    win.action_new_sketch()
    m = win.sketch.model
    p0, p1 = m.point(0, 0), m.point(40, 20)
    m.add_rect(p0, p1)                               # CLOSED profile -
    bottom = m.sketch.lines[0]                       #  E must extrude it
    m.constrain(Distance(bottom.a, bottom.b, 40.0))
    cv = win.sketch
    qapp2.processEvents()
    cv.grab()
    assert win._dispatch_key(Qt.Key_E, Qt.NoModifier) is True   # E
    #                                       extrudes FROM a sketch...
    qapp2.processEvents()
    feat = [f for f in win.doc.features
            if isinstance(f, ExtrudeFeature)][0]
    win.edit_sketch(feat)
    cv = win.sketch
    cv.grab()
    dist = next(c for _r, c in cv._dim_hits if isinstance(c, Distance))
    cv._open_dim_editor(dist)
    qapp2.processEvents()
    assert win._dispatch_key(Qt.Key_E, Qt.NoModifier) is False  # ...but
    #                                        a live chip edit is DEAF:
    QTest.keyClick(cv._dim_edit.edit, Qt.Key_Escape)  # letters type in
    _reap(qapp2)                                      #  the field only


def test_widget_edit_drives_the_solid(win, monkeypatch):
    # The m5 end-to-end, dialog-free: dclick, type, Enter, finish.
    from tracer.core.document import ExtrudeFeature
    from tracer.ui.cmddialog import Shell
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *a, **k: (5.0, True)))
    win.new_document()
    win.action_new_sketch()
    m = win.sketch.model
    p0 = m.point(0, 0)
    p1 = m.point(40, 20)
    m.add_rect(p0, p1)
    bottom = m.sketch.lines[0]
    m.constrain(Fixed(p0, x=0.0, y=0.0))
    m.constrain(Distance(bottom.a, bottom.b, 40.0))
    cv = win.sketch
    qapp2.processEvents()
    cv.finish()
    qapp2.processEvents()
    feat = [f for f in win.doc.features if isinstance(f, ExtrudeFeature)][0]
    v0 = win.doc.result.volume
    assert v0 == pytest.approx(40 * 20 * 5, rel=1e-2)
    win.edit_sketch(feat)
    cv = win.sketch
    cv.grab()
    dim = next(c for _r, c in cv._dim_hits if isinstance(c, Distance))
    rect = next(r for r, c in cv._dim_hits if c is dim)
    QTest.mouseDClick(cv, Qt.LeftButton, Qt.NoModifier,
                      rect.center().toPoint(), 10)
    _settle(qapp2)
    ed = cv._dim_edit
    assert type(ed) is ChipField                     # the REAL door, no
    QTest.keyClicks(ed.edit, "60")                   #  patch anywhere on
    QTest.keyClick(ed.edit, Qt.Key_Return)           #   the edit path
    _settle(qapp2)
    cv.finish()
    qapp2.processEvents()
    assert win.doc.result.volume == pytest.approx(60 * 20 * 5, rel=1e-2)
    _reap(qapp2)


def test_key_laws_untouched():
    # The do-not-touch list, restated as greps. M165 R2 RETARGET
    # (cited): F2 LANDED this rung - the law flipped from "absent" to
    # "present in the canvas, absent from the claim tables" (F2 is
    # non-printable: a SKETCH_KEYS entry would be inert dead code and
    # m113's claim-set honesty gate must never see it).
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "tracer" / "ui"
    se = (root / "sketcheditor.py").read_text(encoding="utf-8")
    assert "Qt.Key_F2" in se                           # the keyboard door
    for marker in ("_open_dim_editor", "_apply_dim_edit", "_reseat",
                   "_chip_under_cursor"):
        assert marker in se
    cp = (root / "cmdpanel.py").read_text(encoding="utf-8")
    assert "parse_scalar" in cp                        # the ONE helper the
    #                                                   chip rides too
    cmds = (root / "commands.py").read_text(encoding="utf-8")
    assert '"F2"' not in cmds                          # NOT in the claim
    assert "'F2'" not in cmds                          #  tables - rung 2
    #                                                   law, m113 honest
    assert "SKETCH_KEYS" in cmds                       # claim tables byte-
    from tracer.ui.commands import SKETCH_KEYS         #  untouched, and
    assert "L" in SKETCH_KEYS                          #  still honest
