"""M141 — sketch on a face, rung B-lite: the loop LANDS.

The vendor law the probe live-verified: face edges auto-project the
moment a face sketch opens — construction-but-dimensionable, and
REPLACED not stacked. M140 froze the frame by derivation; this rung
lands the HOST FACE's own boundary (outer + its holes, per ASME
"the face you drew on is the one that speaks") as M82 refs, mapped
into the derived sketch frame. The source is NOT the plane-slice
(project() cuts the whole doc at that height and catches the boss
standing there too) — it is face_region() over the picked face's
coplanar-ADJACENCY group (M59's _gid: disjoint coplanar faces never
merge, so the plate-top loop is the plate's, not the world's). The
pick chain finally uses the triangle index M140 stopped throwing
away: probe -> tri -> _group -> face_region -> refs. project()
stays the user's opt-in cross-section and still REPLACES (a P
after the landing re-includes, never duplicates).
"""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from tracer.core.document import HoleFeature, PrimitiveFeature
from tracer.core.sketch.model import SketchModel


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
    d.add_body("Stud")
    d.add(PrimitiveFeature(name="stud", kind="box", body="Stud",
                           dims={"dx": 10, "dy": 10, "dz": 20}))
    w.recompute()
    qapp.processEvents()
    yield w
    w._unsaved = False          # m63/m56 law: leave no mapped window
    w.close()
    r.ctx.release()
    qapp.processEvents()


def screen_of(vp, pt):
    sp = vp._cam.project(pt, vp.width(), vp.height())
    assert sp is not None, "test camera cannot see that point"
    from PySide6.QtCore import QPointF
    return QPointF(*sp)


def face_sketch_at(win, world):
    """The real chain: probe (which knows the tri) -> slot."""
    hit, why = win.viewport.face_probe(screen_of(win.viewport, world))
    assert hit is not None, why
    win._start_sketch_on_face(hit["point"], hit["normal"],
                              hit["body"], hit.get("tri"))
    return win.sketch.model


def test_host_face_loop_lands_at_start(win, qapp):
    m = face_sketch_at(win, (20.0, 15.0, 6.0))       # plate top
    assert m.plane == "FACE"
    assert len(m.refs) == 1, m.refs
    assert m.refs[0]["closed"]
    got = {tuple(np.round(p).astype(int)) for p in m.refs[0]["pts"]}
    assert got == {(0, 0), (40, 0), (40, 30), (0, 30)}


def test_disjoint_coplanar_faces_never_merge(win, qapp):
    # stud top (z=20) is a different logical face than plate top
    # (z=6); the stud's loop lands in ITS OWN frame: origin (0,0,20)
    m = face_sketch_at(win, (5.0, 5.0, 20.0))
    assert len(m.refs) == 1
    got = {tuple(np.round(p).astype(int)) for p in m.refs[0]["pts"]}
    assert got == {(0, 0), (10, 0), (10, 10), (0, 10)}


def test_a_hole_in_the_face_lands_too(win, qapp):
    win.doc.active_body = "Body 1"
    win.doc.add(HoleFeature(name="bore", op="subtract",
                            center=(30.0, 20.0, 6.0),
                            normal=(0.0, 0.0, -1.0), radius=3.0,
                            through=True, cut_length=50.0))
    win.recompute()
    qapp.processEvents()
    m = face_sketch_at(win, (20.0, 5.0, 6.0))        # plate top, far
    assert len(m.refs) == 2, "outer + the bore"      # from the bore
    ring = m.refs[1] if len(m.refs[1]["pts"]) > 8 else m.refs[0]
    c = ring["pts"].mean(axis=0)
    assert np.allclose(c, (30.0, 20.0), atol=0.1)
    r = np.hypot(*(ring["pts"] - c).T).max()
    assert abs(r - 3.0) < 0.1                        # tessellated bore


def test_project_replaces_never_stacks(win, qapp):
    tm = win.viewport._tm
    m = face_sketch_at(win, (20.0, 15.0, 6.0))       # 1 landed ring
    n = m.project(np.asarray(tm.vertices, float),
                  np.asarray(tm.faces, np.int64))    # the P key
    # M82's slice grazes a hair off-plane and honestly catches the
    # boss section above the plate top; the LAW under test is the
    # one the probe pinned: re-include REPLACES, never duplicates.
    assert n >= 1 and len(m.refs) == n


def test_plane_sketches_stay_unprojected(win, qapp):
    win.action_new_sketch("XY")
    assert win.sketch.model.refs == []               # M82 law kept:
    #                                             opt-in project


def test_legacy_call_without_tri_is_honest(win, qapp):
    # body=None + no tri (the old arity): frame still derives, no
    # loop, no crash
    m1 = win.sketch.model
    win._start_sketch_on_face(np.array([20.0, 15.0, 6.0]),
                              np.array([0.0, 0.0, 1.0]))
    m = win.sketch.model
    assert m.plane == "FACE" and m.refs == []
    assert np.allclose(m.origin, (20.0, 15.0, 6.0))
    # no body -> the M140 fallback: the plane's own point, honestly
