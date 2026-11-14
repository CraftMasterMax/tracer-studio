import os

import pytest

# ---- SETTINGS ISOLATION LAW (M201 R41 v3 root-cause, 2026-11-14) -----------
# CI run 43592792796 died with ONE disease and TWO faces. Windows named five
# real failures — every one a QSettings round-trip (palette promote/identity/
# law/open-near + the knob): the app-wide QSettings() DEFAULT constructor with
# NO organization/application name set lands tests on an anonymous per-
# platform backend, and the Windows face of it returns None and string-instead-
# of-list where the Linux ini face round-trips fine. Ubuntu's face was the
# 45-minute burn (log lost again): xdist workers are separate PROCESSES sharing
# that ONE store file, and Qt file-locks it — lock contention waits forever
# headless. The m236/m237 dialogs joining the suite this rung shifted the
# worker/file map AND added remember-key traffic: both faces surfaced at once.
# THE CURE: one private settings store PER TEST PROCESS, IniFormat in a temp
# dir (identical backend on every platform, zero cross-process sharing, and
# headless can never touch a real user's config). Production keeps its names
# (app.py); tests keep theirs. The assert below makes a failed isolation RED
# with the whole story instead of quietly shared.
_SETTINGS_DIR = None


@pytest.fixture(scope="session", autouse=True)
def _isolate_settings_store():
    """Every test process gets its own fresh IniFormat store in a temp dir."""
    global _SETTINGS_DIR
    import shutil
    import tempfile

    from PySide6.QtCore import QCoreApplication, QSettings
    _SETTINGS_DIR = tempfile.mkdtemp(prefix="tracer-settings-")
    # names BEFORE any QSettings() exists (static — no app instance needed)
    QCoreApplication.setOrganizationName("tracer-cad")
    QCoreApplication.setApplicationName("Tracer Studio")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope,
                      _SETTINGS_DIR)
    probe = QSettings()
    assert os.path.realpath(probe.fileName()).startswith(
        os.path.realpath(_SETTINGS_DIR)), (
        f"settings isolation FAILED: QSettings() file is "
        f"{probe.fileName()!r}, not inside {_SETTINGS_DIR!r} — a shared "
        f"store means Windows None-reads and Linux lock-hangs (R41 v3)")
    yield
    shutil.rmtree(_SETTINGS_DIR, ignore_errors=True)


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

# ---- HARNESS TRUTH LAW (M201 R39 root-cause) --------------------------------
# The app is EDITABLE-INSTALLED in the venv (a meta-path finder maps the
# top-level `tracer` name to ~/tracer-studio). A worktree run can therefore
# silently import the MAIN checkout's code: test_m185's own absolute-path
# shim made an m185-alone run test R38 chrome while the drain's other
# chunks tested the branch - "order-dependent pollution" that was really
# TWO CODEBASES mixed by collection order. A test process must run against
# the tree its tests live in: conftest loads BEFORE every test module, so
# pinning the import HERE wins for the whole process - and the assert
# turns a wrong-tree run RED with the whole story instead of quietly
# green on borrowed code.
import pathlib
import sys

_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import tracer as _tracer                                          # noqa: E402
assert str(pathlib.Path(_tracer.__file__).resolve()).startswith(
    _ROOT + os.sep), (
        f"tests/conftest.py lives in {_ROOT} but `tracer` imported from "
        f"{_tracer.__file__} - this run would test the WRONG tree")


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


def script_extrude_door(monkeypatch, height, direction="one",
                        measurement="whole", height2=0.0, offset=0.0,
                        op="Join", wall=0.0, wall_location="center",
                        extent="distance", flip=False):
    """M201 R3: answer the GROWN extrude creation door - ONE dialog
    (title "Extrude", [SLD-REF-EXTRUDE] Direction row + the house's
    one number + the page's two conditional siblings). Any OTHER
    dialog title is delegated to the ask that was patched BEFORE this
    call (script_cmd etc.), so order is law: script the rest first,
    wrap the door last. Records born through the resting reply speak
    the door's legacy voice - direction "one" is what the one-number
    door always birthed. M201 R4: the door READS the page's Offset
    row too (page order: Start above Direction) - the reply grows it
    at 0.0, "Profile Plane", the start every repaid test was born
    with. M201 R5: and the Operation row - answered "Join" (what this
    door has always birthed off-face); a reply key the door did not
    open (a FACE sketch, where the probe owns operation) is simply
    never read, so one coin serves both doors. M201 R8: and the
    thin-wall family (page order: Wall Thickness + Wall Location
    after the distance rows) - the reply grows them at 0.0/"center",
    and 0.0 IS the page's Type "Extrude", the whole area every
    repaid test was born with (the reader's .get fallbacks make even
    a reply dict WITHOUT the new keys speak it - zero rewrites)."""
    from tracer.ui import cmddialog
    prior = cmddialog.ask

    def routed(parent, title, fields, remember_key=None):
        if title == "Extrude":
            return dict(height=float(height), direction=direction,
                        measurement=measurement, height2=float(height2),
                        offset=float(offset), op=op,
                        wall=float(wall), wall_location=wall_location,
                        extent=str(extent), flip=bool(flip))
        return prior(parent, title, fields, remember_key=remember_key)
    monkeypatch.setattr(cmddialog, "ask", routed)


def script_revolve_door(monkeypatch, angle=360.0, extent="Full",
                        op="Join"):
    """M201 R6: answer the GROWN revolve creation door - ONE dialog
    (title "Revolve", [SLD-REF-REVOLVE] Extent Type / Angle /
    Operation rows; Direction stays UNPROMISED - the page splits no
    angle across the profile plane and the kernel sweeps one way).
    Same router law as script_extrude_door: wrap the door LAST, other
    titles delegate to whatever ask was patched BEFORE this call. The
    resting reply is the door's LEGACY voice: extent "Full" writes
    angle 360.0 - what the old getDouble door always birthed (the
    page itself defines Full as 360 degrees; NUMERIC-ENCODES-EXTENT) -
    and op "Join" is what the fold has always folded. A typed angle
    under "Full" is stored-and-inert, exactly as the real door reads
    it."""
    from tracer.ui import cmddialog
    prior = cmddialog.ask

    def routed(parent, title, fields, remember_key=None):
        if title == "Revolve":
            return dict(extent=extent, angle=float(angle), op=op)
        return prior(parent, title, fields, remember_key=remember_key)
    monkeypatch.setattr(cmddialog, "ask", routed)


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
def _isolate_recovery_dir(_isolate_settings_store):
    """No headless test may poison the user's real crash-recovery folder
    — an autosave written by pytest would haunt their next app start.
    Point every test run at a temp directory and restore after. R41 v3:
    the dependency names the settings store fixture, so the recovery key
    is written into the ISOLATED store, never the anonymous shared one."""
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
