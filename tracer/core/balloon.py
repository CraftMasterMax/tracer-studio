"""M201 R40 - the balloon family's OWN arithmetic.

The pages, verbatim: [Create balloons] "Select an edge of the component
to identify in a drawing view." / "For Patent type balloons, click to
place the bend point for the leader." / "Click to place the balloon." /
"Press Esc to complete the Balloon command." / "The numbers in the
balloons match the Item numbers for each component in the parts list."
[Balloon reference] the DIALOG IS ONE ROW: Type - "Standard: Creates a
leader with a straight line connecting the balloon to the component." /
"Patent: Creates a leader with a curved spline connecting the balloon
to the component." (the task page's typo "a curves spline" quoted as
printed; the dialog page's form rules - the dialog's own reference
page rules its own door). [Renumber] "Specify the starting Number." /
"Select the first balloon to renumber. The balloon updates and the
parts list sorts to reflect the new number." / "The number will
automatically increment as you select balloons or bend identifiers"
(the reference page prints it without a terminal period - verbatim
reading, our arithmetic obeys it). [Align Balloons] "The left edge of
each balloon aligns along the line. The balloons distribute equally
between the two points."

Not ONE "cannot" and not ONE "must" exists in this family (a computed
scan over every page - BALLOON-FAMILY dossier), so every refusal here
rides either the IDENTITY law (a balloon number IS the table's Item,
one direction only) or the page's own WORDS ("Select an edge of the
COMPONENT" - bare paper is no component). Geometry the pages leave
unprinted (the hit region, the bubble radius, the left-edge offset
direction, which balloon wins an overlap) is OURS, named in the
function that owns it.
"""
from __future__ import annotations

import numpy as np

# [Balloon reference, verbatim members, printed order]
BALLOON_TYPES = ("Standard", "Patent")


def require_balloon_type(t) -> str:
    """The dialog prints exactly two Type members and nothing else; an
    unknown type is refused BY NAME (the page's vocabulary is the
    door's, and a third bubble shape has no page)."""
    if t not in BALLOON_TYPES:
        raise ValueError(f"BALLOON_TYPE_UNKNOWN {t!r} - the Balloon "
                         "dialog prints only Standard and Patent")
    return t


def balloon_item_at(bodies, solids, view: str, model_xy) -> int | None:
    """Which part's Item answers the click? [Create balloons, verbatim]
    "Select an edge of the component to identify" - so the click must
    land ON a component. The hit region is the projected bounding box
    of the solid in the view's own basis (OURS, named: the page prints
    no region for a 2D paper); the Item number RE-WALKS the exact
    parts_list()/balloon_targets() key order - identity by SHARED
    arithmetic, never a copied number. Overlap: the SMALLEST containing
    region wins (OURS, named - the tighter claim is the edge you
    meant); a click on bare paper answers None, and the UI says no in
    the page's own words."""
    from .drawing import _basis, _stem                    # one walk, one home
    _d, px, py = _basis(view)
    cand = []                                             # (area, item)
    item_of = {}
    for b in bodies or []:
        if not b.get("visible", True):
            continue
        name = b.get("name", "")
        s = solids.get(name) if solids else None
        vol = round(float(s.volume), 6) if s is not None else None
        key = (_stem(name), vol, b.get("material") or "")
        if key in item_of:
            continue
        item_of[key] = len(item_of) + 1
        if s is None:
            continue                                      # no mesh, no region
        lo, hi = s.bounding_box
        us, vs = [], []
        for i in (0, 1):
            for j in (0, 1):
                for k in (0, 1):
                    c = np.array((lo[0] + i * (hi[0] - lo[0]),
                                  lo[1] + j * (hi[1] - lo[1]),
                                  lo[2] + k * (hi[2] - lo[2])), float)
                    us.append(float(np.dot(c, px)))
                    vs.append(float(np.dot(c, py)))
        u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
        if u0 - 1e-9 <= model_xy[0] <= u1 + 1e-9 and \
           v0 - 1e-9 <= model_xy[1] <= v1 + 1e-9:
            cand.append(((u1 - u0) * (v1 - v0), item_of[key]))
    if not cand:
        return None
    return min(cand)[1]                                   # smallest region wins


