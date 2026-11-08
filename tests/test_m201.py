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
                                  MirrorFeature, PrimitiveFeature)
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
                         direction="two", height2=3.0)
    rows = {f["key"]: f for f in win._feature_params(rec)}
    assert list(rows) == ["height", "fillet", "chamfer", "taper",
                          "symmetric", "direction", "measurement",
                          "height2"]
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
