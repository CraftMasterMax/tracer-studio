"""M83 — DXF / SVG import into sketches (Fusion's Insert ▸ Import).

Panels, engraving art, laser-cut gaskets: makers live in DXF and SVG,
and Fusion's move is to import them as SKETCH PROFILES that snap,
stitch and extrude.  Here: LINE/CIRCLE/ARC/LWPOLYLINE/SPLINE from DXF
and path/shape elements from SVG land as REAL sketch entities — lines,
true circles, true circular arcs; splines and elliptical arcs flatten
to polyline chains — with every coincident vertex WELDED to a shared
Point so imported outlines close into loops and extrude like anything
drawn by hand.

Honest limits: imports are assumed to be in the document's measures
(Fusion prompts; the dialog tells you the scale it used); SVG's
y-down world is flipped to sketch y-up; text/hatch/dimensions inside
DXF are ignored (they are paper, not profile); and imported vertices
are real solver points — a dense spline import arrives under-
constrained, exactly like Fusion's.
"""
import math
import os

import pytest

pytest.importorskip("PySide6")
ezdxf = pytest.importorskip("ezdxf")

from tracer.core import import2d                                           # noqa: E402
from tracer.core.sketch.model import (SketchModel, model_from_dict,        # noqa: E402
                                      model_to_dict)


def _ring_area(pts):
    x = [p[0] for p in pts]
    y = [p[1] for p in pts]
    return abs(sum(x[i] * y[(i + 1) % len(x)]
                   - x[(i + 1) % len(x)] * y[i] for i in range(len(x)))) / 2


# ---------------------------------------------------------------- DXF read

def test_read_dxf_knows_the_maker_types(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (40, 0))
    msp.add_circle((20, 20), 5)
    msp.add_arc((10, 10), 4, 0, 90)
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 5)], close=True)
    dxf = tmp_path / "part.dxf"
    doc.saveas(str(dxf))

    ops = import2d.read(str(dxf))
    kinds = [o[0] for o in ops]
    assert kinds.count("line") == 1
    assert kinds.count("circle") == 1
    assert kinds.count("arc") == 1
    assert kinds.count("poly") == 1              # lwpolyline → chain
    poly = [o for o in ops if o[0] == "poly"][0]
    assert poly[2] is True                        # closed flag survives
    arc = [o for o in ops if o[0] == "arc"][0]    # 3-point arc (start,mid,end)
    (sx, sy), (mx, my), (ex, ey) = arc[1], arc[2], arc[3]
    assert (sx, sy) == pytest.approx((14, 10), abs=1e-6)     # 0°
    assert (ex, ey) == pytest.approx((10, 14), abs=1e-6)     # 90°
    assert mx == pytest.approx(10 + 4 * math.cos(math.radians(45)), abs=1e-6)


def test_read_dxf_ignores_the_paper(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_text("TITLE BLOCK", dxfattribs={"height": 5})
    doc.saveas(str(tmp_path / "p.dxf"))
    ops = import2d.read(str(tmp_path / "p.dxf"))
    assert [o[0] for o in ops] == ["line"]


# ---------------------------------------------------------------- SVG read

def test_read_svg_flips_y_and_keeps_arcs(tmp_path):
    svg = tmp_path / "art.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" '
                   'viewBox="0 0 20 20">'
                   '<path d="M 0 0 L 10 10 L 20 0 Z"/>'
                   '<circle cx="10" cy="10" r="3"/>'
                   '<path d="M 2 2 A 4 4 0 0 1 10 2"/>'
                   '</svg>')
    ops = import2d.read(str(svg))
    kinds = [o[0] for o in ops]
    assert "circle" in kinds and "arc" in kinds
    line = [o for o in ops if o[0] == "line"][0]
    assert line[2][1] == pytest.approx(-10.0)     # y-down flipped to y-up
    circle = [o for o in ops if o[0] == "circle"][0]
    assert circle[1] == pytest.approx((10.0, -10.0), abs=1e-6)


def test_read_svg_elliptical_arcs_flatten(tmp_path):
    svg = tmp_path / "e.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><path '
                   'd="M 0 0 A 10 4 0 0 1 20 0"/></svg>')
    ops = import2d.read(str(svg))
    assert [o[0] for o in ops] == ["poly"]
    assert len(ops[0][1]) >= 8                    # flattened, honestly


def test_read_rejects_unknown_extensions(tmp_path):
    f = tmp_path / "x.stl"
    f.write_bytes(b"\0")
    with pytest.raises(ValueError) as e:
        import2d.read(str(f))
    assert "DXF" in str(e.value) or "SVG" in str(e.value)


# ------------------------------------------------------------- welding in

def test_import_welds_shared_vertices_into_one_loop():
    # four separate LINE ops that touch corner to corner
    box = [0, 0], [30, 0], [30, 20], [0, 20]
    ops = [("line", box[i], box[(i + 1) % 4]) for i in range(4)]
    m = SketchModel()
    n = m.import_ops(ops)
    sk = m.sketch
    assert n == 4 and len(sk.lines) == 4
    assert len(sk.points) == 4                    # 8 raw ends → 4 shared
    loops, warns = m.to_loops()
    assert len(loops) == 1 and not warns
    assert _ring_area(list(loops[0]["points"])) == pytest.approx(600.0)


def test_import_lands_true_circles_and_arcs():
    m = SketchModel()
    m.import_ops([("circle", (5, 5), 2.5),
                  ("arc", (14, 10), (12.828, 12.828), (10, 14))])
    assert len(m.sketch.circles) == 1
    assert m.sketch.circles[0].r == pytest.approx(2.5)
    assert len(m.sketch.arcs) == 1
    assert m.sketch.circles[0].c.x == pytest.approx(5.0)


def test_imported_refs_round_trip():
    m = SketchModel()
    m.import_ops([("circle", (0, 0), 1.0)])
    back = model_from_dict(model_to_dict(m))
    assert len(back.sketch.circles) == 1


# -------------------------------------------------------------------- UI

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        from tracer.ui.renderer import SceneRenderer
        from tracer.ui.mainwindow import MainWindow
        try:
            r = SceneRenderer()
        except Exception as e:                 # CI windows runners: no GL
            pytest.skip(f"no headless GL available: {e}")
        w = MainWindow(renderer=r)
        w.resize(1000, 700)
        w.show()
        qapp.processEvents()
        yield w
        w._unsaved = False
        w.close()
        r.close()
    except Exception:
        raise


def test_import_action_lands_the_profile_in_a_sketch(win, qapp, tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    box = [(0, 0), (40, 0), (40, 30), (0, 30)]
    for i in range(4):
        msp.add_line(box[i], box[(i + 1) % 4])
    msp.add_circle((20, 15), 4)
    dxf = tmp_path / "plate.dxf"
    doc.saveas(str(dxf))

    win.new_document()
    win.action_new_sketch("XY")
    qapp.processEvents()
    win.action_import_profile(str(dxf))
    qapp.processEvents()
    cv = win.sketch
    assert len(cv.model.sketch.lines) == 4
    assert len(cv.model.sketch.circles) == 1
    assert "Imported 5" in win.status.currentMessage()
    # and the profile is REAL: it stitches — outer box + hole ring,
    # the same flat loop list the extrude path eats
    loops, warns = cv.model.to_loops()
    assert len(loops) == 2
    # undo restores the empty sketch
    assert cv.undo_op()
    assert cv.model.sketch.lines == [] or len(cv.model.sketch.lines) == 0
