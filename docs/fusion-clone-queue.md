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

**M48 — Section Analysis.** ✓ SHIPPED.  Clip plane in the fragment
shader (discard past the plane): ribbon ▸ Design ▸ Section flyout picks
XY/XZ/YZ, Flip swaps the clipped side, the same plane twice (or Turn
off) restores the body.  Purely visual, non-destructive — the model,
hits and exports are untouched.  Construction-plane sections land in
M49's neighbourhood.

**M49 — Thread.** ✓ SHIPPED.  The Hole dialog gains a **Thread** row
(None + ISO metric coarse M3–M12).  Choosing a size drills at the tap-
drill Ø (major − pitch, the maker rule) and lofts a helical wire groove
out to the ISO major radius — real, watertight thread geometry, not a
decal.  The helix ring frame is analytic (constant lead ⇒ roll-free), so
it stitches through the same loft engine as sweeps.  Thread pitch/length
persist in the `.tracer` JSON and re-drill updates in place.  Bonus fix:
the Hole dialog's bore-row show/hide (untested since M31 because every
test patched `.ask`) was silently broken — now on the version-stable
LabelRole/FieldRole API and pinned by a real-dialog test.

**M49b — External thread.** ✓ SHIPPED.  Click a boss's cylindrical face,
ribbon ▸ Thread, pick the ISO size — a helical ridge cuts down to the
minor and the boss becomes a bolt.  Cylindrical faces are recognised by
fitting the picked facet's smooth region (grow-across-30°-bends flood,
axis from the normal fan, Kåsa circle fit) — flat or conical patches are
refused with words a maker can act on.  The size dialog names the
closest ISO size to the fitted Ø.  Cosmetic threads deferred.

**M50 — Pattern on path.** ✓ SHIPPED.  Draw an open line/arc chain
(reusing M35's path_chain, now with the profile circle optional), pick a
feature and a count, and N copies walk the path at equal arc-length
stations — ribs, handles-in-a-row, bolt circles on an arc.  Placement is
translation-along-the-polyline (v1: no rotation following the curve),
the sketch's frame lifts the 2D walk into 3D exactly like a sweep, and
the feature is JSON-persistent with a timeline glyph and inspector
length readout.  Rotation-follows-path and closed loops deferred.

**M51 — Split Body (plane trim).** ✓ SHIPPED.  Ribbon ▸ Split Body:
choose XY/XZ/YZ, an offset from the body centre (0 = half), flip which
half survives — the body is trimmed flush with the plane as a parametric
feature (move it and the cut follows), validated against the current
solid BEFORE history is touched so a plane that would eat everything
warns instead.  Multi-body splitting (keep both halves as separate
bodies) stays out of v1 scope — this is the maker-truth 90% of it.

**M52 — Appearance.** ✓ SHIPPED.  Ribbon ▸ Appearance: paint the body
with a shop material (Steel, Brass, Copper, Anodized red/blue, rubber…)
or a custom colour, and dial opacity — below 1.0 the body ghosts like
Fusion's edit-transparency, the grid showing through the walls.  The
paint is a shader uniform (one multiplication in the Blender-solid
lighting model), rides the document JSON, re-syncs on open/new/undo,
and the exact colour returns when the paint is cleared.  Per-body
appearances arrive with multi-body.

**M53 — Move Body.** ✓ SHIPPED.  Modify ▸ Move body (ribbon button too):
the RGB triad appears at the body centre exactly like Fusion — press an
arrow, and the solid slides along that axis 1:1 with the mouse (the
cursor ray's closest-approach parameter along the grabbed axis IS the
distance); the live preview is a shader offset, so dragging is free of
kernel calls; release commits a parametric ✥ MoveFeature (edit the
vector, the body slides), Esc or an empty click cancels without leaving
a trace.  While at it the mouse grammar was corrected to Fusion's
real defaults: **MMB drags orbit, Shift+MMB pans** (it had been
inverted).  Rotate-by-triad and copy-on-move deferred.

**M54 — Visual Styles.** ✓ SHIPPED.  View ▸ Visual Styles, the honest
five: **Wireframe** (faces discard, only crease + silhouette edges
remain), **Ghosted** (20% body — the grid reads through, Fusion's edit
look), **Shaded**, **Shaded with edges** (our pixel-pinned Blender
default — restoring it restores every pixel), and **X-ray** (blue-grey
at 35%).  Each style is shader-uniform state, pixel-tested per style;
paints from Appearance still tint through Ghosted and X-ray.

**M55 — Rotate Body.** ✓ SHIPPED.  Modify ▸ Rotate body: three RGB
rings appear around the solid — drag one and the body spins about that
axis following the cursor's polar angle in the ring plane (right-hand
rule, the same convention as every Tracer angle); the preview is one
4x4 matrix uniform, release commits a parametric ⟳ RotateFeature named
for its axis and degrees, Esc/empty-click cancels.  Together with
Press-Pull (M35) and Move (M53), the body now answers to Fusion's full
direct-manipulation mouse grammar.

