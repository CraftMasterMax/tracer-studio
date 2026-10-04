"""Loop-finding + nesting + end-to-end sketch->solid."""
import math

import numpy as np
import pytest

from forma.core.geometry import Solid
from forma.core.sketch.model import SketchModel
from forma.core.sketch.profile import regions


def _rect(model, x0, y0, x1, y1):
    p0, p1 = model.point(x0, y0), model.point(x1, y1)
    model.add_rect(p0, p1)


def test_single_rectangle_loop():
    m = SketchModel()
    _rect(m, 0, 0, 40, 20)
    loops, warns = m.to_loops()
    assert not warns and len(loops) == 1
    assert loops[0]["area"] == pytest.approx(800)
    regs = regions(loops)
    assert len(regs) == 1 and regs[0]["holes"] == []


def test_l_shape_single_loop():
    m = SketchModel()
    pts = [(0, 0), (30, 0), (30, 10), (10, 10), (10, 25), (0, 25)]
    for i in range(len(pts)):
        a = m.point(*pts[i])
        b = m.point(*pts[(i + 1) % len(pts)])
        # share points to close chain: recreate as shared nodes
    # proper shared-point chain:
    ps = [m.point(*p) for p in pts]
    for i in range(len(ps)):
        m.add_line(ps[i], ps[(i + 1) % len(ps)])
    loops, warns = m.to_loops()
    assert len(loops) == 1
    assert loops[0]["area"] == pytest.approx(30 * 10 + 10 * 15)
    assert len(loops[0]["points"]) == 6


def test_rect_with_circle_hole():
    m = SketchModel()
    _rect(m, 0, 0, 20, 10)
    m.add_circle(m.point(10, 5), 3)
    regs = regions(m.to_loops()[0])
    assert len(regs) == 1 and len(regs[0]["holes"]) == 1
    area = regs[0]["area"] - sum(h["area"] for h in regs[0]["holes"])
    assert area == pytest.approx(200 - math.pi * 9, rel=1e-3)


def test_two_holes_two_rects_nesting():
    m = SketchModel()
    _rect(m, 0, 0, 50, 30)
    _rect(m, 5, 5, 12, 12)
    _rect(m, 30, 18, 40, 26)
    regs = regions(m.to_loops()[0])
    assert len(regs) == 1
    assert len(regs[0]["holes"]) == 2
    area = regs[0]["area"] - sum(h["area"] for h in regs[0]["holes"])
    assert area == pytest.approx(1500 - 49 - 80)


def test_sketch_to_solid_volume():
    m = SketchModel()
    _rect(m, 0, 0, 20, 10)
    m.add_circle(m.point(10, 5), 2)
    regs = regions(m.to_loops()[0])
    r = regs[0]
    solid = Solid.extrude(r["points"], [h["points"] for h in r["holes"]], 4)
    truth = (200 - math.pi * 4) * 4
    assert solid.volume == pytest.approx(truth, rel=2e-3)
    assert solid.to_trimesh().is_watertight


def test_disconnected_rects_are_two_regions():
    m = SketchModel()
    _rect(m, 0, 0, 10, 10)
    _rect(m, 20, 0, 25, 10)
    regs = regions(m.to_loops()[0])
    assert len(regs) == 2


def test_open_chain_warns_and_extracts_nothing():
    m = SketchModel()
    a, b, c = m.point(0, 0), m.point(10, 0), m.point(10, 10)
    m.add_line(a, b)
    m.add_line(b, c)
    loops, warns = m.to_loops()
    assert loops == []
    assert any("odd-degree" in w for w in warns)


def test_unsnapped_coincident_endpoints_still_close():
    """Two separately drawn rects sharing a corner drawn at the same coords."""
    m = SketchModel()
    _rect(m, 0, 0, 10, 10)
    _rect(m, 10, 0, 20, 10)          # x=10 edges coincide exactly
    loops, warns = m.to_loops()
    regs = regions(loops)
    assert len(regs) == 2            # merged nodes -> two face loops
