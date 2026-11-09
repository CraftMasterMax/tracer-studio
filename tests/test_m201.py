"""M201: the mirror dialog's own Operation row.

[SLD-REF-MIRROR-DIALOG, verbatim] "Operation: Select whether to create
a new body or join the mirrored body with the original body." -
"Join: Joins the mirrored body with the original body, if they
intersect. Solid bodies are combined." | "New Body: Creates a new body
mirrored across the mirror plane."

Join is exactly what this tool has ALWAYS done (the twin lands in the
source's body and the solids are combined), so operation="join" is the
legacy voice: the door rests there, old files replay it, and the door's
sentence stays byte-identical. "New Body" needs no kernel change - the
M104 fold already streams a feature into ITS OWN body bucket - so the
door opens a body for the twin and hands the previous active body back.

THE PAGE'S SILENCES, KEPT: the page words the join "if they intersect"
and says NOTHING about a twin that does not touch - no consequence is
invented, join combines either way ("Solid bodies are combined" already
says so). The page names NO offset row: our `offset` stays the house's
own mouth. The word "default" appears ZERO times on the page, so Join
is the resting voice because it is the legacy voice, never because a
vendor default is quoted. Tolerance (surfaces), Compute Option
(feature-face BRep), Object Type Faces/Bodies picking and Construction
Geometry mirroring stay UNPROMISED - a names-and-numbers door cannot
obey them.

Laws this rung pays: a record that CLAIMS a new body but streams into
the source's is a lying record - the fold REFUSES it ("... not 'Body 1'
twice"), and the door that catches such a refusal leaves NOTHING (M197:
no record, no undo step, no orphan body, the volume to the last digit).
The Operation row is a DOOR row: the lever opens only plane and offset
(one record one voice - the record got its body at birth), the browser
menu never asks, so the menu stays the join it always was.

GEOMETRY LAW (paid at the writing bench): solids that merely TOUCH at a
coplanar face shave slivers in the mesh boolean (a lug resting ON the
plate measured 3084 against the analytic 3096), so every witness here
INTERPENETRATES - the lug buries 1 mm into the plate and the analytic
numbers hold rel 1e-6.
"""
import json

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                           # noqa: E402

from tracer.core.document import (Document, ExtrudeFeature,          # noqa: E402
                                  MirrorFeature, PrimitiveFeature,
                                  RevolveFeature)
from tracer.ui import cmddialog, cmdpanel                            # noqa: E402
from tracer.ui.mainwindow import MainWindow                          # noqa: E402
from tracer.ui.renderer import SceneRenderer                         # noqa: E402


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
    cmddialog._REMEMBERED.pop("mirror", None)


# ---- helpers ---------------------------------------------------------------

PLATE = 30 * 20 * 5                    # 3000 mm^3


def _plate_lug():
    """Plate 30x20x5 CENTRED at the origin (placement is the MIN
    corner: (-15,-10,-2.5)) with ONE 4x6x4 lug buried 1 mm into its top
    at x=+12 (min corner (10,-3,1.5) - interpenetration, not
    face-touch: see the module's geometry law): u(plate, lug) =
    3000 + 96 - 24 = 3072. Its YZ@0 twin stands at x=-12, touching
    neither the lug nor any other twin: join folds all three into ONE
    body (3144), new keeps the twin as a body of its own (Body 1 3072 +
    Body 2 96), and the whole still reads 3144 - the operation moves
    BOOKKEEPING, never material."""
    d = Document("mir")
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 30, "dy": 20, "dz": 5},
                           placement=(-15, -10, -2.5)))
    lug = d.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 4, "dy": 6, "dz": 4},
                                 placement=(10, -3, 1.5), op="union"))
    return d, lug


# ---- kernel law -------------------------------------------------------------

def test_the_two_voices_are_the_only_two_and_the_lie_is_refused():
    """add_mirror refuses a third word NAMING both voices and opens no
    body while refusing - even for an exact-looking word with a stray
    space (it reports the word as typed). The fold refuses a lying
    record - one that says "new" but streams into the source's own
    body - with the cure in its words, and a bad word smuggled through
    a FILE hits the same guard. The door route never lies:
    add_mirror(operation="new") gives the twin a body of its own, keeps
    the active body where the user left it, and BUILDS there - the twin
    of a SUBTRACTED slot is a solid of the tool's own 96 mm^3 in Body 2
    (not a second cut), while Body 1 still carries the cut (3000 - 72
    buried inside the plate's thickness)."""
    d, lug = _plate_lug()
    with pytest.raises(ValueError, match="'join' or 'new'"):
        d.add_mirror("M", lug, "YZ", 0.0, operation="weld")
    assert [b["name"] for b in d.bodies] == ["Body 1"]   # no orphan body
    with pytest.raises(ValueError, match="not 'new '"):
        d.add_mirror("M", lug, "YZ", 0.0, operation="new ")  # exact word

    lying = Document("lie")
    s = lying.add(PrimitiveFeature(name="s", kind="box",
                                   dims={"dx": 4, "dy": 4, "dz": 4}))
    lying.add(MirrorFeature(name="M", op="union", source_uid=s.uid,
                            plane="YZ", offset=0.0, operation="new"))
    with pytest.raises(ValueError, match="needs a body of its own"):
        lying.recompute()                    # add() stamped Body 1 = src
    with pytest.raises(ValueError, match="not 'Body 1' twice"):
        lying.features[-1].body = "Body 1"   # the lie, spelled out
        lying.dirty = True
        lying.recompute()

    bad = Document("bw")
    z = bad.add(PrimitiveFeature(name="z", kind="box",
                                 dims={"dx": 4, "dy": 4, "dz": 4}))
    bad.add(MirrorFeature(name="M", op="union", source_uid=z.uid,
                          plane="YZ", offset=0.0, operation="stitch"))
    with pytest.raises(ValueError, match="'join' or 'new'"):
        bad.recompute()
    raw = json.loads(json.dumps(bad.to_dict()))
    with pytest.raises(ValueError, match="'join' or 'new'"):
        Document.from_dict(raw).recompute()  # the file mouth feeds it too

    dc = Document("mc")                      # mirrored CUT as New Body
    dc.add(PrimitiveFeature(name="plate", kind="box",
                            dims={"dx": 30, "dy": 20, "dz": 5},
                            placement=(-15, -10, -2.5)))
    slot = dc.add(PrimitiveFeature(
        name="slot", kind="box", dims={"dx": 4, "dy": 6, "dz": 4},
        placement=(4, -3, -0.5), op="subtract"))
    m = dc.add_mirror("M", slot, "YZ", 0.0, operation="new")
    bs = dc.body_solids()
    assert m.op == "union" and m.body == "Body 2"
    assert dc.active_body == "Body 1"        # the workbench stays put
    assert bs["Body 2"].volume == pytest.approx(96, rel=1e-6)
    assert bs["Body 1"].volume == pytest.approx(3000 - 4 * 6 * 3,
                                                rel=1e-6)


def test_join_is_the_law_that_never_moved_and_new_moves_only_bodies():
    """Fresh against fresh in ONE process: the default record and the
    explicit join reground BIT-EQUAL (== - the same computation), so
    the legacy voice is not "close", it is the same arithmetic. The two
    voices land the SAME material - the whole reads 3144 under both
    (rel 1e-9: the union order differs, so not ==) - and the witness
    is bookkeeping: join folds ONE body, new folds TWO (Body 1 alone
    keeps plate+lug at 3072, Body 2 the twin at 96). Bodies may CLAIM
    the same ground - the twin stands in plate material at x -12, so
    the parts sum to 3168 while the whole fuses the overlap once at
    3144 - and suppressing the twin folds its body clean OUT, leaving
    Body 1 standing alone at 3072."""
    d1, lug1 = _plate_lug()
    d1.add_mirror("M", lug1, "YZ", 0.0)
    d2, lug2 = _plate_lug()
    d2.add_mirror("M", lug2, "YZ", 0.0, operation="join")
    assert d1.recompute().volume == d2.recompute().volume   # ==, one law
    assert list(d1.body_solids()) == ["Body 1"]
    assert d1.result.volume == pytest.approx(3144, rel=1e-6)

    d3, lug3 = _plate_lug()
    d3.add_mirror("M", lug3, "YZ", 0.0, operation="new")
    bs = d3.body_solids()
    assert sorted(bs) == ["Body 1", "Body 2"]
    assert bs["Body 1"].volume == pytest.approx(3072, rel=1e-6)
    assert bs["Body 2"].volume == pytest.approx(96, rel=1e-6)
    assert d3.result.volume == pytest.approx(d1.result.volume, rel=1e-9)
    assert sum(v.volume for v in bs.values()) > d3.result.volume  # 3168
    d3.features[-1].suppressed = True
    d3.dirty = True
    assert list(d3.body_solids()) == ["Body 1"]          # twin's body gone
    assert d3.result.volume == pytest.approx(3072, rel=1e-6)


