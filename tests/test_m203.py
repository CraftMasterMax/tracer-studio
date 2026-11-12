"""M201 R15 - the pattern ring wears the PAGES' words (naming pass).

[rectangular REFERENCE page, verbatim] the row prints "One direction"
sentence-case - the REFERENCE page's casing WINS over the how-to's
title-case print (banked adjudication), so every dialog mouth now
speaks "One direction" while the kernel records keep their lowercase
record voice ("one"/"symmetric") and no saved file moves an inch.
The tool's NAME is likewise the page's: the Create menu and the door
title wear "Rectangular pattern…"/"Rectangular Pattern" - "linear"
lives only in the CAM book - healing the house's own mouth-conflict
(ribbon tooltip already said Rectangular while the menu said Linear).

[CIRCULAR section, verbatim] the page's circular dialog carries
EXACTLY the Axis and Distribution rows; "Full: Distributes pattern
instances 360 degrees around the axis" spells the number IN WORDS,
so a Full pick speaks "over 360 degrees" - never the Angle row's
value (the row rides the conditional-row law: NOTICED and NEVER
WRITTEN under Full).  Partial and Symmetric are the page's two
angle-speakers and keep "over Ng°" byte for byte; the rung-era
"auto" derivation - OUR fourth choice - keeps its number too.
The linear rail finally READS its record: extent records say "over
the full extent" (the page's own phrase), spacing legacy keeps "at".

House words are STAMPED, not hidden: "Occurrences" (the page row is
"Quantity"), the lever's fourth circular choice "auto", and the
ENTIRE Geometric door (extension-gated, HOW-TO ONLY - no reference
page prints its rows) are declared OURS in the mouths that speak
them, and the declarations are pinned here.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                          # noqa: E402

from conftest import script_cmd                                     # noqa: E402
from tracer.core import document as docmod                          # noqa: E402
from tracer.ui import cmddialog                                     # noqa: E402
from tracer.ui.commands import REPEATABLE_LABELS                    # noqa: E402
from tracer.ui.mainwindow import MainWindow                         # noqa: E402
from tracer.ui.renderer import SceneRenderer                        # noqa: E402


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
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


@pytest.fixture(autouse=True)
def _clean_memory():
    yield
    for k in ("linear_pattern", "circular_pattern"):
        cmddialog._REMEMBERED.pop(k, None)


def _plate_hole(win):
    win.new_document()
    win.doc.add_plate("plate", 60, 10, 2)
    win.doc.add_cylinder("h", 1.5, 10, center=(30, 5), z=-4,
                         op="subtract")
    win.recompute()


def _capture_asks(win, monkeypatch, reply):
    calls = []

    def fake_ask(parent, title, fields, remember_key=None):
        calls.append((title, fields))
        return dict(reply)
    monkeypatch.setattr(cmddialog, "ask", fake_ask)
    return calls


# ---- the names the pages print ----------------------------------------------

def test_the_create_menu_wears_the_page_name(win):
    """Menu, REPEATABLE ledger and ribbon tooltip all speak RECT-
    ANGULAR now - the house's own mouth-conflict (tooltip said
    Rectangular, menu said Linear) is healed at every mouth, and no
    menu action in the window still says "Linear pattern"."""
    texts = []
    for act in win.menuBar().actions():
        m = act.menu()
        if m is None:
            continue
        texts.extend(a.text() for a in m.actions())
    assert "&Rectangular pattern…" in texts
    assert not any("Linear pattern" in t for t in texts)
    assert "Rectangular pattern…" in REPEATABLE_LABELS
    assert "Linear pattern…" not in REPEATABLE_LABELS


def test_the_door_title_and_direction_rows_wear_the_reference_voice(
        win, monkeypatch):
    """ONE dialog still, titled "Rectangular Pattern"; both Direction
    rows offer the REFERENCE page's casing - choices AND default -
    while every key stays where the files and the levers put it."""
    calls = _capture_asks(win, monkeypatch, {
        "src": "h", "dx": 10.0, "dy": 0.0, "dz": 0.0, "count": 3,
        "dist": "Spacing", "dir": "One direction",
        "count2": 1, "dx2": 0.0, "dy2": 0.0, "dz2": 0.0,
        "dist2": "Spacing", "dir2": "One direction"})
    _plate_hole(win)
    win.action_linear_pattern()
    assert len(calls) == 1
    title, fields = calls[0]
    assert title == "Rectangular Pattern"
    by_key = {f["key"]: f for f in fields}
    for k in ("dir", "dir2"):
        assert by_key[k]["choices"] == ["One direction", "Symmetric"]
        assert by_key[k]["default"] == "One direction"
    f = win.doc.features[-1]
    assert (f.direction, f.direction2) == ("one", "one")   # record voice


def test_the_old_record_voice_lands_untouched(win, monkeypatch):
    """A file/lever record keeps its lowercase voice: the door maps
    "Symmetric" to the record word and everything else to "one" -
    the casing pass moves NOTHING below the dialog mouth."""
    script_cmd(monkeypatch, {
        "src": "h", "dx": 10.0, "dy": 0.0, "dz": 0.0, "count": 3,
        "dist": "Spacing", "dir": "One direction",
        "count2": 1, "dx2": 0.0, "dy2": 3.0, "dz2": 0.0,
        "dist2": "Spacing", "dir2": "Symmetric"})
    _plate_hole(win)
    win.action_linear_pattern()
    f = win.doc.features[-1]
    assert (f.direction, f.direction2) == ("one", "symmetric")
    assert win.status.currentMessage() == \
        "Patterned h: 3x at (10, 0, 0) mm"          # byte-rung-era


# ---- circular: the page's spelled 360, and the angle-speakers ----------------

def test_full_speaks_the_pages_spelled_words(win, monkeypatch):
    """Typed 45, stored 360, spoken IN WORDS - the page's Full row
    spells "360 degrees", and the Angle row was never asked of it
    (NOTICED and NEVER WRITTEN under Full; one dialog, as always)."""
    calls = _capture_asks(win, monkeypatch, {
        "src": "h", "axis": "+Z (through center)", "cx": 30.0,
        "cy": 5.0, "dist": "Full", "ang": 45.0, "count": 6})
    _plate_hole(win)
    win.action_circular_pattern()
    assert len(calls) == 1 and calls[0][0] == "Circular Pattern"
    f = win.doc.features[-1]
    assert f.distribution == "full" and f.angle == 360.0    # typed 45 lost
    assert win.status.currentMessage() == \
        "Patterned h: 6x over 360 degrees about (30, 5)"


def test_partial_and_symmetric_keep_their_number(win, monkeypatch):
    """The page's TWO angle-speakers ("enter an exact value") keep
    the rung-era degree mouth byte for byte; the symmetric tail
    rides unchanged."""
    script_cmd(monkeypatch, {"src": "h", "axis": "+Z (through center)",
                             "cx": 30.0, "cy": 5.0, "dist": "Partial",
                             "ang": 90.0, "count": 4})
    _plate_hole(win)
    win.action_circular_pattern()
    assert win.status.currentMessage() == \
        "Patterned h: 4x over 90° about (30, 5)"
    script_cmd(monkeypatch, {"src": "h", "axis": "+Z (through center)",
                             "cx": 30.0, "cy": 5.0, "dist": "Symmetric",
                             "ang": 120.0, "count": 3})
    win.new_document()
    win.doc.add_plate("plate", 60, 10, 2)
    win.doc.add_cylinder("h", 1.5, 10, center=(30, 5), z=-4,
                         op="subtract")
    win.recompute()
    win.action_circular_pattern()
    assert win.status.currentMessage() == \
        "Patterned h: 3x over 120° about (30, 5), symmetrically " \
        "from the source"


# ---- the rail finally READS its record ---------------------------------------

def test_the_linear_rail_reads_distribution(win, monkeypatch):
    """An Extent record spread over the vector as the FULL EXTENT
    and the rail said "at" - a lie by omission, healed in the
    page's own phrase; the spacing legacy voice stays byte for byte."""
    script_cmd(monkeypatch, {
        "src": "h", "dx": 20.0, "dy": 0.0, "dz": 0.0, "count": 3,
        "dist": "Extent", "dir": "One direction",
        "count2": 1, "dx2": 0.0, "dy2": 0.0, "dz2": 0.0,
        "dist2": "Spacing", "dir2": "One direction"})
    _plate_hole(win)
    win.action_linear_pattern()
    f = win.doc.features[-1]
    win.rail.props.show_feature(f)
    txt = win.rail.props._body.text()
    assert "pattern: 3x over the full extent (20, 0, 0) mm" in txt
    assert "pattern: 3x at" not in txt
    f.distribution = "spacing"
    win.rail.props.show_feature(f)
    assert "pattern: 3x at (20, 0, 0) mm" in \
        win.rail.props._body.text()                 # byte-legacy


