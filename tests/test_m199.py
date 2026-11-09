"""M201 R13: the Fluid Volume dialog's OWN contract — External only.

[SLD fluid volume page, verbatim] "Fluid Volume creates a body that
envelopes or fills the interior of the selected tool bodies." The
EXTERNAL procedure names its shapes exactly - "Box", "Cylinder",
"Hemisphere" - gates the direction row ("This option is available
when the Shape Type is Cylinder or Hemisphere", words "X-Axis Y-Axis
Z-Axis"), offers "click Flip Direction to invert the hemisphere", and
ONE number: "This value is the distance between the outer faces of
the tool bodies and the outer faces of the fluid volume."

THE STREAM IS A BODY OF ITS OWN (the interference precedent): the
envelope MINUS the tools - the body a flow would travel around. The
page's tool selection is a canvas PICK; our bridge is the check-list
of NAMED bodies (names compose; the geometry follows), and the
envelope RE-SOLVES on every recompute - move a tool, the fluid
follows.

INTERNAL is NOT offered - the page gates it itself ("You will not be
permitted to complete the fluid body creation until the program
detects a completely isolated interior volume", and capping needs
surface bodies this kernel has none of) - a scripted other word is
refused BY NAME, before the capture (R12's Spiral coin). The Split
Result row is a tangent-EDGE story the mesh subtract cannot honour:
the door does not speak it (absence is honesty, R4's law).

"default" counts ZERO on the page: every rest (External, Box, Z-Axis,
flip off, offset 0.0) and every piece of envelope arithmetic below is
a HOUSE FACT, named as one. Offset is a DISTANCE, so it wears the
unit on both mouths (UNIT-SUFFIX LAW's other edge - R12's turn count
wore none, this one must).
"""
import json

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                           # noqa: E402

from tracer.core.document import (Document, FluidVolumeFeature,      # noqa: E402
                                  PrimitiveFeature)
from tracer.ui import cmddialog                                      # noqa: E402
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
    cmddialog._REMEMBERED.pop("fluid", None)


# ---- helpers ---------------------------------------------------------------

def approx_ratio(actual, truth, rel=2e-3):
    """Faceted-truth comparison (the geometry module's house coin):
    mesh cylinders and spheres carry a ~1e-3 faceting error; EXACT
    box arithmetic must not ride the tolerance."""
    assert abs(actual - truth) <= abs(truth) * rel + 1e-9


def _spy_ask(reply, store):
    def _ask(parent, title, fields, remember_key=None):
        store["title"] = title
        store["keys"] = [f["key"] for f in fields]
        store["defaults"] = {f["key"]: f.get("default") for f in fields}
        store["choices"] = {f["key"]: tuple(f.get("choices", ()))
                            for f in fields if f["kind"] == "combo"}
        store["kinds"] = {f["key"]: f["kind"] for f in fields}
        out = {f["key"]: f.get("default") for f in fields}
        out.update(reply or {})
        return dict(out)
    return _ask


def _stage(win, kind="box", dims=None, placement=(0, 0, 0)):
    """Kernel-staged primitive (no primitive door - this module's law
    is the FLUID door): one real body, implicitly "Body 1"."""
    win.doc.add(PrimitiveFeature(name="tool", kind=kind,
                                 dims=dict(dims or {"dx": 2, "dy": 2,
                                                    "dz": 2}),
                                 placement=placement))
    win.doc.dirty = True
    win.doc.recompute()


def _cube_doc():
    """One 2x2x2 box at the origin corner - the tools' bbox is then
    [0,2]^3, so the resting arithmetic is hand-checkable to the digit."""
    d = Document("fl")
    d.add(PrimitiveFeature(name="cube", kind="box",
                           dims={"dx": 2, "dy": 2, "dz": 2}))
    return d


# ---- gates ------------------------------------------------------------------

