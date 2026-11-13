"""M201 R20 - the Create Drawing door wears the sheet pages.

[DWG-REF-CREATE-DRAWING + DWG-REF-SHEET-SIZE + DWG-REF-DOCUMENT-
SETTINGS, verbatim] "In the Create Drawing dialog, set the Destination
options, and click OK."  The sheet-size page prints TWO families -
ISO {A4 (297mm x 210mm) | A3 | A2 | A1 | A0 | Custom} and ASME
{A (11in x 8.5in) | B | C | D | E | Custom} - and Orientation
{Landscape | Portrait}; the inch members convert by the EXACT 25.4
law (R16), computed not copied.  "The maximum value is 200in or
5000mm." caps Custom - a vendor DEFECT (200 in IS 5080 mm): we honour
the millimetre member of the pair.  "The default is ISO." is one of
the whole drawing book's THREE printed defaults, so Standard rests at
the PAGE's word; Sheet size (A3) and Orientation (Landscape) rest at
STAMPS - no page prints defaults for them.  Base Document offers only
FROM SCRATCH (no template kernel).  UNOFFERED by law: Units (voice
rides the design; the page pair "default is ISO" with "default is in
(inches)" is the vendor's own contradiction), Sheet Count (it prints
"Default is 1." and one sheet per drawing IS the kernel), Destination
/ Contents / Representation / Storyboard / Automation (no reference,
storyboard or multi-sheet kernels).  The old "New drawing…" mouth is
gone: the UI's ONE drawing mouth is the door; action_new_drawing
survives as the creation PRIMITIVE the door lands on (tests stage
through it - the m199 precedent).
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox      # noqa
from PySide6.QtWidgets import QLabel, QLineEdit                       # noqa

from conftest import script_cmd                                       # noqa
from tracer.core import drawing                                       # noqa
from tracer.core.document import PrimitiveFeature                     # noqa
from tracer.ui import cmddialog                                       # noqa
from tracer.ui.mainwindow import MainWindow                           # noqa
from tracer.ui.renderer import SceneRenderer                          # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    w.new_document()
    w.doc.add(PrimitiveFeature(name="b", kind="box",
                               dims={"dx": 40, "dy": 30, "dz": 10}))
    w.recompute()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


@pytest.fixture(autouse=True)
def _no_memory():
    yield
    cmddialog._REMEMBERED.pop("create_drawing", None)


def _menu_text(win, which):
    for a in win.menuBar().actions():
        if a.text().replace("&", "") == which:
            return [x.text() for x in a.menu().actions()]
    return []


# ---- the sheet table, verbatim families -------------------------------------

def test_the_two_families_are_the_pages_own_numbers():
    """ISO prints A4 297x210 through A0 1189x841 (mm); ASME prints
    A..E in INCHES - and the clone stores them by the exact 25.4 law,
    so sheet B is 17 x 11 in to the last decimal the law allows."""
    assert drawing.PAGES["A4"] == (297.0, 210.0)
    assert drawing.PAGES["A3"] == (420.0, 297.0)
    assert drawing.PAGES["A2"] == (594.0, 420.0)
    assert drawing.PAGES["A1"] == (841.0, 594.0)
    assert drawing.PAGES["A0"] == (1189.0, 841.0)
    assert drawing.sheet_size("A") == pytest.approx((279.4, 215.9))
    assert drawing.sheet_size("B") == pytest.approx((431.8, 279.4))
    assert drawing.sheet_size("E") == pytest.approx((1117.6, 863.6))
    assert drawing.SHEET_FAMILIES["ISO"] == ["A4", "A3", "A2", "A1", "A0"]
    assert drawing.SHEET_FAMILIES["ASME"] == ["A", "B", "C", "D", "E"]


def test_orientation_and_custom_grammar_and_the_mm_cap():
    """Portrait is the page's word riding the long-edge swap;
    "Custom WxH" speaks millimetres; the cap refuses a custom sheet
    over 5000 mm - and proves we honour the MILLIMETRE member of the
    page's unequal pair by refusing even 200 in worth of sheet."""
    assert drawing.sheet_size("A3 Portrait") == (297.0, 420.0)
    assert drawing.sheet_size("Custom 500x350") == (500.0, 350.0)
    assert drawing.sheet_size("Custom 500x350 Portrait") == (350.0, 500.0)
    assert drawing.sheet_size("Custom 5000x10") == (5000.0, 10.0)
    with pytest.raises(ValueError, match="maximum value of 5000 mm"):
        drawing.sheet_size("Custom 6000x100")
    with pytest.raises(ValueError, match="maximum value of 5000 mm"):
        drawing.sheet_size("Custom 5080x100")     # 200 in in mm - DEFECT
    with pytest.raises(ValueError, match="Custom <W>x<H>"):
        drawing.sheet_size("Custom 500 by 350")


