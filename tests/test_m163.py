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

from PySide6.QtCore import QPoint, QPointF, Qt, QSettings     # noqa: E402
from PySide6.QtGui import QWheelEvent                        # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialogButtonBox,      # noqa:
                               QLabel, QMessageBox)                # E402

from tracer.core import params                                # noqa: E402
from conftest import settle_panels                            # noqa: E402
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


# ---- G6 (W1/E1): ExprField wears the modal's setRange voice ----------------

def test_field_clamps_at_declared_bounds_like_the_modal(qapp):
    got = []
    f = ExprField(0.5, minimum=0.05, maximum=1.0, decimals=2)
    f.committed.connect(got.append)
    f.edit.setText("5")
    f._finish()                              # Enter
    assert f.value_mm() == 1.0               # clamped SILENTLY - setRange
    assert f.edit.text() == "1.00 mm"        #  never complains...
    assert got == [1.0]                      # ...and reads back clamped


def test_under_range_clamps_up_and_valid_values_pass_through(qapp):
    got = []
    f = ExprField(0.5, minimum=0.05, maximum=1.0, decimals=2)
    f.committed.connect(got.append)
    f.edit.setText("-2")
    f._finish()
    assert f.value_mm() == 0.05 and got == [0.05]   # envelope, not filter:
    f.edit.setText("0.5")                           #  a legal value rides
    f._finish()
    assert f.value_mm() == 0.5 and got == [0.05, 0.5]
    assert not f.is_invalid()                # red stays for PARSE failures


def test_wheel_scrub_stops_at_the_bound_and_goes_silent(qapp):
    got = []
    f = ExprField(19.0, minimum=0.0, maximum=20.0, step=1.0, decimals=1)
    f.committed.connect(got.append)
    f.edit.hasFocus = lambda: True           # the gate is hasFocus (G2)
    QApplication.sendEvent(f.edit, _wheel(f.edit, 120))
    assert got == [20.0]                     # last notch lands ON the max
    got.clear()
    QApplication.sendEvent(f.edit, _wheel(f.edit, 120))     # at the bound:
    assert got == []                         #  notch consumed, emits ZERO
    assert f.value_mm() == 20.0              #  (no-change law)


def test_decimals_and_suffix_shape_the_display(qapp):
    f = ExprField(3.0, decimals=1, suffix=" DIP")
    assert f.edit.text() == "3.0 DIP"        # the " mm" hardcode is dead
    f.set_value_mm(4.5)
    assert f.edit.text() == "4.5 DIP"        #  scrub speaks the suffix too
    g = ExprField(3.0)                       # bare: legacy trimmed voice
    assert g.edit.text() == "3 mm"           #  (decimals=None trims, but
    #  the default suffix still rides - E1b state, not a literal)


def test_make_passes_min_max_decimals_from_the_spec(qapp):
    p = CmdPanel("Clamp check", [dict(key="x", label="X", kind="double",
                                      min=0.05, max=1.0, decimals=2,
                                      default=2.0)])
    w = p._edits["x"]
    assert w.value_mm() == 1.0               # default clamps IN at open
    w.edit.setText("5")
    w._finish()
    assert p.values()["x"] == 1.0            # the wiring gate (_make E1)
    q = CmdPanel("voice", [dict(key="off", label="Off", kind="double",
                                default=0.0)])
    assert q._edits["off"].edit.text() == "0.00 mm"   # Mirror's row now
    #  speaks the modal's 2-decimal voice (ask()'s own default, cmddialog)


# ---- G7 (W1/E2): the remember opt-out, pinned on the real run() ------------

def test_remember_key_false_leaves_the_store_untouched(win, qapp):
    cmdpanel.run(win, "forget_me", "Forget",
                 [dict(key="a", label="A", kind="double", default=1.0)],
                 commit=lambda v: None, abort=lambda: None,
                 remember_key=False)
    win._cmd_panel.btn_commit.click()
    settle_panels(qapp)                      # reap now - the law (W1/m86)
    assert cmddialog._REMEMBERED == {}       # the store never heard of it
    assert cmddialog._REMEMBER_ON == {}
    assert cmddialog.remembered("forget_me") is None


def test_no_remember_key_still_falls_back_to_the_command_id(win, qapp):
    cmdpanel.run(win, "plain_fall", "Plain",
                 [dict(key="a", label="A", kind="double", default=1.0)],
                 commit=lambda v: None, abort=lambda: None)
    win._cmd_panel.btn_commit.click()
    settle_panels(qapp)                      # reap now - the law (W1/m86)
    assert cmddialog.remembered("plain_fall") == {"a": 1.0}


# ---- G8 (W1/E3): the readout row - the box without the modal ----------------

