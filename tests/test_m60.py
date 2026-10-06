"""M60 — Document Measures: the unit is vocabulary, not geometry.

units helpers keep mm output byte-identical to the old f-strings (the
suite pins those voices); inch/cm only change how numbers are SPOKEN.
Tools ▸ Document Measures switches the vocabulary live: the inspector,
the body card and the measure card all re-voice, the unit rides the
JSON, and new documents start in mm again.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                              # noqa: E402

from conftest import script_cmd                                         # noqa: E402
from tracer.core import units                                           # noqa: E402
from tracer.core.document import Document, PrimitiveFeature             # noqa: E402
from tracer.core.measure import describe                                # noqa: E402


# ---- core ------------------------------------------------------------------------

def test_mm_voice_is_byte_identical_to_the_old_f_strings():
    assert units.L(8) == "8 mm"
    assert units.L(12.5) == "12.5 mm"
    assert units.V(8000) == "8,000.0 mm³"
    assert units.A(400) == "400.0 mm²"
    assert units.D(2.5) == "2.50 mm"


def test_inch_and_cm_conversions():
    assert units.val(25.4, "inch") == pytest.approx(1.0)
    assert units.val(30, "cm") == pytest.approx(3.0)
    assert units.L(25.4, "inch") == "1 in"
    assert units.L(30, "cm") == "3 cm"
    assert units.V(254000.0, "inch").endswith("in³")


def test_describe_respects_unit():
    a = {"area": 900.0, "planar": True, "normal": (0, 0, 1),
         "point": (0, 0, 0)}
    assert describe(a, None) == "face area 900.0 mm²"
    assert describe(a, None, "inch").endswith("in²")


def test_units_persist_in_json():
    d = Document("u")
    d.units = "inch"
    assert Document.from_dict(d.to_dict()).units == "inch"


# ---- UI ----------------------------------------------------------------------------

from tracer.ui.mainwindow import MainWindow                             # noqa: E402
from tracer.ui.renderer import SceneRenderer                            # noqa: E402


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
                                 dims={"dx": 40, "dy": 20, "dz": 10}))
    win.recompute()
    qapp.processEvents()


def test_tools_menu_holds_document_measures(win):
    menus = {a.text().replace("&", ""): a.menu()
             for a in win.menuBar().actions()}
    assert "Document Measures…" in [
        x.text().replace("&", "") for x in menus["Tools"].actions()]


def test_measure_dialog_switches_the_vocabulary(win, qapp, monkeypatch):
    _block(win, qapp)
    assert win.rail.props.unit == "mm"
    script_cmd(monkeypatch, {"unit": "Inch (in)"})
    win.action_document_measures()
    qapp.processEvents()
    assert win.doc.units == "inch"
    assert win.rail.props.unit == "inch"
    assert "Document measures: in" in win.status.currentMessage()
    win.rail.props.show_stats(8000.0, 4000.0)
    assert "in³" in win.rail.props._body.text()
    assert "in²" in win.rail.props._body.text()
    win._update_status()
    assert "units in" in win.status.currentMessage()


def test_feature_card_voices_the_unit(win, qapp, monkeypatch):
    _block(win, qapp)
    script_cmd(monkeypatch, {"unit": "Centimetre (cm)"})
    win.action_document_measures()
    feat = [f for f in win.doc.features
            if isinstance(f, PrimitiveFeature)][0]
    win.rail.props.show_feature(feat)
    text = win.rail.props._body.text()
    assert "dx: 4 cm" in text and "mm" not in text


def test_new_document_resets_to_mm(win, qapp, monkeypatch):
    _block(win, qapp)
    script_cmd(monkeypatch, {"unit": "Inch (in)"})
    win.action_document_measures()
    assert win.rail.props.unit == "inch"
    win.new_document()
    assert win.doc.units == "mm"
    assert win.rail.props.unit == "mm"
