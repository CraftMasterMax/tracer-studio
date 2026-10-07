"""M6: circular patterns + keyboard feature delete."""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                 # noqa: E402
from PySide6.QtTest import QSignalSpy, QTest          # noqa: E402
from PySide6.QtWidgets import (QApplication,          # noqa: E402
                               QInputDialog)

from tracer.core.document import (CircularPatternFeature, Document)  # noqa: E402
from conftest import script_cmd                       # noqa: E402


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


def _flange():
    doc = Document("t")
    doc.add_plate("flange", 40, 40, 5)                # 8000 mm^3, spans 0..40
    hole = doc.add_cylinder("bolt hole", 2, 10, center=(32, 20),
                            z=-2.5, op="subtract")
    return doc, hole


HOLE = math.pi * 2 ** 2 * 5


def test_circular_pattern_even_spread():
    doc, hole = _flange()
    assert doc.result.volume == pytest.approx(8000 - HOLE, rel=2e-2)
    doc.add_circular_pattern("bolt circle", hole, (20, 20), 360.0, 6)
    v6 = doc.result.volume
    assert v6 == pytest.approx(8000 - 6 * HOLE, rel=2e-2)


def test_partial_angle_inclusive():
    doc, hole = _flange()
    doc.add_circular_pattern("arc", hole, (20, 20), 90.0, 4)
    assert doc.result.volume == pytest.approx(8000 - 4 * HOLE, rel=2e-2)


def test_circular_pattern_serialization():
    doc, hole = _flange()
    doc.add_circular_pattern("bolt circle", hole, (20, 20), 360.0, 5)
    v0 = doc.result.volume
    d = doc.to_dict()
    pat = next(fd for fd in d["features"]
               if fd["type"] == "CircularPatternFeature")
    assert pat["center"] == [20.0, 20.0] and pat["count"] == 5
    doc2 = Document.from_dict(d)
    p2 = next(f for f in doc2.features
              if isinstance(f, CircularPatternFeature))
    assert p2.source_uid == hole.uid
    assert doc2.recompute().volume == pytest.approx(v0, rel=1e-9)


def test_pattern_skips_suppressed_source():
    doc, hole = _flange()
    doc.add_circular_pattern("bolt circle", hole, (20, 20), 360.0, 6)
    v_full = doc.result.volume
    hole.suppressed = True
    assert doc.recompute().volume == pytest.approx(8000, rel=1e-6)
    hole.suppressed = False
    assert doc.recompute().volume == pytest.approx(v_full, rel=1e-9)


# ---- UI ---------------------------------------------------------------
def test_circular_pattern_dialog_and_undo(win, monkeypatch):
    win.new_document()
    win.doc.add_plate("flange", 40, 40, 5)
    win.doc.add_cylinder("bolt hole", 2, 10, center=(32, 20), z=-2.5,
                         op="subtract")
    win.recompute()
    script_cmd(monkeypatch, {"src": "bolt hole", "axis": "+Z (through center)",
                             "cx": 20.0, "cy": 20.0,
                             "ang": 360.0, "count": 5})
    win.action_circular_pattern()
    pats = [f for f in win.doc.features
            if isinstance(f, CircularPatternFeature)]
    assert len(pats) == 1
    assert win.doc.result.volume == pytest.approx(8000 - 5 * HOLE, rel=2e-2)
    win.undo()
    assert not [f for f in win.doc.features
                if isinstance(f, CircularPatternFeature)]


def test_timeline_delete_key(win, qapp):
    win.new_document()
    win.doc.add_plate("p", 10, 10, 1)
    win.doc.add_cylinder("peg", 2, 3, center=(5, 5), z=1, op="union")
    win.recompute()
    qapp.processEvents()
    bar = win.timeline.bar
    assert bar._chips, "chips not laid out"
    x, w = bar._chips[1][0], bar._chips[1][1]
    QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, QPoint(int(x + w / 2), 20), 10)
    assert bar._sel == 1
    spy = QSignalSpy(bar.feature_delete)
    QTest.keyPress(bar, Qt.Key_Delete)
    assert spy.count() == 1
    assert len(win.doc.features) == 1          # wired to _delete_feature
    assert win.doc.result.volume == pytest.approx(100, rel=1e-6)
