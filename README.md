# Forma

> Working title. A keyboard-first parametric CAD for makers — Linux & Windows,
> free forever (GPL-3). Think "the 15% of Fusion 360 everyone actually uses,
> with an interface that doesn't fight you."

**Status: M1 (vertical slice)** — geometry kernel, document model, shaded
viewport (orbit/pan/zoom, crease-only edges, horizon-faded grid),
STL/3MF/OBJ/PLY export+import, JSON `.forma` save/open (Ctrl+S/Ctrl+O),
2D constraint solver engine. Sketcher UI, history tree, STEP, and packaging
are next milestones.

## Using it

Shortcuts: **F** fit · **G** grid · **E** edges · **0/1/2/3** iso/front/top/right
· **LMB** orbit · **RMB/MMB or Shift+LMB** pan · **wheel** zoom.

## Run it

```bash
python3 -m venv .venv
./.venv/bin/pip install -e .[dev]        # Windows: .venv\Scripts\pip install -e .[dev]
./.venv/bin/python -m forma
```

## Test it

```bash
./.venv/bin/python -m pytest -q
```

## Layout

- `forma/core/` — kernel (`geometry.py`, manifold3d), `document.py` (features),
  `io.py`, `sketch/` (entities/constraints/solver)
- `forma/ui/` — `camera.py` (numpy), `renderer.py` (moderngl), `viewport.py`
  (Qt blit), `panels.py`, `mainwindow.py`, `theme.py`
- `tests/` — geometry vs analytic truth, I/O round-trips, solver, pixel tests

## Design decisions

- **One render path**: moderngl → RGBA → QPainter blit. Identical pixels on
  screen, in tests, and in CI (no display server needed).
- **Kernel behind an interface**: mesh CSG (manifold3d) today; OpenCascade
  B-rep bridge next (fillets/chamfers/STEP need real topology).
- **Z-up, millimetres** everywhere inside the app.
