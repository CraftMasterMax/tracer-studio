"""M183 R1: THE PROMOTE MOUTH (FD8 LAW-36).

The law (Autodesk blog, "New ways to access commands"): "select the
Promote button... the tool appears at the top each time the character
is keyed in; 'c' + Space/Enter invokes Chamfer."  R1 lands the STORE
and the PIN: promotion persists (QSettings), survives restarts, rides
one identity mouth (plain() - "Cham&fer" and "Chamfer" are the SAME
tool), keeps a star marker in the row text, pins the promoted hit to
the top of every list it matches - and bows to the ENABLED law (a
promoted-but-disabled command stays invisible: the pin is an ORDER,
never a resurrection).
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, QPoint, Qt                  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget               # noqa: E402

from tracer.ui.commands import Command                            # noqa: E402
from tracer.ui.palette import CommandPalette                      # noqa: E402

STAR = "\u2605"                                                    # ★


@pytest.fixture
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def settings_scrub():
    """No test may haunt the real user's toolbox with our stars."""
    s = QSettings()
    saved = s.value("palette/promoted", None)
    s.remove("palette/promoted")
    s.sync()
    yield
    if saved is None:
        s.remove("palette/promoted")
    else:
        s.setValue("palette/promoted", saved)
    s.sync()


@pytest.fixture
def host(qapp, settings_scrub):
    h = QWidget()
    h.resize(800, 600)
    h.show()
    qapp.processEvents()
    yield h
    h.close()
    h.deleteLater()          # POLLUTION LAW: shown widget, close then reap


def _cmds(ran):
    def runner(name):
        return lambda: ran.append(name)
    # Chamfer is LAST in collection order: without a pin, "c" ties with
    # Circle and the EARLIER entry wins - so a row-0 Chamfer can only
    # mean the PROMOTION moved it.  Plain-cop and mnemonics mix on
    # purpose (identity law).
    return [
        Command("Circle", "Sketch", "C", runner("circle"), lambda: True),
        Command("Cut", "Sketch", "", runner("cut"), lambda: True),
        Command("Cham&fer", "Modify", "G", runner("chamfer"), lambda: True),
    ]


def _pal(host, commands):
    p = CommandPalette(host)
    p.set_commands(commands)
    return p


def test_promote_persists_across_a_restart(host):
    ran = []
    p = _pal(host, _cmds(ran))
    p.toggle_promote(_cmds(ran)[2])            # the SAME identity, fresh obj
    assert p._promoted, "promote must enter the live set"
    q = _pal(host, _cmds(ran))                 # a NEW palette = the restart
    assert p._promoted == q._promoted, "the store must round-trip settings"


def test_promoted_pins_to_row_zero_on_its_letter(host):
    ran = []
    p = _pal(host, _cmds(ran))
    p.edit.setText("c")
    assert p.list.item(0).text().startswith("Circle")  # pre-law truth
    p.toggle_promote(_cmds(ran)[2])
    p.edit.setText("")                                 # force a refilter
    p.edit.setText("c")
    assert p.list.count() == 3, "Circle, Cut and Chamfer all carry the c"
    it0 = p.list.item(0)
    assert "Cham" in it0.text() and STAR in it0.text(), \
        "the promoted hit rides row 0 WHENEVER its character is keyed"
    assert STAR not in p.list.item(1).text(), "only promoted rows wear stars"


def test_unpromote_round_trips_everything(host):
    ran = []
    p = _pal(host, _cmds(ran))
    p.toggle_promote(_cmds(ran)[2])
    p.toggle_promote(_cmds(ran)[2])                    # the same mouth off
    p.edit.setText("c")
    assert p.list.item(0).text().startswith("Circle"), "the pin must lift"
    assert STAR not in p.list.item(1).text()
    assert not p._promoted, "unpromote must empty the store it owns"


