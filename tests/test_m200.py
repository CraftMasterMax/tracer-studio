"""M200: the linear pattern's own Distribution and Direction.

[SLD-REF-PATTERN / GUID-9622573F, verbatim] "Distribution: Extent -
Distributes pattern instances evenly along the FULL EXTENT of the
distance value that you specify | Spacing - ...spaced at the distance
value" and "Direction: One Direction - ...in one direction from the
source | Symmetric - ...symmetrically in two directions FROM THE
SOURCE OBJECT along this axis".  M201 R15 [rectangular REFERENCE
page]: that page prints the row sentence-case - "One direction" -
and the REFERENCE page's casing WINS the dialog voice (the title-
case quote above stays the SLD page's own print, verbatim).

Rung one cuts the two typed rows. The house's rung-era voice (count
INCLUDING the source, offsets k x vector) is EXACTLY the page's
Spacing + One direction, so that route lands BIT-IDENTICAL and old
files replay untouched. Extent re-reads the vector as the full
end-to-end extent - the page's own "the meaning flips with the
Distribution row". Symmetric centers the count ON the source: an ODD
count is law-derivable (the source is an instance AND the middle);
an even one has no middle instance and the page words no rule - the
kernel REFUSES with the cure rather than inventing one.

Unpromised, by the pages' own words: Suppression (canvas checkboxes
over instances - no typed equivalent), Compute Type (feature-face
BRep), picked edge/cylindrical Axes, second-edge skew.

Rung two took the circular sibling's Distribution (Full | Partial |
Symmetric - "around the axis" instead of "along it"), rung three the
pattern-on-path's Orientation ("Identical: Orients all pattern
instances to match the source object" | "Path Direction: Orients each
pattern instance relative to its position along the path"), and rung
four the rectangular tool's SECOND DIRECTION: the vendor has one tool
whose rows repeat per axis, and the how-to words the one-direction
case as "set the Quantity value for Axis 2 to 1" - so the second axis
is a count row defaulting to 1, and at that value the rung-era list
comes back untouched.
"""
import json
import math

import numpy as np
import pytest

from tracer.core.document import (CircularPatternFeature,
                                  Document, LinearPatternFeature,
                                  PathPatternFeature, PrimitiveFeature,
                                  circular_rotations, linear_offsets)
from tracer.core.geometry import Solid
from tracer.ui import cmddialog


@pytest.fixture()
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
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
    r.close()


V = (10.0, 0.0, 0.0)


# ---- the placement law ------------------------------------------------------

def test_spacing_one_is_the_ladder_bit_unchanged():
    """The legacy voice IS the page's Spacing + One direction: the
    count includes the source (k=0) and the step is the vector.
    Measured BIT-IDENTICAL to the rung-era arithmetic (the exact
    multiplication k x v), the n<1 guard lands a single source copy,
    and Extent re-reads the SAME vector as the full end-to-end
    extent: 0/5/10 for v=10, n=3 - ends exactly the typed distance
    apart, "evenly along the full extent" in the page's own words."""
    assert linear_offsets(V, 3) == [tuple(x * k for x in V)
                                    for k in range(3)]
    assert linear_offsets(V, 0) == [(0.0, 0.0, 0.0)]      # legacy guard
    ext = linear_offsets(V, 3, "extent")
    assert ext == [(0.0, 0.0, 0.0), (5.0, 0.0, 0.0), (10.0, 0.0, 0.0)]
    assert ext[-1] == tuple(V)                  # ends exactly "10" apart
    assert linear_offsets(V, 1, "extent") == [(0.0, 0.0, 0.0)]


