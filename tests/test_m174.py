"""M174 rung 1 - THE LABEL CLAIMS THE PRESS (draggable dim chips).

FD5 LAW 35, observed and cloned: "Dragging an EXISTING dim relocates
it live." The chip's rect already rules the double-click door (M165 R2,
paint == hit); today the PRESS obeys it too - a chip outranks the
canvas beneath it, so a label never mutates into a marquee or a grab
in disguise. And a LABEL IS NOT GEOMETRY: the drag is a RAW delta with
no magnet, no solve and no selection change - the label drifts in
world units while the figure holds its coordinates BIT-EXACT. Chrome
still pays the ledger honestly: exactly ONE undo row per gesture, and
- because the undo ledger is model_to_dict itself - the position rides
the "lo" key, omitted at zero so an undragged file stays byte-identical
and an undone label comes back HOME, not merely near it.

Rung 2 audits that ledger as a FILE: the position survives the full
json transport, a parked-at-zero label keeps the bytes EXACTLY as
untouched as never having moved, a PRE-M174 file (no key) loads at the
default post and paints there, REDO re-files the label onto its new
home (the future stack is the same JSON), and the positional fx
bindings of M89 look the other way - a label that moved changes which
pixel you click, never which constraint a driving expression steers.
"""
import json
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, QPoint, Qt               # noqa
from PySide6.QtGui import QMouseEvent                                # noqa
from PySide6.QtTest import QTest                                    # noqa
from PySide6.QtWidgets import QApplication                          # noqa

from tracer.core.sketch.constraints import Distance                 # noqa
from tracer.core.sketch.model import (SketchModel, model_from_dict,  # noqa
                                      model_to_dict)
from tracer.ui.sketcheditor import SketchCanvas                     # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    c = SketchCanvas()
    c.set_model(SketchModel())        # empty once: scale 4 / centre 0 stay
    c.resize(600, 400)
    c._snap_grid = False
    yield c
    c.deleteLater()


def _scr(x, y):
    return QPoint(int(round(300 + 4.0 * x)), int(round(200 - 4.0 * y)))


def _pt(qpf):
    return QPoint(int(round(qpf.x())), int(round(qpf.y())))


def _paint(ed, qapp):
    ed.grab()                          # paint FRESH: _dim_hits is paint's
    for _ in range(3):                 #  own ledger (paint == hit law)
        qapp.processEvents()
    return list(ed._dim_hits)


def _dim_scene(ed, qapp):
    m = ed.model
    a, b = m.point(0, 0), m.point(8, 0)
    m.add_line(a, b)
    c = Distance(a, b, 8.0)
    m.constrain(c)
    ed._solve()
    hits = _paint(ed, qapp)
    assert len(hits) == 1 and hits[0][1] is c
    return m, a, b, c, hits[0][0]


def _lmove_px(ed, p):
    #  ONE left-held move at RAW PIXELS (the chip's own coordinates)
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))


def test_dragging_a_label_moves_only_the_label(ed, qapp):
    m, a, b, c, rect0 = _dim_scene(ed, qapp)
    home = (a.x, a.y, b.x, b.y)        #  POST-SOLVE truth to stay exact
    cx = rect0.center()
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _pt(cx))
    assert ed._dim_drag is not None    #  THE LABEL CLAIMED THE PRESS
    p2 = QPointF(cx.x() + 24.0, cx.y() - 16.0)
    _lmove_px(ed, p2)                  #  +6 world-x, +4 world-y (scale 4)
    assert c.label_off == pytest.approx((6.0, 4.0))
    assert (a.x, a.y, b.x, b.y) == home          # geometry BIT-EXACT
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _pt(p2))
    assert ed._dim_drag is None
    hits = _paint(ed, qapp)
    assert hits[0][0].center().x() - cx.x() == pytest.approx(24.0, abs=0.5)
    assert hits[0][0].center().y() - cx.y() == pytest.approx(-16.0, abs=0.5)
    assert c is next(x for x in m.sketch.constraints
                     if isinstance(x, Distance))   # same object, moved home


def test_a_press_on_a_label_leaves_the_picks_alone(ed, qapp):
    m, a, b, c, rect0 = _dim_scene(ed, qapp)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(0, 0))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(0, 0))
    assert ed._sel == [a]                          # a plain click picks
    cx = rect0.center()
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _pt(cx))
    assert ed._band is None                        # NO marquee under a
    assert ed._sel == [a]                          #  chip; the pick rides
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _pt(cx))
    assert ed._dim_drag is None                    # a no-move grip DIES
    assert getattr(c, "label_off", None) is None   #  and costs NOTHING
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _scr(-9, -9))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _scr(-9, -9))
    assert ed._sel == []                           # CONTRAST: an empty
    #                                               press still clears


def test_a_label_gesture_costs_one_row_and_goes_home_on_undo(ed, qapp):
    m, a, b, c, rect0 = _dim_scene(ed, qapp)
    assert "lo" not in model_to_dict(m)["constraints"][0]   # zero rides
    h0 = len(ed._hist)                               #  NOTHING in the
    cx = rect0.center()                              #   file
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _pt(cx))
    p2 = QPointF(cx.x() + 24.0, cx.y() - 16.0)
    _lmove_px(ed, p2)
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _pt(p2))
    assert len(ed._hist) == h0 + 1                   # ONE row, whole act
    assert "lo" in model_to_dict(m)["constraints"][0]
    assert ed.undo_op()
    r = next(x for x in m.sketch.constraints         # undo-SWAP law:
             if isinstance(x, Distance))             #  RE-READ through
    assert getattr(r, "label_off", None) is None     #   m.sketch: the
    assert len(ed._hist) == h0                       #    label is HOME
    assert "lo" not in model_to_dict(m)["constraints"][0]


