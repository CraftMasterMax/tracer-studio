"""M112: theme-token discipline.

The whole UI speaks in tokens: the INK NAVY chrome (M159 retarget —
the only recorded values of the class's dark-blue family), the canvas
semantics, one generated stylesheet whose sizes all ride the SP
rhythm (plus the one RADIUS token) — and no UI module is allowed to
spell a raw colour again.
"""
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from tracer.ui import theme                                        # noqa: E402

UI_DIR = Path(__file__).resolve().parents[1] / "tracer" / "ui"


# ---- the values themselves ---------------------------------------------------
def test_brand_and_status_tokens():
    # M159 INK NAVY (research/fd7_visual_design.md fact 7): the CHROME
    # accent retargets to #4c9bff (focus/links, brighter on dark) while
    # the CANVAS pick color stays the sky blue until M160 pairs the
    # hover/selection duo — the old accent==select equality becomes a
    # documented SPLIT.
    assert theme.DARK["accent"] == "#4c9bff"
    # M160 THE CANVAS SPEAKS lands the duo: the canvas pick takes the
    # digest's decided accent blue (FD2-L2 publishes NO hex — "blue
    # selection" and "turns white" are the users' recorded language;
    # the peach was folklore wearing a hex). The SPLIT that survives
    # is worlds, not shades: chrome fill #3d6cb9 vs canvas pick #4c9bff.
    assert theme.DARK["select"] == "#4c9bff"             # canvas pick
    assert theme.DARK["hover"] == "#9cc4ff"              # "turns white"
    assert theme.DARK["success"] == "#87b340"
    assert theme.DARK["warn"] == "#faa21b"
    assert theme.DARK["danger"] == "#ec4a41"
    assert theme.DARK["sel_bg"] == "#3d6cb9"             # list selection fill


def test_surfaces_ride_the_ink_navy_scale():
    # M159: chrome retargets onto the ONLY recorded values for the
    # Autodesk dark-blue family (FD7 fact 5 — Inventor add-in
    # FromArgb(59,68,83)/(69,79,97)/(44,52,64), text #E1E1E1).
    assert theme.DARK["bg0"] == theme.NAVY["window"] == "#3b4453"
    assert theme.DARK["bg1"] == theme.NAVY["panel"]       # ours-said step
    assert theme.DARK["bg2"] == theme.NAVY["control"] == "#454f61"
    assert theme.DARK["line"] == theme.NAVY["press"] == "#2c3440"
    assert theme.DARK["fg"] == "#e1e1e1"                  # recorded
    assert theme.DARK["bg0"] != theme.DARK["bg2"]         # controls lighter
    # the canvas stays on the DB rungs — chrome re-tune, viewport untouched
    assert theme.DARK["sky_top"] == theme.DB[".300"]
    assert theme.DARK["sky_bottom"] == theme.DB[".350"]


def test_viewport_semantic_colours():
    # M160 duo: bright bluish-white hover, accent-blue pick (FD2-L2's
    # recorded language, OURS-Said hexes, cited in theme.py)
    assert theme.DARK["hi_hover"] == theme.rgb01("#9cc4ff")
    assert theme.DARK["hi_sel"] == theme.rgb01("#4c9bff")
    assert theme.DARK["preview"] == theme.rgb01("#faa21b")   # amber ghost
    assert theme.DARK["plane_line"] == theme.rgb01("#fbb549")  # work plane


def test_sketch_state_tokens():
    s = theme.SKETCH
    assert s["under"] == "#6ac0e7" and s["full"] == "#ffffff"
    assert s["construction"] == "#db5942" and s["projected"] == "#b384f2"
    assert s["fixed"] == "#9fdc66" and s["sel"] == "#00d5ff"
    assert s["dim"] == theme.SUCCESS and s["infer"] == theme.INFER
    assert s["hud"] == "#38abdf"
    assert s["hover"] == "#9cc4ff"           # M164 R2: the hover ring


