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
| Sketch on a face | ✓ M140–M142 rungs A+B-lite+C-core (derived frame, loop lands, FaceHandle follows at recompute) — C-datum/D queued |
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

**M99 — Thicken: an open sketch becomes a solid wall.** ✓ SHIPPED.
Print-makers live here: a drawn path that should be a 3 mm rib, a
stiffener, a patch plate. Fusion speaks Patch/Thicken for surfaces;
the honest mesh-kernel twin is a buffer — every OPEN chain of the
sketch (lines and arcs, construction excluded, sampled and stitched
where the M93 walker split at a junction) is thickened with BUTT caps
(a straight wall is exactly length × thickness, no semicircular ears)
and ROUND joins (corners bend like sheet, never mitre-spike),
overlapping chains union into one wall before extrusion, and the
strip extrudes `depth` along the plane normal. Closed loops are
refused with directions: "every chain here is closed; use Extrude" —
a maker who means Extrude hears it, not a surprise sliver. The
feature is parametric like its siblings: sketch payload frozen
sweep-style, re-run Thicken to re-extract, edit thickness/depth to
rebuild, timeline ▬ chip, file round-trips, undo captures the mint.
Measured proof: an L-rib of 95 mm stock reads 3,414.2 mm³ against
3,420 straight — the round join trimmed the corner by the exact
sliver it should. Honest scope: XY-style plane transforms like sweep
(one plane per wall); frozen sketch re-edit shares sweep's dormant
path; no variable thickness (that's loft's language).

