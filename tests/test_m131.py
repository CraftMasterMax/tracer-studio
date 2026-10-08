"""M131 — cross-highlight: the browser and the canvas answer each other.

Click a Body row and the body wears the selection wash; pick a face
and its owning Body row lights up in the tree. The identity that
makes this honest is the stitch ORDER: visible bodies concatenate in
browser order, so each body's faces are one contiguous block, and
`display_ranges` is the one function that knows where every block
begins and ends. Two invariants the tests hold tight: the wash is
VISUAL — self._sel (what measure-on-pick and every face command
target) never grows from clicking a row; and the canvas→browser hop
selects with signals blocked, so it can never bounce back into a
full-body wash the pick never asked for.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tracer.core.document import PrimitiveFeature


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
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
    w.new_document()
    qapp.processEvents()
    w._discard_guard = lambda: True
    yield w
    w._unsaved = False
    w.close()
    r.ctx.release()


def _two_bodies(win):
    """Body 1 = plate, Stud = an offset second body; returns ranges."""
    d = win.doc
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 20, "dy": 20, "dz": 4}))
    d.add_body("Stud")
    d.add(PrimitiveFeature(name="stud", kind="box",
                           dims={"dx": 4, "dy": 4, "dz": 10},
                           placement=(30, 0, 0)))
    win.recompute()
    return d


def _row(tree, role):
    def walk(it):
        for i in range(it.childCount()):
            ch = it.child(i)
            if ch.data(0, Qt.UserRole) == role:
                return ch
            hit = walk(ch)
            if hit is not None:
                return hit
        return None
    return walk(tree.topLevelItem(0))


# ---- core: the map that makes body identity honest -----------------------

def test_display_ranges_are_contiguous_blocks_in_browser_order(win):
    d = _two_bodies(win)
    stitched, rng = d.display_ranges()
    nf = len(stitched[2])
    assert [nm for nm, _, _ in rng] == ["Body 1", "Stud"]
    assert rng[0][1] == 0 <= rng[0][2] == rng[1][1] < rng[1][2] == nf


def test_hidden_bodies_leave_the_ranges(win):
    d = _two_bodies(win)
    for b in d.body_list():
        if b["name"] == "Body 1":
            b["visible"] = False
    _s, rng = d.display_ranges()
    assert [nm for nm, _, _ in rng] == ["Stud"]
    assert rng[0][1] == 0                       # the space renumbered


# ---- browser -> canvas ----------------------------------------------------

def test_body_row_washes_the_body_not_the_selection(win, qapp):
    d = _two_bodies(win)
    vp = win.viewport
    assert _row(win.rail.tree, ("body", "Stud")) is not None
    win.rail.tree.setCurrentItem(_row(win.rail.tree, ("body", "Stud")))
    qapp.processEvents()
    lo, hi = [r for r in d.display_ranges()[1] if r[0] == "Stud"][0][1:]
    assert vp._body_hi == list(range(lo, hi))   # the wash covers it
    assert vp._sel == []                        # ...and _sel stayed clean


def test_feature_row_washes_its_owning_body(win, qapp):
    _two_bodies(win)
    win.rail.tree.setCurrentItem(_row(win.rail.tree, ("feature", 1)))
    qapp.processEvents()
    lo, hi = [r for r in win.viewport._body_rng if r[0] == "Stud"][0][1:]
    assert win.viewport._body_hi == list(range(lo, hi))


def test_wash_moves_with_the_row_and_none_clears(win, qapp):
    _two_bodies(win)
    win.viewport.emphasize_body("Stud")
    assert win.viewport._body_hi
    win.rail.tree.setCurrentItem(_row(win.rail.tree, ("body", "Body 1")))
    qapp.processEvents()
    lo, hi = [r for r in win.viewport._body_rng if r[0] == "Body 1"][0][1:]
    assert win.viewport._body_hi == list(range(lo, hi))   # follows cursor
    win.viewport.emphasize_body(None)                     # datum/folder
    assert win.viewport._body_hi == []


def test_clicking_a_work_axis_recentres_the_orbit(win, qapp):
    _two_bodies(win)
    ax = win.doc.add_axis_2pt((30, 0, 5), (30, 0, 40))
    win.recompute()
    qapp.processEvents()
    assert win.viewport.focus_datum("caxis", ax["name"]) is True
    assert win.viewport._cam.target == pytest.approx((30.0, 0.0, 5.0),
                                                     abs=1e-9)
    assert win.viewport.focus_datum("caxis", "Nope") is False


# ---- canvas -> browser ----------------------------------------------------

def test_picked_faces_light_their_owning_body_row(win, qapp):
    d = _two_bodies(win)
    vp = win.viewport
    lo, hi = [r for r in d.display_ranges()[1] if r[0] == "Stud"][0][1:]
    vp._sel = [lo]                              # one face inside Stud
    vp._apply_hi()
    assert vp.selected_body() == "Stud"
    win._on_face_selection(1)
    qapp.processEvents()
    cur = win.rail.tree.currentItem()
    assert cur is not None and cur.data(0, Qt.UserRole) == ("body", "Stud")


def test_body_of_faces_majority_rules(win):
    _two_bodies(win)
    rng = {nm: (lo, hi) for nm, lo, hi in win.viewport._body_rng}
    b1, b2 = rng["Body 1"], rng["Stud"]
    faces = [b1[0]] + list(range(b2[0], b2[0] + 4))   # 4 to 1 for Stud
    assert win.viewport.body_of_faces(faces) == "Stud"
    assert win.viewport.body_of_faces([]) is None
