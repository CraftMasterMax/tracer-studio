"""M127 — coil-v1: the helical ridge, honestly lofts.

The coil is the first feature the mesh kernel builds that curves in
three dimensions on purpose: a closed section riding a helix, lofted
through dense ring stations. Pappus' centroid theorem is the analytic
judge (volume = section area x helix length, chord/polygon losses
bounded by tolerance), hand must mirror exactly, and the pitch-vs-
section refusal is the difference between a thread and a screw-shaped
blob. Axes resolve through the M125 datum store, so a coil can spin
about a tilted work axis, and datum_references keeps it honest."""
import math

import numpy as np
import pytest

from tracer.core import params
from tracer.core.coil import coil_solid
from tracer.core.document import (CoilFeature, Document, PrimitiveFeature)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    w.new_document()
    qapp.processEvents()
    w._discard_guard = lambda: True
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


def _helix_len(r, p, t):
    return math.hypot(2.0 * math.pi * r, p) * t


# ---- core: analytic truth --------------------------------------------------

def test_circular_coil_matches_pappus():
    v = coil_solid((0, 0, 0), (0, 0, 1), 6.0, 4.0, 4.0, "circular", 3.0)
    exp = math.pi * 1.5 ** 2 * _helix_len(6.0, 4.0, 4.0)
    assert v.volume == pytest.approx(exp, rel=0.02)   # chord+polygon loss


def test_square_coil_matches_pappus():
    v = coil_solid((0, 0, 0), (0, 0, 1), 6.0, 4.0, 4.0, "square", 3.0)
    exp = (3.0 ** 2 / 2.0) * _helix_len(6.0, 4.0, 4.0)
    assert v.volume == pytest.approx(exp, rel=0.03)


def test_left_hand_mirrors_right_exact_enough():
    kw = dict(section="circular", size=3.0)
    r = coil_solid((0, 0, 0), (0, 0, 1), 6.0, 4.0, 4.0, **kw)
    l = coil_solid((0, 0, 0), (0, 0, 1), 6.0, 4.0, 4.0, hand="left", **kw)
    assert l.volume == pytest.approx(r.volume, rel=2e-3)
    assert np.allclose(np.asarray(r.bounding_box)[:, 2],
                       np.asarray(l.bounding_box)[:, 2], atol=0.05)


def test_coil_rides_a_tilted_named_axis_frame():
    up = coil_solid((0, 0, 0), (0, 0, 1), 6.0, 4.0, 3.0, "circular", 2.0)
    til = coil_solid((1, 2, 3), (1, 1, 2), 6.0, 4.0, 3.0, "circular", 2.0)
    assert til.volume == pytest.approx(up.volume, rel=2e-3)
    bb = np.asarray(til.bounding_box, float)
    assert bb[0].min() < 0.9                     # genuinely swung off-Z


# ---- core: honest refusals ---------------------------------------------------

def test_coil_refusals_all_six():
    with pytest.raises(params.ParamError):        # section swallows pitch
        coil_solid((0, 0, 0), (0, 0, 1), 6, 2.0, 3, "circular", 5.0)
    with pytest.raises(params.ParamError):
        coil_solid((0, 0, 0), (0, 0, 1), 0.0, 2.0, 3, "circular", 1.0)
    with pytest.raises(params.ParamError):
        coil_solid((0, 0, 0), (0, 0, 1), 6, 0.0, 3, "circular", 1.0)
    with pytest.raises(params.ParamError):
        coil_solid((0, 0, 0), (0, 0, 1), 6, 2.0, 0.2, "circular", 1.0)
    with pytest.raises(params.ParamError):
        coil_solid((0, 0, 0), (0, 0, 1), 6, 2.0, 3, "hexagonal", 1.0)
    with pytest.raises(params.ParamError):
        coil_solid((0, 0, 0), (0, 0, 1), 6, 2.0, 3, "circular", 1.0,
                   hand="sideways")


# ---- document wiring ---------------------------------------------------------

def _bolt(d):
    d.add(PrimitiveFeature(name="rod", kind="cylinder",
                           dims={"radius": 2.2, "height": 12},
                           placement=(0, 0, 0)))
    d.recompute()
    return d


