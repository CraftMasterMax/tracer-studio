"""M35 — Sweep (W): a circle piped along a drawn path (tubes, handles).

v1 keeps the profile circular — the one shape that sweeps with zero frame
ambiguity: each path station is a ring normal to the local tangent, on the
sketch normal + in-plane normal (rotation-minimising for planar paths, so
nothing rolls).  The path is the sketch's loose chain of connected lines/
arcs, open (capped tube) or a closed loop (endless ring, genus 1).  Sharp
corners physically round over ~2.5 diameters, so volumes track Pappus'
theorem — the kernel's proof: a quarter arc R=20 swept by r=3 lands at
98.5 % of (theta/2)*2*pi*R*pi*r^2, and a closed circle path gives a true
torus, genus 1, watertight.
"""
import json
import math

import numpy as np
import pytest

from tracer.core.document import Document, SweepFeature
from tracer.core.sweep import _arc_samples, path_chain, sweep_tube
from tracer.core.sketch.model import SketchModel


def _arc_path(r_major=20.0, a0=0.0, a1=90.0):
    mid = math.radians((a0 + a1) / 2)
    return _arc_samples((r_major * math.cos(math.radians(a0)),
                         r_major * math.sin(math.radians(a0))),
                        (r_major * math.cos(mid), r_major * math.sin(mid)),
                        (r_major * math.cos(math.radians(a1)),
                         r_major * math.sin(math.radians(a1))))


def _circle_sketch(radius=4.0):
    m = SketchModel()
    m.add_circle(m.point(0, 0), radius)
    return m


def _path_lines(m, coords):
    pts = [m.point(*c) for c in coords]
    for i in range(len(pts) - 1):
        m.add_line(pts[i], pts[i + 1])
    return pts


# ---- kernel -----------------------------------------------------------------

def test_straight_path_is_a_round_rod():
    rod = sweep_tube([(0, 0), (30, 0)], 2.0, False)
    assert rod.volume == pytest.approx(math.pi * 4 * 30, rel=0.01)
    assert rod.to_trimesh().is_watertight


def test_quarter_arc_sweeps_to_pappus_volume():
    tube = sweep_tube(_arc_path(), 3.0, False)
    want = (math.pi / 2) * 20 * math.pi * 9          # theta * R * area
    assert tube.volume == pytest.approx(want, rel=0.03)
    assert tube.to_trimesh().is_watertight


def test_closed_circle_path_is_a_true_torus():
    th = np.linspace(0, 2 * math.pi, 25, endpoint=True)
    ring = [(20 * math.cos(t), 20 * math.sin(t)) for t in th]
    tor = sweep_tube(ring, 3.0, True)
    assert tor.volume == pytest.approx(2 * math.pi * 20 * math.pi * 9,
                                       rel=0.04)
    assert tor.to_trimesh().is_watertight
    assert tor._m.genus() == 1                        # endless ring


def test_sharp_corner_rounds_like_bent_tubing():
    bend = sweep_tube([(0, 0), (30, 0), (30, 30)], 2.0, False)
    straight = math.pi * 4 * 60                       # two rods
    assert bend.to_trimesh().is_watertight
    assert 0.82 * straight < bend.volume < straight   # corner shortens


def test_arc_endpoint_samples_are_ordered_and_dense():
    pts = _arc_path()
    assert math.hypot(*pts[0]) == pytest.approx(20.0, abs=1e-6)
    assert math.hypot(*pts[-1]) == pytest.approx(20.0, abs=1e-6)
    assert len(pts) >= 7                              # ~every 15 degrees


# ---- path extraction ---------------------------------------------------------

def test_path_chain_walks_lines_in_order():
    m = _circle_sketch(4.0)
    _path_lines(m, [(-20, 0), (20, 0), (20, 15)])
    pts, closed = path_chain(m)
    assert not closed and len(pts) == 3
    assert tuple(pts[0]) == (-20.0, 0.0)
    assert tuple(pts[-1]) == (20.0, 15.0)


def test_path_chain_walks_a_mixed_line_arc_chain():
    m = _circle_sketch(3.0)
    a, b = m.point(0, 0), m.point(30, 0)
    m.sketch.arc(a, m.point(15, 10), b)
    m.add_line(b, m.point(30, 20))
    pts, closed = path_chain(m)
    assert not closed and len(pts) > 5                # arc tessellated
    assert np.allclose(sorted([pts[0], pts[-1]]),
                       [(0.0, 0.0), (30.0, 20.0)], atol=1e-9)


def test_rejections_are_specific():
    m = _circle_sketch()                              # no path
    with pytest.raises(ValueError, match="needs a path"):
        path_chain(m)
    m2 = _circle_sketch()
    m2.add_circle(m2.point(9, 9), 2.0)                # second circle
    _path_lines(m2, [(0, 0), (10, 0)])
    with pytest.raises(ValueError, match="exactly one circle"):
        path_chain(m2)
    m3 = _circle_sketch()
    p0, p1, p2, p3 = [m3.point(*u) for u in ((0, 0), (10, 0), (20, 0),
                                             (10, 10))]
    m3.add_line(p0, p1)
    m3.add_line(p1, p2)
    m3.add_line(p1, p3)                               # branch
    with pytest.raises(ValueError, match="branch"):
        path_chain(m3)