**M56 — Marking menu.** ✓ SHIPPED.  A right-CLICK (no drag) anywhere in
the canvas pops Fusion's veteran shortcut menu: Fit, Zoom to
selection, the four standard views, the Visual Styles submenu, grid and
edge toggles — every entry drives the real command.  A right-DRAG
still orbits, exactly like Fusion telling the two gestures apart.

**M57 — Copy (Ctrl-drag).** ✓ SHIPPED.  Hold Ctrl when grabbing a
triad arrow or ring and the gesture becomes Fusion's Copy: release
JOINS a shifted/spun twin to the body as one parametric feature
(the +90° copy of a 40×20 plate unions to a cross at exactly 12000 mm³,
watertight — boolean truth, not a mesh merge).  Copy rides undo, the
JSON file, the inspector's "twin joined" line, suppress.

**M58 — Recent Files.** ✓ SHIPPED.  File ▸ Recent Files, Fusion-style:
every open and save pushes the path to the front (dedup, last eight,
QSettings-backed), the submenu lists only files that still exist with
full paths as tooltips, and Clear forgets everything.  Menu order now
matches Fusion: New · Open · Open Recent · Save · Save As.

**M59 — Selection grammar.** ✓ SHIPPED.  Fusion-exact on real faces:
a plain click REPLACES the selection (whole logical faces), Ctrl+click
toggles faces in and out of the set, Ctrl+click empty ground changes
nothing, plain click empty clears, and a Ctrl+drag rubber band ADDS to
the set (left→right still windows, right→left still crosses).  Measure
now follows Fusion: click one face to read it, Ctrl+click a second to
read between.

**M60 — Document Measures.** ✓ SHIPPED.  Tools ▸ Document Measures
(now a Tools menu of its own, like Fusion): millimetre, centimetre or
inch, and every readout re-voices live — the body card, every feature
card, the measure line, the status bar's unit tag.  The model never
changes: geometry stays pure millimetres and the unit ships as file
metadata, so an inch document is the same math with a different
accent.  mm output is byte-identical to the pre-M60 voice the suite
pins.

**M61 — Change Parameters.** ✓ SHIPPED.  Fusion's Modify ▸ Change
Parameters: right-click any parametric feature (or the Modify menu) and
its real levers open in a unit-aware dialog — box dims, extrude height,
hole depth, pattern counts, split position, move vectors, rotate
axis+angle, copy flags.  OK re-runs the kernel and the body follows
(undo-safe); cancel changes nothing; captured geometry (loft/sweep)
honestly reports it has no plain numbers.  In an inch document the
dialog takes inches.

**M62 — Zoom window.** ✓ SHIPPED.  The marking menu's third zoom
entry, in Fusion's place after Fit and Zoom to selection: arm Zoom
window, rubber-band a rectangle, and the camera refits onto the world
bbox of the mesh that fell inside it.  A plain click or Esc aborts with
the camera untouched.

**M63 — Cube hover & rubber voices.** ✓ SHIPPED.  The ViewCube lights
the face under the cursor (hit-testing the very polygons it painted)
and offers the hand cursor, Fusion-style; and the selection rubber
band now speaks Fusion's two colours — blue WINDOW left→right (must
contain) versus green CROSSING right→left (just touches).

