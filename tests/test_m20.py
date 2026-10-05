"""M20: Fusion fidelity — hover/selection face tint, cursor coordinates,
playhead + icon-only timeline chips, quick toolbar with generated icons,
and the blue-grey horizon palette.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QPointF, Qt            # noqa: E402
from PySide6.QtTest import QTest                           # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog   # noqa: E402

from tracer.core import step                               # noqa: E402
from tracer.core.document import (BodyFilletFeature,       # noqa: E402
                                  PrimitiveFeature)
from tracer.ui import icons                                # noqa: E402
from tracer.ui.renderer import SceneRenderer               # noqa: E402
from tracer.ui.theme import DARK                           # noqa: E402
from tracer.ui.viewport import _coplanar_groups            # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from tracer.ui.mainwindow import MainWindow
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
    r.ctx.release()
    w.close()


def _plate_win(win):
    win.new_document()
    win.doc.add_plate("plate", 20, 20, 5)      # top face z=5, centre (10,10)
    win.recompute()
    return win


def _px_of(vp, world):
    cam = vp.camera()
    vp_m = cam.proj_matrix(vp.width() / vp.height()) @ cam.view_matrix()
    clip = vp_m @ np.append(np.asarray(world, float), 1.0)
    ndc = clip[:3] / clip[3]
    return QPointF((ndc[0] * 0.5 + 0.5) * vp.width(),
                   (0.5 - ndc[1] * 0.5) * vp.height())


def _move(vp, pos):
    """Deliver a button-less mouse move deterministically (Wayland does not
    always route synthetic moves without a physical pointer)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    p = QPointF(pos)
    g = QPointF(vp.mapToGlobal(pos.toPoint() if hasattr(pos, "toPoint")
                               else pos))
    ev = QMouseEvent(QEvent.Type.MouseMove, p, g, Qt.MouseButton.NoButton,
                     Qt.MouseButtons.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, ev)


# ---- palette ---------------------------------------------------------------
def test_fusionish_palette():
    assert "hi_hover" in DARK and "hi_sel" in DARK
    lum = lambda hx: sum(int(hx[i:i + 2], 16) for i in (1, 3, 5))
    assert lum(DARK["sky_top"]) > lum(DARK["sky_bottom"])  # Blender graphite: settles darker under the model
    assert DARK["bg0"] == "#2b2e33"            # blue-grey chrome


# ---- coplanar face grouping (whole-face highlight) --------------------------
def test_groups_merge_box_planes():
    tm = PrimitiveFeature(name="b", kind="box",
                          dims={"dx": 4, "dy": 5, "dz": 6}).build().to_trimesh()
    gid = _coplanar_groups(tm)
    assert len(set(gid.tolist())) == len(tm.faces) // 2      # 12 tris -> 6 faces


def test_caps_merge_but_cylinder_facets_stay_individual():
    from tracer.core.geometry import Solid
    import manifold3d as m3
    m3.set_circular_segments(64)
    tm = Solid.cylinder(5, 10).to_trimesh()
    gid = _coplanar_groups(tm)
    n = np.asarray(tm.face_normals)
    up = np.flatnonzero(n[:, 2] > 0.999)
    dn = np.flatnonzero(n[:, 2] < -0.999)
    wall = np.flatnonzero(np.abs(n[:, 2]) <= 0.999)
    assert len(set(gid[up].tolist())) == 1      # whole cap = one face
    assert len(set(gid[dn].tolist())) == 1
    # wall: each quad's diagonal pair fuses, but the 5.6° ring never does
    gw = len(set(gid[wall].tolist()))
    assert gw == pytest.approx(len(wall) / 2, abs=2)
    assert gw > 1
    m3.set_circular_segments(256)


# ---- renderer tint ----------------------------------------------------------
def test_highlight_changes_pixels():
    from tracer.ui.camera import Camera
    from tracer.ui.mainwindow import demo_document
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    try:
        solid = demo_document().recompute()
        v, n, f = solid.to_render_arrays()
        r.resize(400, 300)
        r.set_mesh(v, n, f)
        r._grid_auto(solid.bounding_box)
        show_grid, show_edges = r.show_grid, r.show_edges
        r.show_grid = False
        cam = Camera()
        cam.set_view("iso")
        cam.fit(solid.bounding_box)
        base = r.render(cam, solid.bounding_box).astype(int)
        faces = list(range(len(f)))
        r.set_highlight(hover_faces=faces)
        hov = r.render(cam, solid.bounding_box).astype(int)
        r.set_highlight(sel_faces=faces)
        sel = r.render(cam, solid.bounding_box).astype(int)
        d_h = np.abs(hov - base).sum(axis=2)
        d_s = np.abs(sel - base).sum(axis=2)
        assert (d_h > 24).sum() > 3000, "hover wash invisible"
        assert (d_s > 24).sum() > (d_h > 24).sum(), \
            "selection tint must read stronger than hover"
        r.set_highlight()                        # clearing restores baseline
        clear = r.render(cam, solid.bounding_box).astype(int)
        assert np.abs(clear - base).mean() < 1.0
        r.show_grid, r.show_edges = show_grid, show_edges
    finally:
        r.ctx.release()


