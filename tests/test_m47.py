"""M47 — unified command dialogs: one Fusion-style shell (header strip,
grouped fields, Remember Values, OK/Cancel) replaces the chains of
QInputDialog prompts.  Circular Pattern's five prompts are now ONE
dialog; Linear Pattern, Mirror and Construction Plane likewise."""
import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog,          # noqa: E402
                               QDoubleSpinBox, QGroupBox, QSpinBox)

from tracer.ui import cmddialog                                           # noqa: E402
from tracer.ui.cmddialog import CommandDialog                             # noqa: E402
from tracer.ui.mainwindow import MainWindow                               # noqa: E402
from tracer.ui.renderer import SceneRenderer                              # noqa: E402


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
    r.ctx.release()


@pytest.fixture(autouse=True)
def _clean_memory():
    yield
    for k in ("construction_plane", "circular_pattern", "linear_pattern",
              "mirror", "m47_test"):
        cmddialog._REMEMBERED.pop(k, None)
        cmddialog._REMEMBER_ON.pop(k, None)


# ---- the shell -------------------------------------------------------------------

def test_shell_anatomy(qapp):
    d = CommandDialog("Extrude", remember_key="m47_test")
    d.add_combo("dir", "Direction", ["Normal", "Both"], group="Type")
    d.add_double("dist", "Distance", 5.0, group="Extents")
    d.add_int("n", "Copies", 2, mn=1, mx=9, group="Extents")
    d.add_check("sym", "Symmetric", group="Extents")
    groups = {g.title() for g in d.findChildren(QGroupBox)}
    assert {"Type", "Extents"} <= groups
    assert any(cb.text() == "Remember Values"
               for cb in d.findChildren(QCheckBox))
    vals = d.values()
    assert vals == {"dir": "Normal", "dist": 5.0, "n": 2, "sym": False}
    assert isinstance(d.value("dist"), float)
    assert isinstance(d.value("n"), int)


def test_remember_values_round_trip(qapp):
    d = CommandDialog("Place", remember_key="m47_test")
    d.add_double("x", "X", 1.0)
    d._fields["x"].setValue(23.5)
    d._remember.setChecked(True)
    d.accept()
    assert cmddialog._REMEMBERED["m47_test"] == {"x": 23.5}

    again = CommandDialog("Place", remember_key="m47_test")
    again.add_double("x", "X", 1.0)
    again._prefill()
    assert again.value("x") == 23.5     # remembered

    off = CommandDialog("Place", remember_key="m47_test")
    off.add_double("x", "X", 1.0)
    off._prefill()
    assert off.value("x") == 23.5       # state persisted: still on
    off._remember.setChecked(False)
    off.accept()
    assert "m47_test" not in cmddialog._REMEMBERED


def test_ask_returns_none_on_cancel(qapp, monkeypatch):
    from tracer.ui.cmddialog import CommandDialog
    monkeypatch.setattr(CommandDialog, "exec_",
                        lambda self: QDialog.Rejected)
    assert cmddialog.ask(None, "X", [dict(key="a", label="A",
                                          kind="double", default=1.0)]) is None


def test_shell_dropins_match_qinputdialog_contract(qapp, monkeypatch):
    """Shell.getDouble/getInt/getItem/getText accept the QInputDialog
    call shape and return (value, ok) — the M47b sweep swaps one for
    the other without touching call sites."""
    from tracer.ui.cmddialog import CommandDialog
    answers = {}

    def fake_exec(dialog):
        w = dialog._fields["v"]
        if hasattr(w, "setValue") and answers.get("num") is not None:
            w.setValue(answers["num"])
        if hasattr(w, "setCurrentIndex") and answers.get("pick") is not None:
            w.setCurrentIndex(answers["pick"])
        if hasattr(w, "setText") and answers.get("txt") is not None:
            w.setText(answers["txt"])
        return QDialog.Accepted
    monkeypatch.setattr(CommandDialog, "exec_", fake_exec)
    answers["num"] = 7.5
    v, ok = cmddialog.Shell.getDouble(None, "Extrude", "Height (mm):", 5.0,
                                      0.01, 1e5, 2)
    assert ok and v == 7.5
    answers["num"] = 4
    v, ok = cmddialog.Shell.getInt(None, "Pattern", "Count:", 3, 2, 500)
    assert ok and v == 4
    answers["pick"] = 1
    v, ok = cmddialog.Shell.getItem(None, "Mirror", "Plane:",
                                    ["YZ", "XZ", "XY"], 0, False)
    assert ok and v == "XZ"
    answers["txt"] = "bearing"
    v, ok = cmddialog.Shell.getText(None, "Rename", "Name:", "old")
    assert ok and v == "bearing"