def test_the_operation_rides_the_file_and_a_key_absent_record_stays_join():
    """A new-body mirror writes operation AND body; the reload replays
    the fold BIT-EQUAL (== - the same computation through the file's
    mouth). A record written before this rung carries NO operation key
    with its body still naming Body 2: it reads join and streams there
    - legal, because the page's rule binds only "create a new body",
    so Body 2 simply holds the whole twin. Strip the body too and the
    record replays the pure-join build to the LAST digit (==)."""
    d, lug = _plate_lug()
    d.add_mirror("M", lug, "YZ", 2.5, operation="new")
    v = d.recompute()
    raw = json.loads(json.dumps(d.to_dict()))
    fe = raw["features"][-1]
    assert fe["operation"] == "new" and fe["body"] == "Body 2"
    re = Document.from_dict(raw)
    assert re.recompute().volume == v.volume               # ==, replay
    assert sorted(re.body_solids()) == ["Body 1", "Body 2"]

    del fe["operation"]
    mid = Document.from_dict(raw)
    assert mid.features[-1].operation == "join"
    bs = mid.body_solids()
    assert sorted(bs) == ["Body 1", "Body 2"]     # a join CAN stream
    assert bs["Body 2"].volume == pytest.approx(96, rel=1e-6)

    fe["body"] = None
    old = Document.from_dict(raw)
    base, plain_lug = _plate_lug()
    base.add_mirror("M", plain_lug, "YZ", 2.5)   # a fresh pure join, same
    assert old.features[-1].operation == "join"  #   rows through the door
    assert old.recompute().volume == base.recompute().volume   # ==


# ---- the door ----------------------------------------------------------------

def _spy(reply, store):
    def _run(parent, command_id, title, fields, *, preview=None,
             commit, abort, remember_key=None, readout=None):
        store["keys"] = [f["key"] for f in fields]
        store["defaults"] = {f["key"]: f.get("default") for f in fields}
        store["choices"] = {f["key"]: list(f.get("choices", []))
                            for f in fields if f["key"] == "op"}
        if preview is not None:
            preview(dict(reply))
        commit(dict(reply))
    return _run


def _stage(win):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 30, "dy": 20, "dz": 5},
                                 placement=(-15, -10, -2.5)))
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 4, "dy": 6, "dz": 4},
                                 placement=(10, -3, 1.5), op="union"))
    win.recompute()


def test_the_door_asks_the_pages_operation_and_lands_both_voices(
        win, qapp, monkeypatch):
    """The REAL panel grown by ONE row: keys [src, plane, off, op], the
    combo offering EXACTLY the page's two words, resting at Join - the
    legacy voice, never a quoted vendor default (the page names none).
    Join says the rung-era sentence BYTE-IDENTICAL and folds one body
    of 3144; New Body grows the tail " as a new body (Body 2)", folds
    two (3072 + 96), hands the active body back where the user left it,
    and still reads 3144 whole - the operation moved bookkeeping, not
    material."""
    seen = {}
    _stage(win)
    monkeypatch.setattr(cmdpanel, "run",
                        _spy({"src": "lug", "plane": "YZ", "off": 0.0,
                              "op": "Join"}, seen))
    win.action_mirror()
    qapp.processEvents()
    assert seen["keys"] == ["src", "plane", "off", "op"]
    assert seen["choices"]["op"] == ["Join", "New Body"]
    assert seen["defaults"]["op"] == "Join"
    f = win.doc.features[-1]
    assert (f.operation, f.body) == ("join", "Body 1")
    assert list(win.doc.body_solids()) == ["Body 1"]
    assert win.status.currentMessage() == \
        "Mirrored lug across YZ @ 0 mm"           # the rung-era sentence
    whole = win.doc.result.volume
    assert whole == pytest.approx(3144, rel=1e-6)

    _stage(win)
    monkeypatch.setattr(cmdpanel, "run",
                        _spy({"src": "lug", "plane": "YZ", "off": 0.0,
                              "op": "New Body"}, seen))
    win.action_mirror()
    qapp.processEvents()
    f = win.doc.features[-1]
    assert (f.operation, f.body, f.op) == ("new", "Body 2", "union")
    bs = win.doc.body_solids()
    assert sorted(bs) == ["Body 1", "Body 2"]
    assert bs["Body 1"].volume == pytest.approx(3072, rel=1e-6)
    assert bs["Body 2"].volume == pytest.approx(96, rel=1e-6)
    assert win.doc.active_body == "Body 1"
    assert win.status.currentMessage() == \
        "Mirrored lug across YZ @ 0 mm as a new body (Body 2)"
    assert win.doc.result.volume == pytest.approx(whole, rel=1e-9)


def test_a_lying_new_mirror_refuses_and_leaves_nothing(win, qapp,
                                                       monkeypatch):
    """The M197 door law, M201 edition, with a NEW witness class: the
    body store. A new-body mirror whose body comes back as the source's
    own (here: an add_body that lies) is refused by the fold, and the
    door rolls ALL of it back - no record, no undo step that undoes
    nothing, NO orphan Body 2 in the store, and the volume bit-for-bit
    what it was."""
    seen = {}
    _stage(win)
    n = len(win.doc.features)
    u = len(win._undo)
    bodies = [b["name"] for b in win.doc.bodies]
    vol = win.doc.result.volume
    monkeypatch.setattr(win.doc, "add_body",
                        lambda name=None: {"name": "Body 1"})
    monkeypatch.setattr(cmdpanel, "run",
                        _spy({"src": "lug", "plane": "YZ", "off": 0.0,
                              "op": "New Body"}, seen))
    win.action_mirror()
    qapp.processEvents()
    msg = win.status.currentMessage()
    assert msg.startswith("Mirror refused:") and \
        "needs a body of its own" in msg, msg
    assert len(win.doc.features) == n
    assert len(win._undo) == u
    assert [b["name"] for b in win.doc.bodies] == bodies    # no orphan
    assert win.doc.result.volume == vol                     # LAST digit


def test_the_lever_opens_no_operation_and_the_menu_stays_join(win):
    """One record, one voice: the lever of ANY mirror - even a
    new-body one - opens only plane and offset (the page words no
    edit-time rule, and a body is not a word to retype), defaults to
    the record's own values, and its apply mouth never touches
    operation or body. The browser-menu flow, which never ASKS the
    operation, must not WRITE one: its mirror is the join it always
    was, one body, the rung-era sentence with no tail."""
    rows = {f["key"]: f for f in win._feature_params(
        MirrorFeature(name="R", source_uid="x", plane="XY", offset=3.0,
                      operation="new", body="Body 2"))}
    assert list(rows) == ["plane", "offset"]
    assert rows["plane"]["default"] == "XY"
    assert rows["offset"]["default"] == 3.0
    g = MirrorFeature(name="G", source_uid="x", operation="new",
                      body="Body 9")
    win._apply_feature_params(g, {"plane": "XZ", "offset": 5.0})
    assert (g.plane, g.offset, g.operation, g.body) == \
        ("XZ", 5.0, "new", "Body 9")               # the voice survives

    _stage(win)
    lug = win.doc.features[1]
    win._mirror_feature(lug, "YZ", 0.0)            # the menu's own call
    m = win.doc.features[-1]
    assert m.operation == "join" and len(win.doc.body_solids()) == 1
    assert win.status.currentMessage() == \
        "Mirrored lug across YZ @ 0 mm"


# ---- R2: the extrude page's own Direction and Measurement ------------------

def _rect():
    return np.array([[0.0, 0.0], [40.0, 0.0], [40.0, 20.0], [0.0, 20.0]])


