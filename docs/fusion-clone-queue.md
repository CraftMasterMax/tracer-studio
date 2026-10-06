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
the session.  Windows CI also spent the day teaching M76 humility:
a first guess (welded counters, fixed with buffer(0) untangling) was
half right — the untangling stays, it costs nothing — but an
always-failing probe commit forced Windows to print the truth: before
the platform font engine is fully awake, QFont resolves to .notdef and
EVERY letter tessellates as one 4-point tofu rectangle, validly and
silently.  So Tracer now SHIPS its lettering: Liberation Sans (SIL OFL,
in resources/fonts, registered via addApplicationFont) is the first
tessellation candidate on every platform, and any candidate whose rings
are all square-and-full boxes is vetoed — a cold engine can no longer
emboss squares, it falls through or the command warns.  Two tests pin
the lesson: a cold-engine T must be taller than wide, and the tofu
guard must recognise a box.

**M78 — Marquee select + drag magnet in the sketcher.** ✓ SHIPPED.
The viewport has box-selected since M62; the sketch editor made you
click entity by entity.  Dragging from empty space now throws a dotted
marquee whose interior tints, and everything it TOUCHES — window AND
crossing at once, lines passing clean through included — lands in the
selection; plain empty-click clears, Ctrl+band adds (the M59 grammar,
kept).  A caught line feeds act_H exactly like a clicked one — the band
makes real selections, not paint.  Dragged points likewise CLICK onto
the origin, grid crossings and other points (the magnet skips the
dragged point itself — it must not eat its own cursor), and the release
lands EXACT: (0,0) is the origin, not 0.0007 off it.

**M79 — The ellipse: the sketcher's last basic shape.** ✓ SHIPPED.
Line, rect, circle, slot, polygon, arc — and the shape Fusion's sketch
palette still had that we lacked.  An Ellipse is now a first-class
entity: a shared centre Point (so the magnet, snapping, Fixed and
dragging all work on it for free) plus rx and ry as REAL solver
variables — a bare ellipse counts four DOF and the toolbar's constraint
voice says so.  Centre-first UX, drag or two clicks, and the E key.
It profiles as a 96-gon loop, so an elliptical prism's volume is
π·rx·ry·h, and JSON round-trips carry it whole.  The proof shot also
caught a sibling bug the marquee script never hit: click-mode rubber
bands rearmed themselves around the M77 Point object and silently
crashed the paint (Qt swallows paint exceptions — tests never saw it);
and radius clicks MINTED stray points, two phantom DOF per circle.
Both fixed where they lived — tools consume their aim clicks now, and
drags reuse the armed centre.

**M80 — Mirror entities.** ✓ SHIPPED.  Shift+M, the Mirror button, or
the two-line context menu: the FIRST selected line is the axis and
every other curve gets a mirrored twin.  Two Fusion-grade behaviours
make the copies geometry rather than paint: points that lie ON the
axis are SHARED between original and twin (the halves weld into one
profile), and geometry that mirrors onto itself is SKIPPED (an edge
lying on the axis must not double — or the stitcher doubles material).
Ellipses mirror about axis-parallel lines only — a slanted axis would
need a rotated ellipse we don't model, and the copy is honestly
skipped rather than silently wrong.  K (construction toggle) grew
circles and ellipses in the same pass.  Mirrors are static copies —
Fusion's parametric mirrored constraints are logged as future work.

