"""M201 R21 - the Coil door wears the reference page's rows.

[SLD-REF-COIL, verbatim] the printed row order is Type, ROTATION,
Radius, Revolutions, Height, Pitch, Angle, Section, Section Position,
Section Size, Operation.  ROTATION: "Click to switch the rotation of
the coil from clockwise to counterclockwise, or vice versa."  The row
was born "Hand" (M127); it now wears the page's word while the RECORD
keeps its hand key - display word over record word, the Joint-Type
contract.  The page prints NO choice words and NO view direction for
the row, so {Right | Left} are OURS, stamped.  DEFECT, flagged not
cloned: the how-to glosses the SAME word as "rotate the coil 90
degrees around the Y axis" - an orientation twist vs the reference's
flip.

SECTION POSITION prints {Inside | On Center | Outside}; only ON
CENTER bakes (coil_solid rides the section's CENTRE on the helix -
what the diameter measures); a scripted Inside refuses BEFORE the
capture.  ANGLE ("Specify the taper angle...") is unoffered - a
constant-radius sweep cannot taper.  TRIANGULAR sections unoffered.
OPERATION prints FIVE; the door offers R17's trio {Join | Cut |
Intersect} - the SAME generic op dispatch every feature rides, so the
FILE schema does not move an inch; rest Join is a STAMP ("default"
counts zero on both pages) and today's exact behavior.  New Body is
the browser's separate tool; New Component is gated by the page's own
"(Hybrid Design type only)".
"""
import contextlib

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                                # noqa

from conftest import script_cmd                                           # noqa
from tracer.core.document import PrimitiveFeature                         # noqa
from tracer.ui import cmddialog                                           # noqa
from tracer.ui.mainwindow import MainWindow                               # noqa
from tracer.ui.renderer import SceneRenderer                              # noqa


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


class _Stop(Exception):
    pass


def _capture_fields(monkeypatch):
    calls = []

    def fake(parent, title, fields, remember_key=None):
        calls.append(fields)
        raise _Stop
    monkeypatch.setattr(cmddialog, "ask", fake)
    return calls


def _rows(win, monkeypatch):
    calls = _capture_fields(monkeypatch)
    with contextlib.suppress(_Stop):
        win.action_coil()
    return {f["key"]: f for f in calls[0]}


# the minimum the door REQUIRES to build (everything else rides .get
# rests - R5's remembered-dict coin):
_MIN = dict(axis="Z", base="0,0,0", diam=10.0, turns=4.0, pitch=2.0,
            height=0.0, hand="Right", section="Circular", size=1.5)


def _box(win):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 20, "dy": 20, "dz": 4}))
    win.recompute()
    return win.doc


# ---- the rows the page prints -------------------------------------------------

def test_rotation_is_the_pages_row_two_word(win, monkeypatch):
    """"Click to switch the rotation of the coil from clockwise to
    counterclockwise, or vice versa." - row TWO right behind Type; the
    RECORD keeps its hand key (display word over record word)."""
    rows = _rows(win, monkeypatch)
    assert list(rows)[:2] == ["type", "hand"]
    assert rows["hand"]["label"] == "Rotation"
    assert rows["hand"]["default"] == "Right"
    assert list(rows["hand"]["choices"]) == ["Right", "Left"]
    assert not any(f["label"] == "Hand" for f in rows.values())


def test_section_position_offers_only_the_member_that_bakes(win,
                                                            monkeypatch):
    """{Inside | On Center | Outside} is the page's trio; the kernel
    rides the section's CENTRE on the helix, so only On Center is
    offered - the Joint-Type precedent, and the rest IS that member."""
    rows = _rows(win, monkeypatch)
    sp = rows["secpos"]
    assert sp["label"] == "Section Position"
    assert list(sp["choices"]) == ["On Center"]
    assert sp["default"] == "On Center"
    for absent in ("Inside", "Outside"):
        assert absent not in sp["choices"]
    # and it rides between Section and Section Size, the page's place
    keys = list(rows)
    assert keys.index("section") < keys.index("secpos") < \
        keys.index("size")


def test_operation_row_is_the_printed_trio_resting_at_the_stamp(
        win, monkeypatch):
    """Five words print on the page; three bake.  Rest Join is a
    STAMP - "default" counts ZERO on both coil pages - and exactly
    what the door has always baked."""
    rows = _rows(win, monkeypatch)
    op = rows["op"]
    assert op["label"] == "Operation"
    assert list(op["choices"]) == ["Join", "Cut", "Intersect"]
    assert op["default"] == "Join"
    assert "New Body" not in op["choices"]      # the browser's tool
    assert "New Component" not in op["choices"]  # "(Hybrid Design...)"


def test_the_section_size_row_wears_the_pages_capitalization(
        win, monkeypatch):
    """The page's h2 says "Section Size" and its gloss matches our
    law to the decimal: "The size of the profile is determined by a
    circumscribed sketch circle." """
    rows = _rows(win, monkeypatch)
    assert rows["size"]["label"] == "Section Size"