def _ex(**kw):
    d = Document("ex")
    d.add(ExtrudeFeature(name="w", outer=_rect(), **kw))
    return d


def test_the_legacy_route_never_moved_and_the_two_mouths_must_agree():
    """[SLD-REF-EXTRUDE, verbatim] Direction: "One Side: Creates an
    extrusion on one side of the profile plane" | "Two Sides: ..." |
    "Symmetric: ...". direction "" is the LEGACY mouth - it defers to
    the symmetric bool and the fold runs the rung-era calls in the
    rung-era order, measured BIT-IDENTICAL (volumes with ==, bounds
    with array_equal) over 36 fresh-vs-fresh configurations (heights
    3/10/0.5 x bool x taper 0/12/-8 x plane XY/XZ). An explicit word
    must AGREE with its paper copy: the bool mirrors the word
    "symmetric" ONLY, so "one"+True and "symmetric"+False are records
    whose mouths tell different stories ("tell different stories")
    while "two"+False is the truth ("two" never claimed to straddle -
    the page says each side gets its OWN settings). A third direction
    word refuses naming all three voices; a bad measurement refuses on
    BOTH symmetric routes (the worded record AND the legacy bool one -
    the cap law validates too); on a "one" record the measurement and
    height2 rows are noticed and NEVER CROSSED (bit-equal to the plain
    build - the vector2-at-count-1 law)."""
    for h in (3.0, 10.0, 0.5):
        for sym in (False, True):
            for taper in (0.0, 12.0, -8.0):
                for plane in ("XY", "XZ"):
                    a = _ex(height=h, symmetric=sym, taper=taper,
                            plane=plane,
                            placement=(1.5, -2.25, 4.0)).recompute()
                    b = _ex(height=h, direction=("symmetric" if sym
                                                  else "one"),
                            symmetric=sym, taper=taper, plane=plane,
                            placement=(1.5, -2.25, 4.0)).recompute()
                    assert a.volume == b.volume
                    assert np.array_equal(a.to_trimesh().bounds,
                                          b.to_trimesh().bounds)
    with pytest.raises(ValueError, match="'one', 'two' or 'symmetric'"):
        _ex(height=5.0, direction="sideways").recompute()
    with pytest.raises(ValueError, match="different stories"):
        _ex(height=5.0, direction="one", symmetric=True).recompute()
    with pytest.raises(ValueError, match="different stories"):
        _ex(height=5.0, direction="symmetric",
            symmetric=False).recompute()
    ok = _ex(height=6.0, direction="two", height2=4.0)   # consistent!
    assert ok.recompute().volume == pytest.approx(8000, rel=1e-6)
    for kw in (dict(direction="symmetric", symmetric=True,
                    measurement="furlong"),
               dict(symmetric=True, measurement="furlong")):
        with pytest.raises(ValueError, match="'whole' or 'half'"):
            _ex(height=5.0, **kw).recompute()
    inert = _ex(height=5.0, direction="one", measurement="furlong",
                height2=99.0)      # INVALID-but-inert on ONE side? no -
    assert inert.recompute().volume == \
        _ex(height=5.0).recompute().volume          # noticed, never read


def test_two_sides_grows_the_page_s_own_second_distance():
    """"Two Sides: Creates a UNIQUE extrusion on EACH side of the
    profile plane" + the how-to's "Adjust the settings in step 6
    independently for each side" - the second side is the page's OWN
    shape, so height2 is its own distance along -normal. A straight
    two-sides wall IS one prism of h1+h2 sunk h2 below the plane (the
    exact point set of the two butt-welded prisms - == the same
    single extrude of that size, no boolean, no slivers): footprint
    800 mm^2 x 10 mm reads 8000 with z -4..+6. A TAPERED two sides
    welds two lofts whose draft reads "+ widens as it goes" along
    each side's OWN going, and the weld at the profile plane stays
    WATERTIGHT. And height2 = 0 says what it says: nothing that way
    (== the one-side build; the page words no minimum, none invented).
    The caps answer in the same coin: cap-top +h, cap-bottom -h2."""
    d = _ex(height=6.0, direction="two", height2=4.0)
    tm = d.recompute().to_trimesh()
    assert tm.volume == pytest.approx(8000.0, rel=1e-6)
    assert (tm.bounds[0][2], tm.bounds[1][2]) == pytest.approx(
        (-4.0, 6.0), abs=1e-6)
    assert tm.is_watertight and tm.is_winding_consistent
    plain = _ex(height=10.0, placement=(0.0, 0.0, -4.0))
    assert d.recompute().volume == plain.recompute().volume  # ==, same
    zero = _ex(height=6.0, direction="two", height2=0.0)     #   prism
    assert zero.recompute().volume == \
        _ex(height=6.0).recompute().volume                    # ==
    dt = _ex(height=5.0, taper=15.0, direction="two", height2=5.0)
    tw = dt.recompute().to_trimesh()
    assert tw.is_watertight and tw.is_winding_consistent
    assert (tw.bounds[0][2], tw.bounds[1][2]) == pytest.approx(
        (-5.0, 5.0), abs=1e-3)
    assert tw.volume > 8000.0                # both drafts widen outward
    d.recompute()
    caps = {name: round(float(p[2]), 6)
            for name, p, _n in d._published_planes(d.features[0])}
    assert caps == {"cap-top": 6.0, "cap-bottom": -4.0}


def test_half_and_whole_read_the_vendor_s_own_swapped_words():
    """[verbatim] Measurement, Symmetric only: "Whole Length: Extrudes
    HALF the specified distance to each side" | "Half Length: Extrudes
    THE SPECIFIED distance to each side" - the labels read swapped to
    plain English, and they are OBEYED AS WRITTEN, never fixed. Whole
    is the pinned legacy straddle: height 10 lands z -5..+5 with the
    volume of ONE 10 mm prism (8000) - BIT-EQUAL to the symmetric-bool
    route. Half lands z -10..+10 with 16000: rel 1e-6 exactly twice
    whole. The caps mirror both readings (±h/2, ±h), and the file's
    ABSENCE of the measurement key is whole (a pre-R2 file cannot
    suddenly reach twice as deep - replays the whole straddle ==)."""
    whole = _ex(height=10.0, direction="symmetric", symmetric=True)
    bool_route = _ex(height=10.0, symmetric=True)
    assert whole.recompute().volume == bool_route.recompute().volume
    tw = whole.recompute().to_trimesh()
    assert (tw.bounds[0][2], tw.bounds[1][2]) == pytest.approx(
        (-5.0, 5.0), abs=1e-6)
    half = _ex(height=10.0, direction="symmetric", symmetric=True,
               measurement="half")
    th = half.recompute().to_trimesh()
    assert (th.bounds[0][2], th.bounds[1][2]) == pytest.approx(
        (-10.0, 10.0), abs=1e-6)
    assert th.is_watertight
    assert th.volume == pytest.approx(2 * tw.volume, rel=1e-6)
    half.recompute()
    caps = {name: round(float(p[2]), 6)
            for name, p, _n in half._published_planes(half.features[0])}
    assert caps == {"cap-top": 10.0, "cap-bottom": -10.0}


def test_the_rows_ride_the_file_and_key_absent_records_defer_to_bool():
    """direction / measurement / height2 ride both mouths; a reload
    replays BIT-EQUAL (== - the same computation through the file). A
    record written BEFORE this rung carries none of the three keys:
    direction reads "" and the fold defers to the symmetric bool - the
    tool stays exactly the tool it was (a True file replays the pinned
    straddle, a False one the one-side build, both ==). A half record
    with its measurement key stripped is the whole straddle again -
    the DEFAULT is the legacy reading, never a vendor fiat (the page
    states no initial value: "default" appears ZERO times on it)."""
    d = _ex(height=6.0, direction="two", height2=4.0)
    v = d.recompute()
    raw = json.loads(json.dumps(d.to_dict()))
    fe = raw["features"][0]
    assert fe["direction"] == "two" and fe["height2"] == 4.0 \
        and fe["measurement"] == "whole"
    assert Document.from_dict(raw).recompute().volume == v.volume
    for k in ("direction", "measurement", "height2"):
        del fe[k]
    old = Document.from_dict(raw)
    assert old.features[0].direction == ""
    assert old.features[0]._effective_direction() == "one"
    assert old.recompute().volume == _ex(height=6.0).recompute().volume
    hraw = json.loads(json.dumps(_ex(height=10.0, symmetric=True,
                                     measurement="half").to_dict()))
    del hraw["features"][0]["measurement"]
    back = Document.from_dict(hraw)
    assert back.features[0].measurement == "whole"
    assert back.recompute().volume == _ex(height=10.0, symmetric=True
                                          ).recompute().volume


