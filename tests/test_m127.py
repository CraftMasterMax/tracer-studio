"""M127 — coil-v1: the helical ridge, honestly lofts.

The coil is the first feature the mesh kernel builds that curves in
three dimensions on purpose: a closed section riding a helix, lofted
through dense ring stations. Pappus' centroid theorem is the analytic
judge (volume = section area x helix length, chord/polygon losses
bounded by tolerance), hand must mirror exactly, and the pitch-vs-
section refusal is the difference between a thread and a screw-shaped
blob. Axes resolve through the M125 datum store, so a coil can spin
about a tilted work axis, and datum_references keeps it honest."""
import math

import numpy as np
import pytest

from tracer.core import params
from tracer.core.coil import coil_solid
from tracer.core.document import (CoilFeature, Document, PrimitiveFeature)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    w.new_document()
    qapp.processEvents()
    w._discard_guard = lambda: True
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _helix_len(r, p, t):
    return math.hypot(2.0 * math.pi * r, p) * t


# ---- core: analytic truth --------------------------------------------------

def test_circular_coil_matches_pappus():
    v = coil_solid((0, 0, 0), (0, 0, 1), 6.0, 4.0, 4.0, "circular", 3.0)
    exp = math.pi * 1.5 ** 2 * _helix_len(6.0, 4.0, 4.0)
    assert v.volume == pytest.approx(exp, rel=0.02)   # chord+polygon loss


def test_square_coil_matches_pappus():
    v = coil_solid((0, 0, 0), (0, 0, 1), 6.0, 4.0, 4.0, "square", 3.0)
    exp = (3.0 ** 2 / 2.0) * _helix_len(6.0, 4.0, 4.0)
    assert v.volume == pytest.approx(exp, rel=0.03)


def test_left_hand_mirrors_right_exact_enough():
    kw = dict(section="circular", size=3.0)
    r = coil_solid((0, 0, 0), (0, 0, 1), 6.0, 4.0, 4.0, **kw)
    l = coil_solid((0, 0, 0), (0, 0, 1), 6.0, 4.0, 4.0, hand="left", **kw)
    assert l.volume == pytest.approx(r.volume, rel=2e-3)
    assert np.allclose(np.asarray(r.bounding_box)[:, 2],
                       np.asarray(l.bounding_box)[:, 2], atol=0.05)


def test_coil_rides_a_tilted_named_axis_frame():
    up = coil_solid((0, 0, 0), (0, 0, 1), 6.0, 4.0, 3.0, "circular", 2.0)
    til = coil_solid((1, 2, 3), (1, 1, 2), 6.0, 4.0, 3.0, "circular", 2.0)
    assert til.volume == pytest.approx(up.volume, rel=2e-3)
    bb = np.asarray(til.bounding_box, float)
    assert bb[0].min() < 0.9                     # genuinely swung off-Z


# ---- core: honest refusals ---------------------------------------------------

def test_coil_refusals_all_six():
    with pytest.raises(params.ParamError):        # section swallows pitch
        coil_solid((0, 0, 0), (0, 0, 1), 6, 2.0, 3, "circular", 5.0)
    with pytest.raises(params.ParamError):
        coil_solid((0, 0, 0), (0, 0, 1), 0.0, 2.0, 3, "circular", 1.0)
    with pytest.raises(params.ParamError):
        coil_solid((0, 0, 0), (0, 0, 1), 6, 0.0, 3, "circular", 1.0)
    with pytest.raises(params.ParamError):
        coil_solid((0, 0, 0), (0, 0, 1), 6, 2.0, 0.2, "circular", 1.0)
    with pytest.raises(params.ParamError):
        coil_solid((0, 0, 0), (0, 0, 1), 6, 2.0, 3, "hexagonal", 1.0)
    with pytest.raises(params.ParamError):
        coil_solid((0, 0, 0), (0, 0, 1), 6, 2.0, 3, "circular", 1.0,
                   hand="sideways")


# ---- document wiring ---------------------------------------------------------

def _bolt(d):
    d.add(PrimitiveFeature(name="rod", kind="cylinder",
                           dims={"radius": 2.2, "height": 12},
                           placement=(0, 0, 0)))
    d.recompute()
    return d