def test_the_double_click_door_survives_the_move(ed, qapp):
    m, a, b, c, rect0 = _dim_scene(ed, qapp)
    cx = rect0.center()
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _pt(cx))
    p2 = QPointF(cx.x() + 20.0, cx.y() + 28.0)       # BELOW the old home
    _lmove_px(ed, p2)
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _pt(p2))
    hits = _paint(ed, qapp)
    newc = hits[0][0].center()
    assert abs(newc.y() - cx.y()) > 20               # it really MOVED
    h1 = len(ed._hist)
    QTest.mouseDClick(ed, Qt.LeftButton, Qt.NoModifier, _pt(newc))
    field = ed._dim_edit                             # ONE door, every
    assert field is not None and field.constraint is c   #  kind, MOVED
    ctr = field.geometry().center()                  #   seat: paint-
    assert abs(ctr.x() - round(newc.x())) <= 1       #   derived, so it
    assert abs(ctr.y() - round(newc.y())) <= 1       #    rides the move
    assert len(ed._hist) == h1                       # a door is not an edit
    ed._close_dim_editor()


# ---- RUNG 2: THE POSITION SURVIVES THE FILE --------------------------------

def test_the_label_home_survives_the_file_round_trip(ed, qapp):
    m, a, b, c, rect0 = _dim_scene(ed, qapp)
    c.label_off = (6.0, -14.0)
    payload = json.loads(json.dumps(model_to_dict(m)))   # the FILE bytes
    assert payload["constraints"][0]["lo"] == [6.0, -14.0]
    m2 = model_from_dict(payload)
    r = next(x for x in m2.sketch.constraints
             if isinstance(x, Distance))
    assert getattr(r, "label_off", None) == (6.0, -14.0)  # EXACT floats


def test_a_label_parked_at_zero_leaves_the_bytes_untouched(ed, qapp):
    m, a, b, c, rect0 = _dim_scene(ed, qapp)
    base = json.dumps(model_to_dict(m), sort_keys=True)
    c.label_off = (0.0, 0.0)         # dragged AND parked back home
    assert json.dumps(model_to_dict(m), sort_keys=True) == base
    assert "lo" not in model_to_dict(m)["constraints"][0]


def test_pre_m174_files_load_at_the_default_post(ed, qapp):
    m, a, b, c, rect0 = _dim_scene(ed, qapp)
    legacy = model_to_dict(m)
    legacy["constraints"][0].pop("lo", None)             # old bytes
    m2 = model_from_dict(legacy)
    assert getattr(next(x for x in m2.sketch.constraints
                        if isinstance(x, Distance)),
                   "label_off", None) is None
    ed.set_model(m2)
    hits = _paint(ed, qapp)                              # set_model FITS
    rp = next(x for x in m2.sketch.constraints           #  the view - so
              if isinstance(x, Distance))                #  the law: the
    s = ed.w2s((rp.p.x + rp.q.x) / 2, (rp.p.y + rp.q.y) / 2)   #  label
    assert hits[0][0].center().x() == pytest.approx(s.x(), abs=0.5)     #
    assert hits[0][0].center().y() == pytest.approx(s.y() - 16.0,       #
                                                    abs=0.5)            # post


def test_redo_refiles_the_label_onto_its_new_home(ed, qapp):
    m, a, b, c, rect0 = _dim_scene(ed, qapp)
    cx = rect0.center()
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, _pt(cx))
    p2 = QPointF(cx.x() + 24.0, cx.y() + 56.0)
    _lmove_px(ed, p2)
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, _pt(p2))
    ed.undo_op()
    assert ed.redo_op()
    r = next(x for x in m.sketch.constraints            # undo-SWAP law:
             if isinstance(x, Distance))                #  RE-READ
    assert r.label_off == pytest.approx((6.0, -14.0))
    hits = _paint(ed, qapp)
    assert hits[0][0].center().x() == pytest.approx(cx.x() + 24.0, abs=0.5)
    assert hits[0][0].center().y() == pytest.approx(cx.y() + 56.0, abs=0.5)


def test_filing_a_label_leaves_the_fx_bindings_alone(ed, qapp):
    m, a, b, c, rect0 = _dim_scene(ed, qapp)
    i = m.sketch.constraints.index(c)
    m.dim_exprs[i] = {"e": "width", "t": "D"}           # M89: fx steers it
    c.label_off = (6.0, -14.0)                          # ship the label
    m2 = model_from_dict(json.loads(json.dumps(model_to_dict(m))))
    k = next(iter(m2.dim_exprs))
    assert m2.dim_exprs[k] == {"e": "width", "t": "D"}
    assert int(k) == m2.sketch.constraints.index(       # the binding
        next(x for x in m2.sketch.constraints           #  still points
             if isinstance(x, Distance)))               #   at the dim
