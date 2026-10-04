"""M18: true 3D body fillet/chamfer through the OpenCascade bridge.

Core = BodyFilletFeature (replaces the accumulated body; bakes its result
so recompute is fast and the file survives OCCT loss). UI = Modify menu +
parametric size editing + tree/timeline glyphs.
"""
import json
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QInputDialog       # noqa: E402

from tracer.core import step                                   # noqa: E402
from tracer.core.document import (BodyFilletFeature,           # noqa: E402
                                  Document, PrimitiveFeature)

requires_occt = pytest.mark.skipif(
    not step.available(), reason="OpenCascade not available")


def box_doc(radius=3.0, chamfer=False):
    d = Document(title="filly")
    d.features.append(PrimitiveFeature(name="Box1", kind="box",
                                       dims={"dx": 40, "dy": 25, "dz": 10}))
    d.features.append(BodyFilletFeature(name="Fillet1", radius=radius,
                                        chamfer=chamfer))
    return d


def rounded_box_volume(a, b, c, r):
    """Exact volume of a box with ALL edges filleted at r (r <= c/2)."""
    edge_loss = r * r * (1 - math.pi / 4) * 4 * ((a - 2 * r) + (b - 2 * r)
                                                 + (c - 2 * r))
    corner_loss = 8 * r ** 3 * (1 - math.pi / 6)
    return a * b * c - edge_loss - corner_loss


# ---- kernel --------------------------------------------------------------------
@requires_occt
def test_body_fillet_matches_analytic_rounded_box():
    d = box_doc(3.0)
    v = d.recompute()
    ideal = rounded_box_volume(40, 25, 10, 3)
    assert v.volume == pytest.approx(ideal, rel=0.01)   # sag of mesh <1%
    tm = v.to_trimesh()
    assert tm.is_watertight
    bb = v.bounding_box
    assert bb[0][0] == pytest.approx(0.0, abs=0.3)      # bbox kept
    assert bb[1][0] == pytest.approx(40.0, abs=0.3)


@requires_occt
def test_body_chamfer_cuts_deeper_than_fillet():
    vf = box_doc(3.0).recompute().volume
    vc = box_doc(3.0, chamfer=True).recompute().volume
    assert vc < vf   # straight bevel removes more corner material


@requires_occt
def test_fillet_result_is_cached_across_recomputes(monkeypatch):
    d = box_doc()
    calls = []
    real = step.fillet_mesh

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(step, "fillet_mesh", counting)
    d.recompute()
    d.dirty = True
    d.recompute()          # same source, same radius -> cache hit
    assert len(calls) == 1


@requires_occt
def test_oversized_radius_surfaces_error_not_stale_result():
    d = box_doc(2.0)
    good = d.recompute().volume
    f = d.features[1]
    f.radius = 500.0
    with pytest.raises(RuntimeError):
        d.recompute()                       # must NOT quietly return `good`


@requires_occt
def test_baked_result_survives_save_load_and_occt_loss():
    d = box_doc(3.0)
    v = d.recompute().volume
    d2 = Document.from_dict(json.loads(json.dumps(d.to_dict())))

    def dead(*a, **k):
        raise RuntimeError("occt gone")
    orig_mesh, orig_avail = step.fillet_mesh, step.available
    step.fillet_mesh = dead
    try:
        assert d2.recompute().volume == pytest.approx(v)  # fresh key hit
        # now the upstream changes: key no longer matches, and OCCT is
        # absent -> the baked fallback must carry the part (Fusion shows
        # the last good tessellation too)
        d2.features[0].dims["dz"] = 12.0
        d2.dirty = True
        step.available = lambda: False
        assert d2.recompute().volume == pytest.approx(v)
    finally:
        step.fillet_mesh, step.available = orig_mesh, orig_avail


def test_fillet_first_feature_is_rejected():
    d = Document()
    d.features.append(BodyFilletFeature(name="F1"))
    with pytest.raises(ValueError, match="no body to fillet"):
        d.recompute()


@requires_occt
def test_suppress_fillet_restores_plain_body():
    d = box_doc(3.0)
    d.recompute()
    f = d.features[1]
    f.suppressed = True
    d.dirty = True
    assert d.recompute().volume == pytest.approx(10000.0)


# ---- UI --------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


@requires_occt
def test_modify_menu_flow_creates_fillet_feature(win, qapp, monkeypatch):
    labels = [a.text() for a in win.menuBar().actions()]
    assert any("dify" in l.replace("&", "") for l in labels)
    win.new_document()
    win.doc.features.append(PrimitiveFeature(name="B", kind="box",
                                             dims={"dx": 30, "dy": 30,
                                                   "dz": 6}))
    win.doc.dirty = True
    base = win.doc.recompute().volume
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (2.0, True)))
    win._body_fillet(chamfer=False)
    qapp.processEvents()
    f = win.doc.features[-1]
    assert isinstance(f, BodyFilletFeature) and f.radius == 2.0
    assert win.doc.result.volume < base
    # tree + timeline pick up the ⌒/◐ identity
    assert win.timeline.bar._label(f).startswith("\u2312")


@requires_occt
def test_fillet_cancel_and_failure_paths(win, qapp, monkeypatch):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(name="B", kind="box",
                                             dims={"dx": 30, "dy": 30,
                                                   "dz": 6}))
    win.doc.dirty = True
    win.doc.recompute()
    # cancel at the size prompt -> no feature added
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (0.0, False)))
    win._body_fillet(chamfer=False)
    assert not any(isinstance(f, BodyFilletFeature)
                   for f in win.doc.features)
    # absurd radius -> warning box, feature rolled back
    from PySide6.QtWidgets import QMessageBox
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a[1])))
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (500.0, True)))
    win._body_fillet(chamfer=False)
    assert warned == ["Fillet failed"]
    assert not any(isinstance(f, BodyFilletFeature)
                   for f in win.doc.features)
    assert win.doc.result.volume == pytest.approx(30 * 30 * 6)


@requires_occt
def test_double_click_fillet_reopens_size_dialog(win, qapp, monkeypatch):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(name="B", kind="box",
                                             dims={"dx": 30, "dy": 30,
                                                   "dz": 6}))
    win.doc.dirty = True
    win.doc.recompute()
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (1.5, True)))
    win._body_fillet(chamfer=False)
    f = win.doc.features[-1]
    v15 = win.doc.result.volume
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (2.5, True)))
    win._feature_activated(f)          # timeline double-click path
    qapp.processEvents()
    assert f.radius == 2.5
    assert win.doc.result.volume < v15


@requires_occt
def test_properties_panel_reports_fillet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(name="B", kind="box",
                                             dims={"dx": 30, "dy": 30,
                                                   "dz": 6}))
    win.doc.dirty = True
    win.doc.recompute()
    from PySide6.QtWidgets import QInputDialog
    orig = QInputDialog.getDouble
    QInputDialog.getDouble = staticmethod(lambda *a, **k: (1.0, True))
    try:
        win._body_fillet(chamfer=False)
    finally:
        QInputDialog.getDouble = orig
    f = win.doc.features[-1]
    win.rail.props.show_feature(f)
    html = win.rail.props._body.text()
    assert "fillet: 1 mm on all sharp edges" in html
    assert "baked triangles" in html