def test_the_door_asks_the_page_s_rows_in_page_order_and_refuses_internal(
        win, qapp, monkeypatch):
    """The spy sees the real field list: Volume | Tool bodies | Shape
    Type | Shape Direction | Flip Direction | Offset - the page's own
    rows in the page's order, the tool selection bridged as the
    check-list of NAMED bodies. The Volume combo carries the ONE word
    this kernel can honour (Internal stays gated by the page itself),
    and a scripted Internal is refused BY NAME quoting the page's own
    precondition - BEFORE the capture, so NOTHING is born (M197: no
    record, no undo step, no orphan body)."""
    win.new_document()
    _stage(win)
    qapp.processEvents()
    store = {}
    monkeypatch.setattr(cmddialog, "ask", _spy_ask({"volume": "Internal"},
                                                   store))
    before = (len(win.doc.features), len(win.doc.body_list()))
    win.action_fluid_volume()
    qapp.processEvents()
    assert store["keys"] == ["volume", "tools", "shape", "direction",
                             "flip", "offset"]
    assert store["kinds"]["tools"] == "checks"
    assert store["choices"]["volume"] == ("External",)
    assert store["choices"]["shape"] == ("Box", "Cylinder", "Hemisphere")
    assert store["choices"]["direction"] == ("X-Axis", "Y-Axis", "Z-Axis")
    assert store["defaults"]["shape"] == "Box"          # house rest
    assert store["defaults"]["offset"] == 0.0
    msg = win.status.currentMessage()
    assert msg.startswith("Fluid Volume refused: the volume is "
                          "'External', not 'Internal'")
    assert "completely isolated interior volume" in msg
    assert (len(win.doc.features), len(win.doc.body_list())) == before


def test_the_box_envelope_is_exact_arithmetic(win, qapp, monkeypatch):
    """The house arithmetic at its exact edge (R12's lesson: the
    solver is pure arithmetic where the shapes allow it): a 2^3 tool
    box grown by offset 1 envelopes 4^3 - 2^3 = 56 mm^3 of fluid, TO
    THE DIGIT - boxes are boxes. The door's sentence speaks the
    MEASURED volume (body_solids is the one mouth), never a promise;
    at the offset REST (0.0) the envelope hugs the tools and the
    fluid reads zero - the record exists, the gap does not."""
    win.new_document()
    _stage(win)
    qapp.processEvents()
    body = win.doc.body_list()[0]["name"]
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"tools": [body], "shape": "Box", "offset": 1.0}, {}))
    win.action_fluid_volume()
    qapp.processEvents()
    f = win.doc.features[-1]
    assert isinstance(f, FluidVolumeFeature)
    assert f.tools == ("Body 1",) and f.volume == "External"
    sol = win.doc.body_solids()
    assert sol[f.name].volume == pytest.approx(56.0, abs=1e-9)
    assert win.status.currentMessage() == (
        "Fluid box — Box envelope around Body 1, offset 1 mm — "
        "56 mm³ of fluid")

    win.new_document()
    _stage(win)
    qapp.processEvents()
    body = win.doc.body_list()[0]["name"]
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"tools": [body], "shape": "Box", "offset": 0.0}, {}))
    win.action_fluid_volume()
    qapp.processEvents()
    sol = win.doc.body_solids()
    assert sol[win.doc.features[-1].name].volume == pytest.approx(
        0.0, abs=1e-9)


