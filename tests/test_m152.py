"""M152 (rung D): the datum wears its letter, silence dies.

Rungs A–C made the sketch DERIVED, LANDED and FOLLOWING; M150 made
letters REAL. This welds the halves and kills the product's last
SILENT failures: the dead face-handle freeze, the mute datum letter,
the stale sketch host. The law the gates pin, from the banked
contract (research/sketch_datum_rungD.md, §8 probes RE-RUN at tip
before any product line — spike1 follow z == 20.0, spike2's voices,
spike5's buried boss 72000.0, spike6's 24000.0 byte-zero churn):

geometry is UNTOUCHED by letters (G2: register/remove is a byte-zero
event); the frozen handle now SPEAKS (G3) but only as a session list
(G4); hints rank beside the validator, never above it (G5); the
registry never touches the paper (G6, the DXF op census); the badge
is the message's second copy — row letters, amber chips on the red
badge's OWN corner, red outranking amber (G7); rename is a COUNTED
relink and the buried-boss rot cannot recur (G8); the delete dialog
names the letter BEFORE the click (G9); the sketch carries a NAME
witness and the dialog path opens no dialog (G10).
"""
import io
import json
import re

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice

from tracer.core import gdt
from tracer.core.document import (Document, HoleFeature,
                                  MirrorFeature, PrimitiveFeature,
                                  ExtrudeFeature)
from tracer.ui import theme
from tracer.ui.panels import FeatureTree


def _nd_handle():
    """spike5's boss, verbatim: a 20x15 cap-top handle extrude."""
    outer = np.array([[0, 0], [20, 0], [20, 15], [0, 15]], float)
    return ExtrudeFeature(name="Boss", outer=outer, height=5.0,
                          placement=(0.0, 0.0, 10.0), plane="FACE",
                          axes=[[1, 0, 0], [0, 1, 0]],
                          handle={"feature": "Pad", "part": "cap-top"})


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def win(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1200, 800)
    w.show()
    qapp.processEvents()
    w.new_document()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    qapp.processEvents()


def _rows(tree):
    out = []

    def walk(item):
        for i in range(item.childCount()):
            c = item.child(i)
            out.append(c.text(0))
            walk(c)
    walk(tree.invisibleRootItem())
    return out


def _px(widget):
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    widget.grab().save(buf, "PNG")
    buf.close()
    return np.asarray(Image.open(io.BytesIO(buf.data())).convert(
        "RGB")).astype(int)


def _rgb(hexs):
    h = hexs.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)])


# ---- G1: the registry as the tree sees it (pure) -----------------------

def test_datum_badges_keys_planes_by_name_and_holes_by_uid():
    d = Document("g1")
    d.add(PrimitiveFeature(name="pad", kind="box",
                           dims={"dx": 20, "dy": 20, "dz": 5}))
    hole = d.add(HoleFeature(name="bore", center=(5.0, 5.0, 5.0),
                             normal=(0.0, 0.0, -1.0), radius=2.0,
                             depth=5.0, through=True))
    pl = d.add_plane("XY", 15.0)
    d.recompute()
    assert FeatureTree.datum_badges(d) == {}       # unregistered: quiet
    d.datum_register("A", "plane", pl["name"])
    d.datum_register("C", "hole-axis", hole.uid)
    badges = FeatureTree.datum_badges(d)
    assert badges[pl["name"]] == ["A"]
    assert badges[hole.uid] == ["C"]               # uid, rename-immune


# ---- G2: a letter is a byte-ZERO geometry event (spike6) ----------------

def test_registering_a_letter_moves_no_float_and_no_key():
    d = Document("g2")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    pl = d.add_plane("XY", 15.0)
    v0 = d.recompute().volume
    assert repr(v0) == "24000.0"                   # spike6's repr
    dump0 = json.dumps({k: v for k, v in d.to_dict().items()
                        if k != "datums"}, sort_keys=True)
    d.datum_register("A", "plane", pl["name"])
    assert d.recompute().volume == v0              # ==, not ~
    d.datum_remove("A")
    assert d.recompute().volume == v0
    assert json.dumps({k: v for k, v in d.to_dict().items()
                       if k != "datums"},
                      sort_keys=True) == dump0     # no new keys


# ---- G3: the frozen handle speaks at last (was pure silence) -----------