def test_the_lever_opens_the_page_s_rows_and_the_mouth_is_guarded(win):
    """The edit door grew the page's rows in the house's order: height,
    fillet, chamfer, taper, symmetric, then DIRECTION (choices exactly
    the three voices), MEASUREMENT (whole|half) and the second side's
    height 2 - every combo defaulting to the RECORD's own voice, and a
    legacy bool record SHOWS its effective word (the lever never
    contradicts the rail). The apply mouth is GUARDED for all three:
    the rung-era five-row script keeps the bool as its whole mouth and
    never invents a direction; an explicit word SYNCS its paper copy
    (symmetric=True follows "symmetric") and the conditional rows write
    as typed. Outside their voice the conditional rows are stored and
    inert: a half straddle ignores the typed height 2."""
    rec = ExtrudeFeature(name="R", outer=_rect(), height=7.0,
                         direction="two", height2=3.0, offset=1.5)
    rows = {f["key"]: f for f in win._feature_params(rec)}
    assert list(rows) == ["height", "fillet", "chamfer", "taper",
                          "symmetric", "offset", "direction",
                          "measurement", "height2"]
    assert rows["offset"]["default"] == 1.5           # the record's own
    # (R4: the Offset row sits BEFORE the Direction row - the page
    # lists Start above Direction - and it is a SIGNED row: dbl()
    # with mn=None grows no "min" key, so ask()'s spin accepts the
    # negative side; the page words no sign rule, silence is silence)
    assert "min" not in rows["offset"]
    assert tuple(rows["direction"]["choices"]) == \
        ("one", "two", "symmetric")
    assert rows["direction"]["default"] == "two"       # the record's own
    assert rows["height2"]["default"] == 3.0
    legacy = ExtrudeFeature(name="L", outer=_rect(), height=4.0,
                            symmetric=True)            # no word spoken
    rows2 = {f["key"]: f for f in win._feature_params(legacy)}
    assert rows2["direction"]["default"] == "symmetric"  # the EFFECTIVE
    g = ExtrudeFeature(name="G", outer=_rect(), height=4.0)
    win._apply_feature_params(g, {"height": 5.0, "fillet": 0.0,
                                  "chamfer": 0.0, "taper": 0.0,
                                  "symmetric": False})
    assert (g.direction, g.measurement, g.height2) == \
        ("", "whole", 0.0)                    # never invented
    win._apply_feature_params(g, {"height": 5.0, "fillet": 0.0,
                                  "chamfer": 0.0, "taper": 0.0,
                                  "symmetric": False,
                                  "direction": "symmetric",
                                  "measurement": "half",
                                  "height2": 9.0})
    assert (g.direction, g.symmetric, g.measurement) == \
        ("symmetric", True, "half")           # paper follows the word
    tm = g.build().to_trimesh()
    assert (tm.bounds[0][2], tm.bounds[1][2]) == pytest.approx(
        (-5.0, 5.0), abs=1e-6)                # half of h=5 each way
    assert g.height2 == 9.0                   # stored...
    # footprint 40x20 = 800 mm^2 x the half reading's 2h = 10 mm reach:
    assert tm.volume == pytest.approx(8000.0, rel=1e-6)  # ...and inert


# ---- R3: the creation door speaks the page's Direction at birth ------------

def _spy_ask(reply, store):
    def _ask(parent, title, fields, remember_key=None):
        store["title"] = title
        store["keys"] = [f["key"] for f in fields]
        store["defaults"] = {f["key"]: f.get("default") for f in fields}
        store["choices"] = {f["key"]: tuple(f.get("choices", ()))
                            for f in fields if f["kind"] == "combo"}
        if reply is None:
            return None
        # M201 R4: a real modal answers EVERY row it opened - the OK
        # click returns the whole values() dict, resting rows included.
        # The fake mirrors that: the field defaults fill the door, the
        # script's reply overrides. (R3 wrote the replies before the
        # door grew the Offset row; auto-fill keeps them honest at the
        # 0.0 rest and pays the fifth row without a rewrite.)
        out = {f["key"]: f.get("default") for f in fields}
        out.update(reply)
        return dict(out)
    return _ask


def _stage_rect():
    return np.array([[0.0, 0.0], [40.0, 0.0], [40.0, 20.0], [0.0, 20.0]])


def test_the_creation_door_asks_the_page_s_rows_and_rests_at_one_side(
        win, qapp, monkeypatch):
    """[SLD-REF-EXTRUDE] the page IS the Extrude TOOL's dialog - its
    rows are the CREATION voice, so the door that asks only a number
    grew the page's Direction and its conditional siblings beside the
    house's own one number (M47: ONE dialog). The spy sees the real
    field list: direction / measurement / height / height2, the page's
    three voices exactly, resting at the legacy answer - direction
    "one" (every record this door ever birthed was one-sided; the page
    names NO default, "default" appears zero times). A record born at
    the resting reply carries the WORD it was asked ("one", never the
    silent "") and folds the rung-era arithmetic: == the plain kernel
    build (same computation in this very process), z 0..6, and the
    door's sentence is byte-identical to the one the one-number door
    always said. The word rides the file the reload replays ==."""
    seen = {}
    win.new_document()
    win.action_new_sketch("XY")           # the door speaks on a live sketch
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"direction": "one", "measurement": "whole", "height": 6.0,
         "height2": 0.0}, seen))
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    assert seen["title"] == "Extrude"
    # R4: the door opens the Start/Offset numeric ABOVE the Direction
    # row (page order). R5: off a FACE sketch it also opens the page's
    # Operation row LAST (Join|Cut|Intersect - the three voices the
    # fold can speak with NO target-picking; New Body/New Component
    # stay unpromised), resting at "Join", the voice this door has
    # ALWAYS birthed off-face (the page names no default).
    assert seen["keys"] == ["offset", "direction", "measurement",
                            "height", "height2", "op"]
    assert seen["choices"]["direction"] == ("one", "two", "symmetric")
    assert seen["choices"]["measurement"] == ("whole", "half")
    assert seen["choices"]["op"] == ("Join", "Cut", "Intersect")
    assert seen["defaults"]["op"] == "Join"            # the legacy rest
    assert seen["defaults"]["offset"] == 0.0   # "Profile Plane" rest
    assert seen["defaults"]["direction"] == "one"      # the legacy rest
    assert seen["defaults"]["measurement"] == "whole"  # the pinned read
    assert seen["defaults"]["height"] == 5.0           # the HOUSE rest
    assert seen["defaults"]["height2"] == 0.0
    f = win.doc.features[-1]
    assert isinstance(f, ExtrudeFeature)
    assert (f.direction, f.symmetric, f.measurement, f.height2) == \
        ("one", False, "whole", 0.0)
    assert f._effective_direction() == "one"
    assert win.doc.result.volume == _ex(height=6.0).recompute().volume
    assert win.status.currentMessage() == \
        "Extruded 1 region(s) from sk by 6 mm"          # byte-identical
    raw = json.loads(json.dumps(win.doc.to_dict()))
    fe = [x for x in raw["features"] if x["type"] == "ExtrudeFeature"][0]
    assert fe["direction"] == "one"                     # the asked word
    assert Document.from_dict(raw).recompute().volume == \
        win.doc.result.volume                            # ==, replay


