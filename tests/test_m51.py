"""M51 — Split Body (plane trim): the maker's "cut away one half".

Core: split_solid trims flush with a plane and refuses to leave
nothing.  Feature: SplitFeature is a body op (like Shell) — it replaces
the accumulator — and survives the JSON round-trip.  Command: ribbon
Split asks plane + offset-from-centre + flip, validates BEFORE history,
and trims; a plane that misses the body warns instead of eating it.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox                # noqa: E402

from conftest import feature_rows, script_cmd                          # noqa: E402
from tracer.core.document import Document, PrimitiveFeature, SplitFeature  # noqa: E402
from tracer.core.geometry import Solid                                 # noqa: E402
from tracer.core.split import split_solid                              # noqa: E402


# ---- core ------------------------------------------------------------------------

def test_split_trims_flush_and_keeps_watertight():
    box = Solid.box(40, 40, 20)                 # volume 32000, z 0..20
    below = split_solid(box, (0, 0, 8), (0, 0, 1))
    assert below.volume == pytest.approx(12800, rel=1e-6)
    assert below.bounding_box[1][2] == pytest.approx(8.0, abs=1e-6)
    assert below.to_trimesh().is_watertight


def test_flip_keeps_the_other_side():
    box = Solid.box(40, 40, 20)
    above = split_solid(box, (0, 0, 8), (0, 0, 1), flip=True)
    assert above.volume == pytest.approx(19200, rel=1e-6)
    assert above.bounding_box[0][2] == pytest.approx(8.0, abs=1e-6)


def test_diagonal_split_is_valid_solid():
    box = Solid.box(40, 40, 20)
    n = (0.0, math.sin(math.pi / 4), math.cos(math.pi / 4))
    cut = split_solid(box, (0, 40, 10), n)
    assert cut.to_trimesh().is_watertight
    assert 0 < cut.volume < 32000


def test_split_that_keeps_nothing_is_refused():
    with pytest.raises(ValueError):
        split_solid(Solid.box(40, 40, 20), (0, 0, -5), (0, 0, 1))


# ---- document --------------------------------------------------------------------

def _box_doc():
    d = Document("trim")
    d.add(PrimitiveFeature(name="block", kind="box",
                           dims={"dx": 40, "dy": 40, "dz": 20}))
    d.recompute()
    return d


def test_split_feature_is_a_body_op():
    d = _box_doc()
    d.add(SplitFeature(name="Split XY", origin=(20, 20, 8.0),
                       normal=(0, 0, 1), flip=False))
    s = d.recompute()
    assert s.volume == pytest.approx(12800, rel=1e-3)
    assert s.to_trimesh().is_watertight


def test_split_feature_json_round_trip():
    d = _box_doc()
    d.add(SplitFeature(name="Split XY", origin=(20, 20, 12.0),
                       normal=(0, 0, 1), flip=True))
    vol = d.recompute().volume
    d2 = Document.from_dict(d.to_dict())
    sf = [f for f in d2.features if isinstance(f, SplitFeature)][0]
    assert sf.flip and np.allclose(sf.origin, (20, 20, 12))
    assert d2.recompute().volume == pytest.approx(vol, abs=1)


# ---- UI ----------------------------------------------------------------------------

from tracer.ui.mainwindow import MainWindow                              # noqa: E402
from tracer.ui.renderer import SceneRenderer                             # noqa: E402


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


def _block(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="block", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 20}))
    win.recompute()
    qapp.processEvents()


def test_action_split_trims_below_centre_minus_2(win, qapp, monkeypatch):
    _block(win, qapp)
    script_cmd(monkeypatch, {"plane": "XY", "dist": -2.0, "flip": False})
    win.action_split_body()
    qapp.processEvents()
    sf = [f for f in win.doc.features if isinstance(f, SplitFeature)]
    assert len(sf) == 1 and sf[0].name == "Split XY"
    assert sf[0].origin[2] == pytest.approx(8.0)      # centre(10) + (-2)
    assert win.doc.result.volume == pytest.approx(12800, rel=1e-3)
    assert win.doc.result.to_trimesh().is_watertight
    assert "Split" in win.status.currentMessage()
    rows = [r.text(0) for r in feature_rows(win)]
    assert any(r.endswith("Split XY") and "\u2702" in r for r in rows)


def test_action_split_flip_keeps_the_upper_half(win, qapp, monkeypatch):
    _block(win, qapp)
    script_cmd(monkeypatch, {"plane": "XY", "dist": 0.0, "flip": True})
    win.action_split_body()
    assert win.doc.result.volume == pytest.approx(16000, rel=1e-3)


def test_action_split_validates_before_touching_history(win, qapp,
                                                        monkeypatch):
    _block(win, qapp)
    # plane 20 mm BELOW the block, removing upward: nothing would survive
    script_cmd(monkeypatch, {"plane": "XY", "dist": -20.0, "flip": False})
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(a[2])))
    win.action_split_body()
    qapp.processEvents()
    assert seen                                          # warned...
    assert not [f for f in win.doc.features
                if isinstance(f, SplitFeature)]          # ...no feature
    assert win.doc.result.volume == pytest.approx(32000, rel=1e-3)
