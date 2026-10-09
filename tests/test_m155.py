"""M155 — the cube's manners: the opacity state, the hysteresis, the
menu, the settings. Every law executed first as a receipt
(spike_m155/live_m155.py, all green at fd5f206) against
research/m155_cube_manners.md (checklist 7d2edfae L5/L10/L12). The
M154 face/click/glide laws stay byte-exact (G7 rides the full file);
the shipped home-less home() pin (28.0) is guarded HERE too."""
import json
import math
import time

import numpy as np
import pytest
from PySide6.QtCore import (QEvent, QPointF, QPoint, QSettings, Qt)
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from tracer.core.document import Document, PrimitiveFeature
from tracer.ui.camera import Camera
from tracer.ui.viewcube import ViewCube, auto_size

KEYS = ("viewcube/size_mode", "viewcube/size",
        "viewcube/inactive_opacity", "viewcube/corner")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def clean_settings():
    s = QSettings()
    for k in KEYS:
        s.remove(k)
    yield


@pytest.fixture
def vp(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    w.new_document()
    d = Document("manners")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    w.doc = d
    w.recompute()
    qapp.processEvents()
    yield w.viewport
    w._unsaved = False
    w.close()
    qapp.processEvents()


def _settle_fade(v, qapp, ms=1200):
    t0 = time.monotonic()
    while v._cube_fade is not None and (time.monotonic() - t0) < ms / 1000:
        qapp.processEvents()
        time.sleep(0.01)


# ---- G1: the opacity state machine --------------------------------------

def test_inactive_starts_at_the_setting(vp, qapp):
    assert vp.cube_inactive_op == 0.5
    assert vp._cube_op == 0.5


def test_fade_lands_exactly_both_ways(vp, qapp):
    vp._cube_fade_to(1.0)
    _settle_fade(vp, qapp)
    assert vp._cube_op == 1.0
    vp._cube_fade_to(0.0)
    _settle_fade(vp, qapp)
    assert vp._cube_op == 0.0            # 0 = the invisible slot


def test_invisible_slot_still_hit_tests(vp, qapp):
    cam = Camera()
    cam.set_view("front")
    img = QImage(400, 300, QImage.Format.Format_RGB32)
    img.fill(0)
    p = QPainter(img)
    p.setOpacity(0.0)                    # the paintEvent law: draw IS
    cube = ViewCube()                    #   called every paint; the
    cube.place(400, 300)                 #   opacity is the painter's
    cube.draw(p, cam)                    #   state, not a skip
    p.end()
    arr = np.frombuffer(img.constBits(), np.uint8,
                        img.sizeInBytes()).reshape(300, 400, 4)
    assert int(arr[..., :3].astype(np.uint32).sum()) == 0, \
        "opacity 0 must ink NOTHING anywhere"
    # the buffer was REBUILT by that zero-opacity draw:
    assert cube.hit(QPointF(cube.rect.center())) == "front"


# ---- G2: hysteresis (the spike trace, byte-pinned) -----------------------

def test_hysteresis_trace_matches_the_spike(vp):
    vp._cube_hover = None
    seq = ["front", "front-top", "front", "front-top", "front",
           "front-top", "front-top", "front-top", None, "front"]
    out = []
    for raw in seq:
        hk = vp._cube_hysteresis(raw)
        vp._cube_hover = hk              # what mouseMove does
        out.append(hk)
    assert out == ["front", "front", "front", "front", "front", "front",
                   "front", "front-top", None, "front"]


# ---- G3: cursor law -------------------------------------------------------

def test_pointing_hand_over_a_zone_arrow_elsewhere(vp, qapp):
    vp._cam.set_view("front")
    vp.update()
    for _ in range(4):
        qapp.processEvents()              # the buffer answers for the
    c = QPointF(vp._cube.rect.center())   #  pose that was PAINTED
    ev = QMouseEvent_wrap(QEvent.Type.MouseMove, c)
    vp.mouseMoveEvent(ev)
    qapp.processEvents()
    assert vp.cursor().shape() == Qt.CursorShape.PointingHandCursor
    far = QPointF(10, vp.height() // 2)
    vp.mouseMoveEvent(QMouseEvent_wrap(QEvent.Type.MouseMove, far))
    qapp.processEvents()
    assert vp.cursor().shape() != Qt.CursorShape.PointingHandCursor
    vp.unsetCursor()


def QMouseEvent_wrap(kind, pos):
    from PySide6.QtGui import QMouseEvent
    return QMouseEvent(kind, pos, QPointF(pos), Qt.MouseButton.NoButton,
                       Qt.MouseButtons.NoButton,
                       Qt.KeyboardModifier.NoModifier)


# ---- G4: the menu (measured correction: NO standard-view list) -----------

def test_cube_menu_item_set_is_exact(vp, qapp, monkeypatch):
    seen = {}

    def fake_show(menu, at):
        seen["texts"] = [a.text() for a in menu.actions()
                         if not a.isSeparator()]

    monkeypatch.setattr(vp, "_show_menu", fake_show)
    vp._cube_menu(QPoint(0, 0))
    # M156 RETARGET (cited): the menu grew "Snap to Closest View"
    # (L8.4's documented option, a toggle — NOT a view list). The
    # five old items keep byte order; the ban-list stands.
    assert seen["texts"] == ["Home", "Set Current View as Home",
                             "Parallel", "Perspective",
                             "Snap to Closest View",
                             "ViewCube Settings..."], seen["texts"]
    for banned in ("Front", "Top", "Right", "Standard"):
        assert banned not in seen["texts"]      # measured correction


def test_parallel_flips_the_scene_not_the_cube(vp, qapp):
    from PIL import Image
    import io
    from PySide6.QtCore import QBuffer, QIODevice

    def grabpx(w):
        b = QBuffer()
        b.open(QIODevice.WriteOnly)
        w.grab().save(b, "PNG")
        b.close()
        return np.asarray(Image.open(io.BytesIO(bytes(b.data()))
                                     ).convert("RGB")).astype(int)
    qapp.processEvents()
    base = grabpx(vp)
    vp._set_projection(True)
    qapp.processEvents()
    par = grabpx(vp)
    assert vp._cam.parallel is True
    assert int((np.abs(par - base).sum(axis=2) > 30).sum()) > 400, \
        "Parallel must actually re-render the scene"
    vp._set_projection(False)
    qapp.processEvents()
    assert int((np.abs(grabpx(vp) - base).sum(axis=2) > 30).sum()) == 0, \
        "back to Perspective is byte-exact (paint is deterministic)"
    # the cube NEVER changes projection: its own Camera is private
    assert vp._cube.project(vp._cam)[1] is not None   # still works


def test_set_home_and_restore(vp, qapp):
    fired = []
    vp.home_changed.connect(lambda: fired.append(1))
    vp._cam.yaw, vp._cam.pitch, vp._cam.distance = 0.3, 0.5, 77.0
    vp._set_home_from_view()
    assert fired == [1]                          # the dot must know
    # M157 RETARGET (cited, contract §1.6): home grows a FOURTH key,
    # roll — the old triple keeps byte-value, the wrist rides with
    # it (receipt V7 proves pre-M157 files restore at roll 0).
    assert vp._doc.home == {"yaw": 0.3, "pitch": 0.5,
                            "distance": 77.0, "roll": 0.0}
    vp._cam.yaw, vp._cam.pitch, vp._cam.distance = 0.0, 0.0, 10.0
    vp.home()
    assert (vp._cam.yaw, vp._cam.pitch, vp._cam.distance) == (
        0.3, 0.5, 77.0)                          # steers AND zooms


def test_home_less_doc_keeps_the_28_deg_pin(vp, qapp):
    assert vp._doc.home is None
    vp.home()
    assert math.degrees(vp._cam.pitch) == 28.0   # M154 G9 law stands


# ---- G5: the document round-trip -----------------------------------------

def test_home_round_trips_and_old_files_survive():
    d = Document("h")
    d.add(PrimitiveFeature(name="B", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10}))
    d.recompute()
    assert d.home is None
    d.home = {"yaw": 0.1, "pitch": 0.2, "distance": 30.0}
    blob = json.dumps(d.to_dict())
    d2 = Document.from_dict(json.loads(blob))
    assert d2.home == {"yaw": 0.1, "pitch": 0.2, "distance": 30.0}
    assert d2.to_dict() == d.to_dict()           # byte-equal files
    old = json.loads(blob)
    del old["home"]                              # a pre-M155 file
    d3 = Document.from_dict(old)
    assert d3.home is None


# ---- G6: settings ----------------------------------------------------------

def test_auto_size_formula_is_the_measured_one():
    assert auto_size(1240, 760) == 61            # receipt V5 values
    assert auto_size(1100, 720) == 60
    assert auto_size(2560, 1440) == 115
    assert auto_size(400, 300) == 60             # the floor


def test_fixed_size_and_dpr_and_corner(vp, qapp):
    vp.cube_size_mode = "fixed"
    vp.cube_fixed_px = 100
    vp.apply_cube_settings()
    assert vp._cube.size_px == 100
    img = QImage(800, 600, QImage.Format.Format_RGB32)
    img.fill(0)
    p = QPainter(img)
    vp._cube.place(800, 600)
    vp._cube.draw(p, Camera(), dpr=2.0)
    p.end()
    assert vp._cube._pick.width() == 200         # logical x DPR (L10.5)
    for corner, at in (("bottom-left", (12, 600)),
                       ("top-left", (12, 0)),
                       ("bottom-right", (800, 600))):
        vp._cube.corner = corner
        vp._cube.place(800, 600)
        r = vp._cube.rect
        if corner.endswith("left"):
            assert r.left() == 12
        else:
            assert r.right() == 800 - 12
        if corner.startswith("bottom"):
            assert abs(r.bottom() - (600 - 12)) < 0.01
        else:
            assert r.top() == 12


def test_settings_persist_and_reset(vp, qapp):
    from tracer.ui.viewport import _CubeSettingsDialog
    dlg = _CubeSettingsDialog(vp)
    dlg._corner.setCurrentText("bottom-left")
    dlg._op.setValue(80)
    qapp.processEvents()
    s = QSettings()
    assert str(s.value("viewcube/corner")) == "bottom-left"
    assert abs(float(s.value("viewcube/inactive_opacity")) - 0.8) < 1e-9
    assert vp._cube.corner == "bottom-left"
    dlg._reset()
    assert vp._cube.corner == "top-right"
    assert vp.cube_inactive_op == 0.5
    assert str(QSettings().value("viewcube/corner")) == "top-right"
    dlg.close()


# ---- G7: the old laws ride untouched ---------------------------------------

def test_right_click_on_the_cube_never_clicks_a_view(vp, qapp):
    vp.view_anim_s = 0.0
    vp._cam.set_view("right")
    vp._cube.place(vp.width(), vp.height())
    qapp.processEvents()
    c = QPointF(vp._cube.rect.center())
    from PySide6.QtGui import QMouseEvent
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, c, QPointF(c),
                     Qt.MouseButton.RightButton,
                     Qt.MouseButtons.RightButton,
                     Qt.KeyboardModifier.NoModifier)
    vp.mousePressEvent(ev)
    assert ev.isAccepted() is False              # it IGNORES — the menu
    #   owns right-click; the view did not move:
    assert (vp._cam.yaw, vp._cam.pitch) == (0.0, 0.0)
