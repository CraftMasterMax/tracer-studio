"""M72 — Browser keyboard grammar: Del deletes, F2 renames, Z zooms.

Fusion's muscle memory on OUR browser tree: select a feature, hit Delete
(it goes through the exact same handler as the context menu — undoable
and recompute-clean), hit F2 (the rename prompt, scripted here), and on
the canvas press Z to frame whatever faces are selected.  The timeline
strip already spoke Del; now the tree does too, and Backspace joins it.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtTest import QTest                                       # noqa: E402
from PySide6.QtWidgets import QApplication                             # noqa: E402

from conftest import feature_rows                                      # noqa: E402
from tracer.core.document import PrimitiveFeature                      # noqa: E402


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


def _plate(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 20, "dz": 10}))
    win.recompute()
    win.viewport.refresh(fit=True)
    qapp.processEvents()


def _click(win, qapp, world):
    vp = win.viewport
    spot = vp.camera().project(np.asarray(world, float),
                               vp.width(), vp.height())
    p = QPoint(int(spot[0]), int(spot[1]))
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p, 10)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p, 10)
    qapp.processEvents()


def test_del_key_in_tree_deletes_the_feature(win, qapp):
    _plate(win, qapp)
    row = feature_rows(win)[0]
    win.rail.tree.setCurrentItem(row)
    QTest.keyPress(win.rail.tree, Qt.Key_Delete)
    qapp.processEvents()
    assert win.doc.features == []
    assert win.doc.result is None or win.doc.result.volume == 0
    assert "Deleted" in win.status.currentMessage()


def test_del_is_undoable(win, qapp):
    _plate(win, qapp)
    win.rail.tree.setCurrentItem(feature_rows(win)[0])
    QTest.keyPress(win.rail.tree, Qt.Key_Delete)
    qapp.processEvents()
    win.undo()
    qapp.processEvents()
    assert len(win.doc.features) == 1
    assert win.doc.result.volume == pytest.approx(8000, rel=1e-3)


def test_f2_renames_the_selected_feature(win, qapp, monkeypatch):
    from tracer.ui.cmddialog import Shell
    _plate(win, qapp)
    monkeypatch.setattr(Shell, "getText",
                        staticmethod(lambda *a, **k: ("base plate", True)))
    win.rail.tree.setCurrentItem(feature_rows(win)[0])
    QTest.keyPress(win.rail.tree, Qt.Key_F2)
    qapp.processEvents()
    assert win.doc.features[0].name == "base plate"
    assert "base plate" in feature_rows(win)[0].text(0)


def test_f2_cancel_keeps_the_name(win, qapp, monkeypatch):
    from tracer.ui.cmddialog import Shell
    _plate(win, qapp)
    monkeypatch.setattr(Shell, "getText",
                        staticmethod(lambda *a, **k: ("ignored", False)))
    win.rail.tree.setCurrentItem(feature_rows(win)[0])
    QTest.keyPress(win.rail.tree, Qt.Key_F2)
    qapp.processEvents()
    assert win.doc.features[0].name == "plate"


def test_selection_bbox_spans_all_picked_triangles(win, qapp):
    # M59 turned _sel into a TRIANGLE list and silently broke M56's
    # zoom-to: min over the (N,3,3) corner block is a matrix, not a
    # corner.  Pin the honest shape and the exact planar corners.
    _plate(win, qapp)
    vp = win.viewport
    _click(win, qapp, (40, 10, 5))
    lo, hi = (np.asarray(a, float) for a in vp.selection_bbox())
    assert lo.shape == (3,) and hi.shape == (3,)
    assert np.allclose(lo, (40, 0, 0), atol=1e-6)
    assert np.allclose(hi, (40, 20, 10), atol=1e-6)


def test_z_zooms_to_the_selection(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    d0 = vp.camera().distance
    _click(win, qapp, (40, 10, 5))            # the little 20×10 end face
    assert vp._sel
    QTest.keyPress(vp, Qt.Key_Z)
    qapp.processEvents()
    assert vp.camera().distance < d0 * 0.9    # framed the picked face
    # no selection -> Z is inert
    _click(win, qapp, (10, 5, 10))
    vp._sel, _h = [], None                    # clear without camera churn
    d1 = vp.camera().distance
    QTest.keyPress(vp, Qt.Key_Z)
    qapp.processEvents()
    assert vp.camera().distance == pytest.approx(d1)
