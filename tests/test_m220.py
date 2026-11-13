"""M201 R32 - the Drawing View dialog: Style rides in on the gesture.

[DWG-REF-DRAWING-VIEW-DLG, verbatim; live-verified lane D 2026-11-13,
served 10,467 = the dwg29 bank byte-for-byte] "In the Drawing View
dialog, you can edit the properties of a drawing view" - the TITLE is
page-printed - and the access line is the gesture we already answer:
"Double-click a base view, projected view, section view, detail view,
or perspective view."  The page's Appearance section prints its rows
in this order - "Adjust the Orientation, Style, Scale, and Name
settings." - so the dialog wears Style then Scale, the two rows this
kernel can back for a base view.  Style's gloss is verbatim "Select
the view style for the selected drawing view."; of the five printed
members only TWO are offered: "From Parent" the page itself scopes
away from base views ("(Projected view, section view, and detail view
only.)"), and "Shaded"/"Shaded with Hidden Edges" stay UNOFFERED-BY-
NAME - every view brush on this sheet is NoBrush (the line-art truth
of paintPage), and decoration is forbidden, the Show-Hatch law.  The
page prints Default: ZERO times and bare "default" zero - the resting
member is OURS-declared, and the honest rest is what today's painter
actually shows: dashed back ink on = "Visible Edges and Hidden
Edges".  The reference form rules; the task pages' "Visible and
Hidden Edges" is flagged vendor label drift.  Scale keeps M100's
picker verbatim; the page's "or type a custom scale" stays unoffered
(the dropdown is our honest coin, declared).  The typed answer is
guarded defense-in-depth: an unoffered member refused by name.
Cancel rides the book-wide silence (Cancel counts 0 in 164 pages);
the reference page prints OK zero times, so no result sentence is
quoted - the status line is ours."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QEvent, QPointF             # noqa: E402
from PySide6.QtGui import QImage, QMouseEvent              # noqa: E402
from PySide6.QtWidgets import QApplication                 # noqa: E402

import numpy as np                                          # noqa: E402
from tracer.core.document import Document, PrimitiveFeature  # noqa: E402
from tracer.ui import cmddialog                             # noqa: E402
from tracer.ui.drawingview import (VIEW_STYLES,             # noqa: E402
                                   VIEW_STYLE_DEFAULT)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        from tracer.ui.mainwindow import MainWindow
        from tracer.ui.renderer import SceneRenderer
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _box_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Block", kind="box", dims={"dx": 40.0, "dy": 20.0,
                                        "dz": 10.0}))
    win.recompute()
    win.action_new_drawing()
    qapp.processEvents()
    return win.drawing


def _grab(cv):
    img = cv.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(img.constBits().tobytes(), np.uint8).reshape(
        img.height(), img.bytesPerLine() // 4, 4)[
        :, :img.width(), :3].copy()


# ---- the dialog contract ---------------------------------------------------------

def test_the_dialog_wears_the_page_title_and_the_page_order(win, qapp,
                                                            monkeypatch):
    calls = []
    monkeypatch.setattr(cmddialog, "ask",
                        lambda p, t, fl, **k: (calls.append(
                            (t, {f["key"]: f for f in fl})), None)[1])
    cv = _box_sheet(win, qapp)
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    (title, specs), = calls
    assert title == "Drawing View"                    # PAGE-PRINTED
    assert list(specs) == ["style", "scale"]          # Appearance order
    assert specs["style"]["choices"] == list(VIEW_STYLES)
    assert specs["style"]["choices"] == [
        "Visible Edges", "Visible Edges and Hidden Edges"]   # verbatim
    assert specs["scale"]["choices"][0] == "Fit (auto)"      # M100 law
    # no Default: is printed anywhere on the page - the rest is OURS,
    # and it is the member the painter actually shows today:
    assert specs["style"]["default"] == VIEW_STYLE_DEFAULT
    assert specs["scale"]["default"] == "Fit (auto)"  # unrest view


# ---- the style lands and the ink obeys --------------------------------------------

def test_visible_edges_removes_the_back_ink_and_the_rest_stores_nothing(
        win, qapp, monkeypatch):
    """The pair is told by PIXELS where the kernel has back ink to
    hide: for a plain box the orthographic hidden chains coincide
    with the outline (HLR culls them - measured: hidden segs 0) and
    only the ISO view really carries dashed creases (3 segs).  So the
    ink gate rides "iso" - a prose claim measured off project_hidden,
    never off a wish."""
    cv = _box_sheet(win, qapp)
    cv.resize(900, 640)
    qapp.processEvents()
    before = _grab(cv)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": "Visible Edges", "scale": "Fit (auto)"})
    cv.view_scale_requested.emit("iso")
    qapp.processEvents()
    assert cv.sheet()["vstyle"]["iso"] == "Visible Edges"
    after = _grab(cv)
    changed = int((np.abs(before.astype(int) - after.astype(int))
                   .max(axis=2) > 24).sum())
    assert changed > 50, f"the dashed creases must vanish: {changed}"
    # the DEVIATION coin: answering the rest member stores nothing
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": VIEW_STYLE_DEFAULT, "scale": "Fit (auto)"})
    cv.view_scale_requested.emit("iso")
    qapp.processEvents()
    assert "vstyle" not in cv.sheet()
    back = _grab(cv)
    same = int((np.abs(before.astype(int) - back.astype(int))
                .max(axis=2) > 24).sum())
    assert same <= 50, f"the rest member must restore the ink: {same}"


def test_both_rows_land_on_one_answer(win, qapp, monkeypatch):
    cv = _box_sheet(win, qapp)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": "Visible Edges", "scale": "1:2"})
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert cv.sheet()["vstyle"]["top"] == "Visible Edges"
    assert cv.sheet()["vscale"]["top"] == pytest.approx(0.5)
    assert cv.frames()["top"][0] == pytest.approx(0.5)
    msg = win.status.currentMessage().lower()
    assert "style" in msg and "scale" in msg          # one dialog,
    #                                                 one sentence


def test_an_unoffered_member_refused_by_name_changes_nothing(win, qapp,
                                                             monkeypatch):
    cv = _box_sheet(win, qapp)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": "Shaded", "scale": "1:2"})           # the combo can
    #   never answer this - defense in depth for programmatic coins
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert "vstyle" not in cv.sheet()
    assert "vscale" not in cv.sheet()                 # NOTHING landed
    assert "unoffered by name" in win.status.currentMessage()


def test_a_rejected_dialog_changes_nothing(win, qapp, monkeypatch):
    cv = _box_sheet(win, qapp)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: None)
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert "vstyle" not in cv.sheet() and "vscale" not in cv.sheet()


# ---- the fork and the file ---------------------------------------------------------

def test_the_double_click_fork_still_delivers_the_base_branch(win, qapp):
    """R32 rewires only what the FORK delivers to the view dialog, and
    it rewires the ANSWER, never the SIGNAL: m137's fork law (a
    section child answers its own M137 props - the page's Name/Depth/
    Objects-to-Cut family it already owns) stays pinned where it
    lives; this gate pins the base branch the dialog now rides."""
    cv = _box_sheet(win, qapp)
    props, views = [], []
    cv.section_edit_requested.connect(props.append)
    cv.view_scale_requested.connect(views.append)

    def dbl(view):
        fr = cv.placed()[view]
        c = np.asarray(fr["ctr"], float)
        wp = cv.s2p(*c)
        ev = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(wp),
                         QPointF(wp), QPointF(wp), Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        cv.mouseDoubleClickEvent(ev)

    dbl("top")
    assert views == ["top"] and props == []           # the fork's
    #   base branch still rides the SAME signal (m137's law holds)


def test_the_dialog_echoes_the_views_current_answers(win, qapp,
                                                     monkeypatch):
    """A door that forgets what it landed is a lie machine: with the
    iso view already at Visible Edges and 1:2, the SAME gesture must
    rest on those answers (measured off the field specs, page-order).
    "Visible Edges" is not the rest member, so it is stored - and
    must come back on the second ask."""
    cv = _box_sheet(win, qapp)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": "Visible Edges", "scale": "1:2"})
    cv.view_scale_requested.emit("iso")
    qapp.processEvents()
    calls = []
    monkeypatch.setattr(cmddialog, "ask",
                        lambda p, t, fl, **k: (calls.append(
                            {f["key"]: f.get("default") for f in fl}),
                            None)[1])
    cv.view_scale_requested.emit("iso")
    qapp.processEvents()
    rests, = calls                    # exactly one ask; rests is the
    #   {key: default} dict (NOT "(rests,), =" - that nested pattern
    #   re-unpacks the DICT itself: the 2 keys raise "got 2". The
    #   m219 coin "(title, specs), =" is right only because there the
    #   elements are 2-tuples.)
    assert rests["style"] == "Visible Edges"
    assert rests["scale"] == "1:2"


def test_the_style_rides_the_file_and_the_undo(win, qapp, monkeypatch):
    cv = _box_sheet(win, qapp)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "style": "Visible Edges", "scale": "Fit (auto)"})
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    back = Document.from_dict(win.doc.to_dict())      # the file's word
    assert back.drawings[-1]["vstyle"]["top"] == "Visible Edges"
    win.undo()
    qapp.processEvents()
    assert not (cv.sheet().get("vstyle") or {})       # undo takes it
