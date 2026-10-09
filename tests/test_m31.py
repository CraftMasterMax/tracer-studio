"""M31 — Hole command: drill every sketch circle into the solid.

Fusion's Hole is a composed feature: the drilled Ø is the circle you drew,
and the dialog adds depth/through plus the two maker classics — counterbore
(second cylinder) and countersink (a triangular wedge revolved 360°).  All
three tools are unioned and subtracted once, so the kernel needs nothing
new; the direction is probed at creation (the plane can sit on either side
of the material), and the feature keeps sid+cidx so re-editing the sketch
relocates the holes.
"""
import json
import math
import os

import numpy as np
import pytest

from tracer.core.document import (Document, HoleFeature, PrimitiveFeature)


def _plate():
    d = Document("t")
    d.add(PrimitiveFeature(name="base", kind="box",
                           dims={"dx": 40, "dy": 40, "dz": 10}))
    return d


# ---- kernel -----------------------------------------------------------------

def test_blind_hole_exact_volume_and_watertight():
    d = _plate()
    d.add(HoleFeature(name="h", op="subtract", center=(20, 20, 10),
                      normal=(0, 0, -1), radius=3.0, depth=6.0,
                      cut_length=6.0))
    v = d.recompute().volume
    assert v == pytest.approx(16000 - math.pi * 9 * 6, abs=0.6)
    assert d.result.to_trimesh().is_watertight


def test_through_hole_runs_the_full_span():
    d = _plate()
    d.add(HoleFeature(name="h", op="subtract", center=(20, 20, 10),
                      normal=(0, 0, -1), radius=3.0, depth=2.0,
                      through=True, cut_length=50.0))
    assert d.recompute().volume == pytest.approx(
        16000 - math.pi * 9 * 10, abs=0.8)


def test_counterbore_ring_analytic():
    d = _plate()
    d.add(HoleFeature(name="h", op="subtract", center=(20, 20, 10),
                      normal=(0, 0, -1), radius=3.0, depth=10.0,
                      through=True, cut_length=50.0,
                      cb_radius=5.0, cb_depth=4.0))
    want = 16000 - math.pi * 9 * 10 - math.pi * (25 - 9) * 4
    assert d.recompute().volume == pytest.approx(want, abs=1.0)


def test_countersink_wedge_analytic():
    d = _plate()
    r, R, ang = 3.0, 5.5, 90.0
    k = (R - r) / math.tan(math.radians(ang) / 2)
    d.add(HoleFeature(name="h", op="subtract", center=(20, 20, 10),
                      normal=(0, 0, -1), radius=r, depth=10.0,
                      through=True, cut_length=50.0,
                      cs_radius=R, cs_angle=ang))
    ring = math.pi * k / 3 * (r * r + r * R + R * R) - math.pi * r * r * k
    assert d.recompute().volume == pytest.approx(
        16000 - math.pi * r * r * 10 - ring, abs=1.2)


def test_counterbore_smaller_than_hole_is_ignored():
    d = _plate()
    d.add(HoleFeature(name="h", op="subtract", center=(20, 20, 10),
                      normal=(0, 0, -1), radius=3.0, depth=6.0,
                      cut_length=6.0, cb_radius=2.0, cb_depth=4.0))
    assert d.recompute().volume == pytest.approx(16000 - math.pi * 9 * 6,
                                                 abs=0.6)


def test_arbitrary_normal_and_suppression():
    d = _plate()
    n = (0, -1, 0)                       # into the y=40 side face
    f = HoleFeature(name="h", op="subtract", center=(10, 40, 5),
                    normal=n, radius=2.5, depth=8.0, cut_length=8.0)
    d.add(f)
    full = d.recompute().volume
    assert full == pytest.approx(16000 - math.pi * 6.25 * 8, abs=0.6)
    f.suppressed = True
    assert d.recompute().volume == pytest.approx(16000, abs=1e-6)


