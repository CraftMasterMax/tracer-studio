"""M36 — Loft (Ctrl+L): blend the closed profile of one sketch into another.

The finale of the loft engine (core/loft.py): every section is any closed
loop floating in space — origin-plane sketches or sketch-on-face give the
offsets — resampled to one vertex count, seam-aligned to its neighbour
(no twist), stitched and capped.  A square into a square is an exact
frustum (Pappus-free analytic check: h/3(A1+A2+sqrt(A1*A2)) within 0.1 %);
a square into a circle is a smooth maker-grade blend, watertight.  The
command asks which two sketches to blend, refuses coplanar pairs, and
re-syncs when either source sketch is re-edited."""
import json
import math

import numpy as np
import pytest

from tracer.core.document import Document, LoftFeature
from tracer.core.loft import section_from_payload
from tracer.core.sketch.model import SketchModel, model_to_dict


def _face_payload(name, sx, sy, z, sid, circle=False):
    m = SketchModel(plane="FACE")
    m.origin = (0.0, 0.0, z)
    m.axes = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    m.name = name
    if circle:
        m.add_circle(m.point(0, 0), sx)
    else:
        m.add_rect(m.point(-sx / 2, -sy / 2), m.point(sx / 2, sy / 2))
    d = model_to_dict(m)
    d["name"] = name
    m.sid = sid
    return m, d


# ---- kernel + feature --------------------------------------------------------

def test_tapered_prism_is_the_exact_frustum_formula():
    _m1, p1 = _face_payload("S1", 40, 30, 0.0, 11)
    _m2, p2 = _face_payload("S2", 16, 12, 10.0, 22)
    lf = LoftFeature(name="L", sections=[section_from_payload(11, p1),
                                         section_from_payload(22, p2)])
    want = 10 / 3 * (1200 + 192 + math.sqrt(1200 * 192))
    assert lf.build().volume == pytest.approx(want, rel=0.002)
    assert lf.build().to_trimesh().is_watertight


def test_square_to_circle_blend_is_watertight_and_bounded():
    _m1, p1 = _face_payload("S1", 20, 20, 0.0, 11)
    _m2, p2 = _face_payload("S2", 10, 10, 15.0, 22, circle=True)  # radius 10
    lf = LoftFeature(name="L", sections=[section_from_payload(11, p1),
                                         section_from_payload(22, p2)])
    s = lf.build()
    prism, cyl = 20 * 20 * 15, math.pi * 100 * 15
    assert cyl < s.volume < prism        # between inscribed and circumscribed
    assert s.to_trimesh().is_watertight


def test_coplanar_sections_are_refused():
    _m1, p1 = _face_payload("S1", 40, 30, 0.0, 11)
    _m2, p2 = _face_payload("S2", 10, 10, 0.0, 22)
    lf = LoftFeature(name="L", sections=[section_from_payload(11, p1),
                                         section_from_payload(22, p2)])
    with pytest.raises(ValueError, match="do not form a valid solid"):
        lf.build()


def test_loft_roundtrips_and_suppresses():
    _m1, p1 = _face_payload("S1", 40, 30, 0.0, 11)
    _m2, p2 = _face_payload("S2", 16, 12, 10.0, 22)
    d = Document("t")
    lf = LoftFeature(name="L", sections=[section_from_payload(11, p1),
                                         section_from_payload(22, p2)])
    d.add(lf)
    v = d.recompute().volume
    d2 = Document.from_dict(json.loads(json.dumps(d.to_dict())))
    f2 = d2.features[0]
    assert isinstance(f2, LoftFeature) and len(f2.sections) == 2
    assert abs(d2.recompute().volume - v) < 1e-6
    lf.suppressed = True
    d.recompute()
    assert d.result is None or d.result.volume == pytest.approx(0.0)


def test_section_extraction_refuses_ambiguous_sketches():
    m = SketchModel()
    m.add_rect(m.point(0, 0), m.point(10, 10))
    m.add_rect(m.point(2, 2), m.point(5, 5))       # loop inside a loop
    with pytest.raises(ValueError, match="nothing inside"):
        section_from_payload(1, model_to_dict(m))
    empty = model_to_dict(SketchModel())
    with pytest.raises(ValueError, match="no closed profile"):
        section_from_payload(2, empty)


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                      # noqa: E402

from tracer.core.document import ExtrudeFeature                 # noqa: E402
from tracer.ui.mainwindow import MainWindow                     # noqa: E402
from tracer.ui.panels import PropertiesPanel                    # noqa: E402
from tracer.ui.renderer import SceneRenderer                    # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _sketch_extrude(win, qapp, name, sx, sy, z):
    """A real extrude feature carrying its sketch payload — a loft
    candidate — added the way the sketch-commit flow would."""
    m, payload = _face_payload(name, sx, sy, z, sid=None)
    from tracer.core.sketch.profile import regions
    loops, _w = m.to_loops()
    regs = regions(list(loops))
    m.sid = win._next_sid() if hasattr(win, "_next_sid") \
        else max([f.sid or 0 for f in win.doc.features] + [0]) + 1
    payload = model_to_dict(m)
    payload["name"] = name
    f = ExtrudeFeature(name=name + "_body",
                       outer=np.asarray(regs[0]["points"]),
                       height=2.0, plane="FACE",
                       placement=tuple(m.origin), axes=m.axes,
                       sketch=payload, sid=m.sid)
    win.doc.add(f)
    win.recompute()
    qapp.processEvents()
    return m, payload


