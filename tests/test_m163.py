"""M163 rung 1 - the live command panel ENGINE (fleet spec:
research/specs/m163_param_transaction_internals.md).

Gates, each traceable to its mined law: parse_scalar speaks number |
arithmetic | named-param | trailing-unit and refuses the FreeCAD-illegal
"2mm + 4"; ExprField commits ONLY on discrete intentions (Enter /
focus-out / focused wheel), Esc rewinds and never commits silently,
invalid paints the danger TOKEN (M112's hex ban) and gates Commit;
ParamTransaction captures LAZILY at first mutation - one undo step per
field-session, same key folds, no-ops leave no trace, rotate() forces
the fresh step (Inkscape's key law); CmdPanel is structurally anti-modal
(no QDialogButtonBox ever), speaks ask()'s field language, and Esc
aborts the whole verb.
"""
import re

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QWheelEvent                        # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialogButtonBox)  # noqa: E402

from tracer.core import params                                # noqa: E402
from tracer.core.document import MirrorFeature, PrimitiveFeature  # noqa: E402
from tracer.ui import cmddialog, cmdpanel, theme              # noqa: E402
from tracer.ui.cmdpanel import (CmdPanel, ExprField,          # noqa: E402
                                ParamTransaction, parse_scalar)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ---- G1: the scalar grammar ----------------------------------------------

def test_number_units_and_formulas_evaluate_to_mm(qapp):
    assert parse_scalar("12") == 12.0                 # bare = mm (home unit)
    assert parse_scalar("12mm") == 12.0
    assert parse_scalar("1inch") == 25.4
    assert parse_scalar("2cm") == 20.0
    assert parse_scalar("4*20 + 7") == 87.0
    assert parse_scalar("wall*2", {"wall": 3.5}) == 7.0


def test_illegal_scalars_speak_the_param_error_family(qapp):
    for bad in ("2mm + 4", "", "wall", "import os"):
        with pytest.raises(params.ParamError):
            parse_scalar(bad, {})          # unit-inside / empty / unknown / unsafe


# ---- G2: ExprField boundaries ---------------------------------------------

def test_commit_only_on_changed_value(qapp):
    got = []
    f = ExprField(10.0)
    f.committed.connect(got.append)
    f.edit.setText("10")                   # same value, just retyped
    f._finish()
    assert got == []                       # no-change emits NOTHING
    f.edit.setText("12")
    f._finish()
    assert got == [12.0] and f.value_mm() == 12.0


def test_escape_rewinds_and_never_commits(qapp):
    got = []
    f = ExprField(8.0)
    f.committed.connect(got.append)
    f.edit.setText("999")
    QTest.keyClick(f.edit, Qt.Key.Key_Escape)
    assert f.edit.text().startswith("8")   # rewound to the accepted text
    assert got == []


def test_invalid_field_goes_red_and_refuses_commit(qapp):
    got, bad = [], []
    f = ExprField(5.0, step=0.5)
    f.committed.connect(got.append)
    f.invalid.connect(bad.append)
    f.edit.setText("2mm + 4")
    f._finish()
    assert got == [] and bad == [True]     # red on, no commit
    assert theme.DARK["danger"] in f.edit.styleSheet()   # TOKEN, never a literal
    f.edit.setText("6")
    f._finish()
    assert bad == [True, False] and got == [6.0]
    assert f.edit.styleSheet() == ""       # red off


def _wheel(widget, dy, mods=Qt.KeyboardModifier.NoModifier):
    pos = widget.rect().center()
    return QWheelEvent(QPointF(pos), QPointF(widget.mapToGlobal(pos)),
                       QPoint(0, 0), QPoint(0, dy),
                       Qt.MouseButton.NoButton, mods,
                       Qt.ScrollPhase.NoScrollPhase, False)


def test_wheel_scrubs_only_while_focused(qapp):
    got = []
    f = ExprField(10.0, step=0.1)
    f.committed.connect(got.append)
    f.edit.hasFocus = lambda: False        # the gate is hasFocus
    QApplication.sendEvent(f.edit, _wheel(f.edit, 120))
    assert got == []                       # unfocused: passes through
    f.edit.hasFocus = lambda: True
    QApplication.sendEvent(f.edit, _wheel(f.edit, 120))
    assert got == [10.1]                   # one focused notch = one step
    got.clear()
    QApplication.sendEvent(f.edit,
                           _wheel(f.edit, -120, Qt.KeyboardModifier.ShiftModifier))
    assert got == [9.1]                    # Shift coarse, direction honoured


# ---- G3: ParamTransaction - lazy capture + the key law ---------------------

def _journal():
    log = []
    return log, ParamTransaction(log.append)


def test_one_session_one_step_and_same_key_folds(qapp):
    log, tx = _journal()
    tx.apply("cmd:d", "Set diameter", mutated=True)
    tx.apply("cmd:d", "Set diameter", mutated=True)     # later wheel notches
    tx.apply("cmd:d", "Set diameter", mutated=True)
    assert log == ["Set diameter"]                      # ONE undo step


