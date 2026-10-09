"""M49 — Threads as real geometry.

The tap-drill table is ISO metric coarse; the groove is a helical wire
cut into the hole wall.  These tests pin the geometry (the groove root
lands on the ISO major radius, the cutter is watertight), the document
integration (a tapped hole cuts MORE than the plain drill, survives the
JSON round-trip), and the command layer (choosing M6 in the Hole dialog
drills at the tap-drill Ø, threads the full depth, and renames the
feature — while "None" keeps the old plain-hole behaviour exactly).
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                       # noqa: E402

from tracer.core.document import (Document, HoleFeature,          # noqa: E402
                                  PrimitiveFeature)
from tracer.core.thread import ISO_COARSE, helix_groove          # noqa: E402


# ---- core: the helical cutter --------------------------------------------------

def test_groove_is_watertight():
    assert helix_groove(2.5, 1.0, 12.0).to_trimesh().is_watertight


def test_groove_root_lands_on_the_iso_major_radius():
    """For every coarse size the cutter's outer diameter equals the
    nominal thread diameter (major) — the groove root, to a mesh step."""
    for name, (pitch, tap) in ISO_COARSE.items():
        major = float(name[1:])
        dia = helix_groove(tap / 2, pitch, 6 * pitch).bounding_box
        outer = dia[1][0] - dia[0][0]
        assert abs(outer - major) < 0.05 * pitch, (name, outer, major)


def test_bigger_pitch_removes_more():
    lo = helix_groove(2.5, 0.8, 10.0).volume
    hi = helix_groove(2.5, 1.5, 10.0).volume
    assert hi > lo


def test_thread_too_short_for_its_pitch_is_rejected():
    with pytest.raises(ValueError):
        helix_groove(2.5, 1.0, 1.0)          # < 1.2 * pitch


def test_tap_drill_table_is_consistent():
    for name, (pitch, tap) in ISO_COARSE.items():
        major = float(name[1:])
        assert pitch > 0
        assert 0 < major - tap < pitch * 1.2          # maker tap-drill rule


# ---- document integration -------------------------------------------------------

def _plate_and_hole(**hf):
    d = Document("t")
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 30, "dy": 30, "dz": 10}))
    d.recompute()
    d.add(HoleFeature(name="Hole", op="subtract", center=(15, 15, 0),
                      normal=(0, 0, 1), radius=2.5, depth=10,
                      cut_length=10.0, **hf))
    return d, d.recompute()


def test_tapped_hole_cuts_more_than_plain():
    _, plain = _plate_and_hole()
    _, tapped = _plate_and_hole(thread_pitch=1.0, thread_len=10.0)
    assert tapped.volume < plain.volume
    assert tapped.to_trimesh().is_watertight


def test_thread_survives_json_round_trip():
    d, _ = _plate_and_hole(thread_pitch=1.0, thread_len=10.0)
    d2 = Document.from_dict(d.to_dict())
    hf = [f for f in d2.features if isinstance(f, HoleFeature)][0]
    assert hf.thread_pitch == pytest.approx(1.0)
    assert hf.thread_len == pytest.approx(10.0)
    assert d2.recompute().volume == pytest.approx(d.recompute().volume, abs=1)


# ---- UI: dialog + command --------------------------------------------------------

from tracer.ui.hole import HoleDialog, THREADS                   # noqa: E402
from tracer.ui.mainwindow import MainWindow                      # noqa: E402
from tracer.ui.renderer import SceneRenderer                     # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:                     # CI windows runners: no GL
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def test_dialog_carries_the_thread_choices(qapp):
    dlg = HoleDialog(None, [5.0])
    assert dlg.thread.count() == len(THREADS) == len(ISO_COARSE) + 1
    assert dlg.thread.itemText(0) == "None"
    assert "M6" in [dlg.thread.itemText(i) for i in range(dlg.thread.count())]
    assert dlg.values()["thread"] == "None"          # default stays plain


def test_dialog_type_toggles_bore_rows(qapp):
    """Constructing the real dialog and changing Type must show/hide the
    counterbore/countersink rows — this code path was silently broken
    until M49 (every prior Hole test patched .ask, never building one)."""
    dlg = HoleDialog(None, [5.0])
    assert dlg.cb_dia.isHidden() and dlg.cs_dia.isHidden()   # Simple: both off
    dlg.type.setCurrentText("Counterbore")
    assert not dlg.cb_dia.isHidden() and dlg.cs_dia.isHidden()
    dlg.type.setCurrentText("Countersink")
    assert dlg.cb_dia.isHidden() and not dlg.cs_dia.isHidden()
    dlg.type.setCurrentText("Simple")
    assert dlg.cb_dia.isHidden() and dlg.cs_dia.isHidden()


def test_dialog_head_announces_the_tap_drill(qapp):
    dlg = HoleDialog(None, [5.0])
    base = dlg.head.text()
    idx = dlg.thread.findText("M6")
    dlg.thread.setCurrentIndex(idx)
    txt = dlg.head.text()
    assert txt != base and "M6" in txt and "5" in txt   # tap-drill Ø shown


def _opts(**kw):
    o = {"type": "simple", "thread": "None", "depth": 6.0, "through": False,
         "cb_dia": 10.0, "cb_depth": 4.0, "cs_dia": 12.0, "cs_angle": 90.0}
    o.update(kw)
    return o


def _plate_with_circle(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 12}))
    win.recompute()
    win.action_new_sketch()
    qapp.processEvents()
    m = win.sketch.model
    m.add_circle(m.point(20, 20), 4.0)          # circle is placement only
    return m


def test_threaded_hole_drills_at_tap_drill_and_threads(win, qapp, monkeypatch):
    _plate_with_circle(win, qapp)
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(thread="M6",
                                                        depth=10.0)))
    win.action_hole()
    qapp.processEvents()
    hf = [f for f in win.doc.features if isinstance(f, HoleFeature)][0]
    pitch, tap = ISO_COARSE["M6"]
    assert hf.radius == pytest.approx(tap / 2)     # drilled at tap-drill Ø
    assert hf.thread_pitch == pytest.approx(pitch)
    assert hf.thread_len == pytest.approx(10.0)    # threaded full depth
    assert hf.name == "Hole M6"
    assert win.doc.result.to_trimesh().is_watertight


def test_none_thread_keeps_plain_hole_behaviour(win, qapp, monkeypatch):
    _plate_with_circle(win, qapp)
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(thread="None",
                                                        depth=10.0)))
    win.action_hole()
    hf = [f for f in win.doc.features if isinstance(f, HoleFeature)][0]
    assert hf.radius == pytest.approx(4.0)         # circle diameter kept
    assert hf.thread_pitch == 0.0 and hf.thread_len == 0.0
    assert hf.name == "Hole Ø8"


def test_redrill_updates_thread_in_place(win, qapp, monkeypatch):
    _plate_with_circle(win, qapp)
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(thread="None",
                                                        depth=10.0)))
    win.action_hole()
    first = [f for f in win.doc.features if isinstance(f, HoleFeature)][0]
    win.edit_sketch(first)
    qapp.processEvents()
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(thread="M8",
                                                        depth=10.0)))
    win.action_hole()
    qapp.processEvents()
    holes = [f for f in win.doc.features if isinstance(f, HoleFeature)]
    assert len(holes) == 1                          # updated, not duplicated
    pitch, tap = ISO_COARSE["M8"]
    assert holes[0].radius == pytest.approx(tap / 2)
    assert holes[0].thread_pitch == pytest.approx(pitch)
    assert holes[0].name == "Hole M8"
