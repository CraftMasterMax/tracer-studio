"""M95 — diameter bubbles: the hole finally says Ø8.

M94 drew linear callouts; a maker's drawing is mostly holes. One click
on a projected circle lays a diameter dimension. Circles are fitted
from their projected silhouette chains (closed, square bbox, round);
the bubble remembers centre + travel direction, and every repaint
re-finds the live circle nearest its centre and re-reads the radius —
so redrilling the bore 4→7 takes the bubble to Ø 14.00 by itself, and
the number can't lie.

Honest scope: full circles on orthographic views only (an iso ellipse
is not fitted; arc R-bubbles later); the match is proximity-based
geometry-following, not named-entity attachment — delete the bore and
the bubble keeps its last honest measurement rather than silently
drifting; DXF export carries the arrow/leader ink, the paper text is
the PNG's job.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                              # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap        # noqa: E402
from PySide6.QtTest import QTest                           # noqa: E402
from PySide6.QtWidgets import QApplication                 # noqa: E402

from tracer.core import drawing                            # noqa: E402
from tracer.core.document import Document, PrimitiveFeature  # noqa: E402


def _plate():
    box = PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 40.0, "dy": 20.0, "dz": 5.0})
    cyl = PrimitiveFeature(name="c", kind="cylinder",
                           dims={"radius": 4.0, "height": 5.0},
                           placement=(20.0, 10.0, 0.0))
    return box.build().subtract(cyl.build())


# ---------------------------------------------------------------- fit

def test_fit_circle_finds_the_bore():
    chains = drawing.project_view(_plate(), view="top")
    hits = [f for f in (drawing.fit_circle(L) for L in chains)
            if f is not None]
    assert len(hits) == 1
    (cx, cy), r = hits[0]
    assert (cx, cy) == pytest.approx((20.0, 10.0), abs=0.15)
    assert r == pytest.approx(4.0, abs=0.15)


def test_fit_circle_refuses_the_square():
    chains = drawing.project_view(_plate(), view="top")
    loops = [L for L in chains if len(L) > 3
             and np.allclose(L[0], L[-1], atol=1e-6)]
    outer = max(loops, key=lambda L: max(p[0] for p in L))
    assert drawing.fit_circle(outer) is None


def test_fit_circle_refuses_open_chains_and_junk():
    assert drawing.fit_circle([(0, 0), (4, 0), (4, 4)]) is None
    assert drawing.fit_circle([(0, 0)] * 10) is None


# ------------------------------------------------------------------ UI

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


def _plate_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Plate", kind="box",
        dims={"dx": 40.0, "dy": 20.0, "dz": 5.0}))
    win.doc.features.append(PrimitiveFeature(
        name="Bore", kind="cylinder",
        dims={"radius": 4.0, "height": 5.0},
        placement=(20.0, 10.0, 0.0), op="subtract"))
    win.recompute()
    win.action_new_drawing()
    qapp.processEvents()
    return win.drawing


def _click_page(cv, qapp, x, y):
    sp = cv.s2p(x, y).toPoint()
    QTest.mouseClick(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, sp)
    qapp.processEvents()


def _bore_ring_pt(cv):
    """The bore rim at 45 degrees, in sheet-mm page coords."""
    sc, off = cv.frames()["top"]
    k = math.sqrt(0.5)
    return ((20.0 + 4.0 * k) * sc + off[0], (10.0 + 4.0 * k) * sc + off[1])


def test_one_click_on_the_bore_lays_a_diameter(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_dim_mode(True)
    _click_page(cv, qapp, *_bore_ring_pt(cv))
    dims = win.doc.drawings[-1]["dims"]
    assert len(dims) == 1                  # ONE click: no second pick
    d = dims[0]
    assert d.get("diameter") is True
    assert d["view"] == "top"
    assert "\u00d8" in d["text"] and "8.00" in d["text"]


def test_diameter_follows_the_live_model(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_dim_mode(True)
    _click_page(cv, qapp, *_bore_ring_pt(cv))
    d = win.doc.drawings[-1]["dims"][0]
    assert "8.00" in d["text"]
    win.doc.features[1].dims["radius"] = 7.0       # redrill the bore
    win.recompute()
    qapp.processEvents()
    assert "\u00d8 14.00" in d["text"]             # live, never stale


def test_linear_flow_still_needs_two_clicks(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_dim_mode(True)
    sc, off = cv.frames()["top"]
    _click_page(cv, qapp, off[0], off[1])          # corner one
    assert win.doc.drawings[-1]["dims"] == []      # still pending
    _click_page(cv, qapp, off[0] + 40.0 * sc, off[1])
    dims = win.doc.drawings[-1]["dims"]
    assert len(dims) == 1 and not dims[0].get("diameter")


def test_diameter_round_trips_and_undoes(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_dim_mode(True)
    _click_page(cv, qapp, *_bore_ring_pt(cv))
    back = Document.from_dict(win.doc.to_dict())
    assert back.drawings[-1]["dims"][0].get("diameter") is True
    win.undo()
    qapp.processEvents()
    assert win.doc.drawings[-1]["dims"] == []


def test_diameter_bubble_paints_its_glyph(win, qapp):
    cv = _plate_sheet(win, qapp)
    cv.set_dim_mode(True)
    _click_page(cv, qapp, *_bore_ring_pt(cv))
    cv.resize(700, 500)
    pm = QPixmap(700, 500)
    pm.fill(QColor(30, 30, 34))
    p = QPainter(pm)
    cv.paintPage(p)
    p.end()
    img = pm.toImage()
    red = 0
    for x in range(0, 700, 2):
        for y in range(0, 500, 2):
            q = img.pixelColor(x, y)
            if (abs(q.red() - 195) <= 45 and abs(q.green() - 60) <= 45
                    and abs(q.blue() - 60) <= 45):
                red += 1
    assert red > 20                    # arrows, leader, and the Ø text


def test_dxf_export_carries_the_diameter_ink(win, qapp, tmp_path):
    cv = _plate_sheet(win, qapp)
    plain = str(tmp_path / "plain.dxf")
    win.export_drawing(plain)                      # chains only
    cv.set_dim_mode(True)
    _click_page(cv, qapp, *_bore_ring_pt(cv))
    dimmed = str(tmp_path / "dim.dxf")
    win.export_drawing(dimmed)
    from tracer.core import import2d
    assert len(import2d.read(dimmed)) > len(import2d.read(plain))
