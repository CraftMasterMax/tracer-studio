"""M103 — the R bubble: arcs get dimensions too.

M95 can only dimension a circle that projects as its OWN closed loop.
But arcs in real parts never ride alone: a scallop on an edge, a
filleted corner, a boss half-buried in a wall — silhouette chains are
whole boundary loops, so the arc arrives threaded with straight runs
(and the junctions are often TANGENT, zero turn).  M103 cuts arcs out
of chains by CURVATURE: mark every vertex that turns (>3° — straight
runs don't, 64-gon walls turn 5.6° each), take maximal marked runs,
fit each with an algebraic circle, and refuse what lies: residuals
beyond 10% of r, spans under 25° or over 330° (a full ring is
fit_circle's business), radii absurdly larger than the run's own
extent (collinear dust).  Closed loops are rotated open at a straight
vertex first, so the rounded-CORNER of a plate is found inside the
one loop that traces the whole outline.

One tap on an arc lays R 6.00; the bubble re-finds its live arc every
repaint (widen the scallop 6->9 and the number follows alone), the
leader paints centre-to-rim, DXF carries it, and iso — where arcs
are ellipse fragments — refuses, exactly as the Ø rule already does.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                   # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtCore import Qt                               # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap          # noqa: E402

from tracer.core import drawing                              # noqa: E402
from tracer.core.document import (Document,                  # noqa: E402
                                  PrimitiveFeature)


def _scallop():
    """40x20x5 plate with an r6 scallop centred on the y=0 edge AND a
    through bore r4 at (20,13) — one model, one arc, one circle (kept
    clear of the arc's tap so the circle never claims its click)."""
    box = PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 40.0, "dy": 20.0, "dz": 5.0})
    sc = PrimitiveFeature(name="s", kind="cylinder",
                          dims={"radius": 6.0, "height": 5.0},
                          placement=(20.0, 0.0, 0.0))
    bore = PrimitiveFeature(name="c", kind="cylinder",
                            dims={"radius": 4.0, "height": 5.0},
                            placement=(20.0, 13.0, 0.0))
    return box.build().subtract(sc.build()).subtract(bore.build())


# ---------------------------------------------------------------- core

def test_find_arcs_cuts_the_scallop_out_of_its_loop():
    chains = drawing.project_view(_scallop(), view="top")
    arcs = drawing.find_arcs(chains)
    assert len(arcs) == 1        # the bore is a full ring: not an arc
    (cx, cy), r = arcs[0]
    assert (cx, cy) == pytest.approx((20.0, 0.0), abs=0.2)
    assert r == pytest.approx(6.0, rel=0.02)


def test_find_arcs_refuses_squares_and_full_rings():
    square = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0),
              (0.0, 0.0)]
    assert drawing.find_arcs([square]) == []
    t = np.linspace(0.0, 2 * math.pi, 65)
    ring = [(20.0 + 6.0 * math.cos(a), 6.0 * math.sin(a)) for a in t]
    ring.append(ring[0])
    assert drawing.find_arcs([ring]) == []      # a circle is NOT an arc
    line = [(float(i), 0.0) for i in range(30)]
    assert drawing.find_arcs([line]) == []


def test_find_arcs_refuses_zigzag_and_dust():
    zig = [(float(i), 0.0 if i % 2 else 3.0) for i in range(24)]
    assert drawing.find_arcs([zig]) == []
    nearly = [(float(i), 1e-3 * math.sin(i)) for i in range(30)]
    assert drawing.find_arcs([nearly]) == []    # dust fits a lie: r too big


def test_find_arcs_finds_a_rounded_corner_of_a_closed_outline():
    # a 40x20 loop whose (40,20) corner rounds at r5
    pts = [(0.0, 0.0), (40.0, 0.0), (40.0, 15.0)]
    for a in range(1, 16):                       # (40,15) -> (35,20)
        t = math.radians(90.0 * a / 16.0)
        pts.append((35.0 + 5.0 * math.cos(t), 15.0 + 5.0 * math.sin(t)))
    pts += [(0.0, 20.0), (0.0, 0.0)]
    arcs = drawing.find_arcs([pts])
    assert len(arcs) == 1
    (cx, cy), r = arcs[0]
    assert (cx, cy) == pytest.approx((35.0, 15.0), abs=0.3)
    assert r == pytest.approx(5.0, rel=0.05)


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
        r.ctx.release()
    except Exception:
        raise


