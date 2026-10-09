"""M88 — the rollback bar: Fusion's rubber band on the timeline.

Suppress (M-era) hides ONE feature; Fusion's real power tool is the
rollback marker — a rubber band across the timeline that hides the
feature AFTER the band and everything downstream, so you edit inside
history exactly where the work continues.  Here the band lands between
chips (context menu "Rollback to here", click the band to end it),
downstream chips dim, and Document.recompute stops at the marker.

Honest scope: the rollback position is VIEW state, not document data —
it is never serialized and never survives opening another file, just
like Fusion does not bake your rubber band into the .f3d.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt                                # noqa: E402
from PySide6.QtTest import QTest                                       # noqa: E402
from PySide6.QtWidgets import QApplication                             # noqa: E402

from tracer.core.document import Document, PrimitiveFeature            # noqa: E402


def _boxes(d: Document, n=3):
    for k in range(n):
        d.features.append(PrimitiveFeature(
            name=f"B{k}", kind="box",
            dims={"dx": 10.0, "dy": 10.0, "dz": 10.0},
            placement=(k * 50.0, 0.0, 0.0)))


# ------------------------------------------------------------------- core

def test_rollback_hides_everything_past_the_band():
    d = Document(title="rb")
    _boxes(d)
    assert d.recompute().volume == pytest.approx(3000.0, rel=1e-6)
    d.rollback_to = 2
    assert d.recompute().volume == pytest.approx(2000.0, rel=1e-6)
    d.rollback_to = 1
    assert d.recompute().volume == pytest.approx(1000.0, rel=1e-6)
    d.rollback_to = None
    assert d.recompute().volume == pytest.approx(3000.0, rel=1e-6)


def test_rollback_at_zero_builds_nothing():
    d = Document(title="rb0")
    _boxes(d)
    d.rollback_to = 0
    assert d.recompute() is None


def test_rollback_is_view_state_not_document_data():
    d = Document(title="rbx")
    _boxes(d)
    d.rollback_to = 1
    raw = d.to_dict()
    assert "rollback_to" not in raw
    back = Document.from_dict(raw)
    assert back.rollback_to is None
    assert back.recompute().volume == pytest.approx(3000.0, rel=1e-6)


def test_pattern_source_under_the_band_drops_out_gracefully():
    from tracer.core.document import LinearPatternFeature
    d = Document(title="rbp")
    _boxes(d, 1)
    d.features.append(LinearPatternFeature(name="Row",
                                           source_uid=d.features[0].uid,
                                           vector=(25.0, 0.0, 0.0),
                                           count=3))
    assert d.recompute().volume == pytest.approx(3000.0, rel=1e-6)
    d.rollback_to = 1                       # pattern sits past the band
    assert d.recompute().volume == pytest.approx(1000.0, rel=1e-6)


# -------------------------------------------------------------------- UI

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


def _win_boxes(win, n=3):
    win.new_document()
    _boxes(win.doc, n)
    win.recompute()
    qapp = QApplication.instance()
    qapp.processEvents()


def test_rollback_handler_hides_and_speaks(win, qapp):
    _win_boxes(win)
    win._rollback_to(win.doc.features[1])      # band after the 2nd chip
    qapp.processEvents()
    assert win.doc.rollback_to == 2
    assert win.doc.result.volume == pytest.approx(2000.0, rel=1e-6)
    assert "showing 2 of 3" in win.status.currentMessage()


def test_rollback_on_the_last_feature_ends_it(win, qapp):
    _win_boxes(win)
    win._rollback_to(win.doc.features[2])      # after the last = end
    qapp.processEvents()
    assert win.doc.rollback_to is None
    assert win.doc.result.volume == pytest.approx(3000.0, rel=1e-6)
    assert "Rollback ended" in win.status.currentMessage()


def test_rollback_ends_on_new_document(win, qapp):
    _win_boxes(win)
    win._rollback_to(win.doc.features[0])
    win.new_document()
    qapp.processEvents()
    assert win.doc.rollback_to is None


def test_band_click_on_the_timeline_ends_rollback(win, qapp):
    _win_boxes(win)
    win._rollback_to(win.doc.features[1])
    qapp.processEvents()
    bar = win.timeline.bar
    bar.grab()                                  # force a paint: layout chips
    assert bar._marker is not None
    QTest.mouseClick(bar, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                     bar._marker.center().toPoint())
    qapp.processEvents()
    assert win.doc.rollback_to is None
    assert "Rollback ended" in win.status.currentMessage()


def test_feature_menu_offers_the_band(win, qapp, monkeypatch):
    # the menu itself is modal; assert through the wiring instead: a
    # rolled-back doc + the timeline's rollback_changed signal contract
    _win_boxes(win)
    seen = []
    win.timeline.bar.rollback_changed.connect(
        lambda n: seen.append(n))
    win.timeline.bar.rollback_changed.emit(1)
    qapp.processEvents()
    assert seen == [1] and win.doc.rollback_to == 1
