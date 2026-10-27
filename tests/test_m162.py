"""M162 — THE BROWSER OPENS ITS EYES (research/fd3_browser.md).

The eye is ALWAYS rendered (LAW-1.1 — their support KB exists because
users begged for hover-toggle and were refused; we clone the refusal),
the Bodies folder OVERRIDES the chain while children keep their latent
say (LAW-1.3), `V` toggles the selection (LAW-2.2), double-click ON THE
NAME renames in place (LAW-2.3), the active row always wears its dot
(LAW-1.6 — the DOCUMENTED deviation from their #1 complaint), canvas-
select underlines the ancestry (LAW-5.2), Find in Browser flashes the
row (LAW-5.1), eyes ride rollbacks untouched (LAW-5.3) and the isolate
round trip returns the exact prior darks (M134's snapshot, pinned here
as LAW-2.10's gate).
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QImage                             # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit        # noqa: E402

from tracer.core.document import PrimitiveFeature            # noqa: E402
from tracer.ui import theme                                  # noqa: E402
from tracer.ui.renderer import SceneRenderer                 # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    r.close()
    w.close()


def _box(name, dz):
    return PrimitiveFeature(name=name, kind="box",
                            dims={"dx": 10.0, "dy": 10.0, "dz": dz})


def _two_bodies(win, qapp):
    """Two REAL bodies, two eyes — the AND-chain needs a child to
    hide while the layer stays on (the M104 fixture pattern)."""
    win.new_document()
    win.doc.add(_box("Cube", 10.0))
    win.action_new_body()
    win.doc.add(_box("Stud", 6.0))
    win.recompute()
    qapp.processEvents()
    return win


def _vis(win):
    return {b["name"]: bool(b.get("visible", True))
            for b in win.doc.body_list()}


def _row_of(tree, role):
    def walk(it):
        for i in range(it.childCount()):
            ch = it.child(i)
            if ch.data(0, Qt.UserRole) == role:
                return ch
            got = walk(ch)
            if got is not None:
                return got
        return None
    return walk(tree.topLevelItem(0))


def _eye_point(tree, role):
    it = _row_of(tree, role)
    r = tree.visualRect(tree.indexFromItem(it))
    return QPoint(r.left() + 10, r.center().y())


# ---- LAW-1.1: who wears an eye ----------------------------------------------
def test_eyes_wear_every_real_visibility_row(win, qapp):
    _two_bodies(win, qapp)
    tree = win.rail.tree
    assert tree.has_eye(("body", "Body 1"))          # kernel exists
    assert tree.has_eye(("folder", "bodies"))        # the AND-chain
    assert not tree.has_eye(("feature", 0))          # no kernel, no eye
    assert not tree.has_eye(("sketch", 0))           #   — banked, not faked
    assert _row_of(tree, ("body", "Body 1")).text(0) == "Body 1"


def test_eye_click_toggles_the_document_truth(win, qapp):
    _two_bodies(win, qapp)
    tree = win.rail.tree
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     _eye_point(tree, ("body", "Body 1")))
    qapp.processEvents()
    assert _vis(win)["Body 1"] is False, "the eye did not write the kernel"
    assert tree.eye_hidden(("body", "Body 1"))
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     _eye_point(tree, ("body", "Body 1")))
    qapp.processEvents()
    assert _vis(win)["Body 1"] is True, "the eye failed to reopen"


def test_eye_click_never_selects(win, qapp):
    """Fusion's bulb law: the click TOGGLES — the current row stays."""
    _two_bodies(win, qapp)
    tree = win.rail.tree
    tree.setCurrentItem(None)
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     _eye_point(tree, ("body", "Body 2")))
    qapp.processEvents()
    assert tree.currentItem() is None, "an eye click hijacked selection"


# ---- LAW-1.3: the folder overrides, children stay latent --------------------
def test_the_folder_is_the_layer_children_stay_latent(win, qapp):
    _two_bodies(win, qapp)
    tree = win.rail.tree
    before = _vis(win)
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     _eye_point(tree, ("folder", "bodies")))
    qapp.processEvents()
    assert win.viewport._r.show_solid is False, "the folder missed the layer"
    assert _vis(win) == before, "the folder overwrote children — LAW-1.3 "  \
        "says it OVERRIDES the chain, their own eyes never moved"
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     _eye_point(tree, ("folder", "bodies")))
    qapp.processEvents()
    assert win.viewport._r.show_solid is True, "the layer never came back"
    assert _vis(win) == before, "latency broken both ways"