def test_the_door_bears_two_sides_and_both_symmetric_readings(
        win, qapp, monkeypatch):
    """The grown door can BIRTH every voice the page words. Two sides
    with 6 and 4 lands z -4..+6 (800 mm^2 x 10 = 8,000 mm^3) and says
    "by 6 mm and 4 mm the other side" - each side its OWN distance,
    the how-to's words. Symmetric + whole (the vendor's SWAPPED line
    "Extrudes half the specified distance to each side", obeyed as
    written) lands z -3..+3 with ONE prism's volume, 4,800, and says
    "straddling the plane (half to each side)". Symmetric + half
    ("the specified distance to each side") lands z -6..+6, 9,600 -
    measured exactly twice whole - and says "to each side of the
    plane". The bool paper follows the word in every birth: True only
    under "symmetric"."""
    def birth(reply):
        win.new_document()
        win.action_new_sketch("XY")       # the door speaks on a live sketch
        monkeypatch.setattr(cmddialog, "ask", _spy_ask(reply, {}))
        win._on_profiles([(_stage_rect(), [])], "sk")
        qapp.processEvents()
        f = win.doc.features[-1]
        tm = win.doc.result.to_trimesh()
        return f, (round(float(tm.bounds[0][2]), 6),
                   round(float(tm.bounds[1][2]), 6)), \
            tm.volume, win.status.currentMessage()

    f, z, vol, msg = birth({"direction": "two", "measurement": "whole",
                            "height": 6.0, "height2": 4.0})
    assert (f.direction, f.symmetric, f.height2) == ("two", False, 4.0)
    assert z == (-4.0, 6.0) and vol == pytest.approx(8000.0, rel=1e-6)
    assert msg == "Extruded 1 region(s) from sk by 6 mm and 4 mm " \
                  "the other side"

    fw, zw, volw, msgw = birth({"direction": "symmetric",
                                "measurement": "whole", "height": 6.0,
                                "height2": 0.0})
    assert (fw.direction, fw.symmetric) == ("symmetric", True)
    assert zw == (-3.0, 3.0) and volw == pytest.approx(4800.0, rel=1e-6)
    assert msgw == "Extruded 1 region(s) from sk by 6 mm straddling " \
                   "the plane (half to each side)"

    fh, zh, volh, msgh = birth({"direction": "symmetric",
                                "measurement": "half", "height": 6.0,
                                "height2": 0.0})
    assert (fh.direction, fh.symmetric, fh.measurement) == \
        ("symmetric", True, "half")
    assert zh == (-6.0, 6.0)
    assert volh == pytest.approx(2 * volw, rel=1e-6)      # twice whole
    assert msgh == "Extruded 1 region(s) from sk by 6 mm to each " \
                   "side of the plane"


def test_a_refused_word_and_a_cancelled_door_leave_nothing(
        win, qapp, monkeypatch):
    """The M197 door law at the grown creation door, PRECHECK edition:
    a direction word outside the page's three and a measurement word
    outside the pair refuse BEFORE the capture - no record, no undo
    step that undoes nothing - the fold would refuse the same words at
    recompute (R2 law), but a door that lets them in would leave a
    dead undo step behind, and that is what the precheck pays. Cancel
    (the dialog's None) leaves the same clean nothing. The refusals
    NAME the legal voices, as the kernel's do."""
    win.new_document()
    win.action_new_sketch("XY")           # the door speaks on a live sketch
    n, u = len(win.doc.features), len(win._undo)
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"direction": "sideways", "measurement": "whole",
         "height": 6.0, "height2": 0.0}, {}))
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    msg = win.status.currentMessage()
    assert msg.startswith("Extrude refused:") \
        and "'one', 'two' or 'symmetric'" in msg and "sideways" in msg
    assert len(win.doc.features) == n and len(win._undo) == u

    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"direction": "symmetric", "measurement": "furlong",
         "height": 6.0, "height2": 0.0}, {}))
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    msg = win.status.currentMessage()
    assert msg.startswith("Extrude refused:") \
        and "'whole' or 'half'" in msg and "furlong" in msg
    assert len(win.doc.features) == n and len(win._undo) == u

    monkeypatch.setattr(cmddialog, "ask", _spy_ask(None, {}))
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    assert len(win.doc.features) == n and len(win._undo) == u
    assert win.status.currentMessage() == msg   # cancel says nothing new


def test_a_grown_region_inherits_its_sketch_s_own_voice(win):
    """The door asks ONCE for the whole sketch - so every region of
    that sketch answers the SAME voice. A region BORN LATER (re-edit
    adds a profile to a two-sided sketch) inherits the parent's whole
    answer: word, paper copy, measurement and second distance, not
    just the height it always copied (the R2 audit named this: an
    inherited height under a silent voice would strand the sibling
    one-sided). The inherited pair agrees (word + paper born true),
    so the fold never sees a disagreement, and the new region straddles
    exactly as its sibling does: z -4..+6 for heights 6 and 4."""
    d = win.doc
    parent = d.add(ExtrudeFeature(name="sk", outer=_stage_rect(),
                                  height=6.0, direction="two",
                                  height2=4.0, sid=7, region=0))
    win._update_sketch_features(7, [(_stage_rect(), []),
                                    (_stage_rect(), [])],
                                {"name": "sk"}, capture=False)
    kids = [f for f in d.features
            if isinstance(f, ExtrudeFeature) and f.sid == 7]
    assert len(kids) == 2
    kid = kids[1]
    assert (kid.direction, kid.symmetric, kid.measurement,
            kid.height2, kid.height) == ("two", False, "whole", 4.0, 6.0)
    assert kid.uid != parent.uid
    tm = d.recompute().to_trimesh()              # both straddle alike
    assert (round(float(tm.bounds[0][2]), 6),
            round(float(tm.bounds[1][2]), 6)) == (-4.0, 6.0)


def test_the_paper_copy_keeps_the_rail_honest_about_the_born_voice(
        win, qapp, monkeypatch):
    """The rail (panels.py) reads the PAPER COPY (the symmetric bool),
    never the word - so the door keeps them in step and the rail can
    never contradict a born record. A "symmetric" birth makes the rail
    say the rung-era line "extent: symmetric" (test_m70's pinned coin,
    unchanged); a "two" birth - whose bool paper is honestly False -
    grows NO extent line at all: the rail keeps silent about a voice
    it has no words for (absence is honesty too - the page's rail
    vocabulary was one extent word, and none was invented)."""
    win.new_document()
    win.action_new_sketch("XY")           # the door speaks on a live sketch
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"direction": "symmetric", "measurement": "whole",
         "height": 6.0, "height2": 0.0}, {}))
    win._on_profiles([(_stage_rect(), [])], "sym")
    qapp.processEvents()
    win.rail.props.show_feature(win.doc.features[-1])
    assert "extent: symmetric" in win.rail.props._body.text()

    win.new_document()
    win.action_new_sketch("XY")
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"direction": "two", "measurement": "whole",
         "height": 6.0, "height2": 4.0}, {}))
    win._on_profiles([(_stage_rect(), [])], "tw")
    qapp.processEvents()
    win.rail.props.show_feature(win.doc.features[-1])
    assert "extent:" not in win.rail.props._body.text()


# ---- R4: the Start/Offset numeric moves the plane every voice speaks from --

def test_the_offset_number_moves_the_plane_for_every_voice():
    """[SLD-REF-EXTRUDE, verbatim] "Offset: Starts extrusion a
    specified offset distance from the profile plane" + "Offset
    (Offset or Object start only): Specify distance to offset
    extrusion from profile plane". The page words NO rule pairing
    Start with Direction and none is invented: the profile plane
    MOVES by the number along the normal and every voice then speaks
    from the moved plane (footprint 40x20 = 800 mm^2). Sign: the page
    says "distance" but words no sign rule - silence is silence - so
    the house coin (the signed number) rules and a negative offset
    starts the other way. Moving a plane conserves the solid: every
    volume below EQUALS the same voice at rest, digit for digit -
    and the rest itself is the identity (offset 0.0 builds == the
    plain build, this very process)."""
    def zv(d):
        tm = d.recompute().to_trimesh()
        return (round(float(tm.bounds[0][2]), 6),
                round(float(tm.bounds[1][2]), 6)), tm.volume

    plain = _ex(height=6.0)
    rest = _ex(height=6.0, offset=0.0)
    assert rest.recompute().volume == plain.recompute().volume   # rest

    z, v = zv(_ex(height=6.0, offset=2.0))                        # one
    assert z == (2.0, 8.0) and v == pytest.approx(4800.0, rel=1e-6)
    z, v = zv(_ex(height=6.0, direction="two", height2=4.0,
                  offset=2.0))                                    # two
    assert z == (-2.0, 8.0) and v == pytest.approx(8000.0, rel=1e-6)
    z, v = zv(_ex(height=6.0, symmetric=True, offset=1.0))        # whole
    assert z == (-2.0, 4.0) and v == pytest.approx(4800.0, rel=1e-6)
    z, v = zv(_ex(height=6.0, symmetric=True, measurement="half",
                  offset=-1.0))                                   # half,
    assert z == (-7.0, 5.0)                                # NEGATIVE sign
    assert v == pytest.approx(9600.0, rel=1e-6)


