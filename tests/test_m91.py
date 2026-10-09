"""M91 — Configurations: named parameter sets on a dropdown.

Fusion's Configurations turn one model into a family: a Small and a
Large row in a table, each overriding sheet names, and a switcher that
rebuilds the solid.  M81 built the sheet, M89 wired dimensions to it —
this is the third leg: `Document.configs` maps a config name to
{parameter: formula}, the active name overlays the base sheet at
resolve time (plain override, no new evaluation math), and the whole
thing serializes with the file.

Sheet grammar for the dialog (M81 precedent — text, not a grid):

    Small: width = 20, height = 10
    Large: width = 50           # comments allowed

Honest scope: one active configuration at a time (Fusion shows several
in an assembly — later); overrides are per NAME and must name real
sheet parameters or a base-legal formula, and switching mid-sketch
edit only lands on the next recompute like any sheet edit.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from tracer.core import params                                         # noqa: E402
from tracer.core.document import Document, ExtrudeFeature              # noqa: E402
from tracer.core.sketch.constraints import (Distance, Fixed,          # noqa: E402
                                            Horizontal, Vertical)
from tracer.core.sketch.model import SketchModel, model_to_dict       # noqa: E402
from tracer.core.sketch.profile import regions


def _bound_rect_doc():
    """The M89 rig: a 30x20 rect whose bottom edge is bound to
    `width`, extruded 5 mm — so a config override moves the solid."""
    d = Document(title="cfg")
    m = SketchModel(plane="XY")
    a, b = m.point(0, 0), m.point(30, 0)
    c, e = m.point(30, 20), m.point(0, 20)
    l1, l2 = m.add_line(a, b), m.add_line(b, c)
    l3, l4 = m.add_line(c, e), m.add_line(e, a)
    sk = m.sketch
    sk.constraints.extend([Horizontal(l1), Horizontal(l3),
                           Vertical(l2), Vertical(l4),
                           Fixed(a, x=a.x, y=a.y)])
    dim = Distance(a, b, 30.0)
    sk.constraints.append(dim)
    i = sk.constraints.index(dim)
    m.dim_exprs[i] = {"e": "width", "t": "D"}
    loops, _w = m.to_loops()
    regs = regions(loops)
    d.params = {"width": "30", "depth": "height * 1.5", "height": "20"}
    d.features.append(ExtrudeFeature(
        name="Plate", outer=regs[0]["points"], holes=[], height=5.0,
        plane="XY", placement=(0.0, 0.0, 0.0),
        sketch=model_to_dict(m), sid=m.sid, region=0))
    return d


# ----------------------------------------------------------------- parser

def test_parse_configs_grammar():
    got = params.parse_configs(
        "Small: width = 20, height = 10\n"
        "# comment line\n"
        "Large: width = 50\n")
    assert got == {"Small": {"width": "20", "height": "10"},
                   "Large": {"width": "50"}}


def test_parse_configs_refuses_bad_lines():
    with pytest.raises(params.ParamError):
        params.parse_configs("Small width = 20")       # no colon
    with pytest.raises(params.ParamError):
        params.parse_configs("Small: width")           # no equals


# ------------------------------------------------------------------- core

def test_active_config_overrides_the_solid():
    d = _bound_rect_doc()
    assert d.recompute().volume == pytest.approx(30 * 20 * 5, rel=1e-3)
    d.configs = {"Small": {"width": "18"}}
    d.active_config = "Small"
    assert d.recompute().volume == pytest.approx(18 * 20 * 5, rel=1e-3)
    d.active_config = None
    assert d.recompute().volume == pytest.approx(30 * 20 * 5, rel=1e-3)


def test_override_flows_through_sheet_formulas():
    d = _bound_rect_doc()                       # depth = height * 1.5
    d.configs = {"Tall": {"height": "40"}}
    d.active_config = "Tall"
    vals = params.resolve(d.merged_sheet())
    assert vals["depth"] == pytest.approx(60.0)  # base formula followed


def test_config_formula_may_reference_base_names():
    d = _bound_rect_doc()
    d.configs = {"Double": {"width": "height * 2"}}
    d.active_config = "Double"
    assert d.recompute().volume == pytest.approx(40 * 20 * 5, rel=1e-3)


def test_unknown_active_config_is_ignored():
    d = _bound_rect_doc()
    d.configs = {"Small": {"width": "18"}}
    d.active_config = "Ghost"
    assert d.recompute().volume == pytest.approx(30 * 20 * 5, rel=1e-3)


def test_configs_round_trip_through_the_file():
    d = _bound_rect_doc()
    d.configs = {"Small": {"width": "18"}}
    d.active_config = "Small"
    back = Document.from_dict(d.to_dict())
    assert back.configs == {"Small": {"width": "18"}}
    assert back.active_config == "Small"
    assert back.recompute().volume == pytest.approx(18 * 20 * 5, rel=1e-3)


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


def test_configurations_verb_parses_and_switches(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    win.new_document()
    win.doc.params = {"width": "30"}
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda *a, **k: {"sheet": "Small: width = 18", "active": "Small"})
    win.action_configurations()
    qapp.processEvents()
    assert win.doc.configs == {"Small": {"width": "18"}}
    assert win.doc.active_config == "Small"
    assert "Small" in win.status.currentMessage()


def test_switcher_moves_the_solid(win, qapp):
    win.new_document()
    d = win.doc
    m = SketchModel(plane="XY")
    a, b = m.point(0, 0), m.point(30, 0)
    c, e = m.point(30, 20), m.point(0, 20)
    l1, l2 = m.add_line(a, b), m.add_line(b, c)
    l3, l4 = m.add_line(c, e), m.add_line(e, a)
    sk = m.sketch
    sk.constraints.extend([Horizontal(l1), Horizontal(l3),
                           Vertical(l2), Vertical(l4),
                           Fixed(a, x=a.x, y=a.y)])
    dim = Distance(a, b, 30.0)
    sk.constraints.append(dim)
    i = sk.constraints.index(dim)
    m.dim_exprs[i] = {"e": "width", "t": "D"}
    loops, _w = m.to_loops()
    regs = regions(loops)
    d.params = {"width": "30"}
    d.features.append(ExtrudeFeature(
        name="Plate", outer=regs[0]["points"], holes=[], height=5.0,
        plane="XY", placement=(0.0, 0.0, 0.0),
        sketch=model_to_dict(m), sid=m.sid, region=0))
    d.configs = {"Small": {"width": "18"}}
    win.recompute()
    qapp.processEvents()
    v0 = d.result.volume
    win._set_active_config("Small")
    qapp.processEvents()
    assert d.result.volume == pytest.approx(18 * 20 * 5, rel=1e-3)
    assert d.result.volume < v0
    win._set_active_config(None)
    qapp.processEvents()
    assert d.result.volume == pytest.approx(v0, rel=1e-6)