def test_the_cylinder_and_its_gated_direction_bake(win, qapp, monkeypatch):
    """Cylinder along Z about a r=3 h=10 tool cylinder: the envelope
    is r=3+1 long 10+2 (the face-to-face law closes BOTH ends), so
    the fluid is pi*(16*12 - 9*10) = 102*pi - faceted truth at the
    house's 2e-3. The X-Axis word MOVES the axis: the tool lies
    ACROSS it (axial span 6 from the r=3 disc grown to 8; radial
    reach sqrt(3^2+5^2)=sqrt(34) from the z=0..10 column - hand-
    checkable), so the radial bbox reads 2*(sqrt(34)+1) on the other
    two - the direction row is no label."""
    win.new_document()
    _stage(win, kind="cylinder", dims={"radius": 3.0, "height": 10.0})
    qapp.processEvents()
    body = win.doc.body_list()[0]["name"]
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"tools": [body], "shape": "Cylinder", "direction": "Z-Axis",
         "offset": 1.0}, {}))
    win.action_fluid_volume()
    qapp.processEvents()
    f = win.doc.features[-1]
    approx_ratio(win.doc.body_solids()[f.name].volume,
                 np.pi * (16.0 * 12.0 - 9.0 * 10.0))

    win.new_document()
    _stage(win, kind="cylinder", dims={"radius": 3.0, "height": 10.0})
    qapp.processEvents()
    body = win.doc.body_list()[0]["name"]
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"tools": [body], "shape": "Cylinder", "direction": "X-Axis",
         "offset": 1.0}, {}))
    win.action_fluid_volume()
    qapp.processEvents()
    bb = win.doc.body_solids()[win.doc.features[-1].name].bounding_box
    span = bb[1] - bb[0]
    assert span[0] == pytest.approx(8.0, abs=1e-4)       # axial 6 + 2
    assert span[1] == pytest.approx(2 * (np.sqrt(34) + 1), abs=1e-2)


def test_the_hemisphere_envelopes_and_flip_inverts(win, qapp, monkeypatch):
    """The dome must ENVELOPE: a hemisphere about a tool box straddling
    the origin rests its flat face at z=-1-1=-2 with the tools INSIDE
    (a flat face through the bbox center would cut them in half -
    that construction was caught and refused in review; an envelope
    that cut its own tools is not an envelope). Radius = the farthest
    tool vertex from the anchor plus the offset: r = sqrt(11)+1, so
    the fluid is the faceted half-ball minus the tool,
    (2/3)*pi*r^3 - 8. Flip Direction ("to invert the hemisphere") is
    an EXACT mirror: equal volume, the flat face jumps to +2."""
    def _hemi(flip):
        win.new_document()
        _stage(win, dims={"dx": 2, "dy": 2, "dz": 2},
               placement=(-1.0, -1.0, -1.0))
        qapp.processEvents()
        body = win.doc.body_list()[0]["name"]
        monkeypatch.setattr(cmddialog, "ask", _spy_ask(
            {"tools": [body], "shape": "Hemisphere",
             "direction": "Z-Axis", "offset": 1.0, "flip": flip}, {}))
        win.action_fluid_volume()
        qapp.processEvents()
        f = win.doc.features[-1]
        return win.doc.body_solids()[f.name]

    r = np.sqrt(11.0) + 1.0
    s = _hemi(False)
    approx_ratio(s.volume, (2.0 / 3.0) * np.pi * r ** 3 - 8.0)
    assert s.bounding_box[0][2] == pytest.approx(-2.0, abs=1e-4)
    assert s.to_trimesh().vertices[:, 2].max() == pytest.approx(
        -2.0 + r, abs=1e-3)
    sf = _hemi(True)
    assert sf.volume == pytest.approx(s.volume, rel=1e-9)
    assert sf.bounding_box[1][2] == pytest.approx(2.0, abs=1e-4)


def test_the_zero_tool_and_scripted_word_refusals_leave_nothing(
        win, qapp, monkeypatch):
    """Two more refusals, both BEFORE the capture (the R12 coin): no
    tool body ticked - the page envelopes the SELECTED bodies, so
    there is nothing to envelope and the door says so; a scripted
    shape word the page never prints - refused by name, the kernel's
    own word list the mouth. Neither leaves a record, a body, or an
    undo step."""
    win.new_document()
    _stage(win)
    qapp.processEvents()
    before = (len(win.doc.features), len(win.doc.body_list()))
    monkeypatch.setattr(cmddialog, "ask", _spy_ask({"tools": []}, {}))
    win.action_fluid_volume()
    qapp.processEvents()
    assert win.status.currentMessage().startswith(
        "Fluid Volume refused: the page envelopes the selected tool "
        "bodies - select at least one")
    assert (len(win.doc.features), len(win.doc.body_list())) == before

    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"tools": ["Body 1"], "shape": "Torus"}, {}))
    win.action_fluid_volume()
    qapp.processEvents()
    assert win.status.currentMessage() == (
        "Fluid Volume refused: the shape type is 'Box', 'Cylinder' "
        "or 'Hemisphere', not 'Torus'")
    assert (len(win.doc.features), len(win.doc.body_list())) == before