def test_readout_row_lies_hidden_until_written(qapp):
    p = CmdPanel("Silent", FIELDS)
    lbl = p.findChild(QLabel, "cmd_readout")
    assert lbl is not None and lbl.isHidden()
    p.set_readout("Volume: 1 mm\u00b3")
    assert not lbl.isHidden() and "Volume" in lbl.text()
    p.set_readout("")                        # empty hides it again
    assert lbl.isHidden()


def test_readout_seeds_at_open_and_moves_only_on_boundaries(win, qapp):
    calls = []

    def readout(v):
        calls.append(v["a"])
        return f"v={v['a']}"
    cmdpanel.run(win, "ro_test", "Readout",
                 [dict(key="a", label="A", kind="double", default=1.0)],
                 commit=lambda v: None, abort=lambda: None,
                 readout=readout, remember_key=False)
    p = win._cmd_panel
    assert calls == [1.0]                    # seeded at open - exactly ONCE
    assert p.findChild(QLabel, "cmd_readout").text() == "v=1.0"
    p._edits["a"].edit.setText("9")          # keystrokes are DEAF (KiCad)
    assert calls == [1.0]
    p._edits["a"]._finish()                  # the boundary speaks ONCE
    assert calls == [1.0, 9.0]
    p.btn_commit.click()                     # closing is not a boundary:
    settle_panels(qapp)                      #  ...and is reaped at once
    assert calls == [1.0, 9.0]               #  run() never re-invokes it


def test_run_without_preview_is_fine(win, qapp):  # class-0: report IS it
    done = []
    cmdpanel.run(win, "noprev", "NoPreview",
                 [dict(key="a", label="A", kind="double", default=2.0)],
                 commit=lambda v: done.append(v["a"]),
                 abort=lambda: None,
                 readout=lambda v: f"r{v['a']}", remember_key=False)
    p = win._cmd_panel
    assert p.findChild(QLabel, "cmd_readout").text() == "r2.0"
    w = p._edits["a"]
    w.edit.setText("5")
    w._finish()
    assert p.findChild(QLabel, "cmd_readout").text() == "r5.0"
    p.btn_commit.click()
    assert done == [5.0] and win._cmd_panel is None


# ---- G9 (W1 carriers): the four migrated doors ------------------------------

def _banned_modals(monkeypatch):
    """Panel-era law: neither ask() nor a results box survives on these
    paths - touching one FAILS by name (m163's own :245 idiom)."""
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: (_ for _ in ()).
                        throw(AssertionError("M163: ask is BANNED here")))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: (_ for _ in ()).
                        throw(AssertionError("M163: box is BANNED here")))


def _cube_doc(win):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="cube", kind="box",
                                 dims={"dx": 20, "dy": 20, "dz": 20}))
    win.recompute()


def _pick_combo(p, key, text):
    w = p._edits[key]                        # the combo's boundary IS the
    w.setCurrentText(text)                   #  activated click - program-
    w.activated.emit(w.currentIndex())       #  matic set is silent (:304)


def test_mass_properties_rides_the_panel_and_reads_its_report(
        win, qapp, monkeypatch):
    s = QSettings()
    prior = s.value("materials/density", None)    # restore-as-found law:
    s.setValue("materials/density", "PETG (1.27)")  #  this gate owns its
    s.sync()                                      #  baseline AND its exit
    _cube_doc(win)
    _banned_modals(monkeypatch)
    win.action_mass_properties()
    p = win._cmd_panel
    assert p.command_id == "mass_properties"
    lbl = p.findChild(QLabel, "cmd_readout")
    assert "Volume:" in lbl.text() and "Mass" in lbl.text()
    _pick_combo(p, "material", "Steel (7.85)")
    # 8000 mm3 of steel at 7.85 g/cm3 = 62.80 g - while the combo is
    # still in your hand, ZERO writes happened
    assert "62.80 g" in lbl.text()
    assert QSettings().value("materials/density") == "PETG (1.27)"
    p.btn_commit.click()
    assert QSettings().value("materials/density") == "Steel (7.85)"
    assert "62.80 g" in win.status.currentMessage()
    assert win._cmd_panel is None
    settle_panels(qapp)                           # reap the panel INSIDE
    s = QSettings()                               #  this test - its dead
    if prior is None:                             #  QSettings would else
        s.remove("materials/density")             #  resurrect Steel via
    else:                                         #  destructor sync and
        s.setValue("materials/density", prior)    #  stomp the next
    s.sync()                                      #  writer (CI bit m86)