**M64 — Combine.** ✓ SHIPPED.  The ribbon's ⊕ button is Fusion's
Combine with the tool built on the spot: pick Box, Cylinder or Sphere,
place its centre, choose **Join / Cut / Intersect** — a boss, a gusset
or a trim lands without a single sketch line, as one parametric
CombineFeature that Change Parameters speaks for, JSON round-trips and
undoes.  Volumes are kernel truth to three decimals (8000 + πr²·20 for
a pushed-through boss, corner cut exact, intersection exact), watertight
every time.

**M65 — Primitive.** ✓ SHIPPED.  Create ▸ Primitive, the fastest
start a maker wants: Box / Cylinder / Sphere dialled in document
measures with a boolean operation and a placement (box corner, cylinder
base centre, sphere centre), dropped as a parametric PrimitiveFeature —
the first one IS the body, later ones Join / Cut / Intersect into it
with exact volumes and per-kind names (Box 1, Box 2…).

**M66 — Cone.** ✓ SHIPPED.  The kernel's cylinder was always a
two-radius secret, so now Box / Cylinder / **Cone** / Sphere all speak
from the Create dialog and as Combine tools: truncated cones at
πh/3(r1²+r1r2+r2²) exactly, sharp cones (top radius 0) watertight, cone
cutters carving chamfer-like corner nicks, all three radii plus height
editable in Change Parameters.

**M67 — Autosave & crash recovery.** ✓ SHIPPED.  Every successful
recompute mirrors the document into a recovery folder
(QSettings-relocatable, so tests never haunt the real one); save, open,
new and a clean close clear it.  The app's entry point offers the
newest autosave at startup — Open reopens the real document with path
and dirty flag intact; Discard deletes it for good.  The recovery tests
also caught a real M58 bug: PySide6 stores an empty QSettings list as
"@Invalid()" and reads it back as None, so Clear Recent Files crashed
the NEXT launch — _recents now shrugs off None, Clear removes the key,
and the fixture poisons are gone.

**M68 — Torus.** ✓ SHIPPED.  Fusion's fifth primitive, via the kernel's
revolve on a circle profile: 2·π²·R·r² to faceting tolerance, genus-1
watertight, resting tangent where placed.  It speaks every primitive
dialect — Create dialog (ring + tube radius), Combine tool (a cutter
that guts a slab by exactly its ring volume), Change Parameters, JSON,
and the ⊕ card's "ring Ø… × tube Ø…".

**M69 — Taper (draft angle).** ✓ SHIPPED.  Extrusions can now lean: a
taper of θ degrees lofts the outer skin to the profile offset outward by
h·tan θ (shapely mitre buffers, winding-normalised so the loft never
twists) while holes shrink on the same slope through cutters that run
1 mm past both caps.  Volumes track the exact prismatoid — a 45° wall
40×20 grows to 60×40 (Simpson-exact areas), a drafted circle is a cone
frustum, a drafted through-hole keeps its channel watertight with genus
honest — and taper 0 stays byte-identical to the old straight extrude.
Dialed from Change Parameters (degrees, negative necks in), shown on
the card as "taper: +45.0°".

**M70 — Symmetric extent.** ✓ SHIPPED.  The extrude dialog's other
extent voice: a symmetric feature grows −h/2…+h/2 about its sketch
plane — an XY box sits z −5…+5, a face-sketch wall centres on ITS plane
wherever that floats, and symmetric + taper composes into a solid that
bulges mid-height exactly like a drafted rib about the profile. One
checkbox in Change Parameters, one "extent: symmetric" line on the
card, JSON-clean, and switching back restores the one-sided box to the
micron.

**M71 — Mass properties.** ✓ SHIPPED.  Inspect-grade answers to the
maker's first question: Tools ▸ Mass properties (and the ribbon's balance
glyph) asks for a material — 13 shop densities from PLA to copper, your
last choice remembered — and answers with volume, surface area, mass in
grammes and the true volume centroid, all in document measures.  The
math is kernel truth: a 20 mm cube is 8 g at density 1.0, and a plate
plus a post balances its centre of mass to the weighted-millimetres
arithmetic a physics tutor would sign.

