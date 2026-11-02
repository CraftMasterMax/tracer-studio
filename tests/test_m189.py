"""M189 rung 1 - THE REFUSAL LADDER: naming refusals step DOWN
(LAW-61 documented TIERS).

"Three-tier refusal: (a) inline panel text for RECOVERABLE INPUT;
(b) non-modal COUNT for partial failure; (c) MODAL only for DATA
LOSS." (adom SKILL; AutoCAD GUID-2729A466; fd8 LAW-61.) The audit
found four pure input refusals sitting in tier-(c) chairs: rename a
feature onto a taken name, rename a datum onto one, register a
letter twice, and an illegal sheet parameter - each answered with
an app-modal pop that interrupts the shop floor. Rung 1 walks them
DOWN to the status line - the SAME kernel sentence (the kernel
already speaks it), just spoken where the maker is already looking.

The ladder is not a mute button: the refusal still REFUSES (names
unchanged, captures unwound, nothing created), and the two doors
that EARNED the modal - data loss (Delete All After Marker) and the
repair doctrine's first voice (Recompute failed) - are gated STANDING.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                       # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        from tracer.ui.renderer import SceneRenderer
        from tracer.ui.mainwindow import MainWindow
        try:
            r = SceneRenderer()
        except Exception as e:                 # CI windows: no headless GL
            pytest.skip(f"no headless GL available: {e}")
        w = MainWindow(renderer=r)
        w.resize(1000, 700)
        w.show()
        qapp.processEvents()
        yield w
        w._unsaved = False
        w.close()
    except ImportError:
        pytest.skip("no PySide6")


def _silence_modal(monkeypatch, hits):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", classmethod(
        lambda cls, *a, **k: hits.append(a[2] if len(a) > 2 else "")))


def test_rename_feature_onto_a_taken_name_speaks_the_status_line(
        win, qapp, monkeypatch):
    from tracer.core.document import PrimitiveFeature as _P
    from tracer.ui.cmddialog import Shell
    d = win.doc
    pad = d.add(_P(name="pad", kind="box", op="union",
                   dims={"dx": 20.0, "dy": 20.0, "dz": 4.0}))
    d.add(_P(name="stud", kind="box", op="union",
             dims={"dx": 4.0, "dy": 4.0, "dz": 10.0}))
    win.recompute()
    monkeypatch.setattr(Shell, "getText", staticmethod(
        lambda p, t, l, text="": ("stud", True)))
    hits = []
    _silence_modal(monkeypatch, hits)
    depth = len(win._undo)
    win._rename_feature(pad)
    qapp.processEvents()
    assert hits == [], "a taken name is RECOVERABLE INPUT - no modal"
    assert pad.name == "pad", "the refusal still REFUSES"
    assert len(win._undo) == depth, "the refused capture still unwinds"
    msg = win.status.currentMessage()
    assert "already taken" in msg, \
        "the SAME kernel sentence rides the status line - the voice " \
        "drops a tier, the WORDS do not soften"


def test_rename_datum_onto_a_taken_name_speaks_the_status_line(
        win, qapp, monkeypatch):
    from tracer.ui.cmddialog import Shell
    d = win.doc
    p1 = d.add_plane("XY", 4.0)
    p2 = d.add_plane("XY", 4.0)
    win.recompute()
    monkeypatch.setattr(Shell, "getText", staticmethod(
        lambda p, t, l, text="": (p2["name"], True)))
    hits = []
    _silence_modal(monkeypatch, hits)
    win._rename_datum("work plane", p1["name"])
    qapp.processEvents()
    assert hits == [], "a datum collision is the SAME tier case"
    assert any(p["name"] == p1["name"] for p in d.planes), \
        "the refusal refused"
    assert "already taken" in win.status.currentMessage()


def test_registering_a_taken_letter_speaks_the_status_line(
        win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    d = win.doc
    d.datum_register("A", "plane", "XY")          # a fair first register
    hits = []
    _silence_modal(monkeypatch, hits)
    monkeypatch.setattr(cmddialog, "ask", staticmethod(
        lambda *a, **k: {"letter": "A"}))
    depth = len(win._undo)
    win._register_datum("plane", "XY", "probe")   # ONE letter, one datum
    qapp.processEvents()
    assert hits == [], "a double-registered letter is INPUT - tier (a)"
    assert len(d.datums) == 1, "the refusal refused"
    assert len(win._undo) == depth, "the refused capture unwound"
    assert "one letter" in win.status.currentMessage(), \
        "and the cure rides with the cause, kernel-worded"


def test_an_illegal_sheet_parameter_speaks_the_status_line(
        win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    hits = []
    _silence_modal(monkeypatch, hits)
    sheets0 = len(win.doc.drawings)
    monkeypatch.setattr(cmddialog, "ask", staticmethod(
        lambda *a, **k: {"t": -1.0, "width": 100.0, "leg": 20.0,
                         "material": "steel"}))
    win.action_new_sheet()
    qapp.processEvents()
    assert hits == [], "a negative thickness is INPUT - tier (a)"
    assert len(win.doc.drawings) == sheets0, "the refusal refused"
    assert win.status.currentMessage(), "and it SPOKE where the eye is"


# ---- the ladder guard: the doors that EARNED the modal stay ---------


def test_the_data_loss_door_keeps_its_modal(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.core.document import PrimitiveFeature as _P
    d = win.doc
    for i in range(2):
        d.add(_P(name=f"GD{i}", kind="box", op="union",
                 dims={"dx": 2.0, "dy": 2.0, "dz": 2.0}))
    win.recompute()
    win._apply_rollback(1)
    hits = []
    monkeypatch.setattr(QMessageBox, "warning", classmethod(
        lambda cls, *a, **k: (hits.append(a[1] if len(a) > 1 else ""),
                              QMessageBox.StandardButton.No)[0]))
    win._delete_after_marker()
    qapp.processEvents()
    assert hits and hits[0] == "Delete All Features After Marker", \
        "LAW-61(c): DATA LOSS keeps the modal - the ladder demotes " \
        "interruptions, not guardrails"
    win._apply_rollback(None)


def test_the_repair_first_voice_keeps_its_modal(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.core.document import Document, PrimitiveFeature as _P
    hits = []
    monkeypatch.setattr(QMessageBox, "warning", classmethod(
        lambda cls, *a, **k: hits.append(a[1] if len(a) > 1 else "")))
    d = Document("t")
    d.features.append(_P(name="cut", kind="box", op="subtract",
                         dims={"dx": 5.0, "dy": 5.0, "dz": 5.0}))
    win.doc = d
    win.recompute()
    qapp.processEvents()
    assert hits == ["Recompute failed"], \
        "the repair doctrine's first voice is MODAL by doctrine (R1) - " \
        "rung 1 moves INPUT refusals, not the fault ambush"


# ---- R2: THE SHOP-FLOOR REJECTIONS STEP DOWN (LAW-61 tier (a)) -----------------
# The dry-run kernel refusals - the validate-before-touching-history
# catches in the geometry tools - sit in tier-(c) chairs they never
# earned: nothing changed, history is untouched, the fix is a typed
# number. They join the ESTABLISHED status family ("Rename refused:",
# "Parameters refused:", "Drawing export refused:"): the SAME kernel
# sentence, one tier lower. The preconditions ("Nothing to shell
# yet") are a DIFFERENT law shape and keep their rung (R3).

import re                                                              # noqa: E402
import numpy as np                                                     # noqa: E402
from conftest import script_cmd                                        # noqa: E402


def _mw_source():
    import inspect
    import tracer.ui.mainwindow as mw
    return inspect.getsource(mw)


def test_the_rejection_family_no_longer_summons_modals():
    src = _mw_source()
    retired = re.findall(
        r'QMessageBox\.warning\(\s*self,\s*"(Shell|Split Body|Flat '
        r'Pattern|Add Flange|Add Fold|Joint|Interlock|Sweep|Thicken'
        r'|Loft)",\s*str\((?:e|err)\).*?\)', src, re.DOTALL)
    assert retired == [], \
        f"kernel rejections still in tier-(c) chairs: {retired}"
    assert '"This member mates TWO bodies' not in src, \
        "the interlock pick-error should speak the status line too"


def test_shell_refusal_rides_the_status_line(win, qapp, monkeypatch):
    from tracer.core.document import PrimitiveFeature as _P, ShellFeature
    from tracer.ui.cmddialog import Shell
    d = win.doc
    d.add(_P(name="plate", kind="box", op="union",
             dims={"dx": 40.0, "dy": 40.0, "dz": 6.0}))
    win.recompute()
    qapp.processEvents()
    monkeypatch.setattr(win.viewport, "selected_face", lambda: dict(
        point=np.array([20.0, 20.0, 6.0]),
        normal=np.array([0.0, 0.0, 1.0])))
    monkeypatch.setattr(Shell, "getDouble",
                        staticmethod(lambda *a, **k: (20.0, True)))
    hits = []
    _silence_modal(monkeypatch, hits)
    win.action_shell()
    qapp.processEvents()
    assert hits == [], "a wall thicker than the body is INPUT - tier (a)"
    msg = win.status.currentMessage().lower()
    assert "refused" in msg, "the kernel's sentence rides the status line"
    assert not [f for f in d.features if isinstance(f, ShellFeature)], \
        "the refusal refused - no feature touched history"


def test_split_below_the_body_refuses_inline(win, qapp, monkeypatch):
    from tracer.core.document import PrimitiveFeature as _P, SplitFeature
    d = win.doc
    d.add(_P(name="block", kind="box", op="union",
             dims={"dx": 40.0, "dy": 40.0, "dz": 20.0}))
    win.recompute()
    qapp.processEvents()
    script_cmd(monkeypatch, {"plane": "XY", "dist": -20.0, "flip": False})
    hits = []
    _silence_modal(monkeypatch, hits)
    v0 = d.result.volume
    win.action_split_body()
    qapp.processEvents()
    assert hits == [], "a split that kills the body is INPUT - tier (a)"
    assert "refused" in win.status.currentMessage().lower()
    assert not [f for f in d.features if isinstance(f, SplitFeature)]
    assert d.result.volume == pytest.approx(v0, rel=1e-3), \
        "validate BEFORE touching history - the body is untouched"


def test_joint_self_refusal_refuses_without_leaking_the_capture(
        win, qapp, monkeypatch):
    from tracer.core.document import PrimitiveFeature as _P
    d = win.doc
    d.add_body("A")
    d.add(_P(name="boxA", kind="box", dims={"dx": 10, "dy": 20, "dz": 30}))
    d.add_body("B")
    d.add(_P(name="boxB", kind="box", dims={"dx": 5, "dy": 5, "dz": 5}))
    win.recompute()
    qapp.processEvents()
    script_cmd(monkeypatch, {"base": "A", "mover": "A", "ground": True})
    hits = []
    _silence_modal(monkeypatch, hits)
    depth = len(win._undo)
    win.action_joint()
    qapp.processEvents()
    assert hits == [], "a self-joint is INPUT - tier (a)"
    assert "refused" in win.status.currentMessage().lower()
    assert d.joints == [] if hasattr(d, "joints") else True
    assert len(win._undo) == depth, \
        "the refused capture unwinds (Joint used to LEAK it - fixed here)"


def test_sweep_empty_recipe_refuses_inline(win, qapp, monkeypatch):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    hits = []
    _silence_modal(monkeypatch, hits)
    win.action_sweep()                       # empty sketch: no path
    qapp.processEvents()
    assert hits == [], "an empty sketch is INPUT - tier (a)"
    msg = win.status.currentMessage().lower()
    assert "refused" in msg and "circle" in msg, \
        "the kernel's own cure (draw the path) rides the status line"


# ---- R3: THE PRECONDITIONS STEP DOWN TOO (LAW-61 tier (a)) ---------------------
# Seven tools still popped a MODAL for "Nothing to X yet" - a state
# with nothing refused, nothing at risk and a one-clause cure. The
# MAJORITY of the shop (Repeat, Adjust, Draw, Publish, Project, Print,
# Measure, Undo/Redo) already murmurs exactly this class of sentence
# in the status bar; the stragglers join them, SAME sentence, one
# tier lower. The drafting dialogs (ISO 286, GD&T, Pattern on Path)
# are a different rung; the data-loss guards keep their modals by
# R1's own law.

def test_no_precondition_summons_a_modal_anymore():
    src = _mw_source()
    retired = re.findall(
        r'QMessageBox\.warning\(\s*self,\s*"[A-Za-z ]+",\s*\n?\s*'
        r'"Nothing to[^\n]*', src)
    assert retired == [], \
        f"preconditions still in tier-(c) chairs: {retired}"


def test_empty_document_move_speaks_the_status_line(win, qapp,
                                                    monkeypatch):
    win.new_document()                       # nothing built at all
    qapp.processEvents()
    hits = []
    _silence_modal(monkeypatch, hits)
    win.action_move_body()
    qapp.processEvents()
    assert hits == [], "an empty model is INPUT state - tier (a)"
    msg = win.status.currentMessage().lower()
    assert "nothing to move" in msg and "extrude" in msg, \
        "the same sentence the majority already murmur"


def test_the_six_remaining_stragglers_all_speak_inline(win, qapp,
                                                       monkeypatch):
    win.new_document()
    qapp.processEvents()
    hits = []
    _silence_modal(monkeypatch, hits)
    for act, key in (("action_shell", "nothing to shell"),
                     ("action_split_body", "nothing to split"),
                     ("action_thread", "nothing to thread"),
                     ("action_appearance", "nothing to paint"),
                     ("action_rotate_body", "nothing to rotate"),
                     ("action_combine", "nothing to combine")):
        getattr(win, act)()
        qapp.processEvents()
        assert hits == [], f"{act} ambushed an empty model"
        assert key in win.status.currentMessage().lower(), \
            f"{act} must speak the status line, got " \
            f"{win.status.currentMessage()!r}"
