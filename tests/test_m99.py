"""M99 — Thicken: an open sketch becomes a solid wall.

Print-makers live here: a drawn path that should be a 2 mm wall —
a bracket rib, a patch plate, a stiffener around a cover. Fusion has
Patch/Thicken for surfaces; on the mesh kernel the honest twin is a
buffer: every OPEN chain of the sketch is thickened to `thickness`
(butt caps so a straight wall is exactly length × thickness, round
joins so corners bend like sheet, never spike), overlapping chains
union into one wall, and the strip extrudes `depth` along the sketch
plane's normal. Closed loops are NOT thickened — that is Extrude's
job, and the verb says so rather than building something silly.

The feature is parametric like its siblings: the sketch payload rides
along (frozen, sweep-style — re-run Thicken to re-extract), editing
thickness or depth re-builds, the file round-trips, undo captures the
mint.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402

from tracer.core import thicken                              # noqa: E402
from tracer.core.document import Document, ThickenFeature    # noqa: E402
from tracer.core.sketch.model import SketchModel             # noqa: E402


# ---------------------------------------------------------------- core

def test_straight_wall_is_exact():
    solids = thicken.thicken_solids([[(0, 0), (100, 0)]], 2.0, 10.0)
    assert len(solids) == 1
    s = solids[0]
    assert s.volume == pytest.approx(2000.0, rel=1e-6)   # butt caps
    lo, hi = s.bounding_box
    assert lo[0] == pytest.approx(0.0, abs=1e-6)
    assert hi[0] == pytest.approx(100.0, abs=1e-6)
    assert hi[1] - lo[1] == pytest.approx(2.0, abs=1e-6)


def test_corner_bends_round_not_spiked():
    solids = thicken.thicken_solids(
        [[(0, 0), (50, 0), (50, 30)]], 2.0, 5.0)
    assert len(solids) == 1
    v = solids[0].volume
    # straight stock (50+30)*2*5 = 800; the round outer join adds a
    # sliver (≈ r²(π/4 − 1)·depth ≈ 0.14), the inner one trims equal —
    # never a mitre spike (which would overshoot by r² ≈ 20)
    assert 795.0 < v < 806.0


def test_overlapping_chains_merge_into_one_wall():
    solids = thicken.thicken_solids(
        [[(0, 0), (40, 0)], [(20, 0), (60, 0)]], 2.0, 4.0)
    assert len(solids) == 1                     # union: one polygon
    assert solids[0].volume == pytest.approx(60 * 2 * 4, rel=1e-6)


def test_open_chains_takes_the_opens_and_skips_the_loops():
    m = SketchModel()
    a, b = m.point(0.0, 0.0), m.point(30.0, 0.0)
    m.sketch.line(a, b)
    p0, p1 = m.point(50.0, 0.0), m.point(70.0, 15.0)
    m.add_rect(p0, p1)                          # a closed helper rect
    chains = thicken.open_chains(m)
    assert len(chains) == 1
    assert len(chains[0]) == 2
    assert chains[0][0] == pytest.approx((0.0, 0.0), abs=1e-6) or \
        chains[0][-1] == pytest.approx((0.0, 0.0), abs=1e-6)


def test_open_chains_refuses_a_purely_closed_sketch():
    m = SketchModel()
    p0, p1 = m.point(0.0, 0.0), m.point(20.0, 10.0)
    m.add_rect(p0, p1)
    with pytest.raises(ValueError) as e:
        thicken.open_chains(m)
    assert "Extrude" in str(e.value)            # points at the right verb


def test_arcs_are_sampled_into_the_chain():
    m = SketchModel()
    ar = m.sketch.arc(m.point(0.0, 0.0), m.point(10.0, 6.0),
                      m.point(20.0, 0.0))
    m.sketch.line(ar.b, m.point(40.0, 0.0))
    chains = thicken.open_chains(m)
    assert len(chains) == 1
    assert len(chains[0]) > 3                   # the arc left crumbs in


def test_thicken_feature_is_parametric_and_watertight():
    f = ThickenFeature(name="Wall", thickness=2.0, depth=5.0,
                       paths=[[[0, 0], [40, 0]]])
    s = f.build()
    assert s.volume == pytest.approx(40 * 2 * 5, rel=1e-6)
    f.thickness = 4.0
    assert f.build().volume == pytest.approx(40 * 4 * 5, rel=1e-6)


def test_thicken_feature_round_trips_through_the_file():
    d = Document(title="wall")
    d.features.append(ThickenFeature(
        name="Wall", thickness=3.0, depth=6.0,
        paths=[[[0, 0], [25, 0], [25, 10]]]))
    back = Document.from_dict(d.to_dict())
    f = back.features[0]
    assert isinstance(f, ThickenFeature)
    assert f.thickness == 3.0 and f.depth == 6.0
    assert f.build().volume == pytest.approx(
        (25 + 10) * 3 * 6, abs=(25 + 10) * 3 * 6 * 0.02)


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


def _click(cv, qapp, x, y):
    sp = cv.w2s(x, y).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, sp)
    qapp.processEvents()
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, sp)
    qapp.processEvents()


def test_action_thicken_mints_the_wall_and_the_solid(win, qapp,
                                                     monkeypatch):
    from tracer.ui import cmddialog
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    cv.set_grid_snap(False)
    cv.set_tool("line")
    _click(cv, qapp, 0, 0)
    _click(cv, qapp, 50, 0)
    cv.set_tool("select")                       # end the line chain
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"thickness": 4.0, "depth": 5.0})
    win.action_thicken()
    qapp.processEvents()
    feats = [f for f in win.doc.features if isinstance(f, ThickenFeature)]
    assert len(feats) == 1
    assert win.doc.result.volume == pytest.approx(50 * 4 * 5, rel=1e-3)


def test_action_thicken_refuses_closed_sketches_honestly(
        win, qapp, monkeypatch):
    import tracer.ui.mainwindow as mw
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    cv.set_grid_snap(False)
    cv.set_tool("rect")
    _click(cv, qapp, 0, 0)
    _click(cv, qapp, 20, 10)
    qapp.processEvents()
    seen = {}
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.update(
                            msg=str(a[2] if len(a) > 2 else ""))))
    win.action_thicken()
    assert seen and not any(isinstance(f, ThickenFeature)
                            for f in win.doc.features)


def test_re_run_updates_in_place_and_undo_undoes(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    cv.set_grid_snap(False)
    cv.set_tool("line")
    _click(cv, qapp, 0, 0)
    _click(cv, qapp, 30, 0)
    cv.set_tool("select")
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"thickness": 2.0, "depth": 4.0})
    win.action_thicken()
    qapp.processEvents()
    n0 = len(win.doc.features)
    win.action_thicken()                        # re-thicken same sketch
    qapp.processEvents()
    assert len(win.doc.features) == n0          # updated, never stacked
    win._show_page(win.viewport)                # Back, then Ctrl+Z×2
    win.undo()
    qapp.processEvents()
    win.undo()
    qapp.processEvents()
    assert not any(isinstance(f, ThickenFeature)
                   for f in win.doc.features)