def test_bolt_union_grows_and_binds_named_axis():
    d = _bolt(Document())
    core = d.result.volume
    d.add_axis_2pt((0, 0, 0), (0, 0, 12))
    d.add_coil("thread", axis="Axis 1", diameter=4.4, pitch=1.25,
               turns=6, size=1.1)
    d.recompute()
    assert d.result.volume > core + 10.0
    bb = np.asarray(d.result.bounding_box, float)
    assert abs(bb[1][0] - 2.75) < 0.05           # ridge stands proud
    assert d.datum_references("Axis 1") == ["thread"]


def test_missing_axis_is_a_param_error():
    d = _bolt(Document())
    d.add_coil("ghost", axis="Axis 42")
    with pytest.raises(params.ParamError):
        d.recompute()


def test_io_roundtrip_keeps_every_coil_field():
    import tempfile
    from pathlib import Path
    from tracer.core.io import save_document, load_document
    d = _bolt(Document())
    d.add_coil("spring", axis="Z", base=(1, 2, 3), diameter=9.0,
               pitch=2.5, turns=4.5, hand="left", section="square",
               size=1.8)
    with tempfile.TemporaryDirectory() as t:
        pth = Path(t) / "k.tracer"
        save_document(d, pth)
        r = load_document(pth)
    c = next(f for f in r.features if isinstance(f, CoilFeature))
    assert c.axis == "Z" and c.base == (1.0, 2.0, 3.0)
    assert (c.diameter, c.pitch, c.turns, c.hand, c.section, c.size) == \
        (9.0, 2.5, 4.5, "left", "square", 1.8)
    assert c.height == pytest.approx(11.25)
    r.recompute()
    assert r.result.volume == pytest.approx(d.result.volume, abs=1e-6)


# ---- UI -----------------------------------------------------------------------

def _dialog_answers(monkeypatch, values):
    from tracer.ui import cmddialog
    monkeypatch.setattr(cmddialog, "ask",
                        lambda parent, title, fields, remember_key=None:
                        dict(values))


def test_coil_dialog_builds_announced_geometry(win, monkeypatch):
    _dialog_answers(monkeypatch, {"axis": "Z", "base": "0,0,0",
                                  "diam": 10.0, "pitch": 3.0,
                                  "turns": 3.0, "hand": "Left",
                                  "section": "Square", "size": 2.0})
    win.action_coil()
    assert win.status.currentMessage().startswith("Coil 3x3")
    assert "left-handed" in win.status.currentMessage()
    c = win.doc.features[-1]
    assert isinstance(c, CoilFeature) and c.hand == "left"
    assert c.section == "square" and c.height == 9.0


def test_coil_dialog_garbage_base_refused_loudly(win, monkeypatch):
    _dialog_answers(monkeypatch, {"axis": "Z", "base": "origin",
                                  "diam": 10.0, "pitch": 3.0,
                                  "turns": 3.0, "hand": "Right",
                                  "section": "Circular", "size": 2.0})
    win.action_coil()                            # must not raise
    assert win.doc.features == []
    assert "refused" in win.status.currentMessage().lower()


def test_coil_dialog_overlap_fails_with_badge_not_crash(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda parent, title, text, *a, **k: QMessageBox.Ok))
    _dialog_answers(monkeypatch, {"axis": "Z", "base": "0,0,0",
                                  "diam": 10.0, "pitch": 1.0,
                                  "turns": 3.0, "hand": "Right",
                                  "section": "Circular", "size": 4.0})
    win.action_coil()                            # section > pitch
    assert getattr(win.doc, "failed_feature", None) is not None


def test_change_parameters_reteams_the_coil(win, monkeypatch):
    win.doc.add_coil("spring", axis="Z", diameter=10.0, pitch=2.0,
                     turns=3.0, size=1.5)
    win.recompute()
    before = win.doc.result.volume
    _dialog_answers(monkeypatch, {"diam": 10.0, "pitch": 3.0,
                                  "turns": 4.0, "size": 2.0})
    win.action_change_params(win.doc.features[-1])
    c = win.doc.features[-1]
    assert (c.pitch, c.turns, c.size) == (3.0, 4.0, 2.0)
    assert win.doc.result.volume > before