def _scallop_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Plate", kind="box",
        dims={"dx": 40.0, "dy": 20.0, "dz": 5.0}))
    win.doc.features.append(PrimitiveFeature(
        name="Scallop", kind="cylinder",
        dims={"radius": 6.0, "height": 5.0},
        placement=(20.0, 0.0, 0.0), op="subtract"))
    win.doc.features.append(PrimitiveFeature(
        name="Bore", kind="cylinder",
        dims={"radius": 4.0, "height": 5.0},
        placement=(20.0, 13.0, 0.0), op="subtract"))
    win.recompute()
    win.action_new_drawing()
    qapp.processEvents()
    return win.drawing


def _click_page(cv, qapp, x, y):
    sp = cv.s2p(x, y).toPoint()
    QTest.mouseClick(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, sp)
    qapp.processEvents()


def _top_pt(cv, mx, my):
    sc, off = cv.frames()["top"]
    return (mx * sc + off[0], my * sc + off[1])


def test_one_click_on_the_scallop_lays_a_radius(win, qapp):
    cv = _scallop_sheet(win, qapp)
    cv.set_dim_mode(True)
    _click_page(cv, qapp, *_top_pt(cv, 20.0, 6.0))   # arc's apex
    dims = win.doc.drawings[-1]["dims"]
    assert len(dims) == 1                  # ONE click: like the Ø rule
    d = dims[0]
    assert d.get("radius") is True
    assert d["view"] == "top"
    assert d["text"] == "R 6.00"


def test_the_circle_in_the_same_view_still_lays_a_diameter(win, qapp):
    cv = _scallop_sheet(win, qapp)
    cv.set_dim_mode(True)
    k = math.sqrt(0.5)
    _click_page(cv, qapp, *_top_pt(cv, 20.0 + 4.0 * k, 13.0 + 4.0 * k))
    d = win.doc.drawings[-1]["dims"][-1]
    assert d.get("diameter") is True and "\u00d8 8.00" in d["text"]
    # and a second tap on the arc adds the R: the kinds coexist
    _click_page(cv, qapp, *_top_pt(cv, 20.0, 6.0))
    dims = win.doc.drawings[-1]["dims"]
    assert len(dims) == 2
    assert dims[-1]["text"] == "R 6.00"


def test_radius_follows_the_live_model(win, qapp):
    cv = _scallop_sheet(win, qapp)
    cv.set_dim_mode(True)
    _click_page(cv, qapp, *_top_pt(cv, 20.0, 6.0))
    d = win.doc.drawings[-1]["dims"][0]
    assert d["text"] == "R 6.00"
    win.doc.features[1].dims["radius"] = 9.0     # widen the scallop
    win.recompute()
    qapp.processEvents()
    assert d["text"] == "R 9.00"                 # re-found, never stale


def test_iso_view_refuses_arc_bubbles(win, qapp):
    cv = _scallop_sheet(win, qapp)
    cv.set_dim_mode(True)
    d3, X, Y = drawing._basis("iso")
    P = np.array([20.0 + 6.0 * math.cos(math.radians(45.0)),
                  6.0 * math.sin(math.radians(45.0)), 2.5])
    sc, off = cv.frames()["iso"]
    _click_page(cv, qapp, (P @ X) * sc + off[0], (P @ Y) * sc + off[1])
    assert win.doc.drawings[-1].get("dims", []) == []   # ellipses lie


def test_radius_bubble_paints_its_leader(win, qapp):
    cv = _scallop_sheet(win, qapp)
    cv.set_dim_mode(True)
    _click_page(cv, qapp, *_top_pt(cv, 20.0, 6.0))
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
    assert red > 15                    # leader, arrowhead, and R text


def test_radius_round_trips_through_the_file(win, qapp):
    cv = _scallop_sheet(win, qapp)
    cv.set_dim_mode(True)
    _click_page(cv, qapp, *_top_pt(cv, 20.0, 6.0))
    back = Document.from_dict(win.doc.to_dict())
    d = back.drawings[-1]["dims"][0]
    assert d["radius"] is True and d["text"] == "R 6.00"


def test_dxf_export_carries_the_radius_leader(win, qapp, tmp_path):
    cv = _scallop_sheet(win, qapp)
    out0 = str(tmp_path / "plain.dxf")
    win.export_drawing(out0, ext=".dxf")
    from tracer.core import import2d
    before = [o for o in import2d.read(out0) if o[0] in ("poly", "line")]
    cv.set_dim_mode(True)
    _click_page(cv, qapp, *_top_pt(cv, 20.0, 6.0))
    out = str(tmp_path / "arc.dxf")
    win.export_drawing(out, ext=".dxf")
    ops = [o for o in import2d.read(out) if o[0] in ("poly", "line")]
    assert len(ops) >= len(before) + 1          # the leader travelled
    assert any(o[0] == "line" for o in ops[len(before):])
