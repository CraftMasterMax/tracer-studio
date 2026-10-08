"""M135 — section view: a named plane cutting the DISPLAY.

The wave-9 probe's headline, live-tested before a line shipped:
trimesh 5.1.1's `slice_plane(cap=True)` returns a WATERTIGHT CAPPED
half-mesh out of the box (manifold3d, already our kernel's dependency,
is the triangulation engine — no new packaging decision at all), and
it handles the hard case — a cut through a bore axis, whose cap is an
annulus — with the volume landing on the analytic answer. So the
geometry cost was zero and this milestone is honest wiring:

* the cut rides a plane BY NAME (origin or stored datum), so M130's
  rename-is-a-relink law had to learn a new limb — the live section
  relinks with the count;
* every EFFECTIVE-visible body is sliced separately and restitched in
  browser order (per-body slicing is forced upstream anyway), so M134
  isolation still rules while cut;
* the cut faces wear the accent colour — the vendor's default that a
  section reads differently from the skin, and the only colour the
  cap ever needs;
* face IDENTITY is the model's mesh, not the cut's, so hover, picks,
  press-pull, sketch-on-face, box-select and re-pivot all go quiet
  together at one choke (_shoot), and Esc's ladder is gestures → cut
  → selection → isolation;
* section is SESSION view state: never saved, like isolation — the
  model file stays the model.
"""
import math

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMenu

from tracer.core.document import Document, HoleFeature, PrimitiveFeature


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def plate_and_bore():
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    d.add(HoleFeature(name="bore", op="subtract", center=(20, 15, 6),
                      normal=(0, 0, -1), radius=5.0, depth=6,
                      cut_length=6, through=True))
    return d


def as_mesh(stitched):
    from trimesh import Trimesh
    v, n, f = stitched[:3]
    return Trimesh(vertices=v, faces=f, process=False)


# ---- the cut itself ---------------------------------------------------------

def test_the_cut_keeps_the_half_the_normal_points_into():
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    p = d.add_plane("YZ", offset=10.0)          # x = 10, normal +x
    d.set_section(p["name"])
    assert d.section_active()
    st, rng = d.sectioned_display()
    assert rng == []                            # no identity travels
    m = as_mesh(st)
    assert m.is_watertight                      # capped, not a shell
    assert m.volume == pytest.approx(30 * 30 * 6, rel=1e-6)
    d.set_section(p["name"], flip=True)         # the other half now
    st, _ = d.sectioned_display()
    assert as_mesh(st).volume == pytest.approx(10 * 30 * 6, rel=1e-6)


def test_a_cut_through_a_bore_axis_caps_the_hole_and_colours_the_cut():
    d = plate_and_bore()                        # 7200 - pi*25*6 solid
    d.set_section("YZ")                         # x=0 keeps all...
    d.set_section(d.add_plane("YZ", offset=20.0)["name"])
    # ...now x=20, exactly through the bore axis: the cap is an annulus
    st, _ = d.sectioned_display()
    m = as_mesh(st)
    assert m.is_watertight
    expect = (7200 - math.pi * 25 * 6) / 2
    assert m.volume == pytest.approx(expect, rel=1e-3)
    v, fc = st[0], st[3]
    on_plane = np.abs((v[st[2]] - np.array([20.0, 0.0, 0.0]))
                      @ np.array([1.0, 0.0, 0.0])) < 1e-3
    cap_rows = np.all(on_plane, axis=1)
    assert cap_rows.any()                       # there IS a cut face
    cap = np.asarray((0.16, 0.55, 0.85), np.float32)
    assert np.allclose(fc[cap_rows], cap)       # it wears the accent...
    assert not np.any(np.allclose(fc[~cap_rows], cap))  # ...and nothing
    #                                          # else does


def test_the_cut_respects_isolation_and_visibility():
    d = plate_and_bore()
    d.add_body("Stud")
    d.add(PrimitiveFeature(name="stud", kind="box",
                           dims={"dx": 5, "dy": 5, "dz": 15},
                           placement=(34, 24, 6)))
    d.isolate(["Stud"])                         # plate suppressed (M134)
    d.set_section(d.add_plane("YZ", offset=32.0)["name"])
    st, _ = d.sectioned_display()
    own = d.body_solids()["Stud"].to_trimesh() \
        .slice_plane((32.0, 0, 0), (1, 0, 0), cap=True)
    assert len(st[2]) == len(own.faces)         # ONLY the stud's half
    # the section plane's own datum rename follows (test below)


