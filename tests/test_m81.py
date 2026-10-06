"""M81 — User Parameters + expressions: the parametric heart.

Fusion's Change Parameters SHEET (not just the per-feature dialog):
named global numbers (`width = 20`), expressions that reference each
other (`thickness = width / 2`), and an fx column on every numeric
lever so a feature's number can be BOUND to a formula.  Change a
parameter and the whole model rebuilds from it.

Honest scope: parameters are unitless scalars spoken in the document's
current measures (like every dialog here); bindings live on feature
fields (sketch-dimension bindings are M81b); and the expression
language is deliberately small — + - * / ** , parentheses and
min/max/sqrt/abs/round — evaluated on a whitelisted AST, never exec().
"""
import math

import pytest

pytest.importorskip("PySide6")

from tracer.core import params                                                # noqa: E402
from tracer.core.document import (Document, LinearPatternFeature,             # noqa: E402
                                  PrimitiveFeature)


# ---------------------------------------------------------------- evaluator

def test_eval_expr_arithmetic_and_functions():
    v = {"width": 20.0}
    assert params.eval_expr("2 + 3 * 4", v) == 14.0
    assert params.eval_expr("(2 + 3) * 4", v) == 20.0
    assert params.eval_expr("width * 2 - 5", v) == 35.0
    assert params.eval_expr("2 ** width ** 0 * sqrt(16)", v) == 8.0
    assert params.eval_expr("-width / 4", v) == -5.0
    assert params.eval_expr("min(width, 3) + max(1, 2) + abs(-1) + round(1.4)",
                            v) == 7.0


def test_eval_expr_rejects_anything_unsafe():
    for bad in ("__import__('os').system('rm -rf /')", "width.real",
                "(lambda: 1)()", "'20' + '0'", "open('/etc/passwd')",
                "width if width else 0", ""):
        with pytest.raises(params.ParamError):
            params.eval_expr(bad, {"width": 20.0})


def test_resolve_chains_and_forward_references():
    got = params.resolve({"a": "b * 2", "b": "10", "c": "sqrt(a)"})
    assert got == {"a": 20.0, "b": 10.0, "c": math.sqrt(20.0)}


def test_resolve_reports_cycles_and_strays():
    with pytest.raises(params.ParamError) as e:
        params.resolve({"a": "b", "b": "c * 2", "c": "a"})
    msg = str(e.value)
    assert "a" in msg and "b" in msg and "c" in msg      # the whole loop
    with pytest.raises(params.ParamError) as e:
        params.resolve({"a": "nope + 1"})
    assert "nope" in str(e.value)
    with pytest.raises(params.ParamError):
        params.resolve({"2bad": "1"})                    # illegal name


def test_parse_sheet_grammar():
    raw = params.parse_sheet("# brackets\nwidth = 20\n\n"
                             "thickness = width / 2   # half\n")
    assert raw == {"width": "20", "thickness": "width / 2"}
    with pytest.raises(params.ParamError):
        params.parse_sheet("width =")                   # empty formula
    with pytest.raises(params.ParamError):
        params.parse_sheet("the width = 20")            # illegal name
    with pytest.raises(params.ParamError):
        params.parse_sheet("a = 1\na = 2")              # duplicate


# ------------------------------------------------------------ document core

def _box_doc():
    d = Document(title="p")
    d.features.append(PrimitiveFeature(name="Box", kind="box",
                                       dims={"dx": 10.0, "dy": 4.0,
                                             "dz": 2.0}))
    return d


def test_params_and_bindings_round_trip():
    d = _box_doc()
    d.params = {"width": "20"}
    d.features[0].bindings = {"dx": "width"}
    back = Document.from_dict(d.to_dict())
    assert back.params == {"width": "20"}
    assert back.features[0].bindings == {"dx": "width"}
    # old files carry neither key and must load clean
    legacy = d.to_dict()
    del legacy["params"]
    legacy["features"][0].pop("bindings")
    old = Document.from_dict(legacy)
    assert old.params == {} and old.features[0].bindings == {}