def test_the_envelope_follows_its_tools_live(win):
    """The interference law, claimed and proven: kinematic STATE is
    what the fluid follows (the architecture's Placement != Feature
    coin) - move_body creates NO timeline feature, so the envelope
    re-reads the tool AS ITS USER SEES IT: the 2^3 box slides 10 mm
    and the whole envelope slides with it, -1 to 9 on x, still 56
    mm^3 to the digit. (A MoveFeature DOWNSTREAM of the fluid could
    never move it - stream order is stream order.)"""
    d = _cube_doc()
    b, f = d.add_fluid_volume(["Body 1"], "Box", offset=1.0)
    before = d.body_solids()[b["name"]].bounding_box
    assert before[0][0] == pytest.approx(-1.0, abs=1e-9)
    d.move_body("Body 1", 10.0, 0.0, 0.0)      # kinematic state
    after = d.body_solids()[b["name"]].bounding_box
    sol = d.body_solids()
    assert sol[f.name].volume == pytest.approx(56.0, abs=1e-9)
    assert after[0][0] == pytest.approx(9.0, abs=1e-9)


def test_the_words_ride_the_file_and_keyless_records_rest():
    """Round trip: every word, the tool names and the distance ride
    the file and the reload replays the SAME envelope to the digit.
    A keyless record (hand-written, silent) lands the house rests -
    External, Box, Z-Axis, flip off, offset 0 - because the page
    prints no default and the .get pair defers to what the door
    rests at (R5's coin)."""
    d = _cube_doc()
    b, f = d.add_fluid_volume(["Body 1"], "Hemisphere",
                              direction="Y-Axis", flip=True, offset=2.5)
    v1 = d.body_solids()[b["name"]].volume
    raw = json.loads(json.dumps(d.to_dict()))
    d2 = Document.from_dict(raw)
    f2 = d2.features[-1]
    assert (f2.tools, f2.volume, f2.shape_type, f2.shape_direction,
            f2.flip, f2.offset) == (("Body 1",), "External",
                                    "Hemisphere", "Y-Axis", True, 2.5)
    assert d2.body_solids()[b["name"]].volume == pytest.approx(
        v1, rel=1e-12)
    for fd in raw["features"]:
        if fd["type"] == "FluidVolumeFeature":
            for k in ("volume", "shape_type", "shape_direction",
                      "flip", "offset"):
                fd.pop(k, None)
    d3 = Document.from_dict(raw)
    f3 = d3.features[-1]
    assert (f3.volume, f3.shape_type, f3.shape_direction, f3.flip,
            f3.offset) == ("External", "Box", "Z-Axis", False, 0.0)


def test_the_fold_refuses_a_lying_volume_and_a_missing_tool():
    """The guards are the fold's OWN mouth (m127's coin: a bare
    recompute RAISES - the badge is the UI's wrapper, not the
    kernel's mercy): a record that SAYS 'Internal' - which only a
    hand-written file can do, the reader takes it verbatim - is
    refused with the page's gate named, and a tool whose stream
    never built is refused by name. No silent empty body."""
    d = _cube_doc()
    b, f = d.add_fluid_volume(["Body 1"], "Box", offset=1.0)
    f.volume = "Internal"
    d.dirty = True
    with pytest.raises(ValueError) as e:
        d.recompute()
    assert "completely isolated interior" in str(e.value)
    d2 = _cube_doc()
    d2.add_body("liar")
    d2.add(FluidVolumeFeature(name="liar", body="liar",
                              tools=("Ghost",), shape_type="Box"))
    with pytest.raises(ValueError) as e2:
        d2.recompute()
    assert "Ghost" in str(e2.value)


