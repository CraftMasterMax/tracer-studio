"""Sketcher interaction: real mouse events into the canvas, live solve,
constraint toggles, extrude wiring in MainWindow."""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402
from conftest import tree_texts  # noqa: E402

from tracer.core.sketch.constraints import (Distance, Fixed,
                                           Horizontal)  # noqa: E402
from tracer.core.sketch.entities import Line, Point  # noqa: E402
from tracer.core.sketch.model import SketchModel  # noqa: E402
from tracer.ui.mainwindow import MainWindow  # noqa: E402
from tracer.ui.renderer import SceneRenderer  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False       # close guard would open a modal
    w.close()


def _press(canvas, button, wx, wy, modifiers=Qt.NoModifier):
    s = canvas.w2s(wx, wy)
    QTest.mousePress(canvas, button, modifiers, s.toPoint(), 10)


def _move(canvas, wx, wy):
    s = canvas.w2s(wx, wy)
    QTest.mouseMove(canvas, s.toPoint(), 10)


def _release(canvas, button, wx, wy):
    s = canvas.w2s(wx, wy)
    QTest.mouseRelease(canvas, button, Qt.NoModifier, s.toPoint(), 10)


def test_rect_tool_drag_creates_constrained_rect(win, qapp):
    win.action_new_sketch()
    canvas = win.sketch
    _press(canvas, Qt.LeftButton, 0, 0)
    _move(canvas, 40, 20)
    _release(canvas, Qt.LeftButton, 40, 20)
    qapp.processEvents()
    sk = canvas.model.sketch
    assert len(sk.lines) == 4
    assert sum(isinstance(c, Horizontal) for c in sk.constraints) == 2
    loops, warns = canvas.model.to_loops()
    assert len(loops) == 1
    assert loops[0]["area"] == pytest.approx(800)


def test_line_tool_with_snap_closes_chain(win, qapp):
    win.action_new_sketch()
    canvas = win.sketch
    canvas.set_tool("line")
    corners = [(0, 0), (30, 0), (30, 30), (0, 30), (0, 0)]
    for x, y in corners:
        _press(canvas, Qt.LeftButton, x, y)
        qapp.processEvents()
    sk = canvas.model.sketch
    assert len(sk.lines) == 4
    # snapping reused the shared start point: closed loop, no warnings
    loops, warns = canvas.model.to_loops()
    assert len(loops) == 1 and not warns
    # clicks round to pixels: at scale=4 px/mm that's +/-0.125 mm of jitter
    assert loops[0]["area"] == pytest.approx(900, rel=0.01)


def test_drag_respects_distance_constraint(win, qapp):
    win.action_new_sketch()
    canvas = win.sketch
    m = canvas.model
    p0, p1 = m.point(0, 0), m.point(50, 0)
    ln = m.add_line(p0, p1)
    m.constrain(Distance(p0, p1, 50.0))
    m.solve()
    # grab the free end and yank it far away: length must hold
    _press(canvas, Qt.LeftButton, 50, 0)
    _move(canvas, 200, 120)
    qapp.processEvents()
    _release(canvas, Qt.LeftButton, 200, 120)
    assert math.hypot(p1.x - p0.x, p1.y - p0.y) == pytest.approx(50.0, abs=1e-4)
    assert canvas._last_result is not None


def test_h_toggle_key_on_selected_line(win, qapp):
    win.action_new_sketch()
    canvas = win.sketch
    m = canvas.model
    a, b = m.point(0, 0), m.point(20, 7)
    ln = m.add_line(a, b)
    m.solve()
    canvas._sel = [ln]
    QTest.keyClick(canvas, Qt.Key_H)
    qapp.processEvents()
    assert b.y == pytest.approx(a.y, abs=1e-6)
    QTest.keyClick(canvas, Qt.Key_H)      # untoggle
    qapp.processEvents()
    assert not any(isinstance(c, Horizontal) for c in m.sketch.constraints)


def test_circle_tool_and_finish_extrudes_into_document(win, qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (6.0, True)))
    v_before = win.doc.result.volume
    win.action_new_sketch()
    canvas = win.sketch
    canvas.set_tool("circle")
    _press(canvas, Qt.LeftButton, 100, 100)
    _move(canvas, 100 + 10, 100)
    _release(canvas, Qt.LeftButton, 120, 100)
    qapp.processEvents()
    assert len(canvas.model.sketch.circles) == 1
    canvas.finish()
    qapp.processEvents()
    v_after = win.doc.result.volume
    assert v_after > v_before + math.pi * 100 * 6 * 0.95
    assert "Extruded" in win.status.currentMessage()
    assert any("Sketch" in t for t in tree_texts(win))


def test_undo_redo_extrude_cycle(win, qapp, monkeypatch):
    n0 = len(win.doc.features)
    v0 = win.doc.result.volume
    win._capture()
    win.doc.add_cylinder("undo-me", radius=2, height=5, center=(70, 20))
    win.recompute()
    assert len(win.doc.features) == n0 + 1
    win.undo()
    assert len(win.doc.features) == n0
    assert win.doc.result.volume == pytest.approx(v0)
    win.redo()
    assert len(win.doc.features) == n0 + 1
    assert win.doc.result.volume > v0


def test_sketch_pixels_drawn(win, qapp):
    win.action_new_sketch()
    canvas = win.sketch
    m = canvas.model
    p0, p1 = m.point(0, 0), m.point(30, 20)
    m.add_rect(p0, p1)
    canvas.fit_view()
    qapp.processEvents()
    img = canvas.grab().toImage()
    from PySide6.QtGui import QImage
    img = img.convertToFormat(QImage.Format_RGBA8888)
    buf = np.frombuffer(img.constBits(), np.uint8,
                        img.sizeInBytes()).reshape(img.height(), img.width(), 4)
    lum = buf[:, :, :3].astype(int).mean(axis=2)
    # geometry strokes (FG #e8eaed) on dark panel
    assert (lum > 150).sum() > 300, "sketch geometry not painted"
    assert (lum > 150).sum() < lum.size * 0.5, "canvas flooded"


def test_solver_pin_does_not_eat_user_constraints():
    """Regression: pin removal after solve must match by IDENTITY — a user
    Fixed constraint comparing equal to a temporary pin used to vanish."""
    m = SketchModel()
    p = m.point(1.0, 1.0)
    q = m.point(5.0, 5.0)
    m.constrain(Fixed(p, x=1.0, y=1.0))
    before = len(m.sketch.constraints)
    for _ in range(3):
        m.solve(pins=[p])
    assert len(m.sketch.constraints) == before
    m.solve(pins=[p, q])
    assert len(m.sketch.constraints) == before


def test_new_sketch_guard_protects_work(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    win.action_new_sketch()
    m = win.sketch.model
    p = m.point(0, 0)
    m.add_rect(p, m.point(10, 10))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.No))
    win.action_new_sketch()          # decline discard
    assert win.sketch.model is m
    assert len(m.sketch.lines) == 4
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    win.action_new_sketch()          # accept discard -> fresh model
    assert win.sketch.model is not m
    assert len(win.sketch.model.sketch.lines) == 0


def test_extrude_from_two_region_sketch(win, qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (2.0, True)))
    n_before = len(win.doc.features)
    win.action_new_sketch()
    m = win.sketch.model
    p = m.point(0, 0); m.add_rect(p, m.point(10, 10))
    p = m.point(30, 0); m.add_rect(p, m.point(35, 10))
    win.sketch.finish()
    qapp.processEvents()
    assert len(win.doc.features) == n_before + 2
