"""M4: linear patterns, suppression, unsaved guard, render export."""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QCloseEvent, QImage          # noqa: E402
from PySide6.QtWidgets import (QApplication, QFileDialog,  # noqa: E402
                               QInputDialog, QMessageBox)

from tracer.core.document import (Document, LinearPatternFeature)  # noqa: E402
from conftest import feature_rows  # noqa: E402


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
    w._unsaved = False            # close guard would pop a modal
    w.close()


# ---- kernel: linear pattern --------------------------------------------------
def _plate_with_hole():
    doc = Document("t")
    doc.add_plate("plate", 30, 10, 2)                  # 600 mm^3
    hole = doc.add_cylinder("hole", radius=1.5, height=10,
                            center=(5, 5), z=-4, op="subtract")
    return doc, hole


def test_linear_pattern_adds_interior_copies():
    doc, hole = _plate_with_hole()
    v1 = doc.result.volume
    hole_vol = np.pi * 1.5 ** 2 * 2                    # clipped to 2 mm plate
    assert v1 == pytest.approx(600 - hole_vol, rel=2e-2)
    doc.add_linear_pattern("row", hole, (10, 0, 0), 3)
    v2 = doc.result.volume
    assert v2 == pytest.approx(600 - 3 * hole_vol, rel=2e-2)


def test_pattern_survives_serialization():
    doc, hole = _plate_with_hole()
    doc.add_linear_pattern("row", hole, (10, 0, 0), 4)
    v0 = doc.result.volume
    doc2 = Document.from_dict(doc.to_dict())
    pats = [f for f in doc2.features
            if isinstance(f, LinearPatternFeature)]
    assert len(pats) == 1 and pats[0].count == 4
    src = next(f for f in doc2.features if f.uid == pats[0].source_uid)
    assert src.name == "hole"
    assert doc2.recompute().volume == pytest.approx(v0)


def test_suppressed_feature_skipped_and_pattern_follows_source():
    doc, hole = _plate_with_hole()
    doc.add_linear_pattern("row", hole, (10, 0, 0), 3)
    v_full = doc.result.volume
    hole.suppressed = True
    v_nosrc = doc.recompute().volume                   # plate only + no copies
    assert v_nosrc == pytest.approx(600, rel=1e-6)
    hole.suppressed = False
    assert doc.recompute().volume == pytest.approx(v_full, rel=1e-9)


# ---- UI: pattern dialog flow ---------------------------------------------------
def test_pattern_dialog_and_undo(win, monkeypatch):
    win.new_document()
    win.doc.add_plate("p", 30, 10, 2)
    h = win.doc.add_cylinder("h", 1.5, 10, center=(5, 5), z=-4, op="subtract")
    win.recompute()
    monkeypatch.setattr(QInputDialog, "getItem",
                        staticmethod(lambda *a, **k: ("h", True)))
    dvals = [10.0, 0.0, 0.0]
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (dvals.pop(0), True)))
    monkeypatch.setattr(QInputDialog, "getInt",
                        staticmethod(lambda *a, **k: (3, True)))
    win.action_linear_pattern()
    pats = [f for f in win.doc.features
            if isinstance(f, LinearPatternFeature)]
    assert len(pats) == 1 and pats[0].source_uid == h.uid
    hole_vol = np.pi * 1.5 ** 2 * 2
    assert win.doc.result.volume == pytest.approx(600 - 3 * hole_vol, rel=2e-2)
    win.undo()
    assert not [f for f in win.doc.features
                if isinstance(f, LinearPatternFeature)]


# ---- UI: suppress toggle -------------------------------------------------------
def test_suppress_toggle_via_ui(win):
    win.new_document()
    win.doc.add_plate("p", 20, 20, 5)                  # 2000
    win.doc.add_cylinder("bump", 3, 5, center=(10, 10), z=5, op="union")
    win.recompute()
    v_with = win.doc.result.volume
    bump = win.doc.features[1]
    win._toggle_suppress(bump)
    assert bump.suppressed
    assert win.doc.result.volume == pytest.approx(2000, rel=1e-6)
    assert feature_rows(win)[1].text(0).startswith("○")   # browser glyph
    win._toggle_suppress(bump)
    assert not bump.suppressed
    assert win.doc.result.volume == pytest.approx(v_with, rel=1e-9)


# ---- unsaved-changes close guard -------------------------------------------------
def test_close_guard_cancel_and_discard(win, monkeypatch):
    win._capture()                                     # marks _unsaved
    assert win._unsaved
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Cancel))
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert not ev.isAccepted()
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Discard))
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert ev.isAccepted()


def test_close_guard_saves_then_closes(win, tmp_path, monkeypatch):
    target = tmp_path / "guard.tracer"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(target), "")))
    win._capture()
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Save))
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert ev.isAccepted() and target.exists()
    assert not win._unsaved


# ---- render export ---------------------------------------------------------------
def test_export_render_png(win, tmp_path, monkeypatch):
    out = tmp_path / "render.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    win.action_export_render()
    assert out.exists() and out.stat().st_size > 1000
    img = QImage(str(out))
    assert not img.isNull() and img.width() >= 600
