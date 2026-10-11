"""M161 — THE TIMELINE GETS ITS TRANSPORT (research/fd4_timeline.md).

Five permanent controls at the LEFT in the recorded order (LAW-2),
the gear at the RIGHT (LAW-3), the marker as a DRAGGABLE integer slot
that is pure evaluation cutoff (LAW-7/8), edit-rolls-the-marker
(LAW-10), rolled-back DIM-WITH-ITS-COLOR never the suppressed gray
(LAW-13), a chip click washing the model (LAW-15), Play as the ONE
sanctioned animation (LAW-34), and the wheel scrolling the strip
(LAW-4 — which the old parent check never let it do). The digest's
own gates: slot math, rollback byte-equality of model state, the dim
differential.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QImage                            # noqa: E402
from PySide6.QtTest import QTest                            # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox     # noqa: E402

from tracer.core.document import PrimitiveFeature           # noqa: E402
from tracer.ui import theme                                 # noqa: E402
from tracer.ui.renderer import SceneRenderer                # noqa: E402


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


def _boxes(win, n=4):
    win.new_document()
    for k in range(n):
        win.doc.add(PrimitiveFeature(
            name=f"B{k}", kind="box",
            dims={"dx": 6, "dy": 6, "dz": 6}))
        win.doc.features[-1].dims["dz"] = 6 + 4 * k
    win.recompute()
    return win


def _bar_pix(bar):
    img = bar.grab().toImage().convertToFormat(
        QImage.Format.Format_RGBA8888)
    buf = bytes(img.bits())
    a = np.frombuffer(buf, np.uint8).reshape(
        img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), :3]
    return a


# ---- LAW-2: the five controls, the recorded order, left docked --------------
def test_the_five_transport_buttons_stand_at_the_left(win, qapp):
    _boxes(win)
    bar = win.timeline.bar
    bar.repaint()
    qapp.processEvents()
    assert [what for what, _ in bar._tb] == \
        ["begin", "prev", "play", "next", "end"]        # LAW-2 ORDER
    xs = [r.x() for _, r in bar._tb]
    assert xs == sorted(xs) and xs[0] < 12              # left docked
    # LAW-14 tooltips ride the transport with the probe's names
    assert bar.TRANSPORT_TIPS["begin"] == "Move to Beginning"
    assert bar.TRANSPORT_TIPS["end"] == "End of Timeline"


def test_the_gear_docks_at_the_right(win, qapp):
    _boxes(win)
    bar = win.timeline.bar
    bar.resize(700, 38)
    bar.repaint()
    qapp.processEvents()
    assert bar._gear.x() > 700 - 40, "the Options button left the edge"


# ---- LAW-7: the marker is a slot; transport buttons just SET it -------------
def test_transport_sets_the_slot(win, qapp):
    _boxes(win, n=4)
    bar = win.timeline.bar
    hits = {what: r.center() for what, r in bar._tb}
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier,
                     hits["begin"].toPoint())
    qapp.processEvents()
    assert win.doc.rollback_to == 0, "begin failed to reach slot 0"
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier,
                     hits["next"].toPoint())
    qapp.processEvents()
    assert win.doc.rollback_to == 1
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier,
                     hits["prev"].toPoint())
    qapp.processEvents()
    assert win.doc.rollback_to == 0
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier,
                     hits["end"].toPoint())
    qapp.processEvents()
    assert win.doc.rollback_to is None, "end must CLEAR the cutoff"


def test_the_stream_survives_the_ride_byte_equal(win, qapp):
    """LAW-8: rollback is an EVALUATION CUTOFF — never a mutation.
    The model at slot 2 is byte-equal every time the marker lands
    there, and the feature stream never felt the ride."""
    _boxes(win, n=4)
    win._apply_rollback(2)
    qapp.processEvents()
    v2a = win.doc.result.volume
    stream_a = [f.name for f in win.doc.features]
    win._apply_rollback(None)
    win._apply_rollback(0)
    win._apply_rollback(4)
    win._apply_rollback(2)
    qapp.processEvents()
    assert win.doc.result.volume == v2a, "the cutoff is not pure"
    assert [f.name for f in win.doc.features] == stream_a


# ---- LAW-7: the marker DRAGS -------------------------------------------------
def test_the_marker_drags_between_icons(win, qapp):
    _boxes(win, n=4)
    bar = win.timeline.bar
    win._apply_rollback(4 - 4)                   # slot 0, marker live
    qapp.processEvents()
    assert bar._marker is not None, "no marker to grab at slot 0"
    p0 = bar._marker.center()
    chip_x, chip_w, _ = bar._chips[1]
    QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, p0.toPoint())
    # drag past the SECOND chip: release over its right boundary
    QTest.mouseMove(bar, QPoint(int(chip_x + chip_w + 6), int(p0.y())))
    qapp.processEvents()
    assert win.doc.rollback_to == 2, \
        "the drag did not land the marker on slot 2 (LIVE rewind)"
    QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier,
                       QPoint(int(chip_x + chip_w + 6), int(p0.y())))
    qapp.processEvents()
    assert win.doc.rollback_to == 2, "release must NOT end the rollback "
    "after a drag (M88's click-to-end belongs to a CLICK alone)"


def test_a_click_on_the_marker_still_ends_it(win, qapp):
    """The M88 law survives the drag: press-and-release WITHOUT motion
    ends the rollback."""
    _boxes(win, n=3)
    win._apply_rollback(1)
    qapp.processEvents()
    bar = win.timeline.bar
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier,
                     bar._marker.center().toPoint())
    qapp.processEvents()
    assert win.doc.rollback_to is None


# ---- LAW-10: editing rolls the marker to the feature -------------------------
def test_editing_a_hidden_feature_rolls_the_marker(win, qapp):
    _boxes(win, n=4)
    win._apply_rollback(1)                       # features 1..3 hidden
    qapp.processEvents()
    hidden = win.doc.features[2]
    win._feature_activated(hidden)               # the single edit door
    qapp.processEvents()
    assert win.doc.rollback_to == 3, \
        "edit entered with the target STILL behind the marker"


# ---- LAW-13: rolled-back dims WITH COLOR, never the suppressed gray ---------
def test_rolled_back_and_suppressed_never_wear_the_same_face(win, qapp):
    _boxes(win, n=3)
    bar = win.timeline.bar
    f2 = win.doc.features[2]
    win.doc.features[1].suppressed = True
    win.recompute()
    win._apply_rollback(2)                       # only f2 rolled back
    qapp.processEvents()
    bar.repaint()
    qapp.processEvents()
    pix = _bar_pix(bar)
    dpr = pix.shape[1] / bar.width()

    def ink(x):
        cx0 = int(x * dpr) + 6
        cx1 = int((x + 30) * dpr) - 6
        col = pix[int(8 * dpr):int(28 * dpr), cx0:cx1, :]
        return col.reshape(-1, 3).max(axis=0)     # glyph ink core

    xs = {id(f): x for x, _, f in bar._chips}
    sup = ink(xs[id(win.doc.features[1])])
    rolled = ink(xs[id(f2)])
    faint = np.array([int(theme.DARK["fg_faint"][i:i + 2], 16)
                      for i in (1, 3, 5)])
    assert np.abs(sup - faint).max() <= 24, "suppressed lost its gray"
    assert np.abs(rolled - sup).max() > 24, \
        "LAW-13 violated: rollback renders IDENTICAL to suppressed"


# ---- LAW-15: a chip click washes the model; empty strip clears --------------
def test_chip_click_highlights_the_result(win, qapp):
    from tracer.ui.mainwindow import demo_document
    win.new_document(demo_document())
    qapp.processEvents()
    bar = win.timeline.bar
    bar.repaint()
    qapp.processEvents()
    x, w, f = bar._chips[1]
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier,
                     QPointF(x + w / 2, bar.height() / 2).toPoint())
    qapp.processEvents()
    assert win.viewport._body_hi, \
        "LAW-15: the click painted nothing on the model"
    # an empty-strip click clears the highlight
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier,
                     QPointF(bar.width() - 40, bar.height() / 2).toPoint())
    qapp.processEvents()
    assert not win.viewport._body_hi, "the wash outlived its click"


# ---- LAW-34: Play is the ONLY sanctioned animation ---------------------------
def test_play_walks_the_filmstrip(win, qapp):
    _boxes(win, n=3)
    bar = win.timeline.bar
    win._apply_rollback(0)
    qapp.processEvents()
    hits = {what: r.center() for what, r in bar._tb}
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier,
                     hits["play"].toPoint())
    qapp.processEvents()
    assert bar._playing, "play never started"
    # run the stepped timer to the end (260 ms steps x 3 + slack)
    import time
    deadline = time.monotonic() + 4.0
    while bar._playing and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    assert win.doc.rollback_to is None, "Play never reached the end"
    assert not bar._playing, "Play outlived the strip"


def test_play_at_the_end_replays(win, qapp):
    """OURS-SAID (LAW-25 filmstrip): Play at the end rewinds first —
    the probe found no vendor law for the at-end case."""
    _boxes(win, n=3)
    bar = win.timeline.bar
    assert win.doc.rollback_to is None
    bar.start_play()
    qapp.processEvents()
    assert win.doc.rollback_to == 0, "Play at the end never rewound"
    bar.stop_play()


# ---- LAW-4: the wheel scrolls the strip (which the old check blocked) -------
def test_the_wheel_scrolls_the_strip(win, qapp):
    _boxes(win, n=30)                    # long enough to outgrow
    sa = win.timeline                      # the viewport
    # resize() is a whisper to a layouted widget — speak its language:
    sa.setMaximumWidth(320)
    qapp.processEvents()
    bar = win.timeline.bar
    bar.repaint()                       # the min-width law rides paint
    qapp.processEvents()
    h = sa.horizontalScrollBar()
    assert h.maximum() > 0, "a 30-chip strip never outgrew its viewport"
    h.setValue(h.maximum())             # start at the far end: wheel UP
    qapp.processEvents()                  # must walk the strip back
    before = h.value()
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtCore import QEvent
    pos = bar.mapToGlobal(QPointF(160, 20))
    ev = QWheelEvent(QPointF(160, 20), pos, QPoint(0, 0), QPoint(0, 120),
                     Qt.MouseButtons.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(bar, ev)
    qapp.processEvents()
    assert h.value() < before, "LAW-4: the wheel did not scroll the strip"
    sa.setMaximumWidth(1 << 20)          # the squeeze was for this test
    #   only — the strip returns to the window's full opinion


# ---- LAW-3: the gear menu contents (through the wiring, not the modal) ------
def test_gear_menu_hides_inactive_and_delete_is_guarded(win, qapp,
                                                        monkeypatch):
    _boxes(win, n=4)
    win.doc.features[1].suppressed = True
    win.recompute()
    qapp.processEvents()
    bar = win.timeline.bar
    before = bar.grab().toImage()
    bar.hide_inactive = True
    bar.repaint()
    qapp.processEvents()
    assert bar.grab().toImage() != before, "hide-inactive repainted nothing"
    # slots stay honest: 4 features still count even with a hidden chip
    assert len(win.doc.features) == 4
    chips = {id(f) for _, _, f in bar._chips}
    assert id(win.doc.features[1]) not in chips, "the inactive chip hid not"
    # LAW-12: delete-after-marker removes downstream, marker None after
    win.doc.rollback_to = 2
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k:
                                     QMessageBox.StandardButton.Yes))
    win._delete_after_marker()
    qapp.processEvents()
    assert [f.name for f in win.doc.features] == ["B0", "B1"]
    assert win.doc.rollback_to is None
    # and the refusal path deletes NOTHING
    win._apply_rollback(1)
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k:
                                     QMessageBox.StandardButton.No))
    win._delete_after_marker()
    assert len(win.doc.features) == 2 and win.doc.rollback_to == 1, \
        "the refusal deleted anyway — the guard is the LAW-12 contract"
