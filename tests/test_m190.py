"""M190: ERRORS ARE DOORS (fd8 LAW-63 tree-error navigation).

The class does not describe errors - clicking one LANDS you on the
guilty feature (SW: "Clicking any entity in that list ADVANCES YOU
DIRECTLY to that feature in the tree"). M188 R5 built the voice
(What's-Wrong quotes the kernel scar); M190 R1 turns the door: the
explanation reveals the culprit in the tree (M162's light+scroll+
flash) and selects its timeline chip (M118's Message-Log idiom)
BEFORE it speaks. A clean feature still opens nothing and moves
nothing - "never a dead badge" holds both ways.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                    # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox          # noqa: E402


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
        except Exception as e:                 # CI windows: no headless GL
            pytest.skip(f"no headless GL available: {e}")
        w = MainWindow(renderer=r)
        w.resize(1000, 700)
        w.show()
        qapp.processEvents()
        yield w
        w._unsaved = False
        w.close()
    except ImportError:
        pytest.skip("no PySide6")


def _two_faults(win):
    """Plate + two coils, both broken the m127-proven way (section
    over pitch). Faults sit at TWO distinct slots (m188's recipe)."""
    win.new_document()
    d = win.doc
    from tracer.core.document import PrimitiveFeature
    plate = d.add(PrimitiveFeature(name="Plate", kind="box", op="union",
                                   dims={"dx": 20.0, "dy": 20.0, "dz": 4.0}))
    a = d.add_coil("CoilA", axis="Z", base=(0.0, 0.0, 4.0),
                   diameter=8.0, pitch=1.0, turns=3.0, size=4.0)
    b = d.add_coil("CoilB", axis="Z", base=(0.0, 0.0, 4.0),
                   diameter=9.0, pitch=1.0, turns=3.0, size=4.0)
    win.recompute()
    return d, plate, a, b


def _tree_target(win):
    it = win.rail.tree.currentItem()
    return None if it is None else it.data(0, Qt.UserRole)


def _silent_recompute_told(monkeypatch):
    """The m188 ritual: a failing recompute may speak the recompute
    guard (warning) - a live modal exec deadlocks headless, so BOTH
    verbs are patched BEFORE the model is broken. Only information is
    collected; any warning is swallowed (it is the standing guard,
    not this rung's seam)."""
    told = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda parent, title, text, *a, **k:
                                     told.append((title, text))))
    return told


# ---- R1: THE EXPLANATION IS A DOOR -----------------------------------------------

def test_the_door_lands_on_the_culprit_before_it_speaks(win, qapp,
                                                       monkeypatch):
    told = _silent_recompute_told(monkeypatch)
    d, plate, a, b = _two_faults(win)
    qapp.processEvents()
    assert getattr(a, "error", None), "the coil must carry a scar"
    win._explain_feature(a)
    qapp.processEvents()
    idx = d.features.index(a)
    assert _tree_target(win) == ("feature", idx), \
        "the tree must land on the guilty row (LAW-63: the list " \
        "ADVANCES you directly to the feature)"
    assert win.timeline.bar._sel == idx, \
        "the timeline chip selects too - one culprit, two lights"
    assert len(told) == 1 and "CoilA" in told[0][1]


def test_a_clean_feature_moves_nothing_and_says_nothing(win, qapp,
                                                        monkeypatch):
    told = _silent_recompute_told(monkeypatch)
    d, plate, a, b = _two_faults(win)
    qapp.processEvents()
    before_tree = _tree_target(win)
    before_chip = win.timeline.bar._sel
    win._explain_feature(plate)                # healthy: no scar, no door
    qapp.processEvents()
    assert told == [], "a clean feature opens no door"
    assert _tree_target(win) == before_tree
    assert win.timeline.bar._sel == before_chip


