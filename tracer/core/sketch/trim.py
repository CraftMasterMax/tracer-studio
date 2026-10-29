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

from ..snaps import _arc_span, _circumference, _intersections
from .constraints import (Angle, Coincident, Collinear, Horizontal,
                          Parallel, Perpendicular, Radius, Symmetry,
                          Vertical)
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


# ---- the WELD (M170 R1) ------------------------------------------------------

def weld_points(model, keep: Point, gone: Point) -> Point:
    """Fuse TWO Points into ONE identity - close_corner's private merge
    read as a verb.  The drag magnet promises a catch KEEPS: after a
    weld every entity and EVERY constraint that named `gone` names
    `keep` (a metric fact bound to that corner FOLLOWS the corner - the
    two points are now ONE thing, so re-homing is never ambiguous the way
    a cut is), a Coincident that welded itself shut is vacuous and DIES,
    and `gone` leaves sk.points exactly as close_corner's loser does.
    keep's coordinates WIN (the magnet target the user aimed at). Refuses
    BEFORE mutation. No hist push - the caller's gesture owns the one
    snapshot the drag already paid."""
    if keep is gone:
        raise ValueError("That point is already this point")
    sk = model.sketch
    if not any(p is gone for p in sk.points):
        raise ValueError("That point is no longer in the sketch")

    def rehome(carrier):                       # every attribute that IS
        for f, v in list(vars(carrier).items()):   # the loser becomes the
            if v is gone:                      #  survivor - identity by
                setattr(carrier, f, keep)      #  scan, no per-class law
    for e in (list(sk.lines) + list(sk.arcs) + list(sk.circles)
              + list(sk.ellipses)):
        rehome(e)
    for c in sk.constraints:
        rehome(c)
    sk.constraints[:] = [c for c in sk.constraints
                         if not (isinstance(c, Coincident) and c.p is c.q)]
    _drop(model, gone)
    return keep


# ---- the CUT (M168 R1) -------------------------------------------------------

def split_entity(model, ent, x, y, seam=None):
    """Cut `ent` at (x, y) into (left, right) sharing ONE seam Point —
    identity keeps every profile closed across the seam.  `seam` (an
    EXISTING Point at the cut, e.g. a T-junction's stem end) is REUSED —
    two Point objects at one coordinate would silently un-join the seam.
    Lines and arcs split; circles, ellipses and points refuse (v1).  SHA-class
    constraint facts are re-copied to BOTH halves; metric/positional facts
    naming the eaten entity drop with it (delete_entity's consumption, fx
    included).  Raises ValueError BEFORE touching the model when the cut
    is illegal."""
    sk = model.sketch
    if isinstance(ent, Line):
        left, right = _cut_line(sk, ent, x, y, seam)
        lines = True
    elif isinstance(ent, Arc):
        left, right = _cut_arc(sk, ent, x, y, seam)
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


def _cut_line(sk, l, x, y, seam=None):
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
    S = seam if seam is not None else sk.point(x, y)
    return (Line(l.a, S, l.construction), Line(S, l.b, l.construction))


def _cut_arc(sk, ar, x, y, seam=None):
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
    S = seam if seam is not None else sk.point(x, y)

    def at(f):                             # arc point at span-fraction f
        a = a0 + sw * f
        return Point(cx + r * math.cos(a), cy + r * math.sin(a))

    return (Arc(ar.a, at(fS / 2), S, ar.construction),
            Arc(S, at((1 + fS) / 2), ar.b, ar.construction))


