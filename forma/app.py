"""Forma entry point: python -m forma (or the `forma` console script)."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui import theme
from .ui.mainwindow import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Forma")
    app.setOrganizationName("forma-cad")
    app.setStyleSheet(theme.stylesheet(theme.DARK))
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
