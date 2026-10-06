"""M75 — Closed ring loft: the dialog finally asks for the endless ring.

LoftFeature always had a `closed` field and the kernel always stitched
the last section back to the first ("endless ring") — but nothing in the
UI ever asked.  Now the dialog has the checkbox and action_loft speaks
it: 'Ring loft base ↻ 3', 'Lofted a closed ring through 3'.

Topology is the proof: three circle sections arranged AROUND an axis
(120° apart on R=20, tube r=5) blend into a genus-1 ring — watertight
with Euler number 0, the honest torus-family signature.  And the dict
contract ({'sids': …, 'closed': …}) falls back to bare tuples inside
action_loft, so every older scripted dialog still lofts.
"""
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from tracer.core.document import Document, LoftFeature                 # noqa: E402


def _ring_sections(R=20.0, r=5.0, n=64):
    """Three circle sections spaced 120° around the Y axis: centres at
    R·radial, planes spanned by (radial, Y) — normals tangential."""
    secs = []
    t = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    for k in range(3):
        th = math.pi / 2.0 + k * 2.0 * math.pi / 3.0
        u = np.array([math.cos(th), 0.0, math.sin(th)])
        v = np.array([0.0, 1.0, 0.0])
        secs.append(dict(sid=k + 1, plane="FACE",
                         placement=[float(x) for x in R * u],
                         axes=[u.tolist(), v.tolist()],
                         outer=np.column_stack([r * np.cos(t),
                                                r * np.sin(t)]).tolist()))
    return secs


# ---- core: the ring is real topology --------------------------------------------------

def test_closed_loft_of_three_sections_is_a_genus_one_ring():
    d = Document("ring")
    d.add(LoftFeature(name="Ring", sections=_ring_sections(), closed=True))
    s = d.recompute()
    tm = s.to_trimesh()
    assert tm.is_watertight
    assert tm.euler_number == 0                 # a genuine endless ring
    assert s.volume > 0


def test_closed_loft_json_round_trip_keeps_the_loop():
    d = Document("ring")
    d.add(LoftFeature(name="Ring", sections=_ring_sections(), closed=True))
    v1 = d.recompute().volume
    d2 = Document.from_dict(d.to_dict())
    lf = [f for f in d2.features if isinstance(f, LoftFeature)][0]
    assert lf.closed is True
    s2 = d2.recompute()
    assert s2.volume == pytest.approx(v1, rel=1e-6)
    assert s2.to_trimesh().euler_number == 0


# ---- UI -------------------------------------------------------------------------------

from tracer.ui.mainwindow import MainWindow                            # noqa: E402
from tracer.ui.renderer import SceneRenderer                           # noqa: E402
from tracer.core.sketch.model import SketchModel, model_to_dict        # noqa: E402
from tracer.core.sketch.profile import regions                         # noqa: E402
from tracer.core.document import ExtrudeFeature                        # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
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


def _stack_sketch(win, qapp, name, radius, z):
    m = SketchModel(plane="FACE")
    m.name = name
    m.origin = (0.0, 0.0, z)
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
                       height=0.001, plane="FACE",
                       placement=(500.0, 0.0, z),   # carriers stay parked
                       axes=m.axes, sketch=payload, sid=sid)
    win.doc.add(f)
    win.recompute()
    qapp.processEvents()
    return m


def _three(win, qapp):
    win.new_document()
    m1 = _stack_sketch(win, qapp, "base", 12.0, 0.0)
    m2 = _stack_sketch(win, qapp, "waist", 5.0, 8.0)
    m3 = _stack_sketch(win, qapp, "crown", 9.0, 16.0)
    return m1, m2, m3


def test_closed_checkbox_lands_on_the_feature(win, qapp, monkeypatch):
    m1, m2, m3 = _three(win, qapp)
    monkeypatch.setattr(
        "tracer.ui.loft.LoftDialog.ask",
        staticmethod(lambda parent, c: {"sids": (m1.sid, m2.sid, m3.sid),
                                        "closed": True}))
    win.action_loft()
    qapp.processEvents()
    lofts = [f for f in win.doc.features if isinstance(f, LoftFeature)]
    assert len(lofts) == 1 and lofts[0].closed is True
    assert lofts[0].name.startswith("Ring loft")
    st = win.status.currentMessage()
    assert "Lofted" in st and "closed ring" in st
    # the whole body (ring + parked carriers) stays watertight
    assert win.doc.result.to_trimesh().is_watertight


def test_open_loft_still_names_and_messages_the_old_way(win, qapp,
                                                        monkeypatch):
    m1, m2 = _three(win, qapp)[:2]
    monkeypatch.setattr(
        "tracer.ui.loft.LoftDialog.ask",
        staticmethod(lambda parent, c: {"sids": (m1.sid, m2.sid),
                                        "closed": False}))
    win.action_loft()
    loft = [f for f in win.doc.features
            if isinstance(f, LoftFeature)][0]
    assert loft.name == "Loft base to waist"
    assert loft.closed is False
    assert win.status.currentMessage() == "Lofted base to waist"


def test_dialog_returns_the_dict_contract_and_the_checkbox_counts(qapp, win,
                                                                  monkeypatch):
    from tracer.ui.loft import LoftDialog
    from PySide6.QtWidgets import QDialog
    cands = [(1, "A"), (2, "B"), (3, "C")]

    def accept_checking(self):
        self.closed.setChecked(True)
        return QDialog.Accepted
    monkeypatch.setattr(LoftDialog, "exec", accept_checking)
    ans = LoftDialog.ask(win, cands)
    assert ans == {"sids": (1, 2), "closed": True}
