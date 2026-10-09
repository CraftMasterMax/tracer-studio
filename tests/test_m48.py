"""M48 — Section Analysis: a shader clip plane that opens the body on
XY/XZ/YZ without touching the model.  The clip must actually remove
pixels (half the body), flip must swap halves, and the ribbon button
must carry the plane menu like Fusion's Construct group."""
import os

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMenu, QToolButton   # noqa: E402

from tracer.ui.camera import Camera                              # noqa: E402
from tracer.ui.mainwindow import MainWindow, demo_document       # noqa: E402
from tracer.ui.renderer import SceneRenderer                     # noqa: E402
from tracer.ui.theme import DARK                                 # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def renderer(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:                     # CI windows runners: no GL
        pytest.skip(f"no headless GL available: {e}")
    yield r
    r.close()


@pytest.fixture
def win(qapp, renderer):
    w = MainWindow(renderer=renderer)
    w.doc = demo_document()
    w.recompute()
    w.resize(1100, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


def _rowbg(h):
    def hx(s):
        s = s.lstrip("#")
        return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], float)
    top, bot = hx(DARK["sky_top"]), hx(DARK["sky_bottom"])
    t = np.linspace(0.0, 1.0, h)[:, None, None]
    return top + (bot - top) * t


def _shot(renderer, view, clip=None):
    doc = demo_document()
    solid = doc.recompute()
    v, n, f = solid.to_render_arrays()
    renderer.resize(400, 300)
    renderer.set_mesh(v, n, f)
    grid, renderer.show_grid = renderer.show_grid, False   # body pixels only
    cam = Camera()
    cam.set_view(view)
    renderer.clip = clip
    img = renderer.render(cam, solid.bounding_box)[:, :, :3].astype(float)
    renderer.show_grid = grid
    mask = np.any(np.abs(img - _rowbg(img.shape[0])) > 24, axis=2)
    renderer.clip = None
    ctr = (np.asarray(solid.bounding_box[0], float)
           + np.asarray(solid.bounding_box[1], float)) / 2.0
    return img, mask, ctr


# ---- the shader clip itself ------------------------------------------------

def test_clip_is_off_until_a_section_is_set(renderer):
    assert renderer.clip is None                 # off until a section is set
    _, mask, _ = _shot(renderer, "iso")
    assert mask.sum() > 500                      # body fully on screen


def test_section_midplane_removes_half_the_body(renderer):
    """Clip through the bracket's X mid-plane: roughly half the silhouette
    must go, and the view must never go fully empty or stay whole."""
    _, base, ctr = _shot(renderer, "iso")
    _, cut, _ = _shot(renderer, "iso",
                      {"normal": (1, 0, 0), "origin": tuple(ctr)})
    full, half = base.sum(), cut.sum()
    assert full > 500
    assert 0.35 * full < half < 0.80 * full, (full, half)


def test_flip_section_shows_the_other_half(renderer):
    _, base, ctr = _shot(renderer, "iso")
    _, px = _shot(renderer, "iso",
                  {"normal": (1, 0, 0), "origin": tuple(ctr)})[:2]
    _, nx = _shot(renderer, "iso",
                  {"normal": (-1, 0, 0), "origin": tuple(ctr)})[:2]
    assert px.sum() < base.sum() and nx.sum() < base.sum()
    both = (px & nx).sum()                       # the two clipped views
    assert both < 0.4 * min(px.sum(), nx.sum())  # keep different halves


def test_screenshot_proof(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.doc = demo_document()
    w.recompute()
    w._show_page(w.viewport)
    w.action_section("XY")
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert w.grab().save(f"{out}/m48_section.png")
    w._unsaved = False
    w.close()
    r.close()


# ---- viewport plumbing -------------------------------------------------------

def test_named_planes_map_to_axis_normals(win):
    for name, n in (("XY", (0, 0, 1)), ("XZ", (0, 1, 0)), ("YZ", (1, 0, 0))):
        win.viewport.set_section(name)
        assert win.viewport.section["label"] == name
        assert win.viewport.section["normal"] == n
    win.viewport.set_section({"name": "Plane1", "normal": (0, 0, 1),
                              "origin": (0, 0, 12)})
    assert win.viewport.section["origin"] == (0, 0, 12)
    win.viewport.set_section(None)
    assert win.viewport.section is None


def test_action_section_toggles_and_flips(win):
    win.action_section("XY")
    assert win.viewport.section["label"] == "XY"
    win.action_flip_section()
    assert win.viewport.section["normal"] == (0, 0, -1)
    win.action_section("XY")                     # same plane twice = off
    assert win.viewport.section is None
    win.action_flip_section()                    # flip while off: no-op
    assert win.viewport.section is None


# ---- ribbon anatomy ----------------------------------------------------------

def _section_button(win):
    lay = win.ribbon.dl
    for i in range(lay.count()):
        it = lay.itemAt(i).widget()
        if (isinstance(it, QToolButton)
                and it.toolTip().startswith("Section analysis")):
            return it
    return None


def test_section_button_carries_the_plane_menu(win):
    b = _section_button(win)
    assert b is not None, "no Section button in the ribbon"
    menu = b.menu()
    assert isinstance(menu, QMenu)
    texts = [a.text() for a in menu.actions()]
    assert texts == ["Section on XY plane", "Section on XZ plane",
                     "Section on YZ plane", "Flip clipped side",
                     "Turn section off"]


def test_section_menu_items_drive_the_viewport(win):
    texts = {a.text(): a for a in _section_button(win).menu().actions()}
    texts["Section on XZ plane"].trigger()
    assert win.viewport.section["label"] == "XZ"
    texts["Flip clipped side"].trigger()
    assert win.viewport.section["normal"] == (0, -1, 0)
    texts["Turn section off"].trigger()
    assert win.viewport.section is None