def test_identity_is_the_plain_label_one_mouth(host):
    ran = []
    p = _pal(host, _cmds(ran))
    p.toggle_promote(Command("Chamfer", "Modify", "X",   # NO mnemonic,
                             runner_noop, lambda: True))  # different key
    q = _pal(host, _cmds(ran))                           # "Cham&fer" copy
    q.edit.setText("c")
    assert STAR in q.list.item(0).text(), \
        "Chamfer and Cham&fer are the SAME tool (plain()'s identity)"


def runner_noop():
    pass


def test_promoted_but_disabled_stays_invisible(host):
    ran = []
    dead = Command("Cham&fer", "Modify", "G", runner_noop, lambda: False)
    p = _pal(host, _cmds(ran) + [dead])
    p.toggle_promote(_cmds(ran)[2])
    p.set_commands([dead])               # ONLY the disabled twin remains
    assert p.list.count() == 0, \
        "the pin is an ORDER law, never a resurrection"


def test_context_mouth_names_the_action(host, qapp):
    ran = []
    p = _pal(host, _cmds(ran))
    p.show()
    qapp.processEvents()
    cham = p._live[2]                                # the Chamfer COMMAND
    menu = p._promote_menu(cham)                     # (the PIN MOVES rows -
    assert menu.actions()[0].text().startswith("Promote"), \
        "the mouth offers PROMOTE before the fact"     #  so the object,
    menu.actions()[0].trigger()                        #  never an index)
    assert any(STAR in p.list.item(i).text()
               for i in range(p.list.count())), \
        "triggering the mouth must paint the star"
    menu2 = p._promote_menu(cham)
    assert menu2.actions()[0].text().startswith("Unpromote"), \
        "the same mouth reverses"


def test_two_promoted_keep_rank_order_between_them(host):
    ran = []
    cmds = _cmds(ran)
    p = _pal(host, cmds)
    p.toggle_promote(cmds[2])                          # Cham&fer
    p.toggle_promote(cmds[0])                          # Circle
    p.edit.setText("c")
    texts = [p.list.item(i).text() for i in range(p.list.count())]
    assert len(texts) == 3
    top = [t for t in texts if STAR in t]
    assert len(top) == 2 and all(t in texts[:2] for t in top), \
        "both promoted ride the top pair, the unpinned stays below"
    assert any("Circle" in t for t in texts[:2]) \
        and any("Cham" in t for t in texts[:2]), "exactly the two pins"
    ci = next(i for i, t in enumerate(texts) if "Circle" in t)
    hi = next(i for i, t in enumerate(texts) if "Cham" in t)
    assert ci < hi, "the pins keep the RANK order among themselves"


# ---- R2: THE SPACE SUMMON (the law's sentence) + its button --------------
# "pressing 'c' followed by Spacebar/Enter will now invoke the Chamfer
# command" - [documented] verbatim.  Fusion's vehicle: "the Promote
# button NEXT TO a resulting command" - an inline row button, which
# lands here too (R1's right-click mouth stays as the keyboard route).

from PySide6.QtCore import QEvent, QPointF, QRect                    # noqa: E402
from PySide6.QtGui import QMouseEvent, QImage                        # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QStyleOptionViewItem                   # noqa: E402


def _opened(host, cmds, query="", ran=None):
    p = _pal(host, cmds)
    if ran is not None:                 # the kit's seam: picked rides ran
        p.picked.connect(lambda: ran.append("picked"))   # BEFORE cmd.run()
    p.show()
    QTest.qWaitForWindowExposed(p)
    p.open_at(200, 100)
    if query:
        p.edit.setText(query)
        QTest.qWait(10)
    return p


def test_space_runs_the_current_row(host):
    ran = []
    p = _opened(host, _cmds(ran), "c", ran)
    QTest.keyClick(p.edit, Qt.Key_Space)
    assert ran == ["picked", "circle"], "Space INVOKES the top hit (LAW-36)"
    assert not p.isVisible(), "invoking closes the toolbox"