def test_the_offset_rides_both_mouths_and_the_caps_answer_in_the_same_coin():
    """The writer carries the number and the reader honours it; a file
    made BEFORE this rung (no "offset" key) cannot suddenly start off
    the plane - the key-absent record defers to 0.0, "Profile Plane",
    and replays == the plain build. The published caps answer in the
    SAME coin as the build: a two-sided record offset 2 with heights 6
    and 4 caps at +8 and -2 (off+h above the original plane, off-h2
    below it) - the faces a sketch on the moved top would trust."""
    d = _ex(height=6.0, direction="two", height2=4.0, offset=2.0)
    raw = json.loads(json.dumps(d.to_dict()))
    fe = [x for x in raw["features"] if x["type"] == "ExtrudeFeature"][0]
    assert fe["offset"] == 2.0                          # the writer
    assert Document.from_dict(raw).recompute().volume == \
        d.recompute().volume                            # the reader
    del fe["offset"]                                    # a pre-R4 file
    back = Document.from_dict(raw)
    assert back.features[0].offset == 0.0
    assert back.recompute().volume == _ex(height=6.0, direction="two",
                                          height2=4.0).recompute().volume
    caps = {name: round(float(p[2]), 6)
            for name, p, _n in d._published_planes(d.features[0])}
    assert caps == {"cap-top": 8.0, "cap-bottom": -2.0}


def test_the_creation_door_bears_the_start_row_says_the_tail_and_the_rail(\
        win, qapp, monkeypatch):
    """The creation door opens the Offset row ABOVE the Direction row
    (page order) at the 0.0 rest - "Profile Plane", the start this
    door has ALWAYS birthed (the page names no default: "default"
    appears zero times). Typed 2 mm, the record is born starting off
    the plane (z 2..8) and the sentence grows the honest tail; at the
    rest the R3 sentence survives BYTE-IDENTICAL and the rail keeps
    its rung-era lines - the "start: 2 mm off the plane" line appears
    only when the plane actually moved (absence is honesty too)."""
    win.new_document()
    win.action_new_sketch("XY")
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"offset": 2.0, "direction": "one", "measurement": "whole",
         "height": 6.0, "height2": 0.0}, {}))
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    f = win.doc.features[-1]
    assert f.offset == 2.0
    tm = win.doc.result.to_trimesh()
    assert (round(float(tm.bounds[0][2]), 6),
            round(float(tm.bounds[1][2]), 6)) == (2.0, 8.0)
    assert win.status.currentMessage() == \
        "Extruded 1 region(s) from sk by 6 mm starting 2 mm off the " \
        "plane"
    win.rail.props.show_feature(f)
    assert "start: 2 mm off the plane" in win.rail.props._body.text()

    win.new_document()
    win.action_new_sketch("XY")
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"direction": "one", "measurement": "whole", "height": 6.0,
         "height2": 0.0}, {}))                # the fake fills offset 0.0
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    g = win.doc.features[-1]
    assert g.offset == 0.0
    assert win.status.currentMessage() == \
        "Extruded 1 region(s) from sk by 6 mm"          # byte-identical
    win.rail.props.show_feature(g)
    assert "start:" not in win.rail.props._body.text()


def test_a_grown_region_inherits_the_start_too(win):
    """The shared-answer law grows to the fifth sibling: the door
    asked the offset ONCE for the whole sketch, so a region BORN
    LATER into an offset family starts off the plane EXACTLY like its
    kin (an inherited distance under a silent start would strand the
    sibling at the plane - the record would contradict its own
    sketch). A two-sided family offset 2: both straddle z -2..+8."""
    d = win.doc
    d.add(ExtrudeFeature(name="sk", outer=_stage_rect(), height=6.0,
                         direction="two", height2=4.0, offset=2.0,
                         sid=7, region=0))
    win._update_sketch_features(7, [(_stage_rect(), []),
                                    (_stage_rect(), [])],
                                {"name": "sk"}, capture=False)
    kids = [f for f in d.features
            if isinstance(f, ExtrudeFeature) and f.sid == 7]
    assert len(kids) == 2
    assert kids[1].offset == 2.0                       # the START travels
    tm = d.recompute().to_trimesh()
    assert (round(float(tm.bounds[0][2]), 6),
            round(float(tm.bounds[1][2]), 6)) == (-2.0, 8.0)


def test_the_lever_writes_the_offset_only_when_it_opened_the_row(win):
    """The guarded coin grows to the Start row: the rung-era five-row
    script never touches a record's start (a lever that was never
    asked never writes - the count2 law), while an answer that names
    the row writes it in document measures. The ROW itself is pinned
    by the R2 gate (page order, the record's own default, signed)."""
    g = ExtrudeFeature(name="G", outer=_rect(), height=4.0, offset=2.0)
    win._apply_feature_params(g, {"height": 5.0, "fillet": 0.0,
                                  "chamfer": 0.0, "taper": 0.0,
                                  "symmetric": False})
    assert g.offset == 2.0                    # kept, never invented-away
    win._apply_feature_params(g, {"height": 5.0, "fillet": 0.0,
                                  "chamfer": 0.0, "taper": 0.0,
                                  "symmetric": False, "offset": 1.5})
    assert g.offset == 1.5                    # the row spoke, it wrote
    tm = g.build().to_trimesh()
    assert (round(float(tm.bounds[0][2]), 6),
            round(float(tm.bounds[1][2]), 6)) == (1.5, 6.5)


# ---- R5: the page's Operation row at the creation door ----------------------

def _base(d, w=50.0, dp=30.0, h=10.0):
    """Material that was already there: a 50x30x10 slab, 15,000 mm^3."""
    d.add(ExtrudeFeature(name="base",
                         outer=np.array([[0.0, 0.0], [w, 0.0],
                                         [w, dp], [0.0, dp]]),
                         height=h))
    return d


def test_the_operation_row_opens_only_where_the_tool_has_no_probe(
        win, qapp, monkeypatch):
    """The page's Operation row OFFERS five voices; the fold speaks
    the three booleans with NO target-picking (a feature joins/cuts/
    intersects the accumulator of the body it streams into), so the
    door asks Join|Cut|Intersect - and ONLY off a FACE sketch, where
    the M140 CONTACT PROBE already owns operation ("PROBE, don't
    guess"): the FACE door asks no op row and a door that never asks
    never writes (its rung-era mouths, m140's pins, untouched).
    New Body / New Component stay UNPROMISED (the vendor restricts
    the fifth to Hybrid Design itself; body creation is the mirror
    door's coin)."""
    win.new_document()
    win.action_new_sketch("XY")
    seen = {}
    monkeypatch.setattr(cmddialog, "ask", _spy_ask({"height": 6.0},
                                                   seen))
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    assert "op" in seen["keys"]                    # off-face: it opens
    assert seen["keys"][-1] == "op"                # LAST: page order
    assert win.doc.features[-1].op == "union"      # the Join rest
    assert win.status.currentMessage() == \
        "Extruded 1 region(s) from sk by 6 mm"     # no tail at the rest

    win.new_document()
    win.action_new_sketch("XY")
    m = win.sketch.model                           # a FACE sketch
    m.plane = "FACE"
    m.axes = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    m.origin = np.zeros(3)
    seen2 = {}
    monkeypatch.setattr(cmddialog, "ask", _spy_ask({"height": 6.0},
                                                   seen2))
    win._on_profiles([(_stage_rect(), [])], "f")
    qapp.processEvents()
    assert "op" not in seen2["keys"], \
        f"the FACE door never asks what the probe owns ({seen2})"
    assert seen2["keys"] == ["offset", "direction", "measurement",
                             "height", "height2"]
    assert win.doc.features[-1].op == "union"      # the probe's word


