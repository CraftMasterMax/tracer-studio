"""Newton/LM hybrid solver for 2D geometric constraints.

Numerical Jacobians on purpose: sketches here are < ~200 params, and
correct-but-simple beats clever-but-buggy for v0. Dense lstsq handles
rank-deficient (under-constrained) systems by taking the minimum-norm
correction instead of exploding.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .entities import Entity, Point, Line, Circle, Ellipse
from .constraints import Constraint, expand


@dataclass
class SolveResult:
    converged: bool
    residual_norm: float
    dof: int
    iterations: int
    failed: list = field(default_factory=list)
    redundant: list = field(default_factory=list)    # M87: add-nothing
    conflicting: list = field(default_factory=list)  # M87: won't close
    point_dof: dict = field(default_factory=dict)    # M119: point.id -> 0..2
    size_dof: dict = field(default_factory=dict)     # M186: entity.id ->
    #   0..2 for the SIZE variables a circle/ellipse also answers to -
    #   M119's null-space answer extended from point columns to size
    #   columns, so the canvas can colour ONE entity at a time (LAW-55).
    free_dirs: dict = field(default_factory=dict)  # M119: point.id -> (dx,dy)
    # M164 R1 "the solver remembers": the FINAL linear-algebra state,
    # kept so on-demand questions (which ONE constraint could I delete to
    # fix this?) answer with rank algebra, never a re-solve.  rank=-1 is
    # the sentinel for "not computed" - the UI must never render it.
    rank: int = -1
    final_J: object = None
    final_r: object = None
    rows: list = field(default_factory=list)     # tagged expanded rows

    def __bool__(self): return self.converged


class Sketch:
    def __init__(self):
        self.points: list[Point] = []
        self.lines: list[Line] = []
        self.circles: list[Circle] = []
        self.arcs: list["Arc"] = []
        self.ellipses: list[Ellipse] = []
        self.constraints: list[Constraint] = []

    # ---- construction ---------------------------------------------------
    def point(self, x=0.0, y=0.0) -> Point:
        p = Point(x, y)
        self.points.append(p)
        return p

    def line(self, a: Point, b: Point) -> Line:
        ln = Line(a, b)
        self.lines.append(ln)
        return ln

    def circle(self, center: Point, radius: float,
               construction: bool = False) -> Circle:
        c = Circle(center, radius, construction)
        self.circles.append(c)
        return c

    def arc(self, a: Point, m: Point, b: Point,
            construction: bool = False):
        from .entities import Arc
        ar = Arc(a, m, b, construction)
        self.arcs.append(ar)
        return ar

    def ellipse(self, center: Point, rx: float, ry: float,
                construction: bool = False) -> Ellipse:
        e = Ellipse(center, rx, ry, construction)
        self.ellipses.append(e)
        return e

    def constrain(self, *c: Constraint):
        self.constraints.extend(c)

    # ---- internals --------------------------------------------------------
    def _free_points(self) -> list[Point]:
        """Points are the only value-carrying free entities; circle and
        ellipse radii are extra scalars on the same vector."""
        seen: dict[int, Point] = {}
        for ln in self.lines:
            for p in (ln.a, ln.b):
                seen.setdefault(p.id, p)
        for c in self.circles:
            seen.setdefault(c.c.id, c.c)
        for e in self.ellipses:
            seen.setdefault(e.c.id, e.c)
        for a in self.arcs:
            for p in (a.a, a.m, a.b):
                seen.setdefault(p.id, p)
        for p in self.points:
            seen.setdefault(p.id, p)
        return list(seen.values())

    def _pack(self):
        pts = self._free_points()
        circles = self.circles
        ells = self.ellipses
        x = np.concatenate(
            [np.array([[p.x, p.y] for p in pts], dtype=float).ravel()]
            + ([np.array([c.r for c in circles], dtype=float)]
               if circles else [])
            + ([np.array([v for e in ells for v in (e.rx, e.ry)],
                         dtype=float)] if ells else []))
        return pts, circles, ells, x

    def _unpack(self, pts, circles, ells, x):
        for i, p in enumerate(pts):
            p.x, p.y = float(x[2 * i]), float(x[2 * i + 1])
        base = 2 * len(pts)
        for j, c in enumerate(circles):
            c.r = float(x[base + j])
        base += len(circles)
        for k, e in enumerate(ells):
            e.rx, e.ry = (float(x[base + 2 * k]),
                          float(x[base + 2 * k + 1]))

    def _residuals(self, constraints, x):
        self._unpack(*self._pack()[:3], x)
        return np.array([c.residual({}) for c in constraints], dtype=float)

    # ---- solving -----------------------------------------------------------
    def solve(self, tol: float = 1e-9, max_iter: int = 100) -> SolveResult:
        rows = []                                   # M87: tag each row
        for c in self.constraints:                  # with its origin so
            if getattr(c, "driven", False):         # M178 R1 (FD5-L35):
                continue                            #  a driven dim is a
            sub = expand([c])                       #  READER: no row, no
            for rw in sub:                          #  rule, no DOF bill -
                rw.origin = c                       #  diagnosis can name
                #                                    the user constraint
                #                                    behind it
            rows.extend(sub)
        pts, circles, ells, x0 = self._pack()
        x = x0.copy()
        n = x.size
        m = len(rows)
        if m == 0:
            res = SolveResult(True, 0.0, n, 0, rank=0, rows=[])
            for p in pts:                   # no constraints: every point
                res.point_dof[p.id] = 2     # floats free, two ways
                res.free_dirs[p.id] = (1.0, 0.0)
            for c in circles:               # M186: sizes float too -
                res.size_dof[c.id] = 1      #  the all-free answer must
            for e in ells:                  #  cover every variable
                res.size_dof[e.id] = 2
            return res

        def res(vec):
            self._unpack(pts, circles, ells, vec)
            return np.array([c.residual({}) for c in rows], float)

        lam = 1e-3  # Levenberg-Marquardt damping
        converged = False
        it = 0
        r = res(x)
        for it in range(1, max_iter + 1):
            # numerical Jacobian, central differences
            J = np.zeros((m, n))
            h = 1e-6 * max(1.0, float(np.max(np.abs(x))))
            for k in range(n):
                xp, xm = x.copy(), x.copy()
                xp[k] += h
                xm[k] -= h
                J[:, k] = (res(xp) - res(xm)) / (2 * h)
            rn = float(np.linalg.norm(r))
            if rn < tol:
                converged = True
                break
            # Marquardt damping in the SVD basis: step = -V diag(s/(s^2+λs̃^2)) Uᵀ r.
            # Near-null singular values (e.g. a symmetry direction whose
            # numerical Jacobian is pure roundoff, or any DOF left free by an
            # underdetermined sketch) contribute ~0 instead of the huge noise
            # amplification the coordinate-basis normal equations produce.
            U, S, Vt = np.linalg.svd(J, full_matrices=False)
            s2 = S * S
            lam_eff = lam * (s2.max() if s2.size else 1.0) + 1e-300
            step = -(Vt.T @ ((S / (s2 + lam_eff)) * (U.T @ r)))
            x_new = x + step
            r_new = res(x_new)
            if np.linalg.norm(r_new) < rn:
                x, r = x_new, r_new
                lam = max(lam * 0.3, 1e-9)
            else:
                lam = min(lam * 4.0, 1e6)
                if lam >= 1e5:  # stuck
                    break
        self._unpack(pts, circles, ells, x)
        rn = float(np.linalg.norm(res(x)))
        rank = int(np.linalg.matrix_rank(J, tol=1e-7)) if m else 0
        dof = max(n - rank, 0)
        failed = [rows[i] for i in range(m) if abs(r[i]) > 1e-6 * _TOL_SCALE]
        # ---- M87 diagnosis: name the culprits -------------------------------
        # Conflicting: rows whose residual refuses to close.  Redundant:
        # rows living in the span of their PREDECESSORS on the solved
        # Jacobian (Gram-Schmidt in constraint order — the later of two
        # duplicates carries the badge, FreeCAD-style).  A dependent row
        # that ALSO fails is conflicting, never redundantly so.
        bad = {i for i in range(m) if abs(r[i]) > 1e-6 * _TOL_SCALE}
        red = set()
        if m:
            basis = []
            for i in range(m):
                vec = J[i].astype(float, copy=True)
                for q in basis:
                    vec -= (vec @ q) * q
                nv = float(np.linalg.norm(vec))
                if nv > 1e-7:
                    basis.append(vec / nv)
                else:
                    red.add(i)
        red -= bad

        def _origins(idxs):
            seen, out = set(), []
            for i in sorted(idxs):
                o = getattr(rows[i], "origin", rows[i])
                if id(o) not in seen:
                    seen.add(id(o))
                    out.append(o)
            return out
        result = SolveResult(converged and rn < tol, rn, dof, it, failed,
                             redundant=_origins(red),
                             conflicting=_origins(bad))
        result.rank = rank                          # M164 R1: remembered
        result.final_J = J                          # state, ready for the
        result.final_r = r                          # drop-one scan (find_
        result.rows = rows                          # removable), no re-solve
        # ---- M119: WHERE the freedom lives, not just how much. The
        # Jacobian's null space holds every instantaneous motion the
        # constraints still allow; projecting it into each point's
        # 2 coords answers Inventor's "show all degrees of freedom"
        # — the view Fusion's users beg for and it never shipped
        # [fusion_kernel_architecture §3; forums 6803824/10057799].
        try:
            from scipy.linalg import null_space
            N = null_space(J, rcond=1e-7)           # n × (n-rank)
        except Exception:
            N = np.zeros((n, 0))
        for i, p in enumerate(pts):
            proj = N[[2 * i, 2 * i + 1], :]         # this point's slice
            if N.shape[1] == 0 or proj.size == 0:
                result.point_dof[p.id] = 0
                continue
            pr = int(np.linalg.matrix_rank(proj, tol=1e-9))
            result.point_dof[p.id] = min(pr, 2)
            if pr:
                ux = (proj @ proj.T)                # 2×2 energy tensor
                w, V = np.linalg.eigh(ux)
                d = V[:, -1]                        # richest free direction
                result.free_dirs[p.id] = (float(d[0]), float(d[1]))
        # M186 R1 [LAW-55]: the SAME null-space answer for the SIZE
        # variables. Column layout from _pack: 2*len(pts) point columns,
        # then one per circle radius, two per ellipse. An empty basis
        # (nothing moves) reports zero everywhere - the whole-sketch
        # truth and the per-entity truth can never disagree.
        p2 = 2 * len(pts)
        for j, c in enumerate(circles):
            sl = N[p2 + j:p2 + j + 1, :]
            result.size_dof[c.id] = 0 if sl.size == 0 else min(
                int(np.linalg.matrix_rank(sl, tol=1e-9)), 1)
        for k, e in enumerate(ells):
            base = p2 + len(circles) + 2 * k
            sl = N[base:base + 2, :]
            result.size_dof[e.id] = 0 if sl.size == 0 else min(
                int(np.linalg.matrix_rank(sl, tol=1e-9)), 2)
        return result


_TOL_SCALE = 100.0


# ---- M164 D1: the removable-constraint finder -------------------------------
# SolveSpace's shape (RefineMissing/identify at system.cpp): drop ONE user
# constraint's WHOLE row set, and the remainder is fixable iff it stands at
# FULL ROW RANK - pure rank algebra on the remembered J, never a re-solve.
# The flavor (redundant vs conflict) comes free from the M87 discriminator.
# Honest-scope law: the list NEVER claims minimality, is capped by candidate
# COUNT (max_scan) with the wall-clock (budget_ms) as backstop only, and a
# timed-out report says so.
_STRUCTURAL_SRC = frozenset({"rect", "slot", "poly", "fillet", "snap"})


def _eligible(c, live_ids):
    """Rank order: 0 = user, 1 = auto-inferred (offered LAST, SolveSpace's
    coincident-last law); None = never a candidate."""
    from .constraints import ArcMiddle, Coincident
    if id(c) not in live_ids:
        return None                     # drag-pin temp Fixed & the like
    if isinstance(c, (Coincident, ArcMiddle)):
        return None                     # welds / fillet witnesses are structural
    if any(getattr(e, "construction", False) for e in c.entities()):
        return None                     # polygon-ring R/oc ride the guide circle
    src = getattr(c, "src", "")
    if src in _STRUCTURAL_SRC:
        return None
    return 1 if src == "inferred" else 0


@dataclass
class Removability:
    kind: str = "clean"                 # redundant | conflict | clean
    removable: list = field(default_factory=list)   # ordered candidates
    unsatisfied: list = field(default_factory=list)  # blamed constraints
    dof: int = 0
    timed_out: bool = False


def find_removable(res, live_constraints, *, budget_ms=1000, max_scan=200):
    """Which ONE constraint, if deleted, leaves the rest of the system
    independent?  Answers from the remembered final state (res.rows/J/r);
    returns a fresh report that NEVER touches res.redundant/conflicting
    (contamination law) and mutates nothing (read-only gate)."""
    import time
    rows = list(getattr(res, "rows", []) or [])
    J = getattr(res, "final_J", None)
    live_ids = {id(c) for c in live_constraints}
    blamed = list(res.conflicting or res.redundant or [])
    kind = ("conflict" if res.conflicting else
            "redundant" if res.redundant else "clean")
    out = Removability(kind=kind, unsatisfied=blamed, dof=int(res.dof))
    if kind == "clean" or J is None or not rows:
        return out
    groups, order = {}, []
    for i, rw in enumerate(rows):
        o = getattr(rw, "origin", None)
        if o is None:
            continue
        k = id(o)
        if k not in groups:
            groups[k] = []
            order.append(o)
        groups[k].append(i)
    m = len(rows)
    cands = [(rank, n, o) for n, o in enumerate(order)
             if (rank := _eligible(o, live_ids)) is not None]
    cands.sort()                        # user first, inferred last;
    t0 = time.perf_counter()            # stable within class (min index)
    scanned = 0
    for _rank, _n, o in cands:
        if scanned >= max_scan or (time.perf_counter() - t0) * 1000 > budget_ms:
            out.timed_out = True
            break
        scanned += 1
        R = set(groups[id(o)])
        keep = [i for i in range(m) if i not in R]
        if not keep:
            continue
        if int(np.linalg.matrix_rank(J[keep], tol=1e-7)) == len(keep):
            out.removable.append(o)
    return out
