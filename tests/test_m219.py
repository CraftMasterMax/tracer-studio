"""M201 R31 - the Sheet Size dialog: resize the sheet you stand on.

[DWG-REF-SHEET-SIZE, verbatim; live-verified lane D 2026-11-13, page
identical to the dwg29 bank] "the Sheet Size dialog displays." - the
TITLE is page-printed.  The dropdown prints BOTH families in this
order, every member in the page's own words: ISO first "A4 (297mm x
210mm)"..."A0", then ASME "A (11in x 8.5in)"..."E", then "Custom" -
the no-space unit strings are the book's voice (dwg29 census: ' mm'
counts 0).  "Width[]... You can change the value when you select the
Custom sheet size option. The maximum value is 200in or 5000mm." -
shown for members, honoured only under Custom (R20's honoured mm
member of the unequal pair).  Zones are "(Custom sheet size only)":
"type in a positive even number. The maximum value is 1000." - the
CONSTRAINTS are the page's; HOW zones look is proven absent from the
whole book (164/164 crawl), so the ruler is OURS-declared (letters
across the top, numbers up the left, riding the standards' reserved-
letter pool M136/M144 already keep).  A zero zone count = NO zones,
our declared reading (no Default: anywhere on the page).  The result
sentence is the task page's verbatim.  Cancel rides the book-wide
silence (counts 0 in 164 pages)."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage                                    # noqa: E402
from PySide6.QtWidgets import QApplication                          # noqa: E402

import numpy as np                                                  # noqa: E402
from tracer.core import drawing                                     # noqa: E402
from tracer.core.document import PrimitiveFeature                   # noqa: E402
from tracer.ui import cmddialog                                     # noqa: E402


# ---- the core layer -------------------------------------------------------------

def test_zone_count_wears_the_pages_words():
    assert drawing.zone_count(0, "Horizontal") == 0
    assert drawing.zone_count(None, "Vertical") == 0      # ours: none
    with pytest.raises(ValueError) as e:
        drawing.zone_count(-2, "Horizontal")
    assert "positive even number" in str(e.value)         # verbatim
    with pytest.raises(ValueError) as e:
        drawing.zone_count(3, "Horizontal")
    assert "odd" in str(e.value)
    with pytest.raises(ValueError) as e:
        drawing.zone_count(1002, "Vertical")
    assert "maximum value is 1000" in str(e.value)        # verbatim


def test_zone_grid_arithmetic_and_our_declared_letters():
    g = drawing.zone_grid(200.0, 100.0, 4, 2)
    assert g["xs"] == [50.0, 100.0, 150.0]                # hz columns
    assert g["ys"] == [50.0]                              # vz rows
    assert [l for _x, l in g["top"]] == ["A", "B", "C", "D"]
    assert [l for _y, l in g["left"]] == ["1", "2"]
    labs = [l for _x, l in drawing.zone_grid(200.0, 100.0, 20, 0)["top"]]
    # the reserved pool (OURS-declared, same coin as M136/M144):
    assert "I" not in labs and "O" not in labs and labs[8] == "J"
    with pytest.raises(ValueError) as e:
        drawing.zone_grid(200.0, 100.0, 22, 0)
    assert "letters" in str(e.value)                      # pool cap


# ---- the dialog ------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(cmddialog, "_REMEMBERED", {})     # process-global
    monkeypatch.setattr(cmddialog, "_REMEMBER_ON", {})
    try:
        from tracer.ui.mainwindow import MainWindow
        from tracer.ui.renderer import SceneRenderer
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
    r.close()


def _sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Block", kind="box", dims={"dx": 40.0, "dy": 20.0,
                                        "dz": 10.0}))
    win.recompute()
    win.action_new_drawing()
    win._show_page(win._drawing_page)
    qapp.processEvents()


def _answer(win, monkeypatch, **over):
    v = dict(size="A3 (420mm x 297mm)", w=420.0, h=297.0,
             orient="Landscape", hz=0, vz=0)
    v.update(over)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: dict(v))
    win.action_sheet_size()


def test_the_dialog_wears_the_page_title_rows_and_words(win, qapp,
                                                        monkeypatch):
    calls = []
    monkeypatch.setattr(cmddialog, "ask",
                        lambda p, t, fl, **k: (calls.append(
                            (t, {f["key"]: f for f in fl})), None)[1])
    _sheet(win, qapp)
    win.action_sheet_size()
    (title, specs), = calls
    assert title == "Sheet Size"                          # PAGE-PRINTED
    assert list(specs) == ["size", "w", "h", "orient", "hz", "vz"]
    ch = specs["size"]["choices"]
    assert ch[0] == "A4 (297mm x 210mm)"                  # page words
    assert ch[4] == "A0 (1189mm x 841mm)"
    assert ch[5] == "A (11in x 8.5in)"                    # ISO prints first
    assert ch[10] == "Custom"                             # ONE Custom
    assert specs["size"]["default"] == "A3 (420mm x 297mm)"
    assert specs["w"]["default"] == pytest.approx(420.0)  # DISPLAYED now
    assert specs["h"]["default"] == pytest.approx(297.0)
    assert specs["hz"]["default"] == 0                    # no default is
    assert specs["vz"]["default"] == 0                    #   printed: ours
    assert specs["orient"]["default"] == "Landscape"


def test_the_bare_window_refuses_with_the_house_cure(win, monkeypatch):
    calls = []
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: (calls.append(1), None)[1])
    win.new_document()
    win.action_sheet_size()
    assert calls == []                                    # no dialog to cancel
    assert win.status.currentMessage() == "Create a drawing first"


def test_members_land_and_the_family_follows_the_choice(win, qapp,
                                                        monkeypatch):
    _sheet(win, qapp)
    _answer(win, monkeypatch, size="A2 (594mm x 420mm)")
    g = win.drawing.sheet()
    assert g["page"] == "A2" and g["standard"] == "ISO"
    _answer(win, monkeypatch, size="B (17in x 11in)",
            w=431.8, h=279.4)
    assert g["page"] == "B" and g["standard"] == "ASME"
    _answer(win, monkeypatch, size="A2 (594mm x 420mm)",
            orient="Portrait")
    assert g["page"] == "A2 Portrait"
    assert win.status.currentMessage().startswith(
        "The new sheet size applies to the current sheet in the drawing")


def test_custom_lands_and_the_cap_refuses_before_state(win, qapp,
                                                       monkeypatch):
    _sheet(win, qapp)
    _answer(win, monkeypatch, size="Custom", w=6000.0, h=10.0)
    g = win.drawing.sheet()
    assert g["page"] == "A3"                              # REFUSED before
    assert "maximum value is" in win.status.currentMessage()
    _answer(win, monkeypatch, size="Custom", w=600.0, h=400.0,
            hz=4, vz=2)
    assert g["page"] == "Custom 600x400"
    assert g["zones"] == [4, 2]
    assert "zones 4 x 2 (Custom only)" in win.status.currentMessage()


def test_odd_zones_refuse_and_a_member_discards_them(win, qapp,
                                                     monkeypatch):
    _sheet(win, qapp)
    _answer(win, monkeypatch, size="Custom", w=600.0, h=400.0,
            hz=4, vz=2)
    _answer(win, monkeypatch, size="Custom", w=600.0, h=400.0,
            hz=3, vz=2)
    assert win.drawing.sheet()["zones"] == [4, 2]         # untouched
    assert "positive even number" in win.status.currentMessage()
    _answer(win, monkeypatch, size="A4 (297mm x 210mm)", hz=4, vz=2)
    g = win.drawing.sheet()
    assert g["page"] == "A4"
    assert "zones" not in g        # "(Custom sheet size only)" - a
    #                                 member DISCARDS the zone values


def test_zones_ride_the_file_and_the_ruler_changes_the_paper(win, qapp,
                                                             monkeypatch):
    def grab():
        from PySide6.QtCore import QPointF
        win.drawing._zoom = 1.1                  # whole sheet on screen
        win.drawing._center = QPointF(300, 200)  #   at a legible ruler
        win.drawing.update()
        qapp.processEvents()
        img = win.drawing.grab().toImage().convertToFormat(
            QImage.Format.Format_RGBA8888)
        return np.frombuffer(img.constBits().tobytes(), np.uint8).reshape(
            img.height(), img.bytesPerLine() // 4, 4)[
            :, :img.width(), :3].copy()

    _sheet(win, qapp)
    _answer(win, monkeypatch, size="Custom", w=600.0, h=400.0,
            hz=6, vz=4)
    back = type(win.doc).from_dict(win.doc.to_dict())     # the file's word
    assert back.drawings[0].get("zones") == [6, 4]
    with_z = grab()
    win.drawing.sheet().pop("zones")                      # ruler off
    without = grab()
    changed = int((np.abs(with_z.astype(int) - without.astype(int))
                   .max(axis=2) > 24).sum())
    assert changed > 200, f"the ruler must move pixels: {changed}"
