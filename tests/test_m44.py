"""M44 — Blender solid-mode shading (user: "Make the shading like the
one blenders editor mode uses"): viewport-fixed studio lights, neutral
grey body, graphite gradient that settles darker under the model.

The invariants here are exactly what makes Blender's Solid shading
Blender's: the same face reads with the same brightness no matter which
way the camera looks at it (the lights ride with the view), the grey is
neutral (no blue cast), and the top of a body is lighter than its
underbelly in every orbit.
"""
import os

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                       # noqa: E402

from tracer.ui.camera import Camera                              # noqa: E402
from tracer.ui.renderer import SceneRenderer                     # noqa: E402
from tracer.ui.mainwindow import MainWindow, demo_document       # noqa: E402
from tracer.ui.theme import DARK                                 # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def renderer():
    try:
        r = SceneRenderer()
    except Exception as e:  # no GPU/EGL -> explicit skip, never silent
        pytest.skip(f"no headless GL available: {e}")
    yield r
    r.ctx.release()


def _rowbg(h):
    def hx(s):
        s = s.lstrip("#")
        return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], float)
    top, bot = hx(DARK["sky_top"]), hx(DARK["sky_bottom"])
    t = np.linspace(0.0, 1.0, h)[:, None, None]
    return top + (bot - top) * t


def _shot(renderer, view):
    doc = demo_document()
    solid = doc.recompute()
    v, n, f = solid.to_render_arrays()
    renderer.resize(400, 300)
    renderer.set_mesh(v, n, f)
    renderer._grid_auto(solid.bounding_box)
    cam = Camera()
    cam.set_view(view)
    cam.fit(solid.bounding_box)
    img = renderer.render(cam, solid.bounding_box)[:, :, :3].astype(float)
    mask = np.any(np.abs(img - _rowbg(img.shape[0])) > 24, axis=2)
    return img, mask


luma = lambda a: 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


# ---- palette ---------------------------------------------------------------

def test_body_grey_is_neutral():
    r, g, b = DARK["solid_base"]
    assert max(r, g, b) - min(r, g, b) <= 0.03      # Blender grey, no cast


def test_backdrop_settles_darker_under_the_model(renderer):
    img, _ = _shot(renderer, "front")
    top = luma(img[2:8]).mean()
    bottom = luma(img[-8:-2]).mean()
    assert top - bottom > 8.0                        # graphite gradient


# ---- viewport-fixed studio light -------------------------------------------

def test_same_face_same_light_from_every_orbit(renderer):
    """The Blender signature: front / top / bottom views all read the
    face-on brightness the same, because the lights ride with the view.
    A world-fixed rig would go dark on the underside view."""
    means = {}
    for view in ("front", "top", "bottom"):
        img, mask = _shot(renderer, view)
        assert mask.sum() > 500                      # body on screen
        means[view] = luma(img)[mask].mean()
    lo, hi = min(means.values()), max(means.values())
    assert lo > 0.55 * hi, means                     # same family of grey


def test_top_of_the_body_is_lighter_than_the_belly(renderer):
    img, mask = _shot(renderer, "iso")
    rows = np.where(mask.any(axis=1))[0]
    band = len(rows) // 4
    ys, xs = np.where(mask)
    up = ys < rows[0] + band
    down = ys > rows[-1] - band
    assert luma(img)[ys[up], xs[up]].mean() > luma(img)[ys[down], xs[down]].mean()


# ---- proof of life -----------------------------------------------------------

def test_screenshot_proof(qapp):
    w = MainWindow()
    w.doc = demo_document()
    w.recompute()
    w._show_page(w.viewport)
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert w.grab().save(f"{out}/m44_shading.png")
    w._unsaved = False
    w.close()
