"""Design tokens — every colour and pixel in the UI traces back here.

The values follow the public Autodesk design-token scales (the unified
dark theme Fusion shipped Oct 2025, "darkBlue" by lineage) re-tuned in
M159 to the RECORDED INK NAVY family, with the M160 canvas duo (bright
bluish-white hover, accent-blue selection — OURS-Said hexes on the
users' recorded language, "turns white" / "blue selection"). Clean-room:
token VALUES are facts; no Autodesk art or naming ships in this product.

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

# ---- INK NAVY: the M159 chrome family (FD7 receipts) ------------------------
# The recorded triplets come from the only published RGB values for the
# Autodesk dark-blue design language (FD7 fact 5: window FromArgb(59,68,83),
# control FromArgb(69,79,97), pressed FromArgb(44,52,64), text #E1E1E1);
# the panel step between window and control is OURS-said (FD7 records no
# third surface — one lightness step, the modder-documented structure).
# select/accent are the FD7 fact 7 decision: ONE desaturated blue does the
# selected job in chrome; the brighter #4c9bff does focus/links. DB stays
# the canvas/sketch scale — the chrome re-tune must not move the viewport
# (that pair is M160's conversation).
NAVY = {"window": "#3b4453",        # recorded (FD7-5)
        "panel": "#414b5c",         # ours-said step (window < panel)
        "control": "#454f61",       # recorded (FD7-5, lighter than window)
        "press": "#2c3440",         # recorded (FD7-5 control highlight)
        "text": "#e1e1e1",          # recorded (FD7-5)
        "text_dim": "#c3c7ce",      # FD7-16 icon gray, lifted to clear
                                    #   4.5:1 on EVERY navy surface
        "text_faint": "#8f97a3",    # ours-said (dimmer rung, tertiary only)
        "select": "#3d6cb9",        # chrome selection fill (FD7-7)
        "select_fg": "#ffffff",     # recorded was #EEEEEE (FD7-6) — it
                                    #   measures 4.44 on select, UNDER our
                                    #   own 4.5 gate; lifted to white,
                                    #   cite-the-move (M159)
        "accent": "#4c9bff",        # focus/links (FD7-7, brighter on dark)
        "accent_dim": "#3d6cb9",    # pressed/rolled accent
        "accent_soft": "#7fb8ff",   # menu-selection ink
        "accent_faint": "#cde4ff",  # pale ink on deep fills
        "accent_deep": "#1f3a5f",   # deep well under the accent
        "line_hi": "#525d71"}       # hover-brightened border (ours-said)

SUCCESS, WARNING, ERROR = "#87b340", "#faa21b", "#ec4a41"
# M160 THE CANVAS SPEAKS (research/fd2_selection.md): NO hex for the
# canvas duo is published anywhere (FD2-L2 — "blue selection" is only
# in-product consensus, "turns white" is the users' own hover language).
# The duo is therefore OURS-Said, anchored to the fleet's decided blues:
# hover = a BRIGHT bluish-white wash (the "turns white" reading), the
# canvas accent #4c9bff does selection (digest palette). The peach
# retires — it was never a recorded value, only folklore with a hex.
HOVER = "#9cc4ff"           # face under the cursor (bright, FD2-L1)
SELECT = NAVY["accent"]     # picked geometry = the canvas accent blue
SEL_BG = NAVY["select"]     # selection fill in trees/lists — chrome
PLANE = "#fbb549"           # datum planes (work-plane amber)
INFER = "#84d7ce"           # inference / live measure


def rgb01(hexc: str) -> tuple[float, float, float]:
    """'#rrggbb' -> 0..1 float triple, the shape GL uniforms want."""
    h = hexc.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))     # type: ignore[return-value]


def rgba(hexc: str, alpha: int) -> str:
    """'#rrggbb' + 0..255 alpha -> '#aarrggbb' (Qt's 8-digit form)."""
    return f"#{alpha:02x}{hexc.lstrip('#')}"


# ---- the dark theme (the product default; the M159 INK NAVY chrome) --------
DARK = {
    # chrome surfaces — the recorded navy family, window < panel <
    # control, pressed DARKER (FD7-5/6; M159 re-target, cite-the-move:
    # was the DB .350/.300/.250 near-black rungs)
    "bg0": NAVY["window"], "bg1": NAVY["panel"], "bg2": NAVY["control"],
    "line": NAVY["press"], "line_hi": NAVY["line_hi"],
    "fg": NAVY["text"], "fg_dim": NAVY["text_dim"],
    "fg_faint": NAVY["text_faint"],
    "accent": NAVY["accent"], "accent_dim": NAVY["accent_dim"],
    "accent_soft": NAVY["accent_soft"], "accent_faint": NAVY["accent_faint"],
    "accent_deep": NAVY["accent_deep"],
    "sel_fg": NAVY["select_fg"],
    "success": SUCCESS, "warn": WARNING, "danger": ERROR,
    "hover": HOVER, "select": SELECT, "sel_bg": SEL_BG,

    # viewport — the canvas keeps the DB rungs: M159 governs CHROME
    # only; the hover/selection canvas PAIR is M160's tranche
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
RADIUS = 3                   # the ONE corner (FD7-6: border-radius 3px)
TYPE = {"ui": 13, "title": 14, "small": 11}      # 13px chrome (FD7-6)
SCROLL = {"bar": 10, "margin": 2, "thumb_r": 4, "thumb_min": 24}
MIN_H = SP * 6               # 24px control min-height (FD7-6)
# The typography stack (FD7-12): the class ships a proprietary UI font
# (Artifakt) which NEVER rides here; this is the metric stand-in family.
FONT_STACK = '"Segoe UI", "Inter", "Noto Sans", sans-serif'


def contrast(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two '#rrggbb' tokens — the
    accessibility arithmetic the class VPAT answers (FD7-20) and our
    own 4.5:1 chrome gate (FD7-21 differentiator) reads."""
    def lum(hexc: str) -> float:
        h = hexc.lstrip("#")
        chans = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255
            chans.append(c / 12.92 if c <= 0.04045
                         else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def stylesheet(t: dict) -> str:
    """One stylesheet, generated from tokens — chrome, inputs, menus
    and tooltips all speak the same voice."""
    rad = RADIUS
    return f"""
    QMainWindow, QWidget {{
        background: {t['bg0']};
        color: {t['fg']};
        font-size: {TYPE['ui']}px;
        font-family: {FONT_STACK};
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
        color: {t['sel_fg']};
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
        border-radius: {rad}px;
        min-height: {MIN_H}px;
        padding: {SP}px {SP * 3}px;
        color: {t['fg']};
    }}
    QPushButton:hover {{ border-color: {t['accent']}; }}
    QPushButton:pressed {{ background: {t['line']}; }}
    QPushButton[tb="true"] {{ padding: {SP}px; border-radius: {SP}px;
                              min-height: 0; }}
    QLineEdit, QAbstractSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
        background: {t['bg2']};
        border: 1px solid {t['line']};
        border-radius: {SP}px;
        min-height: {MIN_H}px;
        padding: {SP}px {SP * 2}px;
        selection-background-color: {t['sel_bg']};
        selection-color: {t['sel_fg']};
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