def test_symmetric_holds_the_source_in_the_middle():
    """"Symmetrically in TWO DIRECTIONS FROM THE SOURCE OBJECT": the
    source IS an instance and holds the middle.  Spacing n=3 stands
    -10/0/+10 (one distance each way); Extent n=3 stands -5/0/+5 -
    the ends are STILL the full extent apart, the middle is the
    source; n=5 under extent spans -5..+5 (step 2.5), symmetric in
    every component of an oblique vector too."""
    assert linear_offsets(V, 3, "spacing", "symmetric") == \
        [(-10.0, -0.0, -0.0), (0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]
    es = linear_offsets(V, 3, "extent", "symmetric")
    assert es == [(-5.0, -0.0, -0.0), (0.0, 0.0, 0.0), (5.0, 0.0, 0.0)]
    e5 = linear_offsets(V, 5, "extent", "symmetric")
    assert (e5[0], e5[-1]) == ((-5.0, -0.0, -0.0), (5.0, 0.0, 0.0))
    ob = linear_offsets((6.0, 4.0, 0.0), 3, "spacing", "symmetric")
    assert ob == [(-6.0, -4.0, -0.0), (0.0, 0.0, 0.0), (6.0, 4.0, 0.0)]


def test_the_even_middle_and_the_wrong_words_refuse():
    """The page words no even-count symmetric rule - the source is
    the middle and an even count HAS no middle instance, so the
    kernel refuses with the cure in its words ("an odd count has
    one, an even one does not"), both distributions alike; and the
    enums refuse whatever is not the page's voice ("'spacing' or
    'extent', not 'spread').  A refusal is a refusal: nothing
    lands."""
    with pytest.raises(ValueError, match="odd count has one"):
        linear_offsets(V, 4, "spacing", "symmetric")
    with pytest.raises(ValueError, match="odd count has one"):
        linear_offsets(V, 2, "extent", "symmetric")
    with pytest.raises(ValueError, match="'spacing' or 'extent'"):
        linear_offsets(V, 3, "spread")
    with pytest.raises(ValueError, match="'one' or 'symmetric'"):
        linear_offsets(V, 3, "spacing", "both")


# ---- the doc route -----------------------------------------------------------

def _doc(count=3, **kw):
    d = Document("lp")
    d.add(PrimitiveFeature(name="sph", kind="sphere",
                           dims={"radius": 2.0}))
    d.add(LinearPatternFeature(name="P", source_uid=d.features[0].uid,
                               count=count, vector=V, **kw))
    return d


def test_the_voices_shape_the_body_and_flip_its_meaning():
    """Through the document the offsets become geometry: spacing+one
    (the legacy route) regrounds BIT-EQUAL to the rung-era union
    (fresh against fresh, one environment - the R3b law); extent
    compresses the SAME typed vector into the full extent (bounds
    -2..12 vs the rung-era -2..22); symmetric stands with the source
    at the middle (-12..12 spacing, -7..7 extent); and the SAME
    vector under the two meanings yields DIFFERENT unions when the
    copies touch (r2 balls, v=6: spacing steps 6 clear, extent
    steps 3 overlap) - the page's "the meaning flips with the
    Distribution row", measured.  Even symmetric refuses through
    recompute, cure in the words."""
    raw = Solid.batch_union([Solid.sphere(2.0).translated((10.0 * k, 0, 0))
                             for k in range(3)])
    d_leg = _doc()
    assert d_leg.recompute().volume == raw.volume               # ==
    b = _doc(distribution="extent").recompute().to_trimesh().bounds
    assert (b[0][0], b[1][0]) == pytest.approx((-2.0, 12.0), abs=1e-4)
    b = _doc(direction="symmetric").recompute().to_trimesh().bounds
    assert (b[0][0], b[1][0]) == pytest.approx((-12.0, 12.0), abs=1e-4)
    b = _doc(distribution="extent",
             direction="symmetric").recompute().to_trimesh().bounds
    assert (b[0][0], b[1][0]) == pytest.approx((-7.0, 7.0), abs=1e-4)

    def d_v(v, **kw):
        d = Document("lp")
        d.add(PrimitiveFeature(name="sph", kind="sphere",
                               dims={"radius": 2.0}))
        d.add(LinearPatternFeature(name="P", source_uid=d.features[0].uid,
                                   count=3, vector=v, **kw))
        return d
    assert d_v((6.0, 0.0, 0.0)).recompute().volume != \
        d_v((6.0, 0.0, 0.0), distribution="extent").recompute().volume
    with pytest.raises(ValueError, match="odd count has one"):
        _doc(count=4, direction="symmetric").recompute()


def test_the_voices_ride_the_file_and_old_files_stay_put():
    """Distribution and Direction ride json as the record's own words
    and the reloaded body regrounds BIT-EQUAL (fresh against fresh).
    A file written BEFORE rung one carries neither key: from_dict
    reads 'spacing'/'one' and the legacy route runs untouched - the
    -2..22 bounds measured, the very union the rung-era ladder
    built.  Old files replay byte-honest."""
    d = _doc(distribution="extent", direction="symmetric")
    v = d.recompute()
    raw = json.loads(json.dumps(d.to_dict()))
    fe = raw["features"][-1]
    assert fe["distribution"] == "extent" and fe["direction"] == "symmetric"
    d2 = Document.from_dict(raw)
    assert (d2.features[-1].distribution, d2.features[-1].direction) \
        == ("extent", "symmetric")
    assert d2.recompute().volume == v.volume                    # ==
    del fe["distribution"], fe["direction"]                     # old file
    d3 = Document.from_dict(raw)
    f3 = d3.features[-1]
    assert (f3.distribution, f3.direction) == ("spacing", "one")
    b3 = d3.recompute().to_trimesh().bounds
    assert (b3[0][0], b3[1][0]) == pytest.approx((-2.0, 22.0), abs=1e-4)


# ---- the door -----------------------------------------------------------------

def _plate_hole(win):
    win.new_document()
    win.doc.add_plate("plate", 60, 10, 2)
    win.doc.add_cylinder("h", 1.5, 10, center=(30, 5), z=-4, op="subtract")
    win.recompute()


def test_the_door_lands_the_two_new_voices_and_refuses_the_even(
        win, qapp, monkeypatch):
    """The page's rows walked through the real door: Extent +
    Symmetric on a subtracted hole (three holes 20 apart span the
    full extent, the source middle HOLE stays - the plate loses
    THREE holes, volume measured); the sentence speaks the voice
    ("over the full extent ... symmetrically from the source");
    Spacing + One direction still rides the rung-era words BYTE-
    IDENTICAL ("3x at (10, 0, 0) mm"); and an even count with
    Symmetric is refused the M197 door law whole: NO record, no undo
    step that undoes nothing, the body untouched to the last digit,
    the cure verbatim."""
    hole_vol = math.pi * 1.5 ** 2 * 2
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "h", "dx": 20.0,
                                         "dy": 0.0, "dz": 0.0,
                                         "count": 3, "dist": "Extent",
                                         "dir": "Symmetric",
                                         "count2": 1, "dx2": 0.0,
                                         "dy2": 0.0, "dz2": 0.0,
                                         "dist2": "Spacing",
                                         "dir2": "One direction"})
    _plate_hole(win)
    win.action_linear_pattern()
    f = win.doc.features[-1]
    assert isinstance(f, LinearPatternFeature)
    assert (f.distribution, f.direction) == ("extent", "symmetric")
    assert win.doc.result.volume == pytest.approx(1200 - 3 * hole_vol,
                                                  rel=2e-2)
    msg = win.status.currentMessage()
    assert "over the full extent (20, 0, 0) mm" in msg \
        and "symmetrically from the source" in msg, msg
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "h", "dx": 10.0,
                                         "dy": 0.0, "dz": 0.0,
                                         "count": 3, "dist": "Spacing",
                                         "dir": "One direction",
                                         "count2": 1, "dx2": 0.0,
                                         "dy2": 0.0, "dz2": 0.0,
                                         "dist2": "Spacing",
                                         "dir2": "One direction"})
    _plate_hole(win)
    win.action_linear_pattern()
    assert win.status.currentMessage() == \
        "Patterned h: 3x at (10, 0, 0) mm"          # byte-rung-era
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "h", "dx": 10.0,
                                         "dy": 0.0, "dz": 0.0,
                                         "count": 4, "dist": "Spacing",
                                         "dir": "Symmetric",
                                         "count2": 1, "dx2": 0.0,
                                         "dy2": 0.0, "dz2": 0.0,
                                         "dist2": "Spacing",
                                         "dir2": "One direction"})
    _plate_hole(win)
    n, u, vol = len(win.doc.features), len(win._undo), \
        win.doc.result.volume
    win.action_linear_pattern()
    assert win.status.currentMessage().startswith("Pattern refused:")
    assert "odd count has one" in win.status.currentMessage()
    assert len(win.doc.features) == n and len(win._undo) == u
    assert win.doc.result.volume == vol