def test_the_gear_door_advances_to_the_queue_head(win, qapp,
                                                  monkeypatch):
    told = _silent_recompute_told(monkeypatch)
    d, plate, a, b = _two_faults(win)
    qapp.processEvents()
    acts = {x.text(): x for x in win._build_gear_menu().actions()
            if x.text()}
    acts["What's Wrong?"].trigger()
    qapp.processEvents()
    assert _tree_target(win) == ("feature", d.features.index(a)), \
        "the gear aims at the queue head - and LANDS on its row"
    assert len(told) == 1 and "CoilA" in told[0][1]


# ---- R2: THE TREE SPEAKS THE FAULT LANGUAGE (LAW-62) -----------------------------
# The chip has worn the red corner since M118 and the amber sibling
# since M152 - the TREE row stayed silent (no red text, no marker, no
# root rollup). The class paints both families at BOTH places and
# rules "if both error AND warning, the ERROR ICON is displayed": the
# row turns red, the root wears the rollup, and red outranks amber so
# the rollup never flickers while any red is home.

from tracer.ui.theme import DARK                                     # noqa: E402


def _row(win, role):
    def walk(it):
        for i in range(it.childCount()):
            ch = it.child(i)
            if ch.data(0, Qt.UserRole) == role:
                return ch
            got = walk(ch)
            if got is not None:
                return got
        return None
    return walk(win.rail.tree.invisibleRootItem())


def test_a_broken_feature_row_turns_red(win, qapp, monkeypatch):
    _silent_recompute_told(monkeypatch)          # patch BEFORE the wound
    d, plate, a, b = _two_faults(win)
    win.rail.tree.reload()
    qapp.processEvents()
    ia = d.features.index(a)
    assert _row(win, ("feature", ia)).foreground(0).color().name() \
        == DARK["danger"], "the class's failing-feature TEXT IS RED"
    assert _row(win, ("feature", 0)).foreground(0).color().name() \
        != DARK["danger"], "the row that baked clean wears no lie"
    assert win.rail.tree._faults[("feature", ia)] == "error"


def test_the_root_rollup_outranks_and_never_flickers(win, qapp,
                                                     monkeypatch):
    _silent_recompute_told(monkeypatch)
    d, plate, a, b = _two_faults(win)
    d.attachment_warnings = ["Plate \u2014 host gone"]   # both families home
    win.rail.tree.reload()
    qapp.processEvents()
    assert win.rail.tree._fault_state == "error", \
        "both error AND warning - the ERROR voice is displayed"
    a.error = None
    b.error = None                         # repair the coils, keep the warn
    win.rail.tree.reload()
    qapp.processEvents()
    assert win.rail.tree._fault_state == "warn", \
        "with the reds gone the amber rollup stands - never flickers off"
    assert _row(win, ("feature", 0)).foreground(0).color().name() \
        == DARK["warn"], "the amber row (M152) rides beside the rollup"
    d.attachment_warnings = []
    win.rail.tree.reload()
    qapp.processEvents()
    assert win.rail.tree._fault_state is None, "a clean doc wears no badge"
    assert win.rail.tree._faults == {}


def test_error_outranks_warn_on_the_same_row(win, qapp, monkeypatch):
    _silent_recompute_told(monkeypatch)
    d, plate, a, b = _two_faults(win)
    ia = d.features.index(a)
    d.attachment_warnings = ["CoilA \u2014 host gone",
                             "Plate \u2014 host gone"]
    win.rail.tree.reload()
    qapp.processEvents()
    # CoilA: scarred AND warned -> red wins the row and the fault map.
    assert _row(win, ("feature", ia)).foreground(0).color().name() \
        == DARK["danger"]
    assert win.rail.tree._faults[("feature", ia)] == "error"
    # Plate: warned only -> amber keeps its voice (M152 unchanged).
    assert _row(win, ("feature", 0)).foreground(0).color().name() \
        == DARK["warn"]
    assert win.rail.tree._faults[("feature", 0)] == "warn"


