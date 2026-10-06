"""M84 — robust offsets from the manifold kernel (CrossSection.offset).

The v1 Offset Entities could only clone a plain straight-edged loop.
Now the bundled kernel does the heavy lifting: rounded joins with
true arc corners, sketches containing circles/arcs/ellipses, outlines
WITH HOLES, and several loops at once — all with the kernel's
guaranteed-clean self-intersection handling (concave corners close
in, collapse is refused, nothing ever flips silently).

Kept exact on purpose: a straight single loop with a MITRE join still
rides the classic shifted-edge construction (byte-identical to M34,
no kernel, no approximation), and a lone circle offsets to a TRUE
circle rather than a 64-gon.  Everything else honestly says so in the
docstring: curved outlines in a crowd offset as their tessellated
truth.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                           # noqa: E402

from tracer.core.sketch.entities import Point                        # noqa: E402
from tracer.core.sketch.model import SketchModel                     # noqa: E402


def _rect(m, w=40.0, h=30.0):
    m.add_rect(Point(0, 0), Point(w, h))


def _ring_area(pts):
    x, y = [p[0] for p in pts], [p[1] for p in pts]
    return abs(sum(x[i] * y[(i + 1) % len(x)]
                   - x[(i + 1) % len(x)] * y[i] for i in range(len(x)))) / 2


# ------------------------------------------------------------------ core

def test_mitre_straight_path_is_unchanged():
    # the M34 classic: exact shifted-edge corners, kernel untouched
    m = SketchModel()
    _rect(m)
    twin = m.add_offset(5.0)
    assert len(twin) == 4
    loops, _w = m.to_loops()
    areas = sorted(round(r["area"], 6) for r in loops)
    assert areas == [1200.0, 2000.0]          # 40×30 and 50×40 exactly


def test_round_join_adds_true_arc_corners():
    # rounded outer corners CUT the mitre square: A = A0 + P·d
    #   − 4·(1 − π/4)·d² for a rectangle (convex corners only)
    m = SketchModel()
    _rect(m)
    m.add_offset(5.0, join="round")
    loops, _w = m.to_loops()
    outer = max(r["area"] for r in loops)
    want = 1200.0 + 140.0 * 5.0 + math.pi * 25.0     # Steiner's formula
    assert outer == pytest.approx(want, rel=1e-3)
    # every corner filleted: far more than the 4 a mitre twin has
    assert len(m.sketch.lines) > 8


def test_lone_circle_stays_a_true_circle():
    m = SketchModel()
    m.add_circle(m.point(0, 0), 5.0)
    assert m.add_offset(1.5)[0].r == pytest.approx(6.5)
    assert len(m.sketch.lines) == 0           # no tessellation at all
    m_in = SketchModel()
    m_in.add_circle(m_in.point(0, 0), 5.0)
    assert m_in.add_offset(-1.0)[0].r == pytest.approx(4.0)
    # inward: honest collapse when the ring passes through nothing
    m2 = SketchModel()
    m2.add_circle(m2.point(0, 0), 5.0)
    with pytest.raises(ValueError, match="collapses or flips"):
        m2.add_offset(-5.5)


def test_arcs_join_the_offset_world():
    m = SketchModel()
    _rect(m, 20.0, 20.0)
    a, b, c = m.point(5, 20), m.point(10, 26), m.point(15, 20)
    m.sketch.arc(a, b, c)                      # bump on the top edge
    before = max(r["area"] for r in m.to_loops()[0])
    m.add_offset(3.0)
    after = max(r["area"] for r in m.to_loops()[0])
    assert after > before                      # outline grew outward


def test_holed_outline_offsets_both_rings():
    m = SketchModel()
    _rect(m)
    m.add_rect(Point(10, 10), Point(30, 20))   # the hole
    twin = m.add_offset(-4.0)
    assert len(twin) == 8                      # outer AND hole moved
    loops, _w = m.to_loops()
    areas = sorted(round(r["area"], 3) for r in loops)
    assert areas == [200.0,                              # hole original
                     pytest.approx(28.0 * 18.0, rel=1e-3),   # twin hole GREW
                     pytest.approx(32.0 * 22.0, rel=1e-3),   # twin outer
                     1200.0]                               # outer original


def test_collapse_is_refused_and_leaves_the_sketch_untouched():
    m = SketchModel()
    _rect(m)
    with pytest.raises(ValueError, match="collapses or flips"):
        m.add_offset(-20.0, join="round")      # kernel path this time
    assert len(m.sketch.lines) == 4


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


def _sk(win, qapp):
    win.new_document()
    win.action_new_sketch()
    qapp.processEvents()
    cv = win.sketch
    _rect(cv.model)
    cv.set_tool("select")
    qapp.processEvents()
    return cv


def test_offset_dialog_offers_the_join_choice(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    cv = _sk(win, qapp)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"d": 5.0, "j": "round"})
    cv.act_offset()
    qapp.processEvents()
    assert len(cv.model.sketch.lines) >= 30        # rect + tessellated


def test_offset_join_fields_reachable_and_undoable(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    cv = _sk(win, qapp)
    seen = []

    def fake(parent, title, fields, *a, **k):
        seen.append(fields)
        return {"d": 5.0, "j": "mitre"}

    monkeypatch.setattr(cmddialog, "ask", fake)
    cv.act_offset()
    kinds = {f["key"]: f["kind"] for f in seen[0]}
    assert kinds == {"d": "double", "j": "combo"}
    assert len(cv.model.sketch.lines) == 8
    assert cv.undo_op()
    assert len(cv.model.sketch.lines) == 4        # twin gone