# ---- the lever ---------------------------------------------------------------

def test_the_lever_opens_the_page_rows_for_every_record(win, qapp):
    """Every linear pattern record owns both rows (the voice is the
    record's own, both values belong to it): the lever opens
    distribution and direction combos AT THE RECORD'S VALUES beside
    the rung-era rows, and the apply mouth writes them AS TYPED -
    while a script driving ONLY the rung-era rows never invents a
    voice (the guarded mouths, draft-style)."""
    rec = LinearPatternFeature(name="R", source_uid="x", count=3,
                               vector=(5.0, 0.0, 0.0),
                               distribution="extent", direction="one")
    rows = {f["key"]: f for f in win._feature_params(rec)}
    assert list(rows) == ["count", "v0", "v1", "v2", "dist", "dir",
                          "count2", "w0", "w1", "w2", "dist2",
                          "dir2"]              # M201 grew the axis
    assert tuple(rows["dist"]["choices"]) == ("spacing", "extent")
    assert rows["dist"]["default"] == "extent"            # the record's own
    assert tuple(rows["dir"]["choices"]) == ("one", "symmetric")
    assert rows["dir"]["default"] == "one"
    g = LinearPatternFeature(name="G", source_uid="x", count=3,
                             vector=(5.0, 0.0, 0.0))
    win._apply_feature_params(g, {"count": 5, "v0": 6.0, "v1": 0.0,
                                  "v2": 0.0})
    assert (g.distribution, g.direction) == ("spacing", "one")  # untouched
    assert g.count == 5
    win._apply_feature_params(g, {"count": 3, "v0": 20.0, "v1": 0.0,
                                  "v2": 0.0, "dist": "extent",
                                  "dir": "symmetric"})
    assert (g.distribution, g.direction) == ("extent", "symmetric")
    assert g.vector == (20.0, 0.0, 0.0)                   # as typed


# ---- R2: the circular Distribution row -----------------------------------

def _ball_cp(count=3, **kw):
    d = Document("cp")
    d.add(PrimitiveFeature(name="ball", kind="sphere",
                           dims={"radius": 2.0},
                           placement=(10.0, 0.0, 0.0)))
    d.add(CircularPatternFeature(name="C", source_uid=d.features[0].uid,
                                 count=count, **kw))
    return d


def test_circular_auto_full_partial_land_bit_identical():
    """The page's Full is "360 degrees around the axis" - it words NO
    angle, so the kernel's full ignores the typed value (step 360/n)
    and lands BIT-IDENTICAL (==) to auto at 360; partial is the
    rung-era inclusive span (step ang/(n-1), == auto at 90); the n<1
    guard lands one source copy; the explicit enums are named in the
    refusal when the voice is wrong.  The auto route itself is the
    old loop untouched - the same floats in the same order."""
    assert circular_rotations(360.0, 4) == [0.0, 90.0, 180.0, 270.0]
    assert circular_rotations(90.0, 4) == [0.0, 30.0, 60.0, 90.0]
    assert circular_rotations(90.0, 4, "full") == \
        circular_rotations(360.0, 4, "auto")          # angle NOTICED
    assert circular_rotations(90.0, 4, "partial") == \
        circular_rotations(90.0, 4, "auto")           # the same span
    assert circular_rotations(360.0, 0, "auto") == [0.0]   # legacy guard
    with pytest.raises(ValueError, match="'auto', 'full'"):
        circular_rotations(90.0, 3, "weave")


def test_circular_symmetric_holds_the_source_in_the_middle():
    """"Symmetric: ...in two directions from the source object to an
    angle value": the source IS an instance AND the angular middle -
    n=3 at 90 stands -45/0/+45, n=5 at 180 spans -90..+90; through
    the document the r2 ball at radius 10 measures exactly that (the
    y extremes are 10 sin45 + 2, x reaches 12 - bounds truth).  An
    EVEN count has no middle instance and the page words no rule -
    the SAME rung-one cure rides ("an odd count has one, an even one
    does not"), and the refusal comes through recompute too.  The
    named-axis voice (M125) rotates the symmetric spread about it."""
    assert circular_rotations(90.0, 3, "symmetric") == [-45.0, 0.0, 45.0]
    assert circular_rotations(180.0, 5, "symmetric") == \
        [-90.0, -45.0, 0.0, 45.0, 90.0]
    assert circular_rotations(90.0, 1, "symmetric") == [0.0]
    v = _ball_cp(angle=90.0, distribution="symmetric") \
        .recompute().to_trimesh().vertices
    want = 10.0 * math.sin(math.radians(45.0)) + 2.0
    assert v[:, 1].min() == pytest.approx(-want, abs=1e-3)
    assert v[:, 1].max() == pytest.approx(want, abs=1e-3)
    assert v[:, 0].max() == pytest.approx(12.0, abs=1e-3)   # source spoke
    v5 = _ball_cp(count=5, angle=180.0, distribution="symmetric") \
        .recompute().to_trimesh().vertices
    assert (v5[:, 1].min(), v5[:, 1].max()) == pytest.approx(
        (-12.0, 12.0), abs=1e-3)
    with pytest.raises(ValueError, match="odd count has one"):
        circular_rotations(90.0, 4, "symmetric")
    with pytest.raises(ValueError, match="odd count has one"):
        _ball_cp(count=4, distribution="symmetric").recompute()
    d = Document("cp")
    d.add(PrimitiveFeature(name="ball", kind="sphere",
                           dims={"radius": 2.0},
                           placement=(10.0, 0.0, 0.0)))
    d.add(CircularPatternFeature(name="C", source_uid=d.features[0].uid,
                                 count=3, angle=90.0, axis="Y",
                                 distribution="symmetric"))
    va = d.recompute().to_trimesh().vertices      # rotation about Y:
    assert va[:, 2].min() == pytest.approx(-want, abs=1e-3)   # the spread
    assert va[:, 2].max() == pytest.approx(want, abs=1e-3)    # lifts in z


