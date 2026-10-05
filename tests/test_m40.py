"""M40 — construction planes (Fusion Construct ▸ Plane).

Offset copies of origin planes that live in the document (and the file),
show up under Origin in the browser as ▭ nodes, render as translucent-
blue quads with faint diagonals in the viewport, and take sketches: a
double-click opens the editor on the plane's own frame so X extrudes
along the plane normal.  The basis rule u × v = n is the hinge that
makes every downstream placement exact.
"""
import numpy as np
import pytest

from tracer.core.document import Document


def _doc_with_planes():
    d = Document("planes")
    a = d.add_plane("XY", 12.0)
    b = d.add_plane("XZ", 7.0)
    c = d.add_plane("YZ", -3.0)
    return d, a, b, c


def test_offset_lives_along_the_base_normal():
    _, a, b, c = _doc_with_planes()
    assert a["origin"] == [0.0, 0.0, 12.0]
    assert b["origin"] == [0.0, 7.0, 0.0]
    assert c["origin"] == [-3.0, 0.0, 0.0]


def test_bases_are_right_handed_u_cross_v_equals_n():
    for p in _doc_with_planes()[0].planes:
        u, v, n = (np.asarray(p[k], float) for k in ("u", "v", "n"))
        assert np.allclose(np.cross(u, v), n)
        assert np.isclose(np.linalg.norm(u), 1) and np.isclose(
            np.linalg.norm(v), 1)
        assert abs(float(u @ v)) < 1e-9


def test_names_never_clash_even_after_deletion():
    d, *_ = _doc_with_planes()
    assert [p["name"] for p in d.planes] == ["Plane 1", "Plane 2", "Plane 3"]
    assert d.remove_plane("Plane 2") and not d.remove_plane("Plane 2")
    assert d.add_plane("XY", 1)["name"] == "Plane 2"


def test_planes_persist_and_old_files_load_clean():
    d, *_ = _doc_with_planes()
    back = Document.from_dict(d.to_dict())
    assert [p["name"] for p in back.planes] == \
           ["Plane 1", "Plane 2", "Plane 3"]
    assert back.planes[0]["origin"] == [0.0, 0.0, 12.0]
    old = d.to_dict()
    del old["planes"]                      # a pre-M40 file
    assert Document.from_dict(old).planes == []


pytest.importorskip("PySide6")

from PySide6.QtWidgets import (QApplication, QInputDialog, QToolButton)  # noqa: E402

from tracer.ui.mainwindow import MainWindow                             # noqa: E402
from tracer.ui.renderer import SceneRenderer                            # noqa: E402


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
    w.new_document()                     # clean slate, no demo body
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


@pytest.fixture
def dialogs(monkeypatch):
    """Scripted Construct ▸ Plane answers: base then distance(s)."""
    def install(base="XY", *distances):
        seq = iter(distances) if distances else iter([12.0])
        monkeypatch.setattr(QInputDialog, "getItem",
                            staticmethod(lambda *a, **k: (base, True)))
        monkeypatch.setattr(QInputDialog, "getDouble",
                            staticmethod(lambda *a, **k: (next(seq), True)))
    return install


def _origin_node(win):
    return win.rail.tree.topLevelItem(0).child(0)


# ---- creation, browser + viewport presence ------------------------------------

def test_command_creates_plane_node_and_viewport_quad(win, qapp, dialogs):
    dialogs("XY", 12.0)
    win.action_construction_plane()
    qapp.processEvents()
    assert len(win.doc.planes) == 1
    assert win.doc.planes[0]["origin"] == [0.0, 0.0, 12.0]
    texts = [_origin_node(win).child(i).text(0)
             for i in range(_origin_node(win).childCount())]
    assert any("▭ Plane 1" in t for t in texts), texts
    assert win.viewport._r._plane_count == 12      # 4 edges + 2 diagonals


def test_ribbon_construct_button_dispatches(win, monkeypatch):
    fired = []
    monkeypatch.setattr(win, "action_construction_plane",
                        lambda checked=False: fired.append(True))
    for b in win.findChildren(QToolButton):
        if b.toolTip().startswith("Construction plane"):
            b.click()
            break
    else:
        raise AssertionError("no Construction plane ribbon button")
    assert fired


# ---- sketch ON the plane: the whole point --------------------------------------

def test_double_click_opens_sketch_on_the_plane_frame(win, qapp, dialogs):
    dialogs("XY", 12.0)
    win.action_construction_plane()
    qapp.processEvents()
    o = _origin_node(win)
    item = next(o.child(i) for i in range(o.childCount())
                if "Plane 1" in o.child(i).text(0))
    win._tree_activated(item, 0)
    qapp.processEvents()
    assert win.stack.currentWidget() is win._sketch_page
    m = win.sketch.model
    assert m.plane == "FACE"
    assert tuple(m.origin) == (0.0, 0.0, 12.0)
    assert np.allclose(m.axes, [[1, 0, 0], [0, 1, 0]])


def test_extrude_from_the_plane_lands_at_its_height(win, qapp, dialogs):
    dialogs("XY", 12.0, 12.0)               # plane @12, extrude distance 12
    win.action_construction_plane()
    qapp.processEvents()
    o = _origin_node(win)
    item = next(o.child(i) for i in range(o.childCount())
                if "Plane 1" in o.child(i).text(0))
    win._tree_activated(item, 0)
    qapp.processEvents()
    outer = np.array([[0, 0], [10, 0], [10, 8], [0, 8]], float)
    win._on_profiles([(outer, [])], win.sketch.model.name)
    qapp.processEvents()
    lo, hi = win.doc.result.bounding_box
    assert abs(lo[2] - 12) < 1e-6 and abs(hi[2] - 24) < 1e-6
    assert win.doc.result.volume == pytest.approx(960, abs=1e-3)


def test_delete_plane_removes_node_and_quad(win, qapp, dialogs):
    dialogs("XY", 12.0)
    win.action_construction_plane()
    qapp.processEvents()
    win._delete_plane("Plane 1")
    qapp.processEvents()
    assert win.doc.planes == []
    assert win.viewport._r._plane_count == 0
    texts = [_origin_node(win).child(i).text(0)
             for i in range(_origin_node(win).childCount())]
    assert not any("▭" in t for t in texts)


# ---- proof of life ---------------------------------------------------------------

def test_screenshot_proof(win, qapp, dialogs):
    import os
    dialogs("XY", 12.0)
    win.action_construction_plane()
    win.doc.add_plane("XZ", 18.0)          # a second, upright one
    win.rail.tree.reload()
    win.viewport.refresh(fit=True)
    win._show_page(win.viewport)
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m40_planes.png")
