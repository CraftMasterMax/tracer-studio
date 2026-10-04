"""Tracer Studio entry point: python -m tracer (or the `tracer` console script)."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui import theme
from .ui.mainwindow import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Tracer Studio")
    app.setOrganizationName("tracer-cad")
    app.setStyleSheet(theme.stylesheet(theme.DARK))
    win = MainWindow()
    win.show()
    win.maybe_show_tour()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
