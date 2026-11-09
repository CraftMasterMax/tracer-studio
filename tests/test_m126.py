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


# ---- M201 R11: the Scale page's own words --------------------------------
# [GUID-D3F6F79B-1498-48B3-B98C-7D57B620005A, verbatim] "Scale Type:
# Uniform: Scales the selected bodies uniformly on all axes. For
# example, enter -0.5 to halve the size or 2 to double it. | Non
# Uniform: Scale along the X, Y, and Z axes separately." + "Scale
# Factor: Specify the proportional value to scale the bodies." + the
# per-axis rows the page NAMES "X Distance" ("Specifies the value to
# scale in the X direction." - a value, no units printed). "default"
# counts ZERO on the page: every rest is the house's (and the house
# rests on the identity). The anchor is the page's "pick a fixed
# anchor point for the scaling" spoken plainly; origin is NOT
# documented as the vendor's default - that rest is ours too.

def test_the_scale_door_speaks_the_pages_type_words(win, monkeypatch):
    """The door's rows wear the page's names: "Scale Type" resting
    over the page's own spellings - "Uniform" and "Non Uniform" (NO
    hyphen, the page's own) - "Scale Factor" and the three
    "X Distance"-class rows our label notes as scale VALUES (the
    page's odd name kept, the truth kept too). A LEGACY remembered
    dict (the m126-era "Per axis" word every saved session carries)
    still resolves PER AXIS - zero rewrites, R5's coin - and the
    new word walks the same path."""
    seen = []

    def spy(parent, title, fields, remember_key=None):
        seen.append({f["key"]: f for f in fields})
        return dict(src="lug", base="0,0,0", mode="Per axis", k=1.0,
                    kx=2.0, ky=1.0, kz=1.0)
    from tracer.ui import cmddialog
    monkeypatch.setattr(cmddialog, "ask", spy)
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2.0, "dy": 2.0, "dz": 2.0}))
    win.recompute()
    win.action_scale()
    rows = seen[0]
    assert list(rows) == ["src", "base", "mode", "k", "kx", "ky", "kz"]
    assert rows["mode"]["label"] == "Scale Type"          # the page's row
    assert tuple(rows["mode"]["choices"]) == ("Uniform", "Non Uniform")
    assert "Scale Factor" in rows["k"]["label"]
    assert "X Distance" in rows["kx"]["label"]            # the page's name
    assert "scale value" in rows["kx"]["label"]           # and our truth
    sc = win.doc.features[-1]
    assert isinstance(sc, ScaleFeature)
    assert sc.factors == pytest.approx((2.0, 1.0, 1.0))   # legacy word,
    win.recompute()                                        # same behavior
    assert win.doc.result.volume == pytest.approx(16.0, abs=1e-6)

    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: dict(src="lug", base="0,0,0",
                                             mode="Uniform", k=2.0,
                                             kx=1.0, ky=1.0, kz=1.0))
    win.action_scale()
    assert win.doc.features[-1].factors == pytest.approx((2.0, 2.0, 2.0))
    win.recompute()      # box [0,2]^3 inside its doubled twin [0,4]^3
    assert win.doc.result.volume == pytest.approx(64.0, abs=1e-6)


def test_the_pages_halving_example_halves_and_mirrors():
    """The page's one numeric sentence - "enter -0.5 to halve the
    size or 2 to double it" - measured on our kernel: the 4x2x1 box
    four off the origin scaled -0.5 about the origin comes back HALF
    (eight eighths to one: volume 8 -> 9 total) and BEHIND (bbox's
    far corner at -4 - the page words no sign law, our negative has
    always mirrored too, m126's pinned house fact). The copy stands
    disjoint from its source, so the arithmetic is exact: 8 + 1 = 9,
    the union to the last digit."""
    import numpy as np
    d = Document("h")
    d.add(PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 4.0, "dy": 2.0, "dz": 1.0},
                           placement=(4.0, 0.0, 0.0)))
    assert d.result.volume == pytest.approx(8.0, abs=1e-9)
    d.add(ScaleFeature(name="S", source_uid=d.features[0].uid,
                       factors=(-0.5, -0.5, -0.5)))
    d.recompute()
    assert d.result.volume == pytest.approx(9.0, abs=1e-6)
    lo, hi = np.asarray(d.result.bounding_box, float)
    assert lo[0] == pytest.approx(-4.0, abs=1e-6)   # the mirrored half
    assert lo[1] == pytest.approx(-1.0, abs=1e-6)
    assert hi[0] == pytest.approx(8.0, abs=1e-6)    # the source stands


def test_the_scale_reader_gets_its_pairs_and_speaks_the_identity():
    """The .get pair the file law demands, MEASURED: a file that
    never speaks factors loads as the IDENTITY (1,1,1) and replays
    the source volume BIT FOR BIT (the identity scale is not an
    "equal" rebuild - it is the same float, measured); a file that
    never speaks source_uid loads too, and the fold's OWN existing
    honest clause skips a scale whose source is unknown - the body
    stands as it stood. m126-era files carry both keys and replay
    untouched."""
    import json
    d = Document("g")
    d.add(PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 4.0, "dy": 2.0, "dz": 1.0}))
    src_vol = d.result.volume
    d.add(ScaleFeature(name="S", source_uid=d.features[0].uid,
                       factors=(2.0, 2.0, 2.0)))
    raw = json.loads(json.dumps(d.to_dict()))
    fd = [x for x in raw["features"] if x["type"] == "ScaleFeature"][0]
    assert fd["factors"] == [2.0, 2.0, 2.0]
    del fd["factors"]
    back = Document.from_dict(raw)
    assert back.features[1].factors == (1.0, 1.0, 1.0)
    assert back.recompute().volume == src_vol        # bit-for-bit, not approx

    raw2 = json.loads(json.dumps(d.to_dict()))
    fd2 = [x for x in raw2["features"] if x["type"] == "ScaleFeature"][0]
    del fd2["source_uid"]
    back2 = Document.from_dict(raw2)
    assert back2.features[1].source_uid == ""
    assert back2.recompute().volume == src_vol       # the fold skips it


def test_the_rail_speaks_the_scale_numbers(win):
    """The scale record finally speaks its OWN numbers: one word for
    a uniform record, three for a per-axis one ("per axis" - the
    page's story, our plain words), and the ANCHOR line joins only
    when the anchor MOVED (the (0,0,0) rest stays unsaid, absence is
    honesty). The header's op word is TRUE here - a scale INHERITS
    its source's op (m126's law), so the generic line prints the
    record's own fold word, not a stranger's (the draft's unused-op
    lie that R10 fixed is structurally impossible here)."""
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2.0, "dy": 2.0, "dz": 2.0}))
    win.recompute()
    uni = win.doc.add_scale("grown", win.doc.features[0], factors=1.5)
    win.recompute()
    win.rail.props.show_feature(uni)
    t = win.rail.props._body.text()
    assert "scale: 1.5" in t
    assert "per axis" not in t and "anchor" not in t   # one number, no move
    assert "operation: union" in t                     # the INHERITED word

    win.doc.add(PrimitiveFeature(name="lug2", kind="box",
                                 dims={"dx": 2.0, "dy": 2.0, "dz": 2.0}))
    win.recompute()
    per = win.doc.add_scale("grown2", win.doc.features[0],
                            base=(5.0, 0.0, 0.0), factors=(1.0, 2.0, 3.0))
    win.recompute()
    win.rail.props.show_feature(per)
    t = win.rail.props._body.text()
    assert "scale: 1 x 2 x 3 per axis" in t
    assert "anchor: (5, 0, 0)" in t
