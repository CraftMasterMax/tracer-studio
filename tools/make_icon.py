"""Regenerate tracer/resources/tracer.png — the app icon.

Clean-room by construction: a QPainter-drawn extruded "T" block in the
darkBlue/autodeskBlue viewport tokens (ui_colors), no third-party art.
Run from anywhere; the PNG is committed next to the fonts.

    ./.venv/bin/python tools/make_icon.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath,
                           QPixmap, QPolygonF)
from PySide6.QtWidgets import QApplication

OUT = Path(__file__).resolve().parents[1] / "tracer" / "resources" / "tracer.png"
SIZE = 256

# ui_colors.md tokens
BG_TOP = QColor("#232a33")
BG_BOT = QColor("#191d23")
EDGE = QColor("#3a4250")
FRONT = QColor("#0696d7")            # autodeskBlue accent
FRONT_HI = QColor("#25aae6")
TOPFACE = QColor("#5cc4ee")
SIDE = QColor("#04709f")
SIDE_DARK = QColor("#035a80")


def _poly(*pts) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in pts])


def paint_icon(px: int = SIZE) -> QPixmap:
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = px / 256.0
    p.scale(s, s)

    # rounded-rect plate, darkBlue gradient
    grad = QLinearGradient(0, 0, 0, 256)
    grad.setColorAt(0.0, BG_TOP)
    grad.setColorAt(1.0, BG_BOT)
    plate = QPainterPath()
    plate.addRoundedRect(QRectF(8, 8, 240, 240), 44, 44)
    p.fillPath(plate, grad)
    p.setPen(Qt.PenStyle.NoPen)

    ox, oy = 20.0, -16.0             # the extrusion vector (up-right)
    front = _poly((70, 80), (186, 80), (186, 116), (145, 116),
                  (145, 208), (109, 208), (109, 116), (70, 116))

    def shift(pt):
        return (pt[0] + ox, pt[1] + oy)

    # visible extrusion faces: top of the bar, right end, bar-step,
    # stem right (drawn before the front so the front overlaps cleanly)
    faces = [
        (_poly((70, 80), (186, 80), shift((186, 80)), shift((70, 80))),
         TOPFACE),
        (_poly((186, 80), (186, 116), shift((186, 116)), shift((186, 80))),
         SIDE),
        (_poly((145, 116), (186, 116), shift((186, 116)), shift((145, 116))),
         SIDE),
        (_poly((145, 116), (145, 208), shift((145, 208)), shift((145, 116))),
         SIDE_DARK),
    ]
    for poly, col in faces:
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(poly)

    # the front face wears a light vertical gradient — the lit face of
    # a printed part
    fg = QLinearGradient(0, 80, 0, 208)
    fg.setColorAt(0.0, FRONT_HI)
    fg.setColorAt(1.0, FRONT)
    fp = QPainterPath()
    fp.addPolygon(front)
    p.fillPath(fp, fg)
    p.end()
    return pm


def main() -> int:
    app = QApplication.instance() or QApplication([])
    pm = paint_icon()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not pm.save(str(OUT), "PNG"):
        print(f"FAILED to write {OUT}", file=sys.stderr)
        return 1
    print(f"wrote {OUT} ({pm.width()}x{pm.height()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
