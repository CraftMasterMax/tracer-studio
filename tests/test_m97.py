"""M97 — hidden lines: the sheet learns to dashed the back.

A drawing that only shows visible edges is a shadow puppet. Real
draughting dashes what the body hides. We do the honest crease pass:
an edge is HIDDEN when neither adjacent face looks at the viewer
(both face away) AND the fold is sharp (>40°, so a smooth wall never
becomes a mesh wireframe), AND its midpoint falls strictly INSIDE the
front-facing silhouette region — coincident rim-to-rim projections
(through holes, convex outlines) are clipped away and deduped,
exactly what the draughting standard expects.

The result: a box's iso view grows its three back edges as a dashed
chain that meets at the hidden corner; the plate's top view stays
clean (a through hole has no hidden geometry); and everything else
about the sheet — live re-derivation, moves, bubbles, export — holds
for hidden chains too, because they are projections, never stored
paper.

Honest scope: hidden BACK CREASES only; grazing back edges (an
interior bore's profile lines in a front view) are a refinement
ahead; hidden lines are recomputed live, never serialised.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap          # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402

from tracer.core import drawing                              # noqa: E402
from tracer.core.document import Document, PrimitiveFeature  # noqa: E402


def _box():
    return PrimitiveFeature(name="b", kind="box",
                            dims={"dx": 40.0, "dy": 20.0,
                                  "dz": 10.0}).build()


def _plate():
    box = PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 40.0, "dy": 20.0, "dz": 5.0})
    cyl = PrimitiveFeature(name="c", kind="cylinder",
                           dims={"radius": 4.0, "height": 5.0},
                           placement=(20.0, 10.0, 0.0))
    return box.build().subtract(cyl.build())


# ---------------------------------------------------------------- core

def test_iso_box_grows_its_three_back_edges():
    from shapely.geometry import MultiPoint, Point
    hidden = drawing.project_hidden(_box(), view="iso")
    segs = sum(len(c) - 1 for c in hidden)
    assert segs == 3                      # the hidden corner's Y, dashed
    # every hidden chain lies inside the visible silhouette (hexagon —
    # which the chain walk delivers as open trails, so the region is
    # the hull of everything visible)
    vis = drawing.project_view(_box(), view="iso")
    pts = np.vstack([np.asarray(c, float) for c in vis])
    poly = MultiPoint(pts).convex_hull
    for c in hidden:
        for p in c:
            assert poly.buffer(-1e-9).contains(Point(p)) or \
                poly.boundary.distance(Point(p)) < 1e-6, p


def test_top_view_plate_is_clean_through_the_hole():
    # a through hole hides nothing: rims coincide and get clipped/deduped
    assert drawing.project_hidden(_plate(), view="top") == []


def test_front_view_box_has_no_hidden_lines():
    # convex body, orthographic face-on: back edges coincide with outline
    assert drawing.project_hidden(_box(), view="front") == []


def test_sphere_never_becomes_a_mesh_wireframe():
    sph = PrimitiveFeature(name="s", kind="sphere",
                           dims={"radius": 10.0},
                           placement=(0.0, 0.0, 10.0)).build()
    hidden = drawing.project_hidden(sph, view="iso")
    segs = sum(len(c) - 1 for c in hidden)
    assert segs <= 1                      # smooth walls: nothing dashed


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


def _box_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Block", kind="box",
        dims={"dx": 40.0, "dy": 20.0, "dz": 10.0}))
    win.recompute()
    win.action_new_drawing()
    qapp.processEvents()
    return win.drawing


def test_canvas_offers_hidden_views(win, qapp):
    cv = _box_sheet(win, qapp)
    hid = cv.hidden_views()
    assert "iso" in hid and sum(len(c) - 1 for c in hid["iso"]) == 3
    assert hid.get("top", []) == []          # orthographic face-on: none


def test_hidden_lines_follow_a_drag_and_the_live_model(win, qapp):
    cv = _box_sheet(win, qapp)
    cv.resize(800, 600)
    qapp.processEvents()
    from PySide6.QtCore import QPoint
    before = cv.hidden_page("iso")[0][0]           # page-space first point
    # drag the iso view: hidden lines travel with it
    placed = cv.placed()
    p = placed["iso"]
    ctr = cv.s2p(p["off"][0] + 0.5 * (p["min"][0] + p["max"][0]),
                 p["off"][1] + 0.5 * (p["min"][1] + p["max"][1])).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                     ctr)
    QTest.mouseMove(cv, ctr + QPoint(60, 0))
    QTest.mouseRelease(cv, Qt.LeftButton,
                       Qt.KeyboardModifier.NoModifier, ctr + QPoint(60, 0))
    qapp.processEvents()
    after = cv.hidden_page("iso")[0][0]
    assert after[0] - before[0] == pytest.approx(60.0 / cv._zoom, abs=0.6)
    # and the model: squash the box flat — hidden Y survives but shifts
    win.doc.features[0].dims["dz"] = 2.0
    win.recompute()
    qapp.processEvents()
    assert sum(len(c) - 1 for c in cv.hidden_views()["iso"]) == 3


def test_hidden_lines_paint_dashed_on_the_sheet(win, qapp):
    cv = _box_sheet(win, qapp)
    cv.resize(700, 500)
    pm = QPixmap(700, 500)
    pm.fill(QColor(30, 30, 34))
    p = QPainter(pm)
    cv.paintPage(p)
    p.end()
    img = pm.toImage()
    grey = 0
    for x in range(0, 700, 2):
        for y in range(0, 500, 2):
            q = img.pixelColor(x, y)
            if (abs(q.red() - 140) <= 35 and abs(q.green() - 144) <= 35
                    and abs(q.blue() - 150) <= 35):
                grey += 1
    assert grey > 12                # the dashed back-corner ink


def test_dxf_export_carries_hidden_geometry(win, qapp, tmp_path):
    cv = _box_sheet(win, qapp)
    out = str(tmp_path / "sheet.dxf")
    win.export_drawing(out)
    from tracer.core import import2d
    ops = import2d.read(out)
    polys = [o for o in ops if o[0] in ("poly", "line")]
    # 6 visible chains + the dashed corner (the walk splits the Y into
    # two open trails: 3 edges, 4 odd nodes) must all reach the paper
    assert len(polys) >= 8


def test_hidden_is_never_stored_paper(win, qapp):
    cv = _box_sheet(win, qapp)
    assert "hidden" not in win.doc.drawings[-1]     # live, like the views
    back = Document.from_dict(win.doc.to_dict())
    assert back.drawings[-1].keys() == win.doc.drawings[-1].keys()