def test_a_born_cut_eats_from_what_was_already_there(win, qapp,
                                                     monkeypatch):
    """"Cut: Cuts an area out of an existing body" - and OUR fold
    needs no "Objects To Cut" pick to do it: the cut reads and writes
    the accumulator of the feature's own body. A 40x20 profile
    extruded 6 mm (4,800 mm^3) CUT into the 15,000 mm^3 slab leaves
    10,200; the record carries the kernel word op="subtract" (the
    file replays it), the rail says the word it always said
    ("operation: subtract"), and the sentence grows the honest tail.
    Join is the rest: no tail, the R4 sentence byte-identical."""
    win.new_document()
    _base(win.doc)
    win.recompute()
    assert win.doc.result.volume == pytest.approx(15000.0, rel=1e-6)
    win.action_new_sketch("XY")
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"height": 6.0, "op": "Cut"}, {}))
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    f = win.doc.features[-1]
    assert f.op == "subtract"
    assert win.doc.result.volume == pytest.approx(10200.0, rel=1e-6)
    assert win.status.currentMessage() == \
        "Extruded 1 region(s) from sk by 6 mm — cut out of what was " \
        "already there"
    win.rail.props.show_feature(f)
    assert "operation: subtract" in win.rail.props._body.text()
    raw = json.loads(json.dumps(win.doc.to_dict()))
    assert Document.from_dict(raw).recompute().volume == \
        pytest.approx(10200.0, rel=1e-6)


def test_a_cut_without_material_and_a_fourth_voice_refuse_early(
        win, qapp, monkeypatch):
    """The M197 precheck law, operation edition: the fold refuses a
    first-feature subtract by name at recompute (m118 pins THAT
    mouth), but a door that let it in would leave an undo step that
    undoes nothing - so the door refuses BEFORE the capture, quoting
    the fold's own words. A fourth operation word refuses naming the
    page's three booleans. And the honesty TRAP: the fold does NOT
    refuse a first INTERSECT (its quirk: with nothing to intersect,
    the feature itself stands) - the door mirrors the fold's refusal
    SET, invents none, and the sentence keeps SILENT about
    intersecting with material that was never there."""
    win.new_document()
    win.action_new_sketch("XY")
    n, u = len(win.doc.features), len(win._undo)
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"height": 6.0, "op": "Cut"}, {}))
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    assert win.status.currentMessage() == \
        "Extrude refused: a cut needs material to cut - the first " \
        "feature cannot be a subtract"
    assert len(win.doc.features) == n and len(win._undo) == u

    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"height": 6.0, "op": "Shrink"}, {}))
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    msg = win.status.currentMessage()
    assert msg.startswith("Extrude refused:") \
        and "'Join', 'Cut' or 'Intersect'" in msg and "Shrink" in msg
    assert len(win.doc.features) == n and len(win._undo) == u

    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"height": 6.0, "op": "Intersect"}, {}))
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    f = win.doc.features[-1]
    assert f.op == "intersect"                     # the fold stands it
    assert win.doc.result.volume == pytest.approx(4800.0, rel=1e-6)
    assert win.status.currentMessage() == \
        "Extruded 1 region(s) from sk by 6 mm"     # SILENT, and honest


def test_a_born_intersect_meets_the_material_it_finds(win, qapp,
                                                      monkeypatch):
    """"Intersect: Creates a body at the intersection of an existing
    body and the new body": the same offset-2 wall that R4 born
    FLOATING (z 2..8) into the slab's z 0..10 INTERSECTS to the
    common space - still 4,800 mm^3 (it sat wholly inside), bounds
    z 2..8 - and the sentence now EARNED its tail: intersected with
    what was already there."""
    win.new_document()
    _base(win.doc)
    win.recompute()
    win.action_new_sketch("XY")
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"height": 6.0, "offset": 2.0, "op": "Intersect"}, {}))
    win._on_profiles([(_stage_rect(), [])], "sk")
    qapp.processEvents()
    f = win.doc.features[-1]
    assert f.op == "intersect"
    tm = win.doc.result.to_trimesh()
    assert (round(float(tm.bounds[0][2]), 6),
            round(float(tm.bounds[1][2]), 6)) == (2.0, 8.0)
    assert tm.volume == pytest.approx(4800.0, rel=1e-6)
    assert win.status.currentMessage() == \
        "Extruded 1 region(s) from sk by 6 mm starting 2 mm off the " \
        "plane — intersected with what was already there"


def test_the_shared_answer_grows_to_the_operation_too(win):
    """The door asks ONCE for the whole sketch - the shared-answer
    law now covers the SIXTH sibling: a region born LATER into a cut
    family must cut like its kin (the growth used to copy the height
    and let the new region default back to union - a family that
    silently switched from eating to adding mid-sketch). Base slab
    15,000; the family's offset-2 walls eat the SAME z 2..8 space
    twice which is once - 10,200 stands."""
    d = win.doc
    _base(d)
    d.add(ExtrudeFeature(name="sk", outer=_stage_rect(), height=6.0,
                         offset=2.0, op="subtract", sid=7, region=0))
    win._update_sketch_features(7, [(_stage_rect(), []),
                                    (_stage_rect(), [])],
                                {"name": "sk"}, capture=False)
    kids = [f for f in d.features
            if isinstance(f, ExtrudeFeature) and f.sid == 7]
    assert len(kids) == 2
    assert kids[1].op == "subtract"                # the voice travels
    assert kids[1].offset == 2.0
    win.recompute()
    assert d.result.volume == pytest.approx(10200.0, rel=1e-6)


# ---- R6: the revolve door speaks its own page ------------------------------

def _tube():
    """A profile a FULL turn makes a ring of: u 5..10, v 0..5 -> a
    cylindrical shell r 5..10, height 5: pi*(100-25)*5 = 375*pi."""
    return np.array([[5.0, 0.0], [10.0, 0.0], [10.0, 5.0], [5.0, 5.0]])


def test_the_revolve_door_opens_the_page_rows_it_can_speak(
        win, qapp, monkeypatch):
    """[SLD-REF-REVOLVE, verbatim] "Extent Type: ... Partial: Revolves
    the profile around the axis to an angle value that you specify.
    To Object: Revolves to a body, face, or plane that you select.
    Full: Revolves the profile 360 degrees around the axis." + "Angle:
    Specifies the angle to revolve around the axis" + "Operation:
    Select an operation to control how the feature affects the
    design". The door traded its one getDouble for the page's THREE
    honorable rows: Extent Partial|Full (To Object is PICKING -
    UNPROMISED, R5's coin), the Angle numeric, and Operation - the
    SAME three booleans as the extrude, which open EVERYWHERE here:
    unlike the extrude, the revolve has NEVER had a contact probe, so
    no plane owns its operation. Direction (One Side/Two Sides/
    Symmetric) stays UNPROMISED: the page splits no angle across the
    profile plane and the kernel sweeps one way - a row there would
    INVENT a pairing rule. Rests are house facts (the page says
    "default" ZERO times): Full = angle 360.0 = what this door has
    ALWAYS birthed (getDouble's own rest), Join = what the fold has
    always folded. The rest sentence - pinned for the first time in
    this rung's gates - stays BYTE-IDENTICAL to the rung-era voice."""
    win.new_document()
    win.action_new_sketch("XY")
    seen = {}
    monkeypatch.setattr(cmddialog, "ask", _spy_ask({}, seen))
    win._on_profiles([(_tube(), [])], "sk", revolve=True)
    qapp.processEvents()
    assert seen["title"] == "Revolve"
    assert seen["keys"] == ["extent", "angle", "op"]     # page order
    assert seen["choices"]["extent"] == ("Partial", "Full")
    assert seen["defaults"]["extent"] == "Full"   # the legacy 360 voice
    assert seen["choices"]["op"] == ("Join", "Cut", "Intersect")
    assert seen["defaults"]["op"] == "Join"
    assert seen["defaults"]["angle"] == 360.0     # getDouble's rest
    f = win.doc.features[-1]
    assert f.angle == 360.0 and f.op == "union"
    assert win.status.currentMessage() == \
        "Revolved 1 region(s) from sk by 360°"    # byte-identical rest
    assert win.doc.result.volume == pytest.approx(np.pi * 375, rel=2e-2)
    win.rail.props.show_feature(f)
    rail = win.rail.props._body.text()
    assert "angle: 360°" in rail and "operation: union" in rail

    # And the row opens off EVERY plane: a FACE revolve asks the op
    # too (the M140 probe never spoke for revolves - not on FACE, not
    # anywhere; a row opens where the tool has no other mouth).
    win.new_document()
    win.action_new_sketch("XY")
    m = win.sketch.model
    m.plane = "FACE"
    m.axes = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    m.origin = np.zeros(3)
    seen2 = {}
    monkeypatch.setattr(cmddialog, "ask", _spy_ask({}, seen2))
    win._on_profiles([(_tube(), [])], "f", revolve=True)
    qapp.processEvents()
    assert seen2["keys"] == ["extent", "angle", "op"]
    assert win.doc.features[-1].op == "union"     # the asked Join rest


