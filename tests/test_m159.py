"""M159 — INK NAVY: the chrome retarget rides RECORDED facts.

The night-2 design fleet (research/fd7_visual_design.md) recovered the
only RGB triplets ever published for the class's dark-blue design
language (fact 5: window FromArgb(59,68,83), control FromArgb(69,79,97),
pressed FromArgb(44,52,64), text 225/225/225) and the chrome STRUCTURE
(fact 6: 13px, 3px radius, 24px controls). This file gates the moves:
every retargeted token must trace to a receipt, every contrast pair
must clear the math the class VPAT answers (fact 20/21 — their recorded
weakness is our checklist), and the canvas must NOT have moved (the
hover/selection duo is M160's tranche, the peach still lives there).
"""
import re

import pytest

pytest.importorskip("PySide6")

from tracer.ui import theme                                        # noqa: E402

# The RECORDED triplets (FD7 fact 5, verbatim FromArgb values) — derived
# here, never copied as hex literals: the tokens must MEET these numbers.
RECORDED_WINDOW = "#%02x%02x%02x" % (59, 68, 83)
RECORDED_CONTROL = "#%02x%02x%02x" % (69, 79, 97)
RECORDED_PRESS = "#%02x%02x%02x" % (44, 52, 64)
RECORDED_TEXT = "#%02x%02x%02x" % (225, 225, 225)


def test_the_navy_family_meets_the_recorded_triplets():
    assert theme.DARK["bg0"].lower() == RECORDED_WINDOW
    assert theme.DARK["bg2"].lower() == RECORDED_CONTROL
    assert theme.DARK["line"].lower() == RECORDED_PRESS
    assert theme.DARK["fg"].lower() == RECORDED_TEXT
    # FD7-5 STRUCTURE, not just values: controls ride LIGHTER than the
    # window, pressed goes DARKER than both
    assert (theme.contrast(theme.DARK["bg2"], theme.DARK["bg0"]) >= 1.05)
    assert theme.DARK["line"] == theme.NAVY["press"]


def test_the_ladder_is_three_levels_never_pure_black():
    """FD7-H: three chrome background levels, faint blue cast, no pure
    black anywhere in the family."""
    levels = [theme.DARK[k] for k in ("bg0", "bg1", "bg2")]
    assert len(set(levels)) == 3
    for hexc in levels + [theme.DARK["line"], theme.NAVY["line_hi"]]:
        assert hexc != "#000000"
        r, g, b = (int(hexc.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        assert b > r                      # the blue cast (FD7-3, not graphite)


def test_chrome_contrast_clears_the_vpat_math():
    """FD7-20/21: the class VPAT claims contrast support while users
    report unreadable chrome — OUR gate computes WCAG per pair."""
    t = theme.DARK
    for fg_key in ("fg", "fg_dim"):
        for bg_key in ("bg0", "bg1", "bg2"):
            c = theme.contrast(t[fg_key], t[bg_key])
            assert c >= 4.5, (fg_key, bg_key, round(c, 2))
    assert theme.contrast(t["fg_faint"], t["bg0"]) >= 3.0   # tertiary
    # selected ink: the recorded #EEEEEE measures 4.44 on the #3d6cb9
    # fill — under our own gate, so M159 lifted it to white (the token
    # comment carries the citation)
    assert theme.contrast("#eeeeee", t["sel_bg"]) < 4.5     # the WHY
    assert theme.contrast(t["sel_fg"], t["sel_bg"]) >= 4.5  # selected ink
    assert theme.contrast(t["accent"], t["bg0"]) >= 3.0     # focus UI


def test_stylesheet_ships_the_recorded_structure():
    """FD7-6: 13px chrome, 3px radius, 24px controls — as literals in
    the GENERATED sheet; FD7-12: the proprietary class font NEVER
    ships, our stack stands in."""
    sheet = theme.stylesheet(theme.DARK)
    assert "border-radius: 3px" in sheet
    assert "min-height: 24px" in sheet
    assert "font-size: 13px" in sheet
    assert "Segoe UI" in sheet and "Inter" in sheet and "Noto Sans" in sheet
    assert "Artifakt" not in sheet


def test_no_hex_literal_in_the_sheet_that_is_not_a_token():
    """The generated stylesheet may only speak DARK values — a stray
    literal is an ungoverned colour wearing a QSS coat."""
    for t in (theme.DARK, theme.LIGHT):
        governed = {v.lower() for v in t.values()
                    if isinstance(v, str) and v.startswith("#")}
        for m in re.finditer(r"#[0-9a-fA-F]{6}\b", theme.stylesheet(t)):
            assert m.group(0).lower() in governed, m.group(0)


def test_the_canvas_did_not_move_m160_owns_that_door():
    """M159 governs CHROME. The viewport rung tokens, the sky, the
    peach and the canvas pick blue are byte-where-they-were — the
    hover/selection duo lands in M160 with its own receipts."""
    t = theme.DARK
    assert t["sky_top"] == theme.DB[".300"]
    assert t["sky_bottom"] == theme.DB[".350"]
    assert t["hover"] == "#e3ad79" and t["select"] == "#0696d7"
    assert t["hi_hover"] == theme.rgb01("#e3ad79")
    assert t["hi_sel"] == theme.rgb01("#0696d7")
    assert set(theme.LIGHT) == set(theme.DARK)       # pair discipline held


def test_the_app_wears_the_tokens():
    """Integration, source-level: tracer/app.py has EXACTLY ONE chrome
    style call and it IS theme.stylesheet(theme.DARK) — retargeting
    theme.py retargets the running product; no second source of
    chrome truth exists to drift."""
    from pathlib import Path
    src = (Path(theme.__file__).parent.parent / "app.py"
           ).read_text(encoding="utf-8")
    assert src.count("setStyleSheet(") == 1
    assert "theme.stylesheet(theme.DARK)" in src
