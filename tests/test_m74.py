"""M74 — N-section loft: blend through as many profiles as you like.

The kernel always lofts a list; the command capped it at two.  Fusion's
dialog gathers sections in order, and now so does ours: a pick + Add, an
ordered list with ▲▼ and Remove (which refuses to starve the loft below
two), and the first two sketches preloaded as base/top so the old one-click
path stays one click.  Three circle sections (r10 → r4 → r8 over 5+5 mm)
build two honest cone frusta: volume = πh/3·(Σ r1²+r1r2+r2²) per segment.
Two-section names and messages are untouched — every M36 test still
speaks to the reshaped dialog.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from tracer.core.document import Document, ExtrudeFeature, LoftFeature  # noqa: E402
from tracer.core.sketch.model import SketchModel, model_to_dict        # noqa: E402
from tracer.core.sketch.profile import regions                         # noqa: E402


def _frustum(r1, r2, h):
    return math.pi * h / 3.0 * (r1 * r1 + r1 * r2 + r2 * r2)


# ---- dialog widget (headless, no exec) ------------------------------------------------

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
        r.close()
    except Exception:
        raise


def test_dialog_preloads_adds_orders_and_protects_two(qapp, win):
    from tracer.ui.loft import LoftDialog
    d = LoftDialog(win, [("A", "Sketch A"), ("B", "Sketch B"),
                         ("C", "Sketch C")])
    assert d.values() == ("A", "B")            # the old base/top defaults
    d.pick.setCurrentIndex(2)
    d._add_current()
    assert d.values() == ("A", "B", "C")
    d.listw.setCurrentRow(2)
    d._move(-1)                                # C up, before B
    assert d.values() == ("A", "C", "B")
    d.listw.setCurrentRow(0)
    d._remove()
    assert d.values() == ("C", "B")
    d.listw.setCurrentRow(0)
    d._remove()                                # never below two
    assert d.values() == ("C", "B")


# ---- core: the ordered sections actually blend ----------------------------------------

def _circle_sketch(win, qapp, name, radius, z):
    """A real extrude carrier with a circle sketch payload — a loft
    candidate — parked FAR in +X so the loft through the origin stays a
    clean, analytically checkable addition to the body.  FACE plane:
    that's how a sketch payload carries its z (origin/axes)."""
    m = SketchModel(plane="FACE")
    m.name = name
    m.origin = (0.0, 0.0, z)                   # the SECTION lives here
    m.axes = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    m.add_circle(m.point(0.0, 0.0), radius)
    sid = max([f.sid or 0 for f in win.doc.features] + [0]) + 1
    m.sid = sid
    payload = model_to_dict(m)
    payload["name"] = name
    loops, _w = m.to_loops()
    regs = regions(list(loops))
    f = ExtrudeFeature(name=f"{name}_body",
                       outer=np.asarray(regs[0]["points"]),
                       height=2.0, plane="FACE",
                       placement=(500.0, 0.0, z),   # carrier parked far
                       axes=m.axes,
                       sketch=payload, sid=sid)
    win.doc.add(f)
    win.recompute()
    qapp.processEvents()
    return m


def test_three_section_loft_is_two_exact_frusta(win, qapp, monkeypatch):
    win.new_document()
    m1 = _circle_sketch(win, qapp, "S1", 10.0, 0.0)
    m2 = _circle_sketch(win, qapp, "S2", 4.0, 5.0)
    m3 = _circle_sketch(win, qapp, "S3", 8.0, 10.0)
    cands = win._loft_candidates()
    assert [s for s, _l, _sec in cands] == [m1.sid, m2.sid, m3.sid]
    monkeypatch.setattr(
        "tracer.ui.loft.LoftDialog.ask",
        staticmethod(lambda parent, c: (m1.sid, m2.sid, m3.sid)))
    win.action_loft()
    qapp.processEvents()
    lofts = [f for f in win.doc.features if isinstance(f, LoftFeature)]
    assert len(lofts) == 1 and len(lofts[0].sections) == 3
    want = _frustum(10, 4, 5) + _frustum(4, 8, 5)
    disks = math.pi * (10.0 ** 2 + 4.0 ** 2 + 8.0 ** 2) * 2.0
    assert win.doc.result.volume == pytest.approx(want + disks, rel=5e-3)
    assert win.doc.result.to_trimesh().is_watertight
    assert "Lofted" in win.status.currentMessage()


def test_repeated_sid_is_refused(win, qapp, monkeypatch):
    win.new_document()
    m1 = _circle_sketch(win, qapp, "R1", 6.0, 0.0)
    m2 = _circle_sketch(win, qapp, "R2", 3.0, 8.0)
    monkeypatch.setattr(
        "tracer.ui.loft.LoftDialog.ask",
        staticmethod(lambda parent, c: (m1.sid, m1.sid)))
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: seen.append(a[2])))
    win.action_loft()
    assert seen and "DIFFERENT" in seen[-1]
    assert not [f for f in win.doc.features
                if isinstance(f, LoftFeature)]


def test_two_section_naming_is_the_untouched_one(win, qapp, monkeypatch):
    win.new_document()
    m1 = _circle_sketch(win, qapp, "T1", 7.0, 0.0)
    m2 = _circle_sketch(win, qapp, "T2", 3.0, 9.0)
    monkeypatch.setattr(
        "tracer.ui.loft.LoftDialog.ask",
        staticmethod(lambda parent, c: (m1.sid, m2.sid)))
    win.action_loft()
    loft = [f for f in win.doc.features if isinstance(f, LoftFeature)][0]
    assert loft.name == "Loft T1 to T2"


def test_core_loft_of_three_built_directly():
    """Straight through Document: a three-circle loft stands alone."""
    def sec(r, z):
        m = SketchModel(plane="XY")
        m.origin = (0.0, 0.0, z)
        m.sketch.circle(m.point(0.0, 0.0), r)
        loops, _w = m.to_loops()
        regs = regions(list(loops))
        return dict(sid=1, plane="XY", placement=[0.0, 0.0, z],
                    axes=None,
                    outer=np.asarray(regs[0]["points"]).tolist())
    d = Document("n")
    d.add(LoftFeature(name="L", sections=[sec(12, 0.0), sec(6, 6.0),
                                          sec(9, 12.0)]))
    s = d.recompute()
    want = _frustum(12, 6, 6) + _frustum(6, 9, 6)
    assert s.volume == pytest.approx(want, rel=5e-3)
    assert s.to_trimesh().is_watertight
