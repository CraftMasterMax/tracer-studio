"""M201 R13: the external Fluid Volume envelope.

[SLD fluid volume page, verbatim] "Fluid Volume creates a body that
envelopes or fills the interior of the selected tool bodies." The
EXTERNAL procedure names its shapes exactly: "Box", "Cylinder",
"Hemisphere"; "When applicable, choose the desired Shape Direction
from the associated drop-down list. This option is available when
the Shape Type is Cylinder or Hemisphere. The direction choices are
based on the three global axes: X-Axis Y-Axis Z-Axis"; "Optionally,
for hemispheric volumes, click Flip Direction to invert the
hemisphere."; and the one number: "Define the size of the fluid
volume in the Offset field. This value is the distance between the
outer faces of the tool bodies and the outer faces of the fluid
volume."

THE ENVELOPE ARITHMETIC IS OURS (the page draws the shapes, it
prints no formula - "default" counts ZERO on the page, so every
rest and every bound below is a HOUSE FACT, named as one):

* Box       - the axis-aligned bounding box of every tool vertex,
              grown by Offset on all six sides (offset is "the
              distance between the outer faces ... and the outer
              faces" - a face-to-face gap, symmetric by the very
              sentence).
* Cylinder  - around the axis PARALLEL to the chosen global axis
              through the bounding-box CENTER; radius = the farthest
              tool vertex's distance from that axis, plus Offset;
              length = the axial span plus two Offsets (the same
              face-to-face law closes both ends).
* Hemisphere- the half of a ball split by a plane through a point on
              the chosen axis at the tools' LOW axial extreme grown
              by Offset; centre over the bounding-box centre of the
              cross-section; radius = the farthest vertex's true
              distance from that point, plus Offset - so the tools
              sit INSIDE the dome (a flat face through the bbox
              centre would cut them in half: the envelope must
              ENVELOPE). The dome points along +axis; Flip Direction
              ("to invert the hemisphere") sends it along -axis.

The fluid is the ENVELOPE MINUS THE TOOLS (it is the body the flow
would travel around). The Split Result row is deliberately NOT
implemented: it is a tangent-EDGE story, and this kernel subtracts
meshes - promising an edge behaviour it cannot deliver would be the
old lie, so the door does not speak it (absence is honesty, R4's
law). INTERNAL is refused by name at the door, quoting the page's
own precondition: "You will not be permitted to complete the fluid
body creation until the program detects a completely isolated
interior volume" - and capping needs surface bodies this kernel
does not have, so the only Volume word here is External.
"""

import numpy as np

from .geometry import Solid, rotation_about

SHAPES = ("Box", "Cylinder", "Hemisphere")          # page order
DIRECTIONS = ("X-Axis", "Y-Axis", "Z-Axis")         # page words


def _all_verts(solid_list):
    vs = [s.to_trimesh().vertices for s in solid_list]
    return np.vstack([v for v in vs if len(v)])


def envelope_solid(solid_list, shape, direction, flip, offset):
    """The envelope solid for the named tool streams. Raises only on
    words the door never sends (the eval guard is the real fold's
    own mouth, R12's coin); math itself never fails on a real mesh."""
    if shape not in SHAPES:
        raise ValueError(f"the shape type is 'Box', 'Cylinder' or "
                         f"'Hemisphere', not {shape!r}")
    if direction not in DIRECTIONS:
        raise ValueError("the shape direction is 'X-Axis', 'Y-Axis' "
                         f"or 'Z-Axis', not {direction!r}")
    o = float(offset)
    if o < 0.0:
        raise ValueError("the offset is the distance between outer "
                         "faces - it cannot be negative")
    v = _all_verts(solid_list)
    lo, hi = v.min(axis=0), v.max(axis=0)
    c = (lo + hi) / 2.0
    ax = DIRECTIONS.index(direction)                 # 0=X 1=Y 2=Z

    if shape == "Box":
        d = hi - lo + 2.0 * o
        return Solid.box(d[0], d[1], d[2]).translated(lo - o)

    # radial frame about the chosen global axis through the center
    t = (v - c) @ np.eye(3)[ax]                      # axial coord
    perp = v - c - np.outer(t, np.eye(3)[ax])
    r = np.linalg.norm(perp, axis=1)

    if shape == "Cylinder":
        radius = float(r.max()) + o
        height = float(t.max() - t.min()) + 2.0 * o
        env = Solid.cylinder(radius, height)         # +Z, base at 0
        if ax == 0:                                  # Z -> X: +90 about Y
            env = env.transformed(
                rotation_about((0.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                               np.pi / 2.0))
        elif ax == 1:                                # Z -> Y: -90 about X
            env = env.transformed(
                rotation_about((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                               -np.pi / 2.0))
        base = c + (float(t.min()) - o) * np.eye(3)[ax]
        return env.translated(base)

    # Hemisphere: the flat face sits at the tools' LOW axial extreme
    # grown by the offset, the dome covers them - an envelope that
    # cut the tools in half would not envelope anything.
    q = c.copy()
    q[ax] = float(lo[ax]) - o
    radius = float(np.linalg.norm(v - q, axis=1).max()) + o
    if flip:                                         # dome to -axis
        q = c.copy()
        q[ax] = float(hi[ax]) + o
        radius = float(np.linalg.norm(v - q, axis=1).max()) + o
    env = Solid.sphere(radius).translated(q)
    L = 10.0 * radius                                # the half-space box
    origin = q - (L / 2.0) * (np.ones(3) - np.eye(3)[ax])
    origin = origin.copy()
    if not flip:
        origin[ax] = q[ax]                           # keep t >= q[ax]
    else:
        origin[ax] = q[ax] - L                       # keep t <= q[ax]
    half = Solid.box(L, L, L).translated(origin)
    return env.intersect(half)
