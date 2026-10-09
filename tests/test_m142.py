"""M142 — sketch on a face, rung C: the attachment SURVIVES
recompute.

Rungs A+B froze a derived frame + landed loop at pick time; the
honest weakness the probe named (§7) is that frozen numbers lie
once the model moves. The vendor's answer (read from its own
recovery strings): the sketch carries a RELATIONSHIP and rebuilds
against it — and when the face is gone it says "Cache is used",
keeping the last good frame rather than blanking geometry. We
clone that shape with the handle the mesh kernel can honour: a
SEMANTIC FaceHandle {"feature": name, "part": "cap-top"|...} —
because our features PUBLISH their cap planes algebraically
(extrude caps = placement(+h·n), box/cylinder caps = the z faces
of their dims, placement-offset honoured), so resolution is pure
arithmetic at current parameters, never a mesh search. The fold
re-derives frame + side (a pocket keeps cutting INTO the face it
follows) before consuming a handled extrude; anything that fails
to resolve keeps its frozen frame — the cache law, silent but
never false. No publisher => no handle => today's byte-identical
snapshot. Datum-plane on-face and tangent handles are the named
continuation (queue); recovery UX (redefine badge) is rung D.
"""
import numpy as np
import pytest

from tracer.core import params
from tracer.core.document import (Document, ExtrudeFeature,
                                  PrimitiveFeature)
from tracer.core.sketch.model import face_axes


def cap_rect(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], float)


def plate_boss_doc(height=4.0, handle=True, op="union"):
    """The pick-law commit, reconstructed at core level: plate
    40x30x6 with a boss/pocket handled to its cap-top. The pocket
    commits in a FLIPPED-u frame (cut side preserved by mirroring —
    press-pull's law), so its sketch x runs negative to land at
    world x 15..25: mirrored, inside the plate, and clear of the
    boss corner so one face means one face."""
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    n = np.array([0.0, 0.0, 1.0])
    u, v = face_axes(n)
    axes = [[float(-a) for a in u], [float(b) for b in v]] \
        if op == "subtract" else [u.tolist(), v.tolist()]
    rect = cap_rect(2, 2, 8, 8) if op == "union" \
        else cap_rect(-25, 2, -15, 12)
    d.add(ExtrudeFeature(
        name="boss", op=op, outer=rect, height=height,
        plane="FACE", axes=axes, placement=(0.0, 0.0, 6.0),
        handle=({"feature": "plate", "part": "cap-top"} if handle
                else None)))
    return d


def grow_plate(d, dz=10.0):
    d.features[0].dims["dz"] = dz
    d.dirty = True
    d.recompute()


# ---- the resolver (plane_frame's voice) -----------------------------
def test_face_frame_resolves_live_algebra():
    d = plate_boss_doc()
    pt, n = d.face_frame({"feature": "plate", "part": "cap-top"})
    assert np.allclose(n, (0, 0, 1))
    assert pt[2] == pytest.approx(6.0)
    grow_plate(d, 10.0)
    pt, _ = d.face_frame({"feature": "plate", "part": "cap-top"})
    assert pt[2] == pytest.approx(10.0)      # LIVE, not captured


def test_face_frame_refuses_by_name():
    d = plate_boss_doc()
    with pytest.raises(params.ParamError) as e:
        d.face_frame({"feature": "ghost", "part": "cap-top"})
    msg = str(e.value)
    assert "ghost" in msg and "cache" in msg.lower()


def test_cylinder_caps_publish():
    d = Document()
    d.add(PrimitiveFeature(name="col", kind="cylinder",
                           dims={"radius": 10, "height": 20}))
    pt, n = d.face_frame({"feature": "col", "part": "cap-top"})
    assert np.allclose(n, (0, 0, 1)) and pt[2] == pytest.approx(20.0)
    d.features[0].dims["height"] = 30
    d.dirty = True
    d.recompute()
    pt, _ = d.face_frame({"feature": "col", "part": "cap-top"})
    assert pt[2] == pytest.approx(30.0)


