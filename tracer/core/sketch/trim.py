"""Trim / extend two lines to their corner.

The maker's cleanup verb: draw the lines of a profile freehand (they
overshoot, fall short, leave gaps) and then close each corner with one
command.  Unlike a drag, the result is EXACT — the loose ends land on
the intersection of the two infinite lines — and the two end Points are
MERGED into one shared Point, because to_loops() joins geometry through
shared identity, not coincident coordinates.

    ╲      ╱  gap          ╲    ╱
     ╲    ╱     ──────►     ╲  ╱      one point, one corner
      ╲  ╱  overshoot        ╲╱

Safety rules (v1):
  * only a FREE end moves — used by exactly this line (no arcs/circles
    sharing it) and referenced by NO constraint, so trimming can never
    tear a joined corner or fight a dimension;
  * an end may EXTEND any distance (X lies beyond it), but may only be
    TRIMMED (X inside the span) when it is a small stub — so a
    T-junction's through-bar or a true X crossing is never halved.
"""
from __future__ import annotations

import math

from .entities import Line, Point

PAR_TOL = 1e-9
STUB_MAX = 0.4                     # an inside-crossing may only cut off
                                   # this fraction of the line's length


def close_corner(model, l1: Line, l2: Line) -> Point:
    """Move the near, free, unconstrained ends of l1/l2 together onto
    their infinite-line intersection and merge them into ONE Point.
    Returns the corner point. Raises ValueError with a user reason."""
    if l1 is l2:
        raise ValueError("Select two different lines")
    if any(p is l2.a or p is l2.b for p in (l1.a, l1.b)):
        raise ValueError("These lines already share a corner")

    X = _intersect(l1, l2)
    if X is None:
        raise ValueError("These lines are parallel — no corner to close")

    c1 = _candidate(model, l1, X)
    c2 = _candidate(model, l2, X)
    if c1 is None and c2 is None:
        _explain(model, l1, l2, X)          # always raises

    P = c1 if c1 is not None else c2
    if c1 is not None and c2 is not None:
        _rewire(l2, c2, P)                  # l2 adopts l1's corner point
        _drop(model, c2)                    # the loser leaves sk.points
    P.x, P.y = X
    return P


# ---- plumbing ----------------------------------------------------------------

def _intersect(l1, l2):
    """Point where the INFINITE lines meet, or None if parallel."""
    x1, y1, x2, y2 = l1.a.x, l1.a.y, l1.b.x, l1.b.y
    x3, y3, x4, y4 = l2.a.x, l2.a.y, l2.b.x, l2.b.y
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < PAR_TOL * max(1.0, math.hypot(x2 - x1, y2 - y1)
                                           * math.hypot(x4 - x3, y4 - y3)):
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return x1 + t * (x2 - x1), y1 + t * (y2 - y1)


def _usage(model, p: Point) -> int:
    """How many entities terminate at (or are centred on) this point."""
    n = 0
    for e in (model.sketch.lines + model.sketch.arcs):
        n += sum(pt is p for pt in _endpoints(e))
    n += sum(c.c is p for c in model.sketch.circles)
    return n


def _constrained(model) -> set:
    refs = set()
    for c in model.sketch.constraints:
        for e in c.entities():
            if isinstance(e, Point):
                refs.add(id(e))
    return refs


def _candidate(model, line, X):
    """The end of `line` that should travel to X, else None.
    Extend (X beyond an end): the near end moves any distance.
    Trim  (X inside the span): only a STUB may be cut — never half a
    line — which is what protects a T-junction's through-bar (crossing
    mid-span: both ends are ~50 % away -> refused) and a true X."""
    refs = _constrained(model)
    ax, ay, bx, by = line.a.x, line.a.y, line.b.x, line.b.y
    length = math.hypot(bx - ax, by - ay)
    if length < 1e-9:
        return None
    s = ((X[0] - ax) * (bx - ax) + (X[1] - ay) * (by - ay)) / length
    p, at = min(((line.a, 0.0), (line.b, length)),
                key=lambda e: abs(s - e[1]))
    # ONLY the geometrically nearest end may move: if it's joined into a
    # corner or carries a constraint, this line stays put — the far end
    # must never swap sides (that would stretch the line backwards)
    if _usage(model, p) != 1 or id(p) in refs:
        return None
    move = abs(s - at)                          # distance this end travels
    inside = -1e-9 <= s <= length + 1e-9
    if inside and move > STUB_MAX * length:
        return None
    return p


def _explain(model, l1, l2, X):
    """Distinguish WHY nothing could move — a refusal that names the
    culprit is worth three that don't."""
    refs = _constrained(model)
    for line in (l1, l2):
        for p in (line.a, line.b):
            if _usage(model, p) == 1 and id(p) not in refs:
                raise ValueError(
                    "These lines cross mid-span — trim only cuts a stub, "
                    "and neither end is one; drag an end past the crossing")
    for line in (l1, l2):
        for p in (line.a, line.b):
            if _usage(model, p) == 1 and id(p) in refs:
                raise ValueError(
                    "That end carries a constraint — trim needs "
                    "unconstrained ends")
    raise ValueError("Every end is already joined — nothing to trim")


def _endpoints(e):
    return (e.a, e.m, e.b) if hasattr(e, "m") else (e.a, e.b)


def _rewire(line, old, new):
    if line.a is old:
        line.a = new
    else:
        line.b = new


def _drop(model, p: Point):
    pts = model.sketch.points
    if any(q is p for q in pts):
        pts[:] = [q for q in pts if q is not p]