# ---- viewport interaction ----------------------------------------------------
def test_hover_tints_face_and_emits_coords(win, qapp):
    _plate_win(win)
    vp = win.viewport
    seen = []
    vp.coords.connect(seen.append)
    try:
        _move(vp, _px_of(vp, (10, 10, 5)))
        qapp.processEvents()
        assert vp._hover, "no faces hovered on the plate top"
        col = vp._r._solid_data[:, 12]
        assert col.max() == pytest.approx(0.5)
        assert len(set(vp._hover)) > 1, "only one triangle lit (no grouping)"
        assert seen, "coords signal never fired"
        assert np.allclose(seen[-1], (10, 10, 5), atol=0.6)
    finally:
        vp.coords.disconnect(seen.append)


def test_click_selects_whole_face_escape_clears(win, qapp):
    _plate_win(win)
    vp = win.viewport
    p = _px_of(vp, (10, 10, 5)).toPoint()
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, p)
    qapp.processEvents()
    assert vp._sel and len(vp._sel) > 1
    assert (vp._r._solid_data[:, 12] == 1.0).sum() >= 3
    QTest.keyClick(vp, Qt.Key_Escape)
    assert vp._sel == []
    assert vp._r._solid_data[:, 12].max() == 0.0


def test_click_empty_space_deselects(win, qapp):
    _plate_win(win)
    vp = win.viewport
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier,
                     _px_of(vp, (10, 10, 5)).toPoint())
    assert vp._sel
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, QPoint(6, 6))
    assert vp._sel == []


# ---- timeline -----------------------------------------------------------------
def test_timeline_icon_chips_and_clicks(win, qapp):
    from tracer.ui.mainwindow import demo_document
    win.new_document(demo_document())
    qapp.processEvents()
    bar = win.timeline.bar
    bar.repaint()
    qapp.processEvents()
    feats = win.doc.features
    assert len(bar._chips) == len(feats)
    assert all(w == 30 for _, w, _ in bar._chips)       # icon-only, uniform
    clicked = []
    bar.feature_clicked.connect(clicked.append)
    bar.home_clicked.connect(lambda: clicked.append("home"))
    try:
        x, w, f = bar._chips[1]
        QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier,
                         QPointF(x + w / 2, bar.height() / 2).toPoint())
        assert clicked == [f]
        hx = bar._home.center()
        QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier,
                         QPointF(hx).toPoint())
        assert clicked[-1] == "home"
    finally:
        bar.feature_clicked.disconnect()
        bar.home_clicked.disconnect()


def test_timeline_glyph_vocabulary(win, qapp):
    from tracer.ui.timeline import TimelineBar
    from tracer.core.document import Document
    bar = TimelineBar()
    d = Document()
    box = PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 1, "dy": 1, "dz": 1})
    fil = BodyFilletFeature(name="f", radius=1)
    cha = BodyFilletFeature(name="c", radius=1, chamfer=True)
    d.features += [box, fil, cha]
    assert bar._glyph(box) == "+"
    assert bar._glyph(fil) == "\u2312" and bar._glyph(cha) == "\u25d0"
    box.suppressed = True
    assert bar._glyph(box) == "\u25cb"
    assert bar._label(fil).startswith("\u2312")         # legacy contract kept


# ---- quick toolbar --------------------------------------------------------------
def _toolbutton(win, tip_start):
    from PySide6.QtWidgets import QToolButton
    for b in win.findChildren(QToolButton):
        if b.toolTip().startswith(tip_start):
            return b
    raise AssertionError(f"no toolbar button {tip_start!r}")


def test_toolbar_sketch_button_opens_sketcher(win, qapp):
    _plate_win(win)
    _toolbutton(win, "New sketch").click()
    qapp.processEvents()
    assert win.stack.currentWidget() is win._sketch_page


def test_toolbar_extrude_from_model_prompts_for_profile(win, qapp):
    _plate_win(win)
    b = _toolbutton(win, "Extrude")
    b.menu().actions()[0].trigger()             # menu: Extrude profile…
    qapp.processEvents()
    assert win.stack.currentWidget() is win._sketch_page
    assert "profile" in win.status.currentMessage()


def test_toolbar_fillet_needs_no_occt(win, qapp, monkeypatch):
    from tracer.ui.mainwindow import demo_document
    monkeypatch.setattr(step, "available", lambda: False)
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (1.0, True)))
    win.new_document(demo_document())
    qapp.processEvents()
    _toolbutton(win, "Fillet").menu().actions()[0].trigger()
    qapp.processEvents()
    f = win.doc.features[-1]
    assert isinstance(f, BodyFilletFeature)
    assert f.n_rims > 0, "rim pass must work without OpenCascade"


# ---- icon factory ---------------------------------------------------------------
def test_icons_generate_nonempty_pixmaps():
    for name in ("sketch", "extrude", "revolve", "pattern", "cpattern",
                 "mirror", "fillet", "chamfer"):
        pm = icons.icon(name).pixmap(32, 32)
        assert not pm.isNull()
        assert pm.hasAlpha()                    # transparent background
    with pytest.raises(KeyError):
        icons.icon("nope")
