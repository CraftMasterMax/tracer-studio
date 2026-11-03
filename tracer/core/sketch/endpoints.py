"""M191 R1 [endpoint truth] — which sketch points are WELDED.

The vendor law, verbatim (help.autodesk.com Fusion-Sketch
GUID-685B9D79, "Distinguish coincident constraints"): "When end
points of lines or splines are not constrained to other geometry,
they are displayed as white dots"; "Point to point coincident
constraints show no dot"; and the repair verb, in the same page:
"To remove a coincident constraint, select the point then right-click
and select Delete Coincident."

Our kernel speaks coincidence in TWO dialects, and the law must
answer BOTH with ONE mouth (paint == menu == act, the standing
doctrine):
  (1) IDENTITY - a snap reuses the existing Point object
      (_place_point: "identity IS coincidence"), so a shared Point
      is welded by having TWO OR MORE SEGMENT ROLES; and
  (2) RECORDS - an autolink or a typed constraint files a
      Coincident / PointOnLine / PointOnCircle / Midpoint against
      the Point.
A point welded by EITHER dialect hides its dot. The verb frees the
point from ONE weld (the record path deletes the record; the
identity path splits one role off the shared object).
"""
from __future__ import annotations

from .constraints import (Coincident, Midpoint, PointOnLine,
                          PointOnCircle)
from .entities import Point

# M191 R4: the vendor's OWN name is the law here - their shortcut page
# calls the midpoint weld "Sketch Coincident Constraint at Midpoint"
# (GUID-F0491540). A Midpoint record pins the point to be coincident
# WITH the line's middle: paper coincidence, so it hides the dot, and
# "Delete Coincident" is its repair verb (uncouple_first drops records
# generically - no new code needed).
RECORDS = (Coincident, PointOnLine, PointOnCircle, Midpoint)


def point_roles(sketch) -> dict:
    """Point.id -> list of (entity, attr) ROLES the geometry plays.
    Segment endpoints only (line.a/.b, arc.a/.m/.b): the law's whole
    subject is "end points of lines"; standalone points and centres
    carry no dot in either direction."""
    roles: dict = {}

    def put(p, ent, attr):
        roles.setdefault(id(p), []).append((ent, attr))

    for l in sketch.lines:
        put(l.a, l, "a")
        put(l.b, l, "b")
    for a in sketch.arcs:
        put(a.a, a, "a")
        put(a.m, a, "m")
        put(a.b, a, "b")
    return roles


def coincident_record(sketch, pt):
    """The FIRST coincidence RECORD that attaches pt to something
    (identity welds leave no paper; paper welds are this). Reads the
    dataclass entities() - the ONE vocabulary every constraint knows -
    so no field-name assumption is ever made."""
    for c in sketch.constraints:
        if isinstance(c, RECORDS) and any(e is pt for e in c.entities()):
            return c
    return None


def is_welded(sketch, pt) -> bool:
    """Dialect (1) OR (2): shared by 2+ roles, or a record binds it."""
    roles = point_roles(sketch).get(id(pt), [])
    if len(roles) >= 2:
        return True
    return coincident_record(sketch, pt) is not None


def uncouple_first(sketch, pt) -> bool:
    """'Delete Coincident', ONE weld at a time - the point's own verb.
    Paper first (a record names its pair, deletion is honest surgery);
    then identity: the point keeps its FIRST role and every LATER role
    gets a fresh copy at the same coordinates, so the corner opens and
    THIS point (the one the user picked, riding role 1) swings free.
    A standalone Point keeps no dot and needs no verb. Returns True
    iff a weld actually fell (the caller only snapshots on a hit)."""
    c = coincident_record(sketch, pt)
    if c is not None:
        sketch.constraints.remove(c)
        return True
    roles = point_roles(sketch).get(id(pt), [])
    if len(roles) < 2:
        return False
    for ent, attr in roles[1:]:
        clone = Point(pt.x, pt.y)
        if attr == "a":
            ent.a = clone
        elif attr == "b":
            ent.b = clone
        else:
            ent.m = clone
    return True
