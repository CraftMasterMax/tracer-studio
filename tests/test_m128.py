"""M128 — cosmetic threads (rung a): designation metadata + decal ring.

The kernel lesson of this milestone is what it does NOT build: the
vendors' own tooling recommends decoration over modeled internal
threads for performance, so a cosmetic hole drills its tap-drill core,
carries its full ISO designation as metadata, and wears a major-Ø
decal ring in the viewport — zero helical geometry. The modeled groove
(M49) stays available and is still the legacy file default, so no
document on disk silently changes shape. Designations follow ISO
grammar exactly: coarse pitch omitted ("M8-6H"), fine pitch written
out ("M8x1-6H"), internal class upper-case, external lower-case."""
import pytest

from tracer.core.document import (Document, HoleFeature, PrimitiveFeature,
                                  ThreadFeature)
from tracer.core.thread import coarse_size, designation


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


# ---- grammar --------------------------------------------------------------

def test_coarse_pitch_is_omitted_fine_is_shown():
    assert designation("M8", 1.25) == "M8-6H"        # coarse: hidden
    assert designation("M8", 1.0) == "M8x1-6H"       # fine: explicit
    assert designation("M6", 1.0, internal=False) == "M6-6g"
    assert designation("M8", 1.25, cls="7H") == "M8-7H"


def test_size_can_be_recovered_from_pitch_alone():
    # legacy holes stored only pitch — they still speak ISO
    assert designation("", 1.75) == "M12-6H"
    assert designation("", 0.35) == ""               # nothing to claim
    assert coarse_size(1.25) == "M8"
    assert coarse_size(0.99) == ""


# ---- geometry: the point of cosmetics is the ABSENT geometry ---------------

def _plate_two_holes(mode):
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 20, "dy": 20, "dz": 8}))
    d.add(HoleFeature(name="h", op="subtract", center=(10, 10, 8),
                      normal=(0, 0, -1), radius=3.4, depth=6.0,
                      cut_length=6.0, thread_pitch=1.25, thread_len=6.0,
                      thread_size="M8", thread_mode=mode))
    d.recompute()
    return d


def test_cosmetic_hole_is_the_plain_core_cut():
    cos = _plate_two_holes("cosmetic")
    mod = _plate_two_holes("modeled")
    assert cos.result.volume > mod.result.volume     # groove cuts extra
    assert cos.result.to_trimesh().is_watertight


def test_legacy_default_stays_modeled():
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 20, "dy": 20, "dz": 8}))
    f = HoleFeature(name="old", op="subtract", center=(10, 10, 8),
                    normal=(0, 0, -1), radius=3.4, depth=6.0,
                    cut_length=6.0, thread_pitch=1.25, thread_len=6.0)
    d.add(f)
    d.recompute()
    assert f.thread_mode == "modeled"                # M49 shape preserved
    assert f.designation == "M8-6H"                  # pitch names the size


# ---- decals ------------------------------------------------------------------

def test_decals_ring_only_the_cosmetic_holes():
    d = _plate_two_holes("cosmetic")
    dc = d.thread_decals()
    assert len(dc) == 1
    assert dc[0]["label"] == "M8-6H"
    assert dc[0]["radius"] == pytest.approx(3.4 + 1.25 / 2.0)  # major Ø/2
    assert dc[0]["center"] == (10.0, 10.0, 8.0)
    assert _plate_two_holes("modeled").thread_decals() == []


def test_suppressed_cosmetic_hole_decals_nothing():
    d = _plate_two_holes("cosmetic")
    d.features[-1].suppressed = True
    d.recompute()
    assert d.thread_decals() == []


def test_external_designation_defaults_lower_case():
    t = ThreadFeature(name="ridge", thread_size="M10", pitch=1.5)
    assert t.designation == "M10-6g"
    assert ThreadFeature(name="f", thread_size="M10", pitch=1.0).designation \
        == "M10x1-6g"


# ---- persistence ---------------------------------------------------------------

