"""M109 — rotate a view on the drawing sheet.

A draughtsman spins a view to sit a slanted part straight, or to stand a
section up.  The whole danger of that in Tracer is that the bubbles must
NOT change their minds: our dimensions are measured live off the MODEL
(M94/M95), so if rotation were baked into the projection it would move
the geometry the bubbles re-measure from and the numbers could drift.

So rotation is a PURE PRESENTATION transform: a page-space spin about the
view's own centre, applied last (model -> canonical page -> rotated page)
and un-applied first on the way back (a click is un-rotated into true
model space).  The layout core `place()` never learns about it, which is
why every pre-M109 drawing test is untouched, and rot = 0 is the exact
identity the sheet used before.  These tests lock that contract:
round-trips are exact at any angle, hit-testing follows the spin, and a
dimension reads the same millimetres upright or turned.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                    # noqa: E402

from tracer.core import drawing                               # noqa: E402
from tracer.core.document import Document, PrimitiveFeature   # noqa: E402


# ---- the transform is a page-space spin with an exact inverse --------------

def test_core_place_never_learns_about_rotation():
    # M109 rotation is a widget display transform; the shared layout core
    # is byte-for-byte what it was, so every pre-M109 drawing test holds.
    one = drawing.place({"top": [[(0, 0), (10, 0), (10, 6), (0, 6)]]})["top"]
    assert set(("sc", "off", "min", "max", "chains")) <= set(one)
    assert "rot" not in one and "ctr" not in one


def test_spin_about_centre_is_its_own_inverse():
    # exercise the widget's static spin helper directly through the class
    from tracer.ui.drawingview import DrawingCanvas as DC
    fr = {"rot": math.radians(37.0), "ctr": (5.0, 3.0)}
    pt = (8.2, 1.4)
    back = DC._spin(fr, DC._spin(fr, pt), neg=True)
    assert math.isclose(back[0], pt[0], abs_tol=1e-9)
    assert math.isclose(back[1], pt[1], abs_tol=1e-9)


def test_zero_rotation_is_the_plain_similarity_map():
    from tracer.ui.drawingview import DrawingCanvas as DC
    fr = {"rot": 0.0, "ctr": (5.0, 3.0), "sc": 2.0, "off": (1.0, 1.0)}
    # at rot 0, model -> page must be exactly model*sc + off (the M94 map)
    assert DC._m2p(fr, (4.0, 5.0)) == (4.0 * 2.0 + 1.0, 5.0 * 2.0 + 1.0)


# ------------------------------------------------------------------ UI

from conftest import script_cmd, script_cmd_cancel             # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        from tracer.ui.renderer import SceneRenderer
        from tracer.ui.mainwindow import MainWindow
        try:
            r = SceneRenderer()
        except Exception as e:                 # CI windows runners: no GL
            pytest.skip(f"no headless GL available: {e}")
        w = MainWindow(renderer=r)
        w.resize(1000, 700)
        w.show()
        qapp.processEvents()
        yield w
        w._unsaved = False
        w._discard_guard = lambda: True
        w.close()
        r.close()
    except Exception:
        raise


def _plate_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Block", kind="box", dims={"dx": 60.0, "dy": 30.0, "dz": 20.0}))
    win.recompute()
    win.action_new_drawing()
    win._show_page(win._drawing_page)
    qapp.processEvents()
    return win.drawing


def _set_rot(cv, view, deg):
    g = cv.sheet()
    g.setdefault("rot", {})[view] = deg
    if not g["rot"]:
        g.pop("rot", None)


def test_view_map_round_trips_through_any_angle(win, qapp):
    cv = _plate_sheet(win, qapp)
    assert cv.placed()["front"]["rot"] == 0.0     # upright default
    assert "ctr" in cv.placed()["front"]          # every frame carries one
    for deg in (0.0, 30.0, 90.0, 200.0, -135.0):
        _set_rot(cv, "front", deg)
        m = (12.5, 7.0)                       # an arbitrary model point
        disp = cv.model_to_page("front", m)
        back = cv.page_to_model("front", disp)
        assert math.isclose(back[0], m[0], abs_tol=1e-7), (deg, back)
        assert math.isclose(back[1], m[1], abs_tol=1e-7), (deg, back)


def test_ninety_degrees_moves_a_point_about_the_view_centre(win, qapp):
    cv = _plate_sheet(win, qapp)
    fr0 = cv.placed()["front"]
    m = (10.0, 4.0)
    canon = cv._m2p({**fr0, "rot": 0.0}, m)   # the unrotated page point
    _set_rot(cv, "front", 90.0)
    fr1 = cv.placed()["front"]
    disp = cv.model_to_page("front", m)
    cx, cy = fr1["ctr"]
    # +90 deg CCW about the centre: (dx,dy) -> (-dy, dx)
    exp = (cx - (canon[1] - cy), cy + (canon[0] - cx))
    assert math.isclose(disp[0], exp[0], abs_tol=1e-6)
    assert math.isclose(disp[1], exp[1], abs_tol=1e-6)


def test_click_on_a_spun_view_still_resolves_to_that_view(win, qapp):
    cv = _plate_sheet(win, qapp)
    _set_rot(cv, "front", 90.0)
    placed = cv.placed()
    # the on-screen (displayed) home of a model point must hit-test back
    # to the same view, because _view_at un-rotates the click first
    dp = cv.model_to_page("front", (15.0, 8.0))
    assert cv._view_at(dp, placed, slack=6.0) == "front"


def test_a_dimension_measures_the_same_upright_or_spun(win, qapp):
    cv = _plate_sheet(win, qapp)
    fr = cv.placed()["front"]
    # two real silhouette corners (model space) as linear endpoints
    pts = sorted({tuple(map(float, p)) for c in fr["chains"] for p in c})
    a, b = pts[0], pts[-1]
    win._add_dim("front", a, b, {})
    g = win.doc.drawings[-1]
    cv.resolve_dims(cv.placed())
    text_upright = g["dims"][-1]["text"]
    a_up, b_up = list(g["dims"][-1]["a"]), list(g["dims"][-1]["b"])
    _set_rot(cv, "front", 90.0)
    cv.resolve_dims(cv.placed())
    text_spun = g["dims"][-1]["text"]
    assert text_spun == text_upright            # the number can't lie
    assert g["dims"][-1]["a"] == a_up           # endpoints stay in model
    assert g["dims"][-1]["b"] == b_up


def test_rotation_survives_the_json_round_trip(win, qapp):
    _plate_sheet(win, qapp)
    _set_rot(win.drawing, "iso", 45.0)
    back = Document.from_dict(win.doc.to_dict())
    assert back.drawings[-1]["rot"]["iso"] == pytest.approx(45.0)


def test_action_rotate_view_stores_and_normalises(win, qapp, monkeypatch):
    cv = _plate_sheet(win, qapp)
    script_cmd(monkeypatch, {"view": "front", "angle": 405.0})
    win.action_rotate_view()
    # 405 -> +45 (folded into (-180, 180])
    assert cv.sheet()["rot"]["front"] == pytest.approx(45.0)


def test_action_rotate_zero_clears_the_entry(win, qapp, monkeypatch):
    cv = _plate_sheet(win, qapp)
    script_cmd(monkeypatch, {"view": "front", "angle": 0.0})
    win.action_rotate_view()
    assert "rot" not in cv.sheet()


def test_action_rotate_undoes(win, qapp, monkeypatch):
    cv = _plate_sheet(win, qapp)
    script_cmd(monkeypatch, {"view": "front", "angle": 90.0})
    win.action_rotate_view()
    assert cv.sheet()["rot"]["front"] == pytest.approx(90.0)
    win.undo()
    assert "rot" not in cv.sheet()


def test_action_rotate_cancels_clean(win, qapp, monkeypatch):
    cv = _plate_sheet(win, qapp)
    script_cmd_cancel(monkeypatch)
    win.action_rotate_view()
    assert "rot" not in cv.sheet()


def test_rotated_sheet_paints_without_crashing(win, qapp):
    cv = _plate_sheet(win, qapp)
    _set_rot(cv, "front", 37.0)
    _set_rot(cv, "top", 90.0)
    cv.resize(900, 620)
    cv.grab()                                  # paintPage: no exception
    assert cv.sheet()["rot"]["front"] == pytest.approx(37.0)