def test_renaming_the_cut_plane_relinks_the_living_cut():
    d = plate_and_bore()
    p = d.add_plane("YZ", offset=20.0)
    d.set_section(p["name"])
    n = d.rename_datum(p["name"], "MidCut")     # M130's law, new limb
    assert n == 1
    assert d.section_plane() == "MidCut"
    st, _ = d.sectioned_display()               # still cuts at x=20...
    assert as_mesh(st).volume == pytest.approx(
        (7200 - math.pi * 25 * 6) / 2, rel=1e-3)


def test_an_unknown_plane_refuses_the_cut_and_changes_nothing():
    d = plate_and_bore()
    with pytest.raises(Exception):
        d.set_section("Nowhere")
    assert not d.section_active()
    assert d.clear_section() is False


def test_the_cut_is_session_state_never_saved():
    d = plate_and_bore()
    d.set_section(d.add_plane("YZ", offset=20.0)["name"])
    blob = d.to_dict()
    assert not any("section" in k for k in blob)
    d2 = Document.from_dict(blob)
    assert not d2.section_active()
    assert d2.section_plane() is None           # honest eyes on load


# ---- the UI surface ---------------------------------------------------------

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
    w.doc.add(PrimitiveFeature(name="plate", kind="box",
                               dims={"dx": 40, "dy": 30, "dz": 6}))
    w.recompute()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


def _menu_labels(win, name, monkeypatch):
    menus = []
    monkeypatch.setattr(QMenu, "exec_",
                        lambda menu, pos: menus.append(menu))
    win._cplane_menu(name, QPoint(10, 10))
    return [a.text() for a in menus[-1].actions()]


def test_plane_rows_offer_the_cut_with_honest_gating(win, monkeypatch):
    # stored datum: cut AND the M130 rename/delete it always had
    pl = win.doc.add_plane("YZ", offset=20.0)["name"]
    win.rail.tree.reload()
    labels = _menu_labels(win, pl, monkeypatch)
    assert "Section: cut here" in labels
    assert "Rename…" in labels and "Delete construction plane" in labels
    assert "Flip section" not in labels          # no cut yet
    # origin plane: cut yes — rename/delete no (it is not ours to kill)
    labels = _menu_labels(win, "XY", monkeypatch)
    assert "Section: cut here" in labels
    assert "Rename…" not in labels and "Delete" not in " ".join(labels)
    # while this plane IS the cut: flip joins clear
    win._section_here("XY")
    labels = _menu_labels(win, "XY", monkeypatch)
    assert "Flip section" in labels and "Clear section" in labels
    labels = _menu_labels(win, pl, monkeypatch)   # another plane: clear
    assert "Flip section" not in labels           # only, never flip
    assert "Clear section" in labels


def test_esc_ladder_cut_yields_before_selection_and_isolation(win,
                                                              qapp):
    vp = win.viewport
    win._section_here("XY")
    win.doc.isolate(["Body 1"])                  # both session modes
    qapp.processEvents()
    esc = lambda: vp.keyPressEvent(              # noqa: E731
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape,
                  Qt.KeyboardModifier.NoModifier))
    esc()
    assert not win.doc.section_active()          # the cut goes first...
    assert win.doc.isolation_active()            # ...isolation survives
    esc()
    assert not win.doc.isolation_active()        # ...then its own Esc


def test_picks_are_suspended_while_the_model_is_cut(win, qapp):
    vp = win.viewport
    win.action_view("iso")
    win.action_view("fit")
    qapp.processEvents()
    cx, cy = vp.width() / 2, vp.height() / 2
    win._section_here("XY")                       # z=0, keeps z>0: the
    qapp.processEvents()                          # whole plate remains
    assert vp._shoot(vp._tm, cx, cy) is None      # yet nothing can pick
    win._flip_section()                           # keep z<0: nothing
    qapp.processEvents()                          # survives the cut
    st_faces = 0 if vp._tm is None else len(vp._tm.faces)
    assert st_faces == 0
    win._clear_section()
    qapp.processEvents()
    assert vp._shoot(vp._tm, cx, cy) is not None  # picks are back


def test_the_status_bar_narrates_the_verb(win, qapp):
    win._section_here("XY")
    qapp.processEvents()
    assert "Section on XY" in win.status.currentMessage()
    win._flip_section()
    qapp.processEvents()
    assert "flipped" in win.status.currentMessage()
    win._clear_section()
    qapp.processEvents()
    assert "Section cleared" in win.status.currentMessage()