**M72 — Keyboard grammar: Del, F2, Z.** ✓ SHIPPED.  The browser tree
now speaks Fusion's muscle memory: Delete (or Backspace) on a selected
feature routes the EXACT context-menu handler — undoable, recompute-
clean — and F2 opens the rename prompt.  On the canvas, Z frames the
picked faces.  Chasing why Z appeared inert uncovered a silent M59
regression: selection_bbox took min/max over the (N,3,3) triangle-corner
block and handed back matrices, so zoom-to-selection had been throwing
inside the key handler since selection went multi-face.  It now flattens
the corners — pinned by a shape-exact test — and an end face fits at half
the distance.

**M73 — The constraint voice.** ✓ SHIPPED.  Fusion never leaves you
guessing whether a sketch is tamed, and now neither do we: the sketch
toolbar reads fully / under-constrained (with the free-dof count)
straight off the LM solver after every edit — and answers immediately on
load — while the browser appends the same verdict to every sketch node,
in both the body nest and the Sketches folder.  Constraints that fight
("fix" the same point twice, elsewhere) get an honest ⚠.  Empty sketches
stay silent; the role data under the renamed text still double-clicks
into the editor.

**M74 — N-section loft.** ✓ SHIPPED.  The kernel always lofts a list;
the command capped it at two.  Fusion's dialog gathers sections in order,
and now so does ours: pick + Add into an ordered list with ▲▼ and Remove
(which refuses to starve the loft below two), the first two sketches
preloaded so the old base→top click path stays one click.  Three circle
sections blend two honest cone frusta — πr²·h arithmetic to 7e-4,
watertight (the hourglass proof).  Two-section names and messages are
untouched; every M36 test speaks to the reshaped dialog unchanged.

**M75 — Closed ring loft.** ✓ SHIPPED.  LoftFeature always
had a `closed` field and the kernel always stitched last-back-to-first
("endless ring") — but nothing in the UI ever asked.  The dialog now has
the checkbox (and graduates to a {sids, closed} contract, with a
bare-tuple fallback so every older scripted dialog still lofts), and
action_loft names it honestly: "Ring loft base ↻ 3".  Topology as proof:
three circle sections spaced 120° around an axis blend into a watertight
genus-1 ring — Euler number 0 — and the JSON round-trip keeps the loop.

**M76 — Emboss / engrave text.** ✓ SHIPPED.  The maker's favourite:
a name, a part number, a warning.  Qt's tessellation of the system font
hands us closed glyph contours, sorted into islands and counters by
containment ranked by AREA (an O's own centroid sits in its counter —
winding alone lets them claim each other), scaled to the requested cap
height and centred.  Every island drops as its own parametric
ExtrudeFeature, so undo, recompute and Change Parameters treat a letter
like any other wall, and the ribbon gains Text next to Primitive.
Volume truths come from the same tessellator the command uses, so the
8000→16000±area·d checks are font-portable: Linux DejaVu and Windows
Arial both pass their own arithmetic.

**M77 — The drawing magnet.** ✓ SHIPPED.  Fusion never lets a drawing
click land on dead air when something is worth catching, and the magnet
was a line-tool private: rect, circle, arc drew from wherever the mouse
happened to be.  Now every tool runs the same grammar — existing point,
then the sketch origin, then (toolbar "Snap to grid") intersections —
and a caught corner SHARES the point it caught: add_rect builds from
the given corners, so a rectangle drawn off an existing point drags
both shapes together.  The hover ring appears before the click, the
crosshair wears itself onto every draw tool, and the setting outlives
the session.  Windows CI also caught M76's first real bug the same day:
DirectWrite welds a glyph's counter into its outer contour as one
self-crossing ring — buffer(0) untangles it now.

**Later candidates (researched, deferred):** Patch/Thicken
(surface kernel gap), Draft, true multi-body (Combine today builds
placed tools, M64; separate bodies in the browser remain),
configurations, assemblies/joints, sheet metal, drawings.
Re-evaluate after M52.

## Testing doctrine (unchanged)

Every milestone: kernel unit tests with analytic ground truth (volumes,
watertightness, genus) + UI tests driving real widgets headless + a
screenshot proof in /tmp/opencode/shots + README/status bump + commit —
then straight to the next.  No permission asks; stop only if the user
redirects.
