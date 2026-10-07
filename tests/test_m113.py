"""M113: the key layer + command search contract.

S finds everything; the tables are the single source of truth; every
registered target actually exists; the sketch canvas owns its alphabet
while the model answers the rest.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                        # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit                # noqa: E402

from tracer.ui.commands import (MODEL_KEYS, SKETCH_KEYS,              # noqa: E402
                                collect_commands, fuzzy_score, rank)


@pytest.fixture
def qapp():
    yield QApplication.instance() or QApplication([])


# ---- pure logic ----------------------------------------------------------------
def test_fuzzy_scores_prefix_over_midword():
    assert fuzzy_score("ex", "Extrude profile") > fuzzy_score("ex",
                                                              "Text export")
    assert fuzzy_score("xy", "Extrude") is None          # subsequence miss
    assert fuzzy_score("", "anything") == 0.0


def test_rank_orders_by_score():
    from tracer.ui.commands import Command
    cmds = [Command("Draw axis", "Sketch", "", lambda: True, lambda: True),
            Command("Extrude profile", "Sketch", "", lambda: True,
                    lambda: True)]
    out = rank("ex", cmds)
    assert out and out[0].label == "Extrude profile"


def test_tables_keep_fusion_ownership():
    # S and / are the toolbox's, E is extrude's — never the sketch's
    assert "S" not in SKETCH_KEYS and "/" not in SKETCH_KEYS
    assert "E" not in SKETCH_KEYS
    # Fusion's sketch core keys are present, exactly as [V]-verified
    for k in ("L", "R", "C", "D", "O", "P", "T", "X"):
        assert k in SKETCH_KEYS
    # Enter finishes a sketch (Fusion's Finish Sketch), Esc escapes
    assert "Enter" in SKETCH_KEYS and "Esc" in SKETCH_KEYS


def test_every_model_key_target_resolves():
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.viewport import Viewport
    for key, (label, target) in MODEL_KEYS.items():
        kind, sep, arg = target.partition(":")
        if sep:
            assert kind in ("view", "style", "viewport", "layout"), key
            if kind == "viewport":
                assert hasattr(Viewport, arg), f"{key} -> {target}"
        else:
            # action_* methods are class-level; act_* QActions are built
            # per instance (pinned live by test_all_key_actions_built)
            if not target.startswith("act_"):
                assert hasattr(MainWindow, target), f"{key} -> {target}"


# ---- the live window -------------------------------------------------------------
@pytest.fixture
def win(qapp):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
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


def test_key_strings_match_table_spellings(win):
    assert win._key_str(Qt.Key_B, Qt.AltModifier | Qt.ControlModifier) \
        == "Ctrl+Alt+B"
    assert win._key_str(Qt.Key_C, Qt.ShiftModifier) == "Shift+C"
    assert win._key_str(Qt.Key_E, Qt.KeyboardModifier.NoModifier) == "E"
    assert win._key_str(Qt.Key_F6, Qt.KeyboardModifier.NoModifier) == "F6"


def test_dispatch_answers_known_and_ignores_strangers(win):
    N = Qt.KeyboardModifier.NoModifier
    assert win._dispatch_key(Qt.Key_F6, N)               # fit
    assert win._dispatch_key(Qt.Key_2, N)                # top view
    assert win._dispatch_key(Qt.Key_J, N) is False       # unowned
    assert win._dispatch_key(Qt.Key_9, N) is False


def test_layout_layer_toggles(win):
    N = Qt.KeyboardModifier.NoModifier
    CA = Qt.AltModifier | Qt.ControlModifier
    before = win.rail.isVisible()
    assert win._dispatch_key(Qt.Key_B, CA)
    assert win.rail.isVisible() != before
    cube0 = win.viewport.show_cube
    assert win._dispatch_key(Qt.Key_V, CA)
    assert win.viewport.show_cube != cube0
    assert win._dispatch_key(Qt.Key_R, CA)               # reset
    assert win.rail.isVisible() and win.viewport.show_cube


def test_palette_finds_everything_and_runs_it(win, qapp):
    cmds = collect_commands(win)
    labels = [c.label for c in cmds]
    assert any("Hole" in l for l in labels)
    assert any("Command search" == l for l in labels)    # searchable too
    grid = win._renderer.show_grid
    win.open_command_search()
    qapp.processEvents()
    win._palette.edit.setText("toggle grid")
    qapp.processEvents()
    assert win._palette.list.count() >= 1
    win._palette.run_current()
    qapp.processEvents()
    assert win._renderer.show_grid != grid               # it ran


def test_S_and_slash_actions_are_installed(win):
    shorts = {a.shortcut().toString() for a in win.actions()
              if not a.shortcut().isEmpty()}
    assert "S" in shorts and "/" in shorts


def test_all_key_actions_built(win):
    """act_* targets are instance QActions — every one must exist and
    the key table must not reference stale members."""
    for key, (label, target) in MODEL_KEYS.items():
        if ":" not in target and target.startswith("act_"):
            act = getattr(win, target, None)
            assert act is not None, f"{key} -> {target} missing"
            assert callable(getattr(act, "trigger", None))


def test_text_fields_sleep_the_keys(win, qapp):
    # Fusion rule, free from Qt: while a text field has focus it CLAIMS
    # printable keys from the shortcut system (typing beats commands)
    from PySide6.QtGui import QKeyEvent
    edit = QLineEdit(win)
    edit.setEnabled(True)
    edit.setFocus()
    qapp.processEvents()
    ev = QKeyEvent(QKeyEvent.Type.ShortcutOverride, Qt.Key_S,
                   Qt.KeyboardModifier.NoModifier, "s")
    edit.event(ev)
    assert ev.isAccepted()          # the editor takes the key, not S
    edit.setText("typed s")
    assert edit.text() == "typed s"
    edit.deleteLater()


def test_sketch_claim_set_is_honest():
    from tracer.ui.sketcheditor import _CLAIM_TEXT
    assert "l" in _CLAIM_TEXT and "x" in _CLAIM_TEXT
    assert "s" not in _CLAIM_TEXT and "e" not in _CLAIM_TEXT
    assert "/" not in _CLAIM_TEXT                       # / = search