# ---- the guards, from the outside ------------------------------------------------

def test_a_scripted_off_center_refuses_before_the_capture(win, monkeypatch):
    d = _box(win)
    n = len(d.features)
    script_cmd(monkeypatch, dict(_MIN, secpos="Inside"))
    depth = len(win._undo)
    win.action_coil()
    assert len(d.features) == n, "an Inside section baked anyway"
    assert len(win._undo) == depth, "the refused capture paid an undo step"
    msg = win.status.currentMessage()
    assert "Section Position 'Inside'" in msg and "centers it" in msg, msg


def test_a_scripted_junk_operation_refuses_before_the_capture(
        win, monkeypatch):
    d = _box(win)
    n = len(d.features)
    script_cmd(monkeypatch, dict(_MIN, op="New Component"))
    depth = len(win._undo)
    win.action_coil()
    assert len(d.features) == n
    assert len(win._undo) == depth
    assert "the operation is 'Join', 'Cut' or 'Intersect'" in \
        win.status.currentMessage()


def test_a_scripted_wrong_rotation_refuses_before_the_capture(
        win, monkeypatch):
    d = _box(win)
    n = len(d.features)
    script_cmd(monkeypatch, dict(_MIN, hand="Counterclockwise"))
    win.action_coil()
    assert len(d.features) == n
    assert "the Rotation the kernel flips" in win.status.currentMessage()


# ---- the booleans really bite ------------------------------------------------------

def test_the_three_operations_land_three_different_bodies(win):
    """The trio is not theatre: Join grows the body, Cut carves the
    helix out of it, Intersect keeps ONLY the coil inside it - all on
    the ONE generic op dispatch, so the file schema never moved."""
    vols = {}
    for word, key in (("Join", "join"), ("Cut", "cut"),
                      ("Intersect", "inter")):
        d = _box(win)
        box_v = d.result.volume
        script = dict(_MIN, op=word, base="0,0,-2")
        from tracer.ui import cmddialog as cd
        _orig = cd.ask
        cd.ask = lambda parent, title, fields, remember_key=None, s=script: \
            dict(s)
        try:
            win.action_coil()
        finally:
            cd.ask = _orig
        assert d.failed_feature is None, (word, d.failed_feature)
        vols[key] = (box_v, d.result.volume)
    assert vols["join"][1] > vols["join"][0]          # grows
    assert vols["cut"][1] < vols["cut"][0]            # carves
    assert vols["inter"][1] < vols["cut"][1]          # only the groove
    assert vols["inter"][1] > 0.0                     # and something


def test_the_rest_lands_todays_behavior(win, monkeypatch):
    """A remembered dict born before this rung speaks the old keys -
    no op, no secpos rows exist in it.  The rests answer: Join,
    On Center - the classic record, zero rewrites (R5's coin)."""
    d = _box(win)
    legacy = dict(_MIN)
    legacy.pop("height")
    script_cmd(monkeypatch, legacy)
    win.action_coil()
    f = [x for x in d.features if type(x).__name__ == "CoilFeature"][0]
    assert f.op == "union"                      # the Join stamp
    assert f.hand == "right"
    assert d.failed_feature is None


def test_a_cut_coil_is_an_old_file_fact(win):
    """op has been a SERIALIZED feature key since before coils
    existed - the Cut lands on the existing file voice; a file whose
    coil says union still loads and still bakes the old answer."""
    d = _box(win)
    from tracer.ui import cmddialog as cd
    script = dict(_MIN, op="Cut", base="0,0,-2")
    _orig = cd.ask
    cd.ask = lambda *a, **k: dict(script)
    try:
        win.action_coil()
    finally:
        cd.ask = _orig
    payload = d.to_dict()
    coil = next(fd for fd in payload["features"]
                if fd["type"] == "CoilFeature")
    assert coil["op"] == "subtract"
    # pre-R21 file voice: the SAME payload speaks union and reloads
    coil["op"] = "union"
    d2 = type(d).from_dict(payload)
    d2.recompute()
    assert d2.failed_feature is None
    assert d2.result.volume > d.result.volume   # join vs cut differs


def test_the_door_quotes_its_law():
    doc = " ".join(MainWindow.action_coil.__doc__.split())
    assert "Click to switch the rotation of the coil from clockwise " \
           "to counterclockwise, or vice versa." in doc
    assert "rotate the coil 90 degrees around the Y axis" in doc  # DEFECT
    assert "Specify the taper angle for all coil types except " \
           "spiral" in doc                                  # Angle unoffered
    assert "Triangular (External)" in doc and "Triangular (Internal)" \
        in doc                                              # unoffered
    assert "(Hybrid Design type only)" in doc               # page's gate
    assert "The size of the profile is determined by a circumscribed " \
           "sketch circle." in doc
    assert "STAMP" in doc                                   # Join's rest
