"""M76 — Emboss / engrave text: Fusion's Sketch Text + Extrude, one step.

The maker's favourite: a name, a part number, a warning.  Glyph outlines
come from Qt's tessellation of the system font, sorted into islands +
counters by containment (an O's own centroid lies in its counter, so the
tree is ranked by area, not winding), scaled so the cap-to-baseline box
is the requested height, centred on the origin.  Every island drops as
its own parametric ExtrudeFeature, so undo/recompute/Change Parameters
treat a letter just like any other wall.

Because fonts differ per platform, the volume truths are computed from
glyph_regions on THIS machine and checked against the kernel — box plus
an embossed prism (8000 + area·d), box minus a pocket (8000 − area·d).
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                             # noqa: E402

from conftest import script_cmd                                        # noqa: E402
from tracer.core.document import Document, ExtrudeFeature, \
    PrimitiveFeature                                                   # noqa: E402
from tracer.core.text import glyph_regions                             # noqa: E402


def _net_area(regs):
    def a(p):
        p = np.asarray(p, float)
        return abs(0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1)
                                - np.roll(p[:, 0], -1) * p[:, 1]))
    return sum(a(r["outer"]) - sum(a(h) for h in r["holes"]) for r in regs)


# ---- core ----------------------------------------------------------------------------

def test_glyph_regions_scale_centre_and_split_islands(qapp):
    regs = glyph_regions("I", 10.0)
    assert len(regs) == 1 and regs[0]["holes"] == []
    allp = np.asarray(regs[0]["outer"])
    assert float(np.ptp(allp[:, 1])) == pytest.approx(10.0, abs=1e-6)
    assert abs(float(allp[:, 1].mean())) < 0.05          # y-centred


def test_a_counter_is_a_hole(qapp):
    regs = glyph_regions("0", 20.0)
    assert len(regs) == 1 and len(regs[0]["holes"]) == 1


def test_cold_font_engine_still_draws_letters(qapp):
    # Windows CI caught the cold-start failure mode: before the font
    # database populated, every glyph tessellated as one .notdef box —
    # one 5-point subpath, area ~100².  Letters must be letters even
    # when the database has never been touched.
    regs = glyph_regions("T", 12.0)
    assert len(regs) == 1
    outer = np.asarray(regs[0]["outer"])
    assert len(outer) > 6                      # a T, not a 4-corner box
    w = float(np.ptp(outer[:, 0]))
    h = float(np.ptp(outer[:, 1]))
    assert h == pytest.approx(12.0, abs=1e-6)  # scaled as asked
    assert w < h                               # a T is taller than wide


def test_the_tofu_guard_recognises_a_box():
    from tracer.core.text import _all_tofu
    box = np.array([[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]], float)
    assert _all_tofu([box])                    # square + full = veto
    stem = np.array([[0, 0], [12, 0], [12, 100], [0, 100]], float)
    assert not _all_tofu([stem])               # an "I" is a THIN bar
    assert not _all_tofu([np.asarray(r["outer"])
                          for r in glyph_regions("OH0", 10.0)])


def test_the_shipped_font_is_registered(qapp):
    # the whole Windows fix rides on this resource shipping with the
    # package; CI catches it if the TTF is ever left out
    from tracer.core.text import _BUNDLED_TTF, _bundled_family
    assert _BUNDLED_TTF.exists()
    assert _bundled_family()


def test_words_split_into_islands_left_to_right(qapp):
    regs = glyph_regions("HI", 12.0)
    assert len(regs) == 2
    xs = [float(np.asarray(r["outer"])[:, 0].mean()) for r in regs]
    assert xs == sorted(xs)                              # reading order


def test_whitespace_draws_nothing(qapp):
    assert glyph_regions("   ", 10.0) == []
    assert glyph_regions("", 10.0) == []


# ---- UI -------------------------------------------------------------------------------

from tracer.ui.mainwindow import MainWindow                            # noqa: E402
from tracer.ui.renderer import SceneRenderer                           # noqa: E402


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
    r.close()


def _plate(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 10}))
    win.recompute()
    qapp.processEvents()


def _emboss_fields(**kw):
    base = dict(text="I", height=10.0, depth=2.0, op="Emboss (join)",
                plane="XY", x=20.0, y=20.0, z=10.0)
    base.update(kw)
    return base


def test_emboss_adds_a_glyph_prism(win, qapp, monkeypatch):
    _plate(win, qapp)
    area = _net_area(glyph_regions("I", 10.0))
    script_cmd(monkeypatch, _emboss_fields())
    win.action_text()
    qapp.processEvents()
    feats = [f for f in win.doc.features if isinstance(f, ExtrudeFeature)]
    assert len(feats) == 1 and feats[0].op == "union"
    assert feats[0].name.startswith("Text")
    assert win.doc.result.volume == pytest.approx(16000 + area * 2,
                                                  rel=1e-3)
    assert win.doc.result.to_trimesh().is_watertight
    assert "Embossed" in win.status.currentMessage()


def test_engrave_pockets_the_body(win, qapp, monkeypatch):
    _plate(win, qapp)
    area = _net_area(glyph_regions("I", 10.0))
    script_cmd(monkeypatch, _emboss_fields(op="Engrave (cut)", z=8.0))
    win.action_text()
    qapp.processEvents()
    feats = [f for f in win.doc.features if isinstance(f, ExtrudeFeature)]
    assert feats and feats[0].op == "subtract"
    assert win.doc.result.volume == pytest.approx(16000 - area * 2,
                                                  rel=1e-3)
    assert "Engraved" in win.status.currentMessage()


def test_countered_letter_carries_its_hole_into_the_feature(win, qapp,
                                                            monkeypatch):
    _plate(win, qapp)
    area = _net_area(glyph_regions("0", 10.0))
    script_cmd(monkeypatch, _emboss_fields(text="0", height=10.0))
    win.action_text()
    qapp.processEvents()
    feat = [f for f in win.doc.features if isinstance(f, ExtrudeFeature)][-1]
    assert feat.holes and len(feat.holes) == 1
    # embossing a ring adds ring-area × depth (hole excluded)
    assert win.doc.result.volume == pytest.approx(16000 + area * 2,
                                                  rel=1e-3)


def test_blank_text_warns_and_adds_nothing(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    _plate(win, qapp)
    seen = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: seen.append(a[2])))
    script_cmd(monkeypatch, _emboss_fields(text="   "))
    win.action_text()
    assert seen and "text" in seen[-1].lower()
    assert not [f for f in win.doc.features
                if isinstance(f, ExtrudeFeature)]


def test_text_glyphs_round_trip_through_json(win, qapp, monkeypatch):
    _plate(win, qapp)
    script_cmd(monkeypatch, _emboss_fields(text="HI"))
    win.action_text()
    qapp.processEvents()
    v1 = win.doc.result.volume
    d2 = Document.from_dict(win.doc.to_dict())
    assert d2.recompute().volume == pytest.approx(v1, rel=1e-6)