def balloon_entry(item: int, anchor, bubble, type_: str = "Standard",
                  bend=None) -> dict:
    """One balloon, stored the way the view painter reads it: the
    ANCHOR rides the design (model mm, M110's law - a spun view carries
    it), the BUBBLE rides the paper (sheet mm - "Click to place the
    balloon" places ON THE SHEET). A bend point belongs to the Patent
    spline only; a Standard asked to carry one DROPS it (OURS, named -
    the page draws the bend point FOR PATENT TYPE BALLOONS and prints
    no prohibition to fight)."""
    require_balloon_type(type_)
    e = {"item": int(item),
         "x": float(anchor[0]), "y": float(anchor[1]),
         "bx": float(bubble[0]), "by": float(bubble[1]),
         "type": type_}
    if type_ == "Patent" and bend is not None:
        e["bend"] = (float(bend[0]), float(bend[1]))
    return e


def place_balloon(pins, entry) -> list:
    """The sheet's balloon list AFTER one placement, under the R39
    identity law: the SAME Item number can never sit at two anchors,
    so a placement REPLACES that item's pin (this is the page's "move"
    affordance made physical - [Create balloons Note] "You can add,
    delete, move, or re-associate balloons"); every unrelated pin -
    hand-placed or auto - survives untouched (replace-by-ITEM, the law
    the parts list already lives by)."""
    out = [p for p in pins or [] if p.get("item") != entry["item"]]
    out.append(dict(entry))
    return out


def renumber_map(selected_items, start: int) -> dict:
    """"Select the first balloon to renumber" ... "The number will
    automatically increment as you select balloons or bend identifiers"
    - the arithmetic is exactly selection-order + start + auto-increment.
    Returns {old item: new item}. A selection that names the same old
    item twice is a click the tool never sees (the balloon renumbers as
    it is selected, the second click hits the NEW number) - refused by
    IDENTITY, not by a printed prohibition."""
    start = int(start)
    if start < 1:
        raise ValueError(f"BALLOON_RENUMBER_START {start} - item numbers "
                         "count parts from 1 (identity: the balloon IS the "
                         "table's Item)")
    if len(set(selected_items)) != len(selected_items):
        raise ValueError("BALLOON_RENUMBER_DUPLICATE - a renumbered balloon "
                         "cannot be selected twice (identity law)")
    return {int(old): start + i for i, old in enumerate(selected_items)}


def apply_renumber(pins, mapping) -> list:
    """The pins AFTER renumber, in SHEET order. [verbatim] "The balloons
    renumber on the sheet as you select them." Collisions are impossible
    by construction: mapping is injective (start + i) and renumber
    permutes; an item the mapping does not mention keeps its number."""
    out = []
    for p in pins or []:
        q = dict(p)
        if q.get("item") in mapping:
            q["item"] = mapping[q["item"]]
        out.append(q)
    return out


def renumbered_rows(rows, mapping) -> list:
    """"The balloon updates and the parts list sorts to reflect the new
    number." Rows are still DERIVED (never stored) - the mapping is the
    sheet's, keyed by the row's DERIVED Item; each row carries the new
    number, and the list SORTS by it. Identity kept: the row's other
    facts (description, qty, material, mass) travel with it."""
    out = [dict(r, item=int(renumber_display(mapping, r["item"])))
           for r in rows or []]
    return sorted(out, key=lambda r: r["item"])


def normalize_mapping(mapping) -> dict:
    """The sheet stores the renumber mapping through JSON, which turns
    every int key into a string - the read side normalises (OURS, named:
    the page prints numbers, not dictionary keys)."""
    return {int(k): int(v) for k, v in (mapping or {}).items()}


def renumber_display(mapping, item) -> int:
    """What number does this balloon READ right now? Identity first: a
    derived Item nobody renumbered still answers its own number; the
    mapping is the sheet's only re-numbering voice."""
    m = normalize_mapping(mapping)
    return m.get(int(item), int(item))


