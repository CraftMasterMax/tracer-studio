"""M104 — multi-body phase 2: Bodies are real.

Fusion's browser always said `Bodies (1) ▸ Body 1` and the tree was
honest about it: there was exactly one, because recompute() had exactly
one accumulator.  Tracer now has the document half of multi-body:

* every FEATURE belongs to a body (`f.body`), every body streams its
  own solid — a cut lands in the active body and leaves the neighbours
  alone;
* `doc.result` stays ONE solid: the union of the bodies — the part.
  Measurement, drawings, HLR, sections and export keep their one-solid
  world untouched (single-body docs are byte-identical to before);
* the VIEWPORT is where bodies stay separate: the display mesh is the
  stitched (concatenated, never booleaned) visible bodies, so hiding
  one body lifts exactly its triangles and a shared wall between two
  touching bodies stays visible, like Fusion;
* New Body is a verb, activation is a double-click, the bulb is a
  menu item, and all of it saves, migrates (legacy files adopt Body 1)
  and undoes.

Honest scope: exports and drawings still see the fused part, not a
per-body file set; per-body appearances and cross-body feature sources
follow in later phases.
"""
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMenu           # noqa: E402
from PySide6.QtCore import Qt                              # noqa: E402

from tracer.core.document import (Document,                 # noqa: E402
                                  PrimitiveFeature)


def _box(name, d=10.0, at=(0.0, 0.0, 0.0)):
    return PrimitiveFeature(name=name, kind="box",
                            dims={"dx": d, "dy": d, "dz": d},
                            placement=at)


def _two_bodies():
    doc = Document("mb")
    doc.add(_box("Cube", 10.0))                       # -> Body 1
    doc.add_body()                                    # -> Body 2 active
    doc.add(_box("Stud", 6.0, (20.0, 0.0, 0.0)))      # disjoint: union adds
    return doc


# ---------------------------------------------------------------- core

def test_plain_document_adopts_body_1_lazily():
    doc = Document("plain")
    assert doc.bodies == [] and doc.active_body is None
    doc.add(_box("Cube"))
    assert [b["name"] for b in doc.bodies] == ["Body 1"]
    assert doc.active_body == "Body 1"
    assert doc.features[0].body == "Body 1"
    assert doc.body_solids()["Body 1"].volume == pytest.approx(1000.0)
    # and result is that solid itself — the pre-multi-body world
    assert doc.result is doc.body_solids()["Body 1"]


def test_two_bodies_keep_their_own_solids():
    doc = _two_bodies()
    solids = doc.body_solids()
    assert set(solids) == {"Body 1", "Body 2"}
    assert solids["Body 1"].volume == pytest.approx(1000.0)
    assert solids["Body 2"].volume == pytest.approx(216.0)
    # result is the PART: the union (disjoint here, so volumes add)
    assert doc.result.volume == pytest.approx(1216.0)


def test_a_cut_lands_only_in_the_active_body():
    doc = Document("cut")
    doc.add(PrimitiveFeature(name="Plate1", kind="box",
                             dims={"dx": 40.0, "dy": 20.0, "dz": 5.0}))
    doc.add_body()
    doc.add(PrimitiveFeature(name="Plate2", kind="box",
                             dims={"dx": 40.0, "dy": 20.0, "dz": 5.0},
                             placement=(0.0, 0.0, 20.0)))
    doc.add(PrimitiveFeature(name="Bore", kind="cylinder",
                             dims={"radius": 4.0, "height": 5.0},
                             placement=(20.0, 10.0, 20.0), op="subtract"))
    solids = doc.body_solids()
    assert solids["Body 1"].volume == pytest.approx(4000.0)     # untouched
    assert solids["Body 2"].volume == pytest.approx(
        4000.0 - math.pi * 16.0 * 5.0, rel=0.02)


def test_a_new_body_rejects_a_solo_cut():
    doc = Document("solo")
    doc.add(_box("Cube"))
    doc.add_body()                                    # Body 2, still empty
    with pytest.raises(ValueError, match="cannot be a subtract"):
        doc.add(PrimitiveFeature(name="Ghost", kind="box",
                                 dims={"dx": 4.0, "dy": 4.0, "dz": 4.0},
                                 op="subtract"))
        doc.recompute()


def test_visibility_is_a_viewport_fact_not_a_part_fact():
    doc = _two_bodies()
    full = doc.display_arrays()
    v1 = doc.body_solids()["Body 1"]
    n1 = len(v1.to_render_arrays()[2])
    assert len(full[2]) == n1 + len(
        doc.body_solids()["Body 2"].to_render_arrays()[2])
    assert doc.set_body_visible("Body 2", False)
    only1 = doc.display_arrays()
    assert len(only1[2]) == n1                       # exactly its triangles
    assert doc.result.volume == pytest.approx(1216.0)  # the part is intact
    doc.set_body_visible("Body 2", True)
    assert len(doc.display_arrays()[2]) == len(full[2])