def test_the_wrap_copy_lands_on_the_source_and_replays_are_honest():
    """Partial at a typed 360 spans 0/180/360 - the last copy lands
    ON the source (the page's "to an angle value", inclusive) and the
    union simply dedups: the bounds stay -12..12 x -2..2.  A
    symmetric spread and its auto sibling are RIGID ROTATIONS of the
    same copy set - their volumes are EQUAL within numerical noise
    (rel 1e-9, NOT bit: the inputs are different rotated meshes and
    each carries its own last-ulp float - the R3b lesson again, and
    the honesty test a naive "differs" assertion would fail).
    Files: the voice rides json EXACT and
    the reload regrounds BIT-EQUAL (==, one environment); a file
    written BEFORE rung two carries no distribution key - auto reads
    and the pre-M200 span replays BIT-EQUAL to the same build made
    fresh with the defaults."""
    b = _ball_cp(angle=360.0, distribution="partial") \
        .recompute().to_trimesh().bounds
    assert (b[0][0], b[1][0]) == pytest.approx((-12.0, 12.0), abs=1e-4)
    assert (b[0][1], b[1][1]) == pytest.approx((-2.0, 2.0), abs=1e-4)
    assert _ball_cp(angle=120.0, distribution="symmetric") \
        .recompute().volume == pytest.approx(
            _ball_cp(angle=120.0).recompute().volume, rel=1e-9)
    d = _ball_cp(angle=90.0, distribution="symmetric")
    vol = d.recompute()
    raw = json.loads(json.dumps(d.to_dict()))
    fe = raw["features"][-1]
    assert fe["distribution"] == "symmetric"
    d2 = Document.from_dict(raw)
    assert d2.recompute().volume == vol.volume             # ==, one env
    del fe["distribution"]                                 # an old file
    d3 = Document.from_dict(raw)
    assert d3.features[-1].distribution == "auto"
    assert d3.recompute().volume == _ball_cp(angle=90.0).recompute().volume


def test_the_circular_door_lands_the_three_voices(win, qapp, monkeypatch):
    """The page's circular Distribution walked through the real door.
    FULL notices the typed Angle and NEVER WRITES it (the page's Full
    words no angle - the draft door's two-voice law): the record
    stores the 360 default and the sentence rides the rung-era words
    BYTE-IDENTICAL.  PARTIAL writes the typed angle, also byte-
    legacy.  SYMMETRIC and PARTIAL on a hole near a plate edge tell
    the geometry TRUTH: at 30 degrees over 3 occurrences the partial
    spread puts its outer hole HALF OFF the plate (half a hole
    removed) while the symmetric spread stands with all THREE holes
    inside - 1200-2.5xH against 1200-3xH, measured (their volumes
    could NOT differ on open material: a rotated set is congruent -
    the container is the witness).  The symmetric sentence grows the
    page's tail; an EVEN symmetric count refuses the R1 door law
    whole: no record, no undo step, body untouched to the last digit.
    """
    H = math.pi * 1.5 ** 2 * 2

    def plate_hole():
        win.new_document()
        win.doc.add_plate("plate", 60, 10, 2)
        win.doc.add_cylinder("h", 1.5, 10, center=(40, 5), z=-4,
                             op="subtract")
        win.recompute()

    # Full notices the angle: typed 45, stored 360, legacy words
    plate_hole()
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "h",
                                         "axis": "+Z (through center)",
                                         "cx": 30.0, "cy": 5.0,
                                         "dist": "Full", "ang": 45.0,
                                         "count": 6})
    win.action_circular_pattern()
    f = win.doc.features[-1]
    assert f.distribution == "full" and f.angle == 360.0    # NOTICED only
    assert win.status.currentMessage() == \
        "Patterned h: 6x over 360 degrees about (30, 5)"   # R15: page words
    # Partial 30x3: the outer hole hangs half off the plate edge
    plate_hole()
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "h",
                                         "axis": "+Z (through center)",
                                         "cx": 30.0, "cy": 5.0,
                                         "dist": "Partial", "ang": 30.0,
                                         "count": 3})
    win.action_circular_pattern()
    assert win.doc.result.volume == pytest.approx(1200 - 2.5 * H,
                                                  rel=2e-2)
    assert win.status.currentMessage() == \
        "Patterned h: 3x over 30\u00b0 about (30, 5)"       # byte-legacy
    # Symmetric 30x3: the source holds the middle, all THREE inside
    plate_hole()
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "h",
                                         "axis": "+Z (through center)",
                                         "cx": 30.0, "cy": 5.0,
                                         "dist": "Symmetric",
                                         "ang": 30.0, "count": 3})
    win.action_circular_pattern()
    f = win.doc.features[-1]
    assert f.distribution == "symmetric" and f.angle == 30.0  # WRITTEN
    assert win.doc.result.volume == pytest.approx(1200 - 3 * H,
                                                  rel=2e-2)
    assert win.status.currentMessage() == \
        "Patterned h: 3x over 30\u00b0 about (30, 5), symmetrically " \
        "from the source"
    # Even symmetric refuses the R1 law whole (FRESH plate)
    plate_hole()
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "h",
                                         "axis": "+Z (through center)",
                                         "cx": 30.0, "cy": 5.0,
                                         "dist": "Symmetric",
                                         "ang": 90.0, "count": 4})
    n, u, vol = len(win.doc.features), len(win._undo), \
        win.doc.result.volume
    win.action_circular_pattern()
    assert win.status.currentMessage().startswith("Pattern refused:")
    assert "odd count has one" in win.status.currentMessage()
    assert len(win.doc.features) == n and len(win._undo) == u
    assert win.doc.result.volume == vol            # to the last digit


