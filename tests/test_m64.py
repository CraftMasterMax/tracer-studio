"""M64 — Combine: Join / Cut / Intersect a placed solid into the body.

Kernel truth first: a Ø10×30 cylinder joined through a 40×20×10 plate
weighs 8000 + πr²h − overlap, a corner-cut box leaves exactly 7750 mm³,
an intersect keeps the 4000 mm³ overlap — each watertight.  Then the
command end to end: dialog → parametric CombineFeature (JSON round
trip), undo, and Change Parameters speaking for it too.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from conftest import feature_rows, script_cmd, script_cmd_cancel       # noqa: E402
from tracer.core.document import CombineFeature, Document, PrimitiveFeature  # noqa: E402


# ---- core -------------------------------------------------------------------------

def _plate():
    d = Document("cmb")
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 20, "dz": 10}))
    return d


def test_combine_join_cylinder_is_boolean_truth():
    d = _plate()
    d.add(CombineFeature(name="boss", tool="cylinder", op="union",
                         dims={"radius": 5.0, "height": 30.0},
                         center=(20, 10, -5)))
    s = d.recompute()
    want = 8000 + math.pi * 25 * 30 - math.pi * 25 * 10
    assert s.volume == pytest.approx(want, rel=1e-3)
    assert s.to_trimesh().is_watertight


def test_combine_cut_and_intersect():
    d = _plate()
    d.add(CombineFeature(name="nick", tool="box", op="subtract",
                         dims={"dx": 10, "dy": 10, "dz": 20},
                         center=(0, 0, 5)))
    s = d.recompute()
    assert s.volume == pytest.approx(8000 - 5 * 5 * 10, rel=1e-3)

    d2 = _plate()
    d2.add(CombineFeature(name="trim", tool="box", op="intersect",
                          dims={"dx": 20, "dy": 20, "dz": 20},
                          center=(10, 10, 5)))
    s2 = d2.recompute()
    assert s2.volume == pytest.approx(20 * 20 * 10, rel=1e-3)
    assert s2.to_trimesh().is_watertight


def test_combine_json_round_trip():
    d = _plate()
    d.add(CombineFeature(name="boss", tool="cylinder", op="union",
                         dims={"radius": 4.0, "height": 12.0},
                         center=(20, 10, 6)))
    vol = d.recompute().volume
    d2 = Document.from_dict(d.to_dict())
    cf = [f for f in d2.features if isinstance(f, CombineFeature)][0]
    assert cf.tool == "cylinder" and cf.op == "union"
    assert cf.dims["radius"] == pytest.approx(4.0)
    assert np.allclose(cf.center, (20, 10, 6))
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
    r.close()


def _block(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 20, "dz": 10}))
    win.recompute()
    qapp.processEvents()


def test_combine_dialog_joins_a_boss(win, qapp, monkeypatch):
    _block(win, qapp)
    script_cmd(monkeypatch, {"tool": "Cylinder", "radius": 5.0,
                             "height": 30.0, "dx": 20.0, "dy": 20.0,
                             "dz": 20.0, "op": "Join",
                             "cx": 20.0, "cy": 10.0, "cz": -5.0})
    win.action_combine()
    qapp.processEvents()
    want = 8000 + math.pi * 25 * 20
    assert win.doc.result.volume == pytest.approx(want, rel=1e-3)
    assert any(isinstance(f, CombineFeature) for f in win.doc.features)
    assert "combined" in win.status.currentMessage().lower()
    rows = [r.text(0) for r in feature_rows(win)]
    assert any("\u2295" in r for r in rows)


def test_combine_cancel_changes_nothing(win, qapp, monkeypatch):
    _block(win, qapp)
    script_cmd_cancel(monkeypatch)
    win.action_combine()
    qapp.processEvents()
    assert not [f for f in win.doc.features
                if isinstance(f, CombineFeature)]
    assert win.doc.result.volume == pytest.approx(8000, rel=1e-6)


def test_combine_params_editable_and_undoable(win, qapp, monkeypatch):
    _block(win, qapp)
    script_cmd(monkeypatch, {"tool": "Box", "dx": 10.0, "dy": 10.0,
                             "dz": 30.0, "radius": 5.0, "height": 30.0,
                             "op": "Cut", "cx": 20.0, "cy": 10.0,
                             "cz": 5.0})
    win.action_combine()
    qapp.processEvents()
    cf = [f for f in win.doc.features if isinstance(f, CombineFeature)][0]
    assert win.doc.result.volume == pytest.approx(8000 - 100 * 10,
                                                  rel=1e-3)
    # Change Parameters widens the cutter: 20 wide now
    script_cmd(monkeypatch, {"tool": "Box", "op": "Cut",
                             "dx": 20.0, "dy": 10.0, "dz": 30.0,
                             "radius": 5.0, "height": 30.0,
                             "c0": 20.0, "c1": 10.0, "c2": 5.0})
    win.action_change_params(cf)
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(8000 - 200 * 10,
                                                  rel=1e-3)
    win.undo()
    qapp.processEvents()
    assert win.doc.result.volume == pytest.approx(8000 - 100 * 10,
                                                  rel=1e-3)
