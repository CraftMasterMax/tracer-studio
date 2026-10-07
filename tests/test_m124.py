"""M124 — print fit-mode: δ that touches the export, never the model.

The mechanism was chosen against evidence (print_fit_mode.md): holes
are the least accurate FDM feature, slicers compensate them with
dedicated knobs whose SIGN CONVENTIONS WAR (SuperSlicer inverts), and
mesh morphology provably cannot move a hole wall larger than its ball
— so Tracer rewrites the parametric radius inside a context manager
and restores it afterwards. These tests pin the analytic truth.
"""
import math

import pytest

from tracer.core import printfit
from tracer.core.document import (Document, HoleFeature, PrimitiveFeature,
                                  ThreadFeature)


def _plate_holes(radii=(3.0,), extra=()):
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 30, "dy": 30, "dz": 5}))
    x = 5.0
    for i, r in enumerate(radii):
        d.add(HoleFeature(name=f"h{i}", op="subtract",
                          center=(x, 15, 5), normal=(0, 0, -1),
                          radius=r, depth=5.0, cut_length=5.0))
        x += 10.0
    for f in extra:
        d.add(f)
    d.recompute()
    return d


def test_plan_enlarges_holes_and_refuses_small_ones():
    d = _plate_holes(radii=(3.0, 0.3))
    pl = printfit.plan(d, 0.2)
    moved = {e["name"]: (e["r"], e["new_r"]) for e in pl["edits"]}
    assert moved["h0"] == (3.0, pytest.approx(3.2))
    assert any(s["name"] == "h1" and "2δ" in s["reason"]
               for s in pl["skipped"])           # r 0.3 < 2·0.2: refused


def test_plan_never_touches_the_document():
    d = _plate_holes()
    v0 = d.result.volume
    printfit.plan(d, 0.5)
    assert d.result.volume == pytest.approx(v0)
    assert [f.radius for f in d.features
            if isinstance(f, HoleFeature)] == [3.0]


def test_threads_are_honestly_skipped_in_v1():
    th = ThreadFeature(name="thr", op="subtract", center=(25, 15, 5),
                       axis=(0, 0, -1), radius=4.0, pitch=1.0, length=4.0)
    d = _plate_holes(extra=[th])
    pl = printfit.plan(d, 0.2)
    assert any(s["name"] == "thr" and "nominal" in s["reason"]
               for s in pl["skipped"])


def test_compensation_is_the_analytic_hole_growth():
    d = _plate_holes()
    base = d.result.volume
    with printfit.compensated(d, 0.2) as (pl, doc):
        inside = doc.result.volume
    # hole Ø 6→6.4 through 5 mm: loses π(3.2² − 3.0²)·5 more material
    assert base - inside == pytest.approx(math.pi * (3.2**2 - 3.0**2) * 5,
                                          rel=1e-3)
    assert pl["edits"][0]["new_r"] == pytest.approx(3.2)


def test_document_restores_byte_for_byte():
    d = _plate_holes()
    before = [(f.name, f.radius) for f in d.features
              if isinstance(f, HoleFeature)]
    v0 = d.result.volume
    with printfit.compensated(d, 0.2):
        pass
    assert [(f.name, f.radius) for f in d.features
            if isinstance(f, HoleFeature)] == before
    assert d.result.volume == pytest.approx(v0)


def test_restoration_survives_a_crash_inside_the_block():
    d = _plate_holes()
    v0 = d.result.volume
    with pytest.raises(RuntimeError):
        with printfit.compensated(d, 0.2):
            raise RuntimeError("export exploded")
    assert [f.radius for f in d.features
            if isinstance(f, HoleFeature)] == [3.0]
    assert d.result.volume == pytest.approx(v0)


def test_zero_delta_is_a_noop_and_says_as_modelled():
    d = _plate_holes()
    with printfit.compensated(d, 0.0) as (pl, doc):
        assert pl["edits"] == [] and pl["expected"] == ()
        assert doc.result.volume == pytest.approx(d.result.volume)
    assert printfit.describe(printfit.plan(d, 0.0)) == \
        "as-modelled (δ 0 — geometry unchanged)"


def test_union_holes_are_not_moved():
    boss = HoleFeature(name="boss", op="union", center=(25, 25, 0),
                       normal=(0, 0, 1), radius=4.0, depth=5.0,
                       cut_length=5.0)
    d = _plate_holes(extra=[boss])
    pl = printfit.plan(d, 0.2)
    assert [e["name"] for e in pl["edits"]] == ["h0"]   # only subtracts


def test_describe_lists_the_real_numbers():
    d = _plate_holes()
    s = printfit.describe(printfit.plan(d, 0.2))
    assert s.startswith("δ 0.2 mm: h0 Ø 6→6.4"), s


def test_label_notes_advertise_the_drift():
    d = _plate_holes()
    pl = printfit.plan(d, 0.2)
    text = " ".join(pl["expected"])
    assert "holes" in text.lower() and "elephant-foot" in text


def test_cmddialog_honours_combo_defaults():
    """The bug M124 tripped over: ask() silently ignored `default` for
    combos — every multi-combo dialog opened on item 0. The δ menu
    depends on defaults actually landing where the caller says."""
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from tracer.ui import cmddialog
    captured = {}

    def fake_exec(self):
        captured["d"] = self
        return cmddialog.QDialog.DialogCode.Rejected

    monkey = cmddialog.CommandDialog
    real, monkey.exec_ = monkey.exec_, fake_exec
    try:
        cmddialog.ask(None, "t", [
            dict(key="a", kind="combo", label="A",
                 choices=("x", "y", "z"), default="y"),
            dict(key="b", kind="combo", label="B", choices=("p", "q")),
        ])
    finally:
        monkey.exec_ = real
    assert captured["d"]._fields["a"].currentText() == "y"
    assert captured["d"]._fields["b"].currentText() == "p"   # no default = item 0
