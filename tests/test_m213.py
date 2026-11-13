"""M201 R25 - the Hole dialog wears the Hole reference's row words.

[Hole reference, GUID-3A76B269-8C8D-437B-8F4A-85D0B2BBA492, verbatim]
"Placement: Select At Point (Single Hole) or From Sketch (Multiple
Holes)." - our mouth drills at the sketch editor's circles, so the row
carries that ONE member; "Extents: Select Distance, To, or All." -
Distance and All land, the born "Through all" checkbox was All in
under-dressed clothes, and "To" stays unoffered (no terminate-on-face
kernel); "Hole Type", "Tip Angle", and the bore pairs in the page's
printed order - "Counterbore Depth" BEFORE "Counterbore Diameter"
(the born dialog had them reversed). [Thread reference, GUID-
C37E8172-DE94-4EB0-AFE3-9D3172328441] lends "Modeled" and "Class".
The values KEY law: label is UI law, key is file law - through stays
the file's word (m201 R7 pinned its very slot in the dict).
Defects flagged not cloned: H2 (gloss drops a word), H3 (Press Pull
"comment"), H5 (Objects to Cut/cut), H6 (Modeled missing from the
Hole reference), H8 (Taper Tapped gate rides only the task page).
"""
import pytest

pytest.importorskip("PySide6")

from pathlib import Path                                      # noqa

from PySide6.QtWidgets import (QApplication, QFormLayout,         # noqa
                               QLabel)

from tracer.ui.hole import HoleDialog                             # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _labels(dlg):
    """(label text, field) for every form row, in LAYOUT order."""
    out = []
    for i in range(dlg._form.rowCount()):
        lab = dlg._form.itemAt(i, QFormLayout.LabelRole)
        fld = dlg._form.itemAt(i, QFormLayout.FieldRole)
        w = lab.widget() if lab is not None else None
        out.append((w.text() if isinstance(w, QLabel) else "",
                    fld.widget() if fld is not None else None))
    return out


def _fresh():
    return HoleDialog(None, [6.0])


# ---- the new rows ---------------------------------------------------------------

def test_the_placement_row_offers_only_what_the_mouth_sees(qapp):
    """One member: the page's second placement word. At Point needs
    the canvas face/point picker (and its References row gate) that
    this dialog has never owned - the kernel cannot bake what the row
    would promise, so the combo never pretends."""
    dlg = _fresh()
    assert dlg.placement.count() == 1
    assert dlg.placement.itemText(0) == "From Sketch (Multiple Holes)"
    texts = [t for t, _w in _labels(dlg)]
    assert "Placement" in texts
    assert texts.index("Placement") == 0            # the page's row 1


def test_the_extents_row_replaces_the_born_check(qapp):
    """{Distance | All}: the page's words; "To" unoffered (no
    terminate kernel). The REST is Distance - the legacy voice, a
    declared stamp (the page prints zero defaults)."""
    dlg = _fresh()
    texts = [t for t, _w in _labels(dlg)]
    assert "Extents" in texts
    assert texts.index("Extents") < texts.index("Hole Type")   # page
    by = dict(_labels(dlg))
    ext = by["Extents"]
    assert [ext.itemText(i) for i in range(ext.count())] == ["Distance",
                                                             "All"]
    assert dlg.values()["through"] is False         # rest = Distance
    old = [t for t, _w in _labels(dlg)]
    assert "Through all" not in old                 # the check is gone


def test_the_extents_row_keeps_the_one_voice_law(qapp):
    dlg = _fresh()
    assert dlg.depth.isEnabled()                  # Distance speaks
    dlg.extents.setCurrentText("All")
    assert not dlg.depth.isEnabled()              # All silences it
    assert dlg.values()["through"] is True        # the FILE's word
    dlg.extents.setCurrentText("Distance")
    assert dlg.depth.isEnabled()
    assert dlg.values()["through"] is False


# ---- the retitles and the page order ---------------------------------------------

def test_the_rows_wear_the_pages_words_in_the_pages_order(qapp):
    dlg = _fresh()
    texts = [t for t, _w in _labels(dlg)]
    for word in ("Placement", "Extents", "Hole Type", "Depth",
                 "Tip Angle", "Counterbore Depth", "Counterbore "
                 "Diameter", "Countersink Diameter", "Countersink "
                 "Angle", "Modeled", "Class"):
        assert word in texts, word
    for gone in ("Type", "Thread form", "Tip angle", "Cbore Ø",
                 "Cbore depth", "Csink Ø", "Csink angle"):
        assert gone not in texts, gone
    # the page's bore order: Depth BEFORE Diameter (the born pair
    # was reversed), Countersink Diameter BEFORE Angle:
    assert texts.index("Counterbore Depth") < texts.index(
        "Counterbore Diameter")
    assert texts.index("Countersink Diameter") < texts.index(
        "Countersink Angle")
    assert texts.index("Depth") < texts.index("Tip Angle")


def test_the_row_hiding_survived_the_reorder(qapp):
    """The hide-tables are computed from rowCount AT BUILD TIME, so a
    reorder could have silently un-hid the wrong widgets: this gate
    walks the LABELS next to the widgets it expects visible."""
    dlg = _fresh()
    assert dlg.cb_depth.isHidden() and dlg.cb_dia.isHidden()
    dlg.type.setCurrentText("Counterbore")
    assert not dlg.cb_depth.isHidden() and not dlg.cb_dia.isHidden()
    assert dlg.cs_dia.isHidden()
    dlg.type.setCurrentText("Countersink")
    assert dlg.cb_depth.isHidden() and not dlg.cs_angle.isHidden()


# ---- the file law: values() keys, byte for byte ------------------------------------

def test_the_record_law_values_keys_never_moved(qapp):
    """R7's pin (through sits immediately before tip_angle) general-
    ised: the WHOLE dict is the era contract - labels are UI law,
    keys are file law, and every scripted answer from m31 onward
    already speaks it."""
    dlg = _fresh()
    assert list(dlg.values()) == ["type", "thread", "thread_size",
                                  "thread_class", "thread_mode",
                                  "drill", "depth", "through",
                                  "tip_angle", "cb_dia", "cb_depth",
                                  "cs_dia", "cs_angle"]


# ---- the door cites its pages -------------------------------------------------------

def test_the_dialog_quotes_its_pages_and_flags_its_defects(qapp):
    doc = " ".join(HoleDialog.__doc__.split()) if HoleDialog.__doc__ \
        else ""
    src = (Path(__file__).resolve().parent.parent / "tracer" / "ui" /
           "hole.py").read_text(encoding="utf-8")
    mod = " ".join(
        line.split("#", 1)[1] if line.lstrip().startswith("#") else line
        for line in src.splitlines())
    mod = " ".join(mod.split())
    for quote in ("Select At Point (Single Hole) or From Sketch "
                  "(Multiple Holes).",
                  "Select Distance, To, or All.",
                  "Select Simple, Counterbore, or Countersink.",
                  "Specifies the angle of the drill point for the "
                  "hole."):
        assert quote in mod, quote
    assert "threads a cosmetic or modeled" in mod        # H2 verbatim
    for flag in ("H2", "H3", "H5", "H6", "H8"):
        assert flag in mod or flag in doc, flag          # registered
    # the silence law, restated where it governs:
    assert "The page names NO default" in mod            # R7's stamp
