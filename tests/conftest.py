import os

import pytest

# Hard isolation for the desktop session (user's Hyprland must never see a
# test window or XWayland wake-up): force Qt offscreen, drop the gtk3
# platform theme (it reaches for X settings/XWayland from inside Qt
# processes — that was thrashing the compositor), and remove every display
# handle so even an accidental fallback (wayland client, GLX/X11, GTK)
# fails inside the test process instead of reaching the session.
# The real app is launched separately with its normal environment.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("QT_QPA_PLATFORMTHEME", None)
os.environ.pop("WAYLAND_DISPLAY", None)
os.environ.pop("DISPLAY", None)


# ---- browser helpers ---------------------------------------------------------
# M43 gave the browser Fusion's folder anatomy (Origin / Bodies / Sketches /
# Construction), so feature nodes are no longer direct children of the root.
# Tests should walk the tree instead of hard-coding positions.

def tree_texts(win):
    """Every browser node label, depth-first."""
    out = []

    def walk(node):
        for i in range(node.childCount()):
            ch = node.child(i)
            out.append(ch.text(0))
            walk(ch)
    walk(win.rail.tree.invisibleRootItem())
    return out


def feature_rows(win):
    """The feature nodes in document order, wherever the folders put them."""
    from PySide6.QtCore import Qt
    out = []

    def walk(node):
        for i in range(node.childCount()):
            ch = node.child(i)
            role = ch.data(0, Qt.UserRole)
            if role and role[0] == "feature":
                out.append(ch)
            walk(ch)
    walk(win.rail.tree.invisibleRootItem())
    return out


def script_cmd(monkeypatch, values):
    """Script the unified command dialog (M47) to answer with `values`,
    keyed by field key — the cmddialog.ask() replacement for headless
    runs (mirrors what the old QInputDialog patches did per prompt)."""
    from tracer.ui import cmddialog
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda parent, title, fields, remember_key=None: dict(values))


def script_cmd_cancel(monkeypatch):
    """Every command dialog answers Cancel."""
    from tracer.ui import cmddialog
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: None)


@pytest.fixture(scope="session", autouse=True)
def _isolate_recovery_dir():
    """No headless test may poison the user's real crash-recovery folder
    — an autosave written by pytest would haunt their next app start.
    Point every test run at a temp directory and restore after."""
    from PySide6.QtCore import QSettings
    s = QSettings()
    key = "paths/recovery_dir"
    saved = s.value(key, None)
    import shutil
    import tempfile
    d = tempfile.mkdtemp(prefix="tracer-recovery-")
    s.setValue(key, d)
    s.sync()
    yield d
    if saved is None:
        s.remove(key)
    else:
        s.setValue(key, saved)
    s.sync()
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def _no_real_command_dialogs(monkeypatch):
    """Hangs happen silently when an unpatched flow reaches a real modal
    dialog (exec_ blocks forever headless). Fail loudly instead — the
    title names the culprit command. Tests that legitimately drive the
    dialog monkeypatch exec_ themselves and override this."""
    try:
        from tracer.ui.cmddialog import CommandDialog
    except Exception:
        return
    import pytest as _pt

    def _boom(self, *a, **k):
        raise _pt.fail(
            f"real command dialog reached in headless test: "
            f"{self.windowTitle()!r} — script it via conftest.script_cmd "
            f"or patch Shell")
    monkeypatch.setattr(CommandDialog, "exec_", _boom)