def test_new_document_opens_with_clean_eyes(win, qapp):
    _two_bodies(win, qapp)
    tree = win.rail.tree
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     _eye_point(tree, ("folder", "bodies")))
    qapp.processEvents()
    assert tree.folder_vis is False
    win.new_document()               # VIEW state: the folder eye reopens
    assert tree.folder_vis is True
    assert win.viewport._r.show_solid is True, "the layer rode the old "  \
        "document's folder into the new one"


# ---- LAW-2.2: V ---------------------------------------------------------------
def test_V_toggles_the_selected_row(win, qapp):
    _two_bodies(win, qapp)
    tree = win.rail.tree
    tree.setCurrentItem(_row_of(tree, ("body", "Body 1")))
    QTest.keyClick(tree, Qt.Key_V)
    qapp.processEvents()
    assert _vis(win)["Body 1"] is False, "V ignored the selection"
    tree.setCurrentItem(_row_of(tree, ("folder", "bodies")))
    QTest.keyClick(tree, Qt.Key_V)
    qapp.processEvents()
    assert tree.folder_vis is False, "V ignored the folder"


# ---- LAW-2.3: double-click the NAME renames in place --------------------------
def _px_of(vp, world):
    """Model point → viewport pixel (the M20/M160 house helper)."""
    cam = vp.camera()
    m = cam.proj_matrix(vp.width() / vp.height()) @ cam.view_matrix()
    clip = m @ np.append(np.asarray(world, float), 1.0)
    ndc = clip[:3] / clip[3]
    return QPointF((ndc[0] * 0.5 + 0.5) * vp.width(),
                   (0.5 - ndc[1] * 0.5) * vp.height())


def test_dbl_click_on_the_name_renames_in_place(win, qapp):
    _two_bodies(win, qapp)
    tree = win.rail.tree
    it = _row_of(tree, ("feature", 0))
    r = tree.visualRect(tree.indexFromItem(it))
    QTest.mouseDClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                      QPoint(r.left() + 100, r.center().y()))
    qapp.processEvents()
    ed = tree.focusWidget()
    assert tree._renaming is it and isinstance(ed, QLineEdit),  \
        "no inline editor on the name"
    assert ed.text() == "Cube", "the field pre-filled the DECORATED text"
    ed.selectAll()
    QTest.keyClicks(ed, "Renamed")
    QTest.keyClick(ed, Qt.Key_Return)
    qapp.processEvents()
    assert win.doc.features[0].name == "Renamed", "commit missed the kernel"
    assert "Renamed" in _row_of(tree, ("feature", 0)).text(0)


def test_escape_leaves_the_name_alone(win, qapp):
    _two_bodies(win, qapp)
    tree = win.rail.tree
    it = _row_of(tree, ("feature", 0))
    r = tree.visualRect(tree.indexFromItem(it))
    QTest.mouseDClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                      QPoint(r.left() + 100, r.center().y()))
    qapp.processEvents()
    ed = tree.focusWidget()
    QTest.keyClicks(ed, "Discarded")
    QTest.keyClick(ed, Qt.Key_Escape)
    qapp.processEvents()
    assert win.doc.features[0].name == "Cube", "Escape committed anyway"
    assert tree._renaming is None


def test_the_icon_side_keeps_its_old_law(win, qapp, monkeypatch):
    """The name zone took LAW-2.3's rename; everything else keeps the
    activation door it always had (M104: dbl-click a body = activate)."""
    _two_bodies(win, qapp)
    tree = win.rail.tree
    seen = []
    monkeypatch.setattr(win, "action_activate_body",
                        lambda nm: seen.append(nm))
    it = _row_of(tree, ("body", "Body 1"))
    r = tree.visualRect(tree.indexFromItem(it))
    p = QPoint(r.left() + 40, r.center().y())
    # x=40: the name side of the row — under Qt's default expand law a
    # double-click here used to COLLAPSE the body instead of acting on
    # it (M104's activate door was mouse-unreachable until M162's
    # expandsOnDoubleClick(False) repair). A prior press is given first:
    # a bare synthetic dbl-click finds QTreeView's pressedIndex unarmed
    # (its release clears it — Qt-internal choreography every real
    # user's first click resolves).
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, p)
    qapp.processEvents()
    QTest.mouseDClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, p)
    qapp.processEvents()
    assert seen == ["Body 1"], "the body row forgot its activation law"