# ---- R3: THE LIST LANDS IN THE TREE, THE ROWS SPEAK ON HOVER ----------------------
# LAW-63's list is the Message Log (M118 minted it) - but its door
# only selected the chip, never the row, and no row ever explained
# itself to a hovering pointer. The class law ends "...ADVANCES YOU
# DIRECTLY to that feature IN THE TREE"; hover explains. A clean row
# carries no tooltip: the badge never lies, either way.

def test_the_log_door_lands_on_the_row_too(win, qapp, monkeypatch):
    _silent_recompute_told(monkeypatch)
    d, plate, a, b = _two_faults(win)
    ia = d.features.index(a)
    win._goto_logged_feature(ia)             # m118's seam, the log row
    qapp.processEvents()
    assert _tree_target(win) == ("feature", ia), \
        "the list advances to the feature IN THE TREE"
    assert win.timeline.bar._sel == ia, "the M118 chip half stands intact"
    assert "CoilA" in win.status.currentMessage()


def test_broken_and_warned_rows_explain_on_hover(win, qapp,
                                                 monkeypatch):
    _silent_recompute_told(monkeypatch)
    d, plate, a, b = _two_faults(win)
    d.attachment_warnings = ["Plate \u2014 host gone"]
    win.rail.tree.reload()
    qapp.processEvents()
    ia = d.features.index(a)
    tip = _row(win, ("feature", ia)).toolTip(0)
    assert "CoilA" in tip and "failed to rebuild" in tip \
        and "What's Wrong" in tip, tip
    assert a.error in tip, "the kernel's scar is QUOTED, never paraphrased"
    assert _row(win, ("feature", 0)).toolTip(0) == "Plate \u2014 host gone"


def test_a_clean_row_carries_no_tooltip_and_speaks_no_lie(win, qapp,
                                                          monkeypatch):
    _silent_recompute_told(monkeypatch)
    from tracer.core.document import PrimitiveFeature
    win.new_document()
    win.doc.add(PrimitiveFeature(name="Sole", kind="box", op="union",
                                 dims={"dx": 10.0, "dy": 10.0, "dz": 2.0}))
    win.recompute()
    win.rail.tree.reload()
    qapp.processEvents()
    assert _row(win, ("feature", 0)).toolTip(0) == ""


# ---- R4: THE ROLLUP DOT IS A BUTTON ------------------------------------------------
# "Click a part name to reveal a list of errors and warnings" - the
# lit root row is that click: the Message Log opens AND the queue
# head lands (R3's walk). A clean root emits nothing: no door knocks
# without a guest.

def _press_root(win, qapp):
    from PySide6.QtTest import QTest
    tree = win.rail.tree
    rect = tree.visualRect(tree.indexFromItem(tree.topLevelItem(0)))
    QTest.mousePress(tree.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier,
                     tree.viewport().mapFrom(tree, rect.center()))
    qapp.processEvents()


def test_the_rollup_reveals_the_list_and_lands_on_the_head(win, qapp,
                                                           monkeypatch):
    _silent_recompute_told(monkeypatch)
    d, plate, a, b = _two_faults(win)
    qapp.processEvents()
    assert not win._log_menu.isChecked()       # the list starts closed
    _press_root(win, qapp)
    assert win._log_menu.isChecked(), "the rollup REVEALS the list"
    assert _tree_target(win) == ("feature", d.features.index(a)), \
        "...and the queue head is landed on in one gesture"
    assert win.timeline.bar._sel == d.features.index(a)


def test_a_clean_root_clicks_quietly_no_door_no_lie(win, qapp,
                                                    monkeypatch):
    _silent_recompute_told(monkeypatch)
    from tracer.core.document import PrimitiveFeature
    win.new_document()
    win.doc.add(PrimitiveFeature(name="Sole", kind="box", op="union",
                                 dims={"dx": 10.0, "dy": 10.0, "dz": 2.0}))
    win.recompute()
    qapp.processEvents()
    assert win.rail.tree._fault_state is None
    _press_root(win, qapp)
    assert not win._log_menu.isChecked(), "no fault - no door"