def test_bodies_and_routing_survive_the_file():
    doc = _two_bodies()
    doc.set_body_visible("Body 1", False)
    back = Document.from_dict(doc.to_dict())
    assert [b["name"] for b in back.bodies] == ["Body 1", "Body 2"]
    assert back.bodies[0]["visible"] is False and back.bodies[1]["visible"]
    assert back.active_body == "Body 2"
    assert [f.body for f in back.features] == ["Body 1", "Body 2"]
    assert back.result.volume == pytest.approx(1216.0)


def test_legacy_files_migrate_into_body_1():
    doc = _two_bodies()                       # two separate streams today…
    legacy = doc.to_dict()
    legacy.pop("bodies", None)
    legacy.pop("active_body", None)
    for fd in legacy["features"]:
        fd.pop("body", None)
    # …which is exactly what an old file looks like: one undivided history
    back = Document.from_dict(legacy)
    assert [b["name"] for b in back.bodies] == ["Body 1"]
    assert back.active_body == "Body 1"
    assert all(f.body == "Body 1" for f in back.features)
    # both boxes were routed to Body 2 while streaming… the legacy reader
    # folds every bodyless feature into Body 1, so the part is a union of
    # the two boxes either way
    assert back.result.volume == pytest.approx(1216.0)


# ------------------------------------------------------------------ UI

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        from tracer.ui.renderer import SceneRenderer
        from tracer.ui.mainwindow import MainWindow
        try:
            r = SceneRenderer()
        except Exception as e:                 # CI windows runners: no GL
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


def _walk(tree):
    items = []

    def rec(it):
        for i in range(it.childCount()):
            ch = it.child(i)
            items.append(ch)
            rec(ch)
    rec(tree.topLevelItem(0))
    return items


def _body_items(tree):
    out = []
    for it in _walk(tree):
        r = it.data(0, Qt.UserRole)
        if r and r[0] == "body":
            out.append(it)
    return out


def _build_two_bodies(win, qapp):
    win.new_document()
    win.doc.add(_box("Cube", 10.0))
    win.action_new_body()
    win.doc.add(_box("Stud", 6.0))
    win.recompute()
    qapp.processEvents()


def test_new_body_verb_creates_activates_and_undoes(win, qapp):
    win.new_document()
    win._discard_guard = lambda: True
    win.action_new_body()
    assert [b["name"] for b in win.doc.bodies] == ["Body 1"]
    assert win.doc.active_body == "Body 1"
    win.action_new_body()
    assert win.doc.active_body == "Body 2"
    win.doc.add(_box("Stud"))
    assert win.doc.features[-1].body == "Body 2"
    # one undo rolls back to just-before-New-Body-2: the body AND the
    # raw doc.add (which took no undo point) both go, back to Body 1 alone
    win.undo()
    assert [b["name"] for b in win.doc.bodies] == ["Body 1"]
    assert win.doc.active_body == "Body 1"
    assert len(win.doc.features) == 0
    # the second undo unwinds Body 1 too — the pristine lazy-empty doc
    win.undo()
    assert win.doc.bodies == []
    assert win.doc.active_body is None


def test_browser_nests_each_body_and_marks_the_active_one(win, qapp):
    _build_two_bodies(win, qapp)
    items = _body_items(win.rail.tree)
    assert [it.text(0).replace("\u25a3 ", "") for it in items] == \
        ["Body 1", "Body 2"]
    assert [it.data(0, Qt.UserRole) for it in items] == \
        [("body", "Body 1"), ("body", "Body 2")]
    # active is bold, and each body carries ONLY its own features
    assert items[1].font(0).bold() and not items[0].font(0).bold()
    kids = [[items[k].child(i).data(0, Qt.UserRole)
             for i in range(items[k].childCount())] for k in (0, 1)]
    assert kids == [[("feature", 0)], [("feature", 1)]]


def test_double_click_a_body_makes_it_active(win, qapp):
    _build_two_bodies(win, qapp)
    body1 = _body_items(win.rail.tree)[0]
    win.rail.tree.itemDoubleClicked.emit(body1, 0)
    qapp.processEvents()
    assert win.doc.active_body == "Body 1"
    win.doc.add(_box("Third"))
    assert win.doc.features[-1].body == "Body 1"


def test_body_menu_bulb_hides_only_its_body(win, qapp, monkeypatch):
    _build_two_bodies(win, qapp)
    menus = []
    monkeypatch.setattr(QMenu, "exec_",
                        lambda menu, pos: menus.append(menu))
    win._body_menu("Body 2", win.geometry().center())
    labels = [a.text() for a in menus[-1].actions()]
    assert labels == ["Activate Body 2", "Paint Body 2…", "Hide Body 2",
                      "Isolate Body 2", "Material"]   # M110 submenu,
    # M134 isolate
    menus[-1].actions()[2].trigger()             # the bulb
    qapp.processEvents()
    win.viewport.grab()                          # paints without it
    assert win.doc.bodies[1]["visible"] is False
    n1 = len(win.doc.body_solids()["Body 1"].to_render_arrays()[2])
    assert len(win.viewport._tm.faces) == n1
    win._body_menu("Body 2", win.geometry().center())
    assert [a.text() for a in menus[-1].actions()] == \
        ["Activate Body 2", "Paint Body 2…", "Show Body 2",
         "Isolate Body 2", "Material"]
    menus[-1].actions()[2].trigger()
    assert win.doc.bodies[1]["visible"] is True
