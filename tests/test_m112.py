"""M112: theme-token discipline.

The whole UI speaks in tokens: the HIG darkBlue surfaces, the
autodeskBlue accent, the peach hover, the status trio, the sketch
semantics, one generated stylesheet whose sizes all ride the SP
rhythm — and no UI module is allowed to spell a raw colour again.
"""
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from tracer.ui import theme                                        # noqa: E402

UI_DIR = Path(__file__).resolve().parents[1] / "tracer" / "ui"


# ---- the values themselves ---------------------------------------------------
def test_brand_and_status_tokens():
    assert theme.DARK["accent"] == "#0696d7"            # autodeskBlue .500
    assert theme.DARK["hover"] == "#e3ad79"             # the peach
    assert theme.DARK["select"] == theme.DARK["accent"]  # pick = brand blue
    assert theme.DARK["success"] == "#87b340"
    assert theme.DARK["warn"] == "#faa21b"
    assert theme.DARK["danger"] == "#ec4a41"
    assert theme.DARK["sel_bg"] == "#1858a8"            # list selection fill


def test_surfaces_ride_the_darkblue_scale():
    assert theme.DARK["bg0"] == theme.DB[".350"]        # darkest chrome base
    assert theme.DARK["bg1"] == theme.DB[".300"]
    assert theme.DARK["bg2"] == theme.DB[".250"]
    assert theme.DARK["line"] == theme.DB[".200"]
    # the canvas follows the chrome: Fusion's "Theme (default)" behaviour
    assert theme.DARK["sky_top"] == theme.DB[".300"]
    assert theme.DARK["sky_bottom"] == theme.DB[".350"]


def test_viewport_semantic_colours():
    assert theme.DARK["hi_hover"] == theme.rgb01("#e3ad79")
    assert theme.DARK["hi_sel"] == theme.rgb01("#0696d7")
    assert theme.DARK["preview"] == theme.rgb01("#faa21b")   # amber ghost
    assert theme.DARK["plane_line"] == theme.rgb01("#fbb549")  # work plane


def test_sketch_state_tokens():
    s = theme.SKETCH
    assert s["under"] == "#6ac0e7" and s["full"] == "#ffffff"
    assert s["construction"] == "#db5942" and s["projected"] == "#b384f2"
    assert s["fixed"] == "#9fdc66" and s["sel"] == "#00d5ff"
    assert s["dim"] == theme.SUCCESS and s["infer"] == theme.INFER
    assert s["hud"] == "#38abdf"


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
    w, wb = Viewport.rubber_style(True)             # window: blue
    c, cb = Viewport.rubber_style(False)            # crossing: green
    assert w == QColor(theme.DARK["accent_soft"])
    assert c == QColor(theme.DARK["success"])
    assert wb.alpha() == 24 and cb.alpha() == 24
