"""M94 — dimension callouts on the drawing sheet.

A drawing without bubbles is a picture. Fusion dims the MODEL and the
view shows it; we do the same honestly: click two endpoints of a
view's projected geometry, and the bubble anchors itself in that
view — endpoints are stored in model millimetres PLUS as fractions of
the view's bounding box — so when the solid stretches, the bubble
slides to the new corner it measures, never a stale number or a
dangling arrow.

Rendering is draughtsman-standard: thin extension lines to the
points, dimension line with arrowheads, and the millimetre value in a
gap over the line. Text is the MEASURED distance re-read from the
live model each repaint, so the number can never lie.

Honest scope: linear dimensions (radius/diameter bubbles later),
endpoint snapping on the projected chains, and DXF export carries the
dimension lines (the paper text is the PNG's job).
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt                              # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap                 # noqa: E402
from PySide6.QtTest import QTest                                    # noqa: E402
from PySide6.QtWidgets import QApplication                          # noqa: E402

from tracer.core import drawing                                     # noqa: E402
from tracer.core.document import PrimitiveFeature                   # noqa: E402


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
        w._discard_guard = lambda: True
        w.close()
        r.close()
    except Exception:
        raise


def _box_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Block", kind="box",
        dims={"dx": 40.0, "dy": 20.0, "dz": 10.0}))
    win.recompute()
    win.action_new_drawing()
    qapp.processEvents()
    return win.drawing


def _page_clicks(cv, qapp, pts):
    for x, y in pts:                          # sheet-mm -> widget px
        sp = cv.s2p(x, y).toPoint()
        QTest.mouseClick(cv, Qt.LeftButton,
                         Qt.KeyboardModifier.NoModifier, sp)
        qapp.processEvents()


# ------------------------------------------------------------- frames

def test_view_frames_round_trip(win, qapp):
    cv = _box_sheet(win, qapp)
    frames = cv.frames()
    assert set(frames) == set(drawing.STANDARD)
    sc, off = frames["top"]                   # scale + page offset
    chains = cv.chains("top")
    p = chains[0][0]                          # a model-space corner
    page = (p[0] * sc + off[0], p[1] * sc + off[1])
    back = cv.page_to_model("top", page)
    assert back == pytest.approx(p, abs=1e-6)


# ------------------------------------------------------------- bubbles

def test_two_endpoint_clicks_lay_a_dimension(win, qapp):
    cv = _box_sheet(win, qapp)
    cv.set_dim_mode(True)
    # bottom corners of the TOP view: model (0,0) and (40,0)
    sc, off = cv.frames()["top"]
    _page_clicks(cv, qapp, [(off[0], off[1]), (off[0] + 40.0 * sc,
                                                  off[1])])
    g = win.doc.drawings[-1]
    assert len(g["dims"]) == 1
    d = g["dims"][0]
    assert d["view"] == "top"
    assert abs(math.dist(d["a"], d["b"]) - 40.0) < 0.5
    assert "40" in d["text"]


def test_snap_grabs_the_nearest_chain_endpoint(win, qapp):
    cv = _box_sheet(win, qapp)
    cv.set_dim_mode(True)
    sc, off = cv.frames()["top"]
    a = (off[0] + 0.4, off[1] - 0.3)           # 0.5 mm off the corner
    b = (off[0] + 40.0 * sc, off[1] + 20.0 * sc)
    _page_clicks(cv, qapp, [a, b])
    d = win.doc.drawings[-1]["dims"][0]
    # snapped to the exact corners: 40x20 diagonal
    assert abs(math.dist(d["a"], d["b"]) - math.hypot(40, 20)) < 0.5


def test_bubble_text_follows_the_live_model(win, qapp):
    cv = _box_sheet(win, qapp)
    cv.set_dim_mode(True)
    sc, off = cv.frames()["top"]
    _page_clicks(cv, qapp, [(off[0], off[1]), (off[0] + 40.0 * sc,
                                                  off[1])])
    g = win.doc.drawings[-1]
    assert "40" in g["dims"][0]["text"]
    win.doc.features[0].dims["dx"] = 80.0      # stretch the block
    win.recompute()
    qapp.processEvents()
    assert "80" in g["dims"][0]["text"]        # the number can't lie
    assert "40" not in g["dims"][0]["text"]


def test_dims_round_trip_through_the_file(win, qapp):
    cv = _box_sheet(win, qapp)
    cv.set_dim_mode(True)
    sc, off = cv.frames()["top"]
    _page_clicks(cv, qapp, [(off[0], off[1]), (off[0] + 40.0 * sc,
                                                  off[1])])
    from tracer.core.document import Document
    back = Document.from_dict(win.doc.to_dict())
    assert back.drawings[-1]["dims"][0]["view"] == "top"


def test_undo_removes_the_last_bubble(win, qapp):
    cv = _box_sheet(win, qapp)
    cv.set_dim_mode(True)
    sc, off = cv.frames()["top"]
    _page_clicks(cv, qapp, [(off[0], off[1]), (off[0] + 40.0 * sc,
                                                  off[1])])
    win.undo()
    qapp.processEvents()
    assert win.doc.drawings[-1]["dims"] == []


def test_bubbles_paint_on_the_sheet(win, qapp):
    cv = _box_sheet(win, qapp)
    cv.set_dim_mode(True)
    sc, off = cv.frames()["top"]
    _page_clicks(cv, qapp, [(off[0], off[1]), (off[0] + 40.0 * sc,
                                                  off[1])])
    cv.resize(700, 500)
    pm = QPixmap(700, 500)
    pm.fill(QColor(30, 30, 34))
    p = QPainter(pm)
    cv.paintPage(p)
    p.end()
    img = pm.toImage()
    dark = sum(1 for x in range(0, 700, 2) for y in range(0, 500, 2)
               if img.pixelColor(x, y).lightness() < 90)
    assert dark > 60          # ink: geometry + arrows + text


def test_dim_mode_off_means_plain_drag(win, qapp):
    cv = _box_sheet(win, qapp)
    assert cv._dim_mode is False
    sc, off = cv.frames()["top"]
    before = win.doc.drawings[-1]["dims"]
    _page_clicks(cv, qapp, [(off[0], off[1]),
                            (off[0] + 20.0 * sc, off[1] - 10.0 * sc)])
    assert win.doc.drawings[-1]["dims"] == before == []


def test_dxf_export_carries_dimension_lines(win, qapp, tmp_path):
    cv = _box_sheet(win, qapp)
    cv.set_dim_mode(True)
    sc, off = cv.frames()["top"]
    _page_clicks(cv, qapp, [(off[0], off[1]), (off[0] + 40.0 * sc,
                                                  off[1])])
    out = str(tmp_path / "dimmed.dxf")
    win.export_drawing(out)
    qapp.processEvents()
    from tracer.core import import2d
    ops = import2d.read(out)
    lines = [o for o in ops if o[0] in ("line", "poly")]
    assert len(lines) >= 7                    # 6 chains + dimension ink