**M100 — Per-view scale: the draughtsman's 1:2.** ✓ SHIPPED.  Every
maker who has squeezed a part onto A4 knows the need: one sheet, but
the detail view must be HALF size. Double-click a view on the sheet
and Fusion's scale picker appears — Fit (back to the layout
assistant's auto), 1:1, 1:2, 1:5, 1:10, 2:1, 5:1. The override rides
on the drawing entry ({view: factor}) exactly like M96 moves do, so
views still re-derive LIVE: scaling never re-projects anything, it
just changes the frame every chain, bubble and dashed hidden line
already rides through. That is the promise this milestone makes
visible: a 1:2 view's bubble still reads 40.00 — the number measures
the MODEL, never the paper (the ink halves, the truth doesn't). A
scaled view wears its ratio as a caption the way drawings say it
("1:2", not "0.5"), DXF export carries the scaled geometry, undo
takes it back to auto, and nonsense input changes nothing and says
why. Honest scope: scale only (no rotation); an explicit scale is the
draughtsman's responsibility — like Fusion, a 5:1 detail may hang off
the sheet, and the auto-fit only balances the NON-overridden views.

**M101 — True hidden-line removal: depth decides, not vibes.** ✓
SHIPPED.  M97's rule was orientation-only — dash edges whose faces
flee the viewer — which is fine for convex blocks and hopeless for
concave ones, because "facing you" is not "visible to you": a milled
pocket's back wall faces the camera THROUGH the plate's intact front
wall (and M93 drew it solid — over-drawing the cavity), while a bore's
far rim, legitimately seen THROUGH an open hole, had no rule that
could promote it. One classifier now owns the whole question: every
candidate edge — turn, crease, back crease, grazing-and-back creases
(pocket floor meeting a fleeing wall) — is sampled at its midpoint
and asked whether any front-facing triangle covers that point with
nearer depth (vectorized barycentric interpolation). Covered →
dashed; uncovered → solid, including a far rim seen through a hole.
The subtlety that makes it trustworthy: a surface's own edge
interpolates to the edge's own depth, so coincident cover loses to
the depth tolerance while a genuinely nearer silhouette crossing wins
— this is what dashes a box's third back edge in the perfectly
symmetric iso (a strict point-in-triangle test misses exactly that
ray). Coincident segments merge, visible winning: rims that repeat
rims draw one line. Proof sheet: a pocket + blind bore in a plate
dashes its back wall, floor lines and bore walls in the elevations
while the opening rims stay solid, and the through bore's walls in
front view now dash as every drawing standard demands — M93's pin
migrated to the truth, the first test this pipeline ever corrected
rather than pinned. Speed too: visible and hidden now share one pass
cached on the immutable Solid, so steady-state painting beats the old
eight-full-projections-per-repaint. Honest scope: midpoint sampling
(a segment that half-slips out from behind a surface flips as whole
— mesh segments are short); the far bore arc in iso dashes with
Steiner crumbs (collinear merging can't straighten circles, and
they're geometrically true); no section/auxiliary views.

**M102 — Section views on the sheet: cut the body, hatch the wound.** ✓
SHIPPED.  M84's Section analysis only clipped the DISPLAY; the paper
had no way to say "here is what is inside". Now the sheet bar's
Section… dialog picks a plane (X/Y/Z + position) and the drawing
gains a stored, NAMED live view — A-A, then B-B — built from the
half of the body BEHIND the plane, projected through the standard
view that reads the cut face straight-on (Y-cut → front, X → right,
Z → top plan). Because every drawing mechanism since M93 is keyed by
view NAME, the section inherits all of it for free: bubbles measure
the model, M96 drags it, M100 scales it, M101 dashes its hidden
edges, DXF carries it, undo uncuts it, and a stretch re-derives the
wound live (the cut face itself is sliced from the ORIGINAL solid —
the M82 jitter trick guards planes that graze feature boundaries).
The hatch is real geometry, not a texture: the family x − y = c
swept across the face and clipped with shapely, so the PNG and the
DXF agree line for line. Two lessons earned the honest way: the
c-range must span the BOUNDS (a formula tuned on miny=0 hatched
nothing once views sat at real sheet positions), and air gets no
ink — a Z-cut through a pocket is a RING, and hatch_region subtracts
inner loops before sweeping, because hatching a cavity is a drafting
lie. The layout assistant parks extra views in the middle band,
staggered, under grey A-A/B-B captions. Honest scope: full sections
only (no offset/aligned/revolved cuts, no cutting-plane arrows),
one dialog per cut, and the removed half is always the viewer-side
one — the standard reading. Suite stands at exactly 1000 tests.

**M103 — The R bubble: arcs buried in outlines get dimensions too.** ✓
SHIPPED.  One tap lays Ø on a circle (M95) — but arcs never ride
alone in a mesh silhouette. A scallop on an edge, a nook in a corner,
a boss breaking through a wall: the chain walker delivers the WHOLE
boundary as one loop, straights and arc fused, often TANGENT at the
junctions (zero turn, invisible to any "split at corners" idea).
find_arcs cuts arcs out by CURVATURE: a vertex turns 1..60°, its
neighbours the same way and the same sign — mesh walls step a steady
5.6° while 90° corners and 0° tangent seams break the run; rings are
opened AT a corner (never through an arc) before the scan. Each run
gets a circle by VOTE — three vantage triples (head, middle, tail)
propose circumcircles, the one with most inliers wins, Kåsa polishes
the inlier set — because a run's last chord often already points down
the straight that follows, and a contaminated least-squares fit lies
prettier than it should (its endpoints sit happily on the wrong
million-millimetre circle: the vote is not decoration, it is
survival; the circumcircle itself had to be computed against a
translated origin or float cancellation manufactured that million).
Refusals: residuals past 10% of r, spans under 25° or over 330° (a
whole ring is fit_circle's), radii beyond 25× the run's extent
(collinear dust), ellipse views (arcs are ortho-only, like the Ø).
The bubble behaves like M95's: one click, centre + travel direction
stored, the arc RE-FOUND among the live runs on every repaint —
widen the scallop 6→8 and the leader redraws alone; DXF carries the
centre-to-rim leader; undo, file round-trip, per-view scale: all
inherited. Honest scope: a run is one arc (multi-arc polylines are
split by their turn profile and each run votes for itself — S-curves
simply break into opposite-signed runs); tangent-split circles dedupe
by centre+radius; the R leader is a single line, no centre cross.

**M104 — Multi-body phase 2: the browser stopped lying.** ✓
SHIPPED.  The tree had read `Bodies (1) ▸ Body 1` since M43 and there
was always exactly one because recompute() had exactly one accumulator.
Now every feature names the body it builds in (`f.body`), each body
streams its OWN solid, and a cut in Body 2 leaves Body 1 standing.
The load-bearing trick that kept the other thousand tests untouched:
`doc.result` is STILL one Solid — the boolean UNION of the bodies, the
PART — so measurement, drawings, HLR, sections and export never learned
multi-body exists, and a single-body doc returns the very same object
it always did.  Bodies stay separate only in the VIEWPORT, where the
mesh is the visible bodies STITCHED (concatenated, never booleaned):
hiding a body lifts exactly its triangles and a wall shared by two
touching bodies stays drawn, like Fusion.  New Body is a verb (ribbon +
Create menu), activation is a double-click, the bulb is a per-body menu
item, active is bold and hidden is grey in the tree, and the whole lot
saves, migrates (a bodyless file adopts the implicit Body 1 on load)
and undoes.  Press-Pull now asks the viewport for its own pick mesh —
the face ids it hands out index the stitched display, not the union.
Honest scope (phase 2b): exports and drawings still see the fused part,
not a per-body file set; per-body appearances; shell/split face-picking
on a multi-body doc can index a different triangulation than the
stitched mesh (single-body is byte-identical).

**M105 — exports speak per body: the file finally keeps the parts apart.** ✓
SHIPPED.  M104 made bodies real inside the app, but every export still
funnelled through doc.result — the boolean UNION — so a bracket (Body 1)
with a separately-modelled handle (Body 2) left the building as one
merged lump, unselectable in the slicer.  Now the part leaves as its
BODIES: Document.export_solids() hands over every body that has a solid,
in browser order, and io.export_solids writes each as its own object —
3MF/OBJ carry them as SEPARATE, NAMED objects (a slicer opens
"Body 1"/"Body 2", CAD reads distinct solids, world positions intact),
while STL/PLY — single-container formats with no notion of an object —
get every shell concatenated so a disjoint part still lands as N
watertight islands.  One body writes exactly the mesh it always did:
the single-body file is byte-for-byte what Tracer produced before
per-body export existed (the old export_mesh() now just calls the
multi path with one body).  The whole part goes regardless of the
viewport bulb — a hidden browser row is a view fact, not a licence to
lose geometry from a shipped file.  The one-click Print STL keeps
exporting the fused whole-tray (it already carried every disjoint
shell, and a print bed wants one coherent tray, not a body picker).
Honest scope: STEP still exports the fused part — a NAMED STEP compound
means teaching the compiled OCCT bridge to accept many solids at once
(and it is untestable where OpenCascade isn't installed), so per-body
STEP rides with the bridge work below.

**M106 — per-body appearance: paint a single body.** ✓
SHIPPED.  M104 gave bodies their own geometry, M105 their own place in
the file; now they get their own LOOK.  Right-click a body → Paint and
pick a shop material (steel → brass → anodised blue); it rides in the
body dict (so it saves, round-trips and undoes for free), the browser
row names it, and the viewport shades that body — and only that body —
by its colour, under the SAME studio lighting as before, so a brass
boss catches the light brassily next to a blue plate.  The M52 whole-part
Appearance is untouched: it stays the default every body follows.
The shader change is deliberately ADDITIVE and gated: the solid gained a
per-vertex base-colour attribute + a ``u_vcolor`` flag, and while no body
is painted the flag is 0 so the fragment shades by ``u_base`` exactly as
it always did (M52's pixel-exact grey-restore test is the proof — the
buffer and the math are byte-identical); the moment a body is painted the
viewport stitches a per-face colour array and flips the flag.  Honest
scope: per-body COLOUR only — opacity stays a whole-part/disp setting (a
ghosted body can't yet sit beside a solid one), and the wireframe/x-ray
visual styles keep their uniform tint.

**M107 — the fastener hole library: name a screw, get the right hole.** ✓
SHIPPED.  A research re-rank (the subagent fleet was back) put this top:
not a kernel gap — HoleFeature already taps, counterbores and countersinks
— but a KNOWLEDGE gap.  Makers kept having to look up (or mistype) that
an M3 clearance is Ø3.4, an M4 socket head wants a Ø9 counterbore ~5.2
deep, and an M3 heat-set insert presses into Ø4.  A pure, sourced table
(core/fasteners.py) turns a named fastener + kind into exactly the
parameters the Hole dialog consumes: ISO 273 clearance (close/medium/
coarse), DIN 912 socket-head counterbores, and typical heat-set-insert
drills — with tap pitch/Ø reused VERBATIM from ISO_COARSE so the tap path
can't drift from the thread it models.  Pick a Fastener + Size and the
dialog fills drill/type/counterbore and the head reads what it will
actually cut; the sketch circle drops to PLACEMENT ONLY.  The change is
strictly OPT-IN: the dialog's first entry is "Custom (Ø from sketch)",
which clears the drill override and leaves every field to the user, so
the pre-library behaviour (and all four hole test files) is byte-for-byte
unchanged — only the verb learned "drill overrides the circle."

**M108 — the drawing title block: provenance for the sheet.** ✓
SHIPPED.  Backlog #2 from the Oct sweep.  A drawing with no title block
is a pretty picture with no story — nobody knows what it is, who drew it,
when, or what it's made of.  Fusion stamps an ISO block bottom-right; so
does Tracer now.  The five HUMAN fields (drawing no., title, drawn-by,
date, material) are stored on the sheet as `sheet["block"]`; scale, page
size and the sheet's place in the set ("2 / 3") are DERIVED at draw time
from the drawing, so a block can never carry a stale scale after the
model grows.  All of it lives in one pure resolver, `drawing.
title_block(sheet, meta, page)`, returning sheet-mm geometry (frame + the
row/column dividers) and text cells with explicit column boxes, so text
clips inside its own cell and never bleeds across a divider.  The canvas
paints it through the same sheet→pixel map as every view; an untouched
sheet still shows a populated, honest block (title falls back to the
sheet name).  The block is deliberately **paper-only**: it paints in the
canvas and so lands in the PNG, but never enters the DXF line stream —
drawing it there corrupts CAD re-import, exactly as the bubble *text*
already stayed the PNG's job.  A `save()/restore()` around the paint
keeps its pen + font from leaking into the views, bubbles and hatch
painted after it.  Editing is one verb (Title… on the sheet bar): a
text dialog prefilled from the current block; blanks are stripped, an
all-empty block is dropped, and the dict rides the document's undo stack
and JSON save for free — no new serialisation.

**M109 — rotate a view on the sheet (display-only spin).** ✓
SHIPPED.  A draughtsman spins a view to stand a slanted part straight or
set a section upright.  The danger in Tracer is that the bubbles must not
change their minds — our dimensions are measured LIVE off the model
(M94/M95), so baking rotation into the projection would move the very
geometry the bubbles re-measure from and the numbers could drift.  So
rotation is a PURE PRESENTATION transform: a page-space spin about the
view's own centre, applied LAST on the way out (model -> canonical page
-> rotated page) and UN-applied FIRST on the way back (a click is
un-rotated into true model space before it reaches the circle/arc
finder).  The layout core `place()` never learns about it — which is why
every pre-M109 drawing test is byte-for-byte untouched — and `rot = 0` is
the exact identity the sheet used before (the same "gate off, stay
identical" discipline as M106's shader).  It lives entirely in the
canvas: `placed()` tags each frame with `rot` + `ctr`, two helpers
(`_m2p`/`_p2m`) compose and de-compose the spin, and every model->page
paint site (visible chains, hidden ink, section hatch, the Ø/R bubbles,
even the scale caption) routes through them.  Rotation is stored per view
as `sheet["rot"]` and rides undo + the JSON save for free.  The verb is a
**Rotate…** button (view picker + angle) that leaves the M100 double-click
scale dialog alone; angles fold to (-180, 180] and 0 hands the view back
to the layout assistant.  Proof: a front-view bubble reads the same 81.58
upright and at +30 deg while the geometry visibly turns.  13 new tests;
suite 1073 -> 1086.

**Later candidates (researched, deferred):** the rest of backlog #2 — a
drawing parts-list BOM table + balloons wired to it; multi-body phase 2c —
per-body STEP compound (needs the C++ OCCT bridge to take a compound)
+ per-body opacity + cross-body feature sources; the fastener library's
own tail (more threads/fine-pitch, more insert brands, a modelled external
thread on a stud); then Draft, sheet metal, assemblies/joints, and a
section cutting-plane arrow on the drawing.  Re-evaluate after M109.

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

## 2026-10-07 — Research-fleet synthesis (wave 1 landed)

A bounded 3-deep research fleet (100-topic queue, provider-capped) has
been banking verified reports to `/tmp/opencode/research/` (see its
`QUEUE.md` tracker; ~23 landed as of writing, each with [V]-verified
findings + sources + ranked actions).  The build queue below is
re-ranked from that corpus; reports by name are the evidence file.

### Corrections the fleet bought us
- Fusion re-themed (Oct-2025): clone target = the **unified darkBlue
  theme**, not 2019 gray (`ui_colors.md` — exact HIG token hexes +
  viewport semantic tokens: hover `#E3AD79`, select `#0696d7`…).
- Fusion has **no default view-orientation shortcuts** and **no sketch
  grid** (`hotkeys.md`, `ui_canvas.md`) — both are FREE differentiators
  for us, not parity obligations.
- Our solver question is answered: **embed planegcs** (PyPI, LGPL)
  behind a thin interface; scipy-LM as MVP/fallback (`solvers.md`) —
  supersedes the old M87 "solver intelligence" entry.
- 2026 product energy at Autodesk is in BOM/data + UI, not geometry —
  our mesh kernel is not the handicap we feared (`updates_2026.md`).

### Ranked queue (fleet-informed)
1. **M110 — Parts list (BOM) + balloons.** ISO 7573 columns
   (item/description/qty/reference/material), ISO 6433 balloons tied to
   BOM rows, mass = volume × ρ from `material_density_db.md`; sheet
   furniture per ISO 5457 (20 mm filing margin, 0.7 mm frame) as
   paint-only layer.  Includes `core/units.py` (unit_handling.md
   doctrine) as step 0.  Paper-only: never in DXF (M108 rule).
2. **M111 — Data-safety sweep:** atomic save NOW, autosave sidecar +
   restore prompt, version-history panel (`file_locking.md` actions).
3. **M112 — `ui/theme.py`:** HIG token table + single QSS → browser/
   timeline/panels adopt darkBlue surfaces, autodeskBlue accent, status
   trio (`ui_colors.md` actions 1–3).
4. **M113 — Key layer:** verified single-keys (E/H/Q/F/M/V/S/A/J…),
   `S`+`/` command-search popup, Ctrl+Alt show/hide set, drawing-mode
   keys incl. **B=balloon** (`hotkeys.md` actions 1–4).
5. **M114 — Limits & Fits on dimensions** (+ hole callouts) — data
   tables already transcribed (`gdt_tolerances_iso.md`; their Nov-2025
   feature, `updates_2025.md` action 1).
6. **M115 — planegcs embed** behind `core/solver.py` iface; DOF colour
   contract blue→white (`solvers.md`; `sketch_constraints.md` tiers
   1–2 ride on it).
7. **M116 — Fastener data library:** vendor cq-fasteners dicts →
   `tracer-fastener-table-v1` JSON; own CC0 heat-set insert chart
   (`fasteners_iso_din.md` — verify its [H] tables first).
8. **M117 — Interlock family: Snap Fit / Boss / Rest / Lip / Emboss**
   — pure 2D+boolean, zero B-rep disadvantage, direct 3D-print maker
   value (`solid_cmds.md` action 2 — the fleet's top differentiator
   find).
9. **View quality v2:** feature-edge classification (crease+n·v) +
   RDP→spline + reversed-Z preview depth pass (`hlr.md` 2-step).
10. **Construction-geometry batch:** pattern/offset/mirror/resize
    construction geo — their Jan/Apr/Jul-2026 focus area
    (`updates_2026.md`, `solid_cmds.md`).
11. **Timeline status glyphs + message log** (red/orange blocks,
    dimmed dependents — `ui_timeline.md`; contract in
    `history_kernel.md`).
12. **Nav presets + orbit-around-point + window/crossing boxes**
    (`mouse_nav.md`; `ui_navcube.md` landing pending).

### Strategic frame (from `oss_cad_2026.md`)
Beat FreeCAD on **reliability/speed**, not feature count; keep a
Python API warm to fence off code-CAD; treat **2027-02-06** (Autodesk
price-lock expiry) as our marketing horizon — credible STEP-in/DXF-out
plus a "your file still opens in 2029" promise captures the refugee
wave FreeCAD historically churns back.

## 2026-10-07 late — Research-fleet synthesis (wave 2: the corpus lands)

Sixty report files, 84 of 100 topics resolved, and the capstone:
**`feature_gap_matrix.md`** — 840 parity cells across 12 domains, every
non-obvious one inline-cited with its [V]/[H] tag, plus 16 honest
**Tracer-BEATS**, a 34-item catch-up ranking (relevance ÷ effort), and
a 20-entry **never-list** that doubles as the anti-roadmap marketing
asset. The full grid lives in the research corpus; this is the build
consequence.

### Shipped since wave 1
- **M110 + M110.1** (`a2a6251`, `dad3e8f`): parts list + balloons,
  ISO 7573/6433, masses from published densities, body ▸ Material
  submenu — all paper furniture, never in the DXF.
- **M111** (`e4790a9`): the data-safety sweep, spec'd from the fleet's
  own file-menu research the same day — atomic saves, save=version
  sidecar (named points forever, non-destructive restore), rolling
  ×5 autosave with ghost-eating recovery, corrupted-file fallback,
  never-silent conflict guard, Revert to Saved. Suite now 1140.
- Side quest (`e88d3f8`, `00bcb2c`): one-easy-launch — install-linux.sh
  puts `tracer` on PATH, adds the app-grid entry, and binds `.tracer`
  files to double-click; `main()` opens a document argument; clean-room
  QPainter icon; LF-pinned shell scripts keep Windows CI honest.
- **M112** (this wave): the theme-token sweep — HIG darkBlue surfaces,
  autodeskBlue accent, the peach hover / blue select / amber ghost in
  the renderer (canvas follows the chrome), sketch states on their
  public semantics (white-constrained, violet projected, green dims,
  blue HUD), view cube + drawing sheet tokenised, one generated QSS
  with SP-rhythm sizes, styled inputs/tooltips and blue list
  selection. "No UI module spells a colour" is pinned by test_m112.
  Suite now 1159.
- **M113**: the key layer + command search — S// opens a fuzzy toolbox
  fed live from the menu tree (104 commands, self-searchable),
  commands.MODEL_KEYS is the one keyboard truth, and the sketch canvas
  claims its alphabet via shortcut override while model keys bubble to
  the window. Fusion-owned keys now behave as Fusion [V]: E extrude,
  F fillet, H hole, M move, A appearance, V visibility, F6 fit,
  Enter finish, X construction, T trim, O offset, P project, Ctrl+B
  compute, Ctrl+4-7 styles, Ctrl+Alt layout layers. Also fixes a real
  latent bug: window-scoped menu shortcuts used to steal keys from the
  sketch editor. Suite now 1171.
- **M114**: Limits & Fits on paper — `core/fits.py` carries the
  ISO 286 maker slice as pure data (IT5-IT9 to Ø120, holes H, shafts
  h g k n p, fine deviation bands so Ø25 g6 differs from Ø30 g6) and
  every published anchor reproduces to the micron; a Fit tool (or **F**
  on the sheet — the drawing now answers D/B/F/Esc) clicks a dimension
  bubble into "Ø40.00 H7 (+0.025/0)" per ISO 129; fit pairs analyse
  clearance/transition/interference; the model and the DXF stay
  nominal — paper carries the fit. Suite now 1182.
- **M115**: 3MF speaks. The audit of trimesh's writer found valid bytes
  but no voice — zero document metadata, colours and materials lost,
  six namespaces re-declared per build item — so the format now leaves
  through `core/threemf.py`: pure stdlib, Core-1.4 exact (the
  translation-LAST transform trap pinned by test, explicit
  unit="millimeter", metadata→resources→build order, `<base>` with
  both required attrs), carrying provenance (Title/Designer/Application/
  CreationDate), painted bodies as real slicer colour slots
  (basematerials, deduped, sRGB #RRGGBBAA), BOM materials as
  tracer:-prefixed metadata, part labels, and the whole build grounded
  on the plate without touching a vertex. STL/OBJ/PLY keep the trimesh
  road untouched. Suite now 1197.
- **M116**: the crowned module — `core/topology.py` reads a triangulated
  Solid the way a designer names it: union-find face groups (box 6,
  cylinder 2 planes + 1 tube), crease-walked semantic edges between
  corners (box exactly 12, a cylinder rim ONE closed loop whose length
  tracks 2πr inside 1%), planarity verdicts per group, and the cone's
  float-noise apex slivers dismissed rather than shredded (the
  256-facet trap, pinned by test). Cached on the immutable Solid;
  face-pair → edge-token lookup ready for the fillet dialog — one
  classifier for selection kinds, crossing windows and drawing-line
  quality. Suite now 1206.
- **M117**: the measure win-pack — Mass Properties grows the numbers
  Fusion's dialog never shows (extents + principal inertia about the
  COG, tensor-by-tetrahedra, cube/cylinder/sphere pinned to textbook
  values); Tools ▸ Show Extents reads the honest bounding box; and a
  Section view now speaks cut area, wetted perimeter, hole count and
  centroid (shoelace with nesting-depth holes — Fusion's Section
  Analysis has NO properties readout [—V], so every line is a beat).
  Suite now 1220.

### Corrections wave 2 bought us
- **Fusion HAS a 3D sketch mode now** (triad, per-point plane
  switching) but with zero 3D dimensions — our planar-only solver is
  parity, not gap (`sketch_3d.md`). Spatial mode joins the never-list.
- **No selection filter bar exists** in Fusion — tool-declared
  receptivity is the model; the crown went to **one feature-edge
  classifier module** (`selection_filter.md` + `hlr.md`) that feeds
  drawings, 3D selection, face appearance AND fillet re-identity.
- **QAT / Ctrl+F1 lore busted** (undocumented; "Add or Remove Buttons"
  was Inventor vocabulary) — our compact-ribbon toggle is ours by
  right (`ui_ribbon.md`).
- **Autodesk REMOVED thickness analysis**, and their sections expose
  zero properties — the measure/analyze gap-swipe is free wins
  (`ui_measure_tool.md`).
- Colour priority chain settled (appearance override > physical >
  default, occurrence-only) — M112+ appearance work inherits it
  (`ui_appearance_panel.md`).
- Positioning line, keeper-grade: *"Onshape's free tier costs your
  privacy; Tracer's history lives in a file you own."*

### Ranked queue v2 (matrix-informed; supersession noted)
*Shipped since this ranking: M112 theme tokens (test_m112, suite
1159); M113 key layer + command search (test_m113, suite 1171 — the
matrix's #1 gap is CLOSED); M114 ISO 286 fit callouts (test_m114,
suite 1182 — matrix rank 2 closed, drawing keys D/B/F/Esc shipped with
it); M115 native 3MF (test_m115, suite 1197 — rank 3 closed, the
writer audit's four gaps fixed); M116 the topology classifier
(test_m116, suite 1206 — the fillet/selection/HLR unblocker lands);
M117 measure win-pack (test_m117, suite 1220 — ranks 11+12 closed,
inertia/extents/section properties shipped); M118 Message Log (test_m118,
suite 1236 — rank 6's item jumped the queue: failures now NAME their
feature, the timeline badges it red, and a log double-click selects it —
the deep-link Fusion's docs never shipped); M119 degrees-of-freedom
overlay (test_m119, suite 1244 — the kernel report's verified beat:
null-space analysis projected per point, crosses and slide-arrows on
the canvas, the view Fusion's forums begged for); M120 object snaps +
live auto-constrain (test_m120, suite 1258 — core/snaps.py typed
candidates with tiered resolution, drop-time binds as first-class
constraints, typed glyphs + Alt-suppress; the snap_geometry.md beat
shipped); M121 interlock family (test_m121, suite
1278 — Boss · Snap fit · Rest · Lip, Fusion's Plastic-extension family
shipped FREE, one interface-plane grammar, and the suite measures the
mated pair's interference volume to pin the zero); M122 assembly phase 1
— interference solids (test_m122, suite 1287 — jumped from the tail per
wave-3 rank (a), "the natural opener": the clash becomes a live BODY
that re-solves on recompute, kinematic placement included — what Fusion's
throwaway InterferenceResults can never be); M123 fastener library with
PROVENANCE (test_m123, suite 1301 — data/*.json tables each stamped with
standard + edition + sources + verified date; Hole dialog names its
sources live; the CI validator cross-checks neighbours — washer ID ==
ISO 273 close — and the sweep it enabled corrected 7 clearance cells);
M124 print fit-mode (test_m124, suite 1311 — δ at the export boundary:
hole radii rewritten parametrically inside a context manager, analytic
to the micron, document never touched; δ=0 default + label-only mode
speaks the sourced deviations; morphological ball-offsets PROVED
unable to move hole walls and dropped from the plan before shipping).
The live queue starts at
M125; items 1-11 below are history.*
1. **M112 — theme tokens** (`ui/theme.py` + single QSS: darkBlue
   surfaces, autodeskBlue accent, hover/select trio; no-px rule from
   `a11y_precision_cad.md`). [matrix rank 5]
2. **M113 — key layer + command search**: verified single-keys,
   **S + / search** (matrix's #1 gap overall), Ctrl+Alt layers,
   drawing keys incl. B=balloon. [ranks 1 + 4]
3. **M114 — Limits & Fits callouts** — `core/fits.py` over the
   transcribed ISO 286 tables; ± and fit rendering per ISO 129.
   [rank 2; model stays nominal — `tolerance_modeling.md`]
4. **M115 — 3MF print-ready export** — stdlib zipfile+xml writer,
   zero new deps, per-body names/materials, print checks. [rank 3]
5. **M116 — `core/topology.py`**: the crowned module — crease-edge
   graph + union-find face grouping per solid. Unblocks edge tokens
   in fillet dialogs, face-level appearance, crossing-window
   classification, 3D face snap, fillet re-bind identity. [rank 27's
   blocker; `selection_filter.md` action 1]
6. **M117 — measure win-pack + section properties** (multi-measure,
   Show-Extents, physical-props dialog, shoelace section
   area/perimeter/centroid — "strongest single differentiator").
   [ranks 11 + 12]
7. **M118 — message log + timeline status glyphs + click-to-select**
   (shipped as the log's debut: Qt-free bus in `core/logservice.py`,
   panel with filter/Copy/Save/Clear, dedupe-at-tail, session chip —
   out of rank order because every later failure-UX milestone stands
   on it). [was rank 6's item]
8. **M119 — degrees-of-freedom overlay** (shipped in planegcs's slot —
   the DOF projection needed no C++ and demos against Fusion today;
   the embed it displaced folds into M120, the milestone whose UX it
   serves). [was rank 9's item; `fusion_kernel_architecture` §3]
9. **M120 — sketch muscle** (shipped in part): object snaps +
   **auto-constrain-on-drop live and free** landed; the **planegcs
   embed** this item also carried is now OPTIONAL (lane-B audit:
   FreeCAD/planegcs repo is a phantom, PyPI wheels skip our Py 3.14,
   dev box lacks cmake/Eigen/Boost) — the pure-Python LM stays the
   shipping engine; embed ships later as an optional accelerator
   behind the solver iface. 2D spline + `core/spline3d.py` (3D-path
   sweep) remain here, renumbered into M121+. [rank 15 + 9 +
   `snap_geometry.md` + `planegcs_embeddability.md`]
10. **M121 — interlock family** (Snap Fit/Boss/Rest/Lip + Emboss
    text via QRawFont — zero new deps). [ranks 7 + 24]
11. **M124 — print fit-mode** (parametric δ at export). [rank 8]
    SHIPPED (v1). Research (`print_fit_mode.md`) settled the design; a
    live test then CORRECTED two of its proposals: (a) a full-solid
    ball offset (`minkowski_sum/difference`) was proven unable to grow
    a hole — morphology can't move a wall larger than the ball, it only
    rounds rims (genus even dropped 1→0 on a Ø10 hole). So v1 rewrites
    the parametric HOLE radius inside a context manager instead
    (analytic to the micron, document restored byte-for-byte, refuses
    holes under 2δ, skips threads/pins honestly). (b) the change-log
    went to the message log, not 3MF metadata (deferred). δ defaults 0
    with label-only mode speaking the sourced deviations; the
    double-compensation + SuperSlicer-inverted-sign trap is surfaced in
    the 3D Print dialog. Deferred to M125+: per-material δ presets,
    3MF metadata, pin −δ and planar elephant-foot compensation.
12. **M125 — construction-geo batch** [from `fusion_construction_geo.md`,
    probed + repo-grounded 2026-10-07]. (v1) SHIPPED — all five scope
    items in three gated commits (1/3 store, 2/3 transforms, 3/3
    errors): (1) named DATUM store under the browser Construction
    bulb — planes+axes share one name pool, key-agnostic persistence,
    legacy files load clean; (2) plane methods offset / At-Angle
    (hinge u|v through a point) / Three-Point / Midplane — pure frame
    algebra, non-parallel refused honestly; (3) axis methods Two-Point
    / Two-Plane (closest-point solve); (4) circular patterns pivot
    about ANY named axis (Rodrigues about the datum line; "+Z through
    center" stays the dialog default so legacy docs recompute
    identically), mirrors sweep across any construction plane
    (frame-aware reflection); (5) datum-aware errors — resolvers name
    the missing datum AND its cure, deleting a referenced datum warns
    listing dependents (core datum_references), and proceed-then-fail
    lands on the M118 badge: my own test caught a raw-exception crash
    here (the deleter's viewport.refresh recomputed outside the safe
    wrapper), fixed by routing deleters through recompute().
    DEFER (expensive without B-rep face identity): To-Object,
    mesh-plane-fit midplane (ours splits two PLANES), tangent /
    perpendicular-at-point on curved faces, along-path, UCS,
    pattern/mirror OF construction geo, proximity re-matching,
    sketch-plane re-host (sketches carry a frozen frame copy —
    reselect beats fake healing, as in Fusion). Grammar still open:
    dashed datum edges and renderer-side name labels (datums ship in
    the construction colour, solid).
13. **M126 — transform-lattice batch: geometric pattern + scale**
    [from wave-4 `coil_geometric_pattern.md`, disk-verified 72l/1534w].
    (v1) SHIPPED — pattern + scale landed as one vertical slice
    (suite 1355): two-direction (T·R·S)^i lattice with NAMED rails and
    pivot through the M125 store, base-anchored scale with negative
    mirror, Change Parameters unit-free for factors, datum_references
    extended so lattice bindings join the delete warning. A live test
    caught a real reload bug mid-build (from_dict silently defaulted
    n2/t2 when the branch was retyped — now pinned with non-defaults).
    coil-v1 RE-RANKED as M127 (2–3×; ring-loft reuses the loft engine
    + this PR's transform util). M127 SINCE SHIPPED: coil.py lofted
    ring-chain about a named axis, circular/square on-center sections,
    hand + pitch-swallow guards, Pappus-pinned volumes, bolt/spring
    dialog, suite 1367. Still deferred: taper, Spiral type, Inside/
    Outside section positioning, runout ends, internal modeled
    threads (cosmetic-thread wedge M128+). DEFER: feature-level patterns,
    boundary/fill patterns, spiral-type coil, internal modeled
    threads (cosmetic-thread story later with drawings). COSMETIC
    WEDGE SHIPPED (M128, rung a, suite 1379): holes carry ISO
    designations (coarse-pitch-omitted grammar, 6H/6g defaults —
    codes, so no new data table for the M123 validator to police),
    a Cosmetic mode drills only the tap-drill core, and the major-Ø
    decal ring rides the datum line buffer. Modeled groove stays the
    legacy default. Rung (b), section-triggered drawing callouts,
    joins the drawings tail next. HOLE NOTES SHIPPED (M129, rung b
    wedge, suite 1389): the sheet carries a metadata-derived hole
    table (grouped+counted, THRU, tap-drill column, cbore notes) and
    per-hole centreline crosses + item bubbles in the bore-facing
    view; default-ON layer with the sheet's hole_notes flag, paper-
    only like the BOM. Rung (b) honest-now: notes ride the TABLE, no
    section needed; a SECTION-triggered view of threaded holes joins
    rung (a)'s mesh-cap upgrade in the drawings tail.
    Next in rank, both fully probed: browser
    polish (in-place rename + "(1)" suffix, tree↔canvas cross-
    highlight, isolate/show-all — ladder in `browser_conventions.md`),
    then nav (quaternion named views, turntable + Shift+MBB re-pivot,
    direction-encoded marquee, 4-wedge hold-wheel — ladder in
    `marking_wheel_nav.md`); zoom-to-selection is an UPSTREAM gap
    (requested since 2015, unimplemented) — cheap ours-first
    differentiator when nav lands. LADDER RUNG ONE SHIPPED (M130,
    suite 1400): rename became a RELINK — datums got context-menu
    Rename that rewrites every name-bound mirror/coil/pattern field
    atomically (counted in the status line), collisions REFUSE with
    the cure (Fusion's auto-"(1)" would lie for a name-resolved
    kernel), duplicate feature names wear "(1) (2)" in the browser
    as display only. Deferred from the rung: Explorer delayed-
    double-click in-place edit (double-click is ours = open editor;
    a click-pause-click timing layer wants its own milestone), and
    body/sheet-row rename. CROSS-HIGHLIGHT SHIPPED (M131, suite 1408):
    the ladder's defining rung — body/feature rows wash their body in
    the viewport via stitch-order face ranges (display_ranges), picks
    resolve majority-body and light the row (signals blocked: no
    bounce-back), datum rows re-centre the orbit; the wash is visual
    — _sel never grows from a row click.
    ISOLATE/SHOW-ALL SHIPPED (M134, suite 1441): the ladder's
    visibility rung, built to the wave-8a law by CONSTRUCTION —
    isolation is a stacked (scope, boosted) overlay that never writes
    eye state, so unisolate restores the pre-isolate world exactly
    (hidden-before come back hidden; boosting shows an isolated
    hidden row while its bulb stays OFF). Show All ships as the
    SEPARATE lossy verb (force-every-bulb-on recovery; the vendor's
    conflation is the confusion we refuse). Esc pops one level after
    gestures/selection yield; the root row carries the always-findable
    exits (Fusion's documented annoyance: leaving required finding the
    isolated row); re-isolate narrows by AND; isolation is session
    state, absent from the save file. Browser tail now: in-place
    click-pause edit, body/sheet-row rename (WHEN rename lands,
    isolation scopes MUST relink — M130 doctrine).
    NAV LADDER RUNG ONE SHIPPED (M132, suite 1422): the 4-wedge
    hold-wheel — RMB still ≥200 ms blooms Undo/Extrude/Sketch/Move at
    the cursor (guarded ribbon verbs under the vendor's quadrant
    themes); release-on-wedge fires, hub/void/Esc dismisses, tap still
    menus, drag still orbits — the three coexistences each pinned. The
    ring is viewport-painted overlay state, not a top-level window:
    deterministic grabs in CI, capturable in proof shots, and a pixel
    test pins hover-fill to the wedge its label names (a one-quadrant
    start-angle slip passes every pick test and lies on screen).
    SHIFT+MMB RE-PIVOT SHIPPED (M133, suite 1430): the probe's
    contract, built as written — modifiers sampled AT press (late
    changes are nothing: the latching trap pinned), hit pivots / miss
    pans (the binding splits on geometry, pan never stolen), the
    pivot IS the camera target so the sticky-centre pathology is
    structurally impossible, Home doubles as Reset Orbit Center, and
    the pivot dot rides dead centre by construction. An off-centre
    pixel test replaced a trivially-passing one. Nav tail: settable
    home, sketch-context wheel ring.
    SECTION VIEW SHIPPED (M135, suite 1451): the wave-9 probe,
    live-tested before a line shipped — trimesh 5.1.1 slice_plane
    (cap=True) watertight-caps through the manifold3d engine already
    in the venv (plate+bore sliced through the bore axis: 78 cap
    faces, all accent, volume 3364.4 vs analytic 3364.38). Geometry
    cost: ZERO. The milestone is honest wiring: per-body slices
    restitched browser-order (isolation still rules), the cut face
    accent-shaded (vendor default), picks/hover/press-pull/sketch-
    face/re-pivot suspended at one choke while cut (mesh identity is
    the model's), the plane bound BY NAME so M130's rename relinks
    the living cut (+1 in the counted relink), flip/or other half,
    Esc's ladder = gestures → cut → selection → isolation, and
    session state absent from the save file. Origin-plane rows got a
    menu at last (section yes, rename/delete no — not ours to kill).
    Drawings rung (a)'s PAPER side (hatched section views) followed
    one milestone later as M136 — and NOT by the predicted cap-hatch
    in the plane's 2D frame: the queue's own archaeology found M102's
    half-solids/cap-loops/page-hatch already in stock. Cosmetic
    backlog: grazing-angle zebra on
    coplanar boolean rims (predates M135 — control shot proved it;
    candidate: polygon-offset or coplanar merge in the renderer).
    PAPER SECTION RUNG ONE SHIPPED (M136, suite 1463): the cutting
    line drawn ON a view — two clicks on top/front/right stand a
    dash-dot line (thick caps, arrows toward the kept side, letter
    at both ends); the child A-A lands middle-band, hatched, live.
    Wave-10a priced the rung ~950 LOC; the truth was grammar-only:
    plane_from_line (line -> plane; the classic drag across the TOP
    view drops the arrow to the FRONT, volume-exact), section_on
    (child = BASIS TUPLE the whole pipeline already carries — HLR,
    hidden ink, nudge, scale, DXF: zero consumer changes),
    section_letter (reserved-letter alphabet, no I O Q S X Z; one
    registry for dialog and line), Shift flips the kept side, Esc
    rung one erases the half-line (the ladder lives in
    _stand_down_drawing — the sheet's Esc is a QShortcut, so a
    canvas keyPress handler would have been dead code). Banked
    lessons: a new _p2m instance method SHADOWED the classmethod of
    the same name (m94/m100 bled, the batch SEGFAULTED — the
    adjacent suite caught it in seconds; grep the class before
    naming a member); and union truth — a fused plate+stud yields
    TWO cap loops at the bore split, the stud's wound joined the
    plate's loop as one ten-sided polygon, not three regions.
    RUNG TWO SHIPPED (M137, suite 1474): the section's own props —
    double-click the child and its dialog answers with the vendor's
    tri-modal DEPTH (Full | Slice = the wound alone | Distance slab),
    the kept side, hidden lines and the per-view scale. The ASME law
    that sections omit hidden lines became the DEFAULT via one
    _hidden_off() set gating paint, hidden_views and hidden_page
    (opt-back-in per entry; a slice never opts — no depth to hide
    behind). Slice costs nothing: the cap loops ARE chains in the
    child's page basis — place/hatch/measure/export needed zero
    changes for the mode with no solid (the basis-tuple decision
    paying rent). The thread-crest hatch rule (ISO 6410-1 3.2.4)
    needed NO code: our bores are geometric, hatch stops at the real
    wall — the rule only bites products faking threads as decals
    (banked verdict, not a skipped rung). Cache keys grew mode+dist
    the day the modes shipped (test_modes_cache_apart pins it). One
    golden moved honestly: m102's DXF count had been counting the
    section's hidden ink — fixed by making the opt-in EXPLICIT in
    the test, not by loosening the assert. Still queued on this
    rung: hatch avoids annotations.
    RUNG THREEa SHIPPED (M138, suite 1485): the JOGGED cutting
    polyline — legs that run on or turn SQUARE, the only family the
    standards admit (AutoCAD/SolidWorks/Onshape all enforce the bend
    by construction; wave-12a verified). The feared hinge rotation
    is the IDENTITY here: all cut planes stand perpendicular to the
    parent, so the orthographic child along the shared eye flattens
    the steps for free. plane_from_polyline decomposes the line into
    cut-runs with lateral ownership (advance-or-reject — no doubling
    back); section_jogged cuts each run's OWN plane inside its slab,
    unions the halves into ONE projectable solid and concatenates
    the cap loops across the hinge: place, hatch, measure, DXF, PNG,
    undo — zero consumer changes. The probe's verdict was
    LIVE-VERIFIED before a line shipped (caps abut exactly at the
    hinge, volumes analytic to the decimal). Tool: Alt sets a
    corner, double-click finishes; two plain clicks still stand a
    straight section byte for byte (M136 law intact, entry unchanged
    when no "pts"). The child's faint step seam is the union's REAL
    edge-on face — the fold-line convention by geometry, not added
    ink (LibreTexts' stricter no-line law noted). The 4-cap jog
    flushed a latent M117 bug: section_properties' centroid
    broadcast mixed weights at 2 loops and crashed at 3+; fixed
    rowwise, golden pinned. RUNG THREE-b SHIPPED (M139): the
    "Objects to Cut" picker — a checks field on the M137 props
    dialog, shown only when bodies>1, pre-ticked from the entry.
    The wave-13 law held to the letter: exclusion rides body NAMES
    as "exclude" on the entry, and unchecked bodies are ADDED BACK
    WHOLE and unhatched behind the cut (ASME standard-parts look;
    the naive body-minus-excluded filter is SILENT DELETION,
    live-tested pre-build). Stale names inert; cutting nothing
    refused BEFORE the undo capture; works on line, jog and
    legacy-axis entries; slice mode honestly omits (no depth to
    stand a whole body in); jog+exclude composes. Fastener
    auto-detect stays deferred loudly — no library, nothing to
    detect. Still queued on this rung: hatch avoids annotations.
    The gate also flushed M139a: the occlusion sweep asked EVERY
    front triangle about EVERY edge midpoint — a tapped plate's
    sheet (41,766 triangles) took 91 s to draw and the suite rode
    the 180 s timeout; 2D bbox binning made identical ink 8.1 s
    (pre-fix baseline diffed byte-for-byte; golden pinned).
- **SKETCH-ON-FACE RUNG A SHIPPED (M140)** — the user complaint
  "you can't sketch on an already extruded surface" researched to
  a 162-line probe (vendor help + FreeCAD AttachmentEngine + our
  code, hypotheses falsified along the way: the face's edges DO
  auto-project there; the vendor refuses curved faces too — tangent
  planes answer them). The rung ships the geometry of trust: the
  pick's frame is DERIVED, never clicked — origin = the host body's
  anchor projected onto the face (same face, same frame, whatever
  the cursor touched), axes by a nearest-axis law with an owner
  seed for exact ties; the pick carries the BODY (M131's stitched
  range map read backwards — the triangle index was already in
  hand and thrown away); sketches are named "Sketch on <body>";
  a refused face answers with a SENTENCE (state, not silence — the
  silent 2-degree shrug was the complaint verbatim); the RMB quick
  menu leads with "Sketch on Face — <body>" (the vendor's
  discoverable route, ~15 lines of highest UX payback); and the
  extrude PRESET probes the contact — air ahead & material behind
  joins (the old law, now chosen not assumed), material both sides
  cuts (the pocket intent is first-class), normal dove inward
  mirrors the frame (press-pull's trick) — with an empty first-body
  document guarded to join. The gate caught the datum-sketch-on-
  empty-doc crash and the m8-era API law-change honestly (tests
  cite the new law, assertions strengthened not loosened).
  Deferred loudly per probe: B-lite the loop lands (SHIPPED as
  M141, the record below),
  C follow-at-recompute (FaceHandle rides the placement layer),
  D health/recovery; cylindrical unwraps: never (the vendor
  refuses too).
- **SKETCH-ON-FACE RUNG B-LITE SHIPPED (M141)** — the vendor law
  the probe live-verified: face edges auto-project the moment the
  sketch OPENS. Not the plane-slice (project() answers "what
  stands at this height" — it catches the boss the face merely
  hosts a) but the HOST FACE's own loop: the picked triangle's
  coplanar-ADJACENCY group (M59's union-find keeps disjoint
  coplanar faces separate — the plate-top loop is the plate's, not
  the world's), validated by face_region (outer + its holes —
  a bored face speaks its bore), mapped into the DERIVED frame so
  a bore at world (30,20) is truthfully (30,20) in sketch
  coordinates. Construction-but-dimensionable refs (M82 machinery:
  drawn, magnetic, serialized, undo-safe); REPLACED never stacked
  (the P key re-includes the full slice, M82 law intact, and the
  grazing-offset truth — a hair above the plate it finds the boss
  section, which is what a slice honestly means). The pick chain
  finally consumes the triangle index M140 stopped throwing away:
  probe -> tri -> _group -> face_region -> refs; face_picked grew
  a fourth voice (body, tri — arity cited where the m140 gate
  moved). Plane sketches stay unprojected (opt-in project kept);
  a group face_region refuses lands NO loop and says nothing false.
- **SKETCH-ON-FACE RUNG C-CORE SHIPPED (M142)** — attachment that
  survives recompute, built the way the mesh kernel can honour it:
  a semantic FaceHandle {"feature", "part"} — NOT a mesh search.
  Features PUBLISH their cap planes algebraically (extrude caps =
  placement and placement + h·n through the real plane_matrix, box
  caps the z faces of dims, cylinder caps ±height, placement
  honoured), so resolution is arithmetic at CURRENT parameters:
  grow the plate, the boss RODE (golden 7600→12400, boss bottom
  z=10), a handled pocket follows AND keeps its cut side (u-mirror
  preserved — press-pull's law; the pocket's sketch x runs negative
  to land inside the plate — pinned by a test that first fell to
  its own assumption), and the fold DERIVES without rewriting:
  the committed record keeps placement z=6 (history honest; the
  vendor's file stores the relationship, not the moved numbers).
  Unresolvable (feature gone/never published/acc empty) keeps the
  FROZEN frame — the vendor's cache law read straight from its
  error text ("Cache is used"), freeze never blank; the healthy/
  unhealthy BADGE is rung D. plane_frame's voice kept: refusal
  names the guilty feature and the cure. Newest-publisher-wins
  attribution (a fresh cap shadows the face it grew from — the
  face the user saw). Revolve/split inherit no handle yet (named),
  datum on-face + tangent handles are the queued continuation
  (add_plane gains method:"on-face" deriving THROUGH the handle),
  revolve publish next. No-handle docs byte-identical (1522).
- **PUBLISH PDF SHIPPED (M143)** — the whole drawing set as ONE
  vector PDF (vendor bundle law: many sheets, one filename chosen
  once, order = creation order), built the way the executed spike
  pinned it: NOT a forked paper-painter but the SAME paintPage run
  against a DEVICE SWAP — shadow width/height/rect, _zoom =
  dpi/25.4, _center at the sheet centre — so every mm coefficient
  the screen already carries lands as physical paper ink (print px
  floors go inert; the pt clamps are fine because a pt ON PAPER is
  physical). The writer's factory defaults (A4 portrait, 10 mm
  margins, SILENT crop — reproduced pixel-wise) get no vote: an
  explicit QPageLayout(size, Landscape, zero margins) per sheet,
  BEFORE its paint; the test publishes at 150 AND 300 dpi and pins
  identical MediaBoxes (1191×842 ±1.5 — Qt rounds). One painter
  across the bundle; PySide6 puts newPage on the DEVICE (painter's
  is unexported) and QPdfWriter finalises on destruction (no
  close()); load-side asserts go through QtPdf itself — zero new
  dependencies (contract §7's audit: pypdf addable but unneeded).
  The page is a VIEW, so print mode fills paper edge-to-edge (no
  desk grey, no dark 1-px ring — the ring the probe measured at
  #14161a), the three frame pens gain true 0.35 mm ink and the
  one cosmetic pen 0.18 (the _w() helper's whole remit — the
  self-healing max(floor, mm·zoom) strokes were left ALONE, honest
  to §8), and the per-sheet sheet_idx repoint makes every title
  block say its own "n / N". The swap is a LOAN: sheet state,
  zoom, centre, _printing and the in-progress tool's ghosts are
  stashed and returned (publish mid-section and your rubber band
  is waiting when it finishes — pinned by spy). Selectable text
  proven via getAllText (ToUnicode rides for free); the refusal
  without sheets precedes the dialog. Continuations named: sheet
  SCOPES (Current/Selected/Range — v1 is All, honestly), PDF/A
  output-intent, the ISO 5457 frame, DWG stays refused in-product
  (§6: LibreDWG's own README admits R2010-writer pain — our
  baseline; the "open the DXF in a DWG tool" cure is documented).
  (1530.)
- **GD&T RUNG 1 SHIPPED (M144)** — the feature control frame,
  hosted by dimensions (the probe's §4 verdict: the FCF is a dim
  property — model-space anchors make travel free). SIX controls
  (straightness/flatness/circularity/cylindricity/perpendicularity/
  position) with PAINTED glyphs — the machine-verified fact that
  the whole Unicode GD&T block is TOFU on real paper fonts makes
  vector coordinates the only honest ink; core/gdt.py ships the
  §1 unit-box specs (Wikimedia PD SVGs confirmed numerically) +
  the §2 CONTROL_TABLE (ISO 1101:2012 Table doctrine + ASME
  Y14.5-2018 6.4 compartment grammar, fetched text). Validator is
  the ONE choke (fits.callout's voice — raises NAMING the broken
  law, dialog undo-pops + warns): ⌀ illegal on form controls,
  spherical S⌀ only for location, M/L per Table, datum arity
  (form 0, perpendicularity ≥1, position 0-3 with a 0-datum
  WARN), separate compartments per datum (6.4.3 — the vendor's
  "|B C|" stack is NOT ASME; the ISO COMMON datum A-B is the one
  legitimate shared cell), reserved letters imported from the
  M136 section registry — SAME OBJECT (gdt.RESERVED_LETTERS is
  drawing.RESERVED_LETTERS), one alphabet, two users. The frame:
  [_gdt_cells_widths = one source for painter AND gate (rect is
  always the sum)], 1.5·h_text box, host's own red pen (never
  overpowers its dim), stacked-list shape ("gdt" is a LIST so
  rung-2 ISO cl.6.4 stacking needs no re-shape — rung 1 writes
  length-1 honestly). Basic box = cl.11's "enclosed in a frame"
  drawn AT the knockout gap; a boxed dim refuses an ISO fit class
  (two tolerance voices, one truth). Editing mirrors the fit flow
  verbatim: G key / GD&T… button (five-way exclusion web grown,
  not re-nested), _dim_at hit, cmddialog ask, "— none —" pops the
  key. Paper-only proven: DXF line-art op count identical with
  frames + boxes on; save/load rides the shallow dict (plain JSON).
  ⌀ entered (U+2300) normalises to the printable letter Ø the
  repo owns (wave-11a: values are STRINGS — resolve_dims never
  touches a typed tolerance). Deferred loudly, each with reason in
  the contract: remaining 6 symbols (profile needs the (ADBEHIK)
  zone cells), Ⓜ arithmetic (needs size limits), Ⓟ projected zone,
  feature targets as first-class objects. (1564.)
- **SHEET METAL SM1 SHIPPED (M145)** — Tools > Flat Pattern: the
  blank as NUMBERS, computed by the shop law, never by unrolling
  facets. The reprobe ran every line against OUR kernel first
  (research/sheet_metal_reprobe.md), and the mesh itself corrected
  the contract's mental model twice, both facts now law in code +
  gate: (1) a kernel bend tessellates as TWO ribbon chains — outer
  chord strip (every hinge-adjacency radius = ro) and inner (= ri),
  all fold axes parallel — so a BEND is a PAIR of ribbons whose axis
  LINES coincide, not one chain (a chain walking THROUGH a tangent
  fuses multi-bend rings into garbage: the walk stops at flats
  2.5x larger than the facet it stands on, the trim sheds them);
  (2) the golden "flat 96.0947" was phrased to-apex while the
  probe's own builder legs are tangent-to-end — the true blank of
  that part is 100 + BA = 106.094690 (K=0.44), pinned re-derived,
  not swallowed. THE LAW: BA = theta_rad*(ri + K*t), neutral fibre
  off the INSIDE face; OSSB = tan(A/2)*(ri+t); BD = 2*OSSB - BA;
  K is a PROCESS constant — 0.44 default is industry folklore, no
  standard (ISO 12195 does not exist; never cited here). Why laws,
  not arcs: our band tessellation's neutral fibre is the
  mid-surface = K 0.5 BY CONSTRUCTION, +0.188 mm silent error per
  bend at K 0.44 — so the flat is SUM(leg extents) + SUM(BA), bend
  facets NEVER ship, and the gate's ORACLE is K=0.5 closing on the
  mesh's own mid-surface arc (106.283185). Leg pairing: canonical
  plane coordinates along +axis (normal sign folds INTO the offset,
  so antiparallel faces of one leg share the key), gap = t pairs,
  far offsets are PARALLEL LEGS; keys are order- and
  representative-independent so two bands naming a shared leg
  AGREE and the cycle guard never misses: a closed section is an
  honest RAISE ("a seam is a draughtsman's cut, not a feature the
  mesh can find"), mixed thickness in one chain refused, never
  averaged. UI is interference's shape: guard BEFORE the dialog
  (bendless body -> status, no K prompt), K double field (0.44
  default, 0<K<=1 enforced by the law itself), multiline report,
  status line. Detector soup-filter: constant adjR (+5%) and fit
  residual <10% R — the §2.3 OCCT chains (radii to 553 mm, resid
  27) die here; the angle reads the flange NORMAL pair (probe's
  span formula had a wraparound bug; normals never lie). SM2 =
  flat GEOMETRY on paper (outline is nearly planar: the §7 slab
  projects to exactly one closed chain); SM3 = parametric
  FlangeFeature owning band geometry (ends the detector fuzz,
  starts the relief conversation). (1578.)
- **ASSEMBLY RUNG 1 SHIPPED (M146)** — Tools > Joint - As-Built
  Rigid: the first rung of the assembly ladder, NO solver. LAW R:
  "a joint follows where a body is PLACED, not how it is BUILT"
  (§7.1 F2a). Body records mint ids (uuid4().hex[:8]) at creation
  and joints bind ids; the first body grounds itself (the vendor's
  own rule for the first component) and the flag rides the file;
  Document.joints is a file-level list of 7-field records {id,
  kind, a, b, m, a_home, note}. THE CONTEXT LAW (the suite's own
  pre-commit catch): the vendor's ground rule is an ASSEMBLY-context
  rule, so move_blocker INERTS the flag in a joint-free document —
  a single-body part moves exactly as M53 always allowed; auto-
  ground biting part-mode failed M53/M55 loudly first, which is
  what the full suite is for. Recompute re-applies
  P'_child = P'_parent @ m in topological order (parents first,
  list order only ties; a star is invariant to bodies order)
  AFTER the placement loop — one 4x4 multiply per jointed child,
  and the identity short-circuit is pinned: a joint-free doc
  never calls Solid.transformed at all. THE CORRECTION (second
  golden of this kind after SM1's 96.09): the contract's §7.1
  formula carried an extra factor, P'_child = P'_parent @
  inv(a_home) @ m — but m is the DELTA inv(P_A0) @ P_B0, so at
  creation the formula returns m, not P_B0: the child TELEPORTS
  whenever the base sat off identity. The spike ran green because
  EVERY pose in it was eye(4) — a law tested only at the identity
  is not tested. The gate's chain test lands the grandchild at
  its measured HOME with the base pose at (12,0,0): the buggy
  formula parks it at (-12,7,0) and the assert IS the correction.
  a_home rides the record as bake context; the re-apply never
  consumes it. What LAW R will not fake: a parametric (stream)
  edit to the base does NOT carry (§7.1 F2 — no per-body frame
  yet; rung 2's migration is priced, not invented), and the gate
  pins that too — the product wording ("where a body is PLACED")
  is the dialog's own title. Refusals loud: self-join, second
  parent, creation cycles (ancestor walk names the chain), and
  jointing an interference clash (F4 — the clash resolves inside
  the feature loop before any joint pass could tell it the parent
  moved; a lying clash body is REFUSED, not patched). A
  hand-edited cycle degrades to own placement and NAMES the
  offenders in doc.joint_warnings — never a crash mid-model.
  rename_body is M130's counted relink over the name ledger
  (features + InterferenceFeature body_a/b); the joint is NOT
  touched — it holds ids, so a rename cannot orphan it
  (byte-identical asserted). UI: browser gains Joints (n)
  (folder appears ONLY when joints exist — part browsers stay
  pixel-identical) with per-row Delete Joint (v1's edit is
  delete-and-recreate; the vendor's Edit Joint is the
  Position/Motion tabs we do not clone); body rows gain
  Ground/Unground (a file fact, refuses drags, rewrites no
  geometry); Move/Rotate refuse grounded and jointed bodies AT
  ARM TIME — the triad never appears, because a refused COMMIT
  leaves a half-dragged preview to explain (§5.4). move_body/
  rotate_body stay the permissive state-layer primitives (the
  choke is the gesture, and jointed children's own placements
  are silently subsumed by the bake — the UI refuses before the
  kernel ever has to argue). As-Built != vendor Joint: we pick
  no geometry and teleport nothing at creation, and the dialog
  title says the honest name. Rung 2 named, not silently
  deferred: per-body frames (b["frame"]) + param-follows-motion;
  joint origins (the vendor's Joint with capture); occurrence
  layer (the vendor binds occurrences — we bind bodies, stated
  in §3.4's deviation note). (1592.)
- Tail (queued by matrix order, unnumbered): single-HTML
  share viewer, STEP `[step]` OCP extra, per-config BOM-diff, drawings
  quick set, version-diff
  overlay, LOD + GPU picking,
  prefs two-pane (re-verify landing), `tracer merge3`, DXF curve-fit,
  exact HLR, truss sim-lite.

### Wave-1 research addendum (2026-10-07; six reports, ~27.5k words)

`fusion_kernel_architecture.md`, `fusion_command_anatomy.md`,
`fusion_large_assembly.md`, `ui_icons.md`, `ui_navcube.md` (+ its
`ui_navcube_cloning_checklist.md`). Landed in `/tmp/opencode/research/`.
Corrections that reshape the queue:

- **Fusion's scale answer is "don't compute", and it has NO
  per-component load tiers.** Fusion's own Sept-2026 notes ship "an
  automatic **mesh-assisted fallback** for Boolean operations that
  cannot be resolved" — the exact-geometry kernel really does fail, and
  the vendor degrades to mesh. SolidWorks has Lightweight/SpeedPak;
  Fusion has nothing per-component. → **Tracer differentiator: per-body
  load tiers (Full / Graphics-only / Suppressed) as a first-class
  browser feature.** A cleaner beat than anything in v2's tail; promote
  above "browser polish".
- **Kill the persistent-topological-naming problem with *selectors*,
  not stored IDs** (Rule Fillet pattern: "all concave edges of feature
  X", re-evaluated each rebuild). Our M116 `core/topology.py` is the
  substrate — this is its intended payoff, and how the fillet dialog
  should bind edges. Fold into the fillet-rebind work (matrix rank 27
  continuation), tag [M].
- **`Placement ≠ Feature` from day one.** Component moves are kinematic
  (no timeline feature) until an explicit `CapturePosition`; body moves
  are parametric. Retrofitting this separation into the tree is brutal
  — encode it as a dataclass boundary now, before assembly phase 1.
  [S, architecture]
- **Error-vs-Warning is kernel-derived, and we can beat the honesty.**
  Fusion: a *geometry* reference failure → yellow warn (replay cached
  mesh); a *topology* reference failure → red error (blocks + propagates
  to dependents). M118 already names the guilty feature; next step is
  the two-tier severity + dependent-propagation, surfaced *proactively*
  (Fusion hides errors behind the rollback bar — a documented footgun).
  [M; extends M118]
- **View orientation is settled enough to build.** Our mini-triad is
  additive (Fusion has no bottom-left widget — confirmed absent);
  defaults ARE the docs (MMB=pan, Shift+MMB=orbit; the "MMB=orbit"
  memory is the SolidWorks preset); F5–F8 do not exist; FOV ≈22.6°
  [community-converged]. Build the ViewCube straight from the
  cloning-checklist file (13 sections, 12 acceptance tests). [M, nav]
- **Icon set v2 = clone the *grammar*, restyle the art.** The real
  Fusion icons are enumerable from a public help CDN (a digger pulled
  120 + montages) but those files are **quarantined — Chinese wall**:
  artists work from this text only. Semantic code to clone: blue dots =
  defining handles, red = constraints/locks, orange dash-dot =
  construction, white = reference, blue = result, yellow sparkle = auto.
  Corrected pictograms: Extrude = blue prism on a white plate (no
  arrow); Revolve = profile + dash-dot axis (no arc). [S–M, art task]
- **DOF overlay is Fusion's #1 documented user gap** (forums begging
  for "show all degrees of freedom"/"find missing constraints"). We
  already have per-entity DOF count — an overlay + "highlight free
  DOFs" button demos against Fusion the same week. Fold into M119
  planegcs work (the solver iface we're embedding already computes it).
  [M; verified beat]
- **The 2025 "unified UI" refresh is a chrome retheme**, not a glyph
  redraw (same-image colour variants) — our M112 token approach was the
  right call and needs no icon re-do to "match 2025". [confirms v2]

Queue impact: the DOF overlay shipped first as M119 (pure Python —
it needed no C++ and demos today); planegcs embed folded into M120,
the sketch-muscle milestone whose UX it serves. Load-tiers and the
selector-based fillet re-bind are the two new items for the next
re-rank; nothing shipped is invalidated, and three beats (load tiers,
DOF overlay, reliability wedge) gained hard citations.

### Wave-2 research addendum (2026-10-07; two engine autopsies, ~13k words)

`fusion_drawing_engine.md` (7423 w, ~35 cloudhelp pages walked by GUID
+ 2 AU handouts) and `fusion_sheetmetal_engine.md` (5651 w, 68 cites,
AU PDFs cached in `/tmp/opencode/research/pdfs/`).

- **A drawing stores a design REFERENCE at a VERSION, not geometry** —
  views re-harvest on Update. And the workspace is reportedly built on
  the AutoCAD core; the smoking gun is Autodesk's own export page:
  "AutoCAD DWG" emits every sheet as **paperspace-only Layouts with an
  empty model space** — one fact explains the whole blank-DWG complaint
  genre. Our paperspace-free drawing design is a *validated
  counter-position*, market it as such. [confirms v2 drawings plan]
- **Title-block "fields don't update" is documented behaviour**: only
  Paper Size + Sheet Number ever re-update; Drawing Scale is a
  one-time capture of the FIRST view placed. Ours derives scale/size
  at draw time (M108) — already better; when drawings v2 ships, make
  every field live and say so in the release note. [S, marketing edge]
- **Export de-association is POLICY** ("Dimensions are no longer
  associative" — their page), DXF got real splines only May-2026,
  lineweights still aren't exported, dims lie at scale ≠ 1:1. The
  report's **T1–T13 fidelity taxonomy is our exporter's acceptance
  checklist** — adopt as tests when STEP/DXF export work lands. [M]
- **Fusion has NO bend table.** The sheet-metal "rule" is a flat
  material×thickness record (6 generic ones ship), bend DEDUCTION is
  not enterable (staff: "calculate backwards and come up with a
  K-Factor"). But the rule fields are **expressions of thickness**
  (`relief depth = t*0.5`) — steal that mechanic; it is free for us
  since expressions already live in our dimension layer. [S]
- **Two flatteners, two contracts**: Unfold keeps reliefs fold-
  consistent so refold round-trips; Flat Pattern resolves cut-ready
  corners — including 3-bend patches that exist ONLY in the flat. And
  non-developable lofts are FACETED into discrete planar bends
  (chord/angle/count knobs), never faked. Both are honest-engineering
  patterns we copy. [M, flange engine]
- **Failure timing is our beat**: Autodesk's KB error catalogue
  ("Collisions found while flattening", zero-gap face fusion → "leave
  a 0.001 gap") is all flat-pattern-stage pain that arrives at the
  worst moment — validate flange collisions at FEATURE time. DXF flat
  export ships four knobs, ALL layers continuous-line (open ticket
  FUS-190565): our unfold→DXF inherits their users' punch list —
  bend lines on their own layer + direction arrows + annotations. [M]

Queue impact: M120 (sketch muscle) unaffected. The two engine reports
feed the sheet-metal v2 slice and drawings v2 when they come up the
matrix, and the T1–T13 list joins the export-test backlog. Fleet is
mid-wave-3 (joint engine, parameters engine).

### Wave-3 research addendum (2026-10-07; four reports, ~17.5k words)

`fusion_joint_engine.md` (7079 w FINAL, after the double lane-death and
refire), `fusion_parameters_engine.md` (4915 w + a 898 w actionable
extract), `planegcs_embeddability.md` (2569 w embed audit harvested
from the main agent's probes), `fusion_materials_appearance.md`
(4525 w, 21 cites — its digger also caught a live bug in OUR repo,
below).

- **Joint: the layering is validated and half-banked.** Collision →
  placement → joints matches Fusion's own stack, and the report's
  cornerstone rule — *component moves are kinematic STATE, not
  timeline features* — shipped before the report even landed
  (`0666ab9`, suite 1265). Next steal is **[S] interference as
  `(a & b).volume()`**: per-pair interference SOLIDS in a parametric
  file, which their API provably cannot make (InterferenceResults is
  throwaway), with a coincident-faces-don't-count default. The joint
  model itself waits: JCS-pair frames, DOF-set = driveable-value set,
  as-built capture before any global drag solver. [S→M]
- **Their grounding is a footgun cluster — we design it away.** Fusion
  grounds the first component *by creation order*, grounding does not
  survive an insert, patterned components cannot be grounded at all,
  and the first comp you *joint* auto-un-grounds. Our answer is one
  explicit `pinned` flag on the placement store, persisted, no
  selection-order magic. Same for their two relationship subsystems
  (grounding + joints) with ZERO over-constraint diagnostics: we ship
  honest conflicting/redundant reporting from day one. [S, doctrine]
- **Parameters v2 has a grammar law now: ONE AST, one grammar
  everywhere.** Fusion runs two divergent parsers (CAD `if(a;b;c)` vs
  CAM `a?b:c`) and stores expression TEXT, which is how renames eat
  values. We store a lossless AST + pretty text, unify M89
  `dim_exprs` into first-class renameable parameter records, ship the
  minimum credible design-scope named-scalar table [M] with
  `name=value` on-the-fly creation in every numeric field [S],
  dimension-checked units where `3mm + 2in` just works (and NO `/1mm`
  stripping ritual — an explicit `tonum()` instead), DAG cycle checks
  that PRINT the cycle path, and — the killer feature Fusion's `if`
  can't express — **conditional feature presence** (`suppress =
  if(...)`), so nobody ever hacks a 0.0001 mm cut again. [L, but the
  seam costs nothing]
- **planegcs: demoted from milestone to optional accelerator.** The
  embed audit's decisive fact is our Python 3.14 — PyPI 0.8.0 ships
  wheels only for cp312/313, so the pip route silently becomes
  sdist-compile-on-every-user's-machine. The pure-Python LM solver
  (with M119 null-space DOF) STAYS the shipping engine; a vendored
  C++ planegcs behind the solver iface is a later accelerator if
  sketch scale ever demands it (LGPL-2.1-or-later, GPL-3-compatible —
  clean when it happens).
- **Materials: the digger found the bug in OUR house.** The print
  dialog's hand-typed `_MATERIAL_DENSITIES` had drifted from
  `core/materials.py` (Stainless 8.00 vs 7.90, Nylon 1.14 vs 1.13,
  Titanium 4.50 vs 4.43) — actionable #2 is **already shipped** in
  this wave: labels now DERIVE from the core table and a test pins it
  so drift cannot return. Doctrine adopted: physical material = fact
  about a body; appearance *shadows, never mutates*; assignment stays
  OUT of the timeline ("features build geometry; materials/paint are
  facts about bodies"). Next: material SNAPSHOT on the body
  (`{name, density, lib}`) so an unknown library still yields honest
  mass — their cloud-asset "missing materials" support queue is the
  cautionary tale; then mass-properties/print-dialog read the body's
  material instead of a chooser constant. No PBR, no textures, no
  cloud libraries, no .tracerlib in v1. [M]

Queue impact: **M121 (interlock family) stands.** Wave 3 adds three
ranked candidates behind it, by value/effort: (a) interference solids
`{a&b}` per pair — small, always-parametric, and the natural opener
for the assembly phase now that placement is banked; (b) parameters v2
minimum engine (named scalars + expression fields everywhere + one
AST); (c) materials snapshot + body-aware dialogs. Fleet is idle —
wave 3 was the last scheduled lane; next probes fire per milestone
need, not by default.

### Strategic frame, upgraded
The matrix turned positioning into inventory: **16 verified
advantages** (offline versions where their own docs lose them, live
collision, free live AutoConstrain, thickness/section properties
Fusion deleted, no-NURBS honesty…) — each citable to a report, ready
for a comparison page that never lies. The **never-list is publishable
as-is**: "we ship less, truer." And the reliability wedge now has code
behind it — M111 made "your file still opens" a *tested promise*
eleven months before the 2027-02-06 cliff.