**M81 — User Parameters + expressions.** ✓ SHIPPED.  First milestone
out of the Oct-2026 research sweep, and the heart of what "parametric"
means: a named parameter sheet (`width = 60`, `height = width / 2`,
comments allowed) plus an fx column on every numeric lever of Change
Parameters, so a feature's number can CARRY A FORMULA instead of a
value.  Edit one parameter and the bound levers rebuild through
`Document.recompute` — formulas are spoken in the document's measures
and scale to stored millimetres, integer levers (pattern counts) round
themselves, and a bound lever always follows its formula: type a plain
number over it and the formula wins, exactly like Fusion's fx cells.
The evaluator is a whitelisted AST walk (+ - * / ** , min/max/sqrt/
abs/round, names only — never exec, because these strings come out of
someone else's JSON); cycles and strays name themselves in the error
and a sheet with one bad line is refused WHOLE.  Bindings and params
serialize with the document; pre-M81 files load untouched.
Sketch-dimension fx bindings (the deeper half) are M81b.

**M82 — Project model edges into sketches.** ✓ SHIPPED.  The single
most-requested workflow on r/3Dprinting forums (and FreeCAD 1.1's
headline feature): sketch on a plane and PROJECT the solid's edges
under the cursor.  On a mesh kernel the honest translation is the
plane cross-section — trimesh slices the current solid and the rings
land as REFERENCE geometry (SketchModel.refs), never solver entities:
a projected circle really is the mesh's 64-gon, and minting solver
points for it would explode the DOF and turn every click into a
phantom magnet.  Refs draw dashed, persist with the sketch payload,
undo with the history snapshots, REPLACE themselves on re-project and
never enter loops or constraints — but the drawing magnet grabs their
vertices, so new geometry snaps to real material edges (verified:
corner snap is exact).  Coplanar grazes fall back ±1 µm into material;
a plane slid along its normal honestly projects nothing.  Sketch
placement offsets of the consuming feature are not yet honoured (the
projection rides the sketch's own frame) — logged with M81b.

**M83 — DXF / SVG profile import.** ✓ SHIPPED.  Insert ▸ Import
body's little sibling for the panel-and-art crowd: File ▸ Import
profile (DXF/SVG) lands a 2D drawing as REAL sketch entities — lines,
true circles, true circular arcs — with every seam vertex WELDED onto
a shared Point, so imported outlines close, stitch (verified: bracket
outline 2800 mm² + two hole rings) and extrude like hand-drawn
geometry.  Splines, elliptical arcs and SVG beziers flatten to honest
polylines; TEXT/HATCH/paper junk is skipped by design; SVG's y-down
world flips to sketch y-up.  Readers live in tracer.core.import2d
(ezdxf + svgelements, both MIT) speaking one tiny op-tuple IR; the
import lands undoably in the open sketch, or auto-starts an XY one.
Assumed scale is the document's measures, and the status says so.

**M84 — Robust offsets from the manifold kernel.** ✓ SHIPPED.  Offset
Entities grew from straight-single-loop-only into the real tool: the
dialog now carries a join choice (mitre/round), and everything beyond
the classic case — rounded joins with TRUE arc corners, sketches with
circles/arcs/ellipses, outlines WITH HOLES, and several loops at once
— rides `manifold3d.CrossSection.offset` (the bundled kernel, zero new
deps, FillRule.EvenOdd composition, CCW normalised).  Self-intersections
are cleaned by the kernel's robust predicates; collapses are refused
and leave the sketch untouched.  Two exactness promises kept: a plain
straight loop with a mitre join still uses the classic shifted-edge
construction (byte-identical to M34 — the old pinned tests did not
move), and a LONE circle offsets to a TRUE circle, not a 64-gon.
Round-join areas verified against Steiner's formula (A + Pd + πd²).
The M34 refusal tests were rewritten into capability tests (curves
and holes now offset); its UI tests rewired to the richer dialog.

**M85 — Batched pattern booleans.** ✓ SHIPPED.  Linear, circular and
path patterns used to weld their copies one pair at a time — N-1
serial manifold calls, each re-processing the growing solid.  They now
fold through `Manifold.batch_boolean` in a single parallel kernel pass
(`Solid.batch_union`): a 60-copy pattern recomputes in ~1 ms, all 57
legacy pattern tests pass with byte-comparable volumes, and the fold
short-circuits count-1 patterns outright.  (The sibling idea from the
sweep — replacing the shapely winding-ranking in regions() with the
kernel's FillRule composition — stays a CANDIDATE: it's invisible
robustness with heavy blast radius on 300+ feature tests; it returns
only when a concrete profile failure demands it.)

**M86 — 3D Print dialog.** ✓ SHIPPED.  Utilities ▸ 3D Print, honest
clone: the part is INSPECTED (triangles, watertightness, island count,
bed-size and hair-thickness warnings), WEIGHED against the same
material table Mass Properties uses (PLA defaults, remembered in
QSettings), and exported as a print-ready STL that — via Drop to Bed —
lands on z=0 while the DOCUMENT never moves.  Changing material
re-weighs the report right in the dialog.  No fake printer drivers, no
cloud: the report is computed from the real mesh in
tracer/core/printcheck.py, which the tests pin directly.

**M87 — Redundant & conflicting constraint diagnosis.** ✓ SHIPPED.
The solver always knew a sketch was bad ("⚠ conflicting constraints");
now it knows WHICH constraint. After every solve, the residual
Jacobian's rows are swept with Gram-Schmidt in constraint order — a row
in the span of its predecessors adds no information and is REDUNDANT
(the LATER duplicate carries the amber badge, FreeCAD-style); a row
whose residual refuses to close is CONFLICTING (red badge, and never
blamed twice — dependent-but-failing rows count only as conflicting).
Rows map back through expand() to the user constraint that minted
them. The status bar counts both ("⚠ N conflicting constraints ·
M redundant"), the classic pinned grammar survives byte-exact for
clean sketches, badges paint red/amber accordingly, and DOF math is
untouched — this names what the rank already knew. Honest quirk the
tests document: LM's least-squares COMPROMISE under conflict drifts
nearby pins, so the blame set can ripple beyond the single fighter —
exactly how Fusion cascades red too.

**M88 — The rollback bar (rubber band).** ✓ SHIPPED.  Fusion's most
iconic timeline verb: a band that sits BETWEEN chips and hides
everything downstream, so you edit inside history. Feature context menu
▸ "Rollback to here" moves the band (on the last chip it ends
rollback); clicking the band itself ends it; downstream chips dim and
`Document.recompute` simply stops at the marker — pattern sources
under the band drop out gracefully. Honest scope: the position is VIEW
state, never serialized, exactly like Fusion not baking your rubber
band into the file.  Suppress (which already existed) hides one
feature; the band rewinds time.

**M89 — Sketch dimensions carry formulas (M81b, the deeper half).**
✓ SHIPPED.  M81 put fx on FEATURE levers; this puts fx on the
DIMENSIONS. Double-clicking a dimension label now opens a dialog with
a formula line: type `width * 2` and the dimension binds to the
parameter sheet — validated against the sheet names, refused loudly on
unknowns, released by blanking the fx field. Bindings are
{constraint-index: {expr, type-tag}} stored in the sketch payload; the
type tag refuses to silently re-drive a different dimension if
geometry was edited underneath (it idles with a warning), so a stale
fx can never move the wrong edge. The rebuild half is the real work:
`Document._refresh_sketch_feature` re-derives extrude/revolve profiles
from the payload (model → apply formulas → solve → regions →
outer/holes) whenever parameters exist, and rewrites the payload from
the solved model so reopening the editor sees the truth. Sheet edit ⇒
solid follows, demonstrated: width 30→50 moves the extrusion
3000→5000 mm³. Driven dimensions paint Fusion's `= 50.00` chip
(accent border) on canvas, and two legacy m5 tests now ride the fx
dialog (blank fx = the old plain-number edit, byte-identical results).
Honest scope: linear dimensions scale with document measures, angles
never do; hole/loft/sweep sketches keep frozen geometry for now;
bindings undo with the sketch (they serialize in the payload, and
`_restore` copies them like M82's refs — the same trap, twice caught).

**M90 — Type a number right after drawing.** ✓ SHIPPED.  Fusion's
fastest verb: draw a line, hit 4-0-Enter, the line IS 40 mm. Line,
circle, arc and rectangle creation leave a type-in armed; digits
buffer into a small accent-bordered chip at the geometry (Fusion's
little white box), Enter mints exactly the constraint act_dim would —
including its remove_last habit, so re-typing never stacks dimensions
— and Esc, any tool key, or the next stroke lets go cleanly.
Rectangles take TWO numbers like Fusion: width Enter, height Enter,
landing on the auto-H/V bottom and side edges the rect tool mints.
Undo rolls a typed dimension back with the geometry. Honest scope:
plain numbers (fx formulas stay in the dimension dialog), millimetres,
ellipses/slots not armed yet.

**M91 — Configurations: named parameter sets.** ✓ SHIPPED.  Fusion's
Configurations turn one model into a family — Small/Large rows that
override sheet names behind a switcher. The third leg of the
parametric triad now stands: M81's sheet, M89's dimension bindings,
and here `Document.configs` ({name: {param: formula}}) with
`active_config` overlaying the base at resolve time via
`merged_sheet()` — a plain dict overlay, so override formulas may
reference other sheet names and base formulas keep following the
overrides. Serialize with the file; unknown active names honestly
ignore; the dialog (Manage + Tools menus) speaks a text table —
`Small: width = 18, height = 10` per line (M81's sheet-text precedent)
— refused whole when malformed, and `_set_active_config` is the
undo-safe switcher. Demonstrated: 30 mm plate at 3000 mm³ becomes
1800 under Small and 5000 under Large without touching the model.
Honest scope: one active configuration at a time (Fusion shows several
in an assembly), no per-feature suppression per config.

**M92 — Export a sketch as DXF/SVG (M83 in reverse).** ✓ SHIPPED.
The maker loop's exit ramp: sketch the bracket, hand it to the laser.
`tracer/core/export2d.py` speaks the same op-tuple IR M83 reads —
DXF gets TRUE LINE/CIRCLE/ARC/LWPOLYLINE primitives with ezdxf
(arcs keep their exact geometry; the CCW/DXF direction swap is tested
as a set, since travel direction is meaningless for profiles), SVG
writes standard positive y-down paths, 1 unit = 1 mm, viewBox "0 0 w
h" — which makes M83's translate+flip reader contract the exact
inverse, spans and lengths preserved through export→import.
Construction geometry is scaffolding and stays home; ellipses flatten
to closed polylines (64 segments); an empty sketch says "That sketch
is empty" and mints no file. Proof by round trip both ways, in tests
and in a screenshot. File ▸ Export profile (DXF/SVG) lands between
Export STEP and Export render — the m15 layout pin moved with it, the
documented pattern. Works from the live editor or straight off a
sketch FEATURE payload (no edit needed).

**M93 — Drawings phase 1: the sheet.** ✓ SHIPPED.  The maker's second
document. No B-rep edges to harvest, so views are VIEW-DEPENDENT
SILHOUETTES — an edge draws where one face turns toward the viewer and
the other doesn't (away or grazing), plus a 40° crease term so the iso
view keeps its corner Y (coplanar triangulation crumbs stay invisible
by the same rule). Boolean tessellations scatter Steiner points along
rims, so segments are endpoint-welded, walked into chains and
collinear runs merged: a plate-with-hole top view = one rectangle +
one circle, not 260 crumbs (the number that motivated the welder).
Standard layout — top/front/right/iso in page slots, auto-fitted,
title block bottom-right. The sheet stores only NAME + PAPER; views
re-derive from the live model every repaint, so it can never be stale
(proved: doubling a dimension between two snapshots doubles the view).
Create ▸ New drawing…; A3/A4 toggle; zoom/pan; exports as PNG (pixels)
or DXF — the drawing IS a profile, and the M83 reader proves it
round-trips. Honest scope: visible lines only (no hidden-line pass),
views auto-place (view dragging is still ahead; the bubbles promised
for M94 arrived with M94), one sheet per drawing entry.

**M94 — Dimension bubbles on the sheet.** ✓ SHIPPED.  A drawing
without bubbles is a picture. Two endpoint clicks in any view lay a
draughtsman-standard callout: extension lines, an arrowed dimension
line offset AWAY from the view centre, and the millimetre value
knocked out of the line in a paper-coloured gap. The engineering is
in the anchor: endpoints store model millimetres PLUS their fraction
of the view's silhouette bbox, and every repaint re-solves them
against the LIVE model — stretch dx 40→80 and the width bubble's
arrows slide to the new corners and its text re-reads 80.00 by
itself (a raw stored number couldn't know it was the right corner;
the fraction can). Clicks snap to projected chain endpoints (3 mm
slack). Numbers can't lie: the text is re-measured, never typed.
Bubbles serialize with the drawing, each is undo-captured, and DXF
export carries the dimension ink — the paper text is the PNG's job.
The Dimension toggle sits on the sheet toolbar; in bubble mode
left-click dims instead of panning. Honest scope: linear only (the Ø
bubbles came in M95), two-click commit, bubbles ride the sheet's
last drawing entry.

**M95 — Diameter bubbles: the hole finally says Ø.** ✓ SHIPPED.  A
maker's drawing is mostly holes, and one click on a projected circle
now lays the diameter: circles are FITTED from their silhouette
chains (closed, square bbox, uniform radius — the fit honestly
refuses rectangles, open chains and iso ellipses), the bubble spans
rim-to-rim through the centre with arrowheads at both ends and the
value knocked out mid-line. Following is the clever part: linear
bubbles anchor by view fractions, but a bore's size isn't part of the
sheet's extent — so a Ø bubble re-FINDS the live circle nearest its
centre each repaint and adopts its true radius: redrill 4→7 and the
bubble reads Ø 14.00 by itself. The match is proximity, not
named-entity attachment: delete the bore and the bubble keeps its
last honest measurement rather than drifting silently. Ø text is
paper ink; DXF export carries the span geometry. Honest scope: full
circles on orthographic views only (arc R-bubbles are ahead), one
click lays it, linear keeps its two.

**M96 — Sheet management: the browser tree, real multi-sheet,
draggable views.** ✓ SHIPPED.  Sheets graduate to first-class
citizens: a `Sheets (n)` folder sits in the browser beside Bodies and
Sketches, every drawing is a node, and double-click puts THAT sheet
on the table (the newest still wins on creation). Views are no longer
nailed to the layout assistant's slots — grab one and drag; the move
is stored per view, IN SHEET MILLIMETRES, on the drawing entry
itself, so the assistant's placement still computes underneath and
the draughtsman's nudge simply rides on top (views keep re-deriving
live: drag a view, then change the solid — both work at once).
Bubbles travel with their view automatically: they anchor to model
geometry, not paper pixels. A drag captures undo on first movement
(not on press, so a fat-finger click leaves no dead undo step),
serialises with the file, and dragging the empty desk still pans as
before. Fixing a genuine stale-paper bug along the way: undo/redo now
rebinds the sheet canvas to the resurrected document instead of
painting a dead one. Honest scope: one body per sheet (the model
result), moves are translation only — rotation and per-view scale are
ahead.

**M97 — Hidden lines: the sheet dashes what the body hides.** ✓
SHIPPED.  A drawing of only visible edges is a shadow puppet. An edge
is HIDDEN when neither adjacent face looks at the viewer (both face
away) AND the fold is sharp (>40° — so a smooth wall never dashes
into a mesh wireframe and spheres stay clean), AND its midpoint lands
STRICTLY inside the front-facing silhouette region — the region the
visible faces actually cover, holes subtracted (a bore is a hole in
the paper). That clip is what makes it correct where the naive
version drowns: rim-on-rim coincidences (through holes, a convex
body's face-on outline) project onto the region's boundary and clip
away, so the plate's top view stays clean while a block's iso grows
its three back edges meeting at the hidden corner. Hidden chains are
projections, never paper: they re-derive on every repaint, ride the
M96 view drags, follow a squash of the model, and travel into DXF
export. Honest scope: hidden BACK CREASES only — grazing back edges
(an interior bore's profile lines in a front view) are the refinement
ahead; one body per sheet.

**M98 — The sketcher speaks diameter (Ø), like Fusion.** ✓ SHIPPED.
A drawn circle is a hole to be drilled and drill bits are sold by
DIAMETER — yet every circle dimension read "R" and asked for a
radius. Now the whole UI translates at once: the chip reads
`Ø 24.00`, the Dimension dialog asks "Diameter (mm)" showing the
number the chip shows, the double-click editor and the M89 fx line
speak diameter, and the M90 type-in after drawing a circle takes the
number as a diameter. Arcs keep their R — that IS what a fillet
gauge measures. Underneath, nothing moved: the solver's native
Radius constraint is untouched (only the label halves/doubles),
serialized files stay byte-honest with radius values, and inch
documents scale diameters like any length (the fx layer halves
AFTER unit scaling). Migration is loud, never silent: an fx binding
stamped under the old radius meaning ("R" on a circle) idles with
"type changed" instead of quietly doubling the hole — re-bind once
and it drives the diameter from then on. Honest scope: closed
circles only; the sketcher's chip is text, not GD&T (tolerance
stacking is a world away).

**Later candidates (researched, deferred):** Patch/Thicken
(surface kernel gap), Draft, true multi-body (Combine today builds
placed tools, M64; separate bodies in the browser remain),
configurations, assemblies/joints, sheet metal, drawings.
Re-evaluate after M52.

## Oct 2026 research sweep — the landscape and the ranked backlog

A ten-thread research pass (subagent fleet was down — provider 503s — so
it was run inline with web tools).  The short version: **nobody clones
Fusion's UX.**  The open field splits into (a) FreeCAD/SolveSpace —
right features, wrong ergonomics; (b) code-CAD (CadQuery/build123d/
ManifoldCAD) — no GUI; (c) a fresh wave of OCCT-based hobby modelers
(rcad, vcad, OneCAD, noBS-CAD, datum, Oblikovati, hobbycad) that all
chase B-rep and none chase Fusion's *feel*.  Redditors ex-Fusion users
say the quiet part out loud: FreeCAD "looks completely alien"; the
10-document Fusion cap and cloud dependency are driving people out.
Tracer's niche — genuine Fusion muscle-memory, offline, GPL — is
confirmed empty.

Field notes worth keeping:

- **FreeCAD 1.1** (2026-03-25, LGPL): headline features were exactly
  ours to steal first — interactive draggers, transparent previews,
  *projection/intersection into sketches*, hole dialog rework with
  threads, "master sketch" internal contours.  Confirms demand for M82.
- **rcad** (GrantObi/rcad, MIT, 2026-06): closest functional cousin —
  constraint glyphs, live DOF, drag-to-solve, holes (simple/cbore/
  ccsink), mirror/patterns, rollback + suppress.  B-rep/OCCT though.
- **ecto/vcad** (MIT): started ON MANIFOLD ("great for 3D printing,
  not enough for real CAD") then ripped it out for a hand-built B-rep.
  Their retreat is our proof: a mesh kernel is *honest scope* for
  maker CAD — we ship threads/text/shells fine without SSI dragons.
  Also: "built for AI agents" (MCP) is their growth angle.
- **KittyCAD/ezpz** (MIT): Zoo's open 2D constraint solver — good
  literature for our redundancy/conflict reporting (M87), not a
  dependency (we stay pure-Python LM).
- **manifold3d (our kernel!) ships more than we use**: CrossSection
  with `offset(JoinType.Round/Miter)`, `compose(FillRule.EvenOdd/
  NonZero)`, mirror/hull/rotate, and `Manifold.batch_boolean`.
  Exact rounded offsets (M84), kernel-side profile rules (M85) and
  batched pattern unions come FREE — no new deps, no shapely winding
  hacks.  This is the highest-leverage finding of the sweep.
- **SketchForge-3D / ManifoldCAD**: browser apps on our kernel, but
  Tinkercad/script flavours — no overlap with our desktop-clone lane.
- Community magnet: DXF/SVG import is what laser/CNC makers ask for
  first (ezdxf, MIT, is the standard); OpenSCAD's Customizer proves
  the parameter-sheet payoff.

**Ranked execution order (the loop runs this):**

1. **M81 — User Parameters + expressions.**  Fusion's parameter sheet:
   named globals (`width = 20`), `= width * 2` bindings on feature
   fields, safe-ast evaluator, cycle/unknown errors, rebuild on edit.
   The parametric heart every serious rival lists first.  Effort M,
   headless-testable, low risk.
2. **M82 — Project model edges into sketches** (mesh-honest
   Project/Include): slice the solid with the sketch plane
   (trimesh.section) → construction loops under the cursor.  Unlocks
   sketch-on-face workflows; FreeCAD 1.1 headline proves demand.  M.
3. **M83 — DXF/SVG import → sketch profiles** (ezdxf + svgelements,
   both MIT): Insert ▸ Import, splines flattened, closed → extrude.
   The maker-audience magnet.  M.
4. **M84 — Robust offset entities via CrossSection.offset**: JoinType
   Round/Miter + miter limit, arcs/circles finally offsettable, self-
   clean.  S–M, zero new deps.
5. **M85 — Profile core on FillRule + batch_boolean**: retire the
   shapely even-odd winding ranking for the kernel's own compose;
   batched unions speed patterns; groundwork for honest multi-body.  M,
   touches core — sequenced AFTER M84 proves the API surface.
6. **M86 — 3D Print dialog** (Utilities ▸ 3D Print clone): watertight
   check, volume/mass/triangle count, drop-to-bed, one-click STL.  S.
7. **M87 — Solver intelligence**: redundant/conflicting constraint
   detection + on-canvas highlights (ezpz/SolveSpace literature).  M.
8. Then: timeline suppress/rollback, drawings (ezdxf again),
   configurations, multi-body phase 2.

**Non-goals (documented, from the same sweep):** migrating to a B-rep
kernel (the vcad saga is the cautionary tale — years for SSI parity),
T-splines/sculpt, CAM, cloud sync / CRDT collaboration, STEP AP-242
exact parametrics (our STEP is mesh; honest in docs), and chasing zoo's
code-first KCL model — Tracer is point-and-click native.

## Testing doctrine (unchanged)

Every milestone: kernel unit tests with analytic ground truth (volumes,
watertightness, genus) + UI tests driving real widgets headless + a
screenshot proof in /tmp/opencode/shots + README/status bump + commit —
then straight to the next.  No permission asks; stop only if the user
redirects.
