"""M160 — THE CANVAS SPEAKS.

The look-&-feel tranche 2, built on FD receipts: the hover/selection
DUO (FD2-L2 — no hex is published anywhere, so ours is OURS-Said on the
users' recorded language: hover "turns white", selection is blue), the
PICKBOX (FD8-45 — one knob, initial 3 DIP, 0 kills previewing only),
browser-row hover washing the canvas with the SAME glow (FD2-L4), and
the bottom-right detail readout as a preference that ships ON
(FD8-34). Every law here carries its probe's name; the pixel gates
ride the ON/OFF differential doctrine.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QPointF, Qt, QSettings    # noqa: E402
from PySide6.QtGui import QImage                           # noqa: E402
from PySide6.QtTest import QTest                           # noqa: E402
from PySide6.QtWidgets import QApplication                 # noqa: E402

from tracer.ui import theme                                # noqa: E402
from tracer.ui.renderer import SceneRenderer               # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def clean_settings():
    s = QSettings()
    s.clear()
    s.sync()
    yield
    s = QSettings()
    s.clear()
    s.sync()


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


def _plate_win(win):
    win.new_document()
    win.doc.add_plate("plate", 20, 20, 5)   # top face z=5, centre (10,10)
    win.recompute()
    return win


def _px_of(vp, world):
    cam = vp.camera()
    vp_m = cam.proj_matrix(vp.width() / vp.height()) @ cam.view_matrix()
    clip = vp_m @ np.append(np.asarray(world, float), 1.0)
    ndc = clip[:3] / clip[3]
    return QPointF((ndc[0] * 0.5 + 0.5) * vp.width(),
                   (0.5 - ndc[1] * 0.5) * vp.height())


def _move(vp, pos):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    p = QPointF(pos)
    g = QPointF(vp.mapToGlobal(p.toPoint()))
    ev = QMouseEvent(QEvent.Type.MouseMove, p, g, Qt.MouseButton.NoButton,
                     Qt.MouseButtons.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, ev)


# ---- the duo (FD2-L2) -------------------------------------------------------
def test_hover_mix_rides_bright():
    """FD2-L1: the hover lights the face INTENSELY (users: "a constant
    bright light"). The shader's hover mix was lifted 0.25 -> 0.40."""
    from pathlib import Path
    src = (Path(theme.__file__).parent / "renderer.py"
           ).read_text(encoding="utf-8")
    assert "u_hi_hover, 0.40" in src


# ---- the pickbox (FD8-45) ----------------------------------------------------
def test_default_pickbox_is_three_DIP(win):
    """FD8-45 verbatim: selection target height in DEVICE INDEPENDENT
    PIXELS, initial 3."""
    assert win.viewport.pick_radius == pytest.approx(3.0)


def test_pickbox_clamps_and_persists(win):
    vp = win.viewport
    assert vp.set_pick_radius(99) == 20.0          # the documented 0-20
    assert vp.set_pick_radius(-5) == 0.0           # envelope, clamped
    assert vp.set_pick_radius(7.5) == 7.5
    assert float(QSettings().value("pick/radius")) == 7.5


def test_open_pickbox_previews_the_face(win, qapp):
    _plate_win(win)
    vp = win.viewport
    _move(vp, _px_of(vp, (10, 10, 5)))
    qapp.processEvents()
    assert vp._hover, "3 DIP default previews nothing on the plate top"
    col = vp._r._solid_data[:, 12]
    assert col.max() == pytest.approx(0.5)         # HOVER value


def test_zero_pickbox_kills_preview_not_clicks(win, qapp):
    """FD8-45's own law: "PICKBOX = 0 -> selection PREVIEWING is not
    available" — the wash dies, the coords keep streaming, and a real
    click still selects (exactness survives its own zero)."""
    _plate_win(win)
    vp = win.viewport
    vp.set_pick_radius(3)                     # preview once, live chip
    _move(vp, _px_of(vp, (10, 10, 5)))
    qapp.processEvents()
    assert vp.readout_text() is not None, "chip never came up"
    vp.set_pick_radius(0)
    assert vp._hover is None and vp.readout_text() is None, \
        "the zero pickbox left a stale chip or wash behind"
    seen = []
    vp.coords.connect(seen.append)
    try:
        _move(vp, _px_of(vp, (10, 10, 5)))
        qapp.processEvents()
        assert vp._hover is None, "preview survived a zero pickbox"
        assert vp._r._solid_data[:, 12].max() == 0.0
        assert seen, "coords died with the preview — FD8-45 kills one, "
        "not the other"
    finally:
        vp.coords.disconnect(seen.append)
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier,
                     _px_of(vp, (10, 10, 5)).toPoint())
    qapp.processEvents()
    assert vp._sel, "a zero pickbox broke the exact click"