def test_the_dead_host_freeze_now_names_itself():
    d = Document("g3")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    boss = d.add(_nd_handle())
    d.recompute()
    d.features.remove(d.features[0])               # delete the HOST
    v = d.recompute()                              # SUCCEEDS (freeze)
    assert v.volume == 1500.0                      # spike1's frozen boss
    assert getattr(boss, "error", None) is None    # NOT a failure (the
    (line,) = d.attachment_warnings                #  NO-ATTR is spike4's
    assert line.startswith("Boss — ")              #  measured fact) —
    assert "no feature named 'Pad' to follow" in line   # yet LOUDER
    #                                   than the silence that was all law


# ---- G4: session law — never serialized, clears when the host lives ----

def test_warnings_are_session_only_and_clear_with_a_living_host():
    d = Document("g4")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    d.add(_nd_handle())
    d.recompute()
    d.features.remove(d.features[0])
    d.recompute()
    assert d.attachment_warnings                   # armed
    assert "attachment_warnings" not in json.dumps(d.to_dict())
    d.add(PrimitiveFeature(name="Pad", kind="box",   # recreate BY NAME
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    d.recompute()
    assert d.attachment_warnings == []             # clean pass, clean


# ---- G5: hints rank BESIDE the validator, never above it ---------------

def test_datum_hints_speaks_letters_the_validator_stays_grammar_only():
    h = gdt.datum_hints(["A", "B-D", "C"], {"B"})
    assert [x.split(" is")[0] for x in h] == ["datum A", "datum C",
                                              "datum D"]      # spike6
    assert all("not registered" in x and "Register as Datum" in x
               for x in h)
    assert gdt.datum_hints(["A-B"], {"A", "B"}) == []
    assert gdt.datum_hints([], set()) == []
    with pytest.raises(ValueError, match="empty datum compartment"):
        gdt.gdt_validate({"sym": "position", "tol": "0.2",
                          "datums": [""]})         # the gate: untouched
    gdt.gdt_validate({"sym": "position", "tol": "0.2", "datums": ["R"],
                      "target": {}})               # R unregistered (Z
    #   would never reach here — RESERVED IOQSXZ is GRAMMAR's business):
    #   the grammar NEVER consults the Document — hints own that voice


# ---- G6: the registry never touches the paper (M150 BOM law extended) --

def test_two_letters_add_zero_dxf_ops_and_zero_sheet_keys(qapp, win,
                                                          tmp_path):
    d = Document("g6")
    d.add(PrimitiveFeature(name="pad", kind="box",
                           dims={"dx": 40, "dy": 25, "dz": 12}))
    pl = d.add_plane("XY", 12.0)
    stud = d.add(PrimitiveFeature(name="stud", kind="cylinder",
                                  dims={"radius": 4.0, "height": 10.0}))
    d.add(MirrorFeature(name="mirror", source_uid=stud.uid,
                        plane=pl["name"]))
    d.recompute()
    win.doc = d
    win.recompute()
    win.action_new_drawing()
    qapp.processEvents()

    def ops(path):
        txt = open(path, encoding="utf-8").read()
        return re.findall(r"^\s*0\s*\n\s*(\w+)", txt, re.M)

    a, b = str(tmp_path / "a.dxf"), str(tmp_path / "b.dxf")
    win.export_drawing(a)
    before, sheet0 = ops(a), json.dumps(d.drawings[0], sort_keys=True,
                                        default=str)
    d.datum_register("A", "plane", pl["name"])
    d.datum_register("B", "plane", "YZ")
    win.export_drawing(b)
    assert ops(b) == before                        # letters are PAINT
    assert json.dumps(d.drawings[0], sort_keys=True,
                      default=str) == sheet0       # never ink


# ---- G7a: rows wear letters; the warning state paints the row ----------

def test_tree_rows_wear_letters_and_the_amber_fg(qapp, win):
    d = Document("g7")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    boss = d.add(_nd_handle())
    pl = d.add_plane("XY", 15.0)
    d.recompute()
    win.doc = d
    win.recompute()
    win.rail.tree.reload()
    qapp.processEvents()
    assert any(t == "\u25ad " + pl["name"] for t in _rows(win.rail.tree))
    d.datum_register("A", "plane", pl["name"])
    win.rail.tree.reload()
    assert any(t == "\u25ad " + pl["name"] + " [A]"
               for t in _rows(win.rail.tree))      # the SAME string

    def boss_row():
        # tree.reload() DELETES the old QTreeWidgetItems — never hold
        # one across a reload, walk fresh every time
        rows = []

        def walk(it):
            for k in range(it.childCount()):
                ch = it.child(k)
                rows.append(ch)
                walk(ch)
        walk(win.rail.tree.invisibleRootItem())
        return next(r for r in rows if r.text(0).endswith(boss.name))

    # the amber state, on the row:
    d.features.remove(d.features[0])
    win.recompute()                                # frozen, warned
    win.rail.tree.reload()
    qapp.processEvents()
    warn = _rgb(theme.DARK["warn"])
    got = np.array([boss_row().foreground(0).color().red(),
                    boss_row().foreground(0).color().green(),
                    boss_row().foreground(0).color().blue()])
    assert (got == warn).all()                     # amber foreground
    d.add(PrimitiveFeature(name="Pad", kind="box",   # host lives again
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    win.recompute()
    win.rail.tree.reload()
    qapp.processEvents()
    assert boss_row().foreground(0).color().name() != \
        theme.DARK["warn"]                         # predicate CLEARS


# ---- G7b: the chip corner — amber sibling, red outranks, clears --------

def test_the_timeline_badge_is_amber_then_red_then_gone(qapp, win,
                                                        monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    d = Document("g7b")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    boss = d.add(_nd_handle())
    d.recompute()
    win.doc = d
    win.recompute()
    d.features.remove(d.features[0])
    win.recompute()
    assert win.status.currentMessage() == d.attachment_warnings[0]
    warn, dang = _rgb(theme.DARK["warn"]), _rgb(theme.DARK["danger"])
    tl = _px(win.timeline.bar)
    am = ((np.abs(tl - warn) < 40).all(axis=2)).sum()
    rd = ((np.abs(tl - dang) < 40).all(axis=2)).sum()
    assert am > 8 and rd == 0                      # the amber SIBLING
    monkeypatch.setattr(QMessageBox, "warning",
                        classmethod(lambda cls, *a, **k: None))
    boss.error = "probe"                           # the chip ALSO
    win.timeline.bar.update()                      #   broke the last
    qapp.processEvents()
    tl = _px(win.timeline.bar)
    assert ((np.abs(tl - dang) < 40).all(axis=2)).sum() > 8
    assert ((np.abs(tl - warn) < 40).all(axis=2)).sum() == 0
    boss.error = None                              # predicate clears
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    win.recompute()
    tl = _px(win.timeline.bar)
    assert ((np.abs(tl - warn) < 40).all(axis=2)).sum() == 0


# ---- G8a: rename is a counted relink — the buried boss cannot recur ----

def test_rename_feature_defuses_the_landmine_with_the_count():
    d = Document("g8")
    pad = d.add(PrimitiveFeature(name="Pad", kind="box",
                                 dims={"dx": 60, "dy": 40, "dz": 10}))
    boss = d.add(_nd_handle())
    boss.sketch = {"name": "s1", "host": "",
                   "handle": {"feature": "Pad", "part": "cap-top"}}
    v0 = d.recompute().volume
    assert repr(v0) == "25500.0"                   # spike5's anchor
    n = d.rename_feature("Pad", "Slab")
    assert n == 1                                  # ONE handle (the
    assert boss.handle["feature"] == "Slab"        #   payload mirror
    assert boss.sketch["handle"]["feature"] == "Slab"    #   is SAME)
    pad.dims["dz"] = 30.0
    v = d.recompute().volume
    assert repr(v) == "73500.0"                    # FOLLOWING, live
    # the pre-M152 raw write froze the boss INSIDE the grown pad:
    # 72000.0 — spike5's measured burial, dead by construction now.
    with pytest.raises(Exception, match="already taken"):
        d.rename_feature("Slab", "Boss")
    assert d.features[0].name == "Slab"


def test_rename_feature_refusal_undoes_cleanly_at_the_ui_seam(qapp,
                                                              win,
                                                              monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.ui.cmddialog import Shell
    d = win.doc
    pad = d.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 20, "dy": 20, "dz": 4}))
    d.add(PrimitiveFeature(name="stud", kind="box",
                           dims={"dx": 4, "dy": 4, "dz": 10}))
    win.recompute()
    monkeypatch.setattr(Shell, "getText", staticmethod(
        lambda p, t, l, text="": ("stud", True)))
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", classmethod(
        lambda cls, *a, **k: seen.append(a[2])))
    depth = len(win._undo)
    win._rename_feature(pad)
    qapp.processEvents()
    assert pad.name == "plate"                     # refused
    assert any("already taken" in s for s in seen)
    assert len(win._undo) == depth                 # capture popped


# ---- G8c/G8d: the two other rename families keep their laws ------------

def test_renaming_the_datum_relinks_the_host_witness_counted():
    d = Document("g8c")
    pl = d.add_plane("XY", 5.0)
    box = d.add(PrimitiveFeature(name="Pad", kind="box",
                                 dims={"dx": 10, "dy": 10, "dz": 2}))
    stud = d.add(PrimitiveFeature(name="stud", kind="cylinder",
                                  dims={"radius": 4.0, "height": 4.0}))
    d.add(MirrorFeature(name="mir", source_uid=stud.uid,
                        plane=pl["name"]))
    holder = d.add(_nd_handle())                   # carries a sketch
    holder.sketch = {"name": "s", "host": pl["name"]}
    d.recompute()
    d.datum_register("A", "plane", pl["name"])
    refs = d.datum_references(pl["name"])
    assert "mir" in refs and "(datum A)" in refs   # letter counted
    assert "Boss" in refs                          # host witness too
    n = d.rename_datum(pl["name"], "Deck")
    assert n == 3                                  # spike2's 2 + the
    assert holder.sketch["host"] == "Deck"         #   witness joins


def test_a_hole_axis_letter_survives_the_feature_rename():
    d = Document("g8d")
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 20, "dy": 20, "dz": 5}))
    hole = d.add(HoleFeature(name="bore", center=(5.0, 5.0, 5.0),
                             normal=(0.0, 0.0, -1.0), radius=2.0,
                             depth=5.0, through=True))
    d.recompute()
    d.datum_register("C", "hole-axis", hole.uid)
    v0 = d.recompute().volume
    assert d.rename_feature("bore", "bore-again") == 0
    d.recompute()
    assert d.recompute().volume == v0              # uid: rename-immune
    d.datum_frame("C")                             # still resolves


