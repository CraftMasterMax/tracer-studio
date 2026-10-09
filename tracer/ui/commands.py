"""M113 command layer: one key table, one search index, one truth.

The keyboard rules (the contract tests/test_m113.py pins):
  * A key that Fusion owns in a context does what Fusion does there
    (hotkeys.md [V]) — S// anywhere but text = command search,
    E extrude, H hole, F fillet, M move, Q press-pull, A appearance,
    V visibility, F6 fit, Ctrl+B compute, Ctrl+4..7 visual styles,
    Ctrl+Alt layout layers, X construction toggle in sketches,
    Enter finishes a sketch, L/R/C draw, T trims, O offsets, P projects.
  * Tracer-only commands live on keys Fusion leaves free in every
    context (K slot, Y polygon, A arc-in-sketch, the constraint
    letters, 0-3 view orientations — a documented BEAT: Fusion has no
    orientation keys at all).
  * Menu entries display their key (``text`` after a tab) but carry no
    live shortcut: single keys are dispatched by MainWindow's table so
    the sketch canvas can keep its own letters.  Ctrl-combos stay as
    real QAction shortcuts (they never race sketch widgets).

``collect_commands`` feeds the palette from the menu tree itself — a
new menu entry is searchable for free; sketch tools join as synthetic
entries so S finds them too.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

# ---- the model-context single-key table --------------------------------------
# key sequence -> (palette label, MainWindow method name).  "viewport:"
# methods live on the viewport widget (they need hover/camera state);
# they are routed there by the dispatcher.
MODEL_KEYS: dict[str, tuple[str, str]] = {
    "E":        ("Extrude / finish active sketch profile", "action_extrude_key"),
    "F":        ("Fillet body edges…", "act_fillet"),
    "H":        ("Hole…", "action_hole"),
    "M":        ("Move body (triad)", "action_move_body"),
    "A":        ("Appearance / material…", "action_appearance"),
    "V":        ("Hide/show active body", "action_toggle_active_visible"),
    "G":        ("Toggle grid", "action_toggle_grid"),
    "F6":       ("Zoom to fit", "viewport:home"),
    "0":        ("View: Isometric", "view:iso"),
    "1":        ("View: Front", "view:front"),
    "2":        ("View: Top", "view:top"),
    "3":        ("View: Right", "view:right"),
    "Z":        ("Zoom to selection", "viewport:zoom_to_selection"),
    "Ctrl+B":   ("Compute All", "action_recompute"),
    "Ctrl+4":   ("Visual style: Shaded", "style:Shaded"),
    "Ctrl+5":   ("Visual style: Shaded with edges", "style:Shaded with edges"),
    "Ctrl+6":   ("Visual style: Ghosted", "style:Ghosted"),
    "Ctrl+7":   ("Visual style: Wireframe", "style:Wireframe"),
    "Ctrl+Alt+V": ("Show/hide ViewCube", "layout:cube"),
    "Ctrl+Alt+B": ("Show/hide Browser", "layout:browser"),
    "Ctrl+Alt+N": ("Show/hide Navigation bar", "layout:nav"),
    "Ctrl+Alt+D": ("Show/hide Datum letters", "layout:datums"),
    "Ctrl+Alt+R": ("Reset panel layout", "layout:reset"),
}

# ---- the sketch-context single-key table (widget-owned; bubbles to model) -----
# key display -> label, for the palette + the sketch widget's override set
SKETCH_KEYS: dict[str, tuple[str, str]] = {
    "L":        ("Sketch: Line", "tool:line"),
    "R":        ("Sketch: Rectangle", "tool:rect"),
    "C":        ("Sketch: Circle", "tool:circle"),
    "A":        ("Sketch: Arc", "tool:arc"),
    "Y":        ("Sketch: Polygon", "tool:poly"),
    "K":        ("Sketch: Slot", "tool:slot"),
    "Shift+C":  ("Sketch: Ellipse", "tool:ellipse"),
    "O":        ("Sketch: Offset (Fusion key)", "tool:offset"),
    "U":        ("Sketch: Offset (classic alias)", "tool:offset"),
    "T":        ("Sketch: Trim corner (two lines)", "tool:trim"),
    "Shift+T":  ("Sketch: Tangent constraint", "tool:tangent"),
    "D":        ("Sketch: Dimension", "tool:dim"),
    "H":        ("Sketch: Horizontal constraint", "tool:H"),
    "V":        ("Sketch: Vertical constraint", "tool:V"),
    "F":        ("Sketch: Fix / fillet corner", "tool:F"),
    "G":        ("Sketch: Chamfer corner (two lines)", "tool:G"),
    "P":        ("Sketch: Project model edges", "tool:project"),
    "Shift+P":  ("Sketch: Perpendicular constraint", "tool:perp"),
    "Q":        ("Sketch: Equal-length constraint", "tool:equal"),
    "I":        ("Sketch: Angle constraint", "tool:angle"),
    "J":        ("Sketch: Midpoint constraint", "tool:midpoint"),
    "M":        ("Sketch: Symmetry constraint", "tool:symmetry"),
    "Shift+M":  ("Sketch: Mirror entities", "tool:mirror"),
    "2":        ("Sketch: Concentric (two circles)", "tool:concentric"),
    ".":        ("Sketch: On-curve constraint", "tool:on"),
    "X":        ("Sketch: Construction toggle", "tool:construction"),
    "Enter":    ("Finish sketch (extrude profile)", "tool:finish"),
    "Shift+R":  ("Revolve sketch profile", "tool:revolve"),
    "Esc":      ("Cancel tool / clear selection", "tool:cancel"),
}

# the sketch keys that are plain printable chars and therefore must be
# claimed from Qt's shortcut-override system by the sketch widget itself
SKETCH_PLAIN_KEYS = {k for k in SKETCH_KEYS
                     if "+" not in k and k not in ("Enter", "Esc")}


@dataclass
class Command:
    """One searchable, runnable thing the app can do."""
    label: str
    category: str
    key: str                       # display-only ("Ctrl+Alt+B"), may be ""
    run: Callable[[], None]
    enabled: Callable[[], bool]    # live check (menu action enabled…)
    keywords: str = ""             # extra search fuel ("bom parts list…")

    @property
    def haystack(self) -> str:
        return f"{self.label} {self.category} {self.keywords}".lower()


def fuzzy_score(query: str, text: str) -> float | None:
    """Subsequence score, Fusion-toolbox flavour: prefix > word start >
    mid-word; a miss returns None (filtered out)."""
    q = query.lower().strip()
    if not q:
        return 0.0
    t = text.lower()
    score = 0.0
    i = 0                              # pointer in t
    word_start = True
    run = 0
    for ch in q:
        j = t.find(ch, i)
        if j < 0:
            return None
        gap = j - i
        if j == 0:
            score += 3.0                       # string prefix
        elif word_start or t[j - 1] == " ":
            score += 2.0                       # word start
        elif gap == 0:
            score += 1.0                       # contiguous run
        run = run + 1 if gap == 0 else 0
        score += min(run, 4) * 0.25            # contiguity bonus
        word_start = False
        i = j + 1
    return score - 0.1 * i                     # prefer early matches


def rank(query: str, commands: Iterable[Command]) -> list[Command]:
    """Commands matching the query, best score first (stable for ties)."""
    if not query.strip():
        return list(commands)
    scored = []
    for idx, cmd in enumerate(commands):
        s = fuzzy_score(query, cmd.haystack)
        if s is not None:
            scored.append((-s, idx, cmd))
    scored.sort()
    return [cmd for _s, _i, cmd in scored]


def collect_commands(win) -> list[Command]:
    """Every menu-bar action (category = its menu), plus synthetic
    sketch-tool entries.  Menu is the source of truth: adding an entry
    makes it searchable with no further registration."""
    from PySide6.QtGui import QAction                                  # noqa: PLC0415

    cmds: list[Command] = []
    seen: set[int] = set()
    cmds.append(Command("Command search", "Search", "S",
                        win.open_command_search, lambda: True,
                        "find run command palette toolbox"))
    mb = win.menuBar()
    for top in mb.actions():
        category = top.text().replace("&", "").rstrip("…").strip()
        sub = top.menu()
        if sub is None:
            if top.isSeparator():
                continue
            _add_qaction(cmds, seen, top, category)
            continue
        stack = [(category, sub)]
        while stack:
            cat, m = stack.pop()
            for a in m.actions():
                if a.isSeparator():
                    continue
                child = a.menu()
                if child is not None:
                    stack.append((f"{cat} ▸ {plain(a.text())}", child))
                    continue
                _add_qaction(cmds, seen, a, cat)

    for keys, (label, target) in SKETCH_KEYS.items():
        if target == "tool:cancel":
            continue
        cmds.append(Command(label=label, category="Sketch", key=keys,
                            run=_sketch_runner(win, target),
                            enabled=lambda: True))
    # the key layer itself is searchable — and this is the only route
    # to ribbon-only commands (they never enter the menu tree)
    have = {c.label.split("—")[0].strip().rstrip("…").lower()
            for c in cmds}
    for keys, (label, target) in MODEL_KEYS.items():
        if label.split("—")[0].strip().rstrip("…").lower() in have:
            continue
        cmds.append(Command(label=label, category="Shortcuts", key=keys,
                            run=lambda t=target: win._run_command(t),
                            enabled=lambda: True))
    return cmds


def plain(text: str) -> str:
    """Menu text -> display label: drop mnemonics and the \t key tail."""
    return text.split("\t")[0].replace("&", "").strip()


def _add_qaction(cmds: list[Command], seen: set[int], act: QAction,
                 category: str) -> None:
    if id(act) in seen or not plain(act.text()):
        return
    seen.add(id(act))
    key = act.text().split("\t")[1].strip() if "\t" in act.text() else ""
    if not key:
        sc = act.shortcut()
        key = sc.toString() if not sc.isEmpty() else ""
    cmds.append(Command(label=plain(act.text()), category=category, key=key,
                        run=act.trigger,
                        enabled=act.isEnabled))


def _sketch_runner(win, target: str):
    """Synthetic palette entries drive the sketch widget directly."""
    def run():
        if win.sketch.model is None:
            win.action_new_sketch()
        cv = win.sketch
        match target:
            case "tool:finish":
                cv.finish()
            case "tool:revolve":
                cv.finish(revolve=True)
            case "tool:offset":
                cv.act_offset()
            case "tool:trim":
                cv.act_trim()
            case "tool:tangent":
                cv.act_tangent()
            case "tool:dim":
                cv.act_dim()
            case "tool:H":
                cv.act_H()
            case "tool:V":
                cv.act_V()
            case "tool:F":
                cv.act_fix()
            case "tool:G":
                cv.act_chamfer()
            case "tool:project":
                win._project_model_edges()
            case "tool:perp":
                cv.act_perp()
            case "tool:equal":
                cv.act_equal()
            case "tool:angle":
                cv.act_angle()
            case "tool:midpoint":
                cv.act_midpoint()
            case "tool:symmetry":
                cv.act_symmetry()
            case "tool:mirror":
                cv.act_mirror()
            case "tool:concentric":
                cv.act_concentric()
            case "tool:on":
                cv.act_on()
            case "tool:construction":
                cv.act_construction()
            case _:                       # tool:<name> is a set_tool arg
                cv.set_tool(target.split(":", 1)[1])
        win.viewport.setFocus()
    return run
