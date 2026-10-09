"""M71 — Mass properties: the maker's first question, answered.

Fusion's Inspect ▸ Mass Properties.  Kernel truth first: a 20 mm cube
weighs 8000 mm³ (exactly mass 8 g at density 1.0), 2400 mm² of surface,
centre of mass dead on its middle.  Then the command end to end: a
material-density dialog (13 shop materials, PLA default), the readout in
DOCUMENT measures (an inch document shows in³), the choice remembered,
and the centre of mass tracking an off-origin body.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from pathlib import Path                                                # noqa: E402

from PySide6.QtCore import QSettings                                    # noqa: E402
from PySide6.QtWidgets import (QApplication, QMessageBox)               # noqa: E402

from conftest import script_cmd, script_cmd_cancel                     # noqa: E402
from tracer.core.document import Document, PrimitiveFeature            # noqa: E402
from tracer.core.measure import mass_properties


# ---- core -------------------------------------------------------------------------

def test_mass_properties_of_a_cube_are_exact():
    d = Document("m")
    d.add(PrimitiveFeature(name="c", kind="box",
                           dims={"dx": 20, "dy": 20, "dz": 20}))
    s = d.recompute()
    p = mass_properties(s, 1.0)
    assert p["volume_mm3"] == pytest.approx(8000, rel=1e-6)
    assert p["area_mm2"] == pytest.approx(2400, rel=1e-6)
    assert p["mass_g"] == pytest.approx(8.0, rel=1e-6)     # 8 cm³ · 1
    assert np.allclose(p["com"], (10, 10, 10), atol=1e-3)


def test_density_scales_the_mass():
    d = Document("m")
    d.add(PrimitiveFeature(name="c", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10}))
    p = mass_properties(d.recompute(), 7.85)              # steel
    assert p["mass_g"] == pytest.approx(1000 / 1000 * 7.85, rel=1e-6)


def test_centre_of_mass_follows_an_off_origin_body():
    d = Document("m")
    d.add(PrimitiveFeature(name="c", kind="box",
                           dims={"dx": 20, "dy": 20, "dz": 20},
                           placement=(30, 0, 0)))
    p = mass_properties(d.recompute(), 1.0)
    assert p["com"][0] == pytest.approx(40, abs=1e-2)


# ---- UI ---------------------------------------------------------------------------

from tracer.ui.mainwindow import MainWindow                            # noqa: E402
from tracer.ui.renderer import SceneRenderer                           # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, tmp_path):
    s = QSettings()
    key = "materials/density"
    saved = s.value(key, None)
    s.remove(key)
    s.sync()
    try:
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
    finally:
        s2 = QSettings()
        if saved is None:
            s2.remove(key)
        else:
            s2.setValue(key, saved)
        s2.sync()


def _cube(win, qapp, dims=(20, 20, 20), place=(0, 0, 0)):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="c", kind="box",
                                 dims={"dx": dims[0], "dy": dims[1],
                                       "dz": dims[2]},
                                 placement=place))
    win.recompute()
    qapp.processEvents()


def test_mass_dialog_reports_weight_in_grammes(win, qapp, monkeypatch):
    _cube(win, qapp)
    script_cmd(monkeypatch, {"material": "Steel (7.85)"})
    seen = {}
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: seen.update(t=self.text()) or 0)
    win.action_mass_properties()
    qapp.processEvents()
    # 20 mm cube = 8 cm³ of steel at 7.85 g/cm³ = 62.80 g
    assert "Mass" in seen["t"] and "62.80 g" in seen["t"]
    assert "8,000.0 mm\u00b3" in seen["t"]          # volume in mm
    assert "Steel" in seen["t"]
    assert "62.80 g" in win.status.currentMessage()


def test_material_choice_is_remembered(win, qapp, monkeypatch):
    _cube(win, qapp)
    script_cmd(monkeypatch, {"material": "Brass (8.50)"})
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    win.action_mass_properties()
    assert QSettings().value("materials/density") == "Brass (8.50)"
    # a later run defaults to the remembered material
    asked = {}

    def spy(parent, title, fields, *a, **k):
        asked["default"] = fields[0]["default"]
        return None
    monkeypatch.setattr("tracer.ui.cmddialog.ask", spy)
    win.action_mass_properties()
    assert asked["default"] == "Brass (8.50)"


def test_inch_document_reads_cubic_inches(win, qapp, monkeypatch):
    _cube(win, qapp)
    win.doc.units = "inch"
    win._apply_units()
    script_cmd(monkeypatch, {"material": "PLA (1.24)"})
    seen = {}
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: seen.update(t=self.text()) or 0)
    win.action_mass_properties()
    qapp.processEvents()
    assert "in\u00b3" in seen["t"]


def test_cancel_and_empty_are_quiet(win, qapp, monkeypatch):
    _cube(win, qapp)
    script_cmd_cancel(monkeypatch)
    hit = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: hit.append(1))
    win.action_mass_properties()
    assert not hit                                  # cancelled -> no box
    win.new_document()
    warn = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: warn.append(a)))
    win.action_mass_properties()
    assert warn and "Nothing to measure" in warn[0][2]