# ---- M201 R12: the Type two-of-three rung --------------------------------
# [SLD-REF-COIL, verbatim] "Type: Select the type of coil to create. |
# Revolution And Height: Creates a coil with a specific number of
# revolutions and a specific height. | Revolution And Pitch: ... |
# Height And Pitch: ... | Spiral: ... using the same settings as the
# Revolution And Pitch coil type, without an Angle value." THE
# TWO-OF-THREE CONTRACT: each mode names which TWO of {Revolutions,
# Height, Pitch} the door is asked for; the third stands derived. Our
# kernel keeps the classic pair (turns, pitch) with height = turns x
# pitch, so the modes are SOLVER WORDS - arithmetic at the door, the
# fold never learns a new number. SPIRAL IS NOT OFFERED (a winding
# radius is not what coil_solid sweeps; a door may not promise what
# cannot bake) and is refused by name. "default" counts ZERO on both
# pages: every rest here is the house's, named as one.

def _full(**over):
    base = {"type": "Revolution And Pitch", "axis": "Z",
            "base": "0,0,0", "diam": 10.0, "turns": 6.0,
            "height": 0.0, "pitch": 1.5, "hand": "Right",
            "section": "Circular", "size": 1.0}
    base.update(over)
    return base


def test_the_door_offers_three_of_the_pages_four_words(win, monkeypatch):
    """Type is row ONE (page order), spelled with the reference's
    capital "And", resting on the mode whose pair the record already
    keeps - "Revolution And Pitch" NAMED AS A HOUSE FACT (the pages
    print no default). Spiral is the page's fourth word and the door
    does not offer it: what cannot bake is not promised. The
    Revolutions row is a COUNT and wears NO unit (the UNIT-SUFFIX LAW
    R11's film caught: ask() defaults doubles to " mm"; a ratio or a
    count may not). A legacy remembered dict (no type, no height -
    every remembered coil born before today) still lands the classic
    pair - zero rewrites, R5's coin."""
    seen = []

    def spy(parent, title, fields, remember_key=None):
        seen.append({f["key"]: f for f in fields})
        return _full(turns=4.0, pitch=3.0)
    from tracer.ui import cmddialog
    monkeypatch.setattr(cmddialog, "ask", spy)
    win.action_coil()
    rows = seen[0]
    # M201 R21 heal: the door wears the REFERENCE page's row order -
    # Type, ROTATION (row TWO, the old "Hand" renamed), the Helix
    # numbers, the house Axis rows, Section, SECTION POSITION,
    # Section Size, OPERATION.
    assert list(rows) == ["type", "hand", "diam", "turns", "height",
                          "pitch", "axis", "base", "section",
                          "secpos", "size", "op"]
    assert rows["type"]["kind"] == "combo"
    assert list(rows["type"]["choices"]) == ["Revolution And Height",
                                             "Revolution And Pitch",
                                             "Height And Pitch"]   # no Spiral
    assert rows["type"]["default"] == "Revolution And Pitch"
    assert "Revolutions" == rows["turns"]["label"]   # the page's word
    assert rows["turns"]["suffix"] == ""             # a count, unit-free
    c = win.doc.features[-1]
    assert (c.turns, c.pitch, c.height) == (4.0, 3.0, 12.0)
    assert c.coil_type == "Revolution And Pitch"

    _dialog_answers(monkeypatch, {"axis": "Z", "base": "0,0,0",
                                  "diam": 10.0, "pitch": 3.0,
                                  "turns": 3.0, "hand": "Left",
                                  "section": "Square", "size": 2.0})
    win.action_coil()
    legacy = win.doc.features[-1]
    assert legacy.coil_type == "Revolution And Pitch"   # the rest word
    assert legacy.height == 9.0


def test_the_solver_divides_height_both_ways(win, monkeypatch):
    """The page's contract MEASURED: "Revolution And Height" with 4
    revolutions and 12 mm of height DIVIDES the pitch to 3 (and the
    record's own height stands 12 - the pair multiplies back to the
    typed height, exactly); "Height And Pitch" with 12 over 3 DIVIDES
    the revolutions to 4. And under the classic word the height row
    is INERT - typed 50 changes nothing: the record is its pair and
    the pair rules (R2's stored-and-inert law, here not even stored:
    height is a property, not a field)."""
    _dialog_answers(monkeypatch, _full(type="Revolution And Height",
                                       turns=4.0, height=12.0,
                                       pitch=99.0))
    win.action_coil()
    c = win.doc.features[-1]
    assert c.pitch == 3.0 and c.height == 12.0
    assert c.name == "Coil 4x3" and "3 mm pitch = 12 mm tall" in \
        win.status.currentMessage()

    _dialog_answers(monkeypatch, _full(type="Height And Pitch",
                                       height=12.0, pitch=3.0,
                                       turns=99.0))
    win.action_coil()
    c = win.doc.features[-1]
    assert c.turns == 4.0 and c.height == 12.0

    _dialog_answers(monkeypatch, _full(height=50.0, turns=6.0,
                                       pitch=1.5))
    win.action_coil()
    c = win.doc.features[-1]
    assert c.height == 9.0                     # the pair, not the row


