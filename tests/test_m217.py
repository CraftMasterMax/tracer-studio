"""M201 R29 - the Combine door now wears the WHOLE reference page.

[SLD-REF-COMBINE, verbatim, byte-identical live re-read combine29] the
page prints six rows in this order: Target Body, Tool Bodies,
Operation (Join | Cut | Intersect), Objects To Cut (its nested h3:
Auto-Select | # Bodies), New Component, Keep Tools. R14 wore the first
three plus Keep Tools; R29 grows the fifth: "New Component: Creates a
new component with the results." - row order is the PAGE's order
(between Operation and Keep Tools, never after Keep Tools). A body is
this kernel's component (R14's own reading), the fresh body is
allocated at placement (the mirror's New Body pattern), and the page
prints NO fate for the target when the result is re-homed - the target
standing is OURS and every mouth says so. Objects To Cut stays
UNOFFERED-BY-NAME: its gate ("only for cut operations... only active
when you edit operations") is edit-time recompute of Hybrid Design
bodies, machinery this kernel has no mouth for; the row AND both
members are declared, never worn as decoration. "default" counts 0 on
both Combine pages: New Component's OFF rest is a house rest, and so
was keep-tools' ON (R14). M31: the member-carrying row is Operation -
no Type row exists on the page, and the door wears none. M27: result
node names stay ours ("Combine <target>", "Body N") - no vendor
result-node name is invented."""
import inspect
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                          # noqa: E402

from tracer.core.document import Document, PrimitiveFeature, \
    CombineFeature                                                   # noqa: E402
from tracer.ui import cmddialog                                     # noqa: E402
from tracer.ui.mainwindow import MainWindow                         # noqa: E402
from tracer.ui.renderer import SceneRenderer                        # noqa: E402


def _mouth(fn):
    return " ".join(inspect.getsource(fn).split())


def _two_body_doc():
    """Body 1: 10x10x10 at the origin; Body 2: the same shifted +5 x.
    Join overlap arithmetic the film can re-measure: union = 1500."""
    d = Document()
    d.add(PrimitiveFeature(name="stub", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10}))
    b2 = d.add_body()["name"]
    d.add(PrimitiveFeature(name="lump", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10},
                           placement=(5, 0, 0), body=b2))
    d.recompute()
    return d, b2


# ---- the record layer ----------------------------------------------------------

def test_new_component_rehomes_the_result_and_the_target_stands():
    d, b2 = _two_body_doc()
    nb = d.add_body()["name"]
    assert nb == "Body 3"                            # ledger naming (M27)
    d.add(CombineFeature(name="Combine Body 1", op="union",
                         tool_bodies=(b2,), keep_tools=True,
                         body="Body 1", new_component=True,
                         result_body=nb))
    d.recompute()
    sols = d.body_solids()
    assert sols[nb].volume == pytest.approx(1500.0)  # the RESULTS (page)
    assert sols["Body 1"].volume == pytest.approx(1000.0)
    #  ^ page-silence made explicit: the target fate we DECLARED, in
    #    the door's own voice - never quoted as the vendor's
    assert sols[b2].volume == pytest.approx(1000.0)  # Keep Tools ON


def test_incomplete_records_refuse_with_the_page_voice():
    d = Document()
    d.add(PrimitiveFeature(name="p", kind="box",
                           dims={"dx": 2, "dy": 2, "dz": 2}))
    d.recompute()
    d.add(CombineFeature(name="bad", op="union", body="Body 1",
                         new_component=True, result_body=""))
    with pytest.raises(ValueError, match="no result body"):
        d.recompute()
    e = Document()
    e.add(PrimitiveFeature(name="p", kind="box",
                           dims={"dx": 2, "dy": 2, "dz": 2}))
    e.recompute()
    e.add(CombineFeature(name="bad2", op="union", body="Body 1",
                         new_component=True, result_body="Body 1"))
    with pytest.raises(ValueError, match="cannot be"):
        e.recompute()


def test_round_trip_carries_the_row_and_pre_r29_files_load():
    d, b2 = _two_body_doc()
    nb = d.add_body()["name"]
    d.add(CombineFeature(name="Combine Body 1", op="union",
                         tool_bodies=(b2,), body="Body 1",
                         new_component=True, result_body=nb))
    data = d.to_dict()
    rec = next(f for f in data["features"] if f["name"] == "Combine Body 1")
    assert rec["new_component"] is True and rec["result_body"] == nb
    d2 = Document.from_dict(data)
    d2.recompute()
    assert d2.body_solids()[nb].volume == pytest.approx(1500.0)
    for f in data["features"]:                       # a pre-R29 file:
        f.pop("new_component", None)                 #   keys absent ->
        f.pop("result_body", None)                   #   honest False
    d3 = Document.from_dict(data)
    d3.recompute()                                   # legacy streams win
    assert d3.body_solids()["Body 1"].volume == pytest.approx(1500.0)


