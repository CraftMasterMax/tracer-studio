# Tracer Studio

A keyboard-first parametric CAD for makers — Linux & Windows, free forever
(GPL-3). Think "the 15% of Fusion 360 everyone actually uses, with an
interface that doesn't fight you." (Workflow inspiration only — this is an
independent project with no Autodesk assets or affiliation.)

**Status: M20**

- Parametric document: sketch → feature timeline, suppress/isolate,
  full undo/redo, JSON `.tracer` save/open (legacy `.forma` files open too)
- 2D constraint sketcher: line/rect/circle/**arc**/**slot** (3-click,
  tangent-locked), click-drag geometry,
  coincident/H/V/parallel/perp/equal(len **or radius**)/point-on-line/
  distance/**radius (arc & circle)**/**tangent (line↔curve, curve↔curve)**/
  **concentric (curves)**/**symmetric points about a line (M)**/**angular dimensions
  (line or between two, arc + editable badge)** constraints, editable
  dimension badges, snap to origin/axes, construction geometry, **corner
  fillet (F on two lines): trims the corner to a tangent arc that stays
  tangent when you drag**, **corner chamfer (G): its flat twin**, **trim /
  extend (/): two loose lines snap to their exact crossing and merge into
  one shared corner point (extend any distance, trim only a stub — T- and
  X-junctions stay intact)**,
  Levenberg-Marquardt solver (SVD-damped)
- Solids: extrude (join/cut/intersect, fillet/chamfer profile corners),
  revolve, linear & circular patterns, **mirror**, sketch-on-face,
  **Press-Pull** — grab any flat face and drag it along its normal to add
  or remove material (Fusion-style live preview; the edit commits as a
  regular parametric extrude feature: suppressible, undoable, editable
  distance), and **body fillet/chamfer** — circular hole/boss rims rounded
  by revolved tools in the mesh kernel (works everywhere, **no OCCT
  needed**), straight edges rounded in true 3D through OCCT when present
  (parametric size, baked result, Modify menu, ⌒ timeline chip)
- I/O: STL/3MF/OBJ/PLY mesh import+export, **STEP import/export** via an
  on-demand OpenCascade bridge (compiled with your system g++, cached;
  degrades gracefully where OCCT is absent — e.g. stock Windows, which
  still gets rim fillets)
- UX: Fusion-style mouse, ViewCube, **hover/whole-face selection tinting**
  with live cursor coordinates, an icon quick-toolbar, a playhead timeline
  of icon chips, and a blue-grey horizon viewport — plus first-launch
  shortcut tour and a persistent Shortcuts tab driven by one canonical
  key table
- 336 headless tests (EGL rendering + Qt pixel assertions)

## Run it

```bash
python3 -m venv .venv
./.venv/bin/pip install -e .[dev]        # Windows: .venv\Scripts\pip install -e .[dev]
./.venv/bin/python -m tracer             # or: ./.venv/bin/tracer
```

## Using it

3D: **click a face** to select · **drag a face** to Press-Pull (+Esc to
cancel, release to commit) · **double-click a face** to sketch on it ·
**MMB/RMB** orbit · **Shift+MMB** pan · **wheel** zoom · **F** fit ·
**G** grid · **E** edges · **0/1/2/3** iso/front/top/right.
Sketch: **N** new sketch · **S/L/R/C/O/A** line/rect/circle/slot/arc · **D**
dimension · **H/V/F/G/T/I/M/2** constraints · **/** trim-to-corner · **X** extrude · **Ctrl+Z** undo.
Full list: **?** / the Shortcuts tab.

## Test it

```bash
./.venv/bin/python -m pytest -q          # 336 tests, fully headless
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
