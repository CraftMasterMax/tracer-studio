"""M197: the Draft tool's kernel.

[SLD-REF-DRAFT, verbatim] "The Draft tool applies a fixed plane or
parting line draft angle to rotate planar faces on a solid body."
Rung one cuts the page's FIXED PLANE type on the bodies whose walls
are straight and vertical: a cylinder on its axis or an axis-aligned
box standing on the plane.  Every wall ROTATES about the line where
it meets the fixed plane, so the walls lean by the angle and the free
end grows - or shrinks - by height x tan(angle).  A cylinder's forty
-odd tessellated facets each rotate about their own bottom edge line,
and those rotations compose exactly into a cone: the honest build is
the library's own cone (its walls are true lean planes, its ring
vertices land exactly on the radius).  A drafted box is a
PRISMATOID, not a similar frustum when the walls tilt independently:
its exact volume is Simpson's h/6 (A0 + 4Am + A1), not the cone-like
h/3 (A0 + A1 + sqrt(A0 A1)) - the formula is the check, so it must be
the right one.

The page's other mouths - Parting Line, Angle Mode Relative/Absolute,
the face list, Tangent Chain, Draft Sides - wait for rungs whose
kernel actually cuts them: a door may not promise what cannot bake
(the M196 law, kept).

SIGN LAW rides the house taper ("+ widens as it goes"): a POSITIVE
angle widens AWAY from the fixed plane; the fixed plane's own ring or
rectangle keeps its exact size - that is what "fixed" means.
"""
import math

import numpy as np

from .geometry import Solid

_Z_TOL = 1e-6           # "same z level": meshes land on exact planes
_SHAPE_TOL = 1e-4       # scale-relative slack for float32 tessellation


def _shape(solid: Solid):
    """Detect a straight-walled body standing on the XY plane: exactly
    two z levels, and either one equal-radius ring on both levels (a
    cylinder on its axis) or the four corners of one axis-aligned
    rectangle on both levels (a box).  Returns ("cylinder", cx, cy, r,
    z0, z1), ("box", x0, x1, y0, y1, z0, z1), or None."""
    v = solid.to_trimesh().vertices
    zs = np.unique(np.round(v[:, 2], 6))
    if len(zs) != 2:
        return None
    z0, z1 = float(zs[0]), float(zs[1])
    lo = np.abs(v[:, 2] - z0) < _Z_TOL
    hi = np.abs(v[:, 2] - z1) < _Z_TOL
    # The axis is the body's own: the centre of each level's vertex
    # cloud.  Measuring rho about the ORIGIN would refuse a cylinder
    # that stands off-centre - the fixed plane cares where the WALLS
    # are, not where the world began.
    c_lo = v[lo][:, :2].mean(axis=0)
    c_hi = v[hi][:, :2].mean(axis=0)
    d = np.hypot(v[:, 0] - c_lo[0], v[:, 1] - c_lo[1])
    u = np.hypot(v[:, 0] - c_hi[0], v[:, 1] - c_hi[1])
    rho = np.where(lo, d, u)           # each vertex: distance to ITS level
    scale = max(1.0, float(rho.max()))
    tol = _SHAPE_TOL * scale

    def rect(mask):
        p = v[mask]
        x0, x1 = float(p[:, 0].min()), float(p[:, 0].max())
        y0, y1 = float(p[:, 1].min()), float(p[:, 1].max())
        if x1 - x0 <= tol or y1 - y0 <= tol:
            return None
        dx = np.minimum(np.abs(p[:, 0] - x0), np.abs(p[:, 0] - x1))
        dy = np.minimum(np.abs(p[:, 1] - y0), np.abs(p[:, 1] - y1))
        if dx.max() > tol or dy.max() > tol:
            return None
        return (x0, x1, y0, y1)

    # Box FIRST: the four corners of a rectangle sit at ONE distance
    # from their level's centre too - ask ring-vs-rectangle in the
    # other order and every box reports as a cylinder (the probe
    # caught this: a 20x10x5 drafted as a cone of circumradius).
    r_lo, r_hi = rect(lo), rect(hi)
    if (r_lo is not None and r_hi is not None
            and max(abs(a - b) for a, b in zip(r_lo, r_hi)) < tol):
        return ("box", *r_lo, z0, z1)
    a = np.arctan2(v[:, 1] - c_lo[1], v[:, 0] - c_lo[0])
    n_ang = len(np.unique(np.round(a[lo], 4)))
    if (abs(c_lo[0] - c_hi[0]) < tol and abs(c_lo[1] - c_hi[1]) < tol
            and rho[lo].min() > tol
            and abs(rho[lo].max() - rho[lo].min()) < tol
            and abs(rho[hi].max() - rho[hi].min()) < tol
            and abs(rho[lo].max() - rho[hi].max()) < tol
            and n_ang >= 128):
        # A RING, not a polygon masquerading as one: fewer angles and
        # the cone build would lie about the facet count, so prisms
        # stay where they are - refused as honest "not straight
        # walls" rather than rebuilt as round lies.
        return ("cylinder", float(c_lo[0]), float(c_lo[1]),
                float((rho[lo].max() + rho[hi].max()) / 2.0), z0, z1)
    return None


