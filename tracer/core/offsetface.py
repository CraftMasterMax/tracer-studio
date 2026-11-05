"""M198: the Offset Face tool's kernel.

[SLD-OFFSET-FACES, verbatim] "Learn how to use the Offset Face tool to
shift faces on a solid body" - "Select a single face or multiple faces
and specify the Offset distance" and the note that makes the tool more
than a resize: "Adjoining curved tangent faces will offset when
geometrically possible."  Rung one cuts the SINGLE-face sentence on
the straight-walled family rung one of Draft earned (the same _shape
mouth - one detector, two tools): a cylinder on its axis or an
axis-aligned box.  A rod's top cap going up takes its wall with it
(the note falls out of the rebuild: a taller library cylinder); its
wall going out takes both caps with it (a wider one).  A box moves
the named face, and the four rectangles the walls trace simply grow
or shrink - exact, this mesh is hand-built at float64.

The faces are spoken PLAINLY (the Draft law kept): a straight-walled
body's faces are "bottom", "top", and either "wall" (the cylinder's
one curved face) or "+x" "-x" "+y" "-y" (the box's four flat ones).
A name the body does not own is refused WITH ITS CURE - the body's
real face names ride in the words.

Multiple faces, the manipulator (the page's "Drag the manipulator or
enter an exact value" - exact value is all this door speaks) and any
body with curved adjoining geometry beyond the cylinder's wall are
later rungs' honest business: a door may not promise what cannot
bake (the M196 law, kept).

SIGN LAW: a POSITIVE distance moves the face OUTWARD, along ITS own
outward normal - material grows; a negative one shrinks it.  This is
the page's "in a positive or negative direction" with the direction
made checkable: every face's outward normal is the way AWAY from the
body's inside.
"""
import math

import numpy as np

from .geometry import Solid
from .draft import _shape, _Z_TOL, _SHAPE_TOL

_FACES_CYL = ("bottom", "top", "wall")
_FACES_BOX = ("bottom", "top", "+x", "-x", "+y", "-y")


def _fail(body_kind: str) -> ValueError:
    return ValueError("offset needs straight vertical walls - a "
                      "cylinder on its axis or a box standing on "
                      "the fixed plane")


def offset_face(solid: Solid, face: str, dist: float):
    """Shift ONE named face of a straight-walled body outward by dist
    millimetres (negative shrinks); adjoining faces follow, exactly
    as the page's note promises.  Returns a solid; raises rather than
    lying about a face the body does not own, a body that has no
    faces it dares touch, or an offset that squeezes the body out of
    existence."""
    shp = _shape(solid)
    if shp is None:
        raise _fail("")
    d = float(dist)
    z0, z1 = shp[-2], shp[-1]
    if shp[0] == "cylinder":
        _, cx, cy, r, z0, z1 = shp
        if face not in _FACES_CYL:
            raise ValueError(f"this cylinder's faces are "
                             f"{', '.join(map(repr, _FACES_CYL))} - "
                             f"not {face!r}")
        if face == "wall":
            r2 = r + d
            if r2 <= _SHAPE_TOL:
                raise ValueError("the offset would collapse the body: "
                                 "the wall must still leave material")
            h = z1 - z0
        else:
            r2 = r
            # POSITIVE moves the face OUTWARD along ITS OWN normal:
            # the top cap's normal is +z (z1 grows), the bottom's is
            # -z (z0 falls) - BOTH grow the height by d.  (The first
            # probe caught this: a signed -(d) here shrank the rod
            # UP from the top while still moving the bottom - zmax
            # 30 on a +5 bottom offset was the tell.)
            h = (z1 - z0) + d
            new_z0 = z0 if face == "top" else z0 - d
            if h <= _Z_TOL:
                raise ValueError("the offset would collapse the body: "
                                 "the caps must still leave material")
            z0 = new_z0
        import manifold3d as m3
        m = m3.Manifold.cylinder(h, r2, r2).translate(
            np.array([cx, cy, z0], np.float32))
        return Solid(m)
    _, x0, x1, y0, y1, z0, z1 = shp
    if face not in _FACES_BOX:
        raise ValueError(f"this box's faces are "
                         f"{', '.join(map(repr, _FACES_BOX))} - "
                         f"not {face!r}")
    if face == "top":
        z1 += d
    elif face == "bottom":
        z0 -= d
    elif face == "+x":
        x1 += d
    elif face == "-x":
        x0 -= d
    elif face == "+y":
        y1 += d
    else:
        y0 -= d
    if min(x1 - x0, y1 - y0, z1 - z0) <= _Z_TOL:
        raise ValueError("the offset would collapse the body: the "
                         "faces must still leave material")
    V = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    F = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
         (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
         (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return Solid.from_mesh(np.asarray(V, float), np.asarray(F, np.int32))
