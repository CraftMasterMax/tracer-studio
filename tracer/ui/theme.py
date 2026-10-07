"""Design tokens — every colour and pixel in the UI traces back here.

The values follow the public Autodesk design-token scales (the unified
dark theme Fusion shipped Oct 2025, "darkBlue" by lineage): darkBlue
surfaces, autodeskBlue accent, the peach hover, a fixed status trio,
and the viewport semantics every Fusion user names from memory — blue
selection, amber ghost preview, white-when-constrained sketch.
Clean-room: token VALUES are facts; no Autodesk art or naming ships
in this product.

Discipline, pinned by tests/test_m112.py:
  * UI modules never spell a hex or an rgb triple — they read
    DARK / LIGHT / SKETCH / VIEWCUBE / DRAWING from here;
  * every pixel size in the generated stylesheet is an SP multiple, a
    TYPE step, an SCROLL step, or a 1px hairline — logical (dpr-
    independent) pixels, which Qt scales per-screen for free.
"""
from __future__ import annotations

# ---- token scales (the only place raw hexes live) --------------------------
DB = {".100": "#454f61", ".200": "#3b4453", ".250": "#2e3440",
      ".300": "#222933", ".350": "#1a1f25"}                    # darkBlue
BLUE = {".100": "#cdeaf7", ".300": "#6ac0e7", ".400": "#38abdf",
        ".500": "#0696d7", ".700": "#006eaf", ".900": "#0a324d"}
CHAR = {".300": "#cccccc", ".500": "#999999", ".700": "#666666"}
LGRAY = {".050": "#ffffff", ".100": "#f5f5f5", ".200": "#eeeeee",
         ".400": "#d9d9d9", ".600": "#cccccc"}

SUCCESS, WARNING, ERROR = "#87b340", "#faa21b", "#ec4a41"
HOVER = "#e3ad79"           # the peach under the cursor
SELECT = BLUE[".500"]       # picked geometry = brand blue
SEL_BG = "#1858a8"          # selection fill in trees/lists
PLANE = "#fbb549"           # datum planes (work-plane amber)
INFER = "#84d7ce"           # inference / live measure


def rgb01(hexc: str) -> tuple[float, float, float]:
    """'#rrggbb' -> 0..1 float triple, the shape GL uniforms want."""
    h = hexc.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))     # type: ignore[return-value]


def rgba(hexc: str, alpha: int) -> str:
    """'#rrggbb' + 0..255 alpha -> '#aarrggbb' (Qt's 8-digit form)."""
    return f"#{alpha:02x}{hexc.lstrip('#')}"


# ---- the dark theme (the product default; Fusion's 2026 look) --------------
DARK = {
    # chrome surfaces, dark→light roles
    "bg0": DB[".350"], "bg1": DB[".300"], "bg2": DB[".250"],
    "line": DB[".200"], "line_hi": DB[".100"],
    "fg": LGRAY[".100"], "fg_dim": CHAR[".500"], "fg_faint": CHAR[".700"],
    "accent": BLUE[".500"], "accent_dim": BLUE[".700"],
    "accent_soft": BLUE[".300"], "accent_faint": BLUE[".100"],
    "accent_deep": BLUE[".900"],
    "success": SUCCESS, "warn": WARNING, "danger": ERROR,
    "hover": HOVER, "select": SELECT, "sel_bg": SEL_BG,

    # viewport — the canvas follows the chrome, Fusion's "Theme
    # (default)" behaviour; the renderer reads every key below
    "sky_top": DB[".300"], "sky_bottom": DB[".350"],
    "grid_minor": rgb01(DB[".200"]), "grid_major": rgb01(DB[".100"]),
    "axis_x": (0.87, 0.42, 0.44), "axis_y": (0.55, 0.80, 0.52),
    "axis_z": rgb01(BLUE[".400"]),
    "solid_base": (0.70, 0.70, 0.72), "solid_edge": (0.12, 0.14, 0.17),
    "hi_hover": rgb01(HOVER), "hi_sel": rgb01(SELECT),
    "preview": rgb01(WARNING), "plane_line": rgb01(PLANE),
}

# ---- the light theme (HIG lightGray pair; wired by the prefs milestone) ----
LIGHT = {
    **DARK,
    "bg0": LGRAY[".200"], "bg1": LGRAY[".100"], "bg2": LGRAY[".050"],
    "line": LGRAY[".400"], "line_hi": LGRAY[".600"],
    "fg": "#1f2328", "fg_dim": CHAR[".700"], "fg_faint": CHAR[".500"],
    "accent": BLUE[".500"], "accent_dim": BLUE[".700"],
    "sky_top": LGRAY[".400"], "sky_bottom": LGRAY[".200"],
    "grid_minor": rgb01(LGRAY[".600"]), "grid_major": rgb01(CHAR[".300"]),
    "solid_edge": (0.30, 0.30, 0.33),
}

# ---- sketch-mode semantics (public viewport-env colours, re-tokenised) -----
SKETCH = {
    "under": BLUE[".300"],        # under-constrained geometry
    "full": LGRAY[".050"],        # fully constrained = white
    "sel": "#00d5ff",             # picked geometry / wireframe
    "fixed": "#9fdc66",           # fixed constraints
    "projected": "#b384f2",       # projected reference edges
    "construction": "#db5942",    # construction geometry
    "dim": SUCCESS,               # dimension text and lines
    "infer": INFER,               # inference / live measure
    "profile": BLUE[".300"],      # profile fill
    "hud": BLUE[".400"],          # heads-up text
    "error": ERROR,               # conflicting constraint
    "handle": SUCCESS,            # manipulator handles
}

