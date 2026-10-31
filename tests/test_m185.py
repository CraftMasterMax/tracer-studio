"""M185 rung 1 - THE PICKBOX (LAW-45 [documented]).

"Selection target height IN DEVICE INDEPENDENT PIXELS, initial 3;
PICKBOX = 0 -> selection PREVIEWING is not available" - and the whole
point of the AutoCAD variable is that ONE knob governs BOTH the click
target and the hover preview (hover radius == pick radius). Tracer
hardcodes _HIT_PX = 9 in every selection leg: a target is a taste, and
taste needs a knob. Rung 1 ships the MOUTH: SketchCanvas.pick_radius /
set_pick_radius, clamped, persisted (QSettings, the grid-snap precedent),
emitted as pick_radius_changed, and honored by every SELECTION seam.
Tools keep their own language: the magnet's tol and trim's stroke
radius are not selection targets and stay module constants.

The law's own zero: PICKBOX 0 silences the PREVIEWS - no live band take
(_band_prev), no geometry preselect (_hover_e) - while the marquee's
BOX math still commits on release (containment is not a target radius).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/home/panzenboeck/tracer-studio")

import pytest                                                        # noqa
import numpy                                                         # noqa
from PySide6.QtCore import QEvent, QPointF, QPoint, Qt, QSettings    # noqa
from PySide6.QtGui import QImage, QMouseEvent                        # noqa
from PySide6.QtTest import QTest                                     # noqa
from PySide6.QtWidgets import QApplication                           # noqa


@pytest.fixture
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def ed(qapp):
    from tracer.core.sketch.model import SketchModel
    from tracer.ui.sketcheditor import SketchCanvas
    QSettings().remove("sketch/pickbox")
    c = SketchCanvas()
    c.set_model(SketchModel())
    c.resize(600, 400)
    c._snap_grid = False
    yield c
    QSettings().remove("sketch/pickbox")          # POLLUTION LAW
    c.close()
    c.deleteLater()


def _scr(x, y):
    return QPoint(int(round(300 + 4.0 * x)), int(round(200 - 4.0 * y)))


def _two_lines(ed):
    m = ed.model
    l1 = m.add_line(m.point(-20, 2), m.point(20, 2))
    l2 = m.add_line(m.point(-20, -2), m.point(5, -2))
    ed._solve()
    return l1, l2


def _bare_move(ed, pt, qapp):
    p = QPointF(float(pt.x()), float(pt.y()))
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.NoButton, Qt.NoButton, Qt.NoModifier))
    for _ in range(3):
        qapp.processEvents()


def _band_live(ed, a, b, mid, qapp):
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, a)
    p = QPointF(float(b.x()), float(b.y()))
    QApplication.sendEvent(
        ed, QMouseEvent(QEvent.Type.MouseMove, p, p, p,
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    for _ in range(3):
        qapp.processEvents()
    w = mid(ed)
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, b)
    for _ in range(3):
        qapp.processEvents()
    return w


# ---- the knob exists, and nothing moved without being asked -----------------

def test_pickbox_default_is_todays_target(ed, qapp):
    assert ed.pick_radius == 9, \
        "the knob opens where Tracer already lived (zero regression)"


# ---- ONE knob: the hover radius IS the pick radius --------------------------

def test_the_knob_moves_hover_and_press_as_one(ed, qapp):
    l1, _ = _two_lines(ed)
    off = _scr(-12.5, 3.5)                     # 6 px off the line (row 192)
    _bare_move(ed, off, qapp)
    assert ed._hover_e is l1, "at 9 the target catches 6px away"
    ed.set_pick_radius(4)                      # the SAME number steers both
    assert ed._hover_e is None, \
        "shrinking the target must evict the stale preselect NOW"
    _bare_move(ed, off, qapp)
    assert ed._hover_e is None, "at 4 the same cursor is OUT of the target"
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, off)
    assert ed._band is not None, "and the press agrees: marquee, not grab"
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, off)
    ed.set_pick_radius(9)
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, off)
    assert ed._band is None, \
        "ONE mouth, ONE number: at 9 the same press GRABS the line"
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, off)


# ---- the law's OWN zero: previewing is not available ------------------------

def test_zero_silences_the_previews_but_not_the_commit(ed, qapp):
    l1, _ = _two_lines(ed)
    ed.set_pick_radius(0)

    def witness(c):
        return dict(prev=list(c._band_prev), band=c._band is not None,
                    hover=c._hover_e)
    _bare_move(ed, _scr(-12.5, 2), qapp)
    assert ed._hover_e is None, "PICKBOX 0: the preselect voice is mute"
    w = _band_live(ed, _scr(-30, 4), _scr(30, 1), witness, qapp)
    assert w["band"], "the band itself still opens and paints"
    assert w["prev"] == [], "PICKBOX 0: selection PREVIEWING is unavailable"
    assert l1 in ed._sel, \
        "the COMMIT rides box math, not a target radius - it lives"


# ---- persistence, clamps, signal ---------------------------------------------

def test_the_knob_persists_like_the_grid_snap(ed, qapp):
    ed.set_pick_radius(14)
    assert int(QSettings().value("sketch/pickbox")) == 14
    from tracer.ui.sketcheditor import SketchCanvas
    fresh = SketchCanvas()
    assert fresh.pick_radius == 14, "the next canvas remembers"
    fresh.close()
    fresh.deleteLater()


def test_the_knob_clamps_and_signals_once(ed, qapp):
    got = []
    ed.pick_radius_changed.connect(lambda v: got.append(v))
    ed.set_pick_radius(-5)
    assert ed.pick_radius == 0
    ed.set_pick_radius(999)
    assert ed.pick_radius == 20
    ed.set_pick_radius(20)                     # a no-change says nothing
    assert got == [0, 20], "the signal rides REAL changes only"


# ---- the knob reaches the pixels ---------------------------------------------

def test_ink_follows_the_knob(ed, qapp):
    l1, _ = _two_lines(ed)
    off = _scr(-12.5, 3.5)                     # 6 px off l1's row
    _bare_move(ed, off, qapp)

    def hover_ink():
        qimg = ed.grab().toImage().convertToFormat(
            QImage.Format.Format_RGBA8888)
        F = numpy.frombuffer(bytes(qimg.bits()), numpy.uint8).reshape(
            qimg.height(), qimg.width(), 4)[:, :, :3].copy()
        return max(int(((F[y, 100:500].astype(int)[:, 0] > 130)
                        & (F[y, 100:500].astype(int)[:, 2] > 200)).sum())
                   for y in range(189, 196))
    assert hover_ink() >= 100, "at 9 the near miss still wears the voice"
    ed.set_pick_radius(4)                      # eviction repaints at once
    assert hover_ink() <= 40, "shrinking the knob silences the frame NOW"


# ---- R2: THE KNOB MEETS THE HAND (the toolbar carries it) ------------------
# A behavior with no handle is half a feature: Fusion keeps the target
# radius in Options; Tracer's canvas settings live on the sketch
# toolbar beside Snap-to-grid. ONE control, both-way bound, persisted
# only by the canvas mouth (R1) - the chrome never writes QSettings.

import pytest                                                        # noqa


@pytest.fixture
def mw(qapp):
    QSettings().remove("sketch/pickbox")            # POLLUTION LAW
    QSettings().remove("pick/radius")               #  R3: the viewport's
    from tracer.ui.mainwindow import MainWindow     #   knob too
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        # House law (test_sketch_ui's win fixture): headless GL is a
        # Linux-CI affordance; Windows runners skip the boot family.
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    for _ in range(6):
        qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    w.deleteLater()
    QSettings().remove("sketch/pickbox")
    QSettings().remove("pick/radius")
    for _ in range(3):
        qapp.processEvents()


def test_the_toolbar_carries_the_knob(mw):
    sp = mw._pick_spin
    assert (sp.minimum(), sp.maximum()) == (0, 20), \
        "the chrome knows the law's range"
    assert sp.value() == 9 and mw.sketch.pick_radius == 9, \
        "it OPENS where the canvas lives"


def test_spin_turns_the_canvas_and_persists(mw):
    mw._pick_spin.setValue(3)
    assert mw.sketch.pick_radius == 3, "the hand turns the mouth"
    assert int(QSettings().value("sketch/pickbox")) == 3, \
        "the canvas (not the spin) persists it - ONE mouth"


def test_canvas_turns_the_spin(mw):
    mw.sketch.set_pick_radius(15)                   # any other door
    assert mw._pick_spin.value() == 15, \
        "the spin listens: it shows the truth, never a copy"


def test_the_loop_never_spins(mw):
    got = []
    mw.sketch.pick_radius_changed.connect(got.append)
    mw._pick_spin.setValue(9)                       # the SAME number
    assert got == [], "a no-change says NOTHING (no echo at all)"
    mw._pick_spin.setValue(6)
    assert got == [6], "ONE turn, ONE emission - the loop converges"
    mw._pick_spin.setValue(6)
    assert got == [6]


def test_the_knob_boots_from_settings(mw, qapp):
    QSettings().setValue("sketch/pickbox", 5)
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    w2 = MainWindow(renderer=SceneRenderer())
    w2.show()
    for _ in range(6):
        qapp.processEvents()
    assert w2.sketch.pick_radius == 5 == w2._pick_spin.value(), \
        "the remembered knob greets the next session"
    w2._unsaved = False
    w2.close()
    w2.deleteLater()


def test_the_chrome_never_moves_the_canvas_center(mw, qapp):
    # LAYOUT PARITY LAW (learned CI-red twice over): the sketch bar's
    # natural size sets the offscreen window, the window sets the
    # canvas - and drag fixtures round w2s() to screen PIXELS, so both
    # canvas halves must be integers. The spin's stock footprint came
    # ODD (99px wide, 28px tall), slid every x by 0.125 world, and
    # turned exact drags into 802.5s. A handle may not redecorate the
    # studio: it sits in its row at its row's PARITY.
    cv = mw.sketch
    mw.action_new_sketch()                       # the VICTIM's context:
    for _ in range(4):                           #  sketch page LIVE
        qapp.processEvents()
    assert cv.width() % 2 == 0 and cv.height() % 2 == 0, \
        f"canvas {cv.width()}x{cv.height()} - centre on a half-pixel"
    for wx, wy in ((40, 20), (-40, -20), (0, 0)):
        p = cv.w2s(wx, wy)
        assert p.x() == int(p.x()) and p.y() == int(p.y()), \
            "w2s must survive toPoint() unharmed at ANY target"


# ---- R3: THE BOX SHOWS ITS TAKE - THE SAME LAW IN THREE DIMENSIONS ---------
# M184 R2 gave the sketch band a live voice; the viewport's rubber band
# dragged BLIND (hover cleared while the box lived, nothing glowed until
# release). The same two laws port: (1) the commit splits off a PURE
# MOUTH (_box_hits) that the preview and the release ask together, so
# the wash and the set can never drift; (2) LAW-45's zero silences this
# preview too - "PICKBOX = 0 -> selection PREVIEWING is not available"
# speaks with one voice on both canvases, while the box's own COMMIT
# (containment, not a target radius) lives on.
# The witness is the renderer's OWN highlight column (m160's precedent):
# hover = 0.5, selection = 1.0 - the ghost must wear the COMMIT's value.


def _plate_vp(mw, qapp):
    mw.new_document()
    mw.doc.add_plate("plate", 20, 20, 5)      # a box: 6 face groups
    mw.recompute()
    for _ in range(4):
        qapp.processEvents()
    return mw.viewport


def _band_move(vp, pt, qapp):
    p = QPointF(float(pt[0]), float(pt[1]))
    g = QPointF(vp.mapToGlobal(QPoint(int(pt[0]), int(pt[1]))))
    QApplication.sendEvent(
        vp, QMouseEvent(QEvent.Type.MouseMove, p, g,
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    for _ in range(3):
        qapp.processEvents()


def _box_drag(vp, a, b, qapp, mid=None):
    """press on EMPTY, one move, WITNESS with the band alive, release."""
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(*a))
    for _ in range(2):
        qapp.processEvents()
    _band_move(vp, b, qapp)
    w = mid(vp) if mid else None
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(*b))
    for _ in range(3):
        qapp.processEvents()
    return w


def _wash(vp):
    return float(vp._r._solid_data[:, 12].max())


def test_the_live_box_shows_its_take(mw, qapp):
    vp = _plate_vp(mw, qapp)
    emits = []
    vp.selection_changed.connect(lambda n: emits.append(n))

    def witness(c):
        return dict(prev=list(c._box_prev), sel=list(c._sel),
                    band=c._box is not None, wash=_wash(c),
                    shouted=len(emits))
    w = _box_drag(vp, (5, 5), (vp.width() - 6, vp.height() - 6), qapp,
                  mid=witness)
    n = len(vp._tm.faces)
    assert w["band"] and len(w["prev"]) == n, \
        "the live box already answers: every face inside is TAKEN"
    assert w["sel"] == [], "preview is PREVIEW - the set commits at release"
    assert w["wash"] == pytest.approx(1.0), \
        "the take wears the COMMIT's value (1.0), not the hover's 0.5"
    assert w["shouted"] == 0, "the preview never shouts: signals are commit's"
    assert set(vp._sel) == set(w["prev"]) and vp._box_prev == [], \
        "release commits the VERY answer the preview showed, ghost dies"


def test_the_mouth_holds_the_direction_law(mw, qapp):
    vp = _plate_vp(mw, qapp)
    vp._cam.set_view("front")
    vp.refresh(fit=True)
    for _ in range(4):
        qapp.processEvents()
    lo, hi = vp.window().doc.result.bounding_box
    mid = (lo[1] + hi[1]) / 2
    z0, rz = lo[2], (hi - lo)[2]
    top = vp._cam.project([(lo + hi)[0] / 2, mid, z0 + rz * 0.35],
                          vp.width(), vp.height())
    bot = vp._cam.project([(lo + hi)[0] / 2, mid, z0 + rz * 0.65],
                          vp.width(), vp.height())
    xr = vp._cam.project([hi[0] + 30, mid, (lo + hi)[2] / 2],
                         vp.width(), vp.height())
    xl = vp._cam.project([lo[0] - 30, mid, (lo + hi)[2] / 2],
                         vp.width(), vp.height())
    cross = (QPoint(int(xr[0]), int(top[1])), QPoint(int(xl[0]), int(bot[1])))
    win_ = (QPoint(int(xl[0]), int(top[1])), QPoint(int(xr[0]), int(bot[1])))
    hits = vp._box_hits(*cross)
    assert 0 < len(hits) < len(vp._tm.faces), \
        "CROSSING takes the four touchers - not the whole model"
    assert vp._box_hits(*win_) == [], \
        "WINDOW same box: no face lands FULLY inside - takes nothing"
    vp._select_box(*cross)
    assert set(vp._sel) == set(hits), \
        "commit IS the mouth's answer - preview and set can never drift"
    keep = hits[0]
    vp._sel = [keep]
    vp._select_box(*win_, add=True)          # adds nothing, loses nothing
    assert vp._sel == [keep], "the add grammar survived the split"


def test_the_zero_mutes_the_live_take_not_the_commit(mw, qapp):
    vp = _plate_vp(mw, qapp)
    vp.set_pick_radius(0)

    def witness(c):
        return dict(prev=len(c._box_prev), band=c._box is not None,
                    wash=_wash(c))
    w = _box_drag(vp, (5, 5), (vp.width() - 6, vp.height() - 6), qapp,
                  mid=witness)
    assert w["band"], "the band itself still opens and paints"
    assert w["prev"] == 0 and w["wash"] < 0.5, \
        "LAW-45's zero: PREVIEWING is not available - no ghost, no wash"
    assert vp._sel, \
        "the BOX commit lives - containment is not a target radius"


def test_the_zero_evicts_a_live_ghost_now(mw, qapp):
    vp = _plate_vp(mw, qapp)
    a, b = (5, 5), (vp.width() - 6, vp.height() - 6)
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(*a))
    _band_move(vp, b, qapp)
    assert vp._box_prev, "the ghost is alive mid-drag (default knob 3)"
    vp.set_pick_radius(0)                    # the knob turns UNDER way
    assert vp._box_prev == [] and _wash(vp) < 0.5, \
        "the zero evicts the stale wash NOW, not on the next move"
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(*b))
    for _ in range(3):
        qapp.processEvents()
    assert vp._sel, "and the release still commits"


def test_a_rebuild_buries_the_ghost(mw, qapp):
    vp = _plate_vp(mw, qapp)
    a, b = (5, 5), (vp.width() - 6, vp.height() - 6)
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(*a))
    _band_move(vp, b, qapp)
    assert vp._box_prev
    vp.refresh()                             # mesh rebuild = old ids lie
    assert vp._box_prev == [] and _wash(vp) < 0.5, \
        "a stale face id must never keep glowing (M160's law, R3 clone)"
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(*b))
    for _ in range(3):
        qapp.processEvents()


def test_the_mouth_silently_denies_a_world_without_mesh(mw):
    vp = mw.viewport
    vp._tm = None                            # the world before a mesh
    assert vp._box_hits(QPoint(0, 0), QPoint(10, 10)) == []
    vp._select_box(QPoint(0, 0), QPoint(10, 10))
    assert vp._sel == [], "no mesh, no mouth, NO crash and no state lie"
