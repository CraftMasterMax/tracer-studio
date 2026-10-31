"""M181 R1 - DELETE MEETS THE HOVERED DIM (FD5-L32).

Fusion's context-sensitive Delete: when the pointer rests on a dimension
chip, Delete eats THE DIM and the geometry stands untouched. The door
already had a hinge - act_remove_constraint is what the hover menu's
'Remove Constraint' calls - but the keyboard never reached it. These gates
pin the CONTEXT part honestly: the SAME keypress removes the dim when the
chip is under the cursor, changes NOTHING when it is not, and never
changes what a real selection is worth.
"""
import numpy as np                                              # noqa
import pytest                                                   # noqa

pytest.importorskip("PySide6")                                  # noqa

from PySide6.QtCore import QEvent, QPointF, Qt        # noqa
from PySide6.QtGui import QMouseEvent, QImage       # noqa
from PySide6.QtTest import QTest                                # noqa
from PySide6.QtWidgets import QApplication                      # noqa

from tracer.core.sketch.constraints import Distance             # noqa
from tracer.core.sketch.model import SketchModel                # noqa
from tracer.ui.sketcheditor import SketchCanvas                 # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    m = SketchModel()
    p1 = m.point(-10.0, 15.0)                   # a floating pair: the DIM
    p2 = m.point(10.0, 15.0)                    #  is their ONLY story -
    m.constrain(Distance(p1, p2, 20.0))         #  no line, no overlap
    m.solve()
    c = SketchCanvas()
    c.set_model(m)
    c.resize(600, 400)
    c._snap_grid = False
    c.show()
    qapp.processEvents()
    yield c
    # M181 POLLUTION LAW: close() BEFORE deleteLater() - a SHOWN canvas
    # torn down with bare deleteLater leaves an offscreen ghost window
    # that KILLS the hover path of every later module in the process
    # (m164's four hover gates collapsed; the close-first variant proved
    # it: 70 green vs 4 failed. m179/m180 only escaped by alphabetical
    # luck - nothing hover-sensitive happened to sort after them).
    c.close()
    qapp.processEvents()
    c.deleteLater()


def _dim_rect(ed, qapp):
    qapp.processEvents()                        # ride the per-paint list
    return next(r for r, c in ed._dim_hits if type(c) is Distance)


def _move_widget(ed, qx, qy):
    p = QPointF(float(qx), float(qy))               # the m37 way: a real
    QApplication.sendEvent(                          #  event; the fixture
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,   #  teardown parks
                        Qt.NoButton, Qt.NoButton, Qt.NoModifier))  #  the mess


def _white(img, cx, cy, hw=24, hh=11):
    q = img.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    a = np.frombuffer(bytes(q.bits()), np.uint8).reshape(
        q.height(), q.width(), 4)[:, :, :3]
    w = a[max(0, cy - hh):cy + hh, max(0, cx - hw):cx + hw].reshape(
        -1, 3).astype(int)
    return int((w.min(axis=1) > 120).sum())


def test_delete_on_a_dim_chip_eats_the_dim_not_the_geometry(ed, qapp):
    r = _dim_rect(ed, qapp)
    n_pts, n_lines = len(ed.model.sketch.points), len(ed.model.sketch.lines)
    _move_widget(ed, r.center().x(), r.center().y())
    qapp.processEvents()
    QTest.keyClick(ed, Qt.Key_Delete)
    dims = [c for c in ed.model.sketch.constraints if type(c) is Distance]
    assert dims == []                           # the DIM is gone...
    assert len(ed.model.sketch.points) == n_pts  #  ...the geometry stands
    assert len(ed.model.sketch.lines) == n_lines
    assert ed._sel == []


def test_delete_without_a_hover_changes_nothing(ed, qapp):
    before = len(ed.model.sketch.constraints)
    _move_widget(ed, 30, 380)                   # empty corner: no chip
    qapp.processEvents()
    QTest.keyClick(ed, Qt.Key_Delete)
    assert len(ed.model.sketch.constraints) == before   # the context is
    assert len(ed.model.sketch.points) == 2              #  the whole gate


def test_a_real_selection_outranks_the_hovered_chip(ed, qapp):
    r = _dim_rect(ed, qapp)
    extra = ed.model.point(0.0, -15.0)          # an UNRELATED point: the
    ed._sel = [extra]                           #  two Delete doors give
    _move_widget(ed, r.center().x(), r.center().y())   #  opposite answers
    qapp.processEvents()                        #   - selection eats THIS
    QTest.keyClick(ed, Qt.Key_Delete)           #   point, the chip eats
    pts = ed.model.sketch.points                #   the DIM only
    assert len(pts) == 2                        # extra gone, the dim's
    assert all(p is not extra for p in pts)     #  pair STAND
    assert len([c for c in ed.model.sketch.constraints
                if type(c) is Distance]) == 1   #  pair untouched: the
    #                                            chip door stayed SHUT


def test_the_removed_chip_stops_answer_to_the_mouse(ed, qapp):
    r = _dim_rect(ed, qapp)
    cx, cy = int(r.center().x()), int(r.center().y())
    white_before = _white(ed.grab(), cx, cy)
    _move_widget(ed, cx, cy)
    qapp.processEvents()
    QTest.keyClick(ed, Qt.Key_Delete)
    qapp.processEvents()
    white_after = _white(ed.grab(), cx, cy)
    assert white_before > 20                    # RELATIVE: the chip was
    assert white_after < white_before - 15      #  WHITE ink; the same
    #   window after the act is EMPTY of it (a floating pair leaves the
    #   window bare - no line hides under it)