def test_mass_properties_remembers_nothing(win, qapp, monkeypatch):
    s = QSettings()
    prior = s.value("materials/density", None)     # restore-as-found law
    _cube_doc(win)
    _banned_modals(monkeypatch)
    win.action_mass_properties()
    p = win._cmd_panel
    p.btn_commit.click()                     # default material commits
    assert cmddialog.remembered("mass_properties") is None
    assert "mass_properties" not in cmddialog._REMEMBERED
    settle_panels(qapp)
    s = QSettings()
    if prior is None:
        s.remove("materials/density")
    else:
        s.setValue("materials/density", prior)
    s.sync()


def test_document_measures_readout_speaks_the_pending_unit(win, qapp,
                                                           monkeypatch):
    _cube_doc(win)
    _banned_modals(monkeypatch)
    win.action_document_measures()
    p = win._cmd_panel
    assert p.command_id == "document_measures"
    lbl = p.findChild(QLabel, "cmd_readout")
    _pick_combo(p, "unit", "Inch (in)")
    assert "in \u2014 0.787402 in \u00d7" in lbl.text()   # the PENDING
    assert "mm" not in lbl.text()            #  unit's numbers, mm-free...
    assert win.doc.units == "mm"             # ...on a zero-write preview
    p.btn_commit.click()                     # the write is the boundary
    settle_panels(qapp)
    assert win.doc.units == "inch"
    assert "Document measures: in" in win.status.currentMessage()
    assert cmddialog.remembered("document_measures") is None


def test_pick_radius_is_commit_only_and_clamped(win, qapp):
    s = QSettings()
    orig = s.value("pick/radius", None)              # leave it as found
    win.viewport.set_pick_radius(3.0)                # deterministic default
    win.action_pick_radius()
    p = win._cmd_panel
    assert p._edits["r"].edit.text() == "3.0 DIP"     # E1b: no " mm" leak
    w = p._edits["r"]
    w.edit.setText("99")
    w._finish()
    assert w.value_mm() == 20.0              # E1 clamp == viewport's own
    assert win.viewport.pick_radius == 3.0   # commit-ONLY: the boundary
    #                                          touched the FIELD, not the
    p.btn_commit.click()                     #  viewport (preview renders)
    assert win.viewport.pick_radius == 20.0
    assert float(QSettings().value("pick/radius")) == 20.0
    win.action_pick_radius()                 # separate case: cancel path
    p2 = win._cmd_panel
    p2._edits["r"].edit.setText("11")
    p2._edits["r"]._finish()
    p2.btn_abort.click()
    assert win.viewport.pick_radius == 20.0  # defensive restore, value
    assert "Pick radius cancelled" in win.status.currentMessage()
    assert cmddialog.remembered("pick_radius") is None
    settle_panels(qapp)                    # reap both panels BEFORE the
    if orig is None:                       #  restore - a zombie's dead
        s.remove("pick/radius")            #  QSettings would else
    else:                                  #  resurrect its value onto
        s.setValue("pick/radius", orig)    #  the suite (m86 law)
    s.sync()


def test_appearance_preview_tints_the_renderer_never_the_doc(
        win, qapp, monkeypatch):
    from tracer.core.appearance import MATERIALS
    _cube_doc(win)
    _banned_modals(monkeypatch)
    win.action_appearance()
    p = win._cmd_panel
    n0 = len(win._undo)
    _pick_combo(p, "preset", "Brass")
    assert tuple(win._renderer._base_override) == \
        tuple(MATERIALS["Brass"])            # paint moved...
    w = p._edits["opacity"]
    w.edit.setText("0.5")
    w._finish()
    assert win._renderer._base_alpha == 0.5  #  live on every boundary
    assert win.doc.appearance is None        # the DOC never heard
    assert len(win._undo) == n0              # no capture until Commit
    p.btn_abort.click()
    settle_panels(qapp)
    assert win._renderer._base_override is None      # paint re-synced from
    assert "Appearance cancelled" in win.status.currentMessage()   # truth


def test_appearance_remember_merges_then_prefills_the_panel(
        win, qapp, monkeypatch):
    _cube_doc(win)
    _banned_modals(monkeypatch)
    win.action_appearance()
    p = win._cmd_panel
    _pick_combo(p, "preset", "Brass")
    w = p._edits["opacity"]
    w.edit.setText("0.8")
    w._finish()
    p.btn_commit.click()
    assert cmddialog.remembered("appearance") == {"preset": "Brass",
                                                  "opacity": 0.8}
    cmddialog.remember("appearance", {"opacity": 0.5})   # the merge store
    win.action_appearance()                  # folds, never replaces
    p2 = win._cmd_panel
    assert p2._edits["opacity"].value_mm() == 0.5        # fresh key wins
    assert p2._edits["preset"].currentText() == "Brass"  # kept from merge
    p2.btn_abort.click()
    settle_panels(qapp)                                  # reap before exit
