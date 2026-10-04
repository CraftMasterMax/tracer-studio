"""M5: editable dimension labels on canvas, constrained-state coloring,
undo guard while sketching."""
import pytest

pytest.importorskip("PySide6")

import numpy as np                                  # noqa: E402
from PySide6.QtCore import Qt                       # noqa: E402
from PySide6.QtTest import QTest                    # noqa: E402
from PySide6.QtWidgets import (QApplication,        # noqa: E402
                               QInputDialog)

from tracer.core.sketch.constraints import Distance, Fixed, Radius  # noqa: E402
from tracer.core.document import ExtrudeFeature      # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


def _rect_with_dims(win, with_circle=True):
    """40x20 rect, corner fixed, bottom edge driven by a Distance dim
    (+ optional circle with a radius dim inside it)."""
    win.new_document()
    win.action_new_sketch()
    m = win.sketch.model
    p0 = m.point(0, 0)
    p1 = m.point(40, 20)
    m.add_rect(p0, p1)
    bottom = m.sketch.lines[0]
    m.constrain(Fixed(p0, x=0.0, y=0.0))
    m.constrain(Distance(bottom.a, bottom.b, 40.0))
    if with_circle:
        cen = m.point(20, 10)
        circ = m.add_circle(cen, 6)
        m.constrain(Radius(circ, 6.0))
    return m


def test_dimension_labels_appear_and_edit_drives_solid(win, qapp, monkeypatch):
    _rect_with_dims(win, with_circle=False)
    answers = [5.0]                       # extrude height on first finish
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (answers.pop(0), True)))
    win.sketch.finish()
    qapp.processEvents()
    feats = [f for f in win.doc.features
             if isinstance(f, ExtrudeFeature) and f.sketch]
    assert len(feats) == 1
    assert win.doc.result.volume == pytest.approx(40 * 20 * 5, rel=1e-2)

    # reopen the sketch: labels must be hittable
    win.edit_sketch(feats[0])
    cv = win.sketch
    cv.grab()                             # paint -> fills _dim_hits
    kinds = [type(c).__name__ for _, c in cv._dim_hits]
    assert "Distance" in kinds

    rect, dim = next((r, c) for r, c in cv._dim_hits
                     if isinstance(c, Distance))
    answers.append(60.0)                  # new width via label double-click
    QTest.mouseDClick(cv, Qt.LeftButton, Qt.NoModifier,
                      rect.center().toPoint(), 10)
    qapp.processEvents()
    assert dim.value == pytest.approx(60.0)

    cv.finish()                           # update solid; height kept at 5
    qapp.processEvents()
    assert len(win.doc.features) == 1
    assert win.doc.result.volume == pytest.approx(60 * 20 * 5, rel=1e-2)


def test_radius_label_edit(win, qapp, monkeypatch):
    _rect_with_dims(win)
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (5.0, True)))
    win.sketch.finish()
    qapp.processEvents()
    feat = win.doc.features[0]
    v_hollow = win.doc.result.volume      # plate minus R6 hole
    win.edit_sketch(feat)
    cv = win.sketch
    cv.grab()
    rect, rad = next((r, c) for r, c in cv._dim_hits
                     if isinstance(c, Radius))
    vals = iter([9.0])
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (next(vals), True)))
    QTest.mouseDClick(cv, Qt.LeftButton, Qt.NoModifier,
                      rect.center().toPoint(), 10)
    qapp.processEvents()
    assert rad.value == pytest.approx(9.0)
    cv.finish()
    qapp.processEvents()
    v_bigger = win.doc.result.volume
    assert v_bigger < v_hollow            # bigger hole removes more material
    assert v_hollow - v_bigger == pytest.approx(np.pi * (81 - 36) * 5,
                                                rel=5e-2)


def test_entities_accent_when_underconstrained(win, qapp):
    """The painter colors entities by _last_result; verify the flag flips."""
    win.new_document()
    win.action_new_sketch()
    m = win.sketch.model
    a, b = m.point(0, 0), m.point(30, 10)
    m.add_line(a, b)
    win.sketch._solve()
    r = win.sketch._last_result
    assert r is not None and r.dof > 0
    win.sketch.grab()
    m.constrain(Fixed(a, x=0.0, y=0.0))
    m.constrain(Fixed(b, x=30.0, y=10.0))
    win.sketch._solve()
    r = win.sketch._last_result
    assert r is not None and r.converged and r.dof == 0
    win.sketch.grab()


def test_undo_guarded_while_sketching(win, qapp):
    win.new_document()
    win.doc.add_plate("p", 10, 10, 1)
    win.recompute()
    win._capture()
    win.action_new_sketch()
    assert win.stack.currentWidget() is win._sketch_page
    n = len(win._undo)
    win.undo()
    assert len(win._undo) == n, "undo fired inside the sketch editor"
    win.stack.setCurrentWidget(win.viewport)
    win.undo()
    assert len(win._undo) == n - 1
