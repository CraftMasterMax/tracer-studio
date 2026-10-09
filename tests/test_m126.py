"""M126 — the transform lattice: geometric pattern + scale.

Both new features are pure matrix algebra over solids — (T·R·S)^i
composed across two directions, and a base-anchored affine scale — so
they need no B-rep face identity, and their directions/pivot resolve
through the M125 named-datum store. These tests pin the lattice maths
against closed-form expectations (geometric-series volumes, corner
symmetry), the honest refusals (zero factors, huge lattices, missing
pivots), persistence, the datum-reference ledger, and the UI paths.
"""
import numpy as np
import pytest

from tracer.core import params
from tracer.core.document import (Document, GeometricPatternFeature,
                                  PrimitiveFeature, ScaleFeature)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    w.new_document()
    qapp.processEvents()
    w._discard_guard = lambda: True
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _box(d, at=(0.0, 0.0, 0.0), s=2.0, name="src"):
    f = PrimitiveFeature(name=name, kind="box",
                         dims={"dx": s, "dy": s, "dz": s}, placement=at)
    d.add(f)
    d.recompute()
    return f


# ---- core: lattice maths -------------------------------------------------

def test_oblique_grid_is_closed_form():
    d = Document()
    src = _box(d)
    d.add_geometric_pattern("row", src, d1=(1, 0, 0), n1=3, t1=10.0)
    d.recompute()
    assert d.result.volume == pytest.approx(24.0, abs=1e-6)
    assert np.allclose(d.result.bounding_box, [[0, 0, 0], [22, 2, 2]],
                       atol=1e-6)


def test_spiral_of_shrinking_copies_matches_geometric_series():
    d = Document()
    src = _box(d, at=(10.0, 0.0, 0.0))
    d.add_axis_2pt((0, 0, 0), (10, 0, 0))          # named rail
    d.add_geometric_pattern("spiral", src, axis="Z", d1="Axis 1", n1=5,
                            t1=0.0, r1=30.0, k1=0.8)
    d.recompute()
    exp = 8.0 * sum(0.8 ** (3 * i) for i in range(5))   # volumes k^3i
    assert d.result.volume == pytest.approx(exp, rel=1e-6)


def test_two_direction_lattice_composes_both_steps():
    d = Document()
    src = _box(d)
    d.add_geometric_pattern("grid", src, d1=(1, 0, 0), n1=2, t1=10.0,
                            d2=(0, 1, 0), n2=2, t2=6.0)
    d.recompute()
    assert d.result.volume == pytest.approx(32.0, abs=1e-6)
    assert np.allclose(d.result.bounding_box, [[0, 0, 0], [12, 8, 2]],
                       atol=1e-6)


def test_solo_copy_rides_in_place():
    d = Document()
    src = _box(d, at=(5.0, 5.0, 5.0))
    d.add_geometric_pattern("solo", src, n1=1, n2=1)
    d.recompute()
    assert np.allclose(d.result.bounding_box, [[5, 5, 5], [7, 7, 7]],
                       atol=1e-9)


# ---- core: scale ----------------------------------------------------------

def test_uniform_scale_volume_is_k_cubed():
    d = Document()
    src = _box(d)
    d.add_scale("big", src, factors=2.0)
    d.recompute()
    assert d.result.volume == pytest.approx(64.0, abs=1e-6)


def test_per_axis_scale_anchors_at_base_point():
    d = Document()
    src = _box(d)
    d.add_scale("flat", src, base=(0.0, 0.0, 2.0), factors=(1.0, 3.0, 1.0))
    d.recompute()
    # z anchored at 2: the box top (z=2) stays put, nothing moves in z
    assert np.allclose(d.result.bounding_box, [[0, 0, 0], [2, 6, 2]],
                       atol=1e-6)


def test_negative_factor_mirrors_and_winding_holds():
    d = Document()
    src = _box(d)
    d.add_scale("flip", src, factors=(1.0, 1.0, -1.0))
    d.recompute()
    assert np.allclose(d.result.bounding_box, [[0, 0, -2], [2, 2, 2]],
                       atol=1e-6)
    assert d.result.volume == pytest.approx(16.0, abs=1e-6)


def test_lattice_and_scale_refusals():
    for kw in (dict(n1=0), dict(k1=0.0), dict(d1=(0, 0, 0)),
               dict(axis="Axis 42")):
        d = Document()
        src = _box(d)
        d.add_geometric_pattern("bad", src, **kw)
        with pytest.raises(params.ParamError):
            d.recompute()
    d = Document()
    src = _box(d)
    d.add_geometric_pattern("huge", src, n1=65, n2=65)
    with pytest.raises(params.ParamError):
        d.recompute()
    d = Document()
    src = _box(d)
    d.add_scale("nil", src, factors=0.0)
    with pytest.raises(params.ParamError):
        d.recompute()


# ---- core: references & persistence ---------------------------------------

def test_lattice_registers_every_named_binding():
    d = Document()
    src = _box(d)
    d.add_axis_2pt((0, 0, 0), (0, 0, 10))           # Axis 1 (pivot)
    d.add_axis_2pt((0, 0, 0), (1, 1, 0))            # Axis 2 (rail)
    d.add_geometric_pattern("lat", src, axis="Axis 1", d1="Axis 2",
                            n1=2, t1=5.0, d2=(1, 0, 0))
    assert d.datum_references("Axis 1") == ["lat"]
    assert d.datum_references("Axis 2") == ["lat"]


