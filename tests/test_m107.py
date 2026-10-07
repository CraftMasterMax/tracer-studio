"""M107 — the fastener hole library: name a screw, get the right hole.

The kernel could already cut any hole; what a maker kept having to look
up (or mistype) was the NUMBERS — that an M3 clearance is Ø3.4, an M4
socket head wants a Ø9 counterbore ~5.2 deep, an M3 heat-set insert
presses into Ø4.  This library turns a named fastener into the exact
parameters HoleFeature consumes, so a single combo pick fills the dialog
and the sketch circle drops to being PLACEMENT ONLY.

Design promise pinned by these tests: the library is pure, sourced data
(the tap/pitch figures are reused verbatim from ISO_COARSE so the tap
path can't drift from it), and the Hole dialog's "Custom" preset keeps
the pre-library behaviour byte-for-byte — the Ø override is None and the
sketch circle rules, exactly as before M107.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                       # noqa: E402

from tracer.core.document import (Document, HoleFeature,          # noqa: E402
                                  PrimitiveFeature)
from tracer.core.thread import ISO_COARSE                        # noqa: E402
from tracer.core import fasteners as F                            # noqa: E402


# ---- core: the library is sane, sourced, and complete -----------------------

def test_library_speaks_every_coarse_size():
    assert F.SIZES == tuple(ISO_COARSE)                # M3..M12
    for s in F.SIZES:
        assert s in F.CLEARANCE and s in F.SHCS_HEAD
        assert len(F.CLEARANCE[s]) == 3                # close/medium/coarse


def test_clearance_holes_bracket_the_nominal():
    # tap-drill < nominal <= close <= medium <= coarse for every size
    for s in F.SIZES:
        close, med, coarse = F.CLEARANCE[s]
        assert F.tap_drill(s) < float(s[1:]) <= close <= med <= coarse, s


def test_clearance_spot_values_are_iso_273():
    assert F.clearance("M3", "medium") == pytest.approx(3.4)
    assert F.clearance("M8", "medium") == pytest.approx(9.0)
    assert F.clearance("M3", "close") == pytest.approx(3.2)
    assert F.clearance("M4", "coarse") == pytest.approx(4.6)


def test_tap_and_pitch_come_from_the_thread_table():
    # the library must not carry its own tap figures — reuse, never drift
    for s in F.SIZES:
        pitch, tap = ISO_COARSE[s]
        assert F.pitch(s) == pitch
        assert F.tap_drill(s) == tap


def test_cbore_clears_the_din912_head_and_deepens_the_seat():
    for s in F.SIZES:
        head, height = F.SHCS_HEAD[s]
        dia, depth = F.cbore(s)
        assert dia == pytest.approx(head + 0.5)        # room for the head
        assert depth == pytest.approx(height + 0.2)    # + a hair of clearance
    assert F.cbore("M3")[0] < F.cbore("M4")[0]          # monotonic in size


def test_insert_sizes_are_the_small_common_ones():
    assert set(F.INSERT) >= {"M3", "M4"}
    for s, dia in F.INSERT.items():
        assert dia > float(s[1:])                        # insert body > screw


def test_insert_drills_match_2026_source_sweep():
    """fastener_tables_verify.md (2026-10-07): M5/M6 had been the
    large-barrel 7.0/8.5 folklore that exceeded EVERY reachable modern
    compact-series chart; corrected into the sourced band."""
    assert F.INSERT["M3"] == 4.0     # ✓✓ two brands
    assert F.INSERT["M4"] == 5.6     # ✓? within a print step of CNCK 5.7
    assert F.INSERT["M5"] == 6.7     # was 7.0
    assert F.INSERT["M6"] == 8.2     # was 8.5


def test_hole_for_bundles_each_kind():
    cl = F.hole_for("M4", "clearance")
    assert cl["drill"] == pytest.approx(4.3) and cl["type"] == "simple"
    assert cl["thread"] == "None" and cl["cb_dia"] == 0.0

    tp = F.hole_for("M4", "tapped")
    assert tp["drill"] is None and tp["thread"] == "M4"  # tap path drives it

    sh = F.hole_for("M5", "socket head")
    assert sh["drill"] == pytest.approx(5.3)
    assert sh["type"] == "counterbore"
    assert sh["cb_dia"] == pytest.approx(9.0)
    assert sh["cb_depth"] == pytest.approx(5.2)

    ins = F.hole_for("M3", "heat-set insert")
    assert ins["drill"] == pytest.approx(4.0) and ins["type"] == "simple"


def test_hole_for_rejects_unknown_kind_and_missing_insert():
    with pytest.raises(ValueError):
        F.hole_for("M3", "counterbore")                  # typo'd kind
    with pytest.raises(KeyError):
        F.hole_for("M12", "heat-set insert")             # no data for M12


# ---- document: a clearance preset actually cuts that diameter ---------------

def _plate_with_clearance(size="M4"):
    d = Document("t")
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 40, "dz": 12}))
    d.recompute()
    dia = F.clearance(size, "medium")
    d.add(HoleFeature(name=f"Hole {size} clearance", op="subtract",
                      center=(20, 20, 12), normal=(0, 0, -1),
                      radius=dia / 2, depth=12, cut_length=12.0, through=True))
    return d, d.recompute()


def test_library_clearance_hole_removes_the_expected_material():
    d, solid = _plate_with_clearance("M4")
    removed = 40 * 40 * 12 - solid.volume
    want = 3.141592653589793 * (F.clearance("M4") / 2) ** 2 * 12
    assert removed == pytest.approx(want, rel=0.02)
    assert solid.to_trimesh().is_watertight


# ---- UI: dialog fills from the library, and "Custom" changes nothing --------

from tracer.ui.hole import HoleDialog, STDS                       # noqa: E402
from tracer.ui.mainwindow import MainWindow                       # noqa: E402
from tracer.ui.renderer import SceneRenderer                      # noqa: E402


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
    w._discard_guard = lambda: True
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


def test_dialog_default_is_custom_and_leaves_no_override(qapp):
    dlg = HoleDialog(None, [5.0])
    assert dlg.std.currentText() == STDS[0]              # Custom first
    assert dlg.values()["drill"] is None             # circle rules, as before


def test_dialog_clearance_fills_the_drill(qapp):
    dlg = HoleDialog(None, [5.0])
    dlg.size.setCurrentText("M4")
    dlg.std.setCurrentText("Clearance")
    v = dlg.values()
    assert v["drill"] == pytest.approx(4.3)
    assert v["type"] == "simple" and v["thread"] == "None"


def test_dialog_socket_head_fills_counterbore(qapp):
    dlg = HoleDialog(None, [5.0])
    dlg.size.setCurrentText("M5")
    dlg.std.setCurrentText("Socket head (cbore)")
    v = dlg.values()
    assert v["drill"] == pytest.approx(5.3)
    assert v["type"] == "counterbore"
    assert v["cb_dia"] == pytest.approx(9.0)
    assert v["cb_depth"] == pytest.approx(5.2)
    assert not dlg.cb_dia.isHidden()


def test_dialog_tapped_hands_off_to_the_thread_path(qapp):
    dlg = HoleDialog(None, [5.0])
    dlg.size.setCurrentText("M3")
    dlg.std.setCurrentText("Tapped")
    v = dlg.values()
    assert v["drill"] is None                           # tap drill from ISO
    assert v["thread"] == "M3"


def test_dialog_insert_without_data_is_graceful(qapp):
    dlg = HoleDialog(None, [5.0])
    dlg.size.setCurrentText("M12")
    dlg.std.setCurrentText("Heat-set insert")
    assert dlg.values()["drill"] is None                # not a crash
    assert "datasheet" in dlg.head.text().lower()


def _opts(**kw):
    o = {"type": "simple", "thread": "None", "drill": None, "depth": 6.0,
         "through": False, "cb_dia": 10.0, "cb_depth": 4.0,
         "cs_dia": 12.0, "cs_angle": 90.0}
    o.update(kw)
    return o


def _plate_with_circle(win, qapp, r=4.0):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 12}))
    win.recompute()
    win.action_new_sketch()
    qapp.processEvents()
    m = win.sketch.model
    m.add_circle(m.point(20, 20), r)          # big circle; presets ignore it
    return m


def test_action_hole_preset_drill_overrides_the_circle(win, qapp, monkeypatch):
    _plate_with_circle(win, qapp, r=4.0)      # sketch Ø8, but preset says M4
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(drill=4.3, depth=12.0,
                                                        through=True)))
    win.action_hole()
    qapp.processEvents()
    hf = [f for f in win.doc.features if isinstance(f, HoleFeature)][0]
    assert hf.radius == pytest.approx(2.15)       # library Ø, not the circle
    assert win.doc.result.to_trimesh().is_watertight


def test_action_hole_socket_head_cuts_clearance_plus_cbore(win, qapp,
                                                           monkeypatch):
    _plate_with_circle(win, qapp, r=4.0)
    monkeypatch.setattr(
        HoleDialog, "ask",
        staticmethod(lambda p, d: _opts(type="counterbore", drill=5.3,
                                        cb_dia=9.0, cb_depth=5.2, depth=12.0)))
    win.action_hole()
    qapp.processEvents()
    hf = [f for f in win.doc.features if isinstance(f, HoleFeature)][0]
    assert hf.radius == pytest.approx(2.65)       # M5 clearance / 2
    assert hf.cb_radius == pytest.approx(4.5)     # Ø9 cbore / 2
    assert hf.cb_depth == pytest.approx(5.2)
    assert win.doc.result.to_trimesh().is_watertight


def test_action_hole_custom_key_preserves_sketch_circle(win, qapp,
                                                        monkeypatch):
    _plate_with_circle(win, qapp, r=3.0)
    monkeypatch.setattr(HoleDialog, "ask",
                        staticmethod(lambda p, d: _opts(drill=None,
                                                        depth=10.0)))
    win.action_hole()
    hf = [f for f in win.doc.features if isinstance(f, HoleFeature)][0]
    assert hf.radius == pytest.approx(3.0)      # circle rules, as before M107