# ---- the view cube + nav stack ------------------------------------------------
VIEWCUBE = {
    "face": "#2a2e35", "face_front": "#3a3f48", "edge": "#565d68",
    "text": "#c8cdd4", "hover": "#4a5a72", "hover_edge": BLUE[".300"],
    "nav_hover": "#464e5a", "nav_bg": rgba("#323840", 210),
    "nav_edge": "#707884", "nav_glyph": "#e2e6ec",
}

# ---- the drawing sheet (theme-independent: it is paper, always) --------------
DRAWING = {
    "desk": "#34383e", "desk_edge": "#14161a", "paper": "#f5f5f2",
    "view_edge": "#1c1e22", "sheet": "#26282c", "border": "#464a50",
    "detail": "#6e7278", "hatch": "#8c9096", "faint": "#5a5e64",
    "red": "#c33c3c", "select": SELECT,
}

# ---- metrics: logical pixels only, one rhythm -------------------------------
SP = 4                       # base spacing unit
TYPE = {"ui": 13, "title": 14, "small": 11}
SCROLL = {"bar": 10, "margin": 2, "thumb_r": 4, "thumb_min": 24}


def stylesheet(t: dict) -> str:
    """One stylesheet, generated from tokens — chrome, inputs, menus
    and tooltips all speak the same voice."""
    rad = SP * 2
    half = SP // 2
    return f"""
    QMainWindow, QWidget {{
        background: {t['bg0']};
        color: {t['fg']};
        font-size: {TYPE['ui']}px;
    }}
    QPanel, QTreeWidget, QListWidget {{
        background: {t['bg1']};
        border: 1px solid {t['line']};
        border-radius: {rad}px;
    }}
    QTreeWidget::item, QListWidget::item {{
        padding: {SP}px;
        border-radius: {SP}px;
    }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background: {t['sel_bg']};
        color: {t['fg']};
    }}
    QTreeWidget::item:hover, QListWidget::item:hover {{
        background: {t['bg2']};
    }}
    QHeaderView::section {{
        background: {t['bg1']};
        color: {t['fg_dim']};
        border: none;
        padding: {SP}px {SP * 2}px;
        font-weight: 600;
    }}
    QPushButton {{
        background: {t['bg2']};
        border: 1px solid {t['line']};
        border-radius: {rad - half}px;
        padding: {SP}px {SP * 3}px;
        color: {t['fg']};
    }}
    QPushButton:hover {{ border-color: {t['accent']}; }}
    QPushButton:pressed {{ background: {t['line']}; }}
    QPushButton[tb="true"] {{ padding: {SP}px; border-radius: {SP}px; }}
    QLineEdit, QAbstractSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
        background: {t['bg2']};
        border: 1px solid {t['line']};
        border-radius: {SP}px;
        padding: {SP}px {SP * 2}px;
        selection-background-color: {t['sel_bg']};
    }}
    QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {{
        border-color: {t['accent']};
    }}
    QComboBox::drop-down {{ border: none; width: {SP * 4}px; }}
    QMenuBar {{ background: {t['bg0']}; color: {t['fg_dim']}; }}
    QMenuBar::item:selected {{ background: {t['bg2']}; color: {t['fg']}; }}
    QMenu {{ background: {t['bg1']}; border: 1px solid {t['line']};
             border-radius: {rad}px; padding: {SP}px; }}
    QMenu::item {{ padding: {SP}px {SP * 4}px; border-radius: {SP}px; }}
    QMenu::item:selected {{ background: {t['bg2']}; color: {t['accent_soft']}; }}
    QMenu::separator {{ height: 1px; background: {t['line']};
                        margin: {SP}px; }}
    QToolTip {{ background: {t['bg2']}; color: {t['fg']};
                border: 1px solid {t['line_hi']}; border-radius: {SP}px;
                padding: {SP}px {SP * 2}px; }}
    QStatusBar {{ background: {t['bg0']}; color: {t['fg_dim']};
                  border-top: 1px solid {t['line']}; }}
    QSplitter::handle {{ background: {t['line']}; width: 1px; }}
    QScrollBar:vertical {{ background: transparent; width: {SCROLL['bar']}px;
                           margin: {SCROLL['margin']}px; }}
    QScrollBar:horizontal {{ background: transparent;
                             height: {SCROLL['bar']}px;
                             margin: {SCROLL['margin']}px; }}
    QScrollBar::handle {{ background: {t['line']};
                          border-radius: {SCROLL['thumb_r']}px;
                          min-height: {SCROLL['thumb_min']}px;
                          min-width: {SCROLL['thumb_min']}px; }}
    QScrollBar::handle:hover {{ background: {t['fg_faint']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QToolBar {{ border-bottom: 1px solid {t['line']}; }}
    QLabel#docTitle {{ font-size: {TYPE['title']}px; font-weight: 700;
                       padding: {SP * 2}px; }}
    QLabel#dim {{ color: {t['fg_dim']}; }}
    """