def test_the_circular_lever_speaks_each_records_own_voice(win, qapp):
    """One record one voice at the lever: the Distribution combo
    rides EVERY circular record (the record's own lowercase values);
    a FULL record never opens the Angle row - the page's Full takes
    no angle, so its stored value is never written from a row that
    does not exist; auto/partial/symmetric all open it.  The apply
    mouth is GUARDED both ways: the rung-era script answer {count,
    angle} still writes and never invents a voice, and a full
    answer writes distribution alone."""
    full = {f["key"]: f for f in win._feature_params(
        CircularPatternFeature(name="F", distribution="full",
                               angle=360.0))}
    assert list(full) == ["count", "dist"]                 # NO angle
    assert tuple(full["dist"]["choices"]) == ("auto", "full", "partial",
                                              "symmetric")
    assert full["dist"]["default"] == "full"               # the record's own
    auto = {f["key"]: f for f in win._feature_params(
        CircularPatternFeature(name="A", distribution="auto",
                               angle=90.0))}
    assert list(auto) == ["count", "dist", "angle"]        # legacy + the row
    assert auto["angle"]["suffix"] == "\u00b0"             # the R1b law
    g = CircularPatternFeature(name="G", count=3, angle=10.0)
    win._apply_feature_params(g, {"count": 5, "angle": 77.0})  # script
    assert (g.count, g.angle, g.distribution) == (5, 77.0, "auto")
    win._apply_feature_params(g, {"count": 3, "angle": 90.0,
                                  "dist": "symmetric"})
    assert (g.distribution, g.angle) == ("symmetric", 90.0)  # as typed


# ---- R3: the pattern-on-path Orientation row -------------------------------

def _path_doc(pts, orientation="identical", count=3,
              dims=None, placement=(0.0, 0.0, 0.0)):
    d = Document("pp")
    src = d.add(PrimitiveFeature(
        name="bar", kind="box",
        dims=dims or {"dx": 4.0, "dy": 1.0, "dz": 1.0},
        placement=placement))
    d.add(PathPatternFeature(name="P", op="union", source_uid=src.uid,
                             path=[list(map(float, p)) for p in pts],
                             count=count, orientation=orientation))
    return d


def test_path_stations_pair_points_with_the_paths_own_turn():
    """[SLD-REF-PATTERN, verbatim] "Path Direction: Orients each
    pattern instance relative to its position along the path" and
    "Identical: Orients all pattern instances to match the source
    object".  path_stations returns the SAME stations as
    sample_polyline (the placement law is untouched) each paired with
    the path's turn in degrees from the first station's direction: a
    straight path turns nothing (0/0/0); an L turns 90 at the corner
    and keeps it for the far leg; a quarter-circle grows 0/30/60/...
    toward ninety; a degenerate point path turns nothing and a lone
    source (n<2) lands the two-station guard with zero turn."""
    from tracer.core.sweep import path_stations, sample_polyline
    straight = [[0, 0], [10, 0], [20, 0]]
    st = path_stations(straight, 3)
    assert [(round(x, 6), round(y, 6)) for x, y, _t in st] == \
        sample_polyline(straight, 3)            # stations UNTOUCHED
    assert [t for _x, _y, t in st] == [0.0, 0.0, 0.0]
    L = [[0, 0], [10, 0], [10, 10]]
    assert [round(t, 6) for _x, _y, t in path_stations(L, 3)] == \
        [0.0, 90.0, 90.0]
    assert [round(t, 6) for _x, _y, t in path_stations(L, 4)] == \
        [0.0, 0.0, 90.0, 90.0]          # still on the first leg = 0
    import math as _m
    th = [i * (_m.pi / 2) / 24 for i in range(25)]
    arc = [[10 * _m.cos(a), 10 * _m.sin(a)] for a in th]
    at = [t for _x, _y, t in path_stations(arc, 4)]
    assert at[0] == 0.0 and all(at[i] < at[i + 1] for i in range(3))
    assert 30 < at[1] < 45 and 80 < at[3] < 95   # monotone toward 90
    assert [t for _x, _y, t in path_stations([[5, 5], [5, 5]], 3)] == \
        [0.0, 0.0, 0.0]                          # degenerate: no turn
    assert [round(t, 6) for _x, _y, t in path_stations(straight, 1)] == \
        [0.0, 0.0]                               # n<2 -> 2 stations


def test_path_direction_turns_the_copies_the_path_turns():
    """Through the document the turns become geometry.  On a STRAIGHT
    path Path Direction lands EXACTLY what Identical gives (same
    bounds, same volume to 1e-6) - there is no bend to follow, so a
    naive "the two modes always differ" claim is a lie this gate
    refuses to tell (the probe-shadow law).  On an L the chiral
    4x1x1 bar witnesses the turn: Identical keeps every copy axis-
    aligned (bounds x 0..14, y 0..11 - the far bar still lying down
    at the top); Path Direction stands the corner copies UP (bounds
    x 0..10, y 0..14 - the tall bar now reaching y 14), volumes
    CLOSE but bounding boxes DISJOINT in shape.  Watertight and
    winding-consistent both ways; a bad orientation word refuses with
    the voice named, and the n<2 guard still lands a solid."""
    straight = [[0, 0], [10, 0], [20, 0]]
    bi = _path_doc(straight).recompute().to_trimesh()
    bp = _path_doc(straight, orientation="path").recompute() \
        .to_trimesh()
    assert bi.bounds == pytest.approx(bp.bounds, abs=1e-4)  # straight!
    assert bi.volume == pytest.approx(bp.volume, rel=1e-6)
    L = [[0, 0], [10, 0], [10, 10]]
    Li = _path_doc(L).recompute().to_trimesh()
    Lp = _path_doc(L, orientation="path").recompute().to_trimesh()
    assert Li.is_watertight and Li.is_winding_consistent
    assert Lp.is_watertight and Lp.is_winding_consistent
    assert (Li.bounds[1][0], Li.bounds[1][1]) == pytest.approx(
        (14.0, 11.0), abs=1e-3)                 # far bar lying down
    assert (Lp.bounds[1][0], Lp.bounds[1][1]) == pytest.approx(
        (10.0, 14.0), abs=1e-3)                 # far bar stood up
    assert Lp.bounds[1][1] > Li.bounds[1][1]    # the turn is REAL
    with pytest.raises(ValueError, match="'identical' or 'path'"):
        _path_doc(straight, orientation="swirl").recompute()
    assert _path_doc(straight, orientation="path", count=1).recompute(
    ).volume > 0