def test_bolt_union_grows_and_binds_named_axis():
    d = _bolt(Document())
    core = d.result.volume
    d.add_axis_2pt((0, 0, 0), (0, 0, 12))
    d.add_coil("thread", axis="Axis 1", diameter=4.4, pitch=1.25,
               turns=6, size=1.1)
    d.recompute()
    assert d.result.volume > core + 10.0
    bb = np.asarray(d.result.bounding_box, float)
    assert abs(bb[1][0] - 2.75) < 0.05           # ridge stands proud
    assert d.datum_references("Axis 1") == ["thread"]


def test_missing_axis_is_a_param_error():
    d = _bolt(Document())
    d.add_coil("ghost", axis="Axis 42")
    with pytest.raises(params.ParamError):
        d.recompute()


def test_io_roundtrip_keeps_every_coil_field():
    import tempfile
    from pathlib import Path
    from tracer.core.io import save_document, load_document
    d = _bolt(Document())
    d.add_coil("spring", axis="Z", base=(1, 2, 3), diameter=9.0,
               pitch=2.5, turns=4.5, hand="left", section="square",
               size=1.8)
    with tempfile.TemporaryDirectory() as t:
        pth = Path(t) / "k.tracer"
        save_document(d, pth)
        r = load_document(pth)
    c = next(f for f in r.features if isinstance(f, CoilFeature))
    assert c.axis == "Z" and c.base == (1.0, 2.0, 3.0)
    assert (c.diameter, c.pitch, c.turns, c.hand, c.section, c.size) == \
        (9.0, 2.5, 4.5, "left", "square", 1.8)
    assert c.height == pytest.approx(11.25)
    r.recompute()
    assert r.result.volume == pytest.approx(d.result.volume, abs=1e-6)


# ---- UI -----------------------------------------------------------------------

def _dialog_answers(monkeypatch, values):
    from tracer.ui import cmddialog
    monkeypatch.setattr(cmddialog, "ask",
                        lambda parent, title, fields, remember_key=None:
                        dict(values))


def test_coil_dialog_builds_announced_geometry(win, monkeypatch):
    _dialog_answers(monkeypatch, {"axis": "Z", "base": "0,0,0",
                                  "diam": 10.0, "pitch": 3.0,
                                  "turns": 3.0, "hand": "Left",
                                  "section": "Square", "size": 2.0})
    win.action_coil()
    assert win.status.currentMessage().startswith("Coil 3x3")
    assert "left-handed" in win.status.currentMessage()
    c = win.doc.features[-1]
    assert isinstance(c, CoilFeature) and c.hand == "left"
    assert c.section == "square" and c.height == 9.0


def test_coil_dialog_garbage_base_refused_loudly(win, monkeypatch):
    _dialog_answers(monkeypatch, {"axis": "Z", "base": "origin",
                                  "diam": 10.0, "pitch": 3.0,
                                  "turns": 3.0, "hand": "Right",
                                  "section": "Circular", "size": 2.0})
    win.action_coil()                            # must not raise
    assert win.doc.features == []
    assert "refused" in win.status.currentMessage().lower()


def test_coil_dialog_overlap_fails_with_badge_not_crash(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda parent, title, text, *a, **k: QMessageBox.Ok))
    _dialog_answers(monkeypatch, {"axis": "Z", "base": "0,0,0",
                                  "diam": 10.0, "pitch": 1.0,
                                  "turns": 3.0, "hand": "Right",
                                  "section": "Circular", "size": 4.0})
    win.action_coil()                            # section > pitch
    assert getattr(win.doc, "failed_feature", None) is not None


def test_change_parameters_reteams_the_coil(win, monkeypatch):
    win.doc.add_coil("spring", axis="Z", diameter=10.0, pitch=2.0,
                     turns=3.0, size=1.5)
    win.recompute()
    before = win.doc.result.volume
    _dialog_answers(monkeypatch, {"diam": 10.0, "pitch": 3.0,
                                  "turns": 4.0, "size": 2.0})
    win.action_change_params(win.doc.features[-1])
    c = win.doc.features[-1]
    assert (c.pitch, c.turns, c.size) == (3.0, 4.0, 2.0)
    assert win.doc.result.volume > before