def piece_bounds(model, ent, x, y):
    """(bounds, t0, cuts): THE PIECE QUESTION for a click - the sorted
    boundary parameters of every piece `ent` is cut into by interior
    crossings, the click's clamped parameter, and the merged cut Snaps
    (tangent double-roots collapsed to one).  READ-ONLY: the hover
    preview and the trim verb share this one question.  None for a
    Point; circles and ellipses answer whole: [0, 1]."""
    if isinstance(ent, Point):
        return None
    sk = model.sketch
    if not isinstance(ent, (Line, Arc)):
        return [0.0, 1.0], 0.5, []                  # one piece, any click
    span = _length_of(ent)
    t0 = min(max(_frac(ent, x, y), 0.0), 1.0)       # the click's parameter
    sn: list = []
    _intersections(sk, sn)
    cuts: list = []
    for s in sn:
        if s.entity is ent or s.entity2 is ent:
            t = _frac(ent, s.x, s.y)
            if _cut_lo(span) < t < 1 - _cut_lo(span):      # interior only:
                cuts.append((t, s))                        #  ends are EDGES
    cuts.sort(key=lambda ts: ts[0])
    merged: list = []
    for t, s in cuts:                               # tangent double-roots
        if merged and abs(t - merged[-1][0]) * span < 1e-7:
            continue
        merged.append((t, s))
    return [0.0] + [t for t, _ in merged] + [1.0], t0, merged


def trim_piece(model, ent, x, y):
    """THE TRIM VERB: cut `ent` at every interior crossing and delete the
    PIECE under (x, y).  An UNCROSSED entity is one piece and goes whole
    (Fusion: Trim on a lonely line erases it); circles and ellipses are
    un-splittable, so they are one piece too.  A click exactly ON a cut is
    ambiguous - nothing is deleted and None comes back; the refusal lands
    BEFORE any mutation (split only after the piece question is settled).
    Only the clicked entity is cut - its neighbours keep their shape (v1).
    Cuts REUSE an existing Point sitting at the crossing (a T-junction's
    stem end): two Points at one coordinate would silently un-join it.
    Returns the deleted entity, or None."""
    pb = piece_bounds(model, ent, x, y)
    if pb is None:                                  # a Point is not trimmable
        return None
    bounds, t0, merged = pb
    if not isinstance(ent, (Line, Arc)):            # circle / ellipse: one
        model.delete_entity(ent)                    #  piece - gone whole
        return ent
    sk = model.sketch
    span = _length_of(ent)
    for b in bounds:                                # ON a cut? refuse first -
        if abs(t0 - b) * span < 1e-7:               #  the model never learns
            return None                             #  the cut was considered
    pieces = []
    cur = ent
    for t, s in merged:                             # sorted ASC: every later
        left, cur = split_entity(model, cur, s.x, s.y,   #  cut lives in the
                                 seam=_point_on(sk, s.x, s.y))  # right piece
        pieces.append(left)
    pieces.append(cur)
    for i in range(len(pieces)):
        if bounds[i] <= t0 <= bounds[i + 1]:
            victim = pieces[i]
            break
    model.delete_entity(victim)                     # metric facts die with
    return victim                                   #  it; the survivors keep
    #                                                the SHA copies R1 mints


def trim_stroke(model, touches):
    """THE SCRIBE (M169 R2): a whole gesture at once - touches
    [(entity, x, y)] in STROKE ORDER, and per touch the piece CONTAINING it
    falls (trim_piece, M168's verb, is the only mutation).  A stroke is ONE
    verb and never warns mid-word: an ON-cut touch, a Point, and a
    DEAD/consumed entity all skip SILENTLY.  A cut CONSUMES the original
    (split identity), so a second touch naming the same object names
    nothing - the next resolution of a live canvas names the survivor, and
    a survivor touched again loses its remaining piece too.  Returns the
    fallen entities in the order they fell.  NO history push: the caller
    owns ONE push per gesture (m167's drag law)."""
    sk = model.sketch
    fallen = []
    for ent, x, y in touches:
        if not any(ent is e for grp in (sk.lines, sk.arcs, sk.circles,
                                        sk.ellipses) for e in grp):
            continue                                # dead or a Point: hush
        gone = trim_piece(model, ent, x, y)
        if gone is not None:                        # ON a cut: hush too
            fallen.append(gone)
    return fallen