def merge_renumber(mapping, clicked_displayed, start: int,
                   live_items=()) -> dict:
    """One CLICK of the renumber tool folded into the sheet's CUMULATIVE
    mapping. [verbatim] "The number will automatically increment as you
    select balloons" and "The balloon updates and the parts list sorts"
    - the session's arithmetic is m232's renumber_map (duplicate
    displayed numbers refuse by IDENTITY); the fold retargets every
    DERIVED item currently reading the clicked number. A displayed
    number no stored key answers is the derived item ITSELF (identity:
    un-renumbered items read their own number). Keys stay the derived
    Items - the parts list re-keys by them, one walk, one truth.
    THE SWAP IS OURS, NAMED (the page prints no collision rule): the
    number the click takes was somebody else's voice - "the numbers in
    the balloons match the Item numbers" forbids two readouts wearing
    one number - so the displaced reader (a keyed mapping entry, or an
    un-renumbered DERIVED item the mapping is silent about - live_items
    answers which) moves into the number the click vacated. Bijection
    by construction: distinct items, distinct numbers, every click."""
    session = renumber_map([int(clicked_displayed)], start)
    out = normalize_mapping(mapping)
    d, new = int(clicked_displayed), int(start)
    moved = [k for k in out if out[k] == d]
    if moved:
        for k in moved:
            out[k] = new
    else:
        out[d] = new
        moved = [d]
    if d != new:
        bumped = [k for k in out if k not in moved and out[k] == new]
        if bumped:
            for k in bumped:
                out[k] = d
        elif new in {int(i) for i in live_items or ()} \
                and new not in out:
            out[new] = d               # the silent identity reader moves
    assert session[d] == new
    return out


RENUMBER_TYPES = ("Automatic", "Balloon", "Bend Identifier")


def require_renumber_type(t) -> str:
    """The Renumber reference prints EXACTLY three Type members and
    nothing else; every unknown is refused BY NAME. "Bend Identifier"
    is refused BY NAME TOO - it is the page's own word, but it renumbers
    the BENDS of a bend table, and no bend table ships: the refusal
    prints the reason rather than quietly mapping bends onto balloons
    (the [Automatic] clause "based on selection" is the ONLY automatic
    the page documents; ours reads selection, which here is balloons)."""
    if t not in RENUMBER_TYPES:
        raise ValueError(f"BALLOON_RENUMBER_TYPE_UNKNOWN {t!r} - the "
                         "Renumber dialog prints only Automatic, Balloon "
                         "and Bend Identifier")
    if t == "Bend Identifier":
        raise ValueError("BALLOON_RENUMBER_BEND_IDENTIFIER - the "
                         "\"Bend Identifier\" member renumbers bends "
                         "only through a bend table; Tracer ships none, "
                         "so the member is refused by NAME, never mapped "
                         "onto balloons")
    return t


def align_balloons(entries, a, b, r: float = 3.4) -> list:
    """[Align balloons, verbatim result] "The left edge of each balloon
    aligns along the line. The balloons distribute equally between the
    two points." The two clicks give the line; n balloons sit at the n
    EQUAL STATIONS between them (endpoints INCLUDED - "between the two
    points", OURS named for the inclusive reading; one balloon answers
    the start point). Each bubble's LEFT EDGE rides the line, so the
    CENTRE is pushed r along the line's direction (OURS, named: the
    page prints the edge law, never the radius - r is the painter's
    own bubble radius default). Anchors and every other field are
    carried untouched; the selection order is the pin order."""
    pts = list(entries or [])
    if not pts:
        return []
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    dx, dy = bx - ax, by - ay
    ln = float(np.hypot(dx, dy))
    if ln <= 0.0:
        raise ValueError("BALLOON_ALIGN_DEGENERATE - the two clicks must "
                         "make a line (the page places a start AND an end "
                         "point)")
    ux, uy = dx / ln, dy / ln                       # the line's own direction
    n = len(pts)
    out = []
    for i, e in enumerate(pts):
        t = 0.0 if n == 1 else i / (n - 1)
        px = ax + t * dx + r * ux                   # centre = station + r along
        py = ay + t * dy + r * uy
        q = dict(e)
        q["bx"], q["by"] = px, py
        out.append(q)
    return out
