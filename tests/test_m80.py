"""M80 — Mirror entities: the sketch tool set's last standing gap.

Fusion's Mirror: pick a line and some geometry, and the geometry gets a
mirrored twin about it.  Here it is: Shift+M (or the Mirror button /
context menu) with exactly ONE selected line as the axis.  The copies
are real parametric entities, and anything that lies ON the axis KEEPS
its point — a mirrored wall butts against the original through a shared
Point, exactly like Fusion's connectivity, so the two halves stay one
closed profile and extrude as one solid.

Honest limits: an ellipse mirrors about an axis-parallel line only (a
slanted axis would need a rotated ellipse we don't model — the copy is
skipped, nothing else is); and the axis itself is never mirrored.
Construction toggle (K) grew a circle and an ellipse while we were in
the neighbourhood — Fusion toggles anything.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from tracer.core.sketch.entities import (Circle, Ellipse, Line)      # noqa: E402
from tracer.core.sketch.model import SketchModel                     # noqa: E402


def _vaxis(m, x=0.0, half=40.0):
    return m.add_line(m.point(x, -half), m.point(x, half))


# ---- core: the reflection -----------------------------------------------------

def test_mirroring_a_rect_doubles_it():
    m = SketchModel()
    p0, p1 = m.point(2, 0), m.point(10, 6)
    m.add_rect(p0, p1)
    axis = _vaxis(m)
    made = m.mirror_about(axis, list(m.sketch.lines))
    assert len(made) == 4 and len(m.sketch.lines) == 9     # +1 axis line
    xs = sorted(p.x for l in m.sketch.lines for p in (l.a, l.b))
    assert xs[0] == pytest.approx(-10.0) and xs[-1] == pytest.approx(10.0)


def test_geometry_on_the_axis_shares_the_point():
    m = SketchModel()
    a = m.point(0, 0)                       # sits ON the axis x = 0
    b = m.point(8, 0)
    ln = m.add_line(a, b)
    axis = _vaxis(m)
    made = m.mirror_about(axis, [ln])
    assert len(made) == 1
    assert a in (made[0].a, made[0].b)      # SAME Point object — joined
    other = made[0].b if made[0].a is a else made[0].a
    assert (other.x, other.y) == pytest.approx((-8.0, 0.0))


def test_a_circle_mirrors_its_centre_and_keeps_its_r():
    m = SketchModel()
    c = m.add_circle(m.point(5, 2), 2.5)
    made = m.mirror_about(_vaxis(m), [c])
    assert len(made) == 1 and made[0].r == 2.5
    assert (made[0].c.x, made[0].c.y) == pytest.approx((-5.0, 2.0))


def test_an_arc_mirrors_and_swaps_its_sweep():
    m = SketchModel()
    ar = m.sketch.arc(m.point(2, 0), m.point(6, 4), m.point(10, 0))
    made = m.mirror_about(_vaxis(m), [ar])
    assert len(made) == 1 and len(m.sketch.arcs) == 2
    new = made[0]
    assert (new.a.x, new.a.y) == pytest.approx((-10.0, 0.0))   # old b
    assert (new.b.x, new.b.y) == pytest.approx((-2.0, 0.0))    # old a
    assert (new.m.x, new.m.y) == pytest.approx((-6.0, 4.0))


def test_ellipses_mirror_axis_parallel_only():
    m = SketchModel()
    e = m.sketch.ellipse(m.point(6, 3), 4.0, 2.0)
    upright = m.mirror_about(_vaxis(m), [e])
    assert len(upright) == 1
    assert (upright[0].c.x, upright[0].c.y) == pytest.approx((-6.0, 3.0))
    assert (upright[0].rx, upright[0].ry) == (4.0, 2.0)
    slant = m.add_line(m.point(-20, -20), m.point(20, 20))     # 45°
    assert m.mirror_about(slant, [e]) == []                    # skipped


def test_the_two_halves_extrude_as_one_solid():
    # the rect's edge AT the axis must not be duplicated — mirror_about
    # skips self-mirroring geometry; the union stitches as two face-to-
    # face half loops whose union is the full 20x6 slab
    from tracer.core.document import Document, ExtrudeFeature
    m = SketchModel()
    p0, p1 = m.point(0, 0), m.point(10, 6)      # edge AT x=0
    m.add_rect(p0, p1)
    axis = _vaxis(m)
    made = m.mirror_about(axis, list(m.sketch.lines))
    assert len(made) == 3                        # the on-axis edge skipped
    assert len(m.sketch.lines) == 8              # 4 rect + axis + 3 twin
    loops, _w = m.to_loops()
    assert len(loops) == 2                       # two halves, face to face
    doc = Document()
    doc.add(ExtrudeFeature(name="half L", outer=loops[0]["points"],
                           height=3.0))
    doc.add(ExtrudeFeature(name="half R", outer=loops[1]["points"],
                           height=3.0))          # default op: union
    s = doc.recompute()
    assert s.volume == pytest.approx(20 * 6 * 3, rel=1e-3)


# ---- the editor: Shift+M, the button, the honest K ----------------------------

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


def _sk(win, qapp, scale=6.0):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    cv.set_grid_snap(False)
    cv._scale = scale
    cv._center = np.array([0.0, 0.0])
    cv.set_tool("select")
    qapp.processEvents()
    return cv


def _click(cv, qapp, x, y):
    p = cv.w2s(x, y)
    QTest.mouseClick(cv, Qt.LeftButton, Qt.NoModifier,
                     QPoint(int(p.x()), int(p.y())))
    qapp.processEvents()


def test_shift_m_mirrors_the_selection(win, qapp):
    cv = _sk(win, qapp)
    m = cv.model
    p0, p1 = m.point(2, 0), m.point(10, 6)
    m.add_rect(p0, p1)
    axis = _vaxis(m)
    cv._sel = [axis, *list(m.sketch.lines)]      # axis + the rect's 4
    QTest.keyClick(cv, Qt.Key_M, Qt.ShiftModifier)
    qapp.processEvents()
    assert len(m.sketch.lines) == 9                    # 4 rect + axis + 4
    assert all(isinstance(e, Line) for e in cv._sel)   # the copies stay
    assert len(cv._sel) == 4


def test_a_plain_m_still_means_symmetry(win, qapp):
    cv = _sk(win, qapp)
    m = cv.model
    a = m.point(2, 0)
    m.add_line(m.point(0, 0), m.point(0, 10))       # a LINE for axis...
    l = m.add_line(a, m.point(8, 0))
    cv._sel = [l]
    before = len(m.sketch.constraints)
    QTest.keyClick(cv, Qt.Key_M)                    # plain M: symmetry
    qapp.processEvents()
    assert len(m.sketch.lines) == 2                 # mirrored NOTHING
    assert len(m.sketch.constraints) == before      # (needs 3 picks anyway)


def test_the_mirror_button_mirrors_too(win, qapp):
    cv = _sk(win, qapp)
    m = cv.model
    c = m.add_circle(m.point(6, 0), 3.0)
    axis = _vaxis(m)
    cv._sel = [axis, c]
    win._sketch_mirror_btn.click()
    assert len(m.sketch.circles) == 2
    assert (m.sketch.circles[1].c.x, m.sketch.circles[1].r) == \
        pytest.approx((-6.0, 3.0))


def test_K_toggles_construction_on_circles_ellipses_and_lines(win, qapp):
    cv = _sk(win, qapp)
    m = cv.model
    c = m.add_circle(m.point(20, 0), 2.0)
    e = m.sketch.ellipse(m.point(30, 0), 4.0, 2.0)
    ln = m.add_line(m.point(40, 0), m.point(50, 0))
    cv._sel = [c, e, ln]
    cv.act_construction()
    assert c.construction and e.construction and ln.construction
    loops, _w = m.to_loops()
    assert loops == []                              # guide geometry only


def test_the_context_menu_offers_mirror(win, qapp):
    cv = _sk(win, qapp)
    m = cv.model
    l = m.add_line(m.point(2, 0), m.point(10, 6))
    axis = _vaxis(m)
    cv._sel = [axis, l]
    menu = cv._build_menu()
    assert any("Mirror" in a.text() for a in menu.actions())
    cv._sel = [l]                                   # one line, no axis set
    menu = cv._build_menu()
    assert not any("Mirror about" in a.text() for a in menu.actions())