def _facets(solid: Solid, z_level: float) -> int:
    """How many wall facets the ring at one level really has: unique
    angles of its vertices (the truth the status line may count on)."""
    v = solid.to_trimesh().vertices
    p = v[np.abs(v[:, 2] - z_level) < _Z_TOL]
    a = np.arctan2(p[:, 1], p[:, 0])
    return int(len(np.unique(np.round(a, 4))))


def draft_solid(solid: Solid, angle_deg: float, fixed: str = "bottom"):
    """Lean every straight vertical wall about its line on the fixed
    plane; returns (solid, n_walls).  Raises rather than lying: a body
    that is not a cylinder or a box does not have "the walls" yet, and
    a lean that squeezes a wall through the axis is no draft at all."""
    if fixed not in ("bottom", "top"):
        raise ValueError(f"the fixed plane is the body's bottom or top, "
                         f"not {fixed!r}")
    shp = _shape(solid)
    if shp is None:
        raise ValueError("draft needs straight vertical walls - a "
                         "cylinder on its axis or a box standing on "
                         "the fixed plane")
    s = (shp[-1] - shp[-2]) * math.tan(math.radians(float(angle_deg)))
    if shp[0] == "cylinder":
        _, cx, cy, r, z0, z1 = shp
        r_bot, r_top = (r, r + s) if fixed == "bottom" else (r + s, r)
        if min(r_bot, r_top) <= _SHAPE_TOL:
            raise ValueError("the draft would collapse the wall: the "
                             "lean must still reach the fixed plane")
        import manifold3d as m3
        m = m3.Manifold.cylinder(z1 - z0, r_bot, r_top)
        m = m.translate(np.array([cx, cy, z0], np.float32))
        return Solid(m), _facets(solid, z0)
    _, x0, x1, y0, y1, z0, z1 = shp
    held = (x0, x1, y0, y1)
    moved = (x0 - s, x1 + s, y0 - s, y1 + s)
    if min(moved[1] - moved[0], moved[3] - moved[2]) <= 2 * _SHAPE_TOL:
        raise ValueError("the draft would collapse the wall: the "
                         "lean must still reach the fixed plane")
    bot, top = (held, moved) if fixed == "bottom" else (moved, held)
    V = []
    for cx0, cx1, cy0, cy1, z in ((bot[0], bot[1], bot[2], bot[3], z0),
                                  (top[0], top[1], top[2], top[3], z1)):
        V += [(cx0, cy0, z), (cx1, cy0, z), (cx1, cy1, z), (cx0, cy1, z)]
    F = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),            # caps
         (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),            # walls
         (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return Solid.from_mesh(np.asarray(V, float),
                           np.asarray(F, np.int32)), 4


def draft_parting(solid: Solid, angle_deg: float, parting_z: float,
                  angle2: float | None = None):
    """M197 R3 [SLD-REF-DRAFT, verbatim]: Parting Line type -
    "Select a parting tool to define a line to draft from", and the
    tool here is spoken PLAINLY (the same plain-speech rung two gave
    the fixed plane): a horizontal plane at parting_z millimetres
    above the body's own bottom.  Fix Parting Line: the ring (or
    rectangle) AT the parting line keeps its EXACT size - that is
    what "fix" means - and each wall rotates about its line there, so
    BOTH free ends move away from the parting by their own distance x
    tan(angle).
    Rung five cuts the page's TWO SIDE, verbatim: "Create a draft on
    both sides of the parting line. Specify a different angle for
    each side" - the two settings the note labels ANGLE 1 and ANGLE
    2.  THE HOUSE MAPPING (the page names no sides until the Faces
    pick, an unpromised mouth): ANGLE 1 = angle_deg leans the side
    BELOW the parting line, ANGLE 2 = angle2 the side ABOVE; each
    sign keeps the same law - positive widens AWAY from the parting.
    angle2=None is rung three's ONE ANGLE both sides, the page's
    SYMMETRIC - measured BIT-IDENTICAL to the single-angle build.
    Move Parting Line and Fixed Edges stay later rungs' business.
    Same refuse-rather-lie laws as the fixed plane; the parting line
    that coincides with an end is that end's FIXED PLANE case and
    says so.  Returns (solid, n_walls)."""
    shp = _shape(solid)
    if shp is None:
        raise ValueError("draft needs straight vertical walls - a "
                         "cylinder on its axis or a box standing on "
                         "the fixed plane")
    z0, z1 = shp[-2], shp[-1]
    height = z1 - z0
    p = float(parting_z)
    if not 0.0 < p < height - _Z_TOL:
        raise ValueError("the parting line must stand between the "
                         "body's bottom and top - at an end it is "
                         "the fixed plane instead")
    t1 = math.tan(math.radians(float(angle_deg)))
    t2 = t1 if angle2 is None else math.tan(math.radians(float(angle2)))
    d_lo, d_hi = p, height - p                  # the ends' own distances
    if shp[0] == "cylinder":
        _, cx, cy, r, z0, z1 = shp
        r_bot, r_top = r + d_lo * t1, r + d_hi * t2
        if min(r_bot, r_top) <= _SHAPE_TOL:
            raise ValueError("the draft would collapse the wall: the "
                             "lean must still reach the parting line")
        import manifold3d as m3

        def seg(h, r_lo, r_hi, z):
            return m3.Manifold.cylinder(h, r_lo, r_hi).translate(
                np.array([cx, cy, z], np.float32))
        m = seg(d_lo, r_bot, r, z0) + seg(d_hi, r, r_top, z0 + d_lo)
        return Solid(m), _facets(solid, z0)
    _, x0, x1, y0, y1, z0, z1 = shp
    s_lo, s_hi = d_lo * t1, d_hi * t2
    bot = (x0 - s_lo, x1 + s_lo, y0 - s_lo, y1 + s_lo)
    mid = (x0, x1, y0, y1)
    top = (x0 - s_hi, x1 + s_hi, y0 - s_hi, y1 + s_hi)
    for e in (bot, top):
        if e[1] - e[0] <= 2 * _SHAPE_TOL or e[3] - e[2] <= 2 * _SHAPE_TOL:
            raise ValueError("the draft would collapse the wall: the "
                             "lean must still reach the parting line")
    V = []
    for (ex0, ex1, ey0, ey1), z in ((bot, z0), (mid, z0 + d_lo),
                                    (top, z1)):
        V += [(ex0, ey0, z), (ex1, ey0, z), (ex1, ey1, z), (ex0, ey1, z)]
    F = [(0, 2, 1), (0, 3, 2), (8, 9, 10), (8, 10, 11),          # caps
         (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),             # lower walls
         (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
         (4, 5, 9), (4, 9, 8), (5, 6, 10), (5, 10, 9),           # upper walls
         (6, 7, 11), (6, 11, 10), (7, 4, 8), (7, 8, 11)]
    return Solid.from_mesh(np.asarray(V, float),
                           np.asarray(F, np.int32)), 4