def test_unknown_keys_keep_the_old_robust_voice():
    """A file naming a sheet the clone has never heard of still draws
    the house A3 - the pre-R20 fallback, voice unchanged."""
    assert drawing.sheet_size("D3") == (420.0, 297.0)


# ---- the door -----------------------------------------------------------------

def test_the_create_menu_wears_the_dialogs_own_name(win):
    """The page names its dialog ("In the Create Drawing dialog...")
    - the menu mouth IS that name; the coined "New drawing..." is gone
    from the UI."""
    items = _menu_text(win, "Create")
    assert "Create Drawing…" in items, items
    assert not any("New drawing" in t for t in items), items


def test_the_door_rows_and_the_printed_defaults(win, monkeypatch):
    """Standard rests at ISO because the PAGE says so ("The default
    is ISO." - one of the drawing book's only printed defaults);
    Base Document offers only From Scratch (no template kernel);
    Orientation and the A3 rest are STAMPS; Sheet Count is absent -
    its printed default of 1 is exactly what the kernel builds."""
    calls = []

    def fake(parent, title, fields, remember_key=None):
        calls.append((title, fields))
        raise _Stop
    monkeypatch.setattr(cmddialog, "ask", fake)

    class _Stop(Exception):
        pass
    import contextlib
    with contextlib.suppress(_Stop):
        win.action_create_drawing()
    title, fields = calls[0]
    assert title == "Create Drawing"
    by = {f["key"]: f for f in fields}
    assert by["base"]["choices"] == ["From Scratch"]
    assert by["standard"]["choices"] == ["ISO", "ASME"]
    assert by["standard"]["default"] == "ISO"
    assert by["orient"]["choices"] == ["Landscape", "Portrait"]
    assert by["orient"]["default"] == "Landscape"
    assert by["size"]["default"] == "A3"
    assert by["open"]["label"] == "Open Drawing After Generation"
    assert by["open"]["default"] is True
    for absent in ("count", "units", "type", "contents", "destination"):
        assert absent not in by


def test_the_door_lands_family_and_orientation_on_the_sheet(win, monkeypatch):
    """ASME + "B Portrait" rides the drawing entry and the sheet
    really measures 279.4 x 431.8 - the status line's numbers ARE the
    sheet's, quoted from the same sheet_size the painter uses."""
    script_cmd(monkeypatch, {"base": "From Scratch", "standard": "ASME",
                             "size": "B", "orient": "Portrait",
                             "open": True})
    win.action_create_drawing()
    g = win.doc.drawings[-1]
    assert g["page"] == "B Portrait"
    W, H = drawing.sheet_size(g["page"])
    assert (W, H) == pytest.approx((279.4, 431.8))
    msg = win.status.currentMessage()
    assert "ASME B Portrait" in msg and f"{W:g} x {H:g}" in msg, msg


def test_an_iso_door_refuses_an_asme_word_by_name(win, monkeypatch):
    """"B" belongs to the ASME page; under ISO the door refuses citing
    the family it prints, and NO drawing is born."""
    n = len(win.doc.drawings)
    script_cmd(monkeypatch, {"base": "From Scratch", "standard": "ISO",
                             "size": "B", "orient": "Landscape",
                             "open": True})
    win.action_create_drawing()
    assert len(win.doc.drawings) == n
    msg = win.status.currentMessage()
    assert "not in the ISO family" in msg and "A4, A3, A2, A1, A0" in msg


def test_a_custom_over_the_cap_refuses_quoting_the_page(win, monkeypatch):
    n = len(win.doc.drawings)
    script_cmd(monkeypatch, {"base": "From Scratch", "standard": "ISO",
                             "size": "Custom 6000x100",
                             "orient": "Landscape", "open": True})
    win.action_create_drawing()
    assert len(win.doc.drawings) == n
    assert "Sheet refused" in win.status.currentMessage()
    assert "maximum value of 5000 mm" in win.status.currentMessage()


def test_open_unchecked_creates_the_sheet_and_stays_in_the_model(
        win, monkeypatch):
    """The page's row, honoured: the sheet still gets built, the eyes
    just stay on the 3D."""
    script_cmd(monkeypatch, {"base": "From Scratch", "standard": "ISO",
                             "size": "A4", "orient": "Landscape",
                             "open": False})
    win.action_create_drawing()
    assert win.doc.drawings[-1]["page"] == "A4"
    assert win.stack.currentWidget() is win.viewport


def test_the_declarations_stand_at_the_door():
    doc = " ".join(MainWindow.action_create_drawing.__doc__.split())
    assert "The default is ISO." in doc
    assert "The maximum value is 200in or 5000mm." in doc
    assert "200 in is 5080 mm" in doc               # DEFECT, flagged
    assert "Default is 1." in doc                   # Sheet Count law
    prim = " ".join(MainWindow.action_new_drawing.__doc__.split())
    assert "CREATION PRIMITIVE" in prim
    assert "A3-and-landscape is OURS" in prim