def test_io_roundtrip_keeps_named_rails_and_str_types():
    import tempfile
    from pathlib import Path
    from tracer.core.io import save_document, load_document
    d = Document()
    src = _box(d, at=(10.0, 0.0, 0.0))
    d.add_axis_2pt((0, 0, 0), (0, 0, 10))
    d.add_geometric_pattern("lat", src, axis="Axis 1", d1="Axis 1",
                            d2=(1, 0, 0), n1=2, t1=5.0, k1=0.9,
                            n2=3, t2=4.0)
    d.add_scale("grown", d.features[0], factors=(2.0, 1.0, 0.5))
    with tempfile.TemporaryDirectory() as t:
        pth = Path(t) / "g.tracer"
        save_document(d, pth)
        r = load_document(pth)
    gp = next(f for f in r.features
              if isinstance(f, GeometricPatternFeature))
    sc = next(f for f in r.features if isinstance(f, ScaleFeature))
    assert gp.axis == "Axis 1" and gp.d1 == "Axis 1"
    assert tuple(gp.d2) == (1.0, 0.0, 0.0)
    assert (gp.n1, gp.n2, gp.t1, gp.t2, gp.k1) == (2, 3, 5.0, 4.0, 0.9)
    assert sc.factors == (2.0, 1.0, 0.5)
    r.recompute()
    assert r.result.volume == pytest.approx(d.result.volume, abs=1e-6)


# ---- UI: dialogs -----------------------------------------------------------

def _dialog_answers(monkeypatch, values):
    from tracer.ui import cmddialog
    monkeypatch.setattr(cmddialog, "ask",
                        lambda parent, title, fields, remember_key=None:
                        dict(values))


def test_geometric_dialog_creates_named_lattice(win, monkeypatch):
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2, "dy": 2, "dz": 2},
                                 placement=(10, 0, 0)))
    win.recompute()
    win.doc.add_axis_2pt((0, 0, 0), (0, 1, 2))
    _dialog_answers(monkeypatch, {
        "src": "lug", "axis": "Axis 1", "base": "0,0,0",
        "d1": "Z", "n1": 3, "t1": 8.0, "r1": 45.0, "k1": 0.9,
        "d2": "X", "n2": 1, "t2": 0.0, "r2": 0.0, "k2": 1.0})
    win.action_geometric_pattern()
    gp = [f for f in win.doc.features
          if isinstance(f, GeometricPatternFeature)][0]
    assert gp.axis == "Axis 1" and gp.d1 == "Z" and gp.k1 == 0.9
    assert "spiral" in win.status.currentMessage()   # twist is announced


def test_geometric_dialog_refuses_garbage_base_loudly(win, monkeypatch):
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2, "dy": 2, "dz": 2}))
    win.recompute()
    _dialog_answers(monkeypatch, {
        "src": "lug", "axis": "Z", "base": "here,0,0",
        "d1": "X", "n1": 2, "t1": 5.0, "r1": 0.0, "k1": 1.0,
        "d2": "Y", "n2": 1, "t2": 0.0, "r2": 0.0, "k2": 1.0})
    win.action_geometric_pattern()                 # must not raise
    assert [f for f in win.doc.features
            if isinstance(f, GeometricPatternFeature)] == []
    assert "refused" in win.status.currentMessage().lower()


def test_scale_dialog_zero_factor_refused_not_recomputed(win, monkeypatch):
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2, "dy": 2, "dz": 2}))
    win.recompute()
    _dialog_answers(monkeypatch, {"src": "lug", "base": "0,0,0",
                                  "mode": "Per axis", "k": 1.0,
                                  "kx": 1.0, "ky": 0.0, "kz": 1.0})
    win.action_scale()
    assert [f for f in win.doc.features
            if isinstance(f, ScaleFeature)] == []
    assert "refused" in win.status.currentMessage().lower()


def test_patterns_cannot_source_themselves_in_dialogs(win):
    from tracer.core.document import LinearPatternFeature
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2, "dy": 2, "dz": 2}))
    win.recompute()
    gp = win.doc.add_geometric_pattern("lat", win.doc.features[0], n1=2,
                                       t1=5.0)
    win.recompute()
    assert gp not in win._pattern_candidates()      # lattice not a source


# ---- UI: change parameters --------------------------------------------------

def test_change_parameters_edits_lattice_and_resolves(win, monkeypatch):
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2, "dy": 2, "dz": 2}))
    win.recompute()
    gp = win.doc.add_geometric_pattern("lat", win.doc.features[0],
                                       n1=2, t1=5.0, n2=1)
    win.recompute()
    before = win.doc.result.volume
    _dialog_answers(monkeypatch, {"n1": 4, "n2": 2, "t1": 10.0,
                                  "t2": 10.0, "r1": 0.0, "r2": 0.0,
                                  "k1": 1.0, "k2": 1.0})
    win.action_change_params(gp)
    assert gp.n1 == 4 and gp.n2 == 2 and gp.t1 == 10.0
    assert win.doc.result.volume > before            # 8 copies now


def test_change_parameters_scale_factors_are_unit_free(win, monkeypatch):
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2, "dy": 2, "dz": 2}))
    win.recompute()
    sc = win.doc.add_scale("grown", win.doc.features[0], factors=1.0)
    win.recompute()
    _dialog_answers(monkeypatch, {"k0": 2.0, "k1": 1.0, "k2": 1.0})
    win.action_change_params(sc)
    assert sc.factors == pytest.approx((2.0, 1.0, 1.0))  # not unit-scaled
    win.recompute()
    assert win.doc.result.volume == pytest.approx(16.0, abs=1e-6)
