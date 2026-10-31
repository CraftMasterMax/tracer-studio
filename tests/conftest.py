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


def settle_panels(app):
    """M163 harness law: processEvents() alone does NOT reap a panel's
    deleteLater(); a half-dead panel can keep a handler's QSettings alive
    past its test, and that instance's destructor sync() re-stamps stale
    state OVER later writers (the CI one-process bite: Steel from m163
    resurrected over m71's PLA and killed m86). Drain deferred deletes
    NOW, inside the test that owns the value."""
    from PySide6.QtCore import QEvent
    for _ in range(3):
        app.processEvents()
        app.sendPostedEvents(None, QEvent.DeferredDelete)


def script_panel(monkeypatch, values):
    """M163: answer the LIVE command panel with `values` - preview then
    commit, immediately (the cmdpanel.run twin of script_cmd).
    M163 W1: `preview` may be None (class-0 commands); a `readout` is
    captured onto parent._panel_readout - the headless twin of the
    panel's report row."""
    from tracer.ui import cmdpanel

    def fake(parent, command_id, title, fields, *, preview=None, commit,
             abort, remember_key=None, readout=None):
        if preview is not None:
            preview(dict(values))
        if readout is not None:
            parent._panel_readout = readout(dict(values))
        commit(dict(values))
        return None
    monkeypatch.setattr(cmdpanel, "run", fake)


def script_panel_cancel(monkeypatch):
    """The live command panel answers Abort."""
    from tracer.ui import cmdpanel

    def fake(parent, command_id, title, fields, *, preview=None, commit,
             abort, remember_key=None, readout=None):
        abort()
        return None
    monkeypatch.setattr(cmdpanel, "run", fake)


def script_dim_edit(monkeypatch, text):
    """M165: answer the INLINE chip editor with `text` — patches the
    dimedit.open seam so _apply_dim_edit runs immediately (the exact
    Enter commit path).  The dimedit twin of script_panel above: the
    amended m5/m17/m89/m98/m164-r4 pins re-target in one line each.
    Creates no widget; the M90 drop and the rung-4 ring live in the
    canvas's _open_dim_editor, which still runs around the seam."""
    from tracer.ui import dimedit

    def fake(canvas, c):
        canvas._apply_dim_edit(c, text)
        return None
    monkeypatch.setattr(dimedit, "open", fake)


def place_dim(canvas, c=None):
    """M175 R2: complete the PLACE gesture the way a hand does - paint
    the ghost, click its rect. Birth alone only ARMS (the newborn has
    been following the cursor); this click settles it and opens the
    value field - so with script_dim_edit patched FIRST, the place-click
    is the moment the scripted number is ANSWERED. Returns the
    constraint placed (None if nothing was armed)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    c = c if c is not None else canvas._dim_place
    if c is None:
        return None
    canvas.grab()                          # fresh paint == fresh hits
    rect = next((r for r, cc in canvas._dim_hits if cc is c), None)
    QTest.mousePress(canvas, Qt.LeftButton, Qt.NoModifier,
                     rect.center().toPoint())
    QTest.mouseRelease(canvas, Qt.LeftButton, Qt.NoModifier,
                       rect.center().toPoint())
    return c


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
