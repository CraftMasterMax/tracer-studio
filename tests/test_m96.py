"""M96 — sheet management: browser tree, multiple sheets, draggable views.

The drawings phase matures one notch: sheets join the browser tree
(Sheets (n) next to Bodies and Sketches), double-click opens one, and
views — no longer pinned to their layout slots — can be dragged to
fresh positions on the sheet. The drag stores a per-view MOVE in
sheet millimetres on the drawing entry itself: views still re-derive
live from the model, the layout assistant still places them, and the
draughtsman's nudge simply rides on top. Undo captures, the file
keeps it, and dragging the empty desk still pans the sheet.

Honest scope: one body per sheet (the model result), moves are
translation only (no rotate), the sheet's bubbles travel with their
view automatically.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt                        # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402

from tracer.core import drawing                              # noqa: E402
from tracer.core.document import Document, PrimitiveFeature  # noqa: E402


# ------------------------------------------------------------- core

def _views():
    box = PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 40.0, "dy": 20.0, "dz": 5.0})
    s = box.build()
    return {v: drawing.project_view(s, view=v)
            for v in drawing.STANDARD}


def test_place_honours_moves():
    views = _views()
    base = drawing.place(views)
    moved = drawing.place(views, moves={"top": (15.0, -5.0)})
    assert moved["top"]["off"][0] - base["top"]["off"][0] == \
        pytest.approx(15.0)
    assert moved["top"]["off"][1] - base["top"]["off"][1] == \
        pytest.approx(-5.0)
    assert moved["front"]["off"] == base["front"]["off"]   # untouched


def test_moves_round_trip_through_the_file():
    d = Document(title="sheets")
    d.drawings = [{"name": "Drawing1", "page": "A3", "dims": [],
                   "move": {"top": [15.0, -5.0]}}]
    back = Document.from_dict(d.to_dict())
    assert back.drawings[0]["move"] == {"top": [15.0, -5.0]}


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
        r.close()
    except Exception:
        raise


def _box_doc(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Block", kind="box",
        dims={"dx": 40.0, "dy": 20.0, "dz": 10.0}))
    win.recompute()
    qapp.processEvents()


def _sheet_node(win):
    tree = win.rail.tree
    roots = [tree.topLevelItem(0).child(i)
             for i in range(tree.topLevelItem(0).childCount())]
    return next((it for it in roots
                 if it.data(0, Qt.UserRole) == ("folder", "sheets")), None)


def test_sheets_folder_appears_in_the_browser(win, qapp):
    _box_doc(win, qapp)
    win.action_new_drawing()
    qapp.processEvents()
    node = _sheet_node(win)
    assert node is not None and node.text(0) == "Sheets (1)"
    assert node.child(0).text(0) == "Drawing1"


def test_two_sheets_and_double_click_opens_the_right_one(win, qapp):
    _box_doc(win, qapp)
    win.action_new_drawing()          # Drawing1
    win.action_new_drawing()          # Drawing2
    qapp.processEvents()
    assert win.drawing.sheet()["name"] == "Drawing2"      # newest wins
    node = _sheet_node(win)
    assert node.text(0) == "Sheets (2)"
    # itemDoubleClicked is Qt's plumbing; the handler is ours
    win.rail.tree.itemDoubleClicked.emit(node.child(0), 0)
    qapp.processEvents()
    assert win.drawing.sheet()["name"] == "Drawing1"
    assert win.stack.currentWidget() is win._drawing_page


def test_drag_a_view_repositions_it(win, qapp):
    _box_doc(win, qapp)
    win.action_new_drawing()
    qapp.processEvents()
    cv = win.drawing
    cv.resize(800, 600)
    qapp.processEvents()
    sc, off = cv.frames()["top"]
    centre = cv.s2p(off[0] + 20.0 * sc, off[1] + 10.0 * sc).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                     centre)
    qapp.processEvents()
    QTest.mouseMove(cv, centre + QPoint(32, 0))
    qapp.processEvents()
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                       centre + QPoint(32, 0))
    qapp.processEvents()
    mv = win.doc.drawings[-1]["move"]["top"]
    assert mv[0] == pytest.approx(32.0 / cv._zoom, abs=0.6)
    assert abs(mv[1]) < 0.6
    sc2, off2 = cv.frames()["top"]        # the view really moved
    assert off2[0] - off[0] == pytest.approx(mv[0], abs=0.6)


def test_empty_desk_drag_still_pans(win, qapp):
    _box_doc(win, qapp)
    win.action_new_drawing()
    qapp.processEvents()
    cv = win.drawing
    cv.resize(800, 600)
    qapp.processEvents()
    from PySide6.QtCore import QPoint
    far = QPoint(60, 560)                  # off-sheet corner: desk
    before = (cv._center.x(), cv._center.y())
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, far)
    QTest.mouseMove(cv, far + QPoint(40, 0))
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                       far + QPoint(40, 0))
    qapp.processEvents()
    assert "move" not in win.doc.drawings[-1] or \
        win.doc.drawings[-1]["move"] == {}
    assert (cv._center.x(), cv._center.y()) != before


def test_view_move_undoes(win, qapp):
    _box_doc(win, qapp)
    win.action_new_drawing()
    qapp.processEvents()
    cv = win.drawing
    cv.resize(800, 600)
    qapp.processEvents()
    from PySide6.QtCore import QPoint
    sc, off = cv.frames()["top"]
    centre = cv.s2p(off[0] + 20.0 * sc, off[1] + 10.0 * sc).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                     centre)
    QTest.mouseMove(cv, centre + QPoint(20, 10))
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                       centre + QPoint(20, 10))
    qapp.processEvents()
    assert win.doc.drawings[-1]["move"].get("top")
    win.undo()
    qapp.processEvents()
    assert win.doc.drawings[-1].get("move", {}) == {}


def test_undo_rebinds_the_sheet_canvas(win, qapp):
    _box_doc(win, qapp)
    win.action_new_drawing()
    win.action_new_drawing()
    qapp.processEvents()
    assert win.drawing.doc is win.doc
    win.undo()                                  # take Drawing2 back off
    qapp.processEvents()
    assert win.drawing.doc is win.doc           # no stale-paper painting
    assert win.drawing.sheet()["name"] == "Drawing1"


def test_bubbles_travel_with_their_view(win, qapp):
    _box_doc(win, qapp)
    win.action_new_drawing()
    qapp.processEvents()
    cv = win.drawing
    cv.resize(800, 600)
    qapp.processEvents()
    from PySide6.QtCore import QPoint
    cv.set_dim_mode(True)
    sc, off = cv.frames()["top"]
    QTest.mouseClick(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                     cv.s2p(off[0], off[1]).toPoint())
    QTest.mouseClick(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                     cv.s2p(off[0] + 40 * sc, off[1]).toPoint())
    cv.set_dim_mode(False)
    qapp.processEvents()
    before = cv.sheet()["dims"][0]["text"]
    # drag the top view away
    sc, off = cv.frames()["top"]
    centre = cv.s2p(off[0] + 20.0 * sc, off[1] + 10.0 * sc).toPoint()
    QTest.mousePress(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                     centre)
    QTest.mouseMove(cv, centre + QPoint(50, 0))
    QTest.mouseRelease(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                       centre + QPoint(50, 0))
    qapp.processEvents()
    assert cv.sheet()["dims"][0]["text"] == before      # still measures
    a_page = cv.model_to_page("top", cv.sheet()["dims"][0]["a"])
    sc2, off2 = cv.frames()["top"]
    assert a_page[0] == pytest.approx(
        cv.sheet()["dims"][0]["a"][0] * sc2 + off2[0], abs=0.5)