# ---- G9: the delete dialog names the letter BEFORE the click -----------

def test_the_delete_warning_names_the_letter_and_the_hosted_sketch(
        qapp, win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    d = win.doc
    box = d.add(PrimitiveFeature(name="Pad", kind="box",
                                 dims={"dx": 10, "dy": 10, "dz": 2}))
    pl = d.add_plane("XY", 5.0)
    stud = d.add(PrimitiveFeature(name="stud", kind="cylinder",
                                  dims={"radius": 3.0, "height": 4.0}))
    d.add(MirrorFeature(name="mir", source_uid=stud.uid,
                        plane=pl["name"]))
    holder = d.add(_nd_handle())
    holder.sketch = {"name": "s", "host": pl["name"]}
    win.recompute()
    d.datum_register("A", "plane", pl["name"])
    texts = []
    monkeypatch.setattr(QMessageBox, "question", classmethod(
        lambda cls, *a, **k: texts.append(a[2])
        or QMessageBox.No))
    assert win._datum_delete_ok(pl["name"]) is False   # refused
    assert "(datum A)" in texts[0] and "Boss" in texts[0]


# ---- G10: the witness lands on a free hand — zero dialogs --------------

def test_sketch_on_a_datum_lands_the_witness_and_opens_no_dialog(
        qapp, win, monkeypatch):
    from tracer.ui import cmddialog
    calls = []

    def fake_ask(parent, title, fields, remember_key=None):
        calls.append(title)
        return {}
    monkeypatch.setattr(cmddialog, "ask", fake_ask)
    d = win.doc
    pl = d.add_plane("XY", 10.0)
    d.recompute()
    d.datum_register("A", "plane", pl["name"])
    win.action_sketch_on_plane(pl["name"])
    qapp.processEvents()
    assert calls == []                             # guard-first shape
    assert win.sketch.model.host == pl["name"]     # the WITNESS lands
    msg = win.status.currentMessage()
    assert f"Sketching on {pl['name']} [A]" in msg # the letter speaks
    assert win.sketch.model.plane == "FACE"        # frame law intact
    win._show_page(win.viewport)                   # leave the editor
    qapp.processEvents()