def test_spiral_and_the_zero_divide_are_refused_before_the_capture(
        win, monkeypatch):
    """Three refusals, NOTHING captured (no feature, no undo step):
    the page's fourth word "Spiral" - the door cannot bake it, so a
    scripted Spiral is refused BY NAME with the three it does offer;
    a word the page never prints ("Tapered") the same sentence; and
    "Revolution And Height" with a ZERO height would divide to a
    pitch that cannot stand - refused before the capture, not after
    the badge. The kernel's OWN guard closes the last mouth: a
    hand-written file's fourth word raises through the real fold."""
    n0, u0 = len(win.doc.features), len(win._undo)
    for word in ("Spiral", "Tapered"):
        _dialog_answers(monkeypatch, _full(type=word))
        win.action_coil()
        msg = win.status.currentMessage()
        assert msg == ("Coil refused: the type is 'Revolution And "
                       "Height', 'Revolution And Pitch' or "
                       "'Height And Pitch', not " + repr(word))
    assert len(win.doc.features) == n0 and len(win._undo) == u0

    _dialog_answers(monkeypatch, _full(type="Revolution And Height",
                                       turns=4.0, height=0.0))
    win.action_coil()
    assert "positive revolutions and height" in \
        win.status.currentMessage()
    assert len(win.doc.features) == n0

    d = Document("g")
    d.add(CoilFeature(name="C", coil_type="Spiral"))
    with pytest.raises(ValueError,
                       match="the coil type is 'Revolution And "
                             "Height', 'Revolution And Pitch' or "
                             "'Height And Pitch', not 'Spiral'"):
        d.recompute()


def test_the_word_rides_the_file_and_old_files_keep_theirs():
    """The Type word is a REAL FILE WORD (written beside its numbers,
    round-trips to the last character) - and a coil file born before
    today, which never speaks it, replays on the HOUSE rest with its
    geometry untouched (the .get pair, R5's coin: zero rewrites; the
    numbers such a file carries ARE the rest mode's pair)."""
    import json
    d = Document("f")
    d.add_coil("spring", diameter=10.0, pitch=3.0, turns=4.0,
               coil_type="Height And Pitch")
    v = d.recompute().volume
    raw = json.loads(json.dumps(d.to_dict()))
    fd = [x for x in raw["features"] if x["type"] == "CoilFeature"][0]
    assert fd["coil_type"] == "Height And Pitch"
    back = Document.from_dict(raw)
    assert back.features[0].coil_type == "Height And Pitch"
    assert back.recompute().volume == v        # the same float
    del fd["coil_type"]
    old = Document.from_dict(raw)
    assert old.features[0].coil_type == "Revolution And Pitch"
    assert old.recompute().volume == v         # inert: same helix


def test_the_rail_speaks_the_helix_and_the_word_only_when_moved(win):
    """The coil record finally speaks its OWN arithmetic on the rail
    - revolutions x pitch = tall, the two-of-three truth in one line
    (the generic op header is HONEST here: a coil's op really rides
    the fold, unlike the draft's unused word R10's fix named). The
    TYPE line joins only OFF the house rest, and a word the solver
    moved stays named: what the door divided for you is the one word
    the record owes you."""
    c = win.doc.add_coil("spring", diameter=10.0, pitch=3.0, turns=4.0)
    win.recompute()
    win.rail.props.show_feature(c)
    t = win.rail.props._body.text()
    assert "helix: 4 x 3 mm = 12 mm tall" in t
    assert "type:" not in t                     # the rest stays unsaid
    c.coil_type = "Height And Pitch"
    win.recompute()
    win.rail.props.show_feature(c)
    t = win.rail.props._body.text()
    assert "type: Height And Pitch" in t
