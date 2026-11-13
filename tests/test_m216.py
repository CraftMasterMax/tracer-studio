"""M201 R28 - the Center of Mass datum [GUID-EB8C9FD9, double-verified].

The page (banked insp28, re-verified byte-exact by insp29verify) prints:
path "Design > Inspect > Center of Mass"; "Displays a glyph at the
location of the Center of Mass for the selected object or objects.";
"The Center of Mass is also associative, so if you change the geometry
of your model, the Center of Mass will update accordingly"; "Click OK.";
and "Click to select the center of mass to display its coordinates in
the global coordinate system."  It prints NO dialog-callout line, NO
Default:, NO ' mm', NO Cancel - every one of those absences verified
0-hits twice.  So: the dialog title is a HOUSE STAMP ("Center of Mass"),
the selection row is the page's Objects step wearing our ONE honest
member ("The design (all solid bodies)" - the page asks for components
or solid bodies, our design is both), and ' mm' on the status line is a
declared stamp while the tail sentence is verbatim.  Associativity is
architecture, not a promise: the record stores ONLY its name and
com_points() re-measures the live result solid every refresh.  The
page's click-to-select step is declared house behavior - our glyph is
not clickable yet, so the coordinates ride at placement instead; that
is why the door speaks the sentence the page reserves for a click, and
why rename_datum stays closed to coms (page prints only Hide/Show and
Delete for the browser node - no Rename).
UNOFFERED-BY-NAME (declared, named): the Analysis-folder browser node
with its Hide/Show and Delete verbs, and measuring a SELECTED SUBSET
from the COM - the page's selection machinery has no second member in
this kernel."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QToolButton             # noqa: E402

from tracer.core.document import Document, PrimitiveFeature          # noqa: E402
from tracer.ui import cmddialog, icons                               # noqa: E402
from tracer.ui.mainwindow import MainWindow                          # noqa: E402
from tracer.ui.renderer import SceneRenderer                         # noqa: E402


def _box(d, at=(10.0, 5.0, 0.0)):
    """A 2x2x2 lug — min-corner placement law, so its centroid is the
    honest arithmetic (10+1, 5+1, 0+1) = (11, 6, 1)."""
    f = PrimitiveFeature(name="lug", kind="box",
                         dims={"dx": 2, "dy": 2, "dz": 2},
                         placement=at)
    d.add(f)
    d.recompute()
    return f


# ---- the document layer: name-only records, live numbers ------------

def test_record_is_name_only_and_naming_is_sequential():
    d = Document()
    c1 = d.add_com()
    assert c1 == {"name": "Center of Mass 1"}       # NOTHING else — the
    c2 = d.add_com()                                #   datum is associative
    assert c2 == {"name": "Center of Mass 2"}
    assert [c["name"] for c in d.coms] == ["Center of Mass 1",
                                           "Center of Mass 2"]


def test_glyph_is_associative_by_construction():
    d = Document()
    f = _box(d)
    d.add_com()
    pts = d.com_points()
    assert len(pts) == 1
    assert pts[0]["point"] == pytest.approx([11.0, 6.0, 1.0])
    # the vendor sentence made flesh: change the geometry, the Center of
    # Mass updates — same record, no re-placing, no stored numbers:
    f.placement = (20.0, 5.0, 0.0)
    d.recompute()
    pts = d.com_points()
    assert pts[0]["point"] == pytest.approx([21.0, 6.0, 1.0])


def test_no_solid_no_points_and_removal_answers():
    d = Document()
    c = d.add_com()
    assert d.com_points() == []                     # nothing to measure —
    assert d.remove_com(c["name"]) is True          #   the glyph simply
    assert d.remove_com("Center of Mass 47") is False   # isn't there
    assert d.coms == []


def test_round_trip_survives_and_pre_r28_files_load():
    d = Document()
    _box(d)
    d.add_com()
    d.add_com()
    data = d.to_dict()
    assert data["coms"] == [{"name": "Center of Mass 1"},
                            {"name": "Center of Mass 2"}]
    d2 = Document.from_dict(data)
    assert [c["name"] for c in d2.coms] == ["Center of Mass 1",
                                            "Center of Mass 2"]
    d2.recompute()
    assert d2.com_points()[0]["point"] == pytest.approx([11.0, 6.0, 1.0])
    del data["coms"]                                # a pre-R28 file has
    d3 = Document.from_dict(data)                   #   no key at all
    assert d3.coms == []


# ---- the door --------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(cmddialog, "_REMEMBERED", {})   # process-global
    monkeypatch.setattr(cmddialog, "_REMEMBER_ON", {})
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _capture(win, monkeypatch):
    calls = []
    monkeypatch.setattr(cmddialog, "ask",
                        lambda p, t, fl, **k: (calls.append(
                            (t, [(f["key"], f["label"],
                                  f.get("choices")) for f in fl])),
                            None)[1])
    return calls


def test_the_door_wears_one_honest_row(win, monkeypatch):
    calls = _capture(win, monkeypatch)
    win.new_document()
    _box(win.doc)
    win.action_center_of_mass()
    (title, rows), = calls
    # house-stamped title (the page prints NO dialog-callout line —
    # 0 hits, double-verified) and exactly ONE row: the page's Objects
    # selection step wearing our one honest member.  No Type row, no
    # Default: line, no unit suffix on the label — none exist upstream.
    assert title == "Center of Mass"
    assert len(rows) == 1
    assert rows[0] == ("objects", "Objects", None)


def test_empty_design_refuses_with_the_cure_words(win, monkeypatch):
    calls = _capture(win, monkeypatch)
    win.new_document()                              # no feature yet
    win.action_center_of_mass()
    assert calls == []                              # no dialog to cancel
    assert win.status.currentMessage() == \
        "Nothing to measure yet — add a feature first"
    assert win.doc.coms == []


def test_placement_records_names_and_speaks_the_page(win, monkeypatch):
    # the click step's PROMISE rides at placement (declared house
    # behavior): the page's verbatim tail sentence on the status line.
    monkeypatch.setattr(cmddialog, "ask",
                        lambda p, t, fl, **k: {f["key"]: f["default"]
                                               for f in fl})
    win.new_document()
    _box(win.doc)
    win.action_center_of_mass()
    assert [c["name"] for c in win.doc.coms] == ["Center of Mass 1"]
    msg = win.status.currentMessage()
    assert msg.startswith("Center of Mass 1 at (+11.00, +6.00, +1.00)")
    assert msg.endswith("coordinates in the global coordinate system")
    # and the canvas glyph is there, fed from the LIVE solid:
    coms = win._renderer._coms
    assert len(coms) == 1
    assert coms[0]["name"] == "Center of Mass 1"
    assert coms[0]["point"] == pytest.approx([11.0, 6.0, 1.0])


def test_mouths_menu_ribbon_and_glyph(win):
    entries = [a.text() for a in win.menuBar().actions()
               for a in (a.menu().actions() if a.menu() else [])]
    assert "Center of Mass…" in entries             # Tools menu mouth
    tips = [b.toolTip() for b in win.findChildren(QToolButton)]
    assert "Center of Mass — associative balance-point glyph" in tips
    assert not icons.icon("com").isNull()           # the quartered disc