def test_center_hit_is_exact_even_with_a_wide_pickbox(win, qapp):
    """The tolerance theorem (found by M20's pin riding green): when the
    cursor's OWN ray hits, that 3D point is the answer — cross rays are
    only for misses. coords, sketch anchors and re-pivot all live on
    this exactness."""
    _plate_win(win)
    vp = win.viewport
    vp.set_pick_radius(9.0)
    seen = []
    vp.coords.connect(seen.append)
    try:
        _move(vp, _px_of(vp, (10, 10, 5)))
        qapp.processEvents()
        assert np.allclose(seen[-1], (10, 10, 5), atol=0.6)
    finally:
        vp.coords.disconnect(seen.append)


def test_pickbox_reaches_across_an_edge(win):
    """THE reach itself: a pixel 5 DIP OUTSIDE the plate's silhouette
    misses with r=0 and HITS with r=6 — the box, not the bullseye."""
    _plate_win(win)
    vp = win.viewport
    V = np.asarray(vp._tm.vertices, float)
    cam = vp.camera()
    m = cam.proj_matrix(vp.width() / vp.height()) @ cam.view_matrix()
    clip = np.column_stack([V, np.ones(len(V))]) @ m.T
    ndc = clip[:, :3] / clip[:, 3:4]
    sx = (ndc[:, 0] * 0.5 + 0.5) * vp.width()
    sy = (0.5 - ndc[:, 1] * 0.5) * vp.height()
    top = int(np.argmin(sy))
    px, py = float(sx[top]), float(sy[top]) - 5.0   # 5 DIP over the edge
    vp.set_pick_radius(0)
    assert vp._shoot(vp._tm, px, py) is None, \
        "the probe pixel sits ON the mesh — pick a real miss"
    vp.set_pick_radius(6)
    assert vp._shoot(vp._tm, px, py) is not None, \
        "a 6 DIP box failed to reach 5 DIP past the silhouette"


# ---- browser-row hover (FD2-L4) ---------------------------------------------
def test_body_row_hover_washes_with_the_hover_value(win, qapp):
    """FD2-L4: hovering the row is "the same thing as hovering over the
    body" — the SAME glow (hover value 0.5), never the selection value,
    and the picked-face set never hears about it."""
    _plate_win(win)
    vp = win.viewport
    body = win.doc.active_body
    vp.hover_body(body)
    col = vp._r._solid_data[:, 12]
    assert int(np.isclose(col, 0.5).sum()) >= 3, "row hover washed nothing"
    assert int(np.isclose(col, 1.0).sum()) == 0, "row hover used the "
    "SELECTION value — FD2-L4 says the same glow, not the same meaning"
    assert not vp._sel, "a hover touched the picked set"
    vp.hover_body(None)
    assert col.max() == 0.0, "the wash outlived the row"


