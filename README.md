# Forma

> Working title. A keyboard-first parametric CAD for makers — Linux & Windows,
> free forever (GPL-3). Think "the 15% of Fusion 360 everyone actually uses,
> with an interface that doesn't fight you."

**Status: M2** — geometry kernel, document model + undo/redo, shaded 3D
viewport, **2D constraint sketcher** (line/rect/circle, live solving,
H/V/fix/distance/radius constraints, snap, profile→extrude),
STL/3MF/OBJ/PLY export+import, JSON `.forma` save/open (Ctrl+S/Ctrl+O).
Next: associative sketches (edit features), STEP + fillets via an
OpenCascade bridge, packaging (Flatpak/PyInstaller), Windows CI.

## Run it

```bash
python3 -m venv .venv
./.venv/bin/pip install -e .[dev]        # Windows: .venv\Scripts\pip install -e .[dev]
./.venv/bin/python -m forma
```

## Using it

3D: **F** fit · **G** grid · **E** edges · **0/1/2/3** iso/front/top/right ·
**LMB** orbit · **RMB/MMB/Shift+LMB** pan · **wheel** zoom.
Sketch: **N** new sketch · **S/L/R/C** tools · drag to edit · **H/V/F/D**
constraints on selection · **Del** delete · **X** extrude profile.
Edit: **Ctrl+Z / Ctrl+Shift+Z** undo/redo · File: **Ctrl+S** save,
**Ctrl+O** open, **Ctrl+I**-style menu for mesh import/export.

## Test it

```bash
./.venv/bin/python -m pytest -q          # 53 tests, fully headless (EGL)
./.venv/bin/python tools/snapshot.py     # render demo model to PNGs
./.venv/bin/python tools/sketch_shot.py  # render demo sketch to PNG
```

## Layout

- `forma/core/` — kernel (`geometry.py`, manifold3d), `document.py` (features
  + JSON), `io.py`, `sketch/` (entities, constraints, solver, `model.py`
  interaction logic, `profile.py` loop/face finder)
- `forma/ui/` — `camera.py` (numpy), `renderer.py` (moderngl/EGL),
  `viewport.py` (Qt blit), `sketcheditor.py` (QPainter canvas), `panels.py`,
  `mainwindow.py`, `theme.py`
- `tests/` — geometry vs analytic truth, I/O round-trips, solver, profile
  loops, pixel assertions, GUI smoke (QTest mouse/keys)

## Design decisions

- **One render path**: moderngl (EGL) → RGBA → QPainter blit. Identical
  pixels on screen, in tests, and in CI — no display server needed.
- **Kernel behind an interface**: mesh CSG (manifold3d) today; OpenCascade
  B-rep bridge next (fillets/chamfers/STEP need real topology).
- **Z-up, millimetres** everywhere inside the app.
- Sketches are **baked** into profile features for now (not yet associative
  — editing a sketch after extruding is M3).
