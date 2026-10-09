"""M153 — datum follow-through UI: the rung-D dialog + the viewport
letter overlay. Laws and EVERY number come from the executed receipts
(research/m153_spike1.md + the L4c/L4d stream-order measurements),
contract research/m153_datum_followthrough.md. The warning STRINGS stay
byte-identical (M152's gates re-defend them beside these); the dialog
reads the structured twins and never parses prose. Follow-relink is
sold ONLY for strictly-upstream hosts — receipt L4c measured the
silent death (buried 72000.0 forever) of every other shape, and a
dialog that sold it would be the product lying with a friendly face.
"""
import json

import numpy as np
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMessageBox

from tracer.core import params
from tracer.core.document import (Document, ExtrudeFeature, HoleFeature,
                                  PrimitiveFeature)
from tracer.ui import theme
from tracer.ui.mainwindow import _AttachmentsDialog


def _boss(name="Boss", handle="Pad"):
    outer = np.array([[0, 0], [20, 0], [20, 15], [0, 15]], float)
    return ExtrudeFeature(name=name, outer=outer, height=5.0,
                          placement=(0.0, 0.0, 10.0), plane="FACE",
                          axes=[[1, 0, 0], [0, 1, 0]],
                          handle={"feature": handle, "part": "cap-top"})


def _rib():
    return ExtrudeFeature(name="Rib", outer=np.array([[0, 0], [10, 0],
                                                      [10, 5]], float),
                          height=4.0)


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


def _px(widget):
    from PySide6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    widget.grab().save(buf, "PNG")
    buf.close()
    return np.asarray(__import__("PIL.Image", fromlist=["Image"])
                      .open(__import__("io").BytesIO(
                          bytes(buf.data()))).convert("RGB"), dtype=int)


# ---- G1: issues mirror warnings — three species, same order -----------

def test_follow_species_twin():
    d = Document("g1a")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    d.add(_boss())
    d.recompute()
    d.features.remove(d.features[0])
    d.recompute()
    assert d.attachment_issues == [dict(species="follow", owner="Boss",
                                        dead="Pad")]
    assert d.attachment_warnings[0].startswith("Boss \u2014 ")
    assert d.result.volume == 1500.0              # M152 freeze, alive


def test_host_species_twin():
    d = Document("g1b")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    p = d.add_plane("XY", 15.0)
    f = d.add(_rib())
    f.sketch = {"host": p["name"]}
    d.recompute()
    vol = d.result.volume
    d.remove_plane(p["name"])
    d.recompute()
    assert d.attachment_issues == [dict(species="host", owner="Rib",
                                        dead="Plane 1")]
    assert "is gone \u2014 its frame is frozen" in \
        d.attachment_warnings[0]
    assert d.result.volume == vol == 24000.0      # M150's byte-zero law


def test_datum_species_twin():
    d = Document("g1c")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    pa = d.add_plane("XY", 20.0)
    d.datum_register("A", "plane", pa["name"])
    d.recompute()
    d.remove_plane(pa["name"])
    d.recompute()
    assert d.attachment_issues == [dict(species="datum", owner="A",
                                        dead="Plane 1")]
    assert d.attachment_warnings[0].startswith("datum A is mute \u2014 ")


def test_issues_are_session_only_like_warnings():
    d = Document("g1d")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    d.recompute()
    assert d.attachment_issues == []
    assert "attachment_issues" not in json.dumps(d.to_dict())


# ---- G2/G3: the host species verbs (frozen frame survives both) --------

def _host_doc(tag):
    d = Document(tag)
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    p = d.add_plane("XY", 15.0)
    f = d.add(_rib())
    f.sketch = {"host": p["name"]}
    d.recompute()
    d.remove_plane(p["name"])
    d.recompute()
    return d


def test_relink_sketch_clears_and_moves_nothing():
    d = _host_doc("g2")
    d.relink_sketch("Rib", "XY")
    d.recompute()
    assert d.attachment_warnings == [] and d.attachment_issues == []
    assert d.result.volume == 24000.0             # receipt L2, byte-equal
    with pytest.raises(params.ParamError, match="not live"):
        d.relink_sketch("Rib", "Plane 1")         # dead ref refused
    with pytest.raises(params.ParamError, match="no sketch host"):
        d.relink_sketch("Pad", "XY")              # wrong-species refusal


def test_break_sketch_is_lawful_silence():
    d = _host_doc("g3")
    d.break_sketch("Rib")
    d.recompute()
    assert d.attachment_warnings == []
    assert d.result.volume == 24000.0             # receipt L3


