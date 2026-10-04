"""M11: boolean operations (Join / Cut / Intersect) on extruded features."""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog     # noqa: E402

from forma.core.document import ExtrudeFeature, PrimitiveFeature  # noqa: E402
from forma.core.document import Document                     # noqa: E402


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


def _draw_rect(cv, x1, y1):
    cv.set_tool("rect")
    p0 = cv.w2s(0, 0).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, p0, 10)
    p1 = cv.w2s(x1, y1).toPoint()
    QTest.mouseMove(cv, p1)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, p1, 10)
    qapp = QApplication.instance()
    qapp.processEvents()


def _draw_circle(cv, cx, cy, r):
    cv.set_tool("circle")
    c = cv.w2s(cx, cy).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier, c, 10)
    QTest.mouseMove(cv, c)
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier, c, 10)   # click arms
    QTest.mouseMove(cv, cv.w2s(cx + r, cy).toPoint())
    QTest.mousePress(cv, Qt.LeftButton, Qt.NoModifier,
                     cv.w2s(cx + r, cy).toPoint(), 10)            # 2nd click
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.NoModifier,
                       cv.w2s(cx + r, cy).toPoint(), 10)
    QApplication.instance().processEvents()


# ---- core: booleans already work in the kernel -----------------------------
def test_cut_punches_through_hole():
    doc = Document()
    doc.features.append(PrimitiveFeature(name="base", kind="box",
                                         dims={"dx": 40, "dy": 25, "dz": 10}))
    outer = [(8, 8), (16, 8), (16, 16), (8, 16)]
    doc.features.append(ExtrudeFeature(name="slot", outer=outer, height=20,
                                       op="subtract"))
    v = doc.recompute().volume
    assert v == pytest.approx(40 * 25 * 10 - 8 * 8 * 10, rel=1e-3)


def test_intersect_keeps_overlap_only():
    doc = Document()
    doc.features.append(PrimitiveFeature(name="a", kind="box",
                                         dims={"dx": 10, "dy": 10, "dz": 10}))
    b = PrimitiveFeature(name="b", kind="box",
                         dims={"dx": 10, "dy": 10, "dz": 10},
                         placement=(5.0, 0.0, 0.0), op="intersect")
    doc.features.append(b)
    assert doc.recompute().volume == pytest.approx(5 * 10 * 10, rel=1e-3)


def test_cut_survives_save_roundtrip(tmp_path):
    from forma.core import io as fio
    doc = Document()
    doc.features.append(PrimitiveFeature(name="base", kind="box",
                                         dims={"dx": 10, "dy": 10, "dz": 10}))
    doc.features.append(ExtrudeFeature(name="hole",
                                       outer=[(4, 4), (6, 4), (6, 6), (4, 6)],
                                       height=20, op="subtract"))
    p = tmp_path / "cut.forma"
    fio.save_document(doc, p)
    d2 = fio.load_document(p)
    assert d2.features[1].op == "subtract"
    assert d2.recompute().volume == pytest.approx(1000 - 40, rel=1e-3)


# ---- UI: the context-menu action path (menu.exec is modal; logic tested) ---
def test_operation_switch_bosses_then_cuts(win):
    win.new_document()
    win.action_new_sketch()
    _draw_rect(win.sketch, 40, 25)
    win.sketch.finish()                       # height patched -> 10 mm
    assert win.doc.result.volume == pytest.approx(40 * 25 * 10, rel=2e-2)

    win.action_new_sketch()                   # same XY plane
    _draw_circle(win.sketch, 20, 12.5, 6)
    win.sketch.finish()
    assert len(win.doc.features) == 2
    v_base = win.doc.result.volume

    win._set_operation(win.doc.features[1], "subtract")
    v_cut = win.doc.result.volume
    assert v_cut < v_base - 1000              # material clearly removed
    assert v_cut == pytest.approx(v_base - math.pi * 36 * 10, rel=0.03)
    assert win.doc.features[1].op == "subtract"


def test_base_feature_cannot_be_cut(win):
    win.new_document()
    win.action_new_sketch()
    _draw_rect(win.sketch, 20, 20)
    win.sketch.finish()
    base = win.doc.features[0]
    assert win._is_base_feature(base)
    win._set_operation(base, "subtract")      # must be refused
    assert base.op == "union"
    assert win.doc.result.volume == pytest.approx(20 * 20 * 10, rel=2e-2)


def test_second_feature_can_intersect(win):
    win.new_document()
    win.action_new_sketch()
    _draw_rect(win.sketch, 20, 20)
    win.sketch.finish()
    win._set_operation(win.doc.features[0], "subtract")  # still base
    assert win.doc.features[0].op == "union"
    win.action_new_sketch()
    _draw_rect(win.sketch, 30, 30)
    win.sketch.finish()
    assert not win._is_base_feature(win.doc.features[1])
    win._set_operation(win.doc.features[1], "intersect")
    assert win.doc.features[1].op == "intersect"
    assert win.doc.result.volume == pytest.approx(20 * 20 * 10, rel=2e-2)


def test_operation_shows_in_browser_and_survives_recompute(win):
    win.new_document()
    win.action_new_sketch()
    _draw_rect(win.sketch, 30, 10)
    win.sketch.finish()
    win.action_new_sketch()
    _draw_rect(win.sketch, 10, 30)            # crosses the first
    win.sketch.finish()
    f2 = win.doc.features[1]
    win._set_operation(f2, "subtract")
    v1 = win.doc.result.volume
    win.doc.dirty = True
    v2 = win.doc.result.volume                       # recompute again from scratch
    assert v1 == pytest.approx(v2, rel=1e-9)