def test_serialize_roundtrip_preserves_everything():
    d = _plate()
    d.add(HoleFeature(name="h", op="subtract", center=(1.5, 2.5, 3.5),
                      normal=(0.0, 0.0, -1.0), radius=2.0, depth=7.0,
                      through=True, cut_length=99.0, cb_radius=4.0,
                      cb_depth=3.0, cs_radius=0.0, cs_angle=82.0,
                      sketch={"name": "Sketch9"}, sid=111, cidx=2))
    v = d.recompute().volume
    d2 = Document.from_dict(json.loads(json.dumps(d.to_dict())))
    f = d2.features[1]
    assert isinstance(f, HoleFeature) and abs(d2.recompute().volume - v) < 1e-6
    assert (f.name, f.through, f.cut_length, f.cb_radius, f.cb_depth,
            f.cs_angle, f.cidx, f.sketch["name"]) == \
           ("h", True, 99.0, 4.0, 3.0, 82.0, 2, "Sketch9")


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                      # noqa: E402
from PySide6.QtTest import QTest                                # noqa: E402
from PySide6.QtCore import Qt                                   # noqa: E402

from tracer.core.sketch.model import model_to_dict              # noqa: E402
from tracer.ui.hole import HoleDialog                           # noqa: E402
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


def _opts(**kw):
    o = {"type": "simple", "depth": 6.0, "through": False,
         "cb_dia": 10.0, "cb_depth": 4.0, "cs_dia": 12.0, "cs_angle": 90.0}
    o.update(kw)
    return o


@pytest.fixture
def no_msgbox(monkeypatch):
    """Guard paths pop QMessageBox — modal boxes block headless runs."""
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.Ok))


def _base_and_circles(win, qapp, circles=((12, 15, 3.0), (28, 15, 2.0))):
    """A 40x40x10 box and a fresh XY sketch holding the given circles."""
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 10}))
    win.recompute()
    win.action_new_sketch()
    qapp.processEvents()
    m = win.sketch.model
    for x, y, r in circles:
        m.add_circle(m.point(x, y), r)
    return m


def test_action_hole_needs_circles_and_a_solid(win, qapp, no_msgbox,
                                               monkeypatch):
    calls = []
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: calls.append(1) or _opts()))
    win.new_document()
    win.action_new_sketch()                       # empty sketch: no dialog
    win.action_hole()
    assert not calls and not any(isinstance(f, HoleFeature)
                                 for f in win.doc.features)
    # circles but no solid:
    m = win.sketch.model
    m.add_circle(m.point(2, 2), 1.0)
    win.doc.features.clear()
    win.action_hole()
    assert not calls and not win.doc.features


def test_drill_two_through_holes_flips_direction_up(win, qapp, monkeypatch):
    m = _base_and_circles(win, qapp)
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(through=True)))
    win.action_hole()
    qapp.processEvents()
    holes = [f for f in win.doc.features if isinstance(f, HoleFeature)]
    assert len(holes) == 2
    # sketch sits at z=0 BELOW the plate — the probe must drill upward
    for f in holes:
        assert np.allclose(f.normal, (0, 0, 1), atol=1e-9)
        assert f.sketch is not None and f.sid == m.sid
    want = 16000 - (math.pi * 9 * 10 + math.pi * 4 * 10)
    assert win.doc.result.volume == pytest.approx(want, abs=1.5)
    assert win.doc.result.to_trimesh().is_watertight
    assert "through all" in win.status.currentMessage()


def test_counterbore_and_countersink_params(win, qapp, monkeypatch):
    _base_and_circles(win, qapp, circles=((20, 20, 3.0),))
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(
                            type="counterbore", cb_dia=10.0, cb_depth=4.0)))
    win.action_hole()
    f = win.doc.features[-1]
    assert f.cb_radius == pytest.approx(5.0) and f.cb_depth == 4.0
    assert "counterbore" in f.name
    # re-drill as countersink through the same feature (in place)
    win.edit_sketch(f)                            # reopen its circle sketch
    qapp.processEvents()
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(
                            type="countersink", cs_dia=12.0, through=True)))
    win.action_hole()
    holes = [x for x in win.doc.features if isinstance(x, HoleFeature)]
    assert len(holes) == 1                        # updated, not duplicated
    f = holes[0]
    assert f.cs_radius == pytest.approx(6.0) and f.through
    assert f.cb_radius == 0.0                     # params replaced, not merged


def test_redrill_after_reopen_does_not_duplicate(win, qapp, monkeypatch):
    _base_and_circles(win, qapp)
    monkeypatch.setattr(HoleDialog, "ask", staticmethod(lambda p, d: _opts()))
    win.action_hole()
    first = [f for f in win.doc.features if isinstance(f, HoleFeature)][0]
    win.edit_sketch(first)                        # browser double-click path
    qapp.processEvents()
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(depth=2.0)))
    win.action_hole()
    holes = [f for f in win.doc.features if isinstance(f, HoleFeature)]
    assert len(holes) == 2                        # one per sketch circle
    assert all(f.depth == 2.0 for f in holes)     # both re-drilled, none added


