"""M17: radius dimensioning of arcs — the D tool on 3-point arcs."""
import json
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                   # noqa: E402
from PySide6.QtTest import QTest                                # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog        # noqa: E402

from forma.core.sketch.constraints import Coincident, Radius    # noqa: E402
from forma.core.sketch.entities import Arc, curve_radius        # noqa: E402
from forma.core.sketch.model import (SketchModel,               # noqa: E402
                                     model_from_dict, model_to_dict)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    from forma.ui.mainwindow import MainWindow
    from forma.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (10.0, True)))
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


def _click(cv, x, y, button=Qt.LeftButton):
    p = cv.w2s(x, y).toPoint()
    QTest.mousePress(cv, button, Qt.NoModifier, p, 10)
    QTest.mouseRelease(cv, button, Qt.NoModifier, p, 10)


def _model_arc(m, ax=0, ay=0, mx=10, my=10, bx=20, by=0):
    a, mi, b = m.point(ax, ay), m.point(mx, my), m.point(bx, by)
    return m.sketch.arc(a, mi, b), a, mi, b


# ---- core --------------------------------------------------------------------
def test_radius_constraint_drives_arc():
    m = SketchModel()
    ar, *_ = _model_arc(m)              # natural r = 10
    assert curve_radius(ar) == pytest.approx(10.0)
    m.constrain(Radius(ar, 15.0))
    res = m.solve()
    assert res.converged
    assert curve_radius(ar) == pytest.approx(15.0, rel=1e-4)
    # still a through-arc: all three defining points lie on the circle
    c, r = ar.circle()
    for p in (ar.a, ar.m, ar.b):
        assert math.hypot(p.x - c[0], p.y - c[1]) == pytest.approx(r, rel=1e-4)


def test_arc_radius_with_coincident_chain():
    # line -> arc sharing an endpoint, plus the radius: classic obround leg
    m = SketchModel()
    p0 = m.point(0, 0)
    p1 = m.point(20, 0)
    ln = m.sketch.line(p0, p1)
    top = m.point(30, 8)
    end = m.point(20, 16)
    ar = m.sketch.arc(p1, top, end)
    m.constrain(Coincident(p0, m.point(0, 16)))
    m.constrain(Radius(ar, 8.0))
    res = m.solve()
    assert res.converged
    assert curve_radius(ar) == pytest.approx(8.0, rel=1e-3)


def test_toggle_radius_on_arc_uses_current_value():
    m = SketchModel()
    ar, *_ = _model_arc(m)
    m.toggle(Radius, (ar,))
    c = [x for x in m.sketch.constraints if isinstance(x, Radius)]
    assert len(c) == 1 and c[0].curve is ar
    assert c[0].value == pytest.approx(curve_radius(ar))


def test_arc_radius_serialization_roundtrip():
    m = SketchModel()
    circ = m.add_circle(m.point(50, 50), 6.0)
    ar, *_ = _model_arc(m)
    m.constrain(Radius(circ, 6.0))
    m.constrain(Radius(ar, 15.0))
    d = json.loads(json.dumps(model_to_dict(m)))
    rs = [c for c in d["constraints"] if c["t"] == "R"]
    assert len(rs) == 2
    assert any("c" in r for r in rs) and any("a" in r for r in rs)
    m2 = model_from_dict(d)
    vals = sorted(c.value for c in m2.sketch.constraints
                  if isinstance(c, Radius))
    kinds = {type(c.curve).__name__ for c in m2.sketch.constraints
             if isinstance(c, Radius)}
    assert vals == [6.0, 15.0] and kinds == {"Circle", "Arc"}


def test_legacy_circle_radius_dict_still_loads():
    """Radius dims saved before M17 carry only the 'c' key."""
    d = {"name": "s", "plane": "XY",
         "points": [[0, 0], [5, 5], [10, 0], [50, 50]],
         "lines": [],
         "circles": [[3, 6.0]],
         "arcs": [[0, 1, 2, 0]],
         "constraints": [{"t": "R", "c": 0, "v": 7.5}]}
    m = model_from_dict(d)
    c = m.sketch.constraints[0]
    assert isinstance(c, Radius) and c.curve is m.sketch.circles[0]
    assert c.value == 7.5


# ---- canvas --------------------------------------------------------------------
def test_canvas_dimension_tool_on_arc(win, qapp, monkeypatch):
    win.new_document(); win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("arc")
    _click(cv, 0, 0); _click(cv, 20, 0); _click(cv, 10, 6)
    qapp.processEvents()
    ar = cv.model.sketch.arcs[0]
    cv.set_tool("select")
    cv._sel = [ar]
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (7.5, True)))
    cv.act_dim()
    qapp.processEvents()
    dims = [c for c in cv.model.sketch.constraints
            if isinstance(c, Radius)]
    assert len(dims) == 1 and dims[0].curve is ar
    assert curve_radius(ar) == pytest.approx(7.5, rel=1e-3)


def test_canvas_badge_edit_and_arc_anchor(win, qapp, monkeypatch):
    win.new_document(); win.action_new_sketch()
    cv = win.sketch
    cv.set_tool("arc")
    _click(cv, 0, 0); _click(cv, 20, 0); _click(cv, 10, 6)
    qapp.processEvents()
    ar = cv.model.sketch.arcs[0]
    cv._sel = [ar]
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (12.0, True)))
    cv.act_dim()
    con = cv.model.sketch.constraints[-1]
    # double-click editing path (badge hit already covered in m8)
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (9.0, True)))
    cv._edit_dim(con)
    qapp.processEvents()
    assert con.value == 9.0
    assert curve_radius(ar) == pytest.approx(9.0, rel=1e-3)
    # anchor sits outside the arc bulge, not at the circumcircle top
    pos = cv._radius_pos(ar)
    bulge = cv.w2s(ar.m.x, ar.m.y)
    assert math.hypot(pos.x() - bulge.x(), pos.y() - bulge.y()) <= 40.0