def test_law_sentence_c_then_space(host):
    ran = []
    p = _pal(host, _cmds(ran))
    p.toggle_promote(_cmds(ran)[2])          # teach: Chamfer
    p2 = _opened(host, _cmds(ran), "c", ran)  # the letter, fresh toolbox
    assert STAR in p2.list.item(0).text()    # pinned row 0 (R1's law)
    QTest.keyClick(p2.edit, Qt.Key_Space)
    assert ran == ["picked", "chamfer"], \
        "'c' + Space invokes Chamfer - the documented sentence end to end"


def test_space_types_only_when_nothing_matches(host):
    ran = []
    p = _opened(host, _cmds(ran), "zzqx")    # the empty-list escape hatch
    assert p.list.count() == 0
    QTest.keyClick(p.edit, Qt.Key_Space)
    assert not ran, "nothing to run: Space is just a space (multi-word fuel)"
    assert p.edit.text() == "zzqx "


def test_modified_space_passes_through(host):
    ran = []
    p = _opened(host, _cmds(ran), "c")
    QTest.keyClick(p.edit, Qt.Key_Space, Qt.ControlModifier)
    assert not ran, "the summon is PLAIN Space; Ctrl+Space is not the law"


def test_enter_still_runs_after_the_filter(host):
    ran = []
    p = _opened(host, _cmds(ran), "c")
    QTest.keyClick(p.edit, Qt.Key_Return)
    assert ran, "R2's event filter may not steal Enter (R1/M113 regression)"


def test_button_label_reads_the_state(host):
    ran = []
    cham = _cmds(ran)[2]
    p = _pal(host, _cmds(ran))
    assert p._btn_label(cham) == "promote"
    p.toggle_promote(cham)
    assert p._btn_label(cham) == "unpromote", \
        "the row's button speaks the current state (Fusion's mouth)"


def test_press_on_the_button_promotes_without_running(host):
    ran = []
    p = _opened(host, _cmds(ran))            # empty query: all rows
    idx = p.list.model().index(2, 0)         # the Cham&fer row
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 620, 24)
    inside = p.delegate._btn_rect(opt.rect).center()
    ev = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(inside),
                     QPointF(inside), QPointF(inside),
                     Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    assert p.delegate.editorEvent(ev, p.list.model(), opt, idx), \
        "the button CLAIMS the press"
    assert p._promoted, "pressing the button taught the toolbox"
    assert not ran, "and NOTHING RAN - the button is not the row"
    outside = QPoint(20, 12)
    ev2 = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(outside),
                      QPointF(outside), QPointF(outside),
                      Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    assert not p.delegate.editorEvent(ev2, p.list.model(), opt, idx), \
        "outside the button the row keeps its own life"


from PySide6.QtCore import QPoint as QPoint2                          # noqa: E402


def test_the_button_is_frame_ink(host, qapp):
    ran = []
    p = _opened(host, _cmds(ran))
    qapp.processEvents()
    img = p.list.viewport().grab().toImage().convertToFormat(
        QImage.Format.Format_RGBA8888)
    import numpy
    a = numpy.frombuffer(bytes(img.bits()), numpy.uint8).reshape(
        img.height(), img.width(), 4)[:, :, :3].astype(int)
    row0 = p.list.visualItemRect(p.list.item(0))
    r = p.delegate._btn_rect(row0)
    win = a[r.top():r.bottom() + 1, r.left():r.right() + 1].reshape(-1, 3)
    bright = int((win.min(axis=1) > 120).sum())
    print("button ink px", bright, "rect", r.getRect())
    assert bright > 20, "the promote button is PAINTED on the row"


# ---- R3: THE PALETTE AT THE CURSOR ----------------------------------------
# The same Autodesk post is explicit: "Command Search is designed to
# place access to every Fusion command AT YOUR CURSOR... typing 'c' will
# present the following list NEAR THE CURSOR" [documented].  Landing a
# PURE placement mouth + the window rides IT (one mouth = no drift).

