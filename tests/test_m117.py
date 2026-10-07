"""M117 — the measure win-pack: extents, inertia, section numbers.

The math must match textbook solids; the dialogs must actually speak
the new lines; the section readout must land in the status bar.
Fusion has none of these surfaces [—V] — every line here is a beat.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                        # noqa: E402

from tracer.core.geometry import Solid                            # noqa: E402
from tracer.core.measure import (extents, principal_inertia,      # noqa: E402
                                 section_properties)


# ---- core math vs the textbook -------------------------------------------------
def test_extents_are_the_honest_box():
    e = extents(Solid.box(40.0, 20.0, 10.0))
    assert e["size_mm"] == pytest.approx((40.0, 20.0, 10.0))
    assert e["diagonal_mm"] == pytest.approx(np.sqrt(1600 + 400 + 100))
    assert e["min_mm"] == pytest.approx((0.0, 0.0, 0.0))


def test_cube_inertia_is_the_classroom_number():
    # 10 mm cube at 1 g/cm³: m = 1 g, I = m·2a²/12 = 16.667 g·mm²
    pr = principal_inertia(Solid.box(10.0, 10.0, 10.0), 1.0)
    assert pr["mass_g"] == pytest.approx(1.0, abs=1e-9)
    assert pr["moments_g_mm2"] == pytest.approx((16.6667,) * 3, abs=0.01)
    # about the COG, so the corner-placed box needs no parallel-axis cry
    assert pr["com"] == pytest.approx((5.0, 5.0, 5.0), abs=1e-6)


def test_inertia_rides_with_the_solid():
    base = principal_inertia(Solid.box(10.0, 4.0, 2.0), 1.0)
    moved = principal_inertia(Solid.box(10.0, 4.0, 2.0).translated(
        [50.0, -20.0, 7.0]), 1.0)
    assert moved["moments_g_mm2"] == pytest.approx(
        base["moments_g_mm2"], abs=0.01)
    assert moved["com"] == pytest.approx(base["com"] + np.array(
        [50.0, -20.0, 7.0]), abs=1e-6)


def test_cylinder_moments_match_the_table():
    cyl = Solid.cylinder(5.0, 12.0)
    pr = principal_inertia(cyl, 1.0)
    m = np.pi * 25.0 * 12.0 / 1000.0
    izz, ixx = m * 25.0 / 2.0, m * (75.0 + 144.0) / 12.0
    moments = sorted(pr["moments_g_mm2"])
    assert moments[0] == pytest.approx(izz, rel=0.02)     # the short one
    assert moments[2] == pytest.approx(ixx, rel=0.02)


def test_sphere_is_two_fifths_mr2():
    sph = Solid.sphere(5.0)
    pr = principal_inertia(sph, 1.0)
    m = 4.0 / 3.0 * np.pi * 125.0 / 1000.0
    assert pr["mass_g"] == pytest.approx(m, rel=0.01)
    mid = sorted(pr["moments_g_mm2"])[1]
    assert mid == pytest.approx(0.4 * m * 25.0, rel=0.03)


def test_principal_axes_are_orthonormal():
    axes = principal_inertia(Solid.box(8.0, 3.0, 5.0), 1.0)["axes"]
    assert axes.T @ axes == pytest.approx(np.eye(3), abs=1e-9)


# ---- section properties (the shoelace beat) -------------------------------------
SQ = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]


def test_shoelace_square_is_exact():
    sp = section_properties([SQ])
    assert sp["area_mm2"] == pytest.approx(800.0)
    assert sp["perimeter_mm"] == pytest.approx(120.0)
    assert sp["centroid"] == pytest.approx((20.0, 10.0))
    assert sp["holes"] == 0


def test_nested_loop_becomes_a_hole():
    hole = [(10.0, 5.0), (30.0, 5.0), (30.0, 15.0), (10.0, 15.0)]
    sp = section_properties([SQ, hole])
    assert sp["area_mm2"] == pytest.approx(600.0)     # 800 − 20·10
    assert sp["holes"] == 1
    # wetted perimeter counts BOTH rims — that's the cut edge a tool sees
    assert sp["perimeter_mm"] == pytest.approx(120.0 + 60.0)
    # reversed winding must not change a thing
    sp2 = section_properties([SQ[::-1], hole])
    assert sp2["area_mm2"] == pytest.approx(600.0)


def test_two_islands_add():
    far = [(100.0, 0.0), (110.0, 0.0), (110.0, 10.0), (100.0, 10.0)]
    sp = section_properties([SQ, far])
    assert sp["area_mm2"] == pytest.approx(900.0)
    assert sp["holes"] == 0


def test_empty_cut_says_nothing():
    assert section_properties([]) is None
    assert section_properties([[(0, 0), (1, 1)]]) is None


def test_real_cut_of_a_cylinder():
    from tracer.core import drawing
    cyl = Solid.cylinder(5.0, 12.0)
    sp = section_properties(drawing.section(cyl, "Z", 6.0)["cut"])
    assert sp["area_mm2"] == pytest.approx(np.pi * 25.0, rel=0.01)
    assert sp["perimeter_mm"] == pytest.approx(2.0 * np.pi * 5.0,
                                               rel=0.01)


# ---- the dialogs ----------------------------------------------------------------
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
    except ImportError:
        pytest.skip("no PySide6")


def _box_doc(win):
    from tracer.core.document import PrimitiveFeature
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="b", kind="box", dims={"dx": 10.0, "dy": 10.0, "dz": 10.0}))
    win.doc.recompute()


def test_mass_dialog_speaks_inertia_and_extents(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.ui import cmddialog
    _box_doc(win)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"material": "PLA (1.24)"})
    shown = {}
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: shown.setdefault(
                            "text", self.text()) or 0)
    win.action_mass_properties()
    t = shown["text"]
    assert "Extents:" in t and "Inertia (COG):" in t
    assert "kg·cm²" in t
    # 10 mm cube at PLA 1.24: I = 1.24 g × 16.667 g·mm²/g ÷ 1e5 ≈ 0.000207
    assert "0.000207" in t or "2.07e-04" in t.replace("e-4", "e-04") \
        or "0.00021" in t


def test_show_extents_reports_the_box(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    _box_doc(win)
    texts = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: texts.append(a[2])))
    win.action_show_extents()
    qapp.processEvents()
    assert any("Bounding box" in t and "Diagonal" in t for t in texts)
    assert "10 mm" in texts[0]


def test_section_view_carries_its_numbers(win, qapp, monkeypatch):
    from tracer.core.document import PrimitiveFeature
    from tracer.ui import cmddialog
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="c", kind="cylinder",
        dims={"radius": 5.0, "height": 12.0}))
    win.doc.recompute()
    win.action_new_drawing()
    qapp.processEvents()
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "action": "New section", "axis": "Z (horizontal cut)",
        "at": 6.0})
    win.action_section_view()
    qapp.processEvents()
    msg = win.status.currentMessage()
    assert "mm²" in msg and "perimeter" in msg
    assert "78.5" in msg                       # π·5² ≈ 78.54
