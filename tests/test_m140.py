"""M140 — sketch on a face, rung A: attach by DERIVATION,
answer with STATE.

Today a face-pick takes the click POINT as the sketch origin and
the face normal through face_basis — so the frame follows wherever
the finger landed, the gesture hides behind a single silent
double-click, and a refused face (curved, grazing, near an edge)
says NOTHING. The wave sketch probe's verdict, live-verified on
this stack before a line of the milestone shipped: the vendor's
face-sketch frame is DERIVED (its own help calls the algorithm
internal and read-only — never the pick point), the face's edges
auto-project (rung B), and every refusal arrives as state, not
silence. This rung ships the geometry of trust: origin = the
picked BODY's bbox anchor PROJECTED onto the face plane (the
natural corner the body was built from — same face, same frame,
whatever you clicked), a nearest-axis U seeded from the owner
(world X/Y/Z fallback), a body-carrying pick signal ("Sketch on
Stud"), a marking-menu entry for the discoverable route, an
honest reason when a face refuses the pick — and the contact
preset: a FACE sketch over material JOINS, one buried BETWEEN
material CUTS (probed, not guessed), so the pocket intent the
probe ranked first-class arrives as the default, not a checkbox.
"""
import math

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from tracer.core.document import (ExtrudeFeature, PrimitiveFeature)
from tracer.core.sketch.model import SketchModel, face_axes
from tracer.ui.cmddialog import Shell


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
    d = w.doc
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    d.add_body("Stud")                 # the app's New Body record:
    d.add(PrimitiveFeature(name="stud", kind="box", body="Stud",
                           dims={"dx": 10, "dy": 10, "dz": 20}))
    w.recompute()
    qapp.processEvents()
    yield w
    # m63/m56 house law: leave no mapped window behind.  A shown
    # window survives the test and STEALS global mouse delivery —
    # QTest.mouseMove routes through the platform cursor to the
    # window owning the GLOBAL point, so sibling hover tests after
    # this file went blind (m63 cube, m77 magnet — invisible alone,
    # deterministic in-suite).
    w._unsaved = False
    w.close()
    r.close()
    qapp.processEvents()


def screen_of(vp, pt):
    sp = vp._cam.project(pt, vp.width(), vp.height())
    assert sp is not None, "test camera cannot see that point"
    return QPointF(*sp)


def face_sketch(win, point, normal, body):
    win._start_sketch_on_face(np.array(point, float),
                              np.array(normal, float), body)
    return win.sketch.model


# ---- the frame law (pure) -------------------------------------------
def test_face_axes_nearest_axis_law():
    u, v = face_axes((0, 0, 1))
    assert np.allclose(u, (1, 0, 0)) and np.allclose(v, (0, 1, 0))
    u, v = face_axes((1, 0, 0))
    assert np.allclose(u, (0, 1, 0)) and np.allclose(v, (0, 0, 1))
    u, v = face_axes((0, 0, -1))
    assert np.allclose(u, (1, 0, 0)) and np.allclose(v, (0, -1, 0))
    n = (0.0, 1 / math.sqrt(2), 1 / math.sqrt(2))
    u, v = face_axes(n)
    assert abs(float(u @ n)) < 1e-9              # U lies in plane
    assert abs(float(u @ v)) < 1e-9
    assert np.allclose(np.cross(u, v), n)        # right-handed
    # an owner seed only breaks an EXACT tie (Y is uniquely best
    # for the tilted normal; for +Y both X and Z tie at zero):
    u, _ = face_axes((0, 1, 0), owner_u=(0, 0, 1))
    assert np.allclose(u, (0, 0, 1))


# ---- derived, never clicked (the complaint's cure) -------------------
def test_frame_is_derived_not_clicked(win, qapp):
    m = face_sketch(win, (17.3, 22.9, 20.0), (0, 0, 1), "Stud")
    assert m.plane == "FACE"
    assert np.allclose(m.origin, (0, 0, 20))
    assert np.allclose(m.axes[0], (1, 0, 0))
    assert np.allclose(m.axes[1], (0, 1, 0))
    assert m.name == "Sketch on Stud"


def test_same_face_same_frame_whatever_the_click(win, qapp):
    a = face_sketch(win, (17.3, 22.9, 20.0), (0, 0, 1), "Stud")
    b = face_sketch(win, (1.0, 2.0, 20.0), (0, 0, 1), "Stud")
    assert tuple(a.origin) == tuple(b.origin)
    assert a.axes == b.axes


def test_committed_host_sketch_names_count_up(win, qapp,
                                              monkeypatch):
    monkeypatch.setattr(Shell, "getDouble", lambda *a, **k:
                        (4.0, True))
    m = face_sketch(win, (5.0, 5.0, 20.0), (0, 0, 1), "Stud")
    outer = np.array([[2, 2], [8, 2], [8, 8], [2, 8], [2, 2]],
                     float)
    win._on_profiles([(outer, [])], m.name)
    assert win.doc.features[-1].name == "Sketch on Stud"
    m2 = face_sketch(win, (5.0, 5.0, 20.0), (0, 0, 1), "Stud")
    assert m2.name == "Sketch on Stud 2"


