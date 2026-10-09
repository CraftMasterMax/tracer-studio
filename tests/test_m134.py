"""M134 — isolation: a suppressive overlay that never touches the bulbs.

The vendor's verbatim law, learned the expensive way by its users and
encoded in the probe: unisolate restores EXACTLY the pre-isolate world
— rows hidden before an isolation come back hidden. Our design gets
that law by construction: isolation stacks (scope, boosted) overlays
and writes NOTHING to eye state, so there is nothing to "undo" on the
way out; hidden members are boosted into view for the session while
their rows stay honestly OFF. The second law is the separation of
verbs: Show All is the LOSSY sister (force every eye on — recovery,
not exit) and the tests hold the two apart, because the vendor's own
recovery docs route users to Show All BECAUSE unisolate surprises
them. Everything else is composition: re-isolate narrows (AND across
the stack), Esc pops one level, the document root row carries the
always-findable exits, and the stitched mesh (hence cross-highlight
and picking) follows the overlay for free."""
import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from tracer.core.document import Document, PrimitiveFeature


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def three_bodies():
    d = Document()
    d.add(PrimitiveFeature(name="base", kind="box",
                           dims={"dx": 30, "dy": 30, "dz": 5}))
    d.add_body("Stud")
    d.add(PrimitiveFeature(name="stud", kind="box",
                           dims={"dx": 5, "dy": 5, "dz": 20},
                           placement=(20, 20, 5)))
    d.add_body("Post")
    d.add(PrimitiveFeature(name="post", kind="box",
                           dims={"dx": 4, "dy": 4, "dz": 12},
                           placement=(-18, -18, 5)))
    return d


def shown(d):
    d.result
    return {b[0]["name"] for b in d._visible_solids()}


# ---- the law: restore is exact because nothing was ever written ------------

def test_isolate_leaves_only_the_named_body_visible():
    d = three_bodies()
    assert d.isolate(["Stud"]) == ["Stud"]
    assert shown(d) == {"Stud"}
    assert d.isolation_active() and d.isolation_depth() == 1


def test_unisolate_restores_the_pre_isolate_world_verbatim():
    d = three_bodies()
    d.set_body_visible("Post", False)           # hidden BEFORE isolating
    d.isolate(["Stud"])
    assert shown(d) == {"Stud"}
    assert d.unisolate() is True
    assert shown(d) == {"Body 1", "Stud"}       # Post came back HIDDEN:
    #                                           # the verbatim vendor law
    assert d.body_list()[2]["visible"] is False  # its bulb never moved


def test_isolating_a_hidden_body_boosts_it_without_touching_the_bulb():
    d = three_bodies()
    d.set_body_visible("Stud", False)
    d.isolate(["Stud"])
    assert "Stud" in shown(d)                    # boosted into view...
    entry = next(b for b in d.body_list() if b["name"] == "Stud")
    assert entry["visible"] is False             # ...bulb still OFF
    d.unisolate()
    assert "Stud" not in shown(d)                # back to the honest OFF


def test_a_hide_performed_during_isolation_sticks_afterwards():
    d = three_bodies()
    d.isolate(["Stud", "Post"])
    d.set_body_visible("Post", False)            # mid-session edit
    assert shown(d) == {"Stud"}
    d.unisolate()
    assert "Post" not in shown(d)                # the user's new hide
    #                                          # survived the exit


def test_stacked_isolates_intersect_and_pop_one_level_at_a_time():
    d = three_bodies()
    d.isolate(["Stud", "Post"])
    d.isolate(["Stud", "Body 1"])                # narrower AND
    assert shown(d) == {"Stud"}
    assert d.unisolate()
    assert shown(d) == {"Stud", "Post"}          # one level back
    assert d.unisolate()
    assert shown(d) == {"Body 1", "Stud", "Post"}
    assert d.unisolate() is False                # nothing left to pop


def test_show_all_is_the_lossy_sister_not_the_exit():
    d = three_bodies()
    d.set_body_visible("Post", False)
    d.isolate(["Stud"])
    forced = d.show_all()
    assert forced == 1                           # Post forced on...
    assert shown(d) == {"Body 1", "Stud", "Post"}
    assert d.isolation_depth() == 0              # ...and isolation gone
    # the contrast IS the lesson: unisolate kept Post dark, Show All
    # cannot — that is why it is recovery, not exit
    d2 = three_bodies()
    d2.set_body_visible("Post", False)
    d2.isolate(["Stud"])
    d2.unisolate()
    assert "Post" not in shown(d2)


def test_isolation_is_session_state_never_saved():
    d = three_bodies()
    d.isolate(["Stud"])
    blob = d.to_dict()
    assert not any("iso" in k for k in blob)      # no isolation in the
    #                                             # file: session, not model
    d2 = Document.from_dict(blob)
    assert d2.isolation_depth() == 0             # fresh eyes on load
    assert shown(d2) == {"Body 1", "Stud", "Post"}


def test_unknown_names_are_dropped_and_a_calm_unisolate_is_a_noop():
    d = three_bodies()
    assert d.isolate(["Ghost"]) == []
    assert not d.isolation_active()
    assert d.unisolate() is False
    assert d.unisolate_all() == 0


# ---- the UI surface ---------------------------------------------------------

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
    w.doc.add(PrimitiveFeature(name="base", kind="box",
                               dims={"dx": 30, "dy": 30, "dz": 5}))
    w.doc.add_body("Stud")
    w.doc.add(PrimitiveFeature(name="stud", kind="box",
                               dims={"dx": 5, "dy": 5, "dz": 20},
                               placement=(20, 20, 5)))
    w.recompute()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def test_the_root_row_carries_the_always_findable_exits(win, qapp):
    win._isolate_body("Stud")
    assert win.doc.isolation_active()
    win._root_menu(QPoint(10, 10))
    qapp.processEvents()
    labels = [a.text() for a in win._root_menu_open.actions()]
    assert "Show All" in labels and "Unisolate All" in labels
    win._root_menu_open.close()
    win._unisolate_all()
    win._root_menu(QPoint(10, 10))
    qapp.processEvents()
    labels = [a.text() for a in win._root_menu_open.actions()]
    assert "Unisolate All" not in labels          # calm document:
    win._root_menu_open.close()                   # only the lossy verb


def test_esc_pops_one_level_and_the_tell_names_the_view(win, qapp):
    vp = win.viewport
    win._isolate_body("Stud")
    win._isolate_body("Stud")                     # stacked two deep
    vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                               Qt.KeyboardModifier.NoModifier))
    assert win.doc.isolation_depth() == 1         # one level per Esc
    vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                               Qt.KeyboardModifier.NoModifier))
    assert not win.doc.isolation_active()         # and no more


def test_cross_highlight_sees_only_the_isolated_world(win, qapp):
    """M131's ranges come from the SAME stitched source as the mesh —
    so isolation propagates to picking and washing for free."""
    win._isolate_body("Stud")
    qapp.processEvents()
    names = {name for name, _, _ in win.viewport._body_rng}
    assert names == {"Stud"}
    win._unisolate_all()
    qapp.processEvents()
    assert {n for n, _, _ in win.viewport._body_rng} == {"Body 1", "Stud"}
