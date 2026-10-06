"""M66 — Cone: the fifth primitive voice (Create dialog + Combine tool).

A cone is a two-radius cylinder, and the kernel knew it — the UI now
does too.  Truncated-cone volume πh/3(r1²+r1r2+r2²) exactly, a sharp
cone (top radius 0) still watertight, cones as Combine tools cut honest
chamfer-like corners, and Change Parameters edits all three radii and
the height.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from conftest import script_cmd                                        # noqa: E402
from tracer.core.document import (CombineFeature, Document,            # noqa: E402
                                  PrimitiveFeature)
from tracer.core.geometry import Solid


def _vol(r1, r2, h):
    return math.pi * h / 3.0 * (r1 * r1 + r1 * r2 + r2 * r2)


def test_cone_kernel_volume_exact():
    s = Solid.cone(10.0, 4.0, 15.0)
    assert s.volume == pytest.approx(_vol(10, 4, 15), rel=1e-3)
    assert s.to_trimesh().is_watertight


def test_sharp_cone_is_watertight():
    s = Solid.cone(8.0, 0.0, 20.0)
    assert s.volume == pytest.approx(math.pi * 64 * 20 / 3.0, rel=1e-3)
    assert s.to_trimesh().is_watertight


def test_cone_feature_json_round_trip():
    d = Document("c")
    d.add(PrimitiveFeature(name="Cone 1", kind="cone",
                           dims={"radius_bottom": 10.0,
                                 "radius_top": 4.0, "height": 15.0}))
    vol = d.recompute().volume
    d2 = Document.from_dict(d.to_dict())
    pf = [f for f in d2.features if isinstance(f, PrimitiveFeature)][0]
    assert pf.kind == "cone" and pf.dims["radius_top"] == 4.0
    assert d2.recompute().volume == pytest.approx(vol, abs=1)


# ---- UI ---------------------------------------------------------------------------

from tracer.ui.mainwindow import MainWindow                            # noqa: E402
from tracer.ui.renderer import SceneRenderer                           # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:                     # CI windows runners: no GL
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


def test_primitive_dialog_cone(win, qapp, monkeypatch):
    win.new_document()
    script_cmd(monkeypatch, {"kind": "Cone", "dx": 40.0, "dy": 30.0,
                             "dz": 15.0, "radius": 10.0, "r1": 10.0,
                             "r2": 4.0, "height": 15.0, "op": "Join",
                             "x": 0.0, "y": 0.0, "z": 0.0})
    win.action_primitive()
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(_vol(10, 4, 15),
                                                  rel=1e-3)
    pf = [f for f in win.doc.features if isinstance(f, PrimitiveFeature)]
    assert pf[0].kind == "cone" and pf[0].name == "Cone 1"


def test_cone_combine_tool_cuts_a_countdown_corner(win, qapp,
                                                   monkeypatch):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 30, "dy": 30, "dz": 10}))
    win.recompute()
    qapp.processEvents()
    script_cmd(monkeypatch, {"tool": "Cone", "dx": 20.0, "dy": 20.0,
                             "dz": 20.0, "radius": 8.0, "r1": 12.0,
                             "r2": 4.0, "height": 8.0, "op": "Cut",
                             "cx": 15.0, "cy": 15.0, "cz": 5.0})
    win.action_combine()
    qapp.processEvents()
    cf = [f for f in win.doc.features if isinstance(f, CombineFeature)][0]
    assert cf.tool == "cone"
    want = 9000 - _vol(12, 4, 8)           # cone fully inside the slab
    assert win.doc.result.volume == pytest.approx(want, rel=1e-3)
    assert win.doc.result.to_trimesh().is_watertight


def test_cone_params_editable(win, qapp, monkeypatch):
    win.new_document()
    d = win.doc
    d.add(PrimitiveFeature(name="Cone 1", kind="cone",
                           dims={"radius_bottom": 10.0, "radius_top": 4.0,
                                 "height": 15.0}))
    win.recompute()
    qapp.processEvents()
    feat = [f for f in d.features if isinstance(f, PrimitiveFeature)][0]
    script_cmd(monkeypatch, {"r1": 10.0, "r2": 0.0, "height": 15.0})
    win.action_change_params(feat)
    qapp.processEvents()
    assert d.result.volume == pytest.approx(_vol(10, 0, 15), rel=1e-3)
