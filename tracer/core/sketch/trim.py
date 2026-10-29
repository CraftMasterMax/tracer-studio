"""Trim / extend two lines to their corner — and the CUT that trim-to-click
needs (M168).

The maker's cleanup verb: draw the lines of a profile freehand (they
overshoot, fall short, leave gaps) and then close each corner with one
command.  Unlike a drag, the result is EXACT — the loose ends land on
the intersection of the two infinite lines — and the two end Points are
MERGED into one shared Point, because to_loops() joins geometry through
shared identity, not coincident coordinates.

    ╲      ╱  gap          ╲    ╱
     ╲    ╱     ──────►     ╲  ╱      one point, one corner
      ╲  ╱  overshoot        ╲╱

split_entity() is the same identity law read in reverse: one entity
becomes TWO that SHARE one new seam Point, so a profile keeps closing
across the cut exactly as before.  Constraints re-home by a v1 law of two
clauses: a SHA-class fact (parallel, horizontal, ...) is TRUE of every
piece and is copied to both sides; anything METRIC or position-bound
along the eaten entity (Equal length, Midpoint, PointOnLine, ...) is
AMBIGUOUS across a cut and is DROPPED — consumption rides delete_entity
(constraints drop, fx bindings follow).  Refusals land BEFORE mutation.

Safety rules (v1):
  * only a FREE end moves — used by exactly this line (no arcs/circles
    sharing it) and referenced by NO constraint, so trimming can never
    tear a joined corner or fight a dimension;
  * an end may EXTEND any distance (X lies beyond it), but may only be
    TRIMMED (X inside the span) when it is a small stub — so a
    T-junction's through-bar or a true X crossing is never halved.
"""
from __future__ import annotations

import dataclasses
import math

from ..snaps import _arc_span, _circumference
from .constraints import (Angle, Collinear, Horizontal, Parallel,
                          Perpendicular, Radius, Symmetry, Vertical)
from .entities import Arc, Line, Point

PAR_TOL = 1e-9
STUB_MAX = 0.4                     # an inside-crossing may only cut off
                                   # this fraction of the line's length
SPLIT_ON_TOL = 1e-6                # a cut point must lie ON the curve
SPLIT_END_TOL = 1e-6               # ... and strictly inside its ends
SHA = (Horizontal, Vertical, Angle, Parallel, Perpendicular, Collinear,
       Radius, Symmetry)           # kind-facts: true of every piece


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


# ---- the CUT (M168 R1) -------------------------------------------------------

def split_entity(model, ent, x, y):
    """Cut `ent` at (x, y) into (left, right) sharing ONE new seam Point —
    identity keeps every profile closed across the seam.  Lines and arcs
    split; circles, ellipses and points refuse (v1).  SHA-class constraint
    facts are re-copied to BOTH halves; metric/positional facts naming the
    eaten entity drop with it (delete_entity's consumption, fx included).
    Raises ValueError BEFORE touching the model when the cut is illegal."""
    sk = model.sketch
    if isinstance(ent, Line):
        left, right = _cut_line(sk, ent, x, y)
        lines = True
    elif isinstance(ent, Arc):
        left, right = _cut_arc(sk, ent, x, y)
        lines = False
    else:
        raise ValueError("Only lines and arcs can be split (yet)")
    pool = sk.lines if lines else sk.arcs
    idx = next(i for i, e in enumerate(pool) if e is ent)
    rehome = []
    for c in sk.constraints:
        if isinstance(c, SHA) and any(e is ent for e in c.entities()):
            rehome += [_rehome(c, ent, left), _rehome(c, ent, right)]
    model.delete_entity(ent)               # consumes: drops its constraints,
    pool = sk.lines if lines else sk.arcs  #  fx follow; arcs REBIND the list,
    pool[idx:idx] = [left, right]          #  so RE-FETCH, then the halves
    sk.constrain(*rehome)                  #  land in the eaten one's own spot
    return left, right


def _cut_line(sk, l, x, y):
    ax, ay, bx, by = l.a.x, l.a.y, l.b.x, l.b.y
    L = math.hypot(bx - ax, by - ay)
    if L < 1e-9:
        raise ValueError("This line has no length to split")
    t = ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / (L * L)
    along = t * L
    off = abs((x - ax) * (by - ay) - (y - ay) * (bx - ax)) / L
    if off > SPLIT_ON_TOL or not -SPLIT_ON_TOL <= along <= L + SPLIT_ON_TOL:
        raise ValueError("The cut must lie ON the curve")
    if min(along, L - along) < SPLIT_END_TOL * max(1.0, L):
        raise ValueError("Split the middle of a segment, not an end")
    S = sk.point(x, y)
    return (Line(l.a, S, l.construction), Line(S, l.b, l.construction))


def _cut_arc(sk, ar, x, y):
    geo = _circumference(ar.a, ar.m, ar.b)
    if geo is None:
        raise ValueError("This arc has no circle to split on")
    cx, cy, r = geo
    if abs(math.hypot(x - cx, y - cy) - r) > SPLIT_ON_TOL:
        raise ValueError("The cut must lie ON the curve")
    a0, sw = _arc_span(ar.a, ar.m, ar.b, cx, cy)

    def frac(px, py):                      # angular position in [0, 1]
        da = math.atan2(py - cy, px - cx) - a0
        da = da % (2 * math.pi) if sw > 0 else -((-da) % (2 * math.pi))
        return da / sw

    fS = frac(x, y)
    if min(fS, 1 - fS) * abs(sw) * r < SPLIT_END_TOL * max(1.0, r):
        raise ValueError("Split the middle of an arc, not an end")
    S = sk.point(x, y)

    def at(f):                             # arc point at span-fraction f
        a = a0 + sw * f
        return Point(cx + r * math.cos(a), cy + r * math.sin(a))

    return (Arc(ar.a, at(fS / 2), S, ar.construction),
            Arc(S, at((1 + fS) / 2), ar.b, ar.construction))


def _rehome(c, ent, side):
    """Copy a SHA constraint onto one half: identity-swap the field(s)
    naming the eaten entity; the src stamp (structural provenance) rides
    the copy — a split is structural, its copies are never removable."""
    kw = {f.name: side for f in dataclasses.fields(c)
          if getattr(c, f.name) is ent}
    n = dataclasses.replace(c, **kw)
    if getattr(c, "src", ""):
        setattr(n, "src", c.src)
    return n


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
