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
    free_dirs: dict = field(default_factory=dict)  # M119: point.id -> (dx,dy)

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
            sub = expand([c])                       # diagnosis can name
            for rw in sub:                          # the user constraint
                rw.origin = c                       # behind it
            rows.extend(sub)
        pts, circles, ells, x0 = self._pack()
        x = x0.copy()
        n = x.size
        m = len(rows)
        if m == 0:
            res = SolveResult(True, 0.0, n, 0)
            for p in pts:                   # no constraints: every point
                res.point_dof[p.id] = 2     # floats free, two ways
                res.free_dirs[p.id] = (1.0, 0.0)
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
        return result


_TOL_SCALE = 100.0