# ---- the door ------------------------------------------------------------------

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
                            (t, [(f["key"], f["label"], f.get("kind"))
                                 for f in fl])), None)[1])
    return calls


def test_the_rows_wear_the_page_order_no_type_no_objects_to_cut(win,
                                                                monkeypatch):
    calls = _capture(win, monkeypatch)
    win.new_document()
    _two_body_doc_into(win)
    win.action_combine()
    (title, rows), = calls
    assert title == "Combine"
    first5 = [(k, l) for k, l, _kind in rows[:5]]
    assert first5 == [("target", "Target Body"), ("tools", "Tool Bodies"),
                      ("op", "Operation"), ("newcomp", "New Component"),
                      ("keep", "Keep Tools")]              # PAGE order
    assert rows[3][2] == "check"                           # a checkbox row
    labels = [l for _k, l, _kind in rows]
    assert "Type" not in labels                            # M31
    assert "Objects To Cut" not in labels                  # UNOFFERED-BY-NAME
    assert not any(m in labels for m in ("Auto-Select", "# Bodies"))


def _two_body_doc_into(win):
    """The house pattern (test_m202._two_bodies): build ON the window's
    live doc after new_document() — no wholesale doc swap.  Same
    arithmetic as _two_body_doc(): 10x10x10 boxes 5 mm apart in x, so
    Join 1500, Cut 500 are hand-checkable."""
    win.doc.add(PrimitiveFeature(name="stub", kind="box",
                                 dims={"dx": 10.0, "dy": 10.0,
                                       "dz": 10.0}))
    b2 = win.doc.add_body("Body 2")["name"]
    win.doc.add(PrimitiveFeature(name="lump", kind="box",
                                 dims={"dx": 10.0, "dy": 10.0,
                                       "dz": 10.0},
                                 placement=(5.0, 0.0, 0.0)))
    win.doc.dirty = True
    win.doc.recompute()
    return b2


def test_new_component_lands_through_the_door_own_answer(win, monkeypatch):
    win.new_document()
    b2 = _two_body_doc_into(win)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "target": "Body 1", "tools": [b2], "op": "Join",
        "newcomp": True, "keep": True})
    win.action_combine()
    names = [b["name"] for b in win.doc.body_list()]
    assert "Body 3" in names                              # allocated fresh
    feat = win.doc.features[-1]
    assert feat.new_component and feat.result_body == "Body 3"
    assert feat.body == "Body 1"                          # stream: target
    sols = win.doc.body_solids()
    assert sols["Body 3"].volume == pytest.approx(1500.0)
    assert sols["Body 1"].volume == pytest.approx(1000.0)
    msg = win.status.currentMessage()
    assert "result is Body 3" in msg
    assert "ours: the page prints no fate for the target" in msg


def test_the_rest_stays_the_r14_world(win, monkeypatch):
    win.new_document()
    b2 = _two_body_doc_into(win)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "target": "Body 1", "tools": [b2], "op": "Join",
        "newcomp": False, "keep": True})
    win.action_combine()
    assert [b["name"] for b in win.doc.body_list()] == ["Body 1", b2]
    sols = win.doc.body_solids()                          # NOTHING re-homed
    assert sols["Body 1"].volume == pytest.approx(1500.0)
    assert "New Component" not in win.status.currentMessage()


def test_keep_off_and_new_component_honest_together(win, monkeypatch):
    win.new_document()
    b2 = _two_body_doc_into(win)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "target": "Body 1", "tools": [b2], "op": "Cut",
        "newcomp": True, "keep": False})
    win.action_combine()
    sols = win.doc.body_solids()
    assert sols["Body 3"].volume == pytest.approx(500.0)   # the OUTSIDE
    #   half of the overlap: Body 1 minus tool = 1000 - 500
    assert sols["Body 1"].volume == pytest.approx(1000.0)  # stands
    assert b2 not in sols or sols.get(b2) is None          # tools dropped
    msg = win.status.currentMessage()
    assert "result is Body 3" in msg and "not retained" in msg


def test_the_mouth_quotes_the_page_and_declares_our_silence():
    mouth = _mouth(MainWindow.action_combine)
    # the page's fifth row, verbatim:
    assert '"New Component: Creates a new component with the results."' \
        in mouth
    # Objects To Cut named UNOFFERED with its own words and members:
    assert "Objects To Cut" in mouth and "UNOFFERED" in mouth
    for frag in ("Auto-Select", "# Bodies", "edit-time"):
        assert frag in mouth
    # our silence, named as ours:
    assert "prints NO fate" in mouth
    # M31 + M27 read as law, not decoration:
    assert "M31" in mouth and "M27" in mouth