def test_different_key_opens_a_new_step(qapp):
    log, tx = _journal()
    tx.apply("cmd:d", "Set diameter", mutated=True)
    tx.apply("cmd:h", "Set height", mutated=True)
    assert log == ["Set diameter", "Set height"]


def test_noop_leaves_no_trace_then_real_edit_still_captures(qapp):
    log, tx = _journal()
    tx.apply("cmd:d", "Set diameter", mutated=False)    # retyped same value
    assert log == []                                    # captured nothing
    tx.apply("cmd:d", "Set diameter", mutated=True)     # now a real edit
    assert log == ["Set diameter"]                      # still captured


def test_rotate_forces_a_fresh_step_for_the_same_key(qapp):
    log, tx = _journal()
    tx.apply("cmd:d", "Set diameter", mutated=True)
    tx.rotate()                                         # selection changed
    tx.apply("cmd:d", "Set diameter", mutated=True)
    assert log == ["Set diameter", "Set diameter"]


# ---- G4: CmdPanel anatomy ---------------------------------------------------

FIELDS = [dict(key="d", label="Diameter", kind="double", default=8.0,
               step=0.5),
          dict(key="side", label="Side", kind="combo",
               choices=["Left", "Right"], default="Right"),
          dict(key="flip", label="Flip", kind="check", default=False)]


def test_panel_is_structurally_antimodal(qapp):
    p = CmdPanel("Mirror", FIELDS, command_id="mirror")
    assert p.findChild(QDialogButtonBox) is None        # no OK/Cancel ever


def test_panel_commits_per_boundary(qapp):
    seen = []
    p = CmdPanel("Mirror", FIELDS, command_id="mirror")
    p.values_committed.connect(lambda v, k: seen.append((k, dict(v))))
    fld = p._edits["d"]
    fld.edit.setText("9")
    fld._finish()
    assert seen[-1][0] == "mirror:d" and seen[-1][1]["d"] == 9.0
    p._edits["flip"].setChecked(True)                   # the click IS it
    assert seen[-1][1]["flip"] is True
    assert seen[-1][1]["side"] == "Right"               # combo default honoured


def test_panel_esc_aborts_and_commit_returns_values(qapp):
    results = []
    p = CmdPanel("Mirror", FIELDS, command_id="mirror")
    p.finished.connect(results.append)
    QTest.keyClick(p, Qt.Key.Key_Escape)
    assert results == [None]
    results.clear()
    p.btn_commit.click()
    assert results and isinstance(results[0], dict) and "d" in results[0]


def test_param_sheet_flows_into_expression_fields(qapp):
    p = CmdPanel("Mirror", FIELDS, command_id="mirror")
    p.set_param_values({"wall": 2.5})
    fld = p._edits["d"]
    fld.edit.setText("wall*4")
    fld._finish()
    assert p.value("d") == 10.0


def test_no_hex_literals_in_the_engine(qapp):
    import tracer.ui.cmdpanel as mod
    src = open(mod.__file__, encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines()
                     if not l.lstrip().startswith("#"))
    assert not re.search(r"#[0-9a-fA-F]{6}\b", body)    # M112's law, extended


# ---- G5: the first carrier - Mirror rides the panel (rung 2) ----------------

@pytest.fixture
def win(qapp, monkeypatch):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    monkeypatch.setattr(cmddialog, "_REMEMBERED", {})   # process-global
    monkeypatch.setattr(cmddialog, "_REMEMBER_ON", {})
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


def _lug_doc(w):
    w.new_document()
    w.doc.add(PrimitiveFeature(name="plate", kind="box",
                               dims={"dx": 20, "dy": 20, "dz": 5}))
    w.doc.add(PrimitiveFeature(name="lug", kind="box",
                               dims={"dx": 2, "dy": 8, "dz": 5},
                               placement=(1, 2, 5)))
    w.recompute()


def test_mirror_opens_a_live_panel_not_a_dialog(win, monkeypatch):
    _lug_doc(win)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("M163: Mirror must not ask")))
    win.action_mirror()
    p = win._cmd_panel
    assert isinstance(p, CmdPanel) and p.command_id == "mirror"
    assert list(p._edits) == ["src", "plane", "off"]
    n = len(win.doc.features)
    p.btn_commit.click()
    assert len(win.doc.features) == n + 1
    assert isinstance(win.doc.features[-1], MirrorFeature)
    assert win._cmd_panel is None             # committing closes the verb


def test_abort_leaves_no_feature_and_no_undo_step(win):
    _lug_doc(win)
    win.action_mirror()
    p = win._cmd_panel
    undo_n = len(win._undo)
    QTest.keyClick(p, Qt.Key.Key_Escape)
    assert len(win.doc.features) == 2         # nothing was built
    assert len(win._undo) == undo_n           # nothing was captured
    assert win._cmd_panel is None