def extend_end(model, ent, x, y):
    """TRIM's OTHER half: when the clicked piece runs OFF an open end that
    another line crosses AHEAD of that end, the end is EXTENDED onto the
    crossing instead of anything being deleted (Fusion trims a stub TO a
    boundary).  The end must be FREE (one user, no constraint - close_
    corner's own safety law) and the partner is cut at the crossing
    REUSING the travelling end Point: after the move ONE Point serves the
    stub, the joint and both partner halves - a true joined T that the
    profile sees.  Raises ValueError with a reason ("Nothing to trim to
    beyond that end") - the caller falls back to deleting the piece.
    v1: straight lines only."""
    pb = piece_bounds(model, ent, x, y)
    if pb is None or not isinstance(ent, Line):
        raise ValueError("Only straight lines can be extended (yet)")
    bounds, t0, _cuts = pb
    for i in range(len(bounds) - 1):
        if bounds[i] <= t0 <= bounds[i + 1]:
            lo, hi = bounds[i], bounds[i + 1]
            break
    cands = []                                      # only the piece's sides
    if lo <= 1e-12:                                 #  at the entity's OWN
        cands.append((t0, ent.a))                   #   ends can be open -
    if hi >= 1 - 1e-12:                             #  a side bounded by a
        cands.append((1.0 - t0, ent.b))             #   CUT is already joined
    cands.sort(key=lambda c: c[0])                  # nearest to the click
    span = _length_of(ent)
    ax, ay, bx, by = ent.a.x, ent.a.y, ent.b.x, ent.b.y
    refs = _constrained(model)
    for _d, p in cands:
        if _usage(model, p) != 1 or id(p) in refs:
            continue                                # not a FREE end
        for other in model.sketch.lines:
            if other is ent:
                continue
            X = _intersect(ent, other)
            if X is None:
                continue                            # parallel: no junction
            s = ((X[0] - ax) * (bx - ax) + (X[1] - ay) * (by - ay)) / span
            ahead = (s > span + 1e-7) if p is ent.b else (s < -1e-7)
            if not ahead:
                continue                            # not beyond THIS end
            oa, ob = other.a, other.b
            L2 = (ob.x - oa.x) ** 2 + (ob.y - oa.y) ** 2
            if L2 < 1e-18:
                continue
            so = ((X[0] - oa.x) * (ob.x - oa.x)
                  + (X[1] - oa.y) * (ob.y - oa.y)) / L2
            if not _cut_lo(math.sqrt(L2)) < so < 1 - _cut_lo(math.sqrt(L2)):
                continue                            # joint must sit INSIDE
            split_entity(model, other, X[0], X[1], seam=p)   # the partner
            p.x, p.y = X                            #  adopts the travelling
            return ent                              #   end: ONE joint Point
    raise ValueError("Nothing to trim to beyond that end")


def _length_of(ent) -> float:
    if isinstance(ent, Line):
        return max(math.dist((ent.a.x, ent.a.y), (ent.b.x, ent.b.y)), 1e-9)
    geo = _circumference(ent.a, ent.m, ent.b)
    if not geo:
        return 1e-9
    cx, cy, r = geo
    return max(abs(_arc_span(ent.a, ent.m, ent.b, cx, cy)[1]) * r, 1e-9)


def _cut_lo(span: float) -> float:
    """Endpoint guard as a parameter fraction: a crossing nearer to an END
    than the split's own refusal keeps the end as a piece BOUNDARY."""
    return SPLIT_END_TOL * max(1.0, span) / span


def _frac(ent, x, y) -> float:
    """The entity-parameter of (x, y): fraction along a line, angular
    fraction along an arc's span (may fall outside [0, 1])."""
    if isinstance(ent, Line):
        ax, ay, bx, by = ent.a.x, ent.a.y, ent.b.x, ent.b.y
        L2 = (bx - ax) ** 2 + (by - ay) ** 2
        return ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / L2 if \
            L2 > 1e-18 else 0.0
    geo = _circumference(ent.a, ent.m, ent.b)
    if not geo:
        return 0.0
    cx, cy, _r = geo
    a0, sw = _arc_span(ent.a, ent.m, ent.b, cx, cy)
    da = math.atan2(y - cy, x - cx) - a0
    da = da % (2 * math.pi) if sw > 0 else -((-da) % (2 * math.pi))
    return da / sw


def _point_on(sk, x, y):
    """An existing Point sitting at (x, y) within 1e-7, else None - the
    identity a crossing-cut must REUSE (T-junction stems end ON a curve)."""
    for p in sk.points:
        if math.hypot(p.x - x, p.y - y) < 1e-7:
            return p
    return None


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
