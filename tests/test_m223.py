"""M201 R35 - the page's Automated Center Marks group lives in OUR door.

[DWG-REF-DRAWING-VIEW-DLG, verbatim; raw HTML banked cache/inv17/raw]
The reference page's heading order prints the group immediately after
Appearance - "Automated Center Marks and Center Lines: Automatically
create center lines and center marks for all holes in a view." - with
"Center Marks: Choose the hole types that receive automated center
marks." and its first member "Hole: Creates a center mark for hole
features." The task page says where the group is reached: "you can do
that while creating the view, or later by DOUBLE-CLICKING THE VIEW" -
which is exactly the door R32/R33 shipped.  So the row enters here, and
it enters ONLY where the kernel really stands the cross: M129's
hole_marks() answers per view and stays silent for an ISO view ("a bore
seen at an angle shows no true circle") and for a bore across the
sight, and a row that toggles nothing would be decoration - forbidden.
UNOFFERED BY NAME, each because no record exists to classify: "Round
Extrudes", "Round Cuts", "Pattern", "Fillet" and the page's
"Minimum/Maximum fillet radius (Fillet only)" fields, plus the whole
"Center Lines" sub-group (Hole/Round Extrudes/Round Cuts) - this
painter owns no automated centre-LINE ink, so wearing that row would
make the page's own words a lie.  Storage is DEVIATIONS ONLY (the
vscale coin): the page prints zero defaults, M129 shipped the cross ON,
so "off" is the only stored answer and ticking it back pops the key -
and the answer retires the MARK alone, leaving the item bubble and the
hole table (other families' ink) standing.  Cancel rides the book-wide
silence."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage                              # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402
import numpy as np                                            # noqa: E402

from tracer.core import drawing                               # noqa: E402
from tracer.core.document import (Document, HoleFeature,      # noqa: E402
                                  PrimitiveFeature)
from tracer.ui import cmddialog                               # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    """A plate with a vertical bore (its true circle shows in TOP) and
    a horizontal side bore (its true circle shows in FRONT): the two
    views answer for themselves, so a per-view answer can be told
    apart from a sheet-wide switch."""
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 760)
    w.show()
    qapp.processEvents()
    w.new_document()
    d = w.doc
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    d.add(HoleFeature(name="bore", op="subtract", center=(20, 15, 6),
                      normal=(0, 0, -1), radius=5.0, depth=6,
                      cut_length=6, through=True))
    d.add(HoleFeature(name="side", op="subtract", center=(10, 0, 3),
                      normal=(0, 1, 0), radius=3.0, depth=30,
                      cut_length=30, through=True))
    w.recompute()
    w.action_new_drawing()
    w._show_page(w._drawing_page)
    qapp.processEvents()
    yield w
    w._unsaved = False
    w._discard_guard = lambda: True
    w.close()
    r.close()


def _grab(cv):
    img = cv.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(img.constBits().tobytes(), np.uint8).reshape(
        img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), :3].copy()


def _dark(cell):
    return int((cell.max(axis=2) < 140).sum())


def _spy(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda p, t, fl, **k: (calls.append({f["key"]: f for f in fl}),
                               None)[1])
    return calls


def _cross_crop(win, view):
    """The pixel neighbourhood of a hole's projected centre, standing
    the canvas up first (the draughtsman's own knobs) so the cross is a
    real run of pixels and not a sub-pixel story."""
    cv = win.drawing
    marks = drawing.hole_marks(win.doc)[view]
    m = marks[0]
    fr = cv.placed()[view]
    cv._zoom = 6.0
    from PySide6.QtCore import QPointF
    cv._center = QPointF(*cv._m2p(fr, (m["x"], m["y"])))
    q = cv.s2p(*cv._m2p(fr, (m["x"], m["y"])))
    cell = _grab(cv)
    half = 90
    return cell[max(0, int(q.y()) - half):int(q.y()) + half,
                max(0, int(q.x()) - half):int(q.x()) + half]


# ---- the door --------------------------------------------------------------------

def test_the_door_grows_the_pages_group_where_the_cross_stands(win,
                                                               qapp,
                                                               monkeypatch):
    calls = _spy(monkeypatch)
    win.drawing.view_scale_requested.emit("top")
    qapp.processEvents()
    specs, = calls                             # ONE dialog, our door
    assert list(specs) == ["style", "scale", "hmarks"]
    f = specs["hmarks"]
    assert f["group"] == "Automated Center Marks and Center Lines"
    assert f["label"] == "Center Marks"        # the settings page's
    #   form (the creation page's "Centermarks" is flagged drift)
    assert f["kind"] == "checks"
    assert f["choices"] == ["Hole"]            # the ONE backable member
    assert f["checked"] == ["Hole"]            # rest = M129's shipped ON


def test_the_iso_door_never_wears_a_row_the_ink_cannot_back(win, qapp,
                                                            monkeypatch):
    """hole_marks() answers no ISO entry (no true circle at an angle),
    so the group is NOT offered there - a row that toggles nothing is
    decoration."""
    cv = win.drawing
    assert "iso" not in drawing.hole_marks(win.doc)
    calls = _spy(monkeypatch)
    cv.view_scale_requested.emit("iso")
    qapp.processEvents()
    specs, = calls
    assert list(specs) == ["style", "scale"]   # byte-true R32 shape


def test_the_unbackable_members_are_unoffered_by_name(win, qapp,
                                                      monkeypatch):
    calls = _spy(monkeypatch)
    win.drawing.view_scale_requested.emit("top")
    qapp.processEvents()
    specs, = calls
    words = " | ".join(
        [f["label"] for f in specs.values()]
        + [str(c) for f in specs.values() for c in f.get("choices", ())])
    for name in ("Round Extrudes", "Round Cuts", "Pattern", "Fillet",
                 "fillet radius", "Center Lines"):
        assert name not in words, f"{name} is unoffered by name"


# ---- the ink ---------------------------------------------------------------------

def test_unticking_the_hole_member_retires_the_cross_not_the_bubble(
        win, qapp, monkeypatch):
    cv = win.drawing
    before = _dark(_cross_crop(win, "top"))
    assert before > 60, f"the cross must be real ink first: {before}"
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": cv.view_style("top"), "scale": "Fit (auto)",
        "hmarks": []})                          # the member UNCHECKED
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    after = _dark(_cross_crop(win, "top"))
    assert before - after > 40, (
        f"the dash-dot cross must retire: {before} -> {after}")
    # the bore's own circle still stands (other families' ink untouched)
    assert after > 60, f"the rim must survive the mark: {after}"


def test_a_views_answer_is_not_another_views(win, qapp, monkeypatch):
    """The page's words are "for all holes IN A VIEW": the answer rides
    the view it was given, never the sheet."""
    cv = win.drawing
    marks = drawing.hole_marks(win.doc)
    assert {"top", "front"} <= set(marks)      # both views really
    #   stand a cross (bore in top, side bore in front)
    front_before = _dark(_cross_crop(win, "front"))
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": cv.view_style("top"), "scale": "Fit (auto)",
        "hmarks": []})
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert cv.sheet()["hmarks"] == {"top": False}   # ONLY top answers
    assert _dark(_cross_crop(win, "front")) == front_before


# ---- the storage law -------------------------------------------------------------

def test_off_is_the_only_deviation_and_ticking_back_pops_it(win, qapp,
                                                            monkeypatch):
    cv = win.drawing
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": cv.view_style("top"), "scale": "Fit (auto)",
        "hmarks": []})
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert cv.sheet()["hmarks"]["top"] is False
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": cv.view_style("top"), "scale": "Fit (auto)",
        "hmarks": ["Hole"]})                   # back to the rest
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert "hmarks" not in cv.sheet()          # file-minimal again


def test_the_answer_rides_the_file_and_one_undo(win, qapp, monkeypatch):
    cv = win.drawing
    cv.sheet().pop("hmarks", None)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": cv.view_style("top"), "scale": "Fit (auto)",
        "hmarks": []})
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    back = Document.from_dict(win.doc.to_dict())      # the file's word
    assert back.drawings[-1]["hmarks"]["top"] is False
    win.undo()                                       # one press back
    qapp.processEvents()
    assert "hmarks" not in cv.sheet()


def test_a_rejected_dialog_changes_nothing(win, qapp, monkeypatch):
    cv = win.drawing
    cv.sheet().pop("hmarks", None)
    before = _dark(_cross_crop(win, "top"))
    doc0 = win.doc.to_dict()
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: None)  # Cancel
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert "hmarks" not in cv.sheet()
    assert win.doc.to_dict() == doc0
    assert _dark(_cross_crop(win, "top")) == before
