"""M65 — Primitive: Create ▸ Box / Cylinder / Sphere from the ribbon.

The kernel always spoke primitives; now the UI does too.  A dialog of
shape, size (in document measures), boolean operation and placement
drops a parametric PrimitiveFeature — first one IS the body, later ones
Join/Cut/Intersect into it with exact volumes.  Placement semantics:
box corner, cylinder base centre, sphere centre; names count per kind.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from conftest import script_cmd, script_cmd_cancel                     # noqa: E402
from tracer.core.document import PrimitiveFeature                      # noqa: E402


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


BOX = {"kind": "Box", "dx": 40.0, "dy": 30.0, "dz": 15.0, "radius": 10.0,
       "height": 30.0, "op": "Join", "x": 0.0, "y": 0.0, "z": 0.0}


def test_primitive_box_starts_the_body(win, qapp, monkeypatch):
    win.new_document()
    script_cmd(monkeypatch, dict(BOX))
    win.action_primitive()
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(18000, rel=1e-3)
    pf = [f for f in win.doc.features if isinstance(f, PrimitiveFeature)]
    assert len(pf) == 1 and pf[0].kind == "box" and pf[0].name == "Box 1"


def test_primitive_cylinder_joins_far_away_exactly(win, qapp, monkeypatch):
    win.new_document()
    script_cmd(monkeypatch, dict(BOX))
    win.action_primitive()
    script_cmd(monkeypatch, {**BOX, "kind": "Cylinder", "x": 100.0})
    win.action_primitive()
    qapp.processEvents()
    want = 18000 + math.pi * 100 * 30
    assert win.doc.result.volume == pytest.approx(want, rel=1e-3)


def test_primitive_cut_and_names_count_per_kind(win, qapp, monkeypatch):
    win.new_document()
    script_cmd(monkeypatch, dict(BOX))
    win.action_primitive()
    script_cmd(monkeypatch, {**BOX, "dx": 10.0, "dy": 10.0, "dz": 10.0,
                             "op": "Cut"})
    win.action_primitive()
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(18000 - 1000, rel=1e-3)
    names = [f.name for f in win.doc.features
             if isinstance(f, PrimitiveFeature)]
    assert names == ["Box 1", "Box 2"]


def test_sphere_centres_at_placement(win, qapp, monkeypatch):
    win.new_document()
    script_cmd(monkeypatch, {**BOX, "kind": "Sphere", "radius": 10.0,
                             "z": 10.0})
    win.action_primitive()
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(
        4.0 / 3.0 * math.pi * 1000, rel=1e-3)
    lo, hi = win.doc.result.bounding_box
    assert float(lo[2]) == pytest.approx(0.0, abs=0.05)   # rests on 0


def test_cancel_changes_nothing(win, qapp, monkeypatch):
    win.new_document()
    script_cmd_cancel(monkeypatch)
    win.action_primitive()
    qapp.processEvents()
    assert win.doc.result is None or win.doc.result.volume == 0 \
        or not [f for f in win.doc.features
                if isinstance(f, PrimitiveFeature)]