def test_scrubbing_the_offset_ghosts_the_twin(win, monkeypatch):
    _lug_doc(win)
    ghosts = []
    monkeypatch.setattr(win.viewport, "preview_mesh",
                        lambda s: ghosts.append(s))
    win.action_mirror()
    p = win._cmd_panel
    fld = p._edits["off"]
    fld.edit.setText("6")
    fld._finish()                             # a discrete intention
    assert ghosts and ghosts[-1] is not None  # cosmetic twin, model intact
    assert len(win.doc.features) == 2
    p.btn_abort.click()
    assert ghosts[-1] is None                 # abort restores the mesh


def test_committed_values_are_remembered_next_time(win):
    _lug_doc(win)
    win.action_mirror()
    p = win._cmd_panel
    p._edits["src"].setCurrentText("lug")
    p._edits["plane"].setCurrentText("XY")
    fld = p._edits["off"]
    fld.edit.setText("7")
    fld._finish()
    p.btn_commit.click()
    assert cmddialog.remembered("mirror") == {"src": "lug", "plane": "XY",
                                              "off": 7.0}
    win.action_mirror()                       # reopen the verb
    p2 = win._cmd_panel
    assert p2._edits["off"].value_mm() == 7.0
    assert p2._edits["src"].currentText() == "lug"


def test_text_field_commits_verbatim(win):
    # M164 R4 engine seam: kind="text" is a QLineEdit row that commits
    # on editingFinished (the KiCad discrete-intention law, same shape
    # as the combo's one-click step) and its VALUE IS THE RAW STRING -
    # binding provenance is text an ExprField would eat on eval.
    seen = []
    p = CmdPanel("T", [dict(key="fx", kind="text", label="fx",
                            default="a*b")], command_id="t")
    p.values_committed.connect(lambda v, k: seen.append((v, k)))
    assert p._edits["fx"].text() == "a*b"
    assert p.values() == {"fx": "a*b"}
    p._edits["fx"].setText("  = wall*2 ")       # the panel NEVER strips
    p._edits["fx"].editingFinished.emit()       #  or rewrites: the verb
    assert seen and seen[-1] == ({"fx": "  = wall*2 "}, "t:fx")   # owns
    assert p.values() == {"fx": "  = wall*2 "}  #  its own grammar


def test_forgetful_command_skips_remember(win, monkeypatch):
    # M164 R3 engine law: remember_key=False opts OUT of BOTH directions -
    # no prefill, no store (the fixer must never carry a pick across
    # sketches).  None-key runs keep the Mirror remember law byte-live.
    from tracer.ui import cmdpanel as cp
    cmddialog._REMEMBERED["forgetverb"] = {"v": 5.0}    # fresh dicts (win)
    cmddialog._REMEMBER_ON["forgetverb"] = True
    real = cmddialog.remember
    calls = []

    def spy(k, v):
        calls.append(k)
        return real(k, v)
    monkeypatch.setattr(cmddialog, "remember", spy)
    p = cp.run(win, "forgetverb", "T",
               [dict(key="v", kind="double", label="v", default=1.0)],
               preview=lambda vals: None, commit=lambda vals: None,
               abort=lambda: None, remember_key=False)
    assert p._edits["v"].value_mm() == 1.0              # store NOT read
    p.btn_commit.click()
    assert calls == []                                  # store NOT written
    assert cmddialog._REMEMBERED == {"forgetverb": {"v": 5.0}}   # untouched
    p2 = cp.run(win, "remembverb", "T",                 # default verb:
                [dict(key="v", kind="double", label="v", default=1.0)],
                preview=lambda vals: None, commit=lambda vals: None,
                abort=lambda: None)                     #  law untouched
    p2.btn_commit.click()
    assert calls == ["remembverb"]                      # default path alive
    assert cmddialog.remembered("remembverb") == {"v": 1.0}


def test_prefill_fires_nothing(win):
    p = CmdPanel("Mirror", FIELDS, command_id="mirror")
    seen = []
    p.values_committed.connect(lambda v, k: seen.append(k))
    p.set_values({"d": 4.0, "side": "Left", "flip": True})
    assert seen == []                         # a prefill is not an act
    assert p.value("d") == 4.0 and p.value("side") == "Left"
    assert p.value("flip") is True


def test_a_new_verb_aborts_the_previous_panel(win, monkeypatch):
    _lug_doc(win)
    ghosts = []
    monkeypatch.setattr(win.viewport, "preview_mesh",
                        lambda s: ghosts.append(s))
    win.action_mirror()
    first = win._cmd_panel
    win.action_mirror()                       # reopen mid-verb
    assert win._cmd_panel is not first
    assert ghosts and ghosts[-1] is None      # the old verb cleaned up
