"""M146 — assembly rung 1: the rigid Joint, NO solver, LAW R.

"A joint follows where a body is PLACED, not how it is BUILT"
(research/assembly_rung1.md §7.1 F2a). Bodies mint ids at creation
(joints bind ids — names are display); the first body grounds
itself (the vendor's own rule for the first component); and
recompute RE-APPLIES joints in topological order after the
placement loop, one 4x4 multiply per jointed body:

    P'_child = P'_parent @ m,    m = inv(P_A0) @ P_B0 baked once

THE CORRECTION (re-derived before the build — the same class of
catch as SM1's 96.09 -> 106.09): the contract's §7.1 formula
carries an extra factor, P'_child = P'_parent @ inv(a_home) @ m.
At creation that returns m, not P_B0 — the child TELEPORTS
whenever the base sat anywhere but identity when the joint was
made. The spike passed because every home in it was eye(4): a
law only ever tested at the identity is not tested. The re-apply
is the delta form above; a_home rides the record as bake
context. The chain test lands the grandchild at its measured
HOME with a NON-identity base pose — the buggy formula parks it
at (-12,7,0) and fails right there.

Rigidity means: dragging the BASE carries the whole subtree
exactly; a PARAMETRIC (stream) edit does NOT carry — we have no
per-body frame until rung 2 (F2's priced option b) and the
product says so out loud. Refusals are loud: self-join, a
second parent, creation cycles, interference clashes (F4). A
hand-edited cycle degrades to own placement and NAMES the
offenders in doc.joint_warnings. Grounded or jointed bodies
refuse the Move/Rotate gesture AT ARM TIME — the triad never
appears (§5.4's vendor law, our words).
"""
import numpy as np
import pytest

from tracer.core import params
from tracer.core.document import Document, PrimitiveFeature
from tracer.core.geometry import Solid


def _two_box_doc():
    """test_placement's builder, verbatim shape."""
    d = Document()
    d.add_body("A")
    d.add(PrimitiveFeature(name="boxA", kind="box",
                           dims={"dx": 10, "dy": 20, "dz": 30}))
    d.add_body("B")
    d.add(PrimitiveFeature(name="boxB", kind="box",
                           dims={"dx": 5, "dy": 5, "dz": 5}))
    d.recompute()
    return d


def _bounds(sol):
    bb = sol.bounding_box
    return [round(v, 6) for v in (list(bb[0]) + list(bb[1]))]


def _shifted(bounds, d):
    return [v + d[i % 3] for i, v in enumerate(bounds)]


def _T(x, y, z):
    m = np.eye(4)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m


# ---- t1: ids and ground are file facts --------------------------------
def test_first_body_is_grounded_and_survives_save():
    d = _two_box_doc()
    a, b = d.bodies
    assert a["grounded"] is True and b["grounded"] is False
    for x in (a, b):
        assert isinstance(x["id"], str) and len(x["id"]) == 8
    assert a["id"] != b["id"] and a["id"] != a["name"]
    e = Document.from_dict(d.to_dict())
    assert [x["id"] for x in e.bodies] == [a["id"], b["id"]]
    assert [x.get("grounded") for x in e.bodies] == [True, False]
    e.recompute()
    assert _bounds(e._body_solids["B"]) == _bounds(d._body_solids["B"])


def test_pre_id_files_hydrate_but_never_ground_at_load():
    d = _two_box_doc()
    dd = d.to_dict()
    for brec in dd["bodies"]:          # a file from before M146
        brec.pop("id")
        brec.pop("grounded")
    e = Document.from_dict(dd)
    assert all(isinstance(b.get("id"), str) and len(b["id"]) == 8
               for b in e.bodies)       # ids hydrated at load...
    assert not any(b.get("grounded") for b in e.bodies)
    # ...but ground is a FILE FACT: loading invents none
    e.recompute()
    assert _bounds(e._body_solids["B"]) == _bounds(d._body_solids["B"])