# ---- answer with state (no more silent refusal) ----------------------
def test_face_probe_answers_with_state(win, qapp):
    vp = win.viewport
    hit, why = vp.face_probe(screen_of(vp, (5, 5, 20)))
    assert hit is not None and why is None
    assert hit["body"] == "Stud"
    assert abs(float(np.dot(np.array(hit["normal"]),
                            (0, 0, 1)))) > 0.99
    # on the plate's rim the +-10 px neighbourhood straddles two
    # faces: refusal is a SENTENCE now, never a shrug
    hit2, why2 = vp.face_probe(screen_of(vp, (40.0, 15.0, 6.0)))
    assert hit2 is None and why2 and "flat" in why2.lower()
    # empty space stays silent — the dbl-click fallthrough law
    hit3, why3 = vp.face_probe(QPointF(2, 2))
    assert hit3 is None and why3 is None


def test_dblclick_carries_the_body(win, qapp):
    seen = []
    # M141: the pick also carries the TRIANGLE (rung B-lite reads the
    # face group from it — the index M140 stopped throwing away).
    win.viewport.face_picked.connect(
        lambda p, n, b, t: seen.append((b, t)))
    pos = screen_of(win.viewport, (5, 5, 20))
    ev = QMouseEvent(QEvent.Type.MouseButtonDblClick, pos, pos,
                     pos, Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    win.viewport.mouseDoubleClickEvent(ev)
    assert seen and seen[0][0] == "Stud"
    assert isinstance(seen[0][1], int)


def test_marking_menu_offers_face_on_planar_hit(win, qapp):
    # The law lives in the BUILDER: _show_marking_menu pops exactly
    # what _marking_menu builds (QMenu(self), no show needed to own
    # the actions).  Popping real menus per test would only add
    # transient top-levels — the popup path itself is m56's ground.
    sp = screen_of(win.viewport, (5, 5, 20))
    menu = win._marking_menu(QPoint(sp.toPoint()))
    labels = [a.text().replace("&", "") for a in menu.actions()
              if a.text()]
    assert any(l.startswith("Sketch on Face") and "Stud" in l
               for l in labels)
    menu = win._marking_menu(QPoint(2, 2))
    labels = [a.text().replace("&", "") for a in menu.actions()
              if a.text()]
    assert not any(l.startswith("Sketch on Face") for l in labels)


# ---- the contact preset (probe, don't guess) -------------------------
def test_face_extrude_over_material_still_joins(win, qapp,
                                                monkeypatch):
    monkeypatch.setattr(Shell, "getDouble", lambda *a, **k:
                        (4.0, True))
    win.doc.active_body = "Body 1"     # the host body is the stream
    m = face_sketch(win, (20.0, 10.0, 6.0), (0, 0, 1), "Body 1")
    outer = np.array([[15, 2], [25, 2], [25, 12], [15, 12],
                      [15, 2]], float)
    v0 = win.doc.result.volume
    win._on_profiles([(outer, [])], m.name)
    f = win.doc.features[-1]
    assert isinstance(f, ExtrudeFeature) and f.op == "union"
    assert abs(win.doc.result.volume - (v0 + 400.0)) < 1e-6


def test_face_extrude_between_material_cuts(win, qapp,
                                            monkeypatch):
    monkeypatch.setattr(Shell, "getDouble", lambda *a, **k:
                        (4.0, True))
    win.doc.active_body = "Body 1"     # the pocket cuts its host body
    m = SketchModel(plane="FACE")
    m.axes = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    m.origin = (20.0, 15.0, 3.0)          # buried in the plate
    m.name = "Buried"
    win.sketch.set_model(m)
    outer = np.array([[-5, -5], [5, -5], [5, 5], [-5, 5],
                      [-5, -5]], float)
    v0 = win.doc.result.volume
    win._on_profiles([(outer, [])], m.name)
    f = win.doc.features[-1]
    assert f.op == "subtract"
    assert abs(win.doc.result.volume - (v0 - 300.0)) < 1e-6


def test_plane_sketches_ride_the_old_law(win, qapp,
                                         monkeypatch):
    monkeypatch.setattr(Shell, "getDouble", lambda *a, **k:
                        (2.0, True))
    win.action_new_sketch("XY")
    m = win.sketch.model
    assert m.plane == "XY" and m.origin == (0.0, 0.0, 0.0)
    outer = np.array([[50, 50], [60, 50], [60, 60], [50, 60],
                      [50, 50]], float)
    v0 = win.doc.result.volume
    win._on_profiles([(outer, [])], m.name)
    f = win.doc.features[-1]
    assert f.op == "union"
    assert abs(win.doc.result.volume - (v0 + 200.0)) < 1e-6
