"""M49b — external threads: pick a cylindrical boss face, choose an
ISO size, get real bolt threads.

Pins the core cutter (helix_ridge: watertight, cuts pitch/2 deep, needs
a sane core), the cylinder recogniser (axis-agnostic fit; flat/conical
patches refused), smooth-region growth (a click is one facet; the
thread needs the whole wall), and the command end-to-end: boss wall
selected -> dialog -> ThreadFeature -> watertight bolt, with the JSON
round-trip carrying it all.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

from tracer.core.document import (Document, PrimitiveFeature,        # noqa: E402
                                  ThreadFeature)
from tracer.core.geometry import Solid                               # noqa: E402
from tracer.core.thread import (ISO_COARSE, fit_cylinder,            # noqa: E402
                                helix_ridge)


# ---- core: the ridge cutter ------------------------------------------------------

def test_ridge_is_watertight_and_fits_over_the_major():
    g = helix_ridge(4.0, 1.25, 12.0)
    assert g.to_trimesh().is_watertight
    bb = g.bounding_box
    dia = bb[1][0] - bb[0][0]
    assert 8.0 < dia < 8.3                    # embeds past the crest


def test_ridge_cuts_a_bolt():
    bolt = Solid.cylinder(4.0, 14.0)
    cut = bolt.subtract(helix_ridge(4.0, 1.25, 14.0))
    assert cut.to_trimesh().is_watertight
    assert 0 < bolt.volume - cut.volume < bolt.volume * 0.5


def test_ridge_refuses_to_eat_the_core():
    with pytest.raises(ValueError):
        helix_ridge(0.5, 1.75, 10.0)          # minor would go negative


# ---- core: cylinder recognition ---------------------------------------------------

def _wall_samples(radius=5.0, height=20.0):
    tm = Solid.cylinder(radius, height).to_trimesh()
    fn = np.asarray(tm.face_normals, float)
    wall = np.abs(fn[:, 2]) < 0.7
    tris = np.asarray(tm.faces)[wall]
    return (tm.vertices[tris].reshape(-1, 3),
            np.repeat(fn[wall], 3, axis=0))


def test_fit_finds_a_straight_cylinder():
    fit = fit_cylinder(*_wall_samples())
    assert fit is not None
    assert fit["radius"] == pytest.approx(5.0, abs=0.05)
    assert np.allclose(np.abs(fit["axis"]), (0, 0, 1), atol=0.02)
    assert fit["zmax"] - fit["zmin"] == pytest.approx(20.0, abs=0.05)


def test_fit_is_axis_agnostic():
    R = np.array([[0., 0, 1], [0, 1, 0], [-1, 0, 0]])   # z -> x
    M = np.eye(4)
    M[:3, :3] = R
    tm = Solid.cylinder(3.0, 12.0).transformed(M).to_trimesh()
    fn = np.asarray(tm.face_normals, float)
    wall = np.abs(fn @ np.array([1.0, 0, 0])) < 0.7
    tris = np.asarray(tm.faces)[wall]
    fit = fit_cylinder(tm.vertices[tris].reshape(-1, 3),
                       np.repeat(fn[wall], 3, axis=0))
    assert fit is not None
    assert fit["radius"] == pytest.approx(3.0, abs=0.05)
    assert np.allclose(np.abs(fit["axis"]), (1, 0, 0), atol=0.02)


def test_fit_refuses_flat_patches():
    d = Document("b")
    d.add(PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 30, "dy": 30, "dz": 5}))
    tm = d.recompute().to_trimesh()
    fn = np.asarray(tm.face_normals, float)
    flat = np.abs(fn[:, 2]) > 0.99
    tris = np.asarray(tm.faces)[flat]
    assert fit_cylinder(tm.vertices[tris].reshape(-1, 3),
                        np.repeat(fn[flat], 3, axis=0)) is None


# ---- document: the feature survives JSON -----------------------------------------

def test_thread_feature_json_round_trip():
    d = Document("bolt")
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 24, "dy": 24, "dz": 8}))
    d.add(PrimitiveFeature(name="boss", kind="cylinder",
                           dims={"radius": 4.0, "height": 12},
                           placement=(12, 12, 8.0), op="union"))
    d.recompute()
    d.add(ThreadFeature(name="Thread M8", op="subtract",
                        center=(12, 12, 8), axis=(0, 0, 1),
                        radius=4.0, pitch=1.25, length=12.0))
    vol = d.recompute().volume
    assert d.result.to_trimesh().is_watertight
    d2 = Document.from_dict(d.to_dict())
    tf = [f for f in d2.features if isinstance(f, ThreadFeature)][0]
    assert (tf.name, tf.pitch, tf.radius) == ("Thread M8", 1.25, 4.0)
    assert d2.recompute().volume == pytest.approx(vol, abs=1)


# ---- UI: selection -> dialog -> feature --------------------------------------------

from conftest import feature_rows                                    # noqa: E402
from tracer.ui import cmddialog                                      # noqa: E402
from tracer.ui.mainwindow import MainWindow                          # noqa: E402
from tracer.ui.renderer import SceneRenderer                         # noqa: E402


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


def _boss_doc(win):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 8}))
    win.doc.add(PrimitiveFeature(name="boss", kind="cylinder",
                                 dims={"radius": 4.0, "height": 12},
                                 placement=(20, 20, 8.0), op="union"))
    win.recompute()
    win.viewport.refresh()


def _pick_boss_wall(win):
    tm = win.viewport._tm
    fn = np.asarray(tm.face_normals, float)
    fc = tm.vertices[np.asarray(tm.faces, int)].mean(1)
    r = np.hypot(fc[:, 0] - 20, fc[:, 1] - 20)
    wall = np.flatnonzero((np.abs(fn[:, 2]) < 0.7) & (np.abs(r - 4.0) < 0.3))
    assert len(wall) > 4
    win.viewport._sel = [int(wall[0])]
    return wall


@pytest.fixture
def silent_boxes(monkeypatch):
    """No real message boxes: record which ones fired."""
    fired = []
    for kind in ("information", "warning"):
        monkeypatch.setattr(
            QMessageBox, kind,
            staticmethod(lambda *a, k=kind, **k2: fired.append(k)))
    return fired


def test_click_on_one_faclet_threads_the_whole_wall(win, qapp, monkeypatch,
                                                    silent_boxes):
    _boss_doc(win)
    _pick_boss_wall(win)
    seen = {}

    def fake_ask(parent, title, fields, **kw):
        seen["title"] = title
        return {"size": "M8 × 1.25"}
    monkeypatch.setattr(cmddialog, "ask", fake_ask)
    before = win.doc.result.volume
    win.action_thread()
    qapp.processEvents()
    assert not silent_boxes, silent_boxes
    assert "Ø 8" in seen["title"] and "M8" in seen["title"]   # boss Ø + hint
    tf = [f for f in win.doc.features if isinstance(f, ThreadFeature)]
    assert len(tf) == 1 and tf[0].name == "Thread M8"
    assert tf[0].radius == pytest.approx(4.0, abs=0.05)
    assert tf[0].pitch == pytest.approx(1.25)
    assert tf[0].length == pytest.approx(12.0, abs=0.6)
    s = win.doc.result
    assert s.to_trimesh().is_watertight
    assert s.volume < before - 1.0                 # real ridge came off
    assert "Thread M8" in win.status.currentMessage()


def test_flat_face_is_refused_before_the_dialog(win, qapp, monkeypatch,
                                                silent_boxes):
    _boss_doc(win)
    tm = win.viewport._tm
    fn = np.asarray(tm.face_normals, float)
    top = int(np.argmax(fn[:, 2]))                 # plate top facet
    win.viewport._sel = [top]

    def boom(*a, **k):
        raise AssertionError("dialog must not open for a flat face")
    monkeypatch.setattr(cmddialog, "ask", boom)
    win.action_thread()
    qapp.processEvents()
    assert silent_boxes == ["information"]
    assert not [f for f in win.doc.features
                if isinstance(f, ThreadFeature)]


def test_smooth_region_grabs_the_whole_wall(win, qapp):
    _boss_doc(win)
    wall = _pick_boss_wall(win)
    region = win.viewport.smooth_region(wall[0])
    tm = win.viewport._tm
    fn = np.asarray(tm.face_normals, float)
    assert len(region) >= 8                        # many facets, not one
    assert all(abs(fn[f][2]) < 0.7 for f in region)  # wall only, no caps


def test_thread_shows_in_browser_and_inspector(win, qapp, monkeypatch):
    _boss_doc(win)
    _pick_boss_wall(win)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"size": "M10 × 1.5"})
    win.action_thread()
    qapp.processEvents()
    tf = [f for f in win.doc.features if isinstance(f, ThreadFeature)][0]
    rows = [r.text(0) for r in feature_rows(win)]
    assert any(r.endswith("Thread M10") and "\u2240" in r for r in rows)
    win.rail.props.show_feature(tf)
    html = win.rail.props._body.text()
    assert "external thread" in html and "pitch 1.5" in html
    assert "major: \u00d88" in html and "minor: \u00d86.5" in html
