"""M201 R18 - the As-Built Joint door wears the pages' words.

[ASM-CREATE-AS-BUILT-JOINT + AS-BUILT-JOINT-REFERENCE, verbatim]
"The As-Built Joint dialog displays." ... "Select two components to
position an as-built joint between them."  The Motion section's
table prints SEVEN Joint Types; only Rigid is offered - its
definition is the only one the kernel bakes: "Locks components
together and removes all degrees of freedom." (Rotation/Translation:
None).  THE PAGES GATE THE REST AWAY THEMSELVES: "For any Joint Type
except Rigid, select a Mode" - so the Mode trio and the "Planes,
Edges, and Snap" block never appear for Rigid; and the limits row is
"available when you have selected a Joint Type that has more than one
degree of motion" - Rigid has ZERO, so Motion/Minimum/Maximum/Rest/
Preview/With All Limits stand gated off by the vendor's own sentence.
Rows speak BODIES (the kernel has no components yet - a door may not
name a thing the design has not got).  VENDOR DEFECT flagged, not
cloned: the glosses print "in relation to each another".
"""
import contextlib
from pathlib import Path

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
    """A door that only-inspect tests never runs past ask(): the
    capturing fake records the FIELDS and stops the build."""


def _capture_asks(monkeypatch):
    calls = []

    def fake_ask(parent, title, fields, remember_key=None):
        calls.append((title, fields))
        raise _Stop
    monkeypatch.setattr(cmddialog, "ask", fake_ask)
    return calls


def _open(win):
    with contextlib.suppress(_Stop):
        win.action_joint()


def _two_bodies(win):
    win.new_document()
    d = win.doc
    d.add_body("A")
    d.add(PrimitiveFeature(name="boxA", kind="box",
                           dims={"dx": 5, "dy": 5, "dz": 5}))
    d.add_body("B")
    d.add(PrimitiveFeature(name="boxB", kind="box", dims={"dx": 5, "dy": 5,
                                                          "dz": 5},
                           placement=(12.0, 0.0, 0.0)))
    win.recompute()
    return d


# ---- the mouth ---------------------------------------------------------

def test_the_dialog_wears_the_pages_name(win, monkeypatch):
    """"The As-Built Joint dialog displays." - the title IS the tool
    word; the merged era's "Joint - As-Built Rigid" is gone."""
    _two_bodies(win)
    calls = _capture_asks(monkeypatch)
    _open(win)
    assert len(calls) == 1 and calls[0][0] == "As-Built Joint"


def test_the_tools_menu_renamed_the_mouth(win):
    tools = None
    for a in win.menuBar().actions():
        if a.text().replace("&", "") == "Tools":
            tools = a.menu()
    assert tools is not None, [a.text() for a in win.menuBar().actions()]
    items = [a.text() for a in tools.actions()]
    assert "As-Built Joint…" in items, items
    assert not any("Joint — rigid" in t for t in items)


def test_one_body_refuses_by_the_tools_word(win):
    """The page opens with two components; a lone body cannot compose
    a joint - and the refusal says the TOOL's word."""
    win.new_document()
    win.action_joint()
    assert win.status.currentMessage().startswith(
        "As-Built Joint needs two bodies")
    assert win.doc.joints == []


# ---- the sections the page composes -------------------------------------

def test_the_components_section_binds_two_body_choices(win, monkeypatch):
    """"Select two components to position an as-built joint between
    them." - our door asks by COMBOS (no canvas picker yet) and the
    rows speak BODIES, because the kernel has no components."""
    _two_bodies(win)
    calls = _capture_asks(monkeypatch)
    _open(win)
    fields = calls[0][1]
    combos = [f for f in fields if f["key"] in ("base", "mover")]
    assert [f["label"] for f in combos] == ["Base body", "Moving body"]
    assert all(f["group"] == "Components" for f in combos)
    assert not any("component" in f["label"].lower() for f in fields)


def test_the_motion_section_offers_only_the_bakeable_type(win, monkeypatch):
    """The table's SEVEN become one honest choice: Rigid - "Locks
    components together and removes all degrees of freedom."
    (Rotation/Translation: None).  The six solved types need
    joint-origin geometry and a solver the kernel does not have."""
    _two_bodies(win)
    calls = _capture_asks(monkeypatch)
    _open(win)
    jt = next(f for f in calls[0][1] if f["key"] == "type")
    assert jt["label"] == "Joint Type"
    assert jt["group"] == "Motion"
    assert jt["choices"] == ["Rigid"]
    assert jt["default"] == "Rigid"        # a STAMPED rest (no default
    # prints on any joint dialog page - verified family-wide)