def test_io_roundtrip_and_legacy_file_defaults():
    import json
    import tempfile
    from pathlib import Path
    from tracer.core.io import save_document, load_document
    d = _plate_two_holes("cosmetic")
    d.features[-1].thread_class = "7H"
    with tempfile.TemporaryDirectory() as t:
        pth = Path(t) / "c.tracer"
        save_document(d, pth)
        r = load_document(pth)
    rh = r.features[-1]
    assert rh.thread_mode == "cosmetic" and rh.thread_size == "M8"
    assert rh.designation == "M8-7H"
    r.recompute()
    assert r.result.volume == pytest.approx(d.result.volume, abs=1e-9)
    # a file written BEFORE this milestone: keys absent entirely
    with tempfile.TemporaryDirectory() as t:
        pth = Path(t) / "l.tracer"
        save_document(_plate_two_holes("modeled"), pth)
        j = json.loads(pth.read_text())
        for f in j["features"]:
            if f["type"] == "HoleFeature":
                for k in ("thread_size", "thread_class", "thread_mode"):
                    f.pop(k, None)
        pth.write_text(json.dumps(j))
        r2 = load_document(pth)
    assert r2.features[-1].thread_mode == "modeled"  # unchanged geometry
    r2.recompute()


# ---- dialog ---------------------------------------------------------------------

def test_dialog_carries_class_mode_and_designation(qapp):
    from tracer.ui.hole import HoleDialog
    dlg = HoleDialog(None, [7.0])
    v = dlg.values()
    assert v["thread"] == "None" and v["thread_mode"] == "modeled"
    assert v["thread_size"] == "" and v["thread_class"] == ""
    dlg.thread.setCurrentText("M8")
    assert dlg.t_class.currentText() == "6H"          # internal default
    assert "M8-6H" in dlg.head.text()                 # ISO in the header
    assert "[modeled]" in dlg.head.text()
    dlg.t_mode.setCurrentIndex(1)
    assert "[cosmetic]" in dlg.head.text()
    dlg.t_class.setCurrentText("7H")
    assert "M8-7H" in dlg.head.text()
    v = dlg.values()
    assert v["thread_size"] == "M8" and v["thread_class"] == "7H"
    assert v["thread_mode"] == "cosmetic"


def _opts(**kw):
    o = {"type": "simple", "thread": "None", "depth": 6.0, "through": False,
         "cb_dia": 10.0, "cb_depth": 4.0, "cs_dia": 12.0, "cs_angle": 90.0}
    o.update(kw)
    return o


def test_action_hole_stores_the_metadata(win, qapp, monkeypatch):
    from tracer.ui.hole import HoleDialog
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 12}))
    win.recompute()
    win.action_new_sketch()
    qapp.processEvents()
    m = win.sketch.model
    m.add_circle(m.point(20, 20), 4.0)
    monkeypatch.setattr(
        HoleDialog, "ask",
        staticmethod(lambda p, d: _opts(thread="M8", thread_size="M8",
                                        thread_class="6H",
                                        thread_mode="cosmetic",
                                        depth=10.0)))
    win.action_hole()
    qapp.processEvents()
    hf = [f for f in win.doc.features if isinstance(f, HoleFeature)][0]
    assert hf.thread_mode == "cosmetic" and hf.designation == "M8-6H"
    assert win.doc.thread_decals()                    # ring is offered
    assert "cosmetic" in win.status.currentMessage()  # and announced


def test_action_hole_legacy_answers_stay_modeled(win, qapp, monkeypatch):
    """A scripted/older values dict without the M128 keys must build
    exactly what M49 built."""
    from tracer.ui.hole import HoleDialog
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 12}))
    win.recompute()
    win.action_new_sketch()
    qapp.processEvents()
    m = win.sketch.model
    m.add_circle(m.point(20, 20), 4.0)
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(thread="M6",
                                                        depth=10.0)))
    win.action_hole()
    hf = [f for f in win.doc.features if isinstance(f, HoleFeature)][0]
    assert hf.thread_mode == "modeled"                # groove as before
    assert hf.thread_size == "M6"                     # inferred anyway
    assert win.doc.thread_decals() == []              # no decal needed


# ---- renderer (GL-gated) ---------------------------------------------------------

def test_decal_rings_reach_the_line_buffer(win, qapp):
    d = _plate_two_holes("cosmetic")
    n0 = win._renderer._plane_count
    win._renderer.set_decals(d.thread_decals())
    assert win._renderer._plane_count >= 128          # 64 chords = 128 verts
    win._renderer.set_decals([])
    assert win._renderer._plane_count == n0
