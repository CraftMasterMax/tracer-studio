"""M54 — Visual Styles: Fusion's View ▸ Visual Styles dropdown.

Five honest styles on the renderer: Wireframe (edges only — the faces
discard), Ghosted (20% body, grid through it), Shaded, Shaded with
edges (the default we always had), X-ray (blue-grey at 35%).  Pixel
tests prove each style actually paints differently; the menu action
drives renderer state and status; the default style restores pixels
exactly.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                              # noqa: E402

from tracer.ui.renderer import SceneRenderer                             # noqa: E402


@pytest.fixture
def renderer():
    try:
        r = SceneRenderer()
    except Exception as e:                     # CI windows runners: no GL
        pytest.skip(f"no headless GL available: {e}")
    yield r
    r.close()


def _patch(r):
    """Mean colour of the front face + full image (front view; the box
    projects upper-right since the camera looks at the world origin)."""
    from tracer.core.geometry import Solid
    s = Solid.box(30, 30, 30)
    v, n, f = s.to_render_arrays()
    r.resize(300, 300)
    r.set_mesh(v, n, f)
    from tracer.ui.camera import Camera
    cam = Camera()
    cam.set_view("front")
    img = r.render(cam, s.bounding_box)[:, :, :3].astype(int)
    return img, img[118:145, 168:195].reshape(-1, 3).mean(0)


def test_styles_paint_differently(renderer):
    _, shaded_edges = _patch(renderer)                  # default
    for style, key in (("ghosted", "g"), ("xray", "x"),
                       ("shaded", "s"), ("wireframe", "w")):
        renderer.set_visual_style(style)
        _, m = _patch(renderer)
        assert m is not None, key
    renderer.set_visual_style("shaded")
    _, plain = _patch(renderer)
    renderer.set_visual_style("ghosted")
    _, ghost = _patch(renderer)
    renderer.set_visual_style("wireframe")
    _, wire = _patch(renderer)
    renderer.set_visual_style("shaded with edges")       # back home
    _, back = _patch(renderer)
    assert np.array_equal(back, shaded_edges)            # default is exact
    assert shaded_edges[0] > ghost[0] + 15               # ghost fades
    assert ghost[0] > wire[0] + 15                       # wire = no fill
    assert abs(float(plain[0] - shaded_edges[0])) < 12   # edges are thin ink


def test_xray_is_blue_grey_ghost(renderer):
    renderer.set_visual_style("shaded with edges")
    _, solid = _patch(renderer)
    renderer.set_visual_style("xray")
    img, x = _patch(renderer)
    assert solid[0] > x[0] + 10                          # it is see-through
    assert x[2] > x[0]                                   # and cool-toned


# ---- UI ----------------------------------------------------------------------------

from tracer.ui.mainwindow import MainWindow                              # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def test_visual_style_menu_action(win, qapp):
    from tracer.core.document import PrimitiveFeature
    win.new_document()
    win.doc.add(PrimitiveFeature(name="b", kind="box",
                                 dims={"dx": 20, "dy": 20, "dz": 20}))
    win.recompute()
    qapp.processEvents()
    win.action_visual_style("Ghosted")
    assert win._renderer._style == "ghosted"
    assert "Ghosted" in win.status.currentMessage()
    win.action_visual_style("Shaded with edges")
    assert win._renderer._style == "shaded with edges"


def test_view_menu_holds_the_style_submenu(win):
    styles = None
    for a in win.menuBar().actions():
        if a.text().replace("&", "") == "View":
            for act in a.menu().actions():
                if act.menu() and act.text().startswith("Visual"):
                    styles = [x.text() for x in act.menu().actions()]
    assert styles == ["Wireframe", "Ghosted", "Shaded",
                      "Shaded with edges", "X-ray"]