# ---- t2: the bake, and the teleport the corrected formula forbids -----
def test_rigid_joint_bakes_delta_and_never_teleports():
    d = _two_box_doc()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    before = _bounds(d._body_solids["B"])
    j = d.add_joint("A", "B")
    d.recompute()
    assert _bounds(d._body_solids["B"]) == before      # no teleport
    m = np.asarray(j["m"], float).reshape(4, 4)
    assert np.allclose(m, _T(12.0, 0.0, 0.0))          # delta form
    assert np.allclose(np.asarray(j["a_home"], float)
                       .reshape(4, 4), np.eye(4))      # bake context
    assert set(j) == {"id", "kind", "a", "b", "m", "a_home", "note"}
    assert j["kind"] == "rigid"
    r = Document.from_dict(d.to_dict())
    r.recompute()
    assert _bounds(r._body_solids["B"]) == before      # rides the file


# ---- the LAW R pair: PLACEMENT follows, BUILD does not -----------------
def test_dragging_the_base_carries_the_whole_subtree():
    d = _two_box_doc()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    b0 = _bounds(d._body_solids["B"])
    d.move_body("A", 12.0, -3.0, 4.0)
    d.recompute()
    assert _bounds(d._body_solids["B"]) == _shifted(b0,
                                                    [12.0, -3.0, 4.0])


def test_parametric_edit_does_not_carry_the_child():
    """F2's honest face, RE-SCOPED by rung 2a (M148 t1): the silent
    non-carry is now the GROWTH half of the law — dims move nothing
    and the joint says "grew" out loud. (A terminal Move/Rotate tail
    or a lone primitive's placement DOES carry: test_m148 t1-t3.)"""
    d = _two_box_doc()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    b0 = _bounds(d._body_solids["B"])
    d.features[0].dims["dy"] = 40.0            # A grows: parametric
    d.recompute()
    assert _bounds(d._body_solids["B"]) == b0  # B stays (rung-1 law)
    assert d.joint_warnings and "grew" in d.joint_warnings[0]
    #                       ^ rung 2a's voice: growth refused, loudly
    d.move_body("A", 3.0, 0.0, 0.0)            # placement still
    d.recompute()                              # carries, delta form
    assert _bounds(d._body_solids["B"]) == _shifted(b0, [3.0, 0.0,
                                                         0.0])


# ---- the correction's scene: a chain whose BASE pose is NOT identity ---
def test_chain_composes_by_depth_from_a_nonidentity_home():
    d = _two_box_doc()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")                      # home A = identity
    d.add_body("C")
    d.add(PrimitiveFeature(name="boxC", kind="box",
                           dims={"dx": 2, "dy": 2, "dz": 2}))
    d.move_body("C", 0.0, 7.0, 0.0)
    d.recompute()
    c0 = _bounds(d._body_solids["C"])          # C sits at (0,7,0)
    d.add_joint("B", "C")                      # base B at (12,0,0)
    d.recompute()
    assert _bounds(d._body_solids["C"]) == c0  # NO TELEPORT at
    #   level 2: the contract's extra inv(a_home) parks C at
    #   (-12,7,0) instead — this assert IS the correction
    d.move_body("A", 5.0, 0.0, 0.0)
    d.recompute()
    assert _bounds(d._body_solids["C"]) == _shifted(c0, [5.0, 0.0,
                                                         0.0])
    assert _bounds(d._body_solids["B"]) == [17.0, 0.0, 0.0,
                                            22.0, 5.0, 5.0]