# ---- the migrated commands are ONE dialog each ------------------------------------

def _capture_asks(win, monkeypatch, reply):
    calls = []

    def fake_ask(parent, title, fields, remember_key=None):
        calls.append((title, [f["key"] for f in fields],
                      [f.get("group", "") for f in fields]))
        return dict(reply)
    monkeypatch.setattr(cmddialog, "ask", fake_ask)
    return calls


def test_circular_pattern_is_one_dialog(win, monkeypatch):
    win.doc.add_plate("plate", 40, 40, 5)
    win.doc.add_cylinder("lug", 3, 8, center=(30, 20), op="union")
    win.recompute()
    calls = _capture_asks(win, monkeypatch, {
        "src": "lug", "cx": 0.0, "cy": 0.0, "ang": 360.0, "count": 6})
    win.action_circular_pattern()
    assert len(calls) == 1, calls
    title, keys, groups = calls[0]
    assert title == "Circular Pattern"
    assert keys == ["src", "cx", "cy", "ang", "count"]      # five, together
    assert groups == ["Object", "Axis", "Axis", "Pattern", "Pattern"]
    assert len([f for f in win.doc.features
                if type(f).__name__ == "CircularPatternFeature"]) == 1


def test_linear_pattern_is_one_dialog(win, monkeypatch):
    win.doc.add_plate("plate", 40, 40, 5)
    win.doc.add_cylinder("lug", 3, 8, center=(30, 20), op="union")
    win.recompute()
    calls = _capture_asks(win, monkeypatch, {
        "src": "lug", "dx": 10.0, "dy": 0.0, "dz": 0.0, "count": 3})
    win.action_linear_pattern()
    assert len(calls) == 1
    assert calls[0][1] == ["src", "dx", "dy", "dz", "count"]


def test_mirror_ribbon_is_one_dialog(win, monkeypatch):
    win.doc.add_plate("plate", 40, 40, 5)
    win.doc.add_cylinder("lug", 3, 8, center=(30, 20), op="union")
    win.recompute()
    calls = _capture_asks(win, monkeypatch,
                          {"src": "lug", "plane": "YZ", "off": 0.0})
    win.action_mirror()
    assert len(calls) == 1
    assert calls[0][1] == ["src", "plane", "off"]
    assert any(type(f).__name__ == "MirrorFeature"
               for f in win.doc.features)


def test_mirror_from_menu_skips_the_object_field(win, monkeypatch):
    """The feature-menu flow already knows the feature and plane: only
    the offset is asked — no redundant dropdowns (Fusion's context)."""
    win.doc.add_plate("plate", 40, 40, 5)
    lug = win.doc.add_cylinder("lug", 3, 8, center=(30, 20), op="union")
    win.recompute()
    calls = _capture_asks(win, monkeypatch, {"off": 12.0})
    win._mirror_feature(lug, "YZ")
    assert len(calls) == 1 and calls[0][1] == ["off"]
    mir = [f for f in win.doc.features if type(f).__name__ == "MirrorFeature"]
    assert len(mir) == 1 and mir[0].offset == 12.0


# ---- proof of life -------------------------------------------------------------------

def test_screenshot_proof(win, qapp, monkeypatch):
    real_ask = cmddialog.ask

    def auto_accept(parent, title, fields, remember_key=None):
        dlg_state = {}

        def fake_exec(dialog):
            dlg_state["d"] = dialog
            return QDialog.Accepted
        monkeypatch.setattr(CommandDialog, "exec_",
                            lambda self: fake_exec(self))
        result = real_ask(parent, title, fields, remember_key)
        win._m47_dialog = dlg_state.get("d")
        return result
    monkeypatch.setattr(cmddialog, "ask", auto_accept)
    win.doc.add_plate("plate", 40, 40, 5)
    win.doc.add_cylinder("lug", 3, 8, center=(30, 20), op="union")
    win.recompute()
    win.action_circular_pattern()
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win._m47_dialog.grab().save(f"{out}/m47_command_dialog.png")