def test_the_circular_rail_spells_full_and_keeps_auto(win, monkeypatch):
    """The rail splits the same way the status does: a FULL record
    wears the spelled 360 degrees; the rung-era "auto" derivation -
    our fourth choice - keeps its number byte for byte."""
    script_cmd(monkeypatch, {"src": "h", "axis": "+Z (through center)",
                             "cx": 30.0, "cy": 5.0, "dist": "Full",
                             "ang": 360.0, "count": 6})
    _plate_hole(win)
    win.action_circular_pattern()
    f = win.doc.features[-1]
    win.rail.props.show_feature(f)
    assert "pattern: 6x over 360 degrees about (30, 5)" in \
        win.rail.props._body.text()
    f.distribution = "auto"
    f.angle = 60.0
    win.rail.props.show_feature(f)
    assert "pattern: 6x over 60° about (30, 5)" in \
        win.rail.props._body.text()                 # byte-legacy


# ---- the declarations, pinned at their mouths ----------------------------------

def test_the_house_words_are_declared_not_hidden():
    """Every word the pages do not print is STAMPED where it speaks:
    Occurrences (the page row is Quantity), the Geometric door
    WHOLESALE (extension-gated, how-to only - no reference page
    exists), and the kernel carries the casing adjudication."""
    lin = " ".join(MainWindow.action_linear_pattern.__doc__.split())
    assert '"Rectangular Pattern"' in lin
    assert '"Occurrences"/"Occurrences 2" - OURS' in lin
    assert '"Quantity"' in lin
    geo = " ".join(MainWindow.action_geometric_pattern.__doc__.split())
    assert "DECLARED HOUSE-NAMED WHOLESALE" in geo
    assert "is a HOW-TO - no reference page prints its row words" in geo
    kern = " ".join(docmod.LinearPatternFeature.__doc__.split())
    assert ("the rectangular REFERENCE page's sentence-case "
            "\"direction\" wins") in kern
    law = " ".join(docmod.linear_offsets.__doc__.split())
    assert "One direction | Symmetric, the REFERENCE page's casing" \
        in law
