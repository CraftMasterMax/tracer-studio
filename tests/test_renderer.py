"""Renderer tests run truly headless (moderngl standalone context).
They assert real pixels, not just 'no exception'.
"""
import numpy as np
import pytest

from tracer.ui.camera import Camera, look_at, perspective
from tracer.ui.renderer import SceneRenderer
from tracer.ui.mainwindow import demo_document


# ---- camera math (pure numpy) -------------------------------------------
def test_camera_fit_frames_object():
    cam = Camera()
    cam.fit(np.array([[-10, -10, 0], [10, 10, 20]], float))
    assert np.allclose(cam.target, [0, 0, 10])
    assert cam.distance > np.linalg.norm([20, 20, 20])  # outside bbox sphere


def test_look_at_orthonormal_rotation():
    m = look_at([10, 0, 0], [0, 0, 0])
    r = m[:3, :3]
    np.testing.assert_allclose(r @ r.T, np.eye(3), atol=1e-9)


def test_perspective_projects_forward():
    p = perspective(45, 1.0, 0.1, 100.0)
    clip = p @ np.array([0, 0, -10, 1])
    assert clip[3] > 0  # w positive in front of camera (NDC z handled by GL)


# ---- pixels -----------------------------------------------------------------
@pytest.fixture(scope="module")
def renderer():
    try:
        r = SceneRenderer()
    except Exception as e:  # no GPU/EGL at all -> explicit skip, never silent
        pytest.skip(f"no headless GL available: {e}")
    yield r
    r.ctx.release()


def _render_doc(renderer, cam_kind="iso"):
    doc = demo_document()
    solid = doc.recompute()
    v, n, f = solid.to_render_arrays()
    renderer.resize(400, 300)
    renderer.set_mesh(v, n, f)
    renderer._grid_auto(solid.bounding_box)
    cam = Camera()
    cam.set_view(cam_kind)
    cam.fit(solid.bounding_box)
    return renderer.render(cam, solid.bounding_box), solid


def _rowbg(img):
    """Expected horizon-gradient background per image row (top->bottom)."""
    from tracer.ui.theme import DARK

    def hx(s):
        s = s.lstrip("#")
        return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], float)
    top, bot = hx(DARK["sky_top"]), hx(DARK["sky_bottom"])
    h = img.shape[0]
    t = np.linspace(0.0, 1.0, h)[:, None, None]        # 0 at top row
    return top + (bot - top) * t                        # (h,1,3)


def _fg_mask(img):
    return np.any(np.abs(img[:, :, :3].astype(float) - _rowbg(img)) > 24,
                  axis=2)


def test_solid_renders_as_silhouette(renderer):
    img, solid = _render_doc(renderer)
    assert img.shape == (300, 400, 4)
    coverage = _fg_mask(img).mean()
    assert 0.05 < coverage < 0.90, f"coverage {coverage:.3f} — model missing/full-frame"


def test_shading_is_not_flat(renderer):
    img, _ = _render_doc(renderer)
    g = img[:, :, 0].astype(int)
    assert g.max() - g.min() > 40, "no lighting gradient — shader broken"


def test_depth_occlusion(renderer):
    """Front view of the bracket: boss must cover fewer pixels than iso."""
    iso, _ = _render_doc(renderer, "iso")
    front, _ = _render_doc(renderer, "front")
    assert _fg_mask(front).mean() < _fg_mask(iso).mean()


def test_edges_toggle_changes_pixels(renderer):
    img_on, _ = _render_doc(renderer)
    renderer.show_edges = False
    img_off, _ = _render_doc(renderer)
    renderer.show_edges = True
    diff = np.abs(img_on.astype(int) - img_off.astype(int)).sum(axis=2)
    assert (diff > 12).sum() > 100, "edge overlay had no visible effect"


def test_grid_actually_draws(renderer):
    """Ground plane must visibly change pixels (regression: a vertex-count
    bug once drew only 13 lines and every absolute-threshold test still
    passed — measure the grid by its on/off difference instead)."""
    img_on, _ = _render_doc(renderer)
    renderer.show_grid = False
    img_off, _ = _render_doc(renderer)
    renderer.show_grid = True
    diff = np.abs(img_on.astype(int) - img_off.astype(int)).sum(axis=2)
    h = img_on.shape[0]
    grid_px = int((diff[int(h * 0.72):] > 20).sum())    # foreground strip
    assert grid_px > 300, f"grid nearly invisible ({grid_px} px)"
    assert (diff > 20).sum() < 0.6 * img_on.shape[0] * img_on.shape[1], \
        "grid toggle changed the whole frame — it should only touch ground"
