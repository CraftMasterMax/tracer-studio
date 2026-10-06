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
| Construction › Plane (offset)  | ✓ M40 (sketch-on-plane, browser + viewport quad)|
| Sketch: 7 tools + 16 constraints | ✓ M5..M17, M41 (midpoint, collinear, polygon)|
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

**✓ M41 — Constraint set to Fusion core.**  Audit found Equal (Q) and
Symmetry (M) already shipped; the true gaps Midpoint (J) and Collinear
(L-with-selection) now live in the LM solver, badges + menus included.

**✓ M42 — Ribbon anatomy.**  User redirect: *"I dont want 15% of
Fusion, make a 1:1 clone if possible"* — queue re-prioritised to
GUI/interaction parity first.  Shipped: "Design ▾" workspace chip,
centred document-title chip (live name + dirty •), Solid-tab group
order (Sketch · Create · Pattern · Modify · Construct) with Pattern
operations as three real buttons.

**M43 — Browser anatomy.**  Fusion tree: `Origin` (Origin point +
X/Y/Z axes + three planes), `Bodies (1) ▸ Body 1 ▸ features+sketches
nested`, `Sketches (n)`, `Construction (n)` — construction planes move
from Origin to Construction; body visibility (bulb) toggle.

**✓ M44 — Blender-style viewport shading (user request: "make the
shading like the one blenders editor mode uses").**  Shipped:
viewport-fixed studio lights (the model reads the same from every orbit
angle), neutral grey body with ground bounce and soft gloss, graphite
gradient that settles darker under the model.

**✓ M44b — Viewport furniture.**  Shipped: Fusion's mini nav stack
under the ViewCube — Home / Zoom In / Zoom Out — with hover highlight,
pointing-hand cursor and working actions (geometry in viewcube.py,
behaviour in the viewport, same split as the cube). In-scene origin
arrows and contact shadows remain open ideas.

**✓ M45 — Sketch ribbon flyouts.**  Shipped: Sketch tab gained a
Dimension button and the Constrain flyout — a two-column grid panel of
all twelve geometric ties with their keys, dispatching late-bound into
the sketcher's act_* methods (Draw ▸ Modify ▸ Dimension ▸ Constrain ▸
Finish, Fusion's ordering).

**✓ M46 — App menu.**  Shipped: launcher mark at the ribbon's far-left
corner opens the primary file surface (New/Open/Save/Save As · Import ·
Export ▸ all formats · Keyboard shortcuts · Exit) — the exact menu-bar
QActions shared, so shortcuts and behaviour can never drift apart.

**✓ M47 — Command dialogs.**  One Fusion-style dialog shell (header
strip, grouped fields, OK/Cancel, Remember Values) replacing scattered
QInputDialogs.  Shipped: the multi-prompt offenders — Circular/Linear
Pattern (five chained prompts → one grouped dialog), Mirror (feature +
plane + offset together; the feature-menu flow asks only the offset it
doesn't know), Construction Plane (base + distance).

**✓ M47b — Dialog sweep finished.**  Shell (drop-in QInputDialog
signature mirror, Fusion chrome + per-prompt Remember Values) now
serves every remaining single-field prompt: extrude distance, press-
pull, revolve angle, rename, shell thickness, fillet/chamfer sizes,
sketcher dimension/offset/angle prompts.  Zero QInputDialog references
left in the app; 18 prompt sites + 39 test patches moved mechanically.

**M48 — Section Analysis.**  Clip-plane toggle in the viewport (discard
in fragment shader beyond the plane), plane = chosen face or origin
plane (construction planes from M40 are natural candidates), flips side;
purely visual, non-destructive — makers live in it.

**M49 — Thread.**  Fusion's most-used maker feature after holes.
v1: cosmetic-style real geometry — helical ridge cut (loft engine along
a helix: rings on a rising circle path), or hole option "tapped Ø" with
ISO pitch table.  Test: helix ring count, min wall, export watertight.

**M50 — Pattern on path.**  Third pattern Fusion offers; reuses the
M35 path chain: place N instances of a body/feature along a sketch
path via frame-transform copies (loft kernel already builds the frames).

**M51 — Split Body (plane trim).**  Multi-body is out of v1 scope, but
Fusion's most common split is "cut away one half": Split › plane ›
discard side, kept as a parametric subtract feature.

**Later candidates (researched, deferred):** Patch/Thicken
(surface kernel gap), Draft, Combine/multi-browser-bodies, Appearances
(per-body colour), configurations, assemblies/joints, sheet metal,
drawings.  Re-evaluate after M48.

## Testing doctrine (unchanged)

Every milestone: kernel unit tests with analytic ground truth (volumes,
watertightness, genus) + UI tests driving real widgets headless + a
screenshot proof in /tmp/opencode/shots + README/status bump + commit —
then straight to the next.  No permission asks; stop only if the user
redirects.
