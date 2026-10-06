"""M68 — Torus: the fifth primitive, a circle revolved on a parallel axis.

2·pi²·R·r² to faceting tolerance at 64 segments, watertight, and every
speaker of the primitive vocabulary now knows the ring: Create dialog,
Combine tool, Change Parameters, JSON.  A torus cutter buried wholly in
a slab leaves slab minus the exact ring volume.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from conftest import script_cmd                                        # noqa: E402
from tracer.core.document import (CombineFeature, Document,            # noqa: E402
                                  PrimitiveFeature)
from tracer.core.geometry import Solid


def _vol(R, r):
    return 2.0 * math.pi ** 2 * R * r * r          # Pappus, ideal


def test_torus_kernel_volume_and_genus():
    s = Solid.torus(20.0, 4.0)
    assert s.volume == pytest.approx(_vol(20, 4), rel=2e-3)
    tm = s.to_trimesh()
    assert tm.is_watertight
    assert tm.euler_number == 0                      # genus 1, a ring


def test_torus_feature_json_round_trip():
    d = Document("t")
    d.add(PrimitiveFeature(name="Torus 1", kind="torus",
                           dims={"major": 18.0, "minor": 3.0},
                           placement=(10.0, 10.0, 6.0)))
    vol = d.recompute().volume
    d2 = Document.from_dict(d.to_dict())
    pf = [f for f in d2.features if isinstance(f, PrimitiveFeature)][0]
    assert pf.kind == "torus" and pf.dims["minor"] == 3.0
    assert d2.recompute().volume == pytest.approx(vol, abs=2)


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


RING = {"kind": "Torus", "dx": 20.0, "dy": 20.0, "dz": 20.0,
        "radius": 8.0, "r1": 12.0, "r2": 4.0, "major": 20.0,
        "minor": 5.0, "op": "Join", "x": 0.0, "y": 0.0, "z": 8.0}


def test_primitive_dialog_torus_rests_on_the_ground(win, qapp,
                                                    monkeypatch):
    win.new_document()
    script_cmd(monkeypatch, dict(RING))
    win.action_primitive()
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(_vol(20, 5), rel=2e-3)
    lo, _hi = win.doc.result.bounding_box
    assert float(lo[2]) == pytest.approx(3.0, abs=0.05)   # z 3..13
    pf = [f for f in win.doc.features if isinstance(f, PrimitiveFeature)]
    assert pf[0].kind == "torus" and pf[0].name == "Torus 1"


def test_torus_combine_tool_guts_a_slab(win, qapp, monkeypatch):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="slab", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 30}))
    win.recompute()
    qapp.processEvents()
    script_cmd(monkeypatch, {"tool": "Torus", "dx": 20.0, "dy": 20.0,
                             "dz": 20.0, "radius": 8.0, "r1": 12.0,
                             "r2": 4.0, "major": 12.0, "minor": 5.0,
                             "op": "Cut", "cx": 20.0, "cy": 20.0,
                             "cz": 15.0})
    win.action_combine()
    qapp.processEvents()
    cf = [f for f in win.doc.features if isinstance(f, CombineFeature)][0]
    assert cf.tool == "torus"
    want = 40 * 40 * 30 - _vol(12, 5)          # torus fully inside
    assert win.doc.result.volume == pytest.approx(want, rel=2e-3)
    assert win.doc.result.to_trimesh().is_watertight


def test_torus_params_editable(win, qapp, monkeypatch):
    win.new_document()
    d = win.doc
    d.add(PrimitiveFeature(name="Torus 1", kind="torus",
                           dims={"major": 15.0, "minor": 4.0}))
    win.recompute()
    qapp.processEvents()
    feat = [f for f in d.features if isinstance(f, PrimitiveFeature)][0]
    script_cmd(monkeypatch, {"major": 15.0, "minor": 2.0})
    win.action_change_params(feat)
    qapp.processEvents()
    assert d.result.volume == pytest.approx(_vol(15, 2), rel=2e-3)
