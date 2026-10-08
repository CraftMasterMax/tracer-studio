# Tracer Studio

A keyboard-first parametric CAD for makers — Linux & Windows, free forever
(GPL-3). Think "the 15% of Fusion 360 everyone actually uses, with an
interface that doesn't fight you." (Workflow inspiration only — this is an
independent project with no Autodesk assets or affiliation.)

**Status: M134**

- Parametric document: sketch → feature timeline, suppress/isolate,
  full undo/redo, JSON `.tracer` save/open (legacy `.forma` files open
  too) — and the save itself is crash-honest: writes land atomically
  (a crash mid-save leaves the OLD file intact), every Save keeps a
  **version** auto point beside the document (named versions are kept
  forever; restoring never truncates the chain, it loads unsaved work),
  autosave mirrors roll the last five with a startup recovery offer,
  a file changed on disk is never silently overwritten, and
  **Revert to Saved** re-reads the file
- 2D constraint sketcher: line/rect/circle/**arc**/**slot** (3-click,
  tangent-locked)/**regular polygon** (Y: 3–9 sides, parametrically locked
  regular — drag spins it, edit R resizes it, the circumring is guide
  geometry), click-drag geometry,
  coincident/H/V/parallel/perp/equal(len **or radius**)/point-on-line/
  **on-curve: point on line/circle/arc (point + curve, .)**/
  distance/**radius (arcs) & diameter (circles — badge, dialog and the
  M90 type-in all speak Ø; the solver keeps its radius underneath)**/**tangent (line↔curve, curve↔curve)**/
  **concentric (curves)**/**symmetric points about a line (M)**/**midpoint —
  pin a point to a segment's centre (J)** /**collinear — two segments on one
  line (L with two lines selected)**/**angular dimensions
  (line or between two, arc + editable badge)** constraints, editable
  dimension badges, snap to origin/axes, construction geometry, **corner
  fillet (F on two lines): trims the corner to a tangent arc that stays
  tangent when you drag**, **corner chamfer (G): its flat twin**, **trim /
  extend (/): two loose lines snap to their exact crossing and merge into
  one shared corner point (extend any distance, trim only a stub — T- and
  X-junctions stay intact)**, **offset outline (U): a mitred parallel
  twin of the closed loop, outward ± — exact for straight edges, collapses
  refused rather than mangled, and the nested twin extrudes as a walled
  frame)**,
  Levenberg-Marquardt solver (SVD-damped), **degrees-of-freedom overlay
  (right-click ▸ Show degrees of freedom): a cross of arrows where a
  point still floats free, a double-headed arrow along the only motion
  a 1-DOF point has, locks stay bare — the view Fusion's forums begged
  for and never shipped; it reads the Jacobian's null space, so the
  arrows are kinematic truth, not decoration**,
  **object snaps + live auto-constrain (M120): the magnet is typed —
  endpoints, exact intersections, midpoints, quadrants, centres — and
  the drop BINDS what it implies (PointOnLine, PointOnCircle, Midpoint)
  as a visible constraint, free and live where Fusion gates batch
  AutoConstrain behind premium; typed glyphs name the kind under the
  cursor, Alt suppresses everything, drags can't eat themselves**,
  **interlock family (M121): Boss · Snap fit · Rest · Lip — Fusion
  gates all four behind the paid Plastic extension; here they are free,
  pure profile+boolean pairs where the join grows on one body and its
  clearance is cut from the mate — printed pairs assemble with ZERO
  interference (the suite measures a∩b and pins it), across a shared
  interface-plane grammar of side 1 / side 2 / flip / δ**,
  **interference solids (M122, assembly phase 1): Tools ▸ Interference
  finds every clashing pair with its exact overlap volume AND can turn
  each clash into a live BODY — a red solid that RE-SOLVES when you move
  a part (kinematic placement included), the collision map Fusion's
  throwaway Interference command can't leave you behind; touching faces
  correctly interfere zero**,
  **provenance-carrying fastener library (M123): every hole/washer/
  insert dimension lives in a JSON data file stamped with its standard,
  edition, sources and verification date — the Hole dialog names where
  its auto-filled numbers came from, and a CI validator fails the build
  if any table ships uncited or stops corroborating its neighbours
  (ISO 7089 washer IDs ARE the ISO 273 close holes, all seven sizes;
  the verified sweep that moved these tables corrected seven cells that
  had drifted into shop-table folklore)**,
  **print fit-mode (M124): the 3D Print dialog carries an honest δ knob —
  holes enlarge by exactly δ in the EXPORTED mesh only (parametric radius
  rewrite inside a context manager, analytic to the micron), the document
  itself never knows; δ defaults 0, label-only mode states the sourced
  expected FDM deviations (holes print small, elephant-foot +0.15–0.2),
  and the double-compensation trap the slicers call a convention war —
  SuperSlicer even inverts the hole sign — gets said out loud**,
  **construction geometry (M125): work planes and work axes are named
  first-class datums — planes by offset, at-angle about a hinge through
  a point, three points, or midplane (non-parallel refused honestly);
  axes by two points or where two planes meet; circular patterns now
  pivot about ANY named axis (datum-line Rodrigues math, "+Z through
  center" stays the default), mirrors sweep across any construction
  plane, and deleting a referenced datum warns naming every dependent
  feature — proceed anyway and the M118 red badge tells, never a raw
  exception**,
  **transform lattice (M126): geometric pattern = step transforms
  (translate + rotate about a named axis + scale about a base point)
  raised to grid indices across two directions — named work axes drive
  the rails and the pivot (the M125 datum store earns its keep), so
  shrinking rotated spirals and oblique grids share one dialog; scale
  is its N=1 degenerate (uniform or per-axis, negative factors mirror
  for left-hand twins); refusals stay honest (a zero factor collapses
  nothing, 4096-copy lattices bounce), Change Parameters round-trips
  every lever, and lattice/scale features register in the
  datum_references ledger so the delete-warning still catches them**,
  **coil (M127): the helical ridge — circular or square section riding
  a helix about a NAMED axis, lofted through dense ring stations with
  honest abrupt ends and the vendor's two-of-three size schema solved
  forward (height = turns x pitch); right/left hand, spring or boss
  thread, Pappus-true volumes; internal modeled cut-threads
  deliberately NOT offered — decoration serves them better, as the
  standards tooling itself admits**,
  **cosmetic threads (M128): a tapped hole carries its full ISO
  designation (M8-6H grammar: coarse pitch omitted, fine written out,
  6H internal / 6g external) as metadata, and in Cosmetic mode drills
  only its tap-drill core — the major-Ø decal ring in the viewport
  replaces the helix the standards tooling itself discourages
  modeling; the M49 groove stays the legacy default, so no file on
  disk silently changes shape**,
  **hole notes on drawings (M129): the sheet tabulates every Hole —
  It./Hole/Qty/Depth/Drill, identical tapped holes counted as one row,
  through-holes reading THRU, counterbores noted — and marks each bore
  with a centreline cross + item bubble in the view you look down its
  axis from; every number derives from feature metadata (M123 sizes,
  M128 designations), never a mesh chord, so the table can no more go
  stale than the BOM — and like the BOM it is paper-only, never in
  the DXF**,
  **renaming is a relink (M130): datums — construction planes and
  work axes — were named but READ-ONLY until now, because our
  references bind by name (M125); renaming one now rewrites every
  mirror, coil and pattern that names it, atomically and counted
  ("4 references retargeted"), and collisions refuse with the cure
  rather than Fusion's silent "(1)" suffix — one name must mean one
  datum. Duplicate *feature* names do get the browser's "(1) (2)"
  display, where nothing resolves by name anyway**,
  **cross-highlighted browser (M131): click a Body row — or a feature's
  — and its body wears the selection wash in the viewport; pick a face
  and the owning body's row lights up and scrolls into view; select a
  construction plane or work axis and the orbit centres on it. The
  wash is visual only: the picked-face selection that measure-on-pick
  and every face command trust never grows from clicking a row,
  because stitched bodies are contiguous face blocks (display_ranges)
  and the highlight merges at one choke point**,
  **marking wheel (M132): hold the right button still and a four-wedge
  ring blooms at the cursor — Undo north, Extrude east, Sketch south,
  Move west, the vendor's quadrant themes carrying the same guarded
  verbs the ribbon calls. Hover highlights its wedge, release inside
  fires it, hub/void/Esc dismisses. The ring is viewport state and
  paint, not a window — so a quick tap still raises the context menu
  and a drag still orbits, all three grammars pinned against each
  other, and the hover fill, the pick and the label are pixel-pinned
  to the same wedge**,
  **orbit around the point you point at (M133): hold Shift and PRESS
  the middle button on geometry and the orbit centre jumps to the
  rayed point — the view parallel-translates it to dead centre (the
  eye derives from the target, so that is one assignment: yaw, pitch
  and distance provably untouched), a pivot dot rides the screen
  centre, and every drag until release spins about that point. Press
  on empty space and nothing pivots — Shift+MMB keeps its pan meaning,
  so the geometry under the cursor splits the gesture and no binding
  is stolen. The vendor's sticky-pivot trap (a centre that outlives
  the session until a reset) cannot exist here: the pivot IS the
  camera target every pan already relocates, and MMB-click Home is
  Reset Orbit Centre, already bound**,
  **isolation (M134): right-click a body — Isolate. The canvas keeps
  only what the overlay scopes while the browser's bulbs stay honestly
  untouched: isolation is a stacked (scope, boosted) overlay that
  writes NO eye state, so Esc restores the pre-isolate world exactly
  (bodies hidden before an isolation come back hidden — the vendor's
  verbatim law, held by construction, not by bookkeeping). Re-isolate
  narrows; the document row carries the always-findable exits; Show
  All is the separate, lossy recovery — force-every-bulb-on — and the
  two verbs' status tells say out loud why they are not each other.
  Picking and cross-highlight see the isolated world for free, since
  every renderer asks the one overlay-aware question**
- Solids: extrude (join/cut/intersect, fillet/chamfer profile corners),
  revolve, **Sweep (W): pipe the sketch's circle along a drawn path —
  lines and arcs, open or a closed ring (true torus): tubes, handles,
  rods; corners round over like bent tubing, volumes track Pappus'
  theorem; rides a new loft engine that threads resampled, seam-aligned
  cross-sections into watertight solids)**,
  **Loft (Ctrl+L): pick two sketches — the closed profile of one blends
  smoothly into the other's, any distance, any planes (sketch-on-face
  offsets are the classic flow); square→square is an exact frustum,
  square→circle a watertight maker-grade blend; coplanar pairs refused
  with advice**,
  **Thicken: wall the sketch's OPEN chains into solid stock (rib,
  stiffener, patch plate) — butt caps keep straight runs exact, round
  joins bend corners like sheet, overlapping chains union into one
  wall; closed profiles are pointed at Extrude instead**,
  **Construction Plane (Ctrl+Shift+P / ribbon Construct group): an offset
  copy of an origin plane you can sketch on — double-click its ▭ browser
  node under Origin and the solid lands exactly at the plane (basis rule
  u×v = n; translucent-blue quad in the viewport)**,
  **Shell (Modify menu): pick the face to remove, type a wall
  thickness — the body hollows into an open case (moulded-style rounded
  inner corners, taller features on the deck never perforated)**,
  **Hole (Ctrl+H): every sketch circle drills a real hole —
  simple, counterbore, or countersink (82°/90°/120°), blind or through-all,
  and now **tapped ISO M3–M12** (drills at the tap-drill Ø and cuts real
   helical thread geometry out to the major radius), plus a **fastener
   library** — pick "M5 socket head" and it fills the clearance Ø, the
   DIN 912 counterbore and depth for you (tap / clearance / heat-set-
   insert sizes; the sketch circle drops to placement-only), plus
   **Thread**:
  click a cylindrical boss face and give it real bolt threads (M3–M12);
  the cut direction is probed into the material and re-editing the sketch
  moves the holes with their circles**, linear, circular & **on-path**
  patterns (N copies walking a sketched path),
  **mirror**, sketch-on-face,
  **Press-Pull** — grab any flat face and drag it along its normal to add
  or remove material (Fusion-style live preview; the edit commits as a
  regular parametric extrude feature: suppressible, undoable, editable
  distance), and **body fillet/chamfer** — circular hole/boss rims rounded
  by revolved tools in the mesh kernel (works everywhere, **no OCCT
  needed**), straight edges rounded in true 3D through OCCT when present
  (parametric size, baked result, Modify menu, ⌒ timeline chip),
  **Split Body** — trim the solid flush with XY/XZ/YZ at any offset
  from centre, flip the kept side (✂ timeline chip, parametric),
  **Appearance** — paint the body with a material (Brass, Anodized
  blue…) or custom colour, ghost it with opacity (saved with the file),
  **Move body** — grab an RGB triad arrow and slide the solid with the
  mouse exactly like Fusion's Move; release commits a parametric ✥
  feature (Esc cancels); **Rotate body** — drag an RGB ring to spin it,
  ⟳ committed parametrically; **Visual Styles** — Wireframe, Ghosted,
  Shaded, Shaded with edges, X-ray (View menu)
- I/O: STL/3MF/OBJ/PLY mesh import+export, **STEP import/export** via an
  on-demand OpenCascade bridge (compiled with your system g++, cached;
  degrades gracefully where OCCT is absent — e.g. stock Windows, which
  still gets rim fillets); sketch profiles export as **DXF/SVG**,
  DXF/SVG sketches import back as constraints
- **Drawings**: Create ▸ New drawing puts a real sheet (A3/A4) on the
  table — top/front/right/iso views are silhouette-projected LIVE
  off the model, no re-project step, no stale paper, and hidden
  edges come out dashed by a true depth test (a pocket's back wall
  dashes behind intact metal; a far rim seen through an open hole
  stays solid); Section… cuts the body on any plane into a live
  hatched A-A view (air stays unmarked) that drags, scales and
  dimensions like any other; dimension the sheet by clicking (two
  endpoints = linear bubble, one tap on a
  circle = Ø, one tap on an arc — even one fused into a boundary
  outline — = R), and the numbers can't lie: bubbles re-measure from the
  model on every repaint, follow a stretch or a redrill, and travel
  when you drag a view; double-click a view for its **scale picker**
  (Fit, 1:1, 1:2, …) — bubbles keep measuring the model while the ink
  follows the ratio; **Rotate…** spins any one view about its own centre
  (a display-only turn — the bubbles ride along and still measure true
  millimetres); a filled-in **title block** (drawing no., title,
  drawn-by, date, material — scale, sheet size and the sheet number are
  added for you) proves the paper came from this model; a **parts
  list** docks above the block (item · description · qty · material ·
  mass — rows derived LIVE from the bodies and their volumes times a
  published density, identical parts merging into one qty row, ISO
  7573 bottom-to-top reading) and **Balloon…** pins numbered item
  bubbles onto views — model-space anchors, so they ride through
  moves and spins while the numbers count parts; sheets live in
  the browser tree and export as PNG+DXF (paper furniture — block,
  list, balloons — paints the PNG and never enters the DXF line art)
- **Configurations**: multiple design variants in one file — a text
  table per config (`Small: width = 18, height = 10`) overrides
  parameters on the fly; switch the active config and the solid,
  sketch and sheet all re-resolve
- **Multi-body**: New Body starts a separate solid that booleans don't
   silently merge — each body streams its own geometry, gets its own ▣
   node under **Bodies (n)** in the browser (double-click to make it
   active, bold is active), and the bulb hides exactly one body's
   triangles while the fused part (measure, drawings, export) stays whole.
   **Exports speak per body**: a multi-body design saves to 3MF/OBJ as
   separate named objects (a slicer opens Body 1, Body 2, …) and to STL
   as every shell; one body exports exactly as before. **3MF is written
   natively** — document provenance (title, designer, app, date), the
   body's painted material as a slicer colour slot (`basematerials`),
   part labels, and the whole build grounded on the plate; the model
   itself is never moved. **Per-body
   appearance**: right-click a body to paint it its own material (brass
   boss beside a blue plate), while the whole-part paint stays the default
- UX: Fusion mouse grammar — MMB orbits, Shift+MMB pans, RMB orbit, wheel zooms
  toward the cursor, left-drag on empty space rubber-bands a selection
  (window/crossing) — ViewCube, **Section Analysis (ribbon ▸ Section: clip
  the body open on XY/XZ/YZ, flip the cut side — purely visual, the model
  and exports stay whole)**, **hover/whole-face selection tinting in
  Fusion orange**, **RGB axis triad docked bottom-left** (far axis
  dimmed), live cursor coordinates, **measure-on-pick — one face for its
  area, two for their gap & angle (perpendicular/parallel detected), body
  volume & surface area always in the inspector**, a Fusion-style ribbon —
  quick-access strip, Design/Sketch workspace tabs, grouped icon panels —
  a playhead timeline of icon chips, and a blue-grey horizon viewport —
  plus first-launch shortcut tour and a persistent Shortcuts tab driven by
  one canonical key table
- 1059 headless tests (EGL rendering + Qt pixel assertions)

## Run it

**Linux — one installer, then just `tracer`:**

```bash
git clone https://github.com/CraftMasterMax/tracer-studio && cd tracer-studio
./tools/install-linux.sh
```

That builds a private `.venv`, puts **`tracer`** on your PATH
(`tracer part.tracer` opens a file), adds **Tracer Studio** to your
app launcher grid, and associates **`.tracer` files** so they open
with a double-click. Removing it: `./tools/uninstall-linux.sh`.

**Windows — one installer, then just `tracer`:**

```powershell
git clone https://github.com/CraftMasterMax/tracer-studio; cd tracer-studio
powershell -ExecutionPolicy Bypass -File tools\install-windows.ps1
```

That builds a private `.venv`, puts **`tracer`** on your PATH
(`tracer part.tracer` opens a file), adds **Tracer Studio** to the Start
Menu, and associates **`.tracer` files** so they open with a
double-click. No admin rights needed. Removing it:
`tools\uninstall-windows.ps1`.

**From source:**

```bash
python3 -m venv .venv
./.venv/bin/pip install -e .[dev]        # Windows: .venv\Scripts\pip install -e .[dev]
./.venv/bin/python -m tracer             # or: ./.venv/bin/tracer [file.tracer]
```

## Using it

**S** (or **/**) opens command search — type to run any command.
3D: **click a face** to select (whole faces; **Ctrl+click** adds/removes;
rubber band left→right windows, right→left crosses, Ctrl+drag adds) ·
**drag a face** to Press-Pull (+Esc to cancel, release to commit) ·
**double-click a face** to sketch on it ·
**Move/Rotate body** spawn a triad — drag an arrow to slide, a ring to
spin, **Ctrl = copy** (Fusion's Move/Copy) ·
**MMB** orbit · **Shift+MMB** pan · **RMB-drag** orbit · **RMB-click**
marking menu · **wheel** zoom toward cursor ·
**drag on empty space** selects (left→right window, right→left crossing) ·
**F6** fit · **Z** zoom to selection ·
**G** grid · **0/1/2/3** iso/front/top/right ·
**E/H/F/M/A/V** extrude/hole/fillet/move/appearance/visibility ·
**Ctrl+4-7** visual styles · **Ctrl+B** compute all ·
**Ctrl+Alt+V/B/N/R** show/hide cube/browser/nav, reset layout.
Sketch: **N** new sketch · **L/R/C/Shift+C/A/Y/K** line/rect/circle/
ellipse/arc/polygon/slot · **Enter** finish → extrude · **Shift+R** revolve ·
**D** dimension · **H/V/F/G/Shift+P/Q/T/I/J/M/2** constraints ·
**P** project model edges · **T** trim corner ·
**O** offset · **X** construction toggle · **Ctrl+Z** undo.
Drawing: **D** dimension · **B** balloon · **F** fit callout (ISO 286 —
Ø30 H7 (+0.021/0) on paper, the model stays nominal) · **Esc** stand down.
Full list: **?** / the Shortcuts tab.

## Test it

```bash
./.venv/bin/python -m pytest -q          # 1441 tests, fully headless
./.venv/bin/python tools/snapshot.py     # render demo model to PNGs
./.venv/bin/python tools/sketch_shot.py  # render demo sketch to PNG
```

## Layout

- `tracer/core/` — kernel (`geometry.py`, manifold3d), `document.py`
  (features + JSON), `io.py`, `step.py` (ctypes OpenCascade bridge),
  `native/occt_bridge.cpp` (STEP + fillets, compiled lazily),
  `sketch/` (entities, constraints, solver, `model.py` interaction logic,
  `profile.py` loop/face finder)
- `tracer/ui/` — `camera.py` (numpy), `renderer.py` (moderngl/EGL),
  `viewport.py` (Qt blit), `sketcheditor.py` (QPainter canvas), `panels.py`,
  `shortcuts.py` (canonical key table + tour), `mainwindow.py`, `theme.py`
- `tests/` — geometry vs analytic truth, I/O round-trips, solver, profile
  loops, pixel assertions, GUI smoke (QTest mouse/keys), per-milestone suites

## Design decisions

- **Kernel behind an interface**: mesh CSG (manifold3d) for the parametric
  core; OCCT reached through a tiny C ABI only for STEP and (soon) solid
  fillets — never a build-time dependency.
- **One render path**: moderngl (EGL) → RGBA → QPainter blit. Identical
  pixels on screen, in tests, and in CI.
- **Z-up, millimetres** everywhere inside the app.
- **No paid anything**: GPL-3 stack, no telemetry, no accounts, no cloud.
- **Assets ship with the app**: Liberation Sans (SIL OFL) is bundled for
  text emboss — the same letters on every machine, and no dependence on
  an OS font chain that Windows CI proved can hand back tofu.
