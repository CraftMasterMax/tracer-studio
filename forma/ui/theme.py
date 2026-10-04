"""Design tokens. Dark-first, tuned for a calm technical surface.

Palette: near-neutral charcoal background (not pure black), a single
saturated accent, and a warm paper-white foreground. Spacing follows a
4px rhythm; type scale stays inside the platform font.
"""
from __future__ import annotations

DARK = {
    "bg0": "#141518",          # app chrome base
    "bg1": "#1b1d22",          # panels
    "bg2": "#23262c",          # raised (inputs, hover)
    "line": "#2d313a",         # separators / borders
    "fg": "#e8eaed",
    "fg_dim": "#9aa1ac",
    "fg_faint": "#5f6672",
    "accent": "#4ea1ff",
    "accent_dim": "#2c6fb8",
    "danger": "#e06c75",

    # viewport
    "sky_top": "#22252b",
    "sky_bottom": "#151719",
    "grid_minor": (0.22, 0.24, 0.28),
    "grid_major": (0.30, 0.33, 0.38),
    "axis_x": (0.85, 0.42, 0.44),
    "axis_y": (0.55, 0.78, 0.50),
    "solid_base": (0.62, 0.66, 0.72),
    "solid_edge": (0.13, 0.15, 0.18),
}

LIGHT = {
    **DARK,
    "bg0": "#f5f6f8", "bg1": "#eceef1", "bg2": "#ffffff",
    "line": "#d5d9df", "fg": "#1f2328", "fg_dim": "#5c636e",
    "fg_faint": "#98a0ab", "accent": "#1f6feb", "accent_dim": "#4892ea",
    "sky_top": "#e8eaee", "sky_bottom": "#d8dbe1",
    "solid_base": (0.70, 0.73, 0.78),
    "solid_edge": (0.25, 0.28, 0.32),
}

SP = 4  # base spacing unit


def stylesheet(t: dict) -> str:
    return f"""
    QMainWindow, QWidget {{
        background: {t['bg0']};
        color: {t['fg']};
        font-size: 13px;
    }}
    QPanel, QTreeWidget, QListWidget {{
        background: {t['bg1']};
        border: 1px solid {t['line']};
        border-radius: 8px;
    }}
    QTreeWidget::item {{
        padding: 5px 6px;
        border-radius: 5px;
    }}
    QTreeWidget::item:selected {{
        background: {t['bg2']};
        color: {t['accent']};
    }}
    QTreeWidget::item:hover {{ background: {t['bg2']}; }}
    QHeaderView::section {{
        background: {t['bg1']};
        color: {t['fg_dim']};
        border: none;
        padding: 6px;
        font-weight: 600;
    }}
    QPushButton {{
        background: {t['bg2']};
        border: 1px solid {t['line']};
        border-radius: 7px;
        padding: 6px 14px;
        color: {t['fg']};
    }}
    QPushButton:hover {{ border-color: {t['accent_dim']}; }}
    QPushButton:pressed {{ background: {t['line']}; }}
    QPushButton[tb="true"] {{ padding: 4px 9px; border-radius: 6px; }}
    QMenuBar {{ background: {t['bg0']}; color: {t['fg_dim']}; }}
    QMenuBar::item:selected {{ background: {t['bg2']}; color: {t['fg']}; }}
    QMenu {{ background: {t['bg1']}; border: 1px solid {t['line']};
             border-radius: 8px; padding: 4px; }}
    QMenu::item:selected {{ background: {t['bg2']}; color: {t['accent']}; }}
    QStatusBar {{ background: {t['bg0']}; color: {t['fg_dim']};
                  border-top: 1px solid {t['line']}; }}
    QSplitter::handle {{ background: {t['line']}; width: 1px; }}
    QLabel#docTitle {{ font-size: 14px; font-weight: 700; padding: {SP*2}px; }}
    QLabel#dim {{ color: {t['fg_dim']}; }}
    """