# ---- G4/G5/G6: the follow species — stream order IS the law ------------

def _follow_doc(tag):
    d = Document(tag)
    pad = d.add(PrimitiveFeature(name="Pad", kind="box",
                                 dims={"dx": 60, "dy": 40, "dz": 10}))
    d.add(PrimitiveFeature(name="Dead", kind="box",
                           dims={"dx": 5, "dy": 5, "dz": 5}))
    d.add(_boss(handle="Nope"))                   # dead from the start
    d.add(PrimitiveFeature(name="Late", kind="box",
                           dims={"dx": 1, "dy": 1, "dz": 1}))
    d.recompute()
    return d, pad


def test_relink_follow_upstream_then_host_edits_follow():
    d, pad = _follow_doc("g4")
    assert d.attachment_issues == [dict(species="follow", owner="Boss",
                                        dead="Nope")]
    d.relink_follow("Boss", "Pad")
    assert d.recompute().volume == 25500.0        # measured alive twin
    assert d.attachment_issues == []
    pad.dims["dz"] = 20.0
    assert d.recompute().volume == 49500.0        # the promise: FOLLOWING


def test_relink_follow_refuses_downstream_self_and_dead():
    d, _ = _follow_doc("g5")
    for bad, why in (("Late", "does not sit strictly"),
                     ("Boss", "itself"),
                     ("Ghost", "does not sit strictly")):
        with pytest.raises(params.ParamError, match=why):
            d.relink_follow("Boss", bad)
    d.recompute()
    assert d.attachment_warnings                  # refusals arm nothing
    # host recreated AFTER the owner is downstream — the G4-shape trap
    # M152 G4 healed by name; the dialog law: never sell the freeze
    d.features.remove(d.features[0])
    d.recompute()
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    with pytest.raises(params.ParamError, match="strictly"):
        d.relink_follow("Boss", "Pad")


def test_break_follow_none_is_silent_and_permanent():
    d, pad = _follow_doc("g6")
    d.relink_follow("Boss", "Pad")
    d.recompute()
    d.break_follow("Boss")
    d.recompute()
    pad.dims["dz"] = 30.0
    assert d.recompute().volume == 72000.0        # M152 buried signature
    assert d.attachment_warnings == []            # and SILENT forever
    assert '"handle": null' in json.dumps(d.to_dict())
    with pytest.raises(params.ParamError, match="follows nothing"):
        d.break_follow("Boss")                    # nothing left to break


# ---- G7: the datum species relink is atomic ----------------------------

def test_relink_datum_atomic_and_clearing():
    d = Document("g7")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    pa = d.add_plane("XY", 3.0)
    d.datum_register("A", "plane", pa["name"])
    d.remove_plane(pa["name"])
    d.recompute()
    assert d.attachment_issues[0]["owner"] == "A"
    with pytest.raises(params.ParamError):
        d.relink_datum("A", "plane", "Plane 9")
    assert d.datums[0]["ref"] == "Plane 1"        # the OLD binding lives
    d.relink_datum("A", "plane", "XZ")
    d.recompute()
    assert d.attachment_warnings == []
    with pytest.raises(params.ParamError, match="register it fresh"):
        d.relink_datum("Q", "plane", "XY")


# ---- G8: candidate sets — resolvable, sorted, self-less, uid-bound -----

def test_candidate_sets_are_the_kernels_own_domain():
    d = Document("g8")
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    p = d.add_plane("XY", 12.0)
    assert d.plane_candidates() == ["Plane 1", "XY", "XZ", "YZ"]
    d.remove_plane(p["name"])
    assert d.plane_candidates() == ["XY", "XZ", "YZ"]   # dead drops out
    assert d.axis_candidates()[:4] == ["X", "Y", "Z"]
    hole = d.add(HoleFeature(name="H1", center=(30.0, 20.0, 5.0),
                             radius=3.2, depth=12.0))
    hc = d.hole_axis_candidates()
    assert hc == [("H1", hole.uid)], hc           # DISPLAY name, BIND uid
    d.add(_boss())
    assert d.follow_candidates("Boss") == ["H1", "Pad"]  # sorted, self out


# ---- G9: the letter overlay — paint-only, mute-silent, toggleable ------

def test_datum_letter_paints_hides_and_toggles(win, qapp):
    d = win.doc
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    d.datum_register("A", "plane", "XY")
    win.recompute()
    vp = win.viewport
    for _ in range(3):                             # flush layout before
        qapp.processEvents()                       #  the pixel pair
    # differential law, not projected-position guesses (the camera may
    # re-fit after attach — the ink delta between show/hide frames is
    # what the renderer actually measured):
    on = _px(vp)
    vp.show_datums = False
    vp.update()
    off = _px(vp)
    lit = int((np.abs(on - off).sum(axis=2) > 30).sum())
    assert lit > 40, f"the [A] never painted ({lit} px)"
    vp.show_datums = True
    vp.update()
    assert np.array_equal(_px(vp), on), "paint must be deterministic"


