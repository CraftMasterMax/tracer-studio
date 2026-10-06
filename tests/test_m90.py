"""M90 — type a number right after drawing (Fusion muscle memory).

Draw a line, hit 4-0-Enter, and the line IS 40 mm — no dialog, no
toolbar hunt. Fusion dimensions at the speed of thought and Tracer now
keeps pace: line, circle, arc and rectangle creation leave a "pending
type-in" armed for a few keystrokes; digits buffer into a small chip on
the canvas (Fusion's little white box), Enter mints the same Distance/
Radius constraint act_dim would (including its remove_last habit, so
re-typing never stacks), Esc or any other action abandons it.

Rectangles take TWO numbers, like Fusion: width Enter height Enter,
landing on the auto-H/V bottom and side edges the rect tool mints.

Honest scope: plain numbers only (fx formulas still live in the
dimension dialog); millimetres, the editor's native tongue.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                          # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap    # noqa: E402
from PySide6.QtTest import QTest                       # noqa: E402
from PySide6.QtWidgets import QApplication             # noqa: E402

from tracer.core.sketch.constraints import Distance, Radius   # noqa: E402


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


def _click(cv, qapp, x, y):
    """Canonical paired press+release at world (x, y)."""
    sp = cv.w2s(x, y).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, sp)
    qapp.processEvents()
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, sp)
    qapp.processEvents()


def _type(cv, qapp, text, enter=True):
    QTest.keyClicks(cv, text)
    qapp.processEvents()
    if enter:
        QTest.keyClick(cv, Qt.Key_Return)
        qapp.processEvents()


def _draw_line(sketch, qapp, a=(0, 0), b=(10, 0)):
    sketch.set_tool("line")
    _click(sketch, qapp, *a)
    _click(sketch, qapp, *b)
    sketch.set_tool("select")            # end the chain cleanly
    qapp.processEvents()


# ----------------------------------------------------------------- type-in

def test_line_gets_its_length_from_the_keyboard(sketch, qapp):
    _draw_line(sketch, qapp)
    assert sketch._pending is not None          # armed right after drawing
    _type(sketch, qapp, "40")
    cons = sketch.model.sketch.constraints
    dim = [c for c in cons if isinstance(c, Distance)]
    assert len(dim) == 1 and dim[0].value == pytest.approx(40.0)
    ln = sketch.model.sketch.lines[0]
    gap = math.hypot(ln.b.x - ln.a.x, ln.b.y - ln.a.y)
    assert gap == pytest.approx(40.0, rel=1e-6)  # the solver obeyed
    assert sketch._pending is None               # spent


def test_circle_radius_typed(sketch, qapp):
    # M98 migration: after a circle the typed number is the DIAMETER
    sketch.set_tool("circle")
    _click(sketch, qapp, 0, 0)
    _click(sketch, qapp, 5, 0)                  # rim click mints r=5
    _type(sketch, qapp, "24")
    cons = [c for c in sketch.model.sketch.constraints
            if isinstance(c, Radius)]
    assert len(cons) == 1 and cons[0].value == pytest.approx(12.0)
    assert sketch.model.sketch.circles[0].r == pytest.approx(12.0, rel=1e-6)


def test_rect_wants_two_numbers(sketch, qapp):
    sketch.set_tool("rect")
    _click(sketch, qapp, 0, 0)
    _click(sketch, qapp, 12, 8)
    _type(sketch, qapp, "30")                   # width
    lns = sketch.model.sketch.lines
    bottom = lns[0]
    dim_h = [c for c in sketch.model.sketch.constraints
             if isinstance(c, Distance)]
    assert len(dim_h) == 1
    assert dim_h[0].value == pytest.approx(30.0)
    assert sketch._pending is not None          # stage 2: the height
    _type(sketch, qapp, "15")
    dims = [c for c in sketch.model.sketch.constraints
            if isinstance(c, Distance)]
    assert len(dims) == 2
    assert sketch._pending is None
    side = lns[1]
    gap = math.hypot(side.b.x - side.a.x, side.b.y - side.a.y)
    assert gap == pytest.approx(15.0, rel=1e-4)


def test_arc_radius_typed(sketch, qapp):
    sketch.set_tool("arc")
    _click(sketch, qapp, 0, 0)
    _click(sketch, qapp, 20, 0)
    _click(sketch, qapp, 10, 6)
    _type(sketch, qapp, "9")
    cons = [c for c in sketch.model.sketch.constraints
            if isinstance(c, Radius)]
    assert len(cons) == 1 and cons[0].value == pytest.approx(9.0)


def test_escape_abandons_the_type_in(sketch, qapp):
    _draw_line(sketch, qapp)
    _type(sketch, qapp, "7", enter=False)
    QTest.keyClick(sketch, Qt.Key_Escape)
    qapp.processEvents()
    assert sketch._pending is None and sketch._num_buf == ""
    assert not [c for c in sketch.model.sketch.constraints
                if isinstance(c, Distance)]


def test_other_keys_abandon_then_act(sketch, qapp):
    _draw_line(sketch, qapp)
    _type(sketch, qapp, "9", enter=False)
    QTest.keyClick(sketch, Qt.Key_C)            # a tool key, not a digit
    qapp.processEvents()
    assert sketch._pending is None              # abandoned...
    assert not [c for c in sketch.model.sketch.constraints
                if isinstance(c, Distance)]
    assert sketch._tool == "circle"             # ...and still heard


def test_next_stroke_abandons_pending(sketch, qapp):
    _draw_line(sketch, qapp)
    _type(sketch, qapp, "9", enter=False)       # buffer open
    sketch.set_tool("line")
    _click(sketch, qapp, 50, 0)                 # new stroke starts
    qapp.processEvents()
    assert sketch._pending is None and sketch._num_buf == ""
    assert not [c for c in sketch.model.sketch.constraints
                if isinstance(c, Distance)]


def test_enter_with_empty_buffer_is_harmless(sketch, qapp):
    _draw_line(sketch, qapp)
    _type(sketch, qapp, "")                     # just the Enter
    assert sketch._pending is not None          # still armed, no crash
    assert not [c for c in sketch.model.sketch.constraints
                if isinstance(c, Distance)]


def test_backspace_edits_the_buffer(sketch, qapp):
    _draw_line(sketch, qapp)
    _type(sketch, qapp, "40", enter=False)
    QTest.keyClick(sketch, Qt.Key_Backspace)
    qapp.processEvents()
    assert sketch._num_buf == "4"
    _type(sketch, qapp, "5")                    # now "45"
    dim = [c for c in sketch.model.sketch.constraints
           if isinstance(c, Distance)]
    assert len(dim) == 1 and dim[0].value == pytest.approx(45.0)


def test_retype_never_stacks_constraints(sketch, qapp):
    _draw_line(sketch, qapp)
    _type(sketch, qapp, "40")
    # second dimension on the same line (e.g. via the dialog path later):
    _type(sketch, qapp, "40")                   # pending already spent —
    cons = [c for c in sketch.model.sketch.constraints             # no-op
            if isinstance(c, Distance)]
    assert len(cons) == 1


# ------------------------------------------------------------- guarantees

def test_idle_digits_do_nothing(sketch, qapp):
    _draw_line(sketch, qapp)
    _type(sketch, qapp, "40")                   # spends the pending
    sketch.set_tool("select")
    _type(sketch, qapp, "77")                   # idle typing afterwards
    assert sketch._num_buf == ""
    assert len([c for c in sketch.model.sketch.constraints
                if isinstance(c, Distance)]) == 1


def test_undo_rolls_back_the_typed_dimension(sketch, qapp):
    _draw_line(sketch, qapp)
    _type(sketch, qapp, "40")
    sketch.undo_op()
    qapp.processEvents()
    assert not [c for c in sketch.model.sketch.constraints
                if isinstance(c, Distance)]


def test_buffer_chips_paints_on_the_canvas(sketch, qapp):
    _draw_line(sketch, qapp)
    _type(sketch, qapp, "4", enter=False)
    sketch.resize(600, 400)
    sketch._scale = 8.0
    sketch._center = np.array([5.0, 0.0])

    def chip_ink():
        pm = QPixmap(600, 400)
        pm.fill(QColor(20, 20, 24))
        p = QPainter(pm)
        sketch._draw_typein(p)
        p.end()
        img = pm.toImage()
        n = 0
        for x in range(0, 600, 2):
            for y in range(0, 400, 2):
                q = img.pixelColor(x, y)
                if (abs(q.red() - 63) <= 2 and abs(q.green() - 68) <= 2
                        and abs(q.blue() - 76) <= 2):
                    n += 1
        return n

    ink = chip_ink()
    assert ink > 0                              # the little white box
    sketch._num_buf = ""
    assert chip_ink() == 0                      # gone with the buffer