def test_the_orientation_voice_rides_the_file_and_old_files_stay_put():
    """Path Direction is EXACT through json and the reloaded body
    regrounds BIT-EQUAL (fresh against fresh, one environment); a
    record written BEFORE rung three carries no orientation key, so
    from_dict reads 'identical' and the v1 translation route runs
    untouched - the L's far bar lies down again (y max 11, not 14).
    Old files replay byte-honest."""
    L = [[0, 0], [10, 0], [10, 10]]
    d = _path_doc(L, orientation="path")
    v = d.recompute()
    raw = json.loads(json.dumps(d.to_dict()))
    fe = raw["features"][-1]
    assert fe["orientation"] == "path"
    d2 = Document.from_dict(raw)
    assert d2.features[-1].orientation == "path"
    assert d2.recompute().volume == pytest.approx(v.volume, rel=1e-9)
    del fe["orientation"]                       # a legacy file
    d3 = Document.from_dict(raw)
    assert d3.features[-1].orientation == "identical"
    b3 = d3.recompute().to_trimesh().bounds
    assert b3[1][1] == pytest.approx(11.0, abs=1e-3)   # v1 lay-down


def _walk_sketch_m200(win, qapp, coords, plate=(80, 20), boss=(10, 10)):
    from PySide6.QtWidgets import QMessageBox
    # A second walk on one window meets the discard guard (the prior
    # sketch's lines are still in the editor); answer it Yes so the
    # door test can walk the straight and the L on one window.
    QMessageBox.question = staticmethod(
        lambda *a, **k: QMessageBox.Yes)
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": plate[0], "dy": plate[1],
                                       "dz": 5}))
    win.doc.add(PrimitiveFeature(name="boss", kind="cylinder",
                                 dims={"radius": 4.0, "height": 6},
                                 placement=(boss[0], boss[1], 5.0),
                                 op="union"))
    win.recompute()
    win.action_new_sketch()
    qapp.processEvents()
    m = win.sketch.model
    pts = [m.point(*c) for c in coords]
    for i in range(len(pts) - 1):
        m.add_line(pts[i], pts[i + 1])
    qapp.processEvents()


def test_the_path_door_asks_the_orientation_row_and_both_voices_land(
        win, qapp, monkeypatch):
    """The page's Orientation row walked through the real door (fresh
    sketch each voice - the probe-shadow law: an active sketch makes
    the SECOND action_new_sketch meet the discard guard).  The door
    asks THREE rows [src, count, orient]; Identical rides the v1
    words BYTE-IDENTICAL ("...×3 along the path") and stores the
    legacy voice; Path Direction grows the page's tail
    ("...turned to its place along it") and stands the corner boss
    UP (an L walk's bounding box reaches further in y than the same
    walk Identical).  The lever speaks both voices and the apply
    mouth is GUARDED - a script driving the rung-era {count} row
    never invents an orientation."""
    straight = ((10, 10), (30, 10), (50, 10))
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "boss", "count": 3,
                                         "orient": "Identical"})
    _walk_sketch_m200(win, qapp, straight)
    calls = []
    monkeypatch.setattr(cmddialog, "ask",
                        lambda p, t, fl, **k: (calls.append(
                            [f["key"] for f in fl]),
                            {"src": "boss", "count": 3,
                             "orient": "Identical"})[1])
    win.action_path_pattern()
    qapp.processEvents()
    assert calls[0] == ["src", "count", "orient"]     # the page's row
    f = win.doc.features[-1]
    assert f.orientation == "identical"
    assert win.status.currentMessage() == \
        "Patterned boss ×3 along the path"            # byte-v1
    ident_vol = win.doc.result.volume

    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "boss", "count": 3,
                                         "orient": "Path Direction"})
    _walk_sketch_m200(win, qapp, straight)
    win.action_path_pattern()
    qapp.processEvents()
    f = win.doc.features[-1]
    assert f.orientation == "path"
    assert win.status.currentMessage() == \
        "Patterned boss ×3 along the path, each turned to its place " \
        "along it"
    assert win.doc.result.volume == pytest.approx(ident_vol, rel=1e-6)

    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "boss", "count": 3,
                                         "orient": "Path Direction"})
    _walk_sketch_m200(win, qapp, ((10, 10), (30, 10), (30, 20)),
                      plate=(50, 25), boss=(14, 10))
    win.action_path_pattern()
    qapp.processEvents()
    ly = win.doc.result.to_trimesh().bounds[1][1]
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "boss", "count": 3,
                                         "orient": "Identical"})
    _walk_sketch_m200(win, qapp, ((10, 10), (30, 10), (30, 20)),
                      plate=(50, 25), boss=(14, 10))
    win.action_path_pattern()
    qapp.processEvents()
    iy = win.doc.result.to_trimesh().bounds[1][1]
    # An OFF-CENTER source is the honest witness (a boss centered on
    # the walk start turns about its own axis - turned, it is the
    # same boss, a "differs" claim there would be a lie). With the
    # boss 4 mm right of the start and the corner turning UPWARD,
    # Path Direction swings the far boss OVER the plate edge (its
    # rim reaches y 28 past the plate's 25) where Identical keeps it
    # inside (y 24): the turn, measured.
    assert ly == pytest.approx(28.0, abs=0.5)
    assert iy == pytest.approx(25.0, abs=0.5)   # the plate edge wins
    assert ly > iy + 1.5

    rows = {fl["key"]: fl for fl in win._feature_params(
        PathPatternFeature(name="R", source_uid="x",
                           path=[[0, 0], [5, 0]], count=3,
                           orientation="path"))}
    assert list(rows) == ["count", "orient"]
    assert tuple(rows["orient"]["choices"]) == ("identical", "path")
    assert rows["orient"]["default"] == "path"
    g = PathPatternFeature(name="G", source_uid="x",
                           path=[[0, 0], [5, 0]], count=3)
    win._apply_feature_params(g, {"count": 5})        # legacy script
    assert (g.count, g.orientation) == (5, "identical")
    win._apply_feature_params(g, {"count": 4, "orient": "path"})
    assert (g.count, g.orientation) == (4, "path")    # as typed


# ---- R4: the rectangular pattern's own second direction ------------------