# ---- document feature ---------------------------------------------------------

def test_sweep_feature_builds_suppresses_and_roundtrips():
    d = Document("t")
    f = SweepFeature(name="sweep", radius=2.0,
                     path=[[0.0, 0.0], [15.0, 0.0], [30.0, 0.0]],
                     closed=False)
    d.add(f)
    vol = d.recompute().volume
    assert vol == pytest.approx(math.pi * 4 * 30, rel=0.01)
    d2 = Document.from_dict(json.loads(json.dumps(d.to_dict())))
    g = d2.features[0]
    assert isinstance(g, SweepFeature) and g.radius == 2.0
    assert abs(d2.recompute().volume - vol) < 1e-6
    f.suppressed = True
    d.recompute()
    assert d.result is None or d.result.volume == pytest.approx(0.0)


def test_sweep_on_a_sketch_plane_other_than_xy():
    from tracer.core.document import PrimitiveFeature
    d = Document("t")
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 40, "dz": 5}))
    d.add(SweepFeature(name="rail", radius=1.5,
                       path=[[0.0, 0.0], [40.0, 0.0]], closed=False,
                       plane="XZ", placement=(0.0, 3.0, 0.0)))
    after = d.recompute().volume
    assert after > 40 * 40 * 5                        # rod sits on the plate
    assert d.result.to_trimesh().is_watertight


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                      # noqa: E402
from PySide6.QtCore import Qt                                   # noqa: E402

from tracer.ui.mainwindow import MainWindow                     # noqa: E402
from tracer.ui.panels import PropertiesPanel                    # noqa: E402
from tracer.ui.renderer import SceneRenderer                    # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _sweep_sketch(win, qapp, coords=((-20, 0), (20, 0), (20, 25)),
                  circle=(0.0, -12.0, 3.0)):
    """Create a sketch via the API on the sketch page: circle + chain."""
    from tracer.core.sketch.model import SketchModel
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    m = win.sketch.model
    m.add_circle(m.point(*circle[:2]), circle[2])
    pts = [m.point(*c) for c in coords]
    for i in range(len(pts) - 1):
        m.add_line(pts[i], pts[i + 1])
    qapp.processEvents()
    return m


def test_action_sweep_creates_the_tube(win, qapp):
    _sweep_sketch(win, qapp)
    win.action_sweep()
    qapp.processEvents()
    sweeps = [f for f in win.doc.features
              if isinstance(f, SweepFeature)]
    assert len(sweeps) == 1
    assert sweeps[0].radius == 3.0 and not sweeps[0].closed
    assert win.doc.result.volume > 0
    assert "tube" in win.status.currentMessage()


def test_action_sweep_re_uses_the_same_feature(win, qapp):
    _sweep_sketch(win, qapp)
    win.action_sweep()
    win.action_sweep()                                # same sketch again
    sweeps = [f for f in win.doc.features
              if isinstance(f, SweepFeature)]
    assert len(sweeps) == 1


def test_action_sweep_warns_when_the_recipe_is_wrong(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(a[2])))
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    win.action_sweep()                                # empty sketch
    assert seen and "circle" in seen[-1]


def test_sweep_survives_save_open_roundtrip(win, qapp, tmp_path):
    from tracer.core import io as fio
    _sweep_sketch(win, qapp)
    win.action_sweep()
    before = win.doc.result.volume
    path = tmp_path / "sweep.tracer"
    fio.save_document(win.doc, path)
    doc2 = fio.load_document(path)
    sweeps = [f for f in doc2.features
              if isinstance(f, SweepFeature)]
    assert len(sweeps) == 1 and sweeps[0].radius == 3.0
    assert doc2.recompute().volume == pytest.approx(before, abs=1e-6)


def test_editing_the_sketch_moves_the_sweep(win, qapp):
    m = _sweep_sketch(win, qapp)
    win.action_sweep()
    f = [f for f in win.doc.features if isinstance(f, SweepFeature)][0]
    before = win.doc.result.volume
    m.sketch.lines[-1].b.y = 50.0                 # stretch the path
    win._editing_sid = m.sid
    win._on_profiles([], "Sketch1")               # the edit-commit flow
    qapp.processEvents()
    assert f in win.doc.features                  # sweep survived
    assert f.path[-1][1] == 50.0                  # path followed
    assert win.doc.result.volume > before         # and really longer now


def test_properties_panel_describes_the_sweep(qapp):
    p = PropertiesPanel()
    p.show_feature(SweepFeature(name="s", radius=2.0,
                                path=[[0.0, 0.0], [30.0, 0.0]],
                                closed=False))
    text = p._body.text()
    assert "Ø4 circle" in text and "30.0 mm open" in text


def test_screenshot_proof(win, qapp):
    import os
    _sweep_sketch(win, qapp, coords=((-25, 0), (0, 0), (25, 18)))
    win.action_sweep()
    win._show_page(win.viewport)                      # show the TUBE itself
    win.action_view("iso")
    win.viewport.refresh(fit=True)
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m35_sweep.png")
