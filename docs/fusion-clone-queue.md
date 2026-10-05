# Fusion clone queue (research-driven)

Source notes (Oct 2026): Autodesk's own help pages block automated
fetching, so this inventory comes from the search-visible UI summaries
(tab-organised toolbar, data panel/browser, bottom timeline, viewport with
ViewCube) plus direct working knowledge of the Design workspace.  The
standing rule applies to everything here: clone the **workflow,
interaction grammar and visual language** — never Autodesk's identity
(no logos, no copied assets; glyphs stay QPainter-drawn generic geometry).

## Feature parity map (what Tracer already has)

| Fusion (Design › Solid)        | Tracer status                                   |
|--------------------------------|-------------------------------------------------|
| Extrude / Revolve              | ✓ (+ join/cut/intersect, corner fillet/chamfer) |
| Sweep                          | ✓ M35 (circular profile, lines+arcs path)       |
| Loft                           | ✓ M36 (two sketches, any planes)                |
| Hole                           | ✓ M31 (simple/counterbore/countersink, assoc.)  |
| Shell                          | ✓ M32 (face pick, thickness, pre-validation)    |
| Fillet / Chamfer (body)        | ✓ M18/M23 rim-based                             |
| Rectangular / Circular Pattern | ✓ M25/M26                                       |
| Mirror                         | ✓ M27                                           |
| Press/Pull (direct edit)       | ✓ M24                                           |
| Inspect › Measure              | ✓ M33 (area, angle/gap, volume, surface)        |
| Sketch: 7 tools + 14 constraints | ✓ M5..M17 (trim, corner ops, on-curve, polygon)|
| Offset Entities                | ✓ M34 (mitred parallel copy, inward/outward)    |
| Timeline + browser             | ✓ M9/M11 (+ glyphs, suppress, reorder-safe)     |
| STEP / STL / 3MF / OBJ / PLY   | ✓ (STEP + fillets via OCCT bridge, degrades)    |

## Gap queue — build in this order, one per milestone, test-gated

**✓ M37 — Navigation & selection grammar.**  Shipped: MMB pans,
Shift+MMB/RMB orbit, wheel zooms toward the cursor, left-drag rubber
band (L→R window / R→L crossing), Fusion-orange selection.

**✓ M38 — Viewport visual identity.**  Shipped: RGB axis triad docked
bottom-left (far axis dimmed), readable dock widths, crisp glyphs.

**✓ M39 — Fusion ribbon GUI (user request: "same gui as Fusion").**
Shipped: quick-access strip, Design/Sketch workspace tabs, grouped icon
panels, 18 new glyphs.  Ribbon removed from the deferred list below.

**✓ M40 — Construct ▸ Plane (offset).**  Shipped: origin-plane offsets
as document data + ▭ browser nodes + sketch-on-plane + viewport quads.
The angled-plane variant (rotate about an in-plane axis) is still open —
fold it into a later milestone when a workflow needs it.

**M41 — Constraint set to Fusion core.**  Add Equal, Midpoint,
Symmetry (about sketch axis or line) to the LM solver, constraint
palette icons + shortcuts; auto-constrain on draw matches Fusion
(H/V snap already present).

**M42 — Thread.**  Fusion's most-used maker feature after holes.
v1: cosmetic-style real geometry — helical ridge cut (loft engine along
a helix: rings on a rising circle path), or hole option "tapped Ø" with
ISO pitch table.  Test: helix ring count, min wall, export watertight.

**M43 — Pattern on path.**  Third pattern Fusion offers; reuses the
M35 path chain: place N instances of a body/feature along a sketch
path via frame-transform copies (loft kernel already builds the frames).

**M44 — Section Analysis.**  Clip-plane toggle in the viewport (discard
in fragment shader beyond the plane), plane = chosen face or origin
plane (construction planes from M40 are natural candidates), flips side;
purely visual, non-destructive — makers live in it.

**M45 — Sketch origin identity.**  Origin point + axis lines visible in
every sketch (RGB like triad), origin snap, rectangle-from-origin
corner behaviour, "Project" origin geometry so constraints can reference
it.

**M46 — Split Body (plane trim).**  Multi-body is out of v1 scope, but
Fusion's most common split is "cut away one half": Split › plane ›
discard side, kept as a parametric subtract feature.

**Later candidates (researched, deferred):** Patch/Thicken
(surface kernel gap), Draft, Combine/multi-browser-bodies, configurations,
Appearances (per-body colour), sheet metal, drawings.  Re-evaluate after
M45.

## Testing doctrine (unchanged)

Every milestone: kernel unit tests with analytic ground truth (volumes,
watertightness, genus) + UI tests driving real widgets headless + a
screenshot proof in /tmp/opencode/shots + README/status bump + commit —
then straight to the next.  No permission asks; stop only if the user
redirects.
