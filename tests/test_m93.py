"""M93 — Drawings phase 1: the silhouette projection + a page.

The maker's second document: sketch → solid is half the job; the
other half is the drawing. Mesh-kernel honesty drives the method —
no B-rep edges to harvest, so views are VIEW-DEPENDENT SILHOUETTES:
an edge of the triangle soup is drawn where one side faces the viewer
and the other doesn't (away or grazing) — top faces against walls,
hole rims against tops. Boolean tessellations scatter Steiner points
along rims, so raw segments are chained at their endpoints and
collinear runs merged: a plate-with-hole reads as four walls, one
square, one circle — not 260 crumbs.

Standard layout (Fusion's layout assistant in spirit): top, front,
right placed in third-angle-ish page slots, auto-fitted to the page
with margins; an iso view rides along. The drawing stores only its
NAME + PAPER — views re-derive from the live model every repaint, so
the drawing is never stale (exactly how Fusion views track rebuilds).

M93 scope: the projection core, Document.drawings, the page canvas
(zoom/pan), PNG + DXF export. Dimension bubbles on the page are M94.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QPainter, QPixmap                    # noqa: E402
from PySide6.QtWidgets import QApplication                            # noqa: E402

from tracer.core import drawing                                        # noqa: E402
from tracer.core.document import (Document, PrimitiveFeature,          # noqa: E402
                                  RevolveFeature)


def _plate():
    box = PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 40.0, "dy": 20.0, "dz": 5.0})
    cyl = PrimitiveFeature(name="c", kind="cylinder",
                           dims={"radius": 4.0, "height": 5.0},
                           placement=(20.0, 10.0, 0.0))
    return box.build().subtract(cyl.build())


def _closed(chains):
    return [c for c in chains
            if len(c) > 3 and np.allclose(c[0], c[-1], atol=1e-6)]


def _area(L):
    P = np.asarray(L)
    x, y = P[:, 0], P[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


# ---------------------------------------------------------------- projection

def test_top_view_is_a_square_with_a_hole():
    chains = drawing.project_view(_plate(), view="top")
    loops = _closed(chains)
    assert len(loops) == 2                     # outer rim + hole rim
    areas = sorted(_area(L) for L in loops)
    assert areas[1] == pytest.approx(800.0, rel=1e-2)     # 40 x 20
    assert areas[0] == pytest.approx(math.pi * 16.0, rel=5e-2)  # hole


def test_front_view_shows_the_visible_hole_walls():
    chains = drawing.project_view(_plate(), view="front")
    # outer 40x5 rectangle + the bore's facing-region boundary (16..24)
    loops = _closed(chains)
    assert len(loops) >= 2
    assert any(7.0 < max(p[0] for p in L) - min(p[0] for p in L) < 17.0
               and 3.0 < max(p[1] for p in L) - min(p[1] for p in L) < 7.0
               for L in loops)


def test_views_cover_the_four_named_cameras():
    p = _plate()
    for v in ("top", "front", "right", "iso"):
        chains = drawing.project_view(p, view=v)
        assert chains, f"{v} produced nothing"
        span = np.vstack([np.asarray(c) for c in chains])
        assert span.max(axis=0)[0] - span.min(axis=0)[0] > 10.0


def test_collinear_runs_merge_and_segments_chain():
    # box only: top view must be FOUR walls after merge, not a crumb field
    box = PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 40.0, "dy": 20.0, "dz": 5.0})
    chains = drawing.project_view(box.build(), view="top")
    loops = _closed(chains)
    assert len(loops) == 1
    assert len(loops[0]) <= 8            # merged collinear runs, ~4 corners


def test_fit_scale_holds_the_page():
    views = {"top": drawing.project_view(_plate(), view="top")}
    sc = drawing.fit_scale(views, page="A4", margin=10.0)
    assert 0.1 < sc <= 1.0
    pts = np.vstack([np.asarray(p) * sc for c in views["top"] for p in c])
    w, h = pts[:, 0].max() - pts[:, 0].min(), pts[:, 1].max() - pts[
        :, 1].min()
    assert w <= 297 - 2 * 10 and h <= 210 - 2 * 10    # A4 landscape inner


# -------------------------------------------------------------- document

def test_drawings_round_trip_through_the_file():
    d = Document(title="dwg")
    d.drawings = [{"name": "Drawing1", "page": "A3"}]
    back = Document.from_dict(d.to_dict())
    assert back.drawings == [{"name": "Drawing1", "page": "A3"}]


def test_pre_m93_files_default_to_no_drawings():
    raw = Document(title="old").to_dict()
    raw.pop("drawings", None)
    assert Document.from_dict(raw).drawings == []


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
        w._discard_guard = lambda: True
        w.close()
        r.ctx.release()
    except Exception:
        raise


def _box_doc(win):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Block", kind="box",
        dims={"dx": 40.0, "dy": 20.0, "dz": 10.0}))
    win.recompute()
    QApplication.instance().processEvents()


def test_new_drawing_verb_opens_a_page(win, qapp):
    _box_doc(win)
    win.action_new_drawing()
    qapp.processEvents()
    assert win.doc.drawings and win.doc.drawings[-1]["name"] == "Drawing1"
    assert "Drawing1" in win.status.currentMessage()
    assert win.drawing is not None             # the canvas is live
    assert win.stack.currentWidget() is win._drawing_page


def test_drawing_re_derives_when_the_model_moves(win, qapp):
    _box_doc(win)
    win.action_new_drawing()
    qapp.processEvents()
    cvd = win.drawing
    chains0 = cvd.chains()                     # live snapshot
    win.doc.features[0].dims["dx"] = 80.0
    win.recompute()
    qapp.processEvents()
    chains1 = cvd.chains()
    w0 = max(p[0] for c in chains0 for p in c) - min(
        p[0] for c in chains0 for p in c)
    w1 = max(p[0] for c in chains1 for p in c) - min(
        p[0] for c in chains1 for p in c)
    assert w1 == pytest.approx(w0 * 2.0, rel=1e-3)   # never stale


def test_drawing_paints_a_sheet_without_crashing(win, qapp):
    _box_doc(win)
    win.action_new_drawing()
    qapp.processEvents()
    cvd = win.drawing
    cvd.resize(600, 450)
    pm = QPixmap(600, 450)
    pm.fill(QColor(30, 30, 34))
    p = QPainter(pm)
    cvd.paintPage(p)                           # raises LOUDLY if broken
    p.end()
    img = pm.toImage()
    paper = sum(1 for x in range(0, 600, 5) for y in range(0, 450, 5)
                if img.pixelColor(x, y).lightness() > 180)
    assert paper > 400                         # white sheet fills the view


def test_drawing_exports_png_and_dxf(win, qapp, tmp_path):
    _box_doc(win)
    win.action_new_drawing()
    qapp.processEvents()
    png = str(tmp_path / "d.png")
    dxf = str(tmp_path / "d.dxf")
    win.export_drawing(png)
    win.export_drawing(dxf)
    qapp.processEvents()
    import os
    assert os.path.getsize(png) > 1000
    from tracer.core import import2d
    ops = import2d.read(dxf)                   # the drawing is a profile!
    # a plain box: 3 orthographic rectangles + iso hexagon + 2 crease
    # branches = 6 polylines minimum
    assert sum(1 for o in ops if o[0] in ("line", "poly")) >= 6
