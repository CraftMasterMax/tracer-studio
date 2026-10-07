"""Tracer Studio entry point: python -m tracer (or the `tracer` console script)."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .ui import theme
from .ui.mainwindow import MainWindow

DOC_EXTS = (".tracer", ".forma")


def _initial_file(argv: list[str]) -> Path | None:
    """The document the app opens on launch: the first argument that
    looks like one — a double-clicked file in a file manager arrives
    exactly this way through the launcher's ``%f``."""
    for arg in argv[1:]:
        p = Path(arg).expanduser()
        if p.suffix.lower() in DOC_EXTS and p.is_file():
            return p
    return None


def main() -> int:
    # idempotent entry: reuse a live QApplication (embedders, tests)
    # rather than demanding a virgin process
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Tracer Studio")
    app.setOrganizationName("tracer-cad")
    # Wayland (Hyprland et al.): bind the window to the installed
    # .desktop entry so the launcher icon and app grouping match
    app.setDesktopFileName("tracer-studio")
    icon = Path(__file__).parent / "resources" / "tracer.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    app.setStyleSheet(theme.stylesheet(theme.DARK))
    win = MainWindow()
    win.show()
    win.maybe_show_tour()
    win.maybe_recover()               # crash rescue first: it is modal
    doc = _initial_file(sys.argv)     # ...then the requested document
    if doc is not None:
        win._open_path(doc)           # the very opener Recent Files uses
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
