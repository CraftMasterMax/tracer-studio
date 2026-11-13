"""M201 R19 - the joint row's menu mirrors the page's six.

[ASM-JOINTS, verbatim] "You can right-click any existing joint, in
the canvas or browser, and use the following additional tools to
modify it:" - the page prints SIX: Edit Joint | Edit Joint Limits |
Lock | Suppress | Animate Joint | Animate Model.  Two of them the
kernel can actually bake, and those two land:

  "Edit Joint: Opens the Edit Joint dialog and lets you edit all
   settings associated with the joint."  Every setting this kernel
   holds is the PAIR, so edit re-runs the WHOLE add_joint contract -
   no refusal can be slipped by an edit - and keeps identity: the
   old id and the old list slot (list order is the bake's tie-break),
   the record untouched on refusal.

  "Suppress: Temporarily removes the joint to prevent it from acting
   upon the components."  A suppressed joint acts on NOTHING (the
   bake skips it, the drag guard lifts), yet keeps its seat (guards
   and the file still count it) - suppression hides the ACT, not the
   existence.  Unsuppressing re-applies the captured pose.

The other four stay UNOFFERED, each gated by a page's own sentence:
limits wait for "a Joint Type that has more than one degree of
motion" (Rigid carries none), Lock holds what nothing moves, and the
two Animates have neither motion nor an animator.  "Delete Joint" is
OURS, stamped - the page's six do not print it.  "Unsuppress" is the
browser's own word since the feature eras.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint                                       # noqa
from PySide6.QtWidgets import QApplication, QMenu                       # noqa

from conftest import script_cmd, script_cmd_cancel                      # noqa
from tracer.core import params                                          # noqa
from tracer.core.document import Document, PrimitiveFeature             # noqa
from tracer.ui.mainwindow import MainWindow                             # noqa
from tracer.ui.renderer import SceneRenderer                            # noqa

import tracer.core.document as docmod                                   # noqa


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


def _two_box_doc():
    d = Document()
    d.add_body("A")
    d.add(PrimitiveFeature(name="boxA", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10}))
    d.add_body("B")
    d.add(PrimitiveFeature(name="boxB", kind="box",
                           dims={"dx": 5, "dy": 5, "dz": 5}))
    d.recompute()
    return d


def _jointed():
    """A at home, B placed at x=12, joint A->B: B now follows A."""
    d = _two_box_doc()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    d.recompute()
    return d


def _b0(d):
    bb = d._body_solids["B"].bounding_box
    return [round(v, 6) for v in (list(bb[0]) + list(bb[1]))]


def _shifted(bounds, dd):
    return [v + dd[i % 3] for i, v in enumerate(bounds)]


def _ui_pair(win):
    """Fresh UI doc with bodies A and B (each one staged kernel box -
    the RECORDS are what this rung's menus edit)."""
    win.new_document()
    d = win.doc
    d.add_body("A")
    d.add(PrimitiveFeature(name="boxA", kind="box",
                           dims={"dx": 5, "dy": 5, "dz": 5}))
    d.add_body("B")
    d.add(PrimitiveFeature(name="boxB", kind="box",
                           dims={"dx": 5, "dy": 5, "dz": 5},
                           placement=(20.0, 0.0, 0.0)))
    win.recompute()
    d.add_joint("A", "B")
    return d


def _tree_texts(win):
    out = []

    def walk(it):
        for i in range(it.childCount()):
            c = it.child(i)
            out.append(c.text(0))
            walk(c)
    walk(win.rail.tree.invisibleRootItem())
    return out


# ---- the kernel's two bakeable tools ---------------------------------------

def test_a_suppressed_joint_acts_on_nothing():
    """The page's sentence IS the test: prevented from acting on the
    components, the child rides its own stream again - the base moves
    and the joint lets it stand.  Unsuppressing re-applies the
    captured pose."""
    d = _jointed()
    b0 = _b0(d)
    d.ground_body("A", False)
    d.suppress_joint(d.joints[0]["id"], True)
    d.move_body("A", 5.0, 0.0, 0.0)
    d.recompute()
    assert _b0(d) == b0                                  # stayed put
    d.suppress_joint(d.joints[0]["id"], False)
    d.recompute()
    assert _b0(d) == _shifted(b0, [5.0, 0.0, 0.0])       # follows again


def test_suppression_hides_the_act_not_the_seat():
    """A hidden relationship still occupies the seat the file says it
    holds: the one-parent guard refuses a second joint on the same
    child while the first sleeps."""
    d = _jointed()
    d.suppress_joint(d.joints[0]["id"])
    with pytest.raises(params.ParamError, match="already has a parent"):
        d.add_joint("A", "B")


def test_the_drag_guard_lifts_with_the_act():
    """move_blocker asks whether a joint ACTS on this body; a
    suppressed one acts on nothing, so the body is draggable again -
    while the capture-POSE guard still stands: capture rewrites the
    base pose itself (the weld-jump algebra is not the joint
    acting)."""
    d = _jointed()
    assert d.move_blocker("B") is not None
    d.suppress_joint(d.joints[0]["id"])
    assert d.move_blocker("B") is None
    with pytest.raises(params.ParamError, match="rides a joint"):
        d.capture_body_placement("B")


def test_edit_reruns_the_whole_contract_and_keeps_identity():
    """Edit is not a back door: the swap A<->B is a legal pair (the
    edited joint vacates its seat first, the guards then run clean),
    and the record keeps its id and its LIST SLOT; an illegal pair
    (self) refuses with the creation voice and leaves the record
    byte-equal."""
    d = _jointed()
    j0 = dict(d.joints[0])
    j = d.edit_joint(j0["id"], "B", "A")
    assert j["id"] == j0["id"]
    assert d.joints[0]["id"] == j0["id"]                 # slot kept
    assert j["a"] == j0["b"] and j["b"] == j0["a"]       # pair swapped
    with pytest.raises(params.ParamError, match="cannot be jointed"):
        d.edit_joint(j0["id"], "A", "A")
    assert d.joints[0] == j                              # refusal intact


def test_the_suppressed_flag_is_a_file_fact():
    """Save/load carries it; a pre-R19 file (no key) reads
    unsuppressed - the old files move not an inch."""
    d = _jointed()
    d.suppress_joint(d.joints[0]["id"])
    payload = d.to_dict()
    assert payload["joints"][0]["suppressed"] is True
    d2 = Document.from_dict(payload)
    assert d2.joints[0].get("suppressed") is True
    payload["joints"][0].pop("suppressed")
    old = Document.from_dict(payload)
    assert old.joints[0].get("suppressed", False) is False


# ---- the menu mirrors the page's six ----------------------------------------

def _menu_items(win, monkeypatch, joint_id):
    rec = []
    monkeypatch.setattr(
        QMenu, "exec_",
        lambda self, p, *a: rec.append(
            [x.text() for x in self.actions() if x.text()]))
    win._joint_menu(joint_id, QPoint(10, 10))
    return rec[0]


def test_the_row_menu_offers_the_two_bakeable_plus_the_house_delete(
        win, monkeypatch):
    """Edit Joint + Suppress land from the page's six; the four the
    gates keep are absent; Delete is the stamped house extra."""
    d = _ui_pair(win)
    items = _menu_items(win, monkeypatch, d.joints[0]["id"])
    assert items == ["Edit Joint", "Suppress", "Delete Joint"], items
    for absent in ("Edit Joint Limits", "Lock", "Animate Joint",
                   "Animate Model"):
        assert absent not in items


def test_the_menu_word_and_row_flip_with_the_state(win, monkeypatch):
    """The house's own flip-word (features Suppress/Unsuppress from
    the browser since the early eras); the row borrows the
    suppressed CIRCLE the browser already draws, and the folder still
    counts the joint - the act sleeps, the existence does not."""
    d = _ui_pair(win)
    jid = d.joints[0]["id"]
    win._toggle_joint_suppress(jid)
    assert d.joints[0]["suppressed"] is True
    items = _menu_items(win, monkeypatch, jid)
    assert "Unsuppress" in items and "Suppress" not in items
    texts = _tree_texts(win)
    row = [t for t in texts if "B → A" in t]
    assert row and row[0].startswith("\u25cb"), texts
    assert any(t.startswith("Joints (1)") for t in texts)


def test_edit_joint_reopens_the_door_and_swaps_honestly(win, monkeypatch):
    """The page: "Opens the Edit Joint dialog and lets you edit all
    settings" - the dialog wears THAT name, pre-fills from the record,
    a Cancel changes nothing, and a swap keeps the id."""
    d = _ui_pair(win)
    jid = d.joints[0]["id"]
    script_cmd_cancel(monkeypatch)
    depth = len(win._undo)
    win._edit_joint(jid)
    assert d.joints[0]["id"] == jid and len(win._undo) == depth
    script_cmd(monkeypatch, {"base": "B", "mover": "A"})
    win._edit_joint(jid)
    j = d.joints[0]
    assert j["id"] == jid
    assert d._body_by_id(j["a"])["name"] == "B"
    assert "Joint edited" in win.status.currentMessage()


def test_the_gate_quotations_stand_at_the_mouth():
    """The menu's restraint cites its license verbatim, and the house
    stamp names what the page never printed."""
    menu = " ".join(MainWindow._joint_menu.__doc__.split())
    assert "Opens the Edit Joint dialog and lets you edit all settings " \
           "associated with the joint." in menu
    assert "Temporarily removes the joint to prevent it from acting " \
           "upon the components." in menu
    assert "more than one degree of motion" in menu
    assert "Delete Joint" in menu and "OURS, stamped" in menu
    ed = " ".join(docmod.Document.edit_joint.__doc__.split())
    assert "edit all settings associated with the joint" in ed
