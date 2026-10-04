"""Newton/LM hybrid solver for 2D geometric constraints.

Numerical Jacobians on purpose: sketches here are < ~200 params, and
correct-but-simple beats clever-but-buggy for v0. Dense lstsq handles
rank-deficient (under-constrained) systems by taking the minimum-norm
correction instead of exploding.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .entities import Entity, Point, Line, Circle
from .constraints import Constraint, expand


@dataclass
class SolveResult:
    converged: bool
    residual_norm: float
    dof: int
    iterations: int
    failed: list = field(default_factory=list)

    def __bool__(self): return self.converged


class Sketch:
    def __init__(self):
        self.points: list[Point] = []
        self.lines: list[Line] = []
        self.circles: list[Circle] = []
        self.arcs: list["Arc"] = []
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

    def constrain(self, *c: Constraint):
        self.constraints.extend(c)

    # ---- internals --------------------------------------------------------
    def _free_points(self) -> list[Point]:
        """Points are the only value-carrying free entities; circle radius is extra."""
        seen: dict[int, Point] = {}
        for ln in self.lines:
            for p in (ln.a, ln.b):
                seen.setdefault(p.id, p)
        for c in self.circles:
            seen.setdefault(c.c.id, c.c)
        for a in self.arcs:
            for p in (a.a, a.m, a.b):
                seen.setdefault(p.id, p)
        for p in self.points:
            seen.setdefault(p.id, p)
        return list(seen.values())

    def _pack(self):
        pts = self._free_points()
        circles = self.circles
        x = np.concatenate(
            [np.array([[p.x, p.y] for p in pts], dtype=float).ravel()]
            + ([np.array([c.r for c in circles], dtype=float)] if circles else []))
        return pts, circles, x

    def _unpack(self, pts, circles, x):
        for i, p in enumerate(pts):
            p.x, p.y = float(x[2 * i]), float(x[2 * i + 1])
        base = 2 * len(pts)
        for j, c in enumerate(circles):
            c.r = float(x[base + j])

    def _residuals(self, constraints, x):
        self._unpack(*self._pack()[:2], x)
        return np.array([c.residual({}) for c in constraints], dtype=float)

    # ---- solving -----------------------------------------------------------
    def solve(self, tol: float = 1e-9, max_iter: int = 100) -> SolveResult:
        rows = expand(self.constraints)
        pts, circles, x0 = self._pack()
        x = x0.copy()
        n = x.size
        m = len(rows)
        if m == 0:
            return SolveResult(True, 0.0, n, 0)

        def res(vec):
            self._unpack(pts, circles, vec)
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
        self._unpack(pts, circles, x)
        rn = float(np.linalg.norm(res(x)))
        rank = int(np.linalg.matrix_rank(J, tol=1e-7)) if m else 0
        dof = max(n - rank, 0)
        failed = [rows[i] for i in range(m) if abs(r[i]) > 1e-6 * _TOL_SCALE]
        return SolveResult(converged and rn < tol, rn, dof, it, failed)


_TOL_SCALE = 100.0