def test_mute_letter_paints_nothing_and_never_raises(win):
    d = win.doc
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    pa = d.add_plane("XY", 25.0)
    d.datum_register("A", "plane", pa["name"])
    win.recompute()
    xy = win.viewport._cam.project((0.0, 0.0, 25.0),
                                   win.viewport.width(),
                                   win.viewport.height())
    assert xy is not None
    x0, y0 = int(xy[0]) + 2, int(xy[1]) - 26
    with_letter = _px(win.viewport)[y0:y0 + 26, x0:x0 + 52]
    d.remove_plane(pa["name"])
    win.recompute()
    assert d.attachment_issues                   # the badge's business
    win.viewport.show_datums = False
    win.viewport.update()
    bare = _px(win.viewport)[y0:y0 + 26, x0:x0 + 52]
    win.viewport.show_datums = True
    win.viewport.update()
    muted = _px(win.viewport)[y0:y0 + 26, x0:x0 + 52]
    assert np.array_equal(bare, muted), "a mute letter echoed in 3-D"


def test_layout_toggle_command_flips_datums(win):
    from tracer.ui.commands import MODEL_KEYS
    assert MODEL_KEYS["Ctrl+Alt+D"][1] == "layout:datums"
    before = win.viewport.show_datums
    assert win._layout_toggle("datums") is True
    assert win.viewport.show_datums is not before
    assert win._layout_toggle("datums") is True
    assert win.viewport.show_datums is before


# ---- G10: the dialog — door only when issues; verbs drive the kernel ---

def test_root_menu_offers_the_door_only_when_it_opens_something(win):
    d = win.doc
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    p = d.add_plane("XY", 15.0)
    f = d.add(_rib())
    f.sketch = {"host": p["name"]}
    win.recompute()
    texts = lambda: [a.text() for a in win._root_menu_open.actions()] \
        if win._root_menu_open else []            # noqa: E731
    win._root_menu(QPoint(0, 0))
    assert "Manage Lost Attachments\u2026" not in texts()   # nothing lost
    d.remove_plane(p["name"])
    win.recompute()
    win._root_menu(QPoint(0, 0))
    assert "Manage Lost Attachments\u2026" in texts()       # armed door


def test_dialog_relink_clears_the_issue(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning",
                        classmethod(lambda cls, *a, **k: None))
    d = win.doc
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    p = d.add_plane("XY", 15.0)
    f = d.add(_rib())
    f.sketch = {"host": p["name"]}
    win.recompute()
    d.remove_plane(p["name"])
    win.recompute()
    dlg = _AttachmentsDialog(win)
    assert dlg._issue.count() == 1
    cands = [dlg._cands.itemText(i)
             for i in range(dlg._cands.count())]
    assert cands == ["XY", "XZ", "YZ"]           # host species law
    assert dlg._break_btn.text() == "Detach"
    dlg._relink()                                 # first candidate: XY
    assert d.attachment_warnings == []
    assert d.attachment_issues == []
    assert f.sketch["host"] == "XY"
    assert d.result.volume == 24000.0            # frozen frame intact
    assert not dlg._relink_btn.isEnabled()       # the door closed itself
    assert "Nothing is lost" in dlg._detail.text()


def test_dialog_refusals_speak_the_kernels_own_sentence(win,
                                                        monkeypatch):
    shown = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        classmethod(lambda cls, *a, k=None, **kw:
                    shown.append(a[2] if len(a) > 2 else "")))
    d = win.doc
    d.add(PrimitiveFeature(name="Pad", kind="box",
                           dims={"dx": 60, "dy": 40, "dz": 10}))
    d.add(_boss(handle="Ghost"))                 # follow species, armed
    win.recompute()
    dlg = _AttachmentsDialog(win)
    assert dlg._issue.count() == 1
    assert dlg._break_btn.text() == "Stop Following"
    d.features.remove(d.features[0])             # Pad gone: no upstream
    win.recompute()
    dlg._reload()
    assert dlg._cands.count() == 0               # nothing lawful to sell
    d.break_follow("Boss")
    win.recompute()
    assert d.attachment_warnings == []           # the freeze keeps the
    assert d.result.volume == 1500.0             # measured buried shape