def test_full_is_the_number_360_and_partial_is_the_typed_number(
        win, qapp, monkeypatch):
    """NUMERIC-ENCODES-EXTENT (R4's law, angular sibling): the page
    ITSELF defines Full as "Revolves the profile 360 degrees", and
    the kernel keeps no other word for a closed sweep (measured: 360
    closes the ring; 361/400/720 clamp to the byte-same solid, so a
    stored "extent" field would record a distinction the machine
    cannot speak). So Full WRITES 360.0 and the typed number goes
    stored-and-inert (M201 R2's conditional-row law, numeric
    edition); Partial speaks the number as the page says: "to an
    angle value that you specify". Rest-as-identity: the new door's
    Full birth equals the direct kernel construction the old door
    always made - same field, same solid, same sentence."""
    win.new_document()
    win.action_new_sketch("XY")
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"extent": "Full", "angle": 90.0}, {}))
    win._on_profiles([(_tube(), [])], "sk", revolve=True)
    qapp.processEvents()
    f = win.doc.features[-1]
    assert f.angle == 360.0, "Full INERTS the typed number"
    assert win.status.currentMessage() == \
        "Revolved 1 region(s) from sk by 360°"
    inert_vol = win.doc.result.volume
    win.new_document()
    d_direct = win.doc
    d_direct.add(RevolveFeature(name="direct", outer=_tube(),
                                angle=360.0))
    d_direct.recompute()
    assert d_direct.result.volume == pytest.approx(inert_vol, rel=1e-9)

    win.new_document()
    win.action_new_sketch("XY")
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"extent": "Partial", "angle": 90.0}, {}))
    win._on_profiles([(_tube(), [])], "sk", revolve=True)
    qapp.processEvents()
    f = win.doc.features[-1]
    assert f.angle == 90.0
    assert win.doc.result.volume == pytest.approx(np.pi * 375 / 4,
                                                  rel=2e-2)
    assert win.status.currentMessage() == \
        "Revolved 1 region(s) from sk by 90°"


def test_a_born_cut_and_a_born_intersect_speak_the_same_coin(
        win, qapp, monkeypatch):
    """The fold is feature-agnostic (it folds EVERY feature's op
    against the accumulator of the body it streams into - the browser
    menu has edited a revolve's operation since M11), so the revolve
    door's Operation row rides R5's coin to the word: same kernel
    mapping, same refusal set, same tails. Ring r 5..10 h 5 (375*pi)
    revolves into the 50x30x10 slab (15,000 mm^3): a QUARTER of it
    sits in the slab's octant (x>=0, z 0..10 - the r<=10 ring fits),
    93.75*pi, so a born Cut leaves 15,000 - 93.75*pi and a born
    Intersect IS that quarter ring (the page's verb again: "Creates a
    body at the intersection")."""
    win.new_document()
    _base(win.doc)
    win.recompute()
    win.action_new_sketch("XY")
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"op": "Cut"}, {}))
    win._on_profiles([(_tube(), [])], "sk", revolve=True)
    qapp.processEvents()
    f = win.doc.features[-1]
    assert f.op == "subtract"
    assert win.doc.result.volume == pytest.approx(
        15000.0 - np.pi * 375 / 4, rel=2e-2)
    assert win.status.currentMessage() == \
        "Revolved 1 region(s) from sk by 360° — cut out of what was " \
        "already there"
    win.rail.props.show_feature(f)
    assert "operation: subtract" in win.rail.props._body.text()
    raw = json.loads(json.dumps(win.doc.to_dict()))
    assert Document.from_dict(raw).recompute().volume == \
        pytest.approx(15000.0 - np.pi * 375 / 4, rel=2e-2)

    win.new_document()
    _base(win.doc)
    win.recompute()
    win.action_new_sketch("XY")
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"op": "Intersect"}, {}))
    win._on_profiles([(_tube(), [])], "sk", revolve=True)
    qapp.processEvents()
    f = win.doc.features[-1]
    assert f.op == "intersect"
    assert win.doc.result.volume == pytest.approx(np.pi * 375 / 4,
                                                  rel=2e-2)
    assert win.status.currentMessage() == \
        "Revolved 1 region(s) from sk by 360° — intersected with " \
        "what was already there"


def test_revolve_refusals_come_before_the_capture(win, qapp,
                                                  monkeypatch):
    """R5's precheck law, revolve edition, at BOTH new words: a Cut
    with no material refuses quoting the fold's own words BEFORE the
    capture (no dead undo step); a third extent word refuses naming
    the two this door speaks - and "To Object" is the pick the door
    cannot honor, so it must not smuggle itself in as a word; a
    fourth operation word refuses naming the three. The fold's
    intersect quirk mirrors byte for byte: a first INTERSECT STANDS
    (with nothing to intersect the feature itself is the body) and
    the sentence stays the plain rest voice - silent, and honest."""
    win.new_document()
    win.action_new_sketch("XY")
    n, u = len(win.doc.features), len(win._undo)

    monkeypatch.setattr(cmddialog, "ask", _spy_ask({"op": "Cut"}, {}))
    win._on_profiles([(_tube(), [])], "sk", revolve=True)
    qapp.processEvents()
    assert win.status.currentMessage() == \
        "Revolve refused: a cut needs material to cut - the first " \
        "feature cannot be a subtract"
    assert len(win.doc.features) == n and len(win._undo) == u

    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"extent": "To Object"}, {}))
    win._on_profiles([(_tube(), [])], "sk", revolve=True)
    qapp.processEvents()
    assert win.status.currentMessage() == \
        "Revolve refused: the extent is 'Partial' or 'Full', not " \
        "'To Object'"
    assert len(win.doc.features) == n and len(win._undo) == u

    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"op": "Shrink"}, {}))
    win._on_profiles([(_tube(), [])], "sk", revolve=True)
    qapp.processEvents()
    assert win.status.currentMessage() == \
        "Revolve refused: the operation is 'Join', 'Cut' or " \
        "'Intersect', not 'Shrink'"
    assert len(win.doc.features) == n and len(win._undo) == u

    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"op": "Intersect"}, {}))
    win._on_profiles([(_tube(), [])], "sk", revolve=True)
    qapp.processEvents()
    f = win.doc.features[-1]
    assert f.op == "intersect"                     # the fold stands it
    assert win.doc.result.volume == pytest.approx(np.pi * 375, rel=2e-2)
    assert win.status.currentMessage() == \
        "Revolved 1 region(s) from sk by 360°"     # SILENT, and honest


def test_the_shared_answer_and_the_rest_voice_survive_the_grown_door(
        win):
    """The door asks ONCE for the whole sketch, and the growth path
    ALREADY streamed op and angle from the sibling (the generic
    extra.update - this gate PINS it for revolves for the first time:
    a region born later into a cut family must cut like its kin).
    The double-eaten ring quarter is eaten ONCE: 15,000 - 93.75*pi
    stands; and the resting voice of the grown door is the OLD
    door's, field for field (the axis key rides the payload, so an
    undeclared sketch grows the legacy V-axis with axis=None)."""
    d = win.doc
    _base(d)
    d.add(RevolveFeature(name="rv", outer=_tube(), angle=360.0,
                         op="subtract", sid=8, region=0))
    win._update_sketch_features(8, [(_tube(), []), (_tube(), [])],
                                {"name": "rv"}, capture=False)
    kids = [f for f in d.features
            if isinstance(f, RevolveFeature) and f.sid == 8]
    assert len(kids) == 2
    assert kids[1].op == "subtract"                # the voice travels
    assert kids[1].angle == 360.0                  # and the number
    assert kids[1].axis is None                    # legacy V-axis
    win.recompute()
    assert d.result.volume == pytest.approx(
        15000.0 - np.pi * 375 / 4, rel=2e-2)
