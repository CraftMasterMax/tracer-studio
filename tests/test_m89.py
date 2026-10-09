"""M89 — sketch dimensions carry formulas (M81b, the deeper half).

M81 put fx on FEATURE levers. Fusion's parameter sheet goes deeper: a
sketch DIMENSION can say `= width * 2`, and when the sheet changes the
sketch RE-SOLVES and the extruded solid follows. Here that round trip
is real: bindings live in the sketch payload as
{constraint-index: {expr, type-tag}} — the tag refuses to silently
re-bind when geometry was edited under the binding — and
Document.recompute re-derives sketch geometry (model → apply formulas →
solve → regions) before building, so a parameter edit on the sheet
moves the extruded body.

Honest scope: extrude/revolve profiles only (hole/loft/sweep sketches
keep frozen geometry for now); linear dimensions scale with document
measures, angles never do; and a bound dimension edited by hand gets
overwritten on the next parameter-driven rebuild — the formula always
wins, exactly like M81's feature bindings.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QPainter, QPixmap                    # noqa: E402
from PySide6.QtWidgets import QApplication                            # noqa: E402

from tracer.core.document import (Document, ExtrudeFeature,            # noqa: E402
                                  PrimitiveFeature)
from tracer.core.sketch.constraints import (Distance, Fixed,          # noqa: E402
                                            Horizontal, Radius,
                                            Vertical)
from tracer.core.sketch.entities import Point                         # noqa: E402
from tracer.core.sketch.model import (SketchModel, model_from_dict,   # noqa: E402
                                      model_to_dict)
from tracer.core.sketch.profile import regions


def _welded_rect(m: SketchModel, w=30.0, h=20.0):
    """A rectangle with an explicit bottom-edge distance dimension —
    the shape the editor's own rect tool produces (H/V constraints
    included), so the solver has something to re-solve."""
    a, b = m.point(0, 0), m.point(w, 0)
    c, d = m.point(w, h), m.point(0, h)
    l1, l2 = m.add_line(a, b), m.add_line(b, c)
    l3, l4 = m.add_line(c, d), m.add_line(d, a)
    sk = m.sketch
    sk.constraints.extend([Horizontal(l1), Horizontal(l3),
                           Vertical(l2), Vertical(l4),
                           Fixed(a, x=a.x, y=a.y)])
    dim = Distance(a, b, w)
    sk.constraints.append(dim)
    return (a, b, c, d), dim


# ------------------------------------------------------------------ core

def test_apply_dim_params_writes_bound_values():
    m = SketchModel()
    (a, b, c, d), dim = _welded_rect(m)
    i = m.sketch.constraints.index(dim)
    m.dim_exprs[i] = {"e": "width", "t": "D"}
    warns = m.apply_dim_params({"width": 55.0})
    assert warns == []
    assert dim.value == pytest.approx(55.0)
    m.solve()
    assert abs(b.x - a.x) == pytest.approx(55.0, abs=1e-6)


def test_angles_never_scale_with_units():
    from tracer.core.sketch.constraints import Angle
    m = SketchModel()
    a, b = m.point(0, 0), m.point(10, 0)
    ln = m.add_line(a, b)
    ang = Angle(ln, math.radians(45))
    m.sketch.constraints.append(ang)
    i = m.sketch.constraints.index(ang)
    m.dim_exprs[i] = {"e": "tilt", "t": "A"}
    m.apply_dim_params({"tilt": 45.0}, scale=25.4)     # INCH document
    assert ang.value == pytest.approx(math.radians(45.0))


def test_stale_and_mismatched_bindings_idle_loudly():
    m = SketchModel()
    (a, b, c, d), dim = _welded_rect(m)
    i = m.sketch.constraints.index(dim)
    m.dim_exprs[i] = {"e": "width", "t": "R"}         # type moved under it
    m.dim_exprs[99] = {"e": "width", "t": "D"}        # constraint gone
    warns = m.apply_dim_params({"width": 55.0})
    assert len(warns) == 2
    assert dim.value == pytest.approx(30.0)           # untouched


def test_dim_exprs_round_trip_through_serialization():
    m = SketchModel()
    (a, b, c, d), dim = _welded_rect(m)
    i = m.sketch.constraints.index(dim)
    m.dim_exprs[i] = {"e": "width", "t": "D"}
    back = model_from_dict(model_to_dict(m))
    assert back.dim_exprs == {i: {"e": "width", "t": "D"}}


# ------------------------------------------------- document end-to-end

def _extruded_rect_doc(w=30.0, h=20.0, height=5.0):
    d = Document(title="fx-sketch")
    m = SketchModel(plane="XY")
    (a, b, c, dd), dim = _welded_rect(m, w, h)
    loops, _warns = m.to_loops()
    regs = regions(loops)
    i_dim = m.sketch.constraints.index(dim)
    m.dim_exprs[i_dim] = {"e": "width", "t": "D"}
    payload = model_to_dict(m)
    d.params = {"width": str(w)}
    d.features.append(ExtrudeFeature(
        name="Plate", outer=regs[0]["points"], holes=[], height=height,
        plane="XY", placement=(0.0, 0.0, 0.0), sketch=payload, sid=m.sid,
        region=0))
    return d, i_dim


def test_parameter_drives_sketch_and_solid_end_to_end():
    d, _i = _extruded_rect_doc()
    v1 = d.recompute().volume
    assert v1 == pytest.approx(30.0 * 20.0 * 5.0, rel=1e-3)
    d.params["width"] = "50"
    v2 = d.recompute().volume
    assert v2 == pytest.approx(50.0 * 20.0 * 5.0, rel=1e-3)
    # the sketch payload itself follows, so reopening the editor sees it
    m = model_from_dict(d.features[0].sketch)
    assert m.sketch.constraints[_i].value == pytest.approx(50.0)


def test_expression_chain_flows_into_the_sketch():
    d, _i = _extruded_rect_doc()
    d.params["double"] = "width * 2"
    d.features[0].sketch["dim_exprs"] = {str(_i): {"e": "double", "t": "D"}}
    d.params["width"] = "18"
    v = d.recompute().volume
    assert v == pytest.approx(36.0 * 20.0 * 5.0, rel=1e-3)


def test_inch_document_scales_the_dimension():
    d, _i = _extruded_rect_doc()
    d.units = "inch"
    d.params["width"] = "2"                    # two INCHES
    v = d.recompute().volume
    assert v == pytest.approx(50.8 * 20.0 * 5.0, rel=1e-2)


def test_unbound_sketches_are_never_touched():
    d, _i = _extruded_rect_doc()
    d.features[0].sketch["dim_exprs"] = {}
    d.params["width"] = "99"
    v = d.recompute().volume
    assert v == pytest.approx(30.0 * 20.0 * 5.0, rel=1e-3)


# -------------------------------------------------------------------- UI

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
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
        qapp.processEvents()
        yield w
        w._unsaved = False
        w.close()
        r.close()
    except Exception:
        raise


def test_dimension_fx_dialog_binds_and_applies_live(win, qapp,
                                                    monkeypatch):
    from tracer.ui import cmddialog
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    m = cv.model
    (a, b, c, d), dim = _welded_rect(m, 30.0, 20.0)
    win.doc.params = {"width": "42"}
    win._wire_sketch_params(cv)                # the provider hookup
    i = m.sketch.constraints.index(dim)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"val": 30.0, "fx": "width"})
    cv._edit_dim(dim)
    qapp.processEvents()
    assert m.dim_exprs[i]["e"] == "width"
    assert m.dim_exprs[i]["t"] == "D"
    assert dim.value == pytest.approx(42.0)    # applied live


def test_fx_rejects_unknown_names_without_touching_anything(
        win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch                            # fresh sketch session
    m = cv.model
    (a, b, c, d), dim = _welded_rect(m, 25.0, 15.0)
    win.doc.params = {}
    win._wire_sketch_params(cv)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"val": 1.0, "fx": "bogus * 2"})
    cv._edit_dim(dim)
    qapp.processEvents()
    assert m.dim_exprs == {}
    assert dim.value == pytest.approx(25.0)    # plain value also refused


def test_blank_fx_releases_the_binding(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch                            # fresh sketch session
    m = cv.model
    (a, b, c, d), dim = _welded_rect(m, 22.0, 11.0)
    i = m.sketch.constraints.index(dim)
    m.dim_exprs[i] = {"e": "width", "t": "D"}
    win.doc.params = {"width": "77"}
    win._wire_sketch_params(cv)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"val": 28.0, "fx": ""})
    cv._edit_dim(dim)
    qapp.processEvents()
    assert i not in m.dim_exprs
    assert dim.value == pytest.approx(28.0)


def test_bound_dimension_paints_the_equals_chip(win, qapp):
    # Fusion marks driven dimensions with "="; the chip grows to fit
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    m = cv.model
    (a, b, c, d), dim = _welded_rect(m, 30.0, 20.0)
    cv.resize(600, 400)
    cv._scale = 6.0
    cv._center = np.array([15.0, 10.0])

    def chip_ink():
        pm = QPixmap(600, 400)
        pm.fill(QColor(20, 20, 24))
        p = QPainter(pm)
        cv._draw_dimensions(p)
        p.end()
        img = pm.toImage()
        from tracer.ui import theme
        chip = QColor(theme.DARK["bg2"])     # M112: chip rides the bg2 token
        n = 0
        for x in range(0, 600, 2):
            for y in range(0, 400, 2):
                q = img.pixelColor(x, y)
                if (abs(q.red() - chip.red()) <= 2
                        and abs(q.green() - chip.green()) <= 2
                        and abs(q.blue() - chip.blue()) <= 2):
                    n += 1
        return n

    plain = chip_ink()
    i = m.sketch.constraints.index(dim)
    m.dim_exprs[i] = {"e": "width", "t": "D"}
    bound = chip_ink()
    assert bound > plain              # the "= 30.00" chip carries more ink
