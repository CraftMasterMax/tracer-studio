"""M19: circular rim fillets/chamfers, pure kernel (no OpenCascade).

Sharp closed loops that fit a circle are detected on the mesh, classified
convex/concave with material probes, and rounded with a revolved
"square minus quarter-disk" tool (or a 45-degree triangle for chamfers).
Because everything happens in the mesh kernel, BodyFilletFeature can now
round hole and boss rims even on stock Windows; the OCCT bridge remains
in charge of straight edges only.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

from tracer.core import step                                   # noqa: E402
from tracer.ui.cmddialog import Shell                    # noqa: E402
from tracer.core.document import (BodyFilletFeature,           # noqa: E402
                                  Document, PrimitiveFeature)
from tracer.core.geometry import Solid                         # noqa: E402
from tracer.core.rimfillet import find_rims, rim_fillet        # noqa: E402

requires_occt = pytest.mark.skipif(
    not step.available(), reason="OpenCascade not available")


def bore_plate():
    """40x40x10 plate with a through bore r=5 at the centre."""
    return (Solid.box(40, 40, 10)
            .subtract(Solid.cylinder(5, 10, center=(20, 20))))


def boss_plate():
    """60x60x5 plate with a boss cylinder r=8 h=10 standing on it."""
    return (Solid.box(60, 60, 5)
            .union(Solid.cylinder(8, 10, center=(30, 30))))


def v_corner(r, R, dr):
    """Revolved volume of the corner square minus its inscribed
    quarter-disk, on the radial side `dr` of the rim."""
    sq = math.pi * abs((r + dr * R) ** 2 - r * r) * R
    rho_c = r + dr * (R - 4 * R / (3 * math.pi))
    qd = 2 * math.pi * rho_c * (math.pi * R * R / 4)
    return sq - qd


def v_bevel(r, R, dr):
    """Same for the chamfer triangle."""
    return math.pi * (r + dr * R / 3) * R * R


def plate_doc():
    d = Document(title="bored")
    d.add_plate("Plate1", 40, 40, 10, holes=[(20, 20, 5.0)])
    return d


# ---- detection & classification -------------------------------------------
def test_finds_and_classifies_bore_rims():
    rims = find_rims(bore_plate())
    assert len(rims) == 2                     # opening + exit, no other loops
    assert all(abs(r["radius"] - 5) < 0.05 for r in rims)
    assert all(not r["concave"] for r in rims)          # both are cut
    assert all(r["dr_mat"] > 0 for r in rims)           # material outside wall
    assert sorted(int(r["dh_mat"]) for r in rims) == [-1, 1]  # top + bottom


def test_finds_concave_boss_base():
    rims = find_rims(boss_plate())
    by = {(round(r["radius"]), r["concave"]) for r in rims}
    assert (8, True) in by                    # bead at the base
    assert (8, False) in by                   # cutter on the boss top
    assert len(rims) == 2                     # square plate rims are skipped


def test_square_loops_are_not_rims():
    assert find_rims(Solid.box(10, 10, 10)) == []


# ---- pure geometry vs closed form ------------------------------------------
def test_bore_rim_fillet_matches_analytic():
    src = bore_plate()
    out, n = rim_fillet(src, 2.0)
    assert n == 2
    assert out.volume == pytest.approx(
        src.volume - 2 * v_corner(5, 2, +1), rel=0.005)
    assert out.to_trimesh().is_watertight


def test_boss_bead_adds_material():
    src = boss_plate()
    out, n = rim_fillet(src, 2.0)
    assert n == 2
    expect = v_corner(8, 2, +1) - v_corner(8, 2, -1)   # bead minus top cut
    assert out.volume - src.volume == pytest.approx(expect, abs=1.5)
    assert out.to_trimesh().is_watertight


def test_rim_chamfer_matches_analytic():
    src = bore_plate()
    out, n = rim_fillet(src, 2.0, chamfer=True)
    assert n == 2
    assert out.volume == pytest.approx(
        src.volume - 2 * v_bevel(5, 2, +1), rel=0.002)
    assert out.to_trimesh().is_watertight


def test_rim_fillet_is_idempotent():
    once, n1 = rim_fillet(bore_plate(), 2.0)
    twice, n2 = rim_fillet(once, 2.0)         # tangent blend: nothing sharp
    assert n1 == 2 and n2 == 0
    assert twice.volume == pytest.approx(once.volume, rel=1e-9)


def test_oversized_tool_skips_rim_without_crashing():
    cyl = Solid.cylinder(3, 10)               # cutter would cross the axis
    out, n = rim_fillet(cyl, 4.0)
    assert n == 0
    assert out.volume == pytest.approx(cyl.volume)


# ---- document feature ------------------------------------------------------
def test_feature_rounds_rims_without_occt(monkeypatch):
    monkeypatch.setattr(step, "available", lambda: False)
    d = plate_doc()
    base = d.recompute().volume
    f = d.add(BodyFilletFeature(name="Fillet1", radius=2.0))
    v = d.recompute()
    assert f.n_rims == 2                      # the Windows promise
    assert v.volume == pytest.approx(
        base - 2 * v_corner(5, 2, +1), rel=0.005)
    assert v.to_trimesh().is_watertight


def test_feature_without_occt_or_rims_raises(monkeypatch):
    monkeypatch.setattr(step, "available", lambda: False)
    d = Document()
    d.features.append(PrimitiveFeature(name="B", kind="box",
                                       dims={"dx": 30, "dy": 30, "dz": 6}))
    d.add(BodyFilletFeature(name="Fillet1", radius=2.0))
    with pytest.raises(RuntimeError, match="OpenCascade"):
        d.recompute()


@requires_occt
def test_occt_rejection_falls_back_to_rims(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bridge said no")
    monkeypatch.setattr(step, "fillet_mesh", boom)
    d = plate_doc()
    base = d.recompute().volume
    f = d.add(BodyFilletFeature(name="Fillet1", radius=2.0))
    v = d.recompute()                         # rims rescue the feature
    assert f.n_rims == 2
    assert v.volume < base


@requires_occt
def test_occt_and_rims_both_run(monkeypatch):
    d = plate_doc()
    f = d.add(BodyFilletFeature(name="Fillet1", radius=2.0))
    v = d.recompute()
    assert f.n_rims == 2                      # rims done kernel-side
    # straight box edges were filleted by OCCT too: a plain rounded box of
    # the same size keeps more material than this (the bore took its share)
    assert v.to_trimesh().is_watertight
    assert f.src_key[-1] == 2                 # M19 cache-key version


def test_m18_4_element_key_recomputes():
    """Documents saved before M19 carry a 4-element src_key: they must
    miss the cache and run the new rim pass exactly once."""
    d = plate_doc()
    f = d.add(BodyFilletFeature(name="Fillet1", radius=2.0))
    v1 = d.recompute()
    f.src_key = f.src_key[:4]                 # pretend it came from M18
    d.dirty = True
    v2 = d.recompute()
    assert len(f.src_key) == 5
    assert v2.volume == pytest.approx(v1.volume, rel=1e-9)


def test_bake_roundtrip_survives_bare_machine(monkeypatch):
    d = plate_doc()
    d.add(BodyFilletFeature(name="Fillet1", radius=2.0))
    v = d.recompute()
    d2 = Document.from_dict(d.to_dict())
    monkeypatch.setattr(step, "available", lambda: False)
    got = d2.recompute()                      # cache hit -> baked mesh
    assert got.volume == pytest.approx(v.volume, rel=1e-9)
    assert d2.features[-1].n_rims == 2        # count survived serialization
    assert len(d.to_dict()["features"][-1]["src_key"]) == 5


# ---- UI --------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


def test_fillet_cmd_works_without_occt(win, qapp, monkeypatch):
    monkeypatch.setattr(step, "available", lambda: False)
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *a, **k: (2.0, True)))
    win.new_document()
    win.doc.add_plate("Plate1", 40, 40, 10, holes=[(20, 20, 5.0)])
    base = win.doc.recompute().volume
    win._body_fillet(chamfer=False)
    qapp.processEvents()
    f = win.doc.features[-1]
    assert isinstance(f, BodyFilletFeature) and f.n_rims == 2
    assert win.doc.result.volume < base
    assert "circular rim" in win.status.currentMessage()


def test_fillet_cmd_without_occt_or_rims_rolls_back(win, qapp, monkeypatch):
    monkeypatch.setattr(step, "available", lambda: False)
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *a, **k: (2.0, True)))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a[1])))
    win.new_document()
    win.doc.features.append(PrimitiveFeature(name="B", kind="box",
                                             dims={"dx": 30, "dy": 30,
                                                   "dz": 6}))
    win.doc.recompute()
    win._body_fillet(chamfer=False)
    qapp.processEvents()
    assert warned == ["Fillet failed"]
    assert not any(isinstance(f2, BodyFilletFeature)
                   for f2 in win.doc.features)
    assert win.doc.result.volume == pytest.approx(30 * 30 * 6)
