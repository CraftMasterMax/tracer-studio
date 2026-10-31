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

from PySide6.QtCore import QSettings, Qt                          # noqa: E402
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