# ---- t5: order determinism — depth, never list order -------------------
def test_star_goldens_survive_body_reorder_and_double_recompute():
    d = _two_box_doc()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    d.add_body("C")
    d.add(PrimitiveFeature(name="boxC", kind="box",
                           dims={"dx": 2, "dy": 2, "dz": 2}))
    d.move_body("C", -8.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "C")                      # star: B and C on A
    d.recompute()
    gb, gc = _bounds(d._body_solids["B"]), _bounds(d._body_solids["C"])
    d.bodies[1], d.bodies[2] = d.bodies[2], d.bodies[1]   # swap rows
    d.recompute()
    assert _bounds(d._body_solids["B"]) == gb
    assert _bounds(d._body_solids["C"]) == gc
    d.move_body("A", 0.0, 6.0, 0.0)
    d.recompute()
    assert _bounds(d._body_solids["B"]) == _shifted(gb, [0, 6, 0])
    assert _bounds(d._body_solids["C"]) == _shifted(gc, [0, 6, 0])
    d.recompute()                              # twice: identical
    assert _bounds(d._body_solids["B"]) == _shifted(gb, [0, 6, 0])


# ---- t3: the joint speaks id, the relink speaks name -------------------
def test_rename_body_never_orphans_the_joint():
    d = _two_box_doc()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    j = d.add_joint("A", "B")
    frozen = dict(j)
    b0 = _bounds(d._body_solids["B"])
    n = d.rename_body("A", "Base")
    assert n >= 1                              # M130's counted voice
    assert j is d.joints[0]
    for k in ("id", "kind", "a", "b", "m", "a_home"):
        assert j[k] == frozen[k]               # nothing rewritten
    d.move_body("Base", 1.0, 0.0, 0.0)         # the joint still
    d.recompute()                              # binds, by id
    assert _bounds(d._body_solids["B"]) == _shifted(b0, [1.0, 0.0,
                                                         0.0])
    with pytest.raises(params.ParamError, match="already taken"):
        d.rename_body("Base", "B")


# ---- t6: the zero-regression law ---------------------------------------
def test_single_body_no_joint_doc_never_touches_a_matrix(monkeypatch):
    calls: list = []
    orig = Solid.transformed
    monkeypatch.setattr(Solid, "transformed",
                        lambda self, m: calls.append(m) or orig(self,
                                                                m))
    d = Document()
    d.add_body("Solo")
    d.add(PrimitiveFeature(name="s", kind="box",
                           dims={"dx": 2, "dy": 2, "dz": 2}))
    d.recompute()
    assert calls == []                         # identity short-circuit
    dd = d.to_dict()
    assert dd["joints"] == []
    assert set(dd["bodies"][0]) == {"name", "visible", "placement",
                                    "rot", "id", "grounded"}
    assert _bounds(d._body_solids["Solo"]) == [0.0, 0.0, 0.0,
                                               2.0, 2.0, 2.0]


# ---- t7: loud refusals ---------------------------------------------------
def test_joint_refusals_are_loud():
    d = _two_box_doc()
    with pytest.raises(params.ParamError, match="itself"):
        d.add_joint("A", "A")
    d.add_joint("A", "B")
    with pytest.raises(params.ParamError, match="parent"):
        d.add_joint("A", "B")                  # second claim
    e = _two_box_doc()
    e.add_joint("A", "B")
    with pytest.raises(params.ParamError, match="LOOP"):
        e.add_joint("B", "A")                  # closes a cycle


def test_interference_clash_refuses_a_joint():
    d = _two_box_doc()
    cl, f = d.add_interference("A", "B")
    d.recompute()
    with pytest.raises(params.ParamError, match="interference"):
        d.add_joint("A", cl["name"])
    with pytest.raises(params.ParamError, match="interference"):
        d.add_joint(cl["name"], "B")


