"""M106 — per-body appearance: paint a single body.

Fusion lets the Appearance dialog target one body; so can Tracer.  This
is an OPT-IN layer sitting on top of the whole-part paint (M52): the
document still carries ``doc.appearance`` as the default every body
follows, and a body that wants its own look carries
``body["appearance"]``.  Nothing about the old whole-part path changes —
when no body is painted the renderer shades by the ``u_base`` uniform
exactly as before (M52's pixel-exact reset proves it); the moment a body
is painted the viewport stitches a per-face colour array and the shader
switches to a per-vertex base.

Honest scope (v1): per-body COLOR only.  Opacity stays a whole-part
(disp-style) setting — a ghosted body and a solid one can't yet coexist
— and the wireframe/x-ray visual styles keep their uniform tint.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMenu          # noqa: E402
from PySide6.QtCore import Qt                              # noqa: E402

from conftest import script_cmd                            # noqa: E402
from tracer.core.appearance import MATERIALS, appearance   # noqa: E402
from tracer.core.document import (Document,                # noqa: E402
                                  PrimitiveFeature)


def _box(name, d=10.0, at=(0.0, 0.0, 0.0)):
    return PrimitiveFeature(name=name, kind="box",
                            dims={"dx": d, "dy": d, "dz": d},
                            placement=at)


def _two_bodies():
    doc = Document("paint")
    doc.add(_box("Cube", 10.0))                       # Body 1
    doc.add_body()
    doc.add(_box("Stud", 6.0, (30.0, 0.0, 0.0)))      # Body 2
    return doc


# ---------------------------------------------------------------- core

def test_body_appearance_defaults_empty_and_paints():
    doc = _two_bodies()
    assert doc.painted_bodies() is False
    assert doc.body_list()[1].get("appearance") is None
    assert doc.set_body_appearance("Body 2", appearance("Brass", 1.0))
    assert doc.painted_bodies() is True
    assert doc.body_list()[1]["appearance"]["name"] == "Brass"
    assert doc.body_list()[0].get("appearance") is None   # Body 1 untouched


def test_unpaint_clears_the_body_record():
    doc = _two_bodies()
    doc.set_body_appearance("Body 1", appearance("Copper", 1.0))
    assert doc.painted_bodies()
    doc.set_body_appearance("Body 1", None)
    assert "appearance" not in doc.body_list()[0]
    assert doc.painted_bodies() is False


def test_body_appearance_survives_the_file():
    doc = _two_bodies()
    doc.set_body_appearance("Body 2", appearance("Anodized blue", 1.0))
    back = Document.from_dict(doc.to_dict())
    assert back.body_list()[1]["appearance"]["name"] == "Anodized blue"
    assert back.painted_bodies() is True


def test_display_stitched_unchanged_when_nothing_painted():
    doc = _two_bodies()
    v, n, f, colors = doc.display_stitched()
    assert colors is None                              # renderer keeps u_base
    # same geometry as display_arrays
    va, na, fa = doc.display_arrays()
    assert len(v) == len(va) and len(f) == len(fa)


def test_display_stitched_carries_per_face_colors_when_painted():
    doc = _two_bodies()
    doc.set_body_appearance("Body 2", appearance("Brass", 1.0))
    v, n, f, colors = doc.display_stitched(default_color=(0.7, 0.7, 0.72))
    assert colors is not None
    assert colors.shape[0] == len(f)                   # one colour per face
    # Body 1's faces fell back to the default grey, Body 2's are brass
    uniq = np.unique(colors.reshape(-1, 3), axis=0)
    assert len(uniq) == 2
    brass = np.asarray(MATERIALS["Brass"], float)
    assert any(np.allclose(row, brass, atol=1e-4) for row in colors)


# ---------------------------------------------------------------- renderer

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def renderer():
    try:
        from tracer.ui.renderer import SceneRenderer
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    yield r
    r.ctx.release()


def _front_patch(r, face_colors):
    from tracer.core.geometry import Solid
    from tracer.ui.camera import Camera
    s = Solid.box(30, 30, 30)
    v, n, f = s.to_render_arrays()
    r.resize(300, 300)
    r.set_mesh(v, n, f, face_colors=face_colors)
    cam = Camera()
    cam.set_view("front")
    img = r.render(cam, s.bounding_box)[:, :, :3].astype(int)
    return img, img[118:145, 168:195].reshape(-1, 3).mean(0)


def test_face_colors_re_tints_the_shaded_body(renderer):
    grey, g_mid = _front_patch(renderer, None)
    assert abs(int(g_mid[0]) - int(g_mid[1])) < 12          # neutral
    from tracer.core.geometry import Solid
    faces = Solid.box(30, 30, 30).to_render_arrays()[2]
    red = np.tile(np.asarray(MATERIALS["Anodized red"], np.float32),
                  (len(faces), 1))                          # one per face
    _, r_mid = _front_patch(renderer, red)
    assert r_mid[0] > r_mid[1] + 15 and r_mid[0] > r_mid[2] + 15
    back, _ = _front_patch(renderer, None)                  # gated back off
    assert np.array_equal(back, grey)


# ------------------------------------------------------------------ UI

@pytest.fixture
def win(qapp):
    try:
        from tracer.ui.renderer import SceneRenderer
        from tracer.ui.mainwindow import MainWindow
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
        w._discard_guard = lambda: True
        w.close()
        r.ctx.release()
    except Exception:
        raise


def _build_two(win, qapp):
    win.new_document()
    win.doc.add(_box("Cube", 10.0))
    win.action_new_body()
    win.doc.add(_box("Stud", 6.0, (30.0, 0.0, 0.0)))
    win.recompute()
    qapp.processEvents()


def _body_items(tree):
    out = []
    root = tree.topLevelItem(0)

    def rec(it):
        for i in range(it.childCount()):
            ch = it.child(i)
            d = ch.data(0, Qt.UserRole)
            if d and d[0] == "body":
                out.append(ch)
            rec(ch)
    rec(root)
    return out


def test_action_paint_body_targets_one_body(win, qapp, monkeypatch):
    _build_two(win, qapp)
    script_cmd(monkeypatch, {"preset": "Brass"})
    win.action_paint_body("Body 2")
    qapp.processEvents()
    assert win.doc.body_list()[1]["appearance"]["name"] == "Brass"
    assert win.doc.body_list()[0].get("appearance") is None
    assert "Brass" in win.status.currentMessage()
    # the browser row names the material
    assert any("Brass" in it.text(0) for it in _body_items(win.rail.tree))


def test_paint_body_undo_restores(win, qapp, monkeypatch):
    _build_two(win, qapp)
    script_cmd(monkeypatch, {"preset": "Copper"})
    win.action_paint_body("Body 1")
    assert win.doc.body_list()[0]["appearance"]["name"] == "Copper"
    win.undo()
    assert win.doc.body_list()[0].get("appearance") is None


def test_body_menu_offers_paint(win, qapp, monkeypatch):
    _build_two(win, qapp)
    menus = []
    monkeypatch.setattr(QMenu, "exec_",
                        lambda menu, pos: menus.append(menu))
    win._body_menu("Body 2", win.geometry().center())
    labels = [a.text() for a in menus[-1].actions()]
    assert "Paint Body 2…" in labels


def test_whole_part_appearance_still_works(win, qapp, monkeypatch):
    # M52's path is untouched: painting via the dialog paints doc-level,
    # not per-body, and no body carries its own appearance.
    _build_two(win, qapp)
    script_cmd(monkeypatch, {"preset": "Steel", "opacity": 1.0})
    win.action_appearance()
    qapp.processEvents()
    assert win.doc.appearance["name"] == "Steel"
    assert all(b.get("appearance") is None for b in win.doc.body_list())