def test_helpers():
    assert theme.rgb01("#ffffff") == (1.0, 1.0, 1.0)
    assert theme.rgba("#222933", 210) == "#d2222933"


# ---- the generated stylesheet --------------------------------------------------
def _px(sheet):
    return [int(n) for n in re.findall(r"(\d+)px", sheet)]


def test_stylesheet_sizes_ride_the_rhythm():
    ok = {0, 1} | set(theme.TYPE.values()) | set(theme.SCROLL.values())
    ok |= {theme.SP * k for k in range(1, 13)}
    ok |= {theme.SP * k + theme.SP // 2 for k in range(0, 6)}   # half steps
    ok |= {theme.RADIUS}          # the one corner (M159, FD7-6: 3px)
    for t in (theme.DARK, theme.LIGHT):
        for n in _px(theme.stylesheet(t)):
            assert n in ok, f"{n}px is off-rhythm"


def test_stylesheet_lists_use_the_blue_selection_fill():
    sheet = theme.stylesheet(theme.DARK)
    assert theme.DARK["sel_bg"] in sheet
    assert "QToolTip" in sheet              # tooltips: chips in the theme


def test_light_theme_is_a_full_key_pair():
    assert set(theme.LIGHT) == set(theme.DARK)
    assert theme.LIGHT["bg0"] != theme.DARK["bg0"]


# ---- the discipline itself ------------------------------------------------------
def test_no_ui_module_spells_a_colour():
    """Raw hexes and numeric QColor triples live ONLY in theme.py."""
    bad = []
    for py in UI_DIR.glob("*.py"):
        if py.name == "theme.py":
            continue
        # Python source files are UTF-8 by spec (PEP 3120) — never the
        # platform default, which is cp1252 on Windows
        text = py.read_text(encoding="utf-8")
        bad += [f"{py.name}: {m.group(0)}"
                for m in re.finditer(r"#[0-9a-fA-F]{6}\b", text)]
        bad += [f"{py.name}: numeric QColor"
                for m in re.finditer(r"QColor\(\s*\d", text)]
    assert not bad, "ungoverned colours:\n" + "\n".join(bad)


def test_renderer_palette_keys_survive():
    """The GPU reads its colours from DARK by name — none may vanish."""
    needed = ["sky_top", "sky_bottom", "grid_minor", "grid_major",
              "axis_x", "axis_y", "axis_z", "solid_base", "solid_edge",
              "hi_hover", "hi_sel", "plane_line", "preview"]
    assert all(k in theme.DARK for k in needed)


def test_ghost_preview_roundtrip():
    """The amber feature preview tints, then restores the appearance."""
    pytest.importorskip("moderngl")
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    try:
        r.set_base_color((0.1, 0.2, 0.3), 1.0)     # a document appearance
        r.set_ghost(True)
        assert r._base_override == r.palette["preview"]
        assert r._base_alpha < 1.0
        r.set_ghost(True)                          # idempotent
        assert r._base_alpha == 0.45
        r.set_ghost(False)
        assert r._base_override == (0.1, 0.2, 0.3)  # appearance restored
        assert r._base_alpha == 1.0
    finally:
        r.close()


def test_rubber_band_voices_are_tokens():
    from PySide6.QtGui import QColor

    from tracer.ui.viewport import Viewport
    # M184 R1: the mouth now answers (QPen, QColor) - the pen carries the
    # LAW-49 dress. The M112 law SURVIVES: both voices are TOKENS, never
    # loose hex - and the fill is the law's 25%, not the old ~9% wash.
    w, wb = Viewport.rubber_style(True)             # window: blue
    c, cb = Viewport.rubber_style(False)            # crossing: green
    assert w.color() == QColor(theme.DARK["accent_soft"])
    assert c.color() == QColor(theme.DARK["success"])
    assert wb.alpha() == 64 and cb.alpha() == 64