def test_the_rail_speaks_the_envelope_line_and_only_the_living_words(
        win, qapp, monkeypatch):
    """The record's OWN rail line: the shape, the distance WEARING
    THE UNIT (offset is a DISTANCE - the UNIT-SUFFIX LAW's other
    edge), and the NAMED tools it envelopes. The gated pair speaks
    only where the page lets it: a stored direction under a BOX
    stays SILENT (stored-and-inert - a rail that spoke an inert word
    would contradict the shape), the same word under a Cylinder off
    its rest speaks, and the inversion line rides a flipped
    hemisphere alone (the page's own verb)."""
    win.new_document()
    _stage(win)
    qapp.processEvents()
    body = win.doc.body_list()[0]["name"]
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"tools": [body], "shape": "Box", "direction": "X-Axis",
         "offset": 1.0}, {}))
    win.action_fluid_volume()
    qapp.processEvents()
    win.rail.props.show_feature(win.doc.features[-1])
    txt = win.rail.props._body.text()
    assert "fluid: Box, offset 1 mm around Body 1" in txt
    assert "direction:" not in txt             # inert under Box: silent

    win.new_document()
    _stage(win, kind="cylinder", dims={"radius": 3.0, "height": 10.0})
    qapp.processEvents()
    body = win.doc.body_list()[0]["name"]
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"tools": [body], "shape": "Cylinder", "direction": "X-Axis",
         "offset": 0.0}, {}))
    win.action_fluid_volume()
    qapp.processEvents()
    win.rail.props.show_feature(win.doc.features[-1])
    txt = win.rail.props._body.text()
    assert "fluid: Cylinder, offset 0 mm around" in txt
    assert "direction: X-Axis" in txt          # alive under Cylinder

    win.new_document()
    _stage(win)
    qapp.processEvents()
    body = win.doc.body_list()[0]["name"]
    monkeypatch.setattr(cmddialog, "ask", _spy_ask(
        {"tools": [body], "shape": "Hemisphere", "flip": True,
         "offset": 0.0}, {}))
    win.action_fluid_volume()
    qapp.processEvents()
    win.rail.props.show_feature(win.doc.features[-1])
    txt = win.rail.props._body.text()
    assert "fluid: Hemisphere" in txt
    assert "hemisphere inverted" in txt


def test_the_lever_echoes_the_record_and_the_offset_mouth_wears_mm(
        win, qapp):
    """One record, one voice: the fluid feature opens ITS rows (page
    order, its own tools ticked) and Change Parameters writes the
    edited words back GUARDED - the offset through mm(), the door's
    other mouth (UNIT-SUFFIX LAW: a typed value in the document unit
    lands millimetres; the record below rests in mm and round-trips
    through the lever untouched)."""
    d_win = win
    d_win.new_document()
    _stage(d_win)
    qapp.processEvents()
    f = None
    d_win.doc.add_fluid_volume(["Body 1"], "Box", offset=1.0)
    d_win.doc.recompute()
    f = d_win.doc.features[-1]
    fields = d_win._feature_params(f)
    keys = [x["key"] for x in fields]
    assert keys == ["volume", "tools", "shape_type", "shape_direction",
                    "flip", "offset"]          # page order, its own voice
    checked = next(x for x in fields if x["key"] == "tools")
    assert checked["checked"] == ["Body 1"]
    d_win._apply_feature_params(f, {
        "volume": "External", "tools": ["Body 1"],
        "shape_type": "Cylinder", "shape_direction": "X-Axis",
        "flip": False, "offset": 2.0})
    assert (f.shape_type, f.shape_direction, f.flip,
            f.offset) == ("Cylinder", "X-Axis", False, 2.0)
    # the guarded coin: a legacy voice that never opened the rows
    # writes NOTHING back (the words stand) - the offset row is the
    # one unconditional lever every feature carries
    d_win._apply_feature_params(f, {"offset": 0.0})
    assert (f.shape_type, f.shape_direction, f.flip,
            f.offset) == ("Cylinder", "X-Axis", False, 0.0)