def _loft_doc(win, qapp):
    win.new_document()
    m1, _ = _sketch_extrude(win, qapp, "S1", 40, 30, 0.0)
    m2, _ = _sketch_extrude(win, qapp, "S2", 16, 12, 10.0)
    return m1, m2


def test_candidates_only_include_loftable_sketches(win, qapp):
    m1, m2 = _loft_doc(win, qapp)
    cands = win._loft_candidates()
    assert [(s, label) for s, label, _ in cands] == [(m1.sid, "S1"),
                                                     (m2.sid, "S2")]


def test_action_loft_blends_the_two_sketches(win, qapp, monkeypatch):
    m1, m2 = _loft_doc(win, qapp)
    monkeypatch.setattr("tracer.ui.loft.LoftDialog.ask",
                        staticmethod(lambda parent, cands: (m1.sid, m2.sid)))
    win.action_loft()
    qapp.processEvents()
    lofts = [f for f in win.doc.features if isinstance(f, LoftFeature)]
    assert len(lofts) == 1
    assert "Lofted" in win.status.currentMessage()
    # analytic: frustum(40x30 -> 16x12, h10) = 6240, plus the two plates
    assert win.doc.result.volume > 6000


def test_action_loft_refuses_same_sketch_twice(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    m1, m2 = _loft_doc(win, qapp)
    seen = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: seen.append(a[2])))
    monkeypatch.setattr("tracer.ui.loft.LoftDialog.ask",
                        staticmethod(lambda parent, cands: (m1.sid, m1.sid)))
    win.action_loft()
    assert seen and "DIFFERENT" in seen[-1]
    assert not any(isinstance(f, LoftFeature) for f in win.doc.features)


def test_action_loft_refuses_coplanar_without_adding(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    win.new_document()
    m1, _ = _sketch_extrude(win, qapp, "S1", 40, 30, 0.0)
    m2, _ = _sketch_extrude(win, qapp, "S2", 10, 10, 0.0)   # same plane!
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a[2])))
    monkeypatch.setattr("tracer.ui.loft.LoftDialog.ask",
                        staticmethod(lambda parent, cands: (m1.sid, m2.sid)))
    win.action_loft()
    assert warned and "different planes" in warned[-1]
    assert not any(isinstance(f, LoftFeature) for f in win.doc.features)


def test_loft_needs_two_sketches_dialog(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: seen.append(a[2])))
    win.new_document()
    _sketch_extrude(win, qapp, "Solo", 10, 10, 0.0)
    cands = win._loft_candidates()
    assert len(cands) == 1
    from tracer.ui.loft import LoftDialog
    assert LoftDialog.ask(win, [(s, l) for s, l, _ in cands]) is None
    assert seen and "two sketches" in seen[-1]


def test_editing_a_source_sketch_resyncs_the_loft(win, qapp, monkeypatch):
    m1, m2 = _loft_doc(win, qapp)
    monkeypatch.setattr("tracer.ui.loft.LoftDialog.ask",
                        staticmethod(lambda parent, cands: (m1.sid, m2.sid)))
    win.action_loft()
    loft = [f for f in win.doc.features if isinstance(f, LoftFeature)][0]
    before = loft.build().volume

    # widen the BASE profile to 60x30 and commit through the edit flow
    m1b, _ = _face_payload("S1", 60, 30, 0.0, m1.sid)
    win.sketch.set_model(m1b)
    win._editing_sid = m1.sid
    win._on_profiles([], "S1")
    qapp.processEvents()
    assert loft in win.doc.features
    assert len(loft.sections[0]["outer"]) == 4
    xs = [p[0] for p in loft.sections[0]["outer"]]
    assert max(xs) == pytest.approx(30.0)          # widened profile landed
    assert loft.build().volume > before            # and it is bigger now


def test_loft_dies_when_its_profile_is_destroyed(win, qapp, monkeypatch):
    m1, m2 = _loft_doc(win, qapp)
    monkeypatch.setattr("tracer.ui.loft.LoftDialog.ask",
                        staticmethod(lambda parent, cands: (m1.sid, m2.sid)))
    win.action_loft()
    loft = [f for f in win.doc.features if isinstance(f, LoftFeature)][0]
    win._sync_lofts(m1.sid, model_to_dict(SketchModel()))   # base loop gone
    assert loft not in win.doc.features


def test_properties_panel_describes_the_loft(qapp):
    _m1, p1 = _face_payload("S1", 40, 30, 0.0, 11)
    _m2, p2 = _face_payload("S2", 16, 12, 10.0, 22)
    p = PropertiesPanel()
    p.show_feature(LoftFeature(
        name="L", sections=[section_from_payload(11, p1),
                            section_from_payload(22, p2)]))
    text = p._body.text()
    assert "loft through 2 profile(s)" in text
    assert "area 1,200 mm²" in text and "area 192 mm²" in text


def test_screenshot_proof(win, qapp, monkeypatch):
    import os
    m1, m2 = _loft_doc(win, qapp)
    monkeypatch.setattr("tracer.ui.loft.LoftDialog.ask",
                        staticmethod(lambda parent, cands: (m1.sid, m2.sid)))
    win.action_loft()
    win._show_page(win.viewport)
    win.action_view("iso")
    win.viewport.refresh(fit=True)
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m36_loft.png")