from PySide6.QtCore import QSize                                     # noqa: E402
from tracer.ui.palette import place_near_cursor                      # noqa: E402

PARENT = QRect(100, 50, 900, 700)          # a viewport's global rect
SIZE = QSize(620, 237)
GAP = 6


def test_cursor_open_room_lands_below_right():
    p = place_near_cursor(PARENT, QPoint(300, 300), SIZE, GAP)
    assert p == QPoint(306, 306), "the list opens AT the cursor, gap aside"


def test_right_edge_flips_left_of_the_cursor():
    cur = QPoint(PARENT.right() - 40, 300)
    p = place_near_cursor(PARENT, cur, SIZE, GAP)
    assert p.x() + SIZE.width() == cur.x() - GAP, \
        "no room right? the palette FLIPS left of the cursor (still AT it)"
    assert p.x() >= PARENT.left(), "and it never escapes the parent"


def test_bottom_edge_flips_above_the_cursor():
    cur = QPoint(400, PARENT.bottom() - 30)
    p = place_near_cursor(PARENT, cur, SIZE, GAP)
    assert p.y() + SIZE.height() == cur.y() - GAP, \
        "no room below? it rides ABOVE the cursor - never off-parent"


def test_top_left_corner_clamps_inside():
    p = place_near_cursor(PARENT, QPoint(101, 51), SIZE, GAP)
    assert p.x() >= PARENT.left() and p.y() >= PARENT.top(), \
        "corner cursor: the WHOLE box stays inside the parent"
    assert p.x() + SIZE.width() <= PARENT.right() + 1 \
        and p.y() + SIZE.height() <= PARENT.bottom() + 1, \
        "a box bigger than the corner clamps to fit"


def test_open_near_clears_refocuses_and_relearns(host):
    cham = Command("Cham&fer", "Modify", "G", lambda: None, lambda: True)
    pa = _pal(host, [cham])
    pa.toggle_promote(cham)              # teach through the store
    pb = _pal(host, [cham])              # a second toolbox (fresh state)
    pb.edit.setText("stale")
    pb.open_near(QRect(0, 0, 1400, 900), QPoint(60, 60))
    assert pb.edit.text() == "", "open clears the query (open_at law rides)"
    assert pb._promoted and STAR in pb.list.item(0).text(), \
        "open_near RE-READS the store - the lesson is visible at once"
    assert pb.edit.hasFocus(), "the field owns the keyboard (LAW-35 twin)"
    pb.hide()


def test_open_near_actually_fits_the_parent(host):
    p = _pal(host, [Command("Aa", "C", "", lambda: None, lambda: True)])
    p.open_near(QRect(0, 0, 800, 600), QPoint(780, 590))
    inside = p.pos().x() >= 0 and p.pos().y() >= 0 \
        and p.pos().x() + p.width() <= 800 + 4 \
        and p.pos().y() + p.height() <= 600 + 4     # offscreen wobble ≤4
    print("corner pal pos", p.pos(), "size", p.width(), p.height())
    assert inside, "the SHOWN box lives inside the parent's global rect"
    p.hide()


def test_the_window_rides_the_same_mouth(win, qapp):
    from PySide6.QtGui import QCursor
    vp = win.viewport
    rect = QRect(vp.mapToGlobal(QPoint(0, 0)), vp.size())
    cur = QPoint(rect.center().x() - 80, rect.center().y() - 40)
    QCursor.setPos(cur)
    qapp.processEvents()
    win.open_command_search()
    qapp.processEvents()
    want = place_near_cursor(rect, QCursor.pos(),
                             QSize(win._palette.width(),
                                   win._palette.height()), 6)
    got = win._palette.pos()
    win._palette.hide()
    assert abs(got.x() - want.x()) <= 4 and abs(got.y() - want.y()) <= 4, \
        f"S places the toolbox AT THE CURSOR via the ONE mouth " \
        f"(want {want}, got {got})"


@pytest.fixture
def win(qapp, settings_scrub):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
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
    w.close()
