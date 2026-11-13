"""M201 R14 - Combine grows the page's OWN body-to-body voice.

[SLD-REF-COMBINE, verbatim] "Combine joins, cuts, or intersects the
selected bodies." - "Target Body: Enables the selection of the body
being acted upon." (SINGULAR: ONE combo, never a check-list) and
"Tool Bodies: Enables the selection of the bodies that change the
model." (the licensed PLURAL - the named-body check-list bridge).
The Operation enum is the page's closed three words: Join | Cut |
Intersect.  "Keep Tools: Retains the tool bodies after the combine
results." - ON is that sentence; the page is machine-grepped SILENT
on the OFF fate, so the drop is OURS and says so at every mouth
(never "consumed" - that word is the vendor's silence).

"default" counts ZERO on both pages: keep-tools ON and the primitive
rests are HOUSE FACTS.  No Tool Bodies ticked, the door keeps its
legacy M64 voice (the map's valid subset) byte-stable; a named-body
record speaks its own voice in lever, rail and file alike.  Every
door refusal stands BEFORE the capture (the window owns the only
undo stack), so nothing is ever born.

Exact box arithmetic is the pin: two 2x2x2 boxes, one at the corner
of the other - Intersect keeps the unit cube (1), Cut leaves 7, Join
weighs 15.  No faceting tolerance rides a box gate.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                          # noqa: E402

from conftest import script_cmd, script_cmd_cancel                  # noqa: E402
from tracer.core.document import (CombineFeature, Document,         # noqa: E402
                                  PrimitiveFeature)
from tracer.ui import cmddialog                                     # noqa: E402
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
    cmddialog._REMEMBERED.pop("combine", None)


# ---- helpers ---------------------------------------------------------------

def _two_bodies(win):
    """Two REAL named bodies, registered before anything stages into
    them (R13's law note: the check-list row reads body_list()): two
    2x2x2 boxes, one at (0,0,0) one at (1,1,1) - the overlap is the
    unit cube, so Intersect 1, Cut 7, Join 15 are hand-checkable."""
    win.doc.add(PrimitiveFeature(name="a", kind="box",
                                 dims={"dx": 2.0, "dy": 2.0,
                                       "dz": 2.0}))
    win.doc.add_body("Body 2")
    win.doc.add(PrimitiveFeature(name="b", kind="box",
                                 dims={"dx": 2.0, "dy": 2.0,
                                       "dz": 2.0},
                                 placement=(1.0, 1.0, 1.0)))
    win.doc.dirty = True
    win.doc.recompute()


def _pair():
    """Kernel twin: bodies A and B, same exact arithmetic, no Qt."""
    d = Document("cbd")
    d.add_body("A")
    d.add(PrimitiveFeature(name="a", kind="box",
                           dims={"dx": 2.0, "dy": 2.0, "dz": 2.0}))
    d.add_body("B")
    d.add(PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 2.0, "dy": 2.0, "dz": 2.0},
                           placement=(1.0, 1.0, 1.0)))
    return d


def _spy_cancel(store):
    def _ask(parent, title, fields, remember_key=None):
        store["keys"] = [f["key"] for f in fields]
        store["kinds"] = {f["key"]: f["kind"] for f in fields}
        store["choices"] = {f["key"]: tuple(f.get("choices", ()))
                            for f in fields if f["kind"] == "combo"}
        store["defaults"] = {f["key"]: f.get("default") for f in fields}
        return None
    return _ask


# ---- the door: the page's rows, in the page's order -------------------------

def test_the_door_asks_the_pages_rows_and_nothing_is_born_on_cancel(
        win, qapp, monkeypatch):
    """The spy sees the real field list: Target Body (combo - ONE
    body, the page's SINGULAR), Tool Bodies (the licensed PLURAL on
    the check-list), Operation (the closed three words), Keep Tools
    (the page's own sentence; its ON rest is a HOUSE FACT - the
    page prints no default).  M201 R29 grew the page's fifth row in
    printed order, so New Component now rides between Operation and
    Keep Tools (test_m217 owns its semantics).  Cancel: nothing is
    born."""
    _two_bodies(win)
    qapp.processEvents()
    store = {}
    monkeypatch.setattr(cmddialog, "ask", _spy_cancel(store))
    before = len(win.doc.features)
    win.action_combine()
    qapp.processEvents()
    assert store["keys"][:5] == ["target", "tools", "op", "newcomp",
                                 "keep"]
    assert store["kinds"]["target"] == "combo"
    assert store["kinds"]["tools"] == "checks"
    assert store["kinds"]["keep"] == "check"
    assert store["kinds"]["newcomp"] == "check"
    assert store["choices"]["op"] == ("Join", "Cut", "Intersect")
    assert set(store["choices"]["target"]) == {"Body 1", "Body 2"}
    assert store["defaults"]["keep"] is True           # ours, named
    assert store["defaults"]["newcomp"] is False       # R29's house rest
    assert len(win.doc.features) == before


def test_combine_body_to_body_is_boolean_truth_through_the_door(
        win, qapp, monkeypatch):
    """Intersect keeps the unit cube: 1 mm^3, measured and spoken;
    the tool is RETAINED (the page's own sentence, so the status
    says nothing extra); the record speaks the body voice."""
    _two_bodies(win)
    qapp.processEvents()
    script_cmd(monkeypatch, {"target": "Body 1", "tools": ["Body 2"],
                             "op": "Intersect", "keep": True})
    win.action_combine()
    qapp.processEvents()
    sol = win.doc.body_solids()
    assert sol["Body 1"].volume == pytest.approx(1.0, abs=1e-6)
    assert sol["Body 2"].volume == pytest.approx(8.0, abs=1e-6)
    assert win.status.currentMessage() == (
        "Combined (Intersect) Body 1 with Body 2 \u2014 1 mm\u00b3")
    feat = win.doc.features[-1]
    assert isinstance(feat, CombineFeature)
    assert feat.tool_bodies == ("Body 2",) and feat.op == "intersect"


@pytest.mark.parametrize("op,want", [("Intersect", 1.0), ("Cut", 7.0),
                                     ("Join", 15.0)])
def test_the_three_page_operations_are_the_pages_arithmetic(
        win, qapp, monkeypatch, op, want):
    """"Combine joins, cuts, or intersects" - the closed enum is
    exactly the arithmetic: 8 - 1 = 7 (Cut), 8 + 8 - 1 = 15 (Join),
    the overlap 1 (Intersect).  A fourth word has no meaning and no
    home."""
    _two_bodies(win)
    qapp.processEvents()
    script_cmd(monkeypatch, {"target": "Body 1", "tools": ["Body 2"],
                             "op": op, "keep": True})
    win.action_combine()
    qapp.processEvents()
    assert win.doc.body_solids()["Body 1"].volume == pytest.approx(
        want, abs=1e-6)


def test_keep_tools_off_is_our_fate_and_says_whose_word_it_is(
        win, qapp, monkeypatch):
    """The page is machine-grepped SILENT on what OFF does, so the
    tool's stream is dropped (ours) and the status names itself as
    ours at the mouth - never "consumed"."""
    _two_bodies(win)
    qapp.processEvents()
    script_cmd(monkeypatch, {"target": "Body 1", "tools": ["Body 2"],
                             "op": "Cut", "keep": False})
    win.action_combine()
    qapp.processEvents()
    sol = win.doc.body_solids()
    assert sol["Body 1"].volume == pytest.approx(7.0, abs=1e-6)
    assert "Body 2" not in sol                 # the house fate
    msg = win.status.currentMessage()
    assert "the tools are not retained (ours: the page prints no " \
           "fate)" in msg
    assert win.doc.features[-1].keep_tools is False


# ---- refusals: BEFORE the capture, nothing is born --------------------------

@pytest.mark.parametrize("reply,word", [
    ({"target": "Body 1", "tools": ["Body 2"], "op": "Merge"},
     "the operation is 'Join', 'Cut' or 'Intersect', not 'Merge'"),
    ({"target": "Ghost", "tools": ["Body 2"], "op": "Cut"},
     "the Target Body is 'the body being acted upon' and 'Ghost' "
     "is not a body"),
    ({"target": "Body 1", "tools": ["Body 1"], "op": "Join"},
     "'Body 1' is the body being acted upon - it cannot also "
     "change the model"),
    ({"target": "Body 1", "tools": ["Ghost"], "op": "Join"},
     "tool body 'Ghost' is not a body"),
])
def test_a_refusal_leaves_nothing_behind(win, qapp, monkeypatch,
                                         reply, word):
    """Every door refusal speaks BEFORE the capture: no record, no
    undo step, no changed solid - the window owns the only stack."""
    _two_bodies(win)
    qapp.processEvents()
    script_cmd(monkeypatch, reply)
    before = (len(win.doc.features),
              win.doc.body_solids()["Body 1"].volume)
    win.action_combine()
    qapp.processEvents()
    assert word in win.status.currentMessage()
    assert "refused" in win.status.currentMessage()
    after = win.doc.body_solids()["Body 1"].volume
    assert (len(win.doc.features), after) == before
    assert not any(isinstance(f, CombineFeature)
                   for f in win.doc.features)


def test_cancel_changes_nothing(win, qapp, monkeypatch):
    _two_bodies(win)
    qapp.processEvents()
    script_cmd_cancel(monkeypatch)
    before = len(win.doc.features)
    win.action_combine()
    qapp.processEvents()
    assert len(win.doc.features) == before


# ---- the legacy M64 voice stays byte-stable ---------------------------------

def test_the_primitive_voice_survives_untouched(win, qapp, monkeypatch):
    """No Tool Bodies ticked (the raw legacy reply never carries the
    key): the M64 sentence is byte-kept, the record keeps its
    primitive voice, the rail still prints the size rows."""
    _two_bodies(win)
    qapp.processEvents()
    script_cmd(monkeypatch, {"tool": "Box", "dx": 2.0, "dy": 2.0,
                             "dz": 2.0, "op": "Join", "cx": 1.0,
                             "cy": 1.0, "cz": 1.0})
    win.action_combine()
    qapp.processEvents()
    assert win.status.currentMessage() == (
        "Combined (join) a box into the body")
    feat = win.doc.features[-1]
    assert feat.tool_bodies == () and feat.keep_tools is True
    win.rail.props.show_feature(feat)
    txt = win.rail.props._body.text()
    assert "combine \u2295 join a box" in txt
    assert "tool:" in txt and "tool centre:" in txt
    assert "not retained" not in txt


# ---- the kernel: one boolean mouth, named refusals, the file pair -----------

@pytest.mark.parametrize("op,want", [("intersect", 1.0),
                                     ("subtract", 7.0),
                                     ("union", 15.0)])
def test_the_boolean_mouth_is_exact(op, want):
    d = _pair()
    d.add(CombineFeature(name="c", op=op, tool_bodies=("B",),
                         body="A"))
    d.recompute()
    sol = d.body_solids()
    assert sol["A"].volume == pytest.approx(want, abs=1e-6)
    assert sol["B"].volume == pytest.approx(8.0, abs=1e-6)


def test_keep_off_drops_the_tool_stream_in_the_fold():
    d = _pair()
    d.add(CombineFeature(name="c", op="subtract", tool_bodies=("B",),
                         keep_tools=False, body="A"))
    d.recompute()
    assert "B" not in d.body_solids()
    assert d.body_solids()["A"].volume == pytest.approx(7.0, abs=1e-6)


def test_the_fold_refuses_by_name():
    d = _pair()
    d.add(CombineFeature(name="c", op="union", tool_bodies=("A",),
                         body="A"))
    with pytest.raises(ValueError,
                       match="cannot also change the model"):
        d.recompute()
    d2 = _pair()
    d2.add(CombineFeature(name="c", op="union",
                          tool_bodies=("Ghost",), body="A"))
    with pytest.raises(ValueError,
                       match="has nothing to combine with yet"):
        d2.recompute()


def test_the_file_pair_carries_the_body_voice_and_the_rests_our_own():
    d = _pair()
    d.add(CombineFeature(name="c", op="union", tool_bodies=("B",),
                         keep_tools=False, body="A"))
    raw = d.to_dict()
    fd = [x for x in raw["features"]
          if x["type"] == "CombineFeature"][0]
    assert fd["tool_bodies"] == ["B"] and fd["keep_tools"] is False
    d2 = Document.from_dict(raw)
    d2.recompute()
    assert "B" not in d2.body_solids()
    assert d2.body_solids()["A"].volume == pytest.approx(15.0,
                                                         abs=1e-6)
    # A file written BEFORE R14 carries neither key: the rests keep
    # it the primitive voice it always spoke (byte-stable legacy).
    fd.pop("tool_bodies")
    fd.pop("keep_tools")
    d3 = Document.from_dict(raw)
    leg = [f for f in d3.features if isinstance(f, CombineFeature)][0]
    assert leg.tool_bodies == () and leg.keep_tools is True
    assert leg.tool == "box"


# ---- the lever: records speak their own voice, guarded ----------------------

def test_the_lever_opens_the_rows_of_the_records_own_voice(win):
    _two_bodies(win)
    body = win.doc.add(CombineFeature(name="c", op="intersect",
                                      tool_bodies=("Body 2",),
                                      body="Body 1"))
    prim = CombineFeature(name="p", tool="box", op="union",
                          dims={"dx": 2.0, "dy": 2.0, "dz": 2.0},
                          center=(1.0, 1.0, 1.0), body="Body 1")
    win.doc.features.append(prim)
    kb = {f["key"]: f for f in win._feature_params(body)}
    assert set(("tools", "op", "keep")) <= set(kb)
    assert "dx" not in kb and "tool" not in kb
    assert kb["tools"]["checked"] == ["Body 2"]
    kp = {f["key"]: f for f in win._feature_params(prim)}
    assert set(("tool", "op", "dx", "c0")) <= set(kp)
    assert "tools" not in kp and "keep" not in kp


def test_the_lever_writes_guarded(win):
    """The body voice writes tools/keep ONLY when the reply carries
    them (an op-only lever answer must not erase the check-list or
    stomp the flag); the op map rides BOTH voices; the primitive
    rows are never read on a body record."""
    _two_bodies(win)
    feat = win.doc.add(CombineFeature(name="c", op="intersect",
                                      tool_bodies=("Body 2",),
                                      body="Body 1"))
    win._apply_feature_params(feat, {"op": "Cut",
                                     "tools": ["Body 2"],
                                     "keep": False})
    assert feat.op == "subtract" and feat.tool_bodies == ("Body 2",)
    assert feat.keep_tools is False
    win._apply_feature_params(feat, {"op": "Join"})
    assert feat.op == "union" and feat.tool_bodies == ("Body 2",)
    assert feat.keep_tools is False          # rests honored, not 0


# ---- the rail: one record, one voice ----------------------------------------

def test_the_rail_speaks_the_body_voice(win):
    _two_bodies(win)
    feat = win.doc.add(CombineFeature(name="c", op="intersect",
                                      tool_bodies=("Body 2",),
                                      body="Body 1"))
    win.rail.props.show_feature(feat)
    txt = win.rail.props._body.text()
    assert "combine \u2295 Intersect with Body 2" in txt
    assert "tool:" not in txt            # the size rows are the
    assert "not retained" not in txt     # OTHER voice's lines
    feat.keep_tools = False
    win.rail.props.show_feature(feat)
    txt = win.rail.props._body.text()
    assert "tools not retained (ours: the page prints no fate)" \
        in txt
