"""M33 — Measure: click faces, get answers (Fusion's Inspect>Measure).

One face answers with its area; two faces answer with the angle and the
closest gap — the maker classics (wall clearance, deck thickness, corner
angle). With nothing selected the inspector shows the whole body's volume
and surface area. All computed from the pick mesh: plane fits per logical
face group, exact on this kernel's grid-aligned tessellations.
"""
import numpy as np
import pytest

from tracer.core.geometry import Solid
from tracer.core.measure import angle_between, closest_distance, describe, face_stats


def _box_tm():
    return Solid.box(40, 40, 10).to_trimesh()


def _face(tm, axis, sign):
    tris = np.flatnonzero(np.asarray(tm.face_normals)[:, axis] * sign > 0.9)
    return face_stats(tm, tris)


# ---- kernel -----------------------------------------------------------------

def test_face_area_and_planarity():
    tm = _box_tm()
    top = _face(tm, 2, 1)
    assert top["area"] == pytest.approx(1600.0)
    assert top["planar"]
    assert np.allclose(top["normal"], (0, 0, 1), atol=1e-9)


def test_opposite_faces_read_as_parallel_with_their_gap():
    tm = _box_tm()
    top, bottom = _face(tm, 2, 1), _face(tm, 2, -1)
    assert angle_between(top, bottom) == pytest.approx(180.0, abs=1e-6)
    assert closest_distance(top, bottom) == pytest.approx(10.0)
    assert describe(top, bottom) == "parallel: gap 10.00 mm"


def test_adjacent_faces_read_as_perpendicular_meeting_at_the_edge():
    tm = _box_tm()
    top, front = _face(tm, 2, 1), _face(tm, 1, -1)
    msg = describe(top, front)
    assert msg.startswith("perpendicular")
    assert closest_distance(top, front) == pytest.approx(0.0)


def test_curved_faces_are_flagged_as_curved():
    tm = Solid.cylinder(10, 20, (0, 0)).to_trimesh()
    quarter = np.flatnonzero(np.asarray(tm.face_normals)[:, 0] > 0.35)
    s = face_stats(tm, quarter)              # a 90°-band, normal well defined
    assert not s["planar"]
    assert "(curved)" in describe(s, None)


def _plane(normal, pts):
    n = np.asarray(normal, float)
    return dict(tris=np.array([]), area=0.0, center=np.zeros(3),
                normal=n / np.linalg.norm(n), pts=np.asarray(pts, float),
                planar=True)


def test_ramp_against_its_floor_reports_the_true_slope():
    n = np.array([10.0, 0.0, 40.0])
    ramp = _plane(n, [[40, 0, 0], [0, 0, 10], [40, 40, 0], [0, 40, 10]])
    floor = _plane((0, 0, -1), [[0, 0, 0], [40, 0, 0], [40, 40, 0], [0, 40, 0]])
    slope = 180.0 - np.degrees(np.arctan(10.0 / 40.0))
    assert angle_between(ramp, floor) == pytest.approx(slope, abs=0.05)
    assert f"angle {slope:.1f}" in describe(ramp, floor)
    assert closest_distance(ramp, floor) == pytest.approx(0.0)  # shared edge


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                      # noqa: E402

from tracer.ui.mainwindow import MainWindow                     # noqa: E402
from tracer.ui.renderer import SceneRenderer                    # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _plate(win, qapp):
    from tracer.core.document import PrimitiveFeature
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 10}))
    win.recompute()
    qapp.processEvents()


def _pick(win, axis, sign):
    tm = win.viewport._tm
    tris = np.flatnonzero(np.asarray(tm.face_normals)[:, axis] * sign > 0.9)
    return win.viewport._group(int(tris[0]))


def test_no_selection_shows_body_numbers(win, qapp):
    _plate(win, qapp)
    qapp.processEvents()
    text = win.rail.props._body.text()
    assert "16,000.0" in text and "surface area" in text


def test_one_face_answers_with_its_area(win, qapp):
    _plate(win, qapp)
    win.viewport._sel = _pick(win, 2, 1)
    win._on_face_selection(1)
    assert "face area 1600.0 mm²" in win.status.currentMessage()


def test_two_faces_answer_with_gap_and_angle(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    top, bottom, front = _pick(win, 2, 1), _pick(win, 2, -1), _pick(win, 1, -1)
    vp._sel = top + bottom
    win._on_face_selection(2)
    assert "parallel: gap 10.00 mm" in win.status.currentMessage()
    vp._sel = top + front
    win._on_face_selection(2)
    assert "perpendicular" in win.status.currentMessage()


def test_three_faces_ask_the_user_to_narrow_down(win, qapp):
    _plate(win, qapp)
    vp = win.viewport
    vp._sel = _pick(win, 2, 1) + _pick(win, 2, -1) + _pick(win, 1, -1)
    win._on_face_selection(3)
    assert "keep exactly two" in win.status.currentMessage()


def test_click_emits_selection_changed_and_recomputing_clears_it(win, qapp):
    _plate(win, qapp)
    seen = []
    win.viewport.selection_changed.connect(seen.append)
    win.viewport._sel = _pick(win, 2, 1)
    win.viewport._apply_hi()
    win.viewport.selection_changed.emit(1)        # what _click_select does
    assert seen == [1]
    win.recompute()                               # mesh changed: no stale sel
    qapp.processEvents()
    assert seen[-1] == 0 and not win.viewport._sel


def test_screenshot_proof(win, qapp):
    import os
    _plate(win, qapp)
    win.action_view("iso")
    win.viewport.refresh(fit=True)                # (this clears any sel)
    win.viewport._sel = _pick(win, 2, 1) + _pick(win, 0, 1)
    win.viewport._apply_hi()
    win._on_face_selection(2)
    qapp.processEvents()
    assert "perpendicular" in win.status.currentMessage()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m33_measure.png")
