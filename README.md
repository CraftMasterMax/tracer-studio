# Tracer Studio

A keyboard-first parametric CAD for makers — Linux & Windows, free forever
(GPL-3). Think "the 15% of Fusion 360 everyone actually uses, with an
interface that doesn't fight you." (Workflow inspiration only — this is an
independent project with no Autodesk assets or affiliation.)

**Status: M109**

- Parametric document: sketch → feature timeline, suppress/isolate,
  full undo/redo, JSON `.tracer` save/open (legacy `.forma` files open too)
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
  Levenberg-Marquardt solver (SVD-damped)
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
  added for you) proves the paper came from this model; sheets live in
  the browser tree and export as PNG+DXF
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
   as every shell; one body exports exactly as before. **Per-body
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

```bash
python3 -m venv .venv
./.venv/bin/pip install -e .[dev]        # Windows: .venv\Scripts\pip install -e .[dev]
./.venv/bin/python -m tracer             # or: ./.venv/bin/tracer
```

## Using it

3D: **click a face** to select (whole faces; **Ctrl+click** adds/
removes; rubber band left→right windows, right→left crosses,
Ctrl+drag adds) · **drag a face** to Press-Pull (+Esc to
cancel, release to commit) · **double-click a face** to sketch on it ·
**Move/Rotate body** spawn a triad — drag an arrow to slide, a ring to
spin, **Ctrl = copy** (Fusion's Move/Copy) ·
**MMB** orbit · **Shift+MMB** pan · **RMB-drag** orbit · **RMB-click**
marking menu · **wheel** zoom toward cursor ·
**drag on empty space** selects (left→right window, right→left crossing) ·
**F** fit ·
**G** grid · **E** edges · **0/1/2/3** iso/front/top/right.
Sketch: **N** new sketch · **S/L/R/C/O/Y/A** line/rect/circle/slot/polygon/arc · **D**
dimension · **H/V/F/G/T/I/J/M/2** constraints · **/** trim-to-corner · **X** extrude · **Ctrl+Z** undo.
Full list: **?** / the Shortcuts tab.

## Test it

```bash
./.venv/bin/python -m pytest -q          # 1086 tests, fully headless
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