def test_the_second_direction_crosses_two_lists_and_obeys_one():
    """[SLD-REF-PATTERN, rectangular how-to, verbatim] "To create a
    Rectangular Pattern in only one direction, set the Quantity value
    for Axis 2 to 1", and Quantity reads "Specify the number of pattern
    instances to create along or around an axis or path" - per axis.
    So the SECOND DIRECTION IS A COUNT ROW like the first: at count2=1
    linear_offsets hands back the rung-era list UNTOUCHED (a typed
    vector2 changes nothing there - it is noticed and never crossed);
    at 3 x 2 the two lists CROSS with the first direction walking
    outermost, so a 3-long ladder and a 2-long leg lay six copies in
    rows of two.  Each axis keeps its OWN voice: extent divides the
    second vector by (n2-1), symmetric spreads the second axis about
    the source even when the first direction holds a single copy, an
    even symmetric second count says the SAME cure ("an odd count has
    one, an even one does not") and an unknown word names the voices
    ("the distribution is 'spacing' or 'extent', not 'sideways'")."""
    one = linear_offsets(V, 3)
    assert one == [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (20.0, 0.0, 0.0)]
    assert linear_offsets(V, 3, "spacing", "one", (0.0, 8.0, 0.0),
                          1) == one                       # axis 2 silent
    assert linear_offsets(V, 3, "spacing", "one", None, 2) == one
    grid = linear_offsets(V, 3, "spacing", "one", (0.0, 8.0, 0.0), 2)
    assert grid == [(0.0, 0.0, 0.0), (0.0, 8.0, 0.0),
                    (10.0, 0.0, 0.0), (10.0, 8.0, 0.0),
                    (20.0, 0.0, 0.0), (20.0, 8.0, 0.0)]
    ext = linear_offsets(V, 3, "spacing", "one", (0.0, 16.0, 0.0), 3,
                         "extent")
    assert ext[:3] == [(0.0, 0.0, 0.0), (0.0, 8.0, 0.0),
                       (0.0, 16.0, 0.0)]     # step = extent/(n2-1)
    assert len(ext) == 9
    sym = linear_offsets(V, 1, "spacing", "one", (0.0, 10.0, 0.0), 3,
                         "spacing", "symmetric")
    assert sym == [(0.0, -10.0, 0.0), (0.0, 0.0, 0.0),
                   (0.0, 10.0, 0.0)]         # axis 1 holds one copy
    with pytest.raises(ValueError, match="odd count has one"):
        linear_offsets(V, 3, "spacing", "one", (0.0, 10.0, 0.0), 4,
                       "spacing", "symmetric")
    with pytest.raises(ValueError, match="'spacing' or 'extent'"):
        linear_offsets(V, 3, "spacing", "one", (0.0, 10.0, 0.0), 2,
                       "sideways")


def test_the_second_direction_lays_a_grid_and_leaves_one_direction_alone():
    """Through the document: three balls along x span -2..22 with the
    y bounds of ONE ball (-2..2); adding a two-long leg along y lifts
    the y bounds to -2..10 while x does not move a millimetre, and the
    volume is SIX balls where the same axis-1 rows gave three (rel
    2e-2 - mesh unions).  And the rung-zero law, measured fresh against
    fresh in ONE process with ==: count2=1 with a TYPED vector2
    regrounds BIT-EQUAL to the same build with no second direction at
    all, because at the page's own one-direction value the second
    axis is absent, not multiplied by zero.  A symmetric second axis
    stands the row about the source (-12..12 in y) while x holds one
    copy at -2..2."""
    one = _doc(count=3).recompute().to_trimesh()
    grid = _doc(count=3, vector2=(0.0, 8.0, 0.0),
                count2=2).recompute().to_trimesh()
    assert (one.bounds[1][0], one.bounds[1][1]) == pytest.approx(
        (22.0, 2.0), abs=1e-4)
    assert (grid.bounds[1][0], grid.bounds[1][1]) == pytest.approx(
        (22.0, 10.0), abs=1e-4)
    assert grid.is_watertight and grid.is_winding_consistent
    assert grid.volume == pytest.approx(2 * one.volume, rel=2e-2)
    v_typed = _doc(count=3, vector2=(0.0, 3.0, 0.0), count2=1).recompute()
    assert v_typed.volume == _doc(count=3).recompute().volume
    row = _doc(count=1, vector2=(0.0, 10.0, 0.0), count2=3,
               direction2="symmetric").recompute().to_trimesh()
    assert (row.bounds[0][1], row.bounds[1][1]) == pytest.approx(
        (-12.0, 12.0), abs=1e-3)
    assert (row.bounds[0][0], row.bounds[1][0]) == pytest.approx(
        (-2.0, 2.0), abs=1e-3)


def test_the_second_direction_rides_the_file_and_legacy_stays_one_way():
    """A grid record carries count2 / vector2 / distribution2 /
    direction2 through json and the reloaded body regrounds BIT-EQUAL
    (fresh against fresh, one environment).  A record written before
    this rung carries NONE of those keys: from_dict reads count 1 and
    the tool stays the one-direction pattern it always was - measured
    by replaying such a stripped record against a fresh one-direction
    build of the same axis-1 rows."""
    d = _doc(count=3, vector2=(0.0, 10.0, 0.0), count2=2,
             distribution2="extent", direction2="symmetric")
    d.features[-1].direction2 = "one"          # 2 x 2: even symmetric
    d.features[-1].count2 = 3                  # ...would refuse at 4
    d.features[-1].direction2 = "symmetric"    # odd: law-derivable
    v = d.recompute()
    raw = json.loads(json.dumps(d.to_dict()))
    fe = raw["features"][-1]
    assert fe["count2"] == 3 and fe["vector2"] == [0.0, 10.0, 0.0]
    assert fe["distribution2"] == "extent" and fe["direction2"] == \
        "symmetric"
    assert Document.from_dict(raw).recompute().volume == \
        pytest.approx(v.volume, rel=1e-9)
    for k in ("vector2", "count2", "distribution2", "direction2"):
        del fe[k]
    old = Document.from_dict(raw)
    assert (old.features[-1].count2, old.features[-1].vector2) == \
        (1, (0.0, 0.0, 0.0))
    assert old.recompute().volume == pytest.approx(
        _doc(count=3).recompute().volume, rel=1e-9)


