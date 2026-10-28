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
from tracer.ui import theme                                   # noqa: E402
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