def test_row_resolver_is_one_truth(win, qapp):
    """M131's click wash and M160's hover wash share ONE row->body
    resolver — folders resolve to nothing."""
    _plate_win(win)
    tree = win.rail.tree
    tree.expandAll()
    resolved = {}
    stack = [tree.topLevelItem(i)
             for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop()
        role = it.data(0, Qt.UserRole)
        if role:
            resolved[role[0]] = it
        stack += [it.child(i) for i in range(it.childCount())]
    feats = list(win.doc.features)
    if "feature" in resolved:
        kind, arg = resolved["feature"].data(0, Qt.UserRole)
        want = getattr(feats[arg], "body", None) if 0 <= arg < len(feats) \
            else None
        assert win._body_name_for_row(resolved["feature"]) == want
    if "folder" in resolved:
        assert win._body_name_for_row(resolved["folder"]) in (None,)


# ---- the detail readout (FD8-34) ---------------------------------------------
def test_readout_line_measures_the_truth(win, qapp):
    """The live spec line COMPUTES: a 20x20 top face reads 400.00 mm²
    under the cursor — mesh truth, never a cached label."""
    _plate_win(win)
    vp = win.viewport
    _move(vp, _px_of(vp, (10, 10, 5)))
    qapp.processEvents()
    line = vp.readout_text()
    assert line is not None and "400.00 mm\u00b2" in line, line
    body = win.doc.active_body
    assert body in line or "|" not in line   # name when the stitch knows


def test_readout_floor_and_fade(win, qapp):
    """Selection is the FLOOR: hover wins live, but lifting the hover
    off the mesh must not erase the selected face's line — until the
    selection itself clears, when the chip goes with it."""
    _plate_win(win)
    vp = win.viewport
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier,
                     _px_of(vp, (10, 10, 5)).toPoint())
    qapp.processEvents()
    assert vp.readout_text() is not None, "no line under a live selection"
    _move(vp, QPointF(4.0, 4.0))             # hover the void (top-left)
    qapp.processEvents()
    assert vp.readout_text() is not None, "the floor evaporated"
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier,
                     QPoint(4, 4))           # a real click in the void
    qapp.processEvents()
    assert not vp._sel and vp.readout_text() is None, \
        "the chip outlived its selection"


def test_readout_toggle_is_a_remembered_preference(win, qapp):
    """FD8-34: it's "General - show detail measure" — a preference, and
    its ABSENCE is treated as a bug; so it ships ON and remembers OFF."""
    _plate_win(win)
    vp = win.viewport
    assert vp.show_readout is True, "ships ON (their QA treats absence "
    "as a bug)"
    _move(vp, _px_of(vp, (10, 10, 5)))
    qapp.processEvents()
    assert vp.readout_text() is not None
    vp.set_readout_visible(False)
    assert vp.readout_text() is None, "OFF must blind the line"
    assert not bool(QSettings().value("measure/detail_readout",
                                      True, type=bool))
    vp.set_readout_visible(True)
    assert vp.readout_text() is not None, "back ON with the same line"


def test_readout_inks_the_corner_on_off(win, qapp):
    """PIXEL-GATE LAW: the chip's ON ink differs from OFF by real
    pixels bottom-right, and OFF returns EXACTLY the earlier image."""
    _plate_win(win)
    vp = win.viewport
    for _ in range(30):
        qapp.processEvents()

    def corner():
        img = vp.grab().toImage().convertToFormat(
            QImage.Format.Format_RGBA8888)
        buf = bytes(img.bits())
        a = np.frombuffer(buf, np.uint8).reshape(
            img.height(), img.bytesPerLine() // 4, 4)[
            :, :img.width(), :3]
        return a

    off = corner()
    _move(vp, _px_of(vp, (10, 10, 5)))
    for _ in range(20):
        qapp.processEvents()
    assert vp.readout_text() is not None
    on = corner()
    h, w = off.shape[:2]
    box = (slice(h - 60, h), slice(max(0, w - 320), w))   # chip corner
    changed = int((np.abs(on[box].astype(int)
                          - off[box].astype(int)).sum(axis=2) > 24).sum())
    assert changed > 400, f"chip inked only {changed} px in its corner"
    vp.set_readout_visible(False)
    _move(vp, QPointF(4.0, 4.0))     # THE WHOLE GUEST LEAVES: chip gone
    #   AND the hover wash gone — only then is a byte-return honest
    for _ in range(20):
        qapp.processEvents()
    off2 = corner()
    assert np.array_equal(off, off2), "OFF is not the earlier truth"
