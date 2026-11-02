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