def test_hand_edited_cycle_names_offenders_and_sits_at_own_placement():
    d = _two_box_doc()
    ia = d._body("A")["id"]
    ib = d._body("B")["id"]
    eye = np.eye(4).ravel().tolist()
    d.joints = [{"id": "j1", "kind": "rigid", "a": ia, "b": ib,
                 "m": eye, "a_home": eye, "note": ""},
                {"id": "j2", "kind": "rigid", "a": ib, "b": ia,
                 "m": eye, "a_home": eye, "note": ""}]
    d.move_body("B", 4.0, 0.0, 0.0)
    d.recompute()                              # does NOT raise
    assert d.joint_warnings
    joined = " ".join(d.joint_warnings)
    assert "A" in joined and "B" in joined
    assert _bounds(d._body_solids["B"]) == _shifted(
        [0.0, 0.0, 0.0, 5.0, 5.0, 5.0], [4.0, 0.0, 0.0])


# ---- UI: t4 — refuse at ARM time, name the blocker ---------------------
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def win(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1200, 800)
    w.show()
    qapp.processEvents()
    w.new_document()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    qapp.processEvents()


def _assembly_in(win):
    """A (grounded base, box), B (jointed child), C (free body)."""
    d = win.doc
    d.add_body("A")
    d.add(PrimitiveFeature(name="boxA", kind="box",
                           dims={"dx": 10, "dy": 20, "dz": 30}))
    d.add_body("B")
    d.add(PrimitiveFeature(name="boxB", kind="box",
                           dims={"dx": 5, "dy": 5, "dz": 5}))
    d.recompute()
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    d.add_joint("A", "B")
    d.add_body("C")
    d.add(PrimitiveFeature(name="boxC", kind="box",
                           dims={"dx": 2, "dy": 2, "dz": 2}))
    d.recompute()
    return d


def _tree_texts(win):
    texts: list = []

    def walk(it):
        for i in range(it.childCount()):
            ch = it.child(i)
            texts.append(ch.text(0))
            walk(ch)
    walk(win.rail.tree.invisibleRootItem())
    return texts


def test_drag_of_grounded_or_jointed_body_refuses_and_says_why(win,
                                                               qapp):
    d = _assembly_in(win)
    n0 = len(d.features)
    d.active_body = "A"                        # the grounded base
    win.action_move_body()
    qapp.processEvents()
    assert win.viewport._mv is None            # the triad NEVER
    assert "grounded" in win.status.currentMessage()
    win.action_rotate_body()
    qapp.processEvents()
    assert win.viewport._rot is None
    assert "grounded" in win.status.currentMessage()
    d.active_body = "B"                        # the jointed child
    win.action_move_body()
    qapp.processEvents()
    assert win.viewport._mv is None
    assert "jointed" in win.status.currentMessage()
    win.action_rotate_body()
    qapp.processEvents()
    assert win.viewport._rot is None
    assert "jointed" in win.status.currentMessage()
    assert len(d.features) == n0               # nothing was added
    assert d.is_movable("C") is True           # the free body can


def test_joint_command_bakes_from_dialog_and_the_browser_lists_it(
        win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    d = _assembly_in(win)
    d.remove_joint(d.joints[0]["id"])          # re-do it through UI
    d.move_body("B", 0.0, 0.0, 0.0)            # place it by STATE...
    d.move_body("B", 12.0, 0.0, 0.0)
    d.recompute()
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda parent, title, fields, remember_key=None: {
            "base": "A", "mover": "B", "ground": True})
    d.active_body = "B"
    win.action_joint()
    qapp.processEvents()
    assert len(d.joints) == 1
    j = d.joints[0]
    assert d._body_by_id(j["a"])["name"] == "A"
    assert d._body_by_id(j["b"])["name"] == "B"
    assert d._body("A")["grounded"] is True
    assert "position captured" in win.status.currentMessage()
    assert "rigid, 0 DOF" in win.status.currentMessage()
    texts = _tree_texts(win)
    assert any("Joints (1)" in t for t in texts)
    assert any("Joints" not in t and "B" in t and "A" in t
               for t in texts)
    d.remove_joint(j["id"])                    # the row's Delete
    win.rail.tree.reload()
    qapp.processEvents()
    assert not any("Joints" in t for t in _tree_texts(win))
