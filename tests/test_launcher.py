"""Launcher plumbing: the double-click / one-command path to the app.

Pins the contract tools/install-linux.sh builds on: the CLI takes a
document argument, the .desktop template carries the %f slot, the MIME
package claims *.tracer, and the committed icon is a real PNG.
"""
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from tracer.app import _initial_file                                   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_initial_file_picks_first_document_argument(tmp_path):
    doc = tmp_path / "part.tracer"
    doc.write_text("{}")
    legacy = tmp_path / "old.forma"
    legacy.write_text("{}")
    assert _initial_file(["tracer", str(doc)]) == doc
    assert _initial_file(["tracer", "notes.txt", str(legacy)]) == legacy
    assert _initial_file(["tracer"]) is None


def test_initial_file_ignores_strangers_and_ghosts(tmp_path):
    assert _initial_file(["tracer", "README.md"]) is None
    assert _initial_file(["tracer", str(tmp_path / "nope.tracer")]) is None
    assert _initial_file(["tracer", str(tmp_path)]) is None   # a directory


def test_desktop_template_is_installer_ready():
    desk = (ROOT / "packaging/linux/tracer-studio.desktop").read_text(
        encoding="utf-8")
    assert "Exec=@PREFIX@/.venv/bin/tracer %f" in desk
    assert "Icon=tracer-studio" in desk
    assert "MimeType=application/x-tracer;" in desk
    assert "[Desktop Entry]" in desk


def test_mime_package_claims_the_extension():
    xml = (ROOT / "packaging/linux/tracer-studio.xml").read_text(
        encoding="utf-8")
    assert 'type="application/x-tracer"' in xml
    assert 'pattern="*.tracer"' in xml


def test_committed_icon_is_a_real_png():
    raw = (ROOT / "tracer/resources/tracer.png").read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(raw) > 1000                 # a glyph, not a placeholder


def test_install_script_survives_bash_syntax_check():
    # the installer is Linux-only plumbing — syntax-check it where it
    # runs (and where a CRLF-mangled checkout would actually matter)
    if os.name != "posix":
        pytest.skip("linux installer")
    import subprocess
    for name in ("install-linux.sh", "uninstall-linux.sh"):
        raw = (ROOT / "tools" / name).read_bytes()
        assert b"\r\n" not in raw, name      # .gitattributes keeps LF
        r = subprocess.run(["bash", "-n", str(ROOT / "tools" / name)])
        assert r.returncode == 0, name


def test_main_opens_the_document_argument(monkeypatch, tmp_path):
    # the end of the double-click chain: argv → main() → _open_path,
    # proven without a real window (dummy records the call)
    import sys

    from PySide6.QtWidgets import QApplication

    from tracer import app as appmod
    QApplication.instance() or QApplication([])

    class DummyWin:
        opened: list = []

        def show(self):
            pass

        def maybe_show_tour(self):
            pass

        def maybe_recover(self):
            pass

        def _open_path(self, p):
            DummyWin.opened.append(Path(p))

    DummyWin.opened = []
    doc = tmp_path / "wired.tracer"
    doc.write_text("{}")
    monkeypatch.setattr(appmod, "MainWindow", DummyWin)
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(sys, "argv", ["tracer", "junk.txt", str(doc)])
    # main() legitimately styles the SHARED app (QSS shifts widget
    # metrics) — hand the process back exactly as we found it
    a = QApplication.instance()
    held = (a.styleSheet(), a.windowIcon(), a.desktopFileName())
    try:
        assert appmod.main() == 0
    finally:
        a.setStyleSheet(held[0])
        a.setWindowIcon(held[1])
        a.setDesktopFileName(held[2])
    assert DummyWin.opened == [doc]        # junk skipped, document opened
