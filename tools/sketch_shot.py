"""Grab a PNG of the sketcher with a representative sketch, for visual
review and UI tests. Usage: python tools/sketch_shot.py [out.png]"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtWidgets import QApplication

from tracer.core.sketch.constraints import Distance, Fixed
from tracer.ui.mainwindow import MainWindow
from tracer.ui.renderer import SceneRenderer


def build_demo(canvas):
    m = canvas.model
    p = m.point(0, 0)
    m.add_rect(p, m.point(60, 40))
    h1 = m.point(6, 6)
    m.add_rect(h1, m.point(18, 18))
    circ = m.add_circle(m.point(42, 28), 8)
    m.constrain(Fixed(circ.c, x=42.0, y=28.0),
                Distance(m.sketch.lines[4].a, m.sketch.lines[4].b, 12.0))
    m.solve()
    canvas.fit_view()


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/sketch-shot.png")
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(renderer=SceneRenderer())
    win.resize(1100, 720)
    win.show()
    win.action_new_sketch()
    build_demo(win.sketch)
    app.processEvents()
    win.sketch.grab().save(str(out))
    print("saved", out)


if __name__ == "__main__":
    main()
