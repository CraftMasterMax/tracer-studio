"""M43 — Browser anatomy: Fusion's folder tree (Origin / Bodies /
Sketches / Construction), body visibility toggle, planes in Origin,
custom construction planes under Construction."""
import os

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                    # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu                # noqa: E402

from conftest import feature_rows, tree_texts, script_cmd              # noqa: E402
from tracer.core.document import Document, ExtrudeFeature        # noqa: E402
from tracer.ui.mainwindow import MainWindow                      # noqa: E402
from tracer.ui.renderer import SceneRenderer                     # noqa: E402
from tracer.ui.theme import DARK                                 # noqa: E402


def _payload(name):
    return {"name": name, "plane": "XY",
            "points": [[0, 0], [20, 0], [20, 12], [0, 12]],
            "lines": [[0, 1, 0], [1, 2, 0], [2, 3, 0], [3, 0, 0]],
            "circles": [], "arcs": [], "constraints": []}


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
    d = Document("m43-demo")
    d.add(ExtrudeFeature(name="base", height=6,
                         outer=np.array([[0, 0], [20, 0], [20, 12], [0, 12]],
                                        float),
                         sketch=_payload("Sketch1")))
    d.add(ExtrudeFeature(name="pad", height=4, placement=(30, 0, 0),
                         outer=np.array([[0, 0], [14, 0], [14, 12], [0, 12]],
                                        float),
                         sketch=_payload("Sketch2")))
    d.add_cylinder("peg", radius=3, height=10, center=(5, 5))
    w.doc = d
    w.recompute()
    w._unsaved = False
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


def _folder(win, name):
    root = win.rail.tree.topLevelItem(0)
    for i in range(root.childCount()):
        if root.child(i).text(0).startswith(name):
            return root.child(i)
    raise AssertionError(f"no folder {name!r} in {[root.child(i).text(0) for i in range(root.childCount())]}")


def _kids(node):
    return [node.child(i).text(0) for i in range(node.childCount())]


# ---- folder anatomy -----------------------------------------------------------

def test_root_folders_in_fusion_order(win):
    root = win.rail.tree.topLevelItem(0)
    labels = [root.child(i).text(0) for i in range(root.childCount())]
    assert labels == ["Origin", "Bodies (1)", "Sketches (2)",
                      "Construction (0)"], labels


def test_origin_holds_point_axes_and_planes(win):
    kids = _kids(_folder(win, "Origin"))
    assert kids[0].startswith("\u2316"), kids          # ⌖ origin point
    assert any(t.startswith("\u2014 X Axis") for t in kids)
    assert any(t.startswith("\u2014 Y Axis") for t in kids)
    assert any(t.startswith("\u2014 Z Axis") for t in kids)
    for pl in ("XY-Plane", "XZ-Plane", "YZ-Plane"):
        assert any("\u25ad " + pl == t for t in kids), kids


def test_axis_nodes_are_tinted_like_the_triad(win):
    colors = {}
    origin = _folder(win, "Origin")
    for i in range(origin.childCount()):
        it = origin.child(i)
        colors[it.text(0)] = it.foreground(0).color()
    for axis, key in (("X", "axis_x"), ("Y", "axis_y"), ("Z", "axis_z")):
        c = colors[f"\u2014 {axis} Axis"]
        want = DARK[key]
        assert (c.red(), c.green(), c.blue()) == tuple(round(v * 255)
                                                       for v in want)


# ---- bodies --------------------------------------------------------------------

def test_features_nest_under_body_1(win):
    body = _folder(win, "Bodies (1)").child(0)
    assert body.text(0).startswith("\u25a3")           # ▣ Body 1
    # M104: bodies became real — the node now carries its name, not None
    assert body.data(0, Qt.UserRole) == ("body", "Body 1")
    nested = [body.child(i).text(0) for i in range(body.childCount())]
    assert len(nested) == len(win.doc.features)
    # roles survive the nesting: click target for the properties panel
    roles = [feature_rows(win)[i].data(0, Qt.UserRole)
             for i in range(len(win.doc.features))]
    assert roles == [("feature", i) for i in range(len(win.doc.features))]


def test_body_toggle_hides_solid_in_viewport(win, qapp):
    assert win.viewport._r.show_solid
    win.viewport.set_solid_visible(False)
    qapp.processEvents()
    win.viewport.grab()                                # paints without it
    assert win.viewport._r.show_solid is False
    win.viewport.set_solid_visible(True)
    assert win.viewport._r.show_solid is True


def test_body_node_menu_activates_and_hides_its_body(win, monkeypatch):
    # M104: the body node's bulb is real — a per-body visibility toggle,
    # not the old whole-canvas show/hide.
    menus = []
    monkeypatch.setattr(QMenu, "exec_", lambda menu, pos: menus.append(menu))
    win._body_menu("Body 1", win.geometry().center())
    assert [a.text() for a in menus[-1].actions()] == ["Activate Body 1",
                                                       "Paint Body 1…",
                                                       "Hide Body 1",
                                                       "Material"]      # M110
    menus[-1].actions()[2].trigger()                  # the per-body bulb
    assert win.doc.bodies[0]["visible"] is False
    win._body_menu("Body 1", win.geometry().center())
    assert [a.text() for a in menus[-1].actions()] == ["Activate Body 1",
                                                       "Paint Body 1…",
                                                       "Show Body 1",
                                                       "Material"]
    menus[-1].actions()[2].trigger()
    assert win.doc.bodies[0]["visible"] is True


# ---- sketches + construction ----------------------------------------------------

def test_sketches_folder_mirrors_embedded_sketches(win, qapp):
    folder = _folder(win, "Sketches")
    kids = [folder.child(i) for i in range(folder.childCount())]
    assert all(k.text(0).startswith("\u270e") for k in kids)
    assert [k.data(0, Qt.UserRole) for k in kids] == [("sketch", i)
                                                      for i in range(2)]
    # double-click from the folder enters the editor, same as nested node
    win._tree_activated(kids[0], 0)
    qapp.processEvents()
    assert win.stack.currentWidget() is win._sketch_page


def test_construction_planes_park_in_construction_folder(win, monkeypatch):
    script_cmd(monkeypatch, {"how": "Offset from origin plane",
                             "base": "XY", "dist": 12.0})
    win.action_construction_plane()
    constr = _folder(win, "Construction")
    assert constr.text(0) == "Construction (1)"
    assert [c.text(0) for c in
            (constr.child(i) for i in range(constr.childCount()))] == \
        ["\u25ad Plane 1"]
    assert not any("Plane 1" in t for t in _kids(_folder(win, "Origin")))
    assert constr.child(0).data(0, Qt.UserRole) == ("cplane", "Plane 1")


# ---- proof of life ---------------------------------------------------------------

def test_screenshot_proof(win, qapp, monkeypatch):
    script_cmd(monkeypatch, {"how": "Offset from origin plane",
                             "base": "XY", "dist": 12.0})
    win.action_construction_plane()
    win._show_page(win.viewport)
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m43_browser.png")
    assert "Construction (1)" in tree_texts(win)
