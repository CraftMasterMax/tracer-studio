"""Appearances (M52): paint the body like Fusion's Appearance dialog.

A small library of shop-floor materials — the colours a maker actually
reaches for — plus a transparency setting.  The colour is a plain
sRGB triple the renderer multiplies into its solid-shading base, so a
Brass body catches the light exactly like the grey one does, only
brassily.

Stored on the document (one body per document in v1), persisted with
the JSON, applied by MainWindow._apply_appearance on every command,
open and new-document.
"""
from __future__ import annotations

# name -> sRGB (0..1) — generic shop materials, our own palette
MATERIALS = {
    "Steel":        (0.62, 0.63, 0.66),
    "Aluminium":    (0.78, 0.79, 0.81),
    "Stainless":    (0.70, 0.71, 0.73),
    "Cast iron":    (0.36, 0.36, 0.38),
    "Brass":        (0.80, 0.64, 0.28),
    "Copper":       (0.72, 0.36, 0.25),
    "Titanium":     (0.55, 0.56, 0.58),
    "Anodized red": (0.78, 0.18, 0.16),
    "Anodized blue": (0.16, 0.36, 0.72),
    "Plastic white": (0.88, 0.88, 0.86),
    "Plastic black": (0.10, 0.10, 0.11),
    "Rubber":       (0.16, 0.16, 0.17),
}


def appearance(name: str, opacity: float = 1.0) -> dict:
    """The document's appearance record for a library material."""
    return {"name": str(name),
            "color": [float(c) for c in MATERIALS[name]],
            "opacity": max(0.0, min(1.0, float(opacity)))}
