"""M86 — Utilities ▸ 3D Print: the honest print-readiness dialog.

Fusion's 3D Print button inspects, weighs against a material, warns
what the slicer will hate and exports a bed-ready STL.  Same here,
with no fake printer driver and no cloud: the report is computed from
the real mesh (triangles, watertightness, islands, bed size), the
mass uses the SAME material table as Mass Properties, and "drop to
bed" translates the EXPORTED copy only — the document never moves.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                           # noqa: E402

from tracer.core import printcheck                                   # noqa: E402
from tracer.core.document import (Document, LinearPatternFeature,
                                  PrimitiveFeature)
from tracer.core.geometry import Solid


# ------------------------------------------------------------------ report

def test_clean_box_reports_clean():
    rep = printcheck.print_report(Solid.box(10, 10, 10), 1.24)
    assert rep["watertight"] is True
    assert rep["islands"] == 1
    assert rep["volume_mm3"] == pytest.approx(1000.0, rel=1e-6)
    assert rep["mass_g"] == pytest.approx(1.24, rel=1e-6)   # 1 cm³ PLA
    assert rep["triangles"] >= 12
    assert rep["warnings"] == []


def test_far_apart_twins_become_islands():
    a = Solid.box(10, 10, 10)
    b = a.translated((50.0, 0.0, 0.0))
    rep = printcheck.print_report(a.union(b))
    assert rep["islands"] == 2
    assert any("island" in w.lower() for w in rep["warnings"])


def test_bed_size_and_thinness_warn():
    big = printcheck.print_report(Solid.box(300, 100, 10))
    assert any("bed" in w.lower() for w in big["warnings"])
    thin = printcheck.print_report(Solid.box(40, 40, 0.3))
    assert any("thick" in w.lower() for w in thin["warnings"])


def test_drop_to_bed_only_touches_the_copy():
    s = Solid.box(10, 10, 10).translated((0, 0, 37.0))
    tm = printcheck.drop_to_bed(s)
    assert float(tm.bounds[0][2]) == pytest.approx(0.0, abs=1e-9)
    assert float(s.bounding_box[0][2]) == pytest.approx(37.0, abs=1e-6)
    assert tm.volume == pytest.approx(1000.0, rel=1e-6)


# -------------------------------------------------------------------- UI

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


def _plate(win):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Plate", kind="box",
        dims={"dx": 40.0, "dy": 40.0, "dz": 4.0}))
    win.doc.features[-1].placement = (0.0, 0.0, 12.0)   # floating high
    win.recompute()


def test_the_dialog_reports_and_exports_a_bed_ready_stl(win, qapp,
                                                        tmp_path,
                                                        monkeypatch):
    from tracer.ui import cmddialog, mainwindow as MW
    _plate(win)
    seen = []

    def fake(parent, title, fields, *a, **k):
        seen.append({f["key"]: f for f in fields})
        return {f["key"]: f.get("default") for f in fields}

    out = tmp_path / "print.stl"
    monkeypatch.setattr(cmddialog, "ask", fake)
    monkeypatch.setattr(MW.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "STL")))
    win.action_3d_print()
    qapp.processEvents()
    report = seen[0]["report"]["default"]
    assert "Watertight: yes" in report
    assert "7.9 g" in report                 # 6.4 cm³ @ PLA 1.24
    assert "6,400.0 mm³" in report
    assert out.exists()
    import trimesh
    tm = trimesh.load(str(out))
    assert float(tm.bounds[0][2]) == pytest.approx(0.0, abs=1e-6)
    assert tm.volume == pytest.approx(6400.0, rel=1e-3)
    assert win.doc.result.bounding_box[0][2] == pytest.approx(12.0)


def test_cancel_changes_nothing(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    _plate(win)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: None)
    called = []
    monkeypatch.setattr(
        "tracer.ui.mainwindow.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: called.append(1) or ("", "")))
    win.action_3d_print()
    qapp.processEvents()
    assert called == []


def test_print_menu_entry_exists(win, qapp):
    labels = [a.text().replace("&", "")
              for a in win.menuBar().actions()[6].menu().actions()]
    assert any("3D Print" in t for t in labels)