def test_the_gated_sections_are_invisible(win, monkeypatch):
    """Not one Mode row, not one Planes/Edges/Snap picker, not one
    limits row - the page gates ALL of them away for Rigid, so the
    door shows none and invents nothing."""
    _two_bodies(win)
    calls = _capture_asks(monkeypatch)
    _open(win)
    fields = calls[0][1]
    words = {f["key"] for f in fields} | {f["label"] for f in fields}
    for forbidden in ("Mode", "Simple", "Between Two Faces",
                      "Two Edge Intersection", "Plane 1", "Plane 2",
                      "Edge 1", "Edge 2", "Snap", "Minimum", "Maximum",
                      "Rest", "Preview", "With All Limits", "Rotate",
                      "Slide", "Axis", "Normal", "Pitch", "Yaw",
                      "Roll"):
        assert forbidden not in words, f"{forbidden} leaked past a gate"
    assert "Motion" not in {f["label"] for f in fields}   # limits row


def test_a_scripted_unbakeable_type_refuses_before_the_capture(
        win, monkeypatch):
    """The combo cannot show it, a scripted reply can fake it: a Revolute
    answer lands NOTHING - no record, no undo step paid."""
    d = _two_bodies(win)
    script_cmd(monkeypatch, {"base": "A", "mover": "B",
                             "type": "Revolute", "ground": True})
    depth = len(win._undo)
    win.action_joint()
    assert d.joints == []
    assert len(win._undo) == depth
    assert "only Joint Type the kernel locks is Rigid" in \
        win.status.currentMessage()


# ---- the record voice below the mouth -------------------------------------

def test_the_rigid_record_and_folder_survive_the_rename(win, monkeypatch):
    """Byte-honest regression: the renamed door lands the SAME M146
    record (kind rigid, a/b ids) and the joint displays in the
    browser's Joints folder - the page's home for it."""
    d = _two_bodies(win)
    script_cmd(monkeypatch, {"base": "A", "mover": "B", "type": "Rigid",
                             "ground": True})
    win.action_joint()
    assert len(d.joints) == 1
    j = d.joints[0]
    assert j["kind"] == "rigid"
    assert d._body_by_id(j["a"])["name"] == "A"
    assert d._body_by_id(j["b"])["name"] == "B"
    win.rail.tree.reload()
    texts = []

    def walk(it):
        for i in range(it.childCount()):
            c = it.child(i)
            texts.append(c.text(0))
            walk(c)
    walk(win.rail.tree.invisibleRootItem())
    assert any(t.startswith("Joints (") for t in texts), texts
    assert "position captured" in win.status.currentMessage()


def test_the_old_record_keys_still_answer(win, monkeypatch):
    """The tip says the two picks may arrive IN ANY ORDER - either
    body may enter either combo; the record simply points the other
    way this time (mover follows base is the LAW R voice)."""
    d = _two_bodies(win)
    script_cmd(monkeypatch, {"base": "B", "mover": "A", "ground": True})
    win.action_joint()
    assert len(d.joints) == 1
    assert d._body_by_id(d.joints[0]["b"])["name"] == "A"


# ---- the declarations, pinned at the mouth --------------------------------

def test_the_gate_sentences_are_quoted_verbatim_in_the_doc():
    """The door's restraint cites its license: the two vendor gate
    sentences and the Rigid definition live in the docstring word
    for word, the component-vs-body honesty stands declared, and the
    DEFECT ("in relation to each another") is flagged - never
    cloned into any row."""
    doc = " ".join(MainWindow.action_joint.__doc__.split())
    assert "For any Joint Type except Rigid, select a Mode" in doc
    assert "more than one degree of motion" in doc
    assert "Locks components together and removes all degrees of " \
           "freedom." in doc
    assert "ROWS SPEAK BODIES" in doc
    assert "each another" in doc and "DEFECT" in doc
    # the typo is cited EXACTLY once in the whole method - inside the
    # DEFECT flag - and never cloned into a row, menu or status voice:
    # (R18 heal: pin the encoding - the source carries em dashes and
    # the ▸ glyph; the Windows CI default codec is cp1252 and it LOST)
    src = (Path(__file__).resolve().parent.parent / "tracer" / "ui" /
           "mainwindow.py").read_text(encoding="utf-8")
    i = src.index("def action_joint")
    j = src.index("def action_interference")
    body = " ".join(src[i:j].split())
    assert body.count("each another") == 1
    assert body.index("flagged not cloned") < body.index("each another")