# ---- follow at recompute (the law itself) ---------------------------
def test_handled_boss_follows_the_growing_face():
    d = plate_boss_doc()
    assert abs(d.result.volume - 7344.0) < 1e-6       # 7200 + 144
    grow_plate(d, 10.0)
    assert abs(d.result.volume - 12144.0) < 1e-6      # 12000 + 144
    assert d.result.to_trimesh().bounds[1][2] == pytest.approx(14.0)
    # the record itself keeps its committed numbers (build-time
    # derivation, history honest; the vendor's file stores the
    # relationship, not the moved numbers)
    assert tuple(d.features[1].placement) == (0.0, 0.0, 6.0)


def test_handled_pocket_follows_and_keeps_its_side():
    d = plate_boss_doc(height=2.0, op="subtract")
    assert abs(d.result.volume - 7000.0) < 1e-6       # cut z4..6
    grow_plate(d, 10.0)
    # follows to z10 AND still cuts DOWNWARD (side preserved):
    assert abs(d.result.volume - 11800.0) < 1e-6


def test_stale_handle_freezes_the_cache_never_blanks():
    d = plate_boss_doc()
    d.features[0].suppressed = True                   # face gone
    d.dirty = True
    d.recompute()                                     # must not raise
    assert abs(d.result.volume - 144.0) < 1e-6        # boss stands
    # the frame frozen at commit, exactly the vendor's cache law
    assert d.result.to_trimesh().bounds[1][2] == pytest.approx(10.0)


def test_no_handle_is_yesterdays_bytes():
    d = plate_boss_doc(handle=False)
    grow_plate(d, 10.0)
    assert abs(d.result.volume - 12000.0) < 1e-6      # swallowed:
    #                                   the untouched frozen law


# ---- round-trip ------------------------------------------------------
def test_handle_roundtrips_and_old_files_default_frozen():
    d = plate_boss_doc()
    d2 = Document.from_dict(d.to_dict())
    assert d2.features[1].handle == {"feature": "plate",
                                     "part": "cap-top"}
    grow_plate(d2, 10.0)
    assert abs(d2.result.volume - 12144.0) < 1e-6


def test_legacy_dump_without_handle_key_loads():
    raw = plate_boss_doc().to_dict()
    for fd in raw["features"]:
        fd.pop("handle", None)
    d = Document.from_dict(raw)
    assert d.features[1].handle is None
    grow_plate(d, 10.0)
    assert abs(d.result.volume - 12000.0) < 1e-6


# ---- the UI seam: the commit CAPTURES the handle ---------------------
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
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
    w.doc.add(PrimitiveFeature(name="plate", kind="box",
                               dims={"dx": 40, "dy": 30, "dz": 6}))
    w.recompute()
    qapp.processEvents()
    yield w
    w._unsaved = False                 # m56/m63 law: close the window
    w.close()
    r.close()
    qapp.processEvents()


def test_face_commit_stores_the_handle_and_follows_live(win, qapp,
                                                        monkeypatch):
    from PySide6.QtCore import QPointF
    from tracer.ui.cmddialog import Shell
    monkeypatch.setattr(Shell, "getDouble", lambda *a, **k:
                        (4.0, True))
    vp = win.viewport
    sp = vp._cam.project((20.0, 15.0, 6.0), vp.width(), vp.height())
    hit, why = vp.face_probe(QPointF(*sp))
    assert hit is not None, why
    win._start_sketch_on_face(hit["point"], hit["normal"],
                              hit["body"], hit["tri"])
    outer = np.array([[2, 2], [12, 2], [12, 12], [2, 12], [2, 2]],
                     float)
    win._on_profiles([(outer, [])], win.sketch.model.name)
    f = win.doc.features[-1]
    assert f.handle == {"feature": "plate", "part": "cap-top"}
    assert abs(win.doc.result.volume - (7200 + 100 * 4)) < 1e-6
    win.doc.features[0].dims["dz"] = 10
    win.recompute()
    assert abs(win.doc.result.volume - (12000 + 400)) < 1e-6