def test_the_linear_door_asks_the_pages_second_direction_and_lands_both(
        win, qapp, monkeypatch):
    """The page's second axis walked through the REAL door: thirteen
    rows in the page's own order, Occurrences 2 DEFAULTING TO 1 - the
    how-to's own one-direction value - so the door's face at rest is
    the rung-era tool and says the rung-era sentence BYTE-IDENTICAL
    ("Patterned h: 3x at (10, 0, 0) mm") whatever was typed into the
    second rows (they are stored, and inert).  Ask for two and the
    sentence grows the grid: "... by 2x at (0, 3, 0) mm" - six holes
    cut, 1200 minus six, while one direction cut three.  The page's
    other voices speak per axis too: extent says "over the full
    extent" and symmetric grows the tail again.  An even symmetric
    SECOND count refuses the M197 door law whole: no record, no undo
    step that undoes nothing, the body untouched to the last digit."""
    def answers(**over):
        base = dict(src="h", dx=10.0, dy=0.0, dz=0.0, count=3,
                    dist="Spacing", dir="One direction",
                    count2=1, dx2=0.0, dy2=3.0, dz2=0.0,
                    dist2="Spacing", dir2="One direction")
        base.update(over)
        return base

    calls = []

    def spy(**over):
        def _ask(parent, title, fields, **k):
            calls.append(([f["key"] for f in fields],
                          {f["key"]: f.get("default") for f in fields}))
            return answers(**over)
        return _ask

    hole = math.pi * 1.5 ** 2 * 2
    monkeypatch.setattr(cmddialog, "ask", spy())
    _plate_hole(win)
    win.action_linear_pattern()
    qapp.processEvents()
    keys, defaults = calls[0]
    assert keys == ["src", "dx", "dy", "dz", "count", "dist", "dir",
                    "count2", "dx2", "dy2", "dz2", "dist2", "dir2"]
    assert defaults["count2"] == 1 and defaults["dist2"] == "Spacing" \
        and defaults["dir2"] == "One direction" \
        and (defaults["dx2"], defaults["dy2"], defaults["dz2"]) == \
        (0.0, 0.0, 0.0)
    f = win.doc.features[-1]
    assert f.count2 == 1 and f.vector2 == (0.0, 3.0, 0.0)   # stored...
    assert win.status.currentMessage() == \
        "Patterned h: 3x at (10, 0, 0) mm"                  # ...and inert
    assert win.doc.result.volume == pytest.approx(1200 - 3 * hole,
                                                  rel=2e-2)
    one_vol = win.doc.result.volume

    monkeypatch.setattr(cmddialog, "ask", spy(count2=2))
    _plate_hole(win)
    win.action_linear_pattern()
    qapp.processEvents()
    assert win.doc.features[-1].count2 == 2
    assert win.status.currentMessage() == \
        "Patterned h: 3x at (10, 0, 0) mm by 2x at (0, 3, 0) mm"
    assert win.doc.result.volume == pytest.approx(1200 - 6 * hole,
                                                  rel=2e-2)
    assert win.doc.result.volume < one_vol - hole           # a real row

    monkeypatch.setattr(cmddialog, "ask",
                        spy(count2=2, dist2="Extent", dy2=16.0))
    _plate_hole(win)
    win.action_linear_pattern()
    qapp.processEvents()
    assert win.status.currentMessage().endswith(
        "by 2x over the full extent (0, 16, 0) mm"), \
        win.status.currentMessage()

    monkeypatch.setattr(cmddialog, "ask",
                        spy(count2=4, dir2="Symmetric"))
    _plate_hole(win)
    n, u, vol = len(win.doc.features), len(win._undo), \
        win.doc.result.volume
    win.action_linear_pattern()
    qapp.processEvents()
    msg = win.status.currentMessage()
    assert msg.startswith("Pattern refused:") and \
        "odd count has one" in msg, msg
    assert len(win.doc.features) == n and len(win._undo) == u
    assert win.doc.result.volume == vol              # LAST digit intact


def test_the_lever_opens_the_second_direction_and_the_mouth_is_guarded(
        win, qapp):
    """Every linear record speaks the page's two axes in its OWN
    voices: the lever opens twelve rows (count, the three offsets,
    distribution, direction, then occurrences 2, the three second
    offsets, distribution 2, direction 2) and each combo defaults to
    what the record says.  The apply mouth is GUARDED for the new
    rows: a script driving the rung-era six rows never invents a
    second axis, while a script that asks for one writes it as typed
    (12 mm in y at the document's own scale)."""
    rec = LinearPatternFeature(name="R", source_uid="x", count=3,
                               vector=V, count2=2, vector2=(0.0, 7.0,
                                                            0.0),
                               distribution2="extent",
                               direction2="symmetric")
    rows = {f["key"]: f for f in win._feature_params(rec)}
    assert list(rows) == ["count", "v0", "v1", "v2", "dist", "dir",
                          "count2", "w0", "w1", "w2", "dist2", "dir2"]
    assert rows["count2"]["default"] == 2
    assert (rows["w0"]["default"], rows["w1"]["default"]) == (0.0, 7.0)
    assert tuple(rows["dist2"]["choices"]) == ("spacing", "extent")
    assert rows["dist2"]["default"] == "extent"        # the record's own
    assert rows["dir2"]["default"] == "symmetric"
    g = LinearPatternFeature(name="G", source_uid="x", count=3,
                             vector=V)
    win._apply_feature_params(g, {"count": 4, "v0": 6.0, "v1": 0.0,
                                  "v2": 0.0})
    assert (g.count2, g.vector2, g.distribution2) == \
        (1, (0.0, 0.0, 0.0), "spacing")                # never invented
    win._apply_feature_params(g, {"count": 4, "v0": 6.0, "v1": 0.0,
                                  "v2": 0.0, "count2": 3, "w0": 0.0,
                                  "w1": 12.0, "w2": 0.0,
                                  "dist2": "extent",
                                  "dir2": "symmetric"})
    assert (g.count2, g.vector2, g.distribution2, g.direction2) == \
        (3, (0.0, 12.0, 0.0), "extent", "symmetric")