def _hole_for(m, cidx):
    from tracer.core.document import HoleFeature as HF
    c = [c for c in m.sketch.circles if not c.construction][cidx]
    f = HF(name="h", op="subtract", center=(float(c.c.x), float(c.c.y), 0.0),
           normal=(0, 0, -1), radius=float(c.r), depth=4.0, cut_length=4.0,
           sketch=model_to_dict(m), sid=m.sid, cidx=cidx)
    return f


def test_sync_holes_follows_and_prunes(win, qapp):
    m = _base_and_circles(win, qapp)
    m.add_circle(m.point(20, 30), 1.5)
    m.add_circle(m.point(30, 30), 1.5)
    m.add_circle(m.point(10, 10), 1.5)
    f = _hole_for(m, 2)                       # drilled at circle (20, 30)
    win.doc.add(f)
    win.recompute()
    # move circle 2, nothing else changes: hole follows
    m.sketch.circles[2].c.x, m.sketch.circles[2].c.y = 35.0, 5.0
    win._sync_holes(m.sid, model_to_dict(m))
    assert np.allclose(f.center, (35.0, 5.0, 0.0), atol=1e-9)
    # delete the circle: hole is pruned
    m.sketch.circles.pop(2)
    win._sync_holes(m.sid, model_to_dict(m))
    assert f not in win.doc.features


def test_sync_holes_survives_index_shift(win, qapp):
    m = _base_and_circles(win, qapp)          # circles at (12,15) (28,15)
    m.add_circle(m.point(20, 35), 1.5)
    f = _hole_for(m, 1)                       # drilled at (28, 15)
    win.doc.add(f)
    win.recompute()
    m.sketch.circles.pop(0)                   # deletes an EARLIER circle
    win._sync_holes(m.sid, model_to_dict(m))  # everything shifts left
    assert f in win.doc.features
    assert f.cidx == 0                        # re-identified by position
    assert np.allclose(f.center, (28.0, 15.0, 0.0), atol=1e-9)


def test_properties_panel_describes_hole(qapp):
    p = PropertiesPanel()
    f = HoleFeature(name="h", op="subtract", center=(0, 0, 0),
                    normal=(0, 0, -1), radius=3.0, depth=6.0,
                    cut_length=6.0, cb_radius=5.0, cb_depth=4.0)
    p.show_feature(f)
    text = p._body.text()
    assert "Ø6" in text and "through" not in text and "counterbore" in text
    assert "Ø10 × 4" in text


def test_screenshot_proof(win, qapp, monkeypatch, tmp_path):
    m = _base_and_circles(win, qapp, circles=((12, 20, 3.0), (20, 20, 2.5),
                                              (28, 20, 3.0)))
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(
                            type="countersink", cs_dia=8.0, through=True)))
    win.action_hole()
    qapp.processEvents()
    win.action_view("iso")
    win.viewport.refresh(fit=True)
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m31_hole.png")


def test_extrude_edit_path_keeps_holes_glued(win, qapp, monkeypatch):
    # one sketch: a boss rect + a hole circle that the user extrudes AND
    # drills; editing the sketch then pressing X must keep the hole glued
    _base_and_circles(win, qapp, circles=((10, 10, 2.0),))
    monkeypatch.setattr(HoleDialog, "ask", staticmethod(lambda p, d: _opts()))
    win.action_hole()
    hole = [f for f in win.doc.features if isinstance(f, HoleFeature)][0]
    win.edit_sketch(hole)
    from tracer.core.sketch.entities import Point
    win.sketch.model.add_rect(Point(30, 30), Point(38, 38))
    monkeypatch.setattr("tracer.ui.cmddialog.Shell.getDouble",
                        staticmethod(lambda *a, **k: (3.0, True)))
    win.sketch.finish()
    qapp.processEvents()
    holes = [f for f in win.doc.features if isinstance(f, HoleFeature)]
    assert len(holes) == 1 and holes[0] is hole
    assert np.allclose(hole.center, (10, 10, 0), atol=1e-9)
