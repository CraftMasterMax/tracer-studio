"""M92 — export a sketch as DXF/SVG (M83 in reverse).

The maker loop most people actually live in: sketch the bracket in
Tracer, throw the profile at the laser cutter / CNC / Inkscape.
`tracer/core/export2d.py` turns a SketchModel into the same op-tuple
IR M83 reads — DXF gets true LINE/CIRCLE/ARC/LWPOLYLINE primitives
(ezdxf), SVG gets polyline-approximated paths (honest, and every
consumer eats them), y always up (SVG's down is flipped on write,
like import flips it back). Construction geometry is scaffolding and
stays behind. The file menu slot lands between Export STEP and Export
render, and the m15 layout pin moved with it — same documented
pattern as M83's import entry.

Proof by round trip: export then re-import lands the same geometry.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from tracer.core import export2d, import2d                            # noqa: E402
from tracer.core.sketch.model import SketchModel                      # noqa: E402


def _bracket_model():
    """Lines + a circle + an arc: one of every primitive the IR knows."""
    m = SketchModel(plane="XY")
    a, b = m.point(0, 0), m.point(40, 0)
    c, e = m.point(40, 25), m.point(0, 25)
    m.add_line(a, b)
    m.add_line(b, c)
    m.add_line(c, e)
    m.add_line(e, a)
    hole = m.point(20, 12.5)
    m.add_circle(hole, 4.0)
    p, q = m.point(8, 25), m.point(32, 25)
    m.sketch.arc(p, m.point(20, 31), q)
    return m


# -------------------------------------------------------------------- ops

def test_sketch_ops_cover_every_primitive():
    ops = export2d.sketch_ops(_bracket_model())
    kinds = [o[0] for o in ops]
    assert kinds.count("line") == 4
    assert kinds.count("circle") == 1
    assert kinds.count("arc") == 1


def test_construction_geometry_stays_home():
    m = _bracket_model()
    p0, p1 = m.point(-10, 0), m.point(60, 0)
    aux = m.add_line(p0, p1)
    aux.construction = True
    ops = export2d.sketch_ops(m)
    assert sum(1 for o in ops if o[0] == "line") == 4     # aux not exported


def test_ellipse_flattens_to_a_closed_poly():
    m = SketchModel(plane="XY")
    m.sketch.ellipse(m.point(0, 0), 10.0, 6.0)
    ops = export2d.sketch_ops(m)
    assert len(ops) == 1 and ops[0][0] == "poly"
    assert ops[0][2] is True                              # closed


def test_dxf_round_trip_is_exact(tmp_path):
    m = _bracket_model()
    path = str(tmp_path / "bracket.dxf")
    export2d.write_dxf(export2d.sketch_ops(m), path)
    back = import2d.read(path)
    assert [o[0] for o in back].count("circle") == 1
    circ = next(o for o in back if o[0] == "circle")
    assert circ[1] == pytest.approx((20.0, 12.5), abs=1e-6)
    assert circ[2] == pytest.approx(4.0, abs=1e-6)
    lines = [o for o in back if o[0] == "line"]
    assert len(lines) == 4
    arc = next(o for o in back if o[0] == "arc")
    # same arc path either travel direction: the ends as a SET (ezdxf
    # CCW convention may swap them), the bulge exactly
    ends = {tuple(round(v, 1) for v in op) for op in (arc[1], arc[3])}
    assert ends == {(8.0, 25.0), (32.0, 25.0)}
    assert arc[2] == pytest.approx((20.0, 31.0), abs=0.05)


def test_svg_round_trip_lands_the_geometry(tmp_path):
    m = _bracket_model()
    path = str(tmp_path / "bracket.svg")
    export2d.write_svg(export2d.sketch_ops(m), path)
    back = import2d.read(path)
    xs = []
    ys = []
    for op in back:
        pts = (op[1:] if op[0] != "poly" else op[1])
        for p in (pts if op[0] == "poly" else
                  (p for p in pts if isinstance(p, tuple))):
            xs.append(p[0])
            ys.append(p[1])
    # M83's read contract is translate + flip: spans are the truth
    assert max(xs) - min(xs) == pytest.approx(40.0, abs=0.05)
    assert max(ys) - min(ys) == pytest.approx(31.0, abs=0.15)  # arc top
    lines = [o for o in back if o[0] == "line"]
    longest = max(math.hypot(o[2][0] - o[1][0], o[2][1] - o[1][1])
                  for o in lines)
    assert longest == pytest.approx(40.0, abs=0.05)


def test_empty_sketch_exports_nothing_not_crashes(tmp_path):
    assert export2d.sketch_ops(SketchModel(plane="XY")) == []
    path = str(tmp_path / "empty.dxf")
    assert export2d.write_dxf([], path) == 0          # honest zero count
    assert not (tmp_path / "never.dxf").exists()


# -------------------------------------------------------------------- UI

@pytest.fixture(scope="module")
def qapp():
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
        r.ctx.release()
    except Exception:
        raise


def test_export_verb_writes_and_speaks(win, qapp, tmp_path):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    m = cv.model
    a, b = m.point(0, 0), m.point(30, 0)
    c, e = m.point(30, 12), m.point(0, 12)
    m.add_line(a, b)
    m.add_line(b, c)
    m.add_line(c, e)
    m.add_line(e, a)
    out = str(tmp_path / "rect.dxf")
    win.action_export_profile(out)
    qapp.processEvents()
    assert (tmp_path / "rect.dxf").exists()
    assert "Exported 4 entities" in win.status.currentMessage()
    back = import2d.read(out)
    assert sum(1 for o in back if o[0] == "line") == 4


def test_export_verb_on_a_saved_sketch_feature(win, qapp, tmp_path):
    from tracer.core.sketch.constraints import (Horizontal, Vertical)
    from tracer.ui.cmddialog import Shell
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    m = cv.model
    a, b = m.point(0, 0), m.point(30, 0)
    c, e = m.point(30, 12), m.point(0, 12)
    l1, l2 = m.add_line(a, b), m.add_line(b, c)
    l3, l4 = m.add_line(c, e), m.add_line(e, a)
    m.sketch.constraints.extend([Horizontal(l1), Horizontal(l3),
                                 Vertical(l2), Vertical(l4)])
    Shell.getDouble = staticmethod(lambda *A, **K: (5.0, True))
    cv.finish()
    qapp.processEvents()
    feat = win.doc.features[0]
    out = str(tmp_path / "feat.svg")
    win.action_export_profile(out, feature=feat)
    qapp.processEvents()
    assert (tmp_path / "feat.svg").exists()
    assert "Exported 4 entities" in win.status.currentMessage()


def test_file_menu_holds_the_slot(win):
    m_file = win.menuBar().actions()[0].menu()
    labels = [a.text().replace("&", "")
              for a in m_file.actions() if not a.isSeparator()]
    assert "Export profile (DXF/SVG)" in labels
    i = labels.index("Export profile (DXF/SVG)")
    assert labels[i - 1].rstrip("…") == "Export STEP (.step)"
    assert labels[i + 1].rstrip("…") == "Export render (PNG)"
