"""Design tokens. Dark-first, tuned for a calm technical surface.

Palette: near-neutral charcoal background (not pure black), a single
saturated accent, and a warm paper-white foreground. Spacing follows a
4px rhythm; type scale stays inside the platform font.
"""
from __future__ import annotations

DARK = {
    "bg0": "#2b2e33",          # app chrome base (cool blue-grey, CAD-style)
    "bg1": "#33373d",          # panels
    "bg2": "#3f444c",          # raised (inputs, hover)
    "line": "#4a5059",         # separators / borders
    "fg": "#e6e9ec",
    "fg_dim": "#a9b1bb",
    "fg_faint": "#767e8a",
    "accent": "#4ea1ff",
    "accent_dim": "#2c6fb8",
    "danger": "#e06c75",

    # viewport — Blender solid-mode flavour: neutral graphite backdrop
    # (brighter above, settling darker under the model), no blue cast
    "sky_top": "#313133",      # horizon gradient: graphite top
    "sky_bottom": "#1c1c1e",   # …deep graphite under the model
    "grid_minor": (0.30, 0.30, 0.32),
    "grid_major": (0.43, 0.43, 0.46),
    "axis_x": (0.87, 0.42, 0.44),
    "axis_y": (0.55, 0.80, 0.52),
    "axis_z": (0.44, 0.62, 0.95),
    "solid_base": (0.70, 0.70, 0.72),   # Blender's viewport grey: neutral
    "solid_edge": (0.17, 0.17, 0.19),
    "hi_hover": (1.0, 0.78, 0.42),   # face under the cursor: pale orange
    "hi_sel": (1.0, 0.55, 0.0),      # picked face: Fusion orange
    "plane_line": (0.55, 0.72, 0.95),  # construction-plane quads
}

LIGHT = {
    **DARK,
    "bg0": "#f5f6f8", "bg1": "#eceef1", "bg2": "#ffffff",
    "line": "#d5d9df", "fg": "#1f2328", "fg_dim": "#5c636e",
    "fg_faint": "#98a0ab", "accent": "#1f6feb", "accent_dim": "#4892ea",
    "sky_top": "#e9e9ea", "sky_bottom": "#d2d2d4",
    "solid_base": (0.70, 0.70, 0.72),
    "solid_edge": (0.30, 0.30, 0.33),
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
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle {{ background: {t['line']}; border-radius: 4px;
                          min-height: 24px; min-width: 24px; }}
    QScrollBar::handle:hover {{ background: {t['fg_faint']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QToolBar {{ border-bottom: 1px solid {t['line']}; }}
    QLabel#docTitle {{ font-size: 14px; font-weight: 700; padding: {SP*2}px; }}
    QLabel#dim {{ color: {t['fg_dim']}; }}
    """
