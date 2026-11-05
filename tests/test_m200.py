"""M200: the linear pattern's own Distribution and Direction.

[SLD-REF-PATTERN / GUID-9622573F, verbatim] "Distribution: Extent -
Distributes pattern instances evenly along the FULL EXTENT of the
distance value that you specify | Spacing - ...spaced at the distance
value" and "Direction: One Direction - ...in one direction from the
source | Symmetric - ...symmetrically in two directions FROM THE
SOURCE OBJECT along this axis".

Rung one cuts the two typed rows. The house's rung-era voice (count
INCLUDING the source, offsets k x vector) is EXACTLY the page's
Spacing + One Direction, so that route lands BIT-IDENTICAL and old
files replay untouched. Extent re-reads the vector as the full
end-to-end extent - the page's own "the meaning flips with the
Distribution row". Symmetric centers the count ON the source: an ODD
count is law-derivable (the source is an instance AND the middle);
an even one has no middle instance and the page words no rule - the
kernel REFUSES with the cure rather than inventing one.

Unpromised, by the pages' own words: Suppression (canvas checkboxes
over instances - no typed equivalent), Compute Type (feature-face
BRep), picked edge/cylindrical Axes, second-edge skew, pattern-on-
path and geometric siblings.
"""
import json
import math

import numpy as np
import pytest

from tracer.core.document import (Document, LinearPatternFeature,
                                  PrimitiveFeature, linear_offsets)
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
    """The legacy voice IS the page's Spacing + One Direction: the
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
    Spacing + One Direction still rides the rung-era words BYTE-
    IDENTICAL ("3x at (10, 0, 0) mm"); and an even count with
    Symmetric is refused the M197 door law whole: NO record, no undo
    step that undoes nothing, the body untouched to the last digit,
    the cure verbatim."""
    hole_vol = math.pi * 1.5 ** 2 * 2
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "h", "dx": 20.0,
                                         "dy": 0.0, "dz": 0.0,
                                         "count": 3, "dist": "Extent",
                                         "dir": "Symmetric"})
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
                                         "dir": "One Direction"})
    _plate_hole(win)
    win.action_linear_pattern()
    assert win.status.currentMessage() == \
        "Patterned h: 3x at (10, 0, 0) mm"          # byte-rung-era
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"src": "h", "dx": 10.0,
                                         "dy": 0.0, "dz": 0.0,
                                         "count": 4, "dist": "Spacing",
                                         "dir": "Symmetric"})
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
    assert list(rows) == ["count", "v0", "v1", "v2", "dist", "dir"]
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