def test_parameter_driven_box_rebuilds():
    d = _box_doc()
    d.params = {"width": "10"}
    d.features[0].bindings = {"dx": "width"}
    assert d.recompute().volume == pytest.approx(80.0, rel=1e-6)
    d.params["width"] = "30"
    assert d.recompute().volume == pytest.approx(240.0, rel=1e-6)


def test_int_levers_stay_int():
    d = _box_doc()
    src = d.features[0]
    d.features.append(LinearPatternFeature(name="Row", source_uid=src.uid,
                                           vector=(20.0, 0.0, 0.0),
                                           count=2))
    d.params = {"w": "8"}
    d.features[1].bindings = {"count": "w / 2"}
    assert d.recompute().volume == pytest.approx(4 * 80.0, rel=1e-3)
    assert d.features[1].count == 4 and isinstance(d.features[1].count, int)


def test_units_spoken_parameters():
    d = _box_doc()
    d.units = "inch"
    d.params = {"width": "1"}            # one INCH of width
    d.features[0].bindings = {"dx": "width"}
    vol_in = d.recompute().volume
    assert vol_in == pytest.approx(25.4 * 4.0 * 2.0, rel=1e-6)


# --------------------------------------------------------------------- UI

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
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
        r.ctx.release()
    except Exception:
        raise


def _win_box(win):
    win.new_document()
    d = win.doc
    d.features.append(PrimitiveFeature(name="Box", kind="box",
                                       dims={"dx": 10.0, "dy": 4.0,
                                             "dz": 2.0}))
    win.recompute()
    return d.features[0]


def test_user_parameters_dialog_edits_sheet(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    box = _win_box(win)
    box.bindings = {"dx": "width"}
    win.recompute()
    assert win.doc.result.volume == pytest.approx(80.0, rel=1e-6)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"sheet": "width = 30\n"})
    win.action_user_parameters()
    qapp.processEvents()
    assert win.doc.params == {"width": "30"}
    assert win.doc.result.volume == pytest.approx(240.0, rel=1e-6)
    # a broken sheet is refused WITHOUT touching the document
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"sheet": "width = bogus\n"})
    win.action_user_parameters()
    assert win.doc.params == {"width": "30"}
    assert win.doc.result.volume == pytest.approx(240.0, rel=1e-6)


def test_change_parameters_exposes_fx_field(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    box = _win_box(win)
    box.bindings = {"dx": "width"}
    seen = []

    def fake_ask(parent, title, fields, *a, **k):
        seen.append(fields)
        return None                                    # user cancelled

    monkeypatch.setattr(cmddialog, "ask", fake_ask)
    win.action_change_params(box)
    fld = seen[0]
    fx = [f for f in fld if f["kind"] == "text" and f["key"] == "fx_dx"]
    assert len(fx) == 1 and fx[0]["default"] == "width"


def test_fx_binding_beats_direct_number(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    box = _win_box(win)
    monkeypatch.setattr(win.doc, "params", {"width": "30"}, raising=False)
    base = {"dims": None, "dx": 999.0, "dy": 4.0, "dz": 2.0}
    # bind the lever: the number field fights the formula and LOSES
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: dict(base, **{"fx_dx": "= width"}))
    win.action_change_params(box)
    qapp.processEvents()
    assert box.bindings.get("dx") == "width"
    assert win.doc.result.volume == pytest.approx(240.0, rel=1e-6)
    # an invalid formula is refused, the old state survives
    bad = dict(base, **{"fx_dx": "width +*"})
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: bad)
    win.action_change_params(box)
    assert box.bindings.get("dx") == "width"
    # clearing the fx field releases the lever to the plain number
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: dict(base, **{"fx_dx": ""}))
    win.action_change_params(box)
    qapp.processEvents()
    assert "dx" not in box.bindings
    assert win.doc.result.volume == pytest.approx(999.0 * 8.0, rel=1e-6)
