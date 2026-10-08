"""M145 — sheet metal SM1: the Flat Pattern, numbers before geometry.

The reprobe (research/sheet_metal_reprobe.md) ran every line of
this rung against our kernel BEFORE the build, and its numbers
are pinned here — one with a correction the contract itself
carried unknowingly: the golden "flat 96.0947" was phrased for
legs measured TO THE APEX, but the p10/p13 builder that produced
it builds legs 60/40 TANGENT-TO-END — the true blank of THAT part
is 100 + BA = 106.094690 (K=0.44) and 106.283185 at K=0.5. The
law itself is shop truth: BA = theta_rad * (ri + K*t) — neutral
fiber measured from the INSIDE face — with K a PROCESS constant
(default 0.44 is folklore, NOT a standard: no ISO 12195 exists and
this repo never cites it). Two laws shape the code: developed
lengths go through the BA LAW, never a mesh arc sum (our band
tessellation's mid-surface is K=0.5 BY CONSTRUCTION — +0.188 mm
per bend of silent error at K=0.44), and the bend facets NEVER
ship in the flat: band-collapse, so the detector's (axis, ri, ro,
angle) + measured flange extents rebuild the blank exactly, and
the K=0.5 mesh-oracle must close back on the arc the mesh really
contains. Closed sections (the band graph has a cycle) need a
user-placed seam the mesh cannot see — an honest RAISE, not a
silent seam.
"""
import math

import numpy as np
import pytest

from tracer.core import sheetmetal
from tracer.core.geometry import Solid

T, RI, LA, LB = 2.0, 3.0, 60.0, 40.0      # the p10/p12/p13 part
RO = RI + T


def _arc(r, cx, cy, a0, a1, n=15):
    th = np.linspace(a0, a1, n + 1)
    return np.column_stack([cx + r * np.cos(th), cy + r * np.sin(th)])


def bent_plate():
    """The probe's part: legs 60/40 tangent-to-end, t=2 ri=3 ro=5,
    one 90 deg band, sheet width 40. Built by the p13 recipe."""
    pts = np.vstack([[[RO, -LA]], _arc(RO, 0, 0, 0, math.pi / 2),
                     [[-LB, RO]], [[-LB, RI]],
                     _arc(RI, 0, 0, math.pi / 2, 0), [[RI, -LA]]])
    return Solid.extrude(pts, height=LB)


def _rounded_square(half, r, n=6):
    c = half - r
    return np.vstack([_arc(r, c, -c, -math.pi / 2, 0, n),
                      _arc(r, c, c, 0, math.pi / 2, n),
                      _arc(r, -c, c, math.pi / 2, math.pi, n),
                      _arc(r, -c, -c, math.pi, 3 * math.pi / 2, n)])


def closed_tube():
    """A sheet tube: the same band geometry, four times, around a
    cycle — SM1 has no seam to cut, so it must REFUSE out loud."""
    outer = _rounded_square(20.0, RO)
    inner = _rounded_square(18.0, RI)
    return Solid.extrude(outer, holes=[inner], height=30.0)


# ---- THE LAW (p12's executed table, digit-for-digit) ---------------

@pytest.mark.parametrize("K,ba", [(0.33, 5.749115), (0.44, 6.094690),
                                  (0.50, 6.283185)])
def test_bend_allowance_is_the_law(K, ba):
    assert sheetmetal.bend_allowance(T, RI, 90.0, K) == pytest.approx(
        ba, abs=5e-4)


def test_deduction_pair():
    # OSSB = tan(A/2)*(ri+t): the OUTSIDE setback; BD = 2*OSSB - BA
    assert sheetmetal.outside_setback(T, RI, 90.0) == pytest.approx(
        5.0, abs=1e-9)
    assert sheetmetal.bend_deduction(T, RI, 90.0, 0.44) == \
        pytest.approx(3.905310, abs=5e-4)


