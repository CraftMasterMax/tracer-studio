"""M175 rung 1 - THE DIMENSION FOLLOWS THE CURSOR (act one: the modal dies).

FD5 LAW 35's opening clause: pick the entity, the dimension appears and
value input opens IMMEDIATELY (Enter keeps it). The product answered
that verb with a MODAL QInputDialog - the one panel Fusion has never
had. act_dim now BIRTHS the dimension at the geometry's own measurement
(the same remove_last honesty M90 kept) and opens the INLINE chip
editor on the newborn: pick, dim, type, Enter - never a dialog. The
dialect from M174 rides at birth: a circle's chip already speaks
diameter, so the typed number is halved into core by the very same
commit every other edit pays; arcs keep radius. Re-dimming still never
stacks. The witnesses patch the old door to RAISE - a rung whose
headline is "the dialog is dead" proves it by trying to open one.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest                                    # noqa
from PySide6.QtCore import Qt                                       # noqa
from PySide6.QtWidgets import QApplication                          # noqa

from tracer.core.sketch.constraints import Distance, Radius         # noqa
from tracer.core.sketch.model import SketchModel                    # noqa
from tracer.ui.cmddialog import Shell                               # noqa
from tracer.ui.sketcheditor import SketchCanvas                     # noqa

from conftest import script_dim_edit                                # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    c = SketchCanvas()
    c.set_model(SketchModel())
    c.resize(600, 400)
    c._snap_grid = False
    yield c
    c.deleteLater()


def _no_modal(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a modal dialog opened - FD5-L35 says NO")
    monkeypatch.setattr(Shell, "getDouble", staticmethod(boom))


def _line_scene(ed):
    m = ed.model
    a, b = m.point(0, 0), m.point(10, 0)
    ln = m.add_line(a, b)
    ed._solve()
    return m, ln


def test_act_dim_opens_no_dialog_and_asks_on_the_canvas(ed, qapp,
                                                        monkeypatch):
    _no_modal(monkeypatch)                     # the dead door TESTIFIES
    m, ln = _line_scene(ed)
    ed._sel = [ln]
    h0 = len(ed._hist)
    ed.act_dim()                               # RAISES if a dialog lives
    assert len(ed._hist) == h0 + 1             # birth costs ONE row
    d = next(x for x in m.sketch.constraints if isinstance(x, Distance))
    assert d.value == pytest.approx(10.0)      # born at the MEASUREMENT
    assert ed._dim_edit is not None and ed._dim_edit.constraint is d
    ed._close_dim_editor()                     # unchanged: no trace


def test_the_newborn_answers_in_canvas_and_redimming_never_stacks(
        ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    script_dim_edit(monkeypatch, "12")         # the seam IS the typing
    m, ln = _line_scene(ed)
    ed._sel = [ln]
    ed.act_dim()
    ds = [x for x in m.sketch.constraints if isinstance(x, Distance)]
    assert len(ds) == 1 and ds[0].value == pytest.approx(12.0)
    ed.act_dim()                               # dim it AGAIN
    ds = [x for x in m.sketch.constraints if isinstance(x, Distance)]
    assert len(ds) == 1                        # remove_last honesty


def test_two_points_dim_without_a_panel(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    script_dim_edit(monkeypatch, "5")
    m = ed.model
    p, q = m.point(0, 0), m.point(10, 0)       # a bare PAIR, no line
    ed._solve()
    ed._sel = [p, q]
    ed.act_dim()
    ds = [x for x in m.sketch.constraints if isinstance(x, Distance)]
    assert len(ds) == 1 and ds[0].value == pytest.approx(5.0)


def test_a_circle_is_born_speaking_diameter(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    script_dim_edit(monkeypatch, "10")         # TEN typed...
    m = ed.model
    ctr = m.point(0, 0)
    circ = m.add_circle(ctr, 3.0)
    ed._solve()
    ed._sel = [circ]
    ed.act_dim()                               # born R 3.00, speaks O
    c = next(x for x in m.sketch.constraints if isinstance(x, Radius))
    assert c.value == pytest.approx(5.0)       # ...FIVE kept in core
    assert ed._dim_text(c) == "\u00d8 10.00"   # the chip says TEN


def test_an_arc_answers_in_radius(ed, qapp, monkeypatch):
    _no_modal(monkeypatch)
    script_dim_edit(monkeypatch, "7.5")
    m = ed.model
    ar = m.sketch.arc(m.point(0, 0), m.point(10, 6), m.point(20, 0))
    ed._solve()
    ed._sel = [ar]
    ed.act_dim()
    c = next(x for x in m.sketch.constraints if isinstance(x, Radius))
    assert c.value == pytest.approx(7.5)       # arcs: no halving
    assert ed._dim_text(c) == "R 7.50"