def test_activation_rides_one_tick_not_the_dispatch_frame(win, qapp):
    """The coredump-125155 gate: reloading the tree INSIDE Qt's
    double-click dispatch frees the rows under Qt's own index —
    use-after-free. The door must DEFER: while no event loop turns,
    the model stays untouched; one tick later, the activation lands."""
    _two_bodies(win, qapp)
    tree = win.rail.tree
    assert win.doc.active_body == "Body 2"          # fixture: Stud wins
    body1 = _row_of(tree, ("body", "Body 1"))
    tree.itemDoubleClicked.emit(body1, 0)           # synchronous emit…
    # …no event loop has run, so a deferred door has NOT fired yet.
    # (Pre-M162, this line's successor mutated the model right here —
    # with a live Qt double-click on the stack that was the SIGSEGV.)
    assert win.doc.active_body == "Body 2",  \
        "the handler rebuilt the tree INSIDE the dispatch frame — "  \
        "that is the SIGSEGV shape (coredump 125155)"
    qapp.processEvents()                            # the tick arrives
    assert win.doc.active_body == "Body 1", "the deferred door never fired"


# ---- LAW-5.1: Find in Browser flashes ----------------------------------------
def test_find_in_browser_reveals_and_flashes(win, qapp):
    _two_bodies(win, qapp)
    tree = win.rail.tree
    tree.collapseAll()
    assert win._find_in_browser(win.doc.features[1]) is True
    qapp.processEvents()
    assert tree.currentItem() is _row_of(tree, ("feature", 1))
    assert tree._flash is not None, "the dashed find-flash never armed"
    tree._end_flash()
    assert tree._flash is None, "the flash outstayed its welcome"


# ---- LAW-5.2: canvas-select underlines the ancestry --------------------------
def test_canvas_select_lights_the_ancestry(win, qapp):
    _two_bodies(win, qapp)
    vp = win.viewport
    p = _px_of(vp, (5, 5, 10)).toPoint()      # the Cube's top face
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, p)
    qapp.processEvents()
    assert vp._sel, "the probe click missed the model entirely"
    under = win.rail.tree._under
    assert ("folder", "bodies") in under, \
        "the pick lit no lineage"
    body = vp.selected_body()
    assert body is not None and ("body", body) in under
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, QPoint(6, 6))
    qapp.processEvents()
    assert win.rail.tree._under == [], "the lineage outlived the pick"


# ---- LAW-5.3 + LAW-2.10: eyes vs history, isolate snapshot -------------------
def test_eyes_ride_the_rollback_untouched(win, qapp):
    _two_bodies(win, qapp)
    win.doc.set_body_visible("Body 2", False)
    win._refresh_visibility()
    qapp.processEvents()
    win._apply_rollback(1)
    qapp.processEvents()
    assert _vis(win)["Body 2"] is False, "history rolled an eye shut — "  \
        "LAW-5.3 says visibility is INDEPENDENT of the marker"
    win._apply_rollback(None)
    qapp.processEvents()
    assert _vis(win)["Body 2"] is False, "ending rollback healed the eye"


def test_the_isolate_round_trip_returns_exact_priors(win, qapp):
    """LAW-2.10's snapshot, M134's machinery, pinned as FD3 law:
    isolate → the scope stands; unisolate → EVERY prior dark returns,
    including the one a hand closed before isolation."""
    _two_bodies(win, qapp)
    win.doc.set_body_visible("Body 2", False)
    win._refresh_visibility()
    qapp.processEvents()
    win._isolate_body("Body 2")               # the hidden one joins
    qapp.processEvents()
    win._unisolate_all()
    qapp.processEvents()
    assert _vis(win) == {"Body 1": True, "Body 2": False},  \
        "the snapshot lost a prior dark"


# ---- LAW-1.6: the active dot (documented deviation) — pixel gate -------------
def test_the_active_row_always_wears_its_dot(win, qapp):
    _two_bodies(win, qapp)
    tree = win.rail.tree
    tree.setCurrentItem(None)                 # no selection tint to confound
    for _ in range(10):
        qapp.processEvents()
    img = tree.grab().toImage().convertToFormat(
        QImage.Format.Format_RGBA8888)
    a = np.frombuffer(bytes(img.bits()), np.uint8).reshape(
        img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), :3]
    dpr = a.shape[1] / tree.width()
    acc = np.array(theme.rgb01(theme.DARK["accent"])) * 255

    def accent_px(role):
        it = _row_of(tree, role)
        r = tree.visualRect(tree.indexFromItem(it))
        band = a[int(r.top() * dpr):int((r.bottom() + 1) * dpr),
                 :, :].astype(int)
        near = np.abs(band - acc).sum(axis=2) <= 36
        return int(near[:, int((r.right() - 18) * dpr):].sum())

    active = accent_px(("body", win.doc.active_body))
    other = [n for n in ("Body 1", "Body 2") if n != win.doc.active_body]
    off = accent_px(("body", other[0]))
    assert active >= 10, f"active row inked only {active} dot px"
    assert off <= 2, f"inactive row inked {off} dot px — the dot must "  \
        "single out the active one"