def test_K_outside_the_shop_range_is_refused():
    for bad in (0.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            sheetmetal.bend_allowance(T, RI, 90.0, bad)


# ---- the detector (reprobe §2.1: kernel bands recover to 4dp) ------

def test_detector_finds_the_band_with_true_radii():
    bands = sheetmetal.detect_bands(bent_plate())
    assert len(bands) == 1
    b = bands[0]
    assert b["ri"] == pytest.approx(3.0, abs=1e-3)
    assert b["ro"] == pytest.approx(5.0, abs=1e-3)
    assert b["angle"] == pytest.approx(90.0, abs=1e-4)
    assert abs(abs(b["axis"][2]) - 1.0) < 1e-6      # bend axis || extrude


# ---- the unfold: law-honest blanks, K=0.5 mesh oracle --------------

def test_flat_blank_is_the_law_not_the_mesh_arc():
    u = sheetmetal.unfold_flat(bent_plate(), K=0.44)
    assert u["thickness"] == pytest.approx(2.0, abs=1e-3)
    assert u["ba_total"] == pytest.approx(6.094690, abs=1e-3)
    # 60 + 40 flange extents + BA — NOT the contract's 96.09, which
    # was phrased to-apex; this part's legs are tangent-to-end:
    assert u["flat_length"] == pytest.approx(106.094690, abs=1e-3)


def test_K_half_close_on_the_mesh_mid_surface():
    # the mesh's own neutral fiber is the mid-surface (K=0.5 BY
    # CONSTRUCTION, §1.4): unfolding at K=0.5 must reproduce the
    # arc the tessellation really holds, rad*rmid to 4dp
    u = sheetmetal.unfold_flat(bent_plate(), K=0.5)
    assert u["flat_length"] == pytest.approx(
        100.0 + math.pi / 2 * 4.0, abs=1e-3)


def test_flange_extents_are_measured_not_assumed():
    u = sheetmetal.unfold_flat(bent_plate())
    ext = sorted(f["extent"] for f in u["flanges"])
    assert ext == pytest.approx([40.0, 60.0], abs=1e-3)


# ---- honest refusals ------------------------------------------------

def test_a_box_has_no_bends_and_says_so():
    box = Solid.extrude(np.array([[0.0, 0.0], [30.0, 0.0],
                                  [30.0, 20.0], [0.0, 20.0]]),
                        height=10.0)
    with pytest.raises(sheetmetal.SheetMetalError) as e:
        sheetmetal.unfold_flat(box)
    assert "bend" in str(e.value).lower()


def test_closed_sections_demand_a_seam_loudly():
    with pytest.raises(sheetmetal.SheetMetalError) as e:
        sheetmetal.unfold_flat(closed_tube())
    assert "seam" in str(e.value).lower()


def test_mixed_thickness_is_not_silently_averaged():
    # two bands of different t joined at a shared flange: SM1 draws
    # one line per part, so it REFUSES rather than average (the
    # reprobe §3.4's guard — a mixed chain is a modelling error)
    bands = [dict(ri=3.0, ro=5.0, legkeys=("a", "b")),
             dict(ri=5.0, ro=8.0, legkeys=("b", "c"))]
    with pytest.raises(sheetmetal.SheetMetalError) as e:
        sheetmetal._tree_check(bands)
    assert "thick" in str(e.value).lower()


# ---- the app seam: Tools > Flat Pattern ------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tracer.core.document import PrimitiveFeature  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
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
    w.resize(1200, 800)
    w.show()
    qapp.processEvents()
    w.new_document()
    w.doc.add(PrimitiveFeature(name="block", kind="box",
                               dims={"dx": 30, "dy": 20, "dz": 10}))
    w.recompute()
    qapp.processEvents()
    yield w
    w._unsaved = False          # m56/m63 law: leave no mapped window
    w.close()
    r.ctx.release()
    qapp.processEvents()


def test_action_flat_pattern_refuses_a_bendless_block(win, qapp,
                                                      monkeypatch):
    from tracer.ui import cmddialog
    asked = []
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: asked.append(1) or None)
    win.action_flat_pattern()
    assert not asked                       # refusal BEFORE the dialog
    assert "bend" in win.status.currentMessage().lower()


def test_action_flat_pattern_reports_the_law(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    from PySide6.QtWidgets import QMessageBox
    win.doc._result = bent_plate()         # the probe part as the
    win.doc.dirty = False                  # computed body
    calls = []

    def fake_ask(parent, title, fields):
        calls.append(fields)
        if fields[0]["key"] == "K":
            return {"K": 0.44}
        return {"report": ""}              # report: user clicks OK

    monkeypatch.setattr(cmddialog, "ask", fake_ask)
    # M147 grew the command a second act (offer the paper); this gate
    # is about SM1's report, which must stand WHOLE when declined.
    monkeypatch.setattr(QMessageBox, "question",
                        classmethod(lambda cls, *a, **k: cls.No))
    win.action_flat_pattern()
    assert len(calls) == 2                           # K, then report
    assert calls[0][0]["kind"] == "double"
    assert calls[0][0]["default"] == pytest.approx(0.44)
    assert calls[1][0]["kind"] == "multiline"
    report = calls[1][0]["default"]
    assert "106.09" in report              # THE number, K-honest
    assert "6.09" in report                # and the band's BA
    assert "106.09" in win.status.currentMessage()
    assert win.doc.flat_feature() is None  # declined: no paper, no
    assert "_flat" not in win.doc.body_solids()      # derived body
