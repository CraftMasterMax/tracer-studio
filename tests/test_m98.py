"""M98 — the sketcher speaks diameter (Ø), like Fusion.

A circle drawn is a hole to be drilled, and drill bits are sold by
DIAMETER. Until now every circle dimension read "R 12.00" and asked
for a radius; Fusion puts a Ø on the chip, asks for the diameter in
the dialog, takes the typed number as a diameter — and so does
Tracer. The engineering stays honest: the solver's Radius constraint
is untouched (radius is its native tongue — only the UI translates),
the chip text, the creation dialogs, the double-click editor, the
M89 fx binding and the M90 type-in all switch to diameter TOGETHER,
and fx bindings stamped under the old radius meaning ("R" on a
circle) idle loudly instead of silently doubling the hole. Arcs keep
their R — an arc's radius is what a fillet gauge measures.

Honest scope: circles (the closed kind) only; serialization keeps the
radius value ("t":"R" entries don't move — files stay byte-honest);
inch documents scale diameters like any length (the fx layer halves
after scaling).
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402

from tracer.core.sketch.constraints import Radius            # noqa: E402
from tracer.core.sketch.model import (SketchModel,           # noqa: E402
                                      _dim_tag)


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
        w._discard_guard = lambda: True
        w.close()
        r.ctx.release()
    except Exception:
        raise


@pytest.fixture
def sketch(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    cv.set_grid_snap(False)
    return cv


# ---------------------------------------------------------- tag & text

def test_circle_and_arc_tags_split():
    m = SketchModel()
    c = m.add_circle(m.point(0.0, 0.0), 5.0)
    ar = m.sketch.arc(m.point(0.0, 0.0), m.point(5.0, 3.0),
                      m.point(10.0, 0.0))
    assert _dim_tag(Radius(c, 5.0)) == "DIA"
    assert _dim_tag(Radius(ar, 7.0)) == "R"      # arcs keep R


def test_chip_text_reads_diameter_for_circles(sketch):
    m = sketch.model
    c = m.add_circle(m.point(0.0, 0.0), 12.0)
    m.constrain(Radius(c, 12.0))
    txt = sketch._dim_text(m.sketch.constraints[-1])
    assert txt == "\u00d8 24.00"


def test_arc_chip_still_reads_radius(sketch):
    m = sketch.model
    ar = m.sketch.arc(m.point(0.0, 0.0), m.point(5.0, 3.0),
                      m.point(10.0, 0.0))
    m.constrain(Radius(ar, 9.0))
    txt = sketch._dim_text(m.sketch.constraints[-1])
    assert txt == "R 9.00"


# ---------------------------------------------------------------- act_dim

def test_act_dim_on_a_circle_asks_diameter(sketch, qapp, monkeypatch):
    from tracer.ui.cmddialog import Shell
    m = sketch.model
    c = m.add_circle(m.point(0.0, 0.0), 7.0)
    sketch._sel = [c]
    seen = {}

    def fake(parent, title, label, cur, lo, hi, dec):
        seen["label"], seen["cur"] = label, cur
        return 30.0, True
    monkeypatch.setattr(Shell, "getDouble", staticmethod(fake))
    sketch.act_dim()
    assert "Diameter" in seen["label"]
    assert seen["cur"] == pytest.approx(14.0)         # the chip's number
    cons = [x for x in m.sketch.constraints if isinstance(x, Radius)]
    assert cons[0].value == pytest.approx(15.0)       # diameter 30 -> r 15


# ------------------------------------------------------------------ edit

def test_double_click_edit_asks_and_stores_diameter(sketch, qapp,
                                                    monkeypatch):
    from tracer.ui import cmddialog
    m = sketch.model
    c = m.add_circle(m.point(0.0, 0.0), 4.0)
    m.constrain(Radius(c, 4.0))
    captured = {}

    def fake_ask(parent, title, fields):
        captured["label"] = fields[0]["label"]
        captured["default"] = fields[0]["default"]
        return {"val": 18.0, "fx": ""}
    monkeypatch.setattr(cmddialog, "ask", fake_ask)
    sketch._edit_dim(m.sketch.constraints[-1])
    assert "Diameter" in captured["label"]
    assert captured["default"] == pytest.approx(8.0)   # shows Ø 8
    assert m.sketch.constraints[-1].value == pytest.approx(9.0)


# -------------------------------------------------------------------- fx

def test_fx_binding_on_a_circle_drives_diameter(sketch, qapp,
                                                monkeypatch):
    from tracer.ui import cmddialog
    m = sketch.model
    c = m.add_circle(m.point(0.0, 0.0), 4.0)
    m.constrain(Radius(c, 4.0))
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"val": 8.0, "fx": "bore"})
    monkeypatch.setattr(sketch, "_params_provider",
                        lambda: ({"bore": 50.0}, 1.0))
    sketch._edit_dim(m.sketch.constraints[-1])
    i = len(m.sketch.constraints) - 1
    assert m.dim_exprs[i]["t"] == "DIA"
    assert m.sketch.constraints[-1].value == pytest.approx(25.0)  # Ø 50 / 2
    m.apply_dim_params({"bore": 30.0}, scale=1.0)
    assert m.sketch.constraints[-1].value == pytest.approx(15.0)


def test_old_radius_tag_on_a_circle_idles_loudly():
    m = SketchModel()
    c = m.add_circle(m.point(0.0, 0.0), 4.0)
    m.constrain(Radius(c, 4.0))
    i = m.sketch.constraints.index(m.sketch.constraints[-1])
    m.dim_exprs[i] = {"e": "bore", "t": "R"}      # stamped pre-M98
    warns = m.apply_dim_params({"bore": 50.0})
    assert warns and "type changed" in warns[0]
    assert m.sketch.constraints[-1].value == pytest.approx(4.0)


# ---------------------------------------------------------------- type-in

def _click(cv, qapp, x, y):
    sp = cv.w2s(x, y).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, sp)
    qapp.processEvents()
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, sp)
    qapp.processEvents()


def test_typed_number_after_a_circle_is_a_diameter(sketch, qapp):
    sketch.set_tool("circle")
    _click(sketch, qapp, 0, 0)
    _click(sketch, qapp, 5, 0)                    # rim click mints r=5
    QTest.keyClicks(sketch, "24")
    QTest.keyClick(sketch, Qt.Key.Key_Return)
    qapp.processEvents()
    cons = [c for c in sketch.model.sketch.constraints
            if isinstance(c, Radius)]
    assert cons[0].value == pytest.approx(12.0)   # Ø 24 = r 12
    assert sketch.model.sketch.circles[0].r == pytest.approx(12.0,
                                                            rel=1e-6)


def test_typed_number_after_an_arc_stays_radius(sketch, qapp):
    sketch.set_tool("arc")
    _click(sketch, qapp, 0, 0)
    _click(sketch, qapp, 5, 3)
    _click(sketch, qapp, 10, 0)
    QTest.keyClicks(sketch, "9")
    QTest.keyClick(sketch, Qt.Key.Key_Return)
    qapp.processEvents()
    cons = [c for c in sketch.model.sketch.constraints
            if isinstance(c, Radius)]
    assert cons[0].value == pytest.approx(9.0)    # arcs speak R
