"""M52 — Appearance: paint the body with a shop material.

Core: the MATERIALS table is sane and `appearance()` clamps opacity.
Renderer: set_base_color re-tints the shaded pixels (pixel assertion)
and None restores the theme grey.  Document: the record JSON
round-trips.  Command: the dialog names the material, applies it to
the live viewport, and cancel changes nothing.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                              # noqa: E402

from conftest import script_cmd                                         # noqa: E402
from tracer.core.appearance import MATERIALS, appearance                # noqa: E402
from tracer.core.document import Document, PrimitiveFeature             # noqa: E402
from tracer.core.geometry import Solid                                  # noqa: E402


# ---- core ------------------------------------------------------------------------

def test_material_table_is_sane():
    assert "Brass" in MATERIALS and "Steel" in MATERIALS
    for name, rgb in MATERIALS.items():
        assert len(rgb) == 3 and all(0.0 <= c <= 1.0 for c in rgb), name
    assert len({rgb for rgb in MATERIALS.values()}) == len(MATERIALS)


def test_appearance_record_clamps_opacity():
    a = appearance("Brass", 1.7)
    assert a["opacity"] == 1.0
    assert appearance("Brass", -3)["opacity"] == 0.0
    assert a["name"] == "Brass"
    assert np.allclose(a["color"], MATERIALS["Brass"])


# ---- document --------------------------------------------------------------------

def _box_doc():
    d = Document("painted")
    d.add(PrimitiveFeature(name="block", kind="box",
                           dims={"dx": 30, "dy": 30, "dz": 30}))
    d.recompute()
    return d


def test_document_appearance_json_round_trip():
    d = _box_doc()
    d.appearance = appearance("Copper", 0.6)
    d2 = Document.from_dict(d.to_dict())
    assert d2.appearance["name"] == "Copper"
    assert d2.appearance["opacity"] == pytest.approx(0.6)
    assert np.allclose(d2.appearance["color"], MATERIALS["Copper"])
    assert _box_doc().appearance is None                 # default unpainted


# ---- renderer ----------------------------------------------------------------------

from tracer.ui.renderer import SceneRenderer                             # noqa: E402


@pytest.fixture
def renderer():
    try:
        r = SceneRenderer()
    except Exception as e:                     # CI windows runners: no GL
        pytest.skip(f"no headless GL available: {e}")
    yield r
    r.close()


def _body_patch(r):
    """Mean colour of a patch on the front face, away from the axis
    cross-hair that crosses the exact screen centre."""
    s = Solid.box(30, 30, 30)
    v, n, f = s.to_render_arrays()
    r.resize(300, 300)
    r.set_mesh(v, n, f)
    from tracer.ui.camera import Camera
    cam = Camera()
    cam.set_view("front")
    img = r.render(cam, s.bounding_box)[:, :, :3].astype(int)
    # camera looks at the world origin, so the 0..30 box projects into
    # the upper-right quadrant; sample the middle of its front face
    return img, img[118:145, 168:195].reshape(-1, 3).mean(0)


def test_base_color_override_re_tints_pixels(renderer):
    grey, g_mid = _body_patch(renderer)
    assert abs(float(g_mid[0]) - float(g_mid[1])) < 12        # neutral grey
    renderer.set_base_color(MATERIALS["Anodized red"])
    red, r_mid = _body_patch(renderer)
    assert r_mid[0] > r_mid[1] + 15 and r_mid[0] > r_mid[2] + 15
    renderer.set_base_color(None)                              # theme restored
    back, _ = _body_patch(renderer)
    assert np.array_equal(back, grey)


def test_ghost_opacity_fades_the_body(renderer):
    grey_img, _ = _body_patch(renderer)                  # theme grey, opaque
    renderer.set_base_color(MATERIALS["Anodized red"], 1.0)
    _, solid = _body_patch(renderer)
    renderer.set_base_color(MATERIALS["Anodized red"], 0.2)
    _, ghost = _body_patch(renderer)
    assert solid[0] > ghost[0] + 15          # background bleeds through
    renderer.set_base_color(None)
    back_img, _ = _body_patch(renderer)
    assert np.array_equal(back_img, grey_img)  # colour AND alpha fully reset


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


def _block(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="block", kind="box",
                                 dims={"dx": 30, "dy": 30, "dz": 30}))
    win.recompute()
    qapp.processEvents()


def test_action_appearance_paints_and_persists(win, qapp, monkeypatch):
    _block(win, qapp)
    script_cmd(monkeypatch, {"preset": "Brass", "opacity": 1.0})
    win.action_appearance()
    qapp.processEvents()
    assert win.doc.appearance["name"] == "Brass"
    assert np.allclose(win._renderer._base_override, MATERIALS["Brass"])
    assert "Brass" in win.status.currentMessage()
    d2 = Document.from_dict(win.doc.to_dict())
    assert d2.appearance["name"] == "Brass"


def test_action_appearance_restore_clears_paint(win, qapp, monkeypatch):
    _block(win, qapp)
    script_cmd(monkeypatch, {"preset": "Steel", "opacity": 1.0})
    win.action_appearance()
    script_cmd(monkeypatch, {"preset": "(none)", "opacity": 1.0})
    win.action_appearance()
    assert win.doc.appearance is None
    assert win._renderer._base_override is None
    assert "unpainted" in win.status.currentMessage()


def test_action_appearance_cancel_changes_nothing(win, qapp, monkeypatch):
    from conftest import script_cmd_cancel
    _block(win, qapp)
    script_cmd_cancel(monkeypatch)
    win.action_appearance()
    qapp.processEvents()
    assert win.doc.appearance is None
    assert win._renderer._base_override is None
