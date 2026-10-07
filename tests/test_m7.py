"""M7: construction geometry, perpendicular/equal constraints, 2-point dims."""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                         # noqa: E402
from PySide6.QtTest import QSignalSpy, QTest          # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402

from tracer.core.sketch.constraints import (Distance, Equal, Fixed,  # noqa: E402
                                           Perpendicular)
from tracer.ui.cmddialog import Shell                    # noqa: E402
from tracer.core.sketch.model import (SketchModel,      # noqa: E402
                                     model_from_dict, model_to_dict)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _box(m):
    a, b, c, d = (m.point(0, 0), m.point(40, 0),
                  m.point(40, 20), m.point(0, 20))
    for p, q in ((a, b), (b, c), (c, d), (d, a)):
        m.add_line(p, q)
    diag = m.add_line(a, c)
    return a, b, c, d, diag


def test_construction_lines_do_not_bound_profiles():
    m = SketchModel()
    _box(m)
    assert len(m.to_loops()[0]) == 2            # diagonal splits the rect
    m.sketch.lines[-1].construction = True
    loops = m.to_loops()[0]
    assert len(loops) == 1 and loops[0]["area"] == pytest.approx(800)


def test_construction_and_two_line_constraints_roundtrip():
    m = SketchModel()
    a, b, c, d, diag = _box(m)
    diag.construction = True
    m.constrain(Perpendicular(m.sketch.lines[0], m.sketch.lines[1]))
    m.constrain(Equal(m.sketch.lines[0], m.sketch.lines[2]))
    m2 = model_from_dict(model_to_dict(m))
    assert m2.sketch.lines[-1].construction          # flag survives
    assert not m2.sketch.lines[0].construction
    kinds = {type(x).__name__ for x in m2.sketch.constraints}
    assert {"Perpendicular", "Equal"} <= kinds


def test_toggle_actually_adds_two_line_constraints():
    m = SketchModel()
    l1 = m.add_line(m.point(0, 0), m.point(30, 0))
    l2 = m.add_line(m.point(0, 0), m.point(10, 5))
    assert m.toggle(Equal, (l1, l2)) is True
    assert any(isinstance(c, Equal) for c in m.sketch.constraints)
    assert m.toggle(Equal, (l1, l2)) is False
    assert not any(isinstance(c, Equal) for c in m.sketch.constraints)


# ---- canvas wiring ------------------------------------------------------------
@pytest.fixture
def canvas(qapp):
    from tracer.ui.sketcheditor import SketchCanvas
    cv = SketchCanvas()
    cv.resize(800, 600)
    cv.show()
    qapp.processEvents()
    yield cv
    cv.close()


def test_key_X_toggles_construction_and_finish_uses_it(canvas, qapp):
    m = SketchModel()
    *_, diag = _box(m)
    canvas.set_model(m)
    canvas._sel = [diag]
    QTest.keyPress(canvas, Qt.Key_X)             # M113: Fusion's toggle key
    assert diag.construction
    spy = QSignalSpy(canvas.profiles_ready)
    canvas.finish()
    assert spy.count() == 1
    assert len(spy.at(0)[0]) == 1                   # single 800 mm² profile


def test_key_P_perpendicular_solves(canvas, qapp):
    m = SketchModel()
    a = m.point(0, 0)
    m.constrain(Fixed(a, x=0.0, y=0.0))
    l1 = m.add_line(a, m.point(30, 0))
    l2 = m.add_line(a, m.point(28, 8))              # clearly not 90 deg
    canvas.set_model(m)
    canvas._sel = [l1, l2]
    QTest.keyPress(canvas, Qt.Key_P, Qt.ShiftModifier)   # M113: perp took
    assert any(isinstance(c, Perpendicular) for c in m.sketch.constraints)  # the Shift
    d1 = np.array([l1.b.x - l1.a.x, l1.b.y - l1.a.y])
    d2 = np.array([l2.b.x - l2.a.x, l2.b.y - l2.a.y])
    assert abs(float(d1 @ d2) / (np.linalg.norm(d1) * np.linalg.norm(d2))) < 1e-6


def test_key_Q_equal_lengths(canvas, qapp):
    m = SketchModel()
    l1 = m.add_line(m.point(0, 0), m.point(30, 0))
    l2 = m.add_line(m.point(0, 10), m.point(11, 10))
    for e in (l1.a, l1.b, l2.a):
        m.constrain(Fixed(e, x=e.x, y=e.y))
    canvas.set_model(m)
    canvas._sel = [l1, l2]
    QTest.keyPress(canvas, Qt.Key_Q)
    assert any(isinstance(c, Equal) for c in m.sketch.constraints)
    L1 = math.hypot(l1.b.x - l1.a.x, l1.b.y - l1.a.y)
    L2 = math.hypot(l2.b.x - l2.a.x, l2.b.y - l2.a.y)
    assert L1 == pytest.approx(L2, rel=1e-6)


def test_dimension_between_two_points(canvas, qapp, monkeypatch):
    m = SketchModel()
    p, q = m.point(0, 0), m.point(30, 0)
    m.add_line(p, q)
    m.constrain(Fixed(p, x=0.0, y=0.0))
    canvas.set_model(m)
    canvas._sel = [p, q]
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *a, **k: (50.0, True)))
    QTest.keyPress(canvas, Qt.Key_D)
    dims = [c for c in m.sketch.constraints if isinstance(c, Distance)]
    assert len(dims) == 1 and dims[0].value == 50.0
    assert math.hypot(q.x - p.x, q.y - p.y) == pytest.approx(50.0, rel=1e-6)
