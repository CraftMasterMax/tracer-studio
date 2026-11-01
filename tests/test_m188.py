"""M188 rung 1 - THE BAND THAT FINDS THE FAULT (LAW-64 documented).

"when repairing a model with errors, the rollback bar SHIFTS TO THE
FEATURE WITH THE FIRST ERROR. As you fix one error, roll forward to
the next." (SolidWorks rebuild-repair docs, fd8 LAW-64.) Tracer owns
every part except the SHIFT: the band (M88) is user-dragged, the scar
(M118) badges the guilty chip, the modal speaks. Now a failed rebuild
lands the rollback marker right BEFORE the fault - the model you look
at becomes the last honest state, and the fault waits just past the
marker wearing its scar.

That scar law is this rung's core honesty: a pass where the band
SKIPPED the failing feature never RAN it, and a pass that never ran
a fault cannot call it healed. The clean-pass wipe now respects the
band; the pointer and the log's "clean again" news survive only when
every scar actually healed. Fixing is the maker's verb: roll the
marker forward and the feature runs again - heals or re-faults (and
the band shifts there, the ride continuing toward the end).
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                       # noqa: E402

from tracer.core import logservice as L                          # noqa: E402
from tracer.core.document import Document, PrimitiveFeature      # noqa: E402


@pytest.fixture(autouse=True)
def _clean_bus():
    L.clear()
    yield
    L.clear()


def _failing_doc():
    """A document whose first recompute is guaranteed to fail (M118's
    own fixture: a subtract with nothing to subtract from)."""
    d = Document("t")
    d.features.append(PrimitiveFeature(name="cut", kind="box",
                                       op="subtract",
                                       dims={"dx": 5.0, "dy": 5.0,
                                             "dz": 5.0}))
    return d


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


# ---- the core law: a SKIP is not a HEAL ---------------------------------------


def test_a_banded_pass_never_heals_the_scar():
    d = _failing_doc()
    with pytest.raises(ValueError):
        d.recompute()
    assert d.record_failure("boom") == (0, "cut")
    assert getattr(d.features[0], "error", None) == "boom"
    d.rollback_to = 0
    r = d.recompute()                       # the band skips the fault
    assert r is None                        # nothing built - honest empty
    assert d.features[0].error == "boom", \
        "the pass never RAN the fault - the scar must outlive the skip"
    assert d.failed_feature == (0, "cut"), \
        "and the pointer rides while any scar is still wearing one"
    d.rollback_to = None
    d.features[0].op = "union"              # the fix, then it RUNS
    d.recompute()
    assert getattr(d.features[0], "error", None) is None
    assert d.failed_feature is None, \
        "a feature that ran clean IS healed - the scar retires"


def test_record_failure_only_wipes_features_that_ran():
    d = _failing_doc()
    d.features.append(PrimitiveFeature(name="plate", kind="box",
                                       op="union",
                                       dims={"dx": 2.0, "dy": 2.0,
                                             "dz": 2.0}))
    d.features[1].error = "old wound"          # a scar past the marker
    d.rollback_to = 1                          # plate will be SKIPPED
    with pytest.raises(ValueError):            # cut (pos 0) still faults
        d.recompute()
    d.record_failure("fresh boom")
    assert d.features[1].error == "old wound", \
        "an old scar BEHIND the marker never got re-tested - the fresh " \
        "failure may not wipe it clean by proxy"


# ---- the UI law: the bar SHIFTS TO the fault -----------------------------------


def test_the_band_shifts_to_the_fault(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(1)))
    win.doc = _failing_doc()
    win.recompute()
    qapp.processEvents()
    assert win.doc.rollback_to == 0, \
        "the rollback bar SHIFTS TO the feature with the first error"
    assert win.doc.failed_feature == (0, "cut"), "the fault still wears"
    assert len(seen) == 1, "the modal speaks ONCE (no re-entry storm)"
    assert "cut" in win.status.currentMessage(), \
        "and the status line names where the marker landed"
    win.recompute()                            # the repair posture:
    assert len(seen) == 1 and win.doc.rollback_to == 0, \
        "the model now LIVES at the marker - the fault is skipped, " \
        "no second modal, the scar stays visible"


def test_a_skip_pass_is_never_news(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    win.doc = _failing_doc()
    win.recompute()                            # fault -> band lands at 0
    win.doc.features[0].op = "union"           # a BLIND fix under the band
    win.recompute()
    assert not any("clean again" in e.text for e in L.entries()), \
        "the fault never RAN - the log may not call it healed"
    assert win.doc.features[0].error           # scar still wears
    win._apply_rollback(None)                  # ROLL FORWARD: test the fix
    qapp.processEvents()
    assert any("clean again" in e.text for e in L.entries()), \
        "run again clean and ONLY then is recovery news"
    assert win.doc.failed_feature is None
    assert win.doc.rollback_to is None


def test_a_clean_pass_never_moves_the_band(win, qapp):
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 2.0, "dy": 2.0, "dz": 2.0}))
    win.recompute()
    win._apply_rollback(0)                     # the user parked the marker
    win.recompute()                            # a healthy rebuild after
    assert win.doc.rollback_to == 0, \
        "a pass with no fault is NOT an opinion about the view - the " \
        "band only moves to find errors, never on its own"
    win._apply_rollback(None)


# ---- R2: THE WALK - "as you fix one error, roll forward to the next" ---------
# LAW-64 names its doors: "Roll to Previous / Roll To End named
# commands". The marker today answers only drags; now the timeline
# gear speaks both verbs, and the pair of faults below walks the
# repair exactly as the sentence reads: fault -> the bar lands at it
# -> fix -> Roll To End -> the bar RODE to the next error -> fix ->
# Roll To End -> clean, and the marker goes home.

def _two_faults(win):
    """Plate + two coils, both broken the m127-proven way (section
    over pitch). Faults are staged at TWO distinct slots."""
    d = win.doc
    d.add(PrimitiveFeature(name="Plate", kind="box", op="union",
                           dims={"dx": 20.0, "dy": 20.0, "dz": 4.0}))
    a = d.add_coil("CoilA", axis="Z", base=(0.0, 0.0, 4.0),
                   diameter=8.0, pitch=1.0, turns=3.0, size=4.0)
    b = d.add_coil("CoilB", axis="Z", base=(0.0, 0.0, 4.0),
                   diameter=9.0, pitch=1.0, turns=3.0, size=4.0)
    return d, a, b


def _gear_actions(win):
    return {x.text(): x for x in win._build_gear_menu().actions()
            if x.text()}


def test_the_gear_names_both_rollback_verbs(win):
    acts = _gear_actions(win)
    assert "Roll to Previous" in acts and "Roll To End" in acts, \
        "the commands are NAMED, like the vendor names them"
    assert acts["Roll To End"].isEnabled() is False, \
        "at the end, Roll To End has nothing to end"
    win.doc.rollback_to = 1
    assert _gear_actions(win)["Roll To End"].isEnabled(), \
        "with the marker parked, ending it is exactly the door"
    win.doc.rollback_to = None


def test_roll_to_previous_steps_the_marker_one_slot(win):
    from tracer.core.document import PrimitiveFeature as _P
    for i in range(3):
        win.doc.add(_P(name=f"WP{i}", kind="box", op="union",
                       dims={"dx": 2.0, "dy": 2.0, "dz": 2.0}))
    win.recompute()
    total = len(win.doc.features)
    win._roll_to_previous()                    # from the END: one back
    assert win.doc.rollback_to == total - 1
    win._roll_to_previous()
    assert win.doc.rollback_to == total - 2
    win.doc.rollback_to = 0                    # at the front: it stays
    win._roll_to_previous()
    assert win.doc.rollback_to == 0, "the marker never runs off the front"
    win._apply_rollback(None)


def test_the_repair_walk_rides_one_fault_to_the_next(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(1)))
    d, a, b = _two_faults(win)
    ia, ib = d.features.index(a), d.features.index(b)
    win.recompute()                            # CoilA faults first
    assert d.rollback_to == ia and d.failed_feature[1] == "CoilA" \
        and len(seen) == 1, "the bar landed at the FIRST error"
    a.pitch = 6.0                              # the first fix
    _gear_actions(win)["Roll To End"].trigger()
    qapp_ev = None                             # (menu verbs recompute)
    assert d.rollback_to == ib and d.failed_feature[1] == "CoilB" \
        and len(seen) == 2, \
        "as you fix one error, roll forward TO THE NEXT - the bar rode"
    assert getattr(a, "error", None) is None, \
        "CoilA RAN clean on the way - its scar healed honestly"
    b.pitch = 6.0                              # the last fix
    _gear_actions(win)["Roll To End"].trigger()
    assert d.rollback_to is None and d.failed_feature is None \
        and len(seen) == 2, "clean at last: the marker goes home"
    news = [e for e in L.entries() if "clean again" in e.text]
    assert len(news) == 1, "recovery became news EXACTLY once"


def test_resting_at_the_fault_never_storms_the_modal(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(1)))
    d, a, b = _two_faults(win)
    ia = d.features.index(a)
    win.recompute()
    assert d.rollback_to == ia and len(seen) == 1
    win.recompute()                            # the maker pokes again:
    win.recompute()                            #  the fault is skipped -
    assert len(seen) == 1 and d.rollback_to == ia, \
        "resting at the marker is a PASSIVE posture - the fault is " \
        "skipped, the scar stays, no repeated modal"
    a.pitch = 6.0
    b.pitch = 6.0
    win._apply_rollback(None)                  # tidy: heal fully

# ---- R3: WHAT'S WRONG? - the explanation is RE-ASKABLE (LAW-65) --------------
# "right-click What's Wrong? diagnostic" (SolidWorks so_messages, fd8
# LAW-65). R2 made the bar WALK; rung 3 lets the fault EXPLAIN itself:
# the gear's "What's Wrong?" QUOTES the kernel's own refusal (state +
# cause + next action - LAW-67: mechanistic, directive, <=2 sentences)
# as often as the maker asks. The first-voice modal stays the ambush;
# the inspector is the door you knock on. Passive: asking runs nothing.

import re                                                        # noqa: E402


def _sentences(text):
    return re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())


def test_the_gear_offers_whats_wrong_only_with_an_answer(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    acts = _gear_actions(win)
    assert "What's Wrong?" in acts, \
        "the diagnostic door is NAMED, vendor-style"
    assert acts["What's Wrong?"].isEnabled() is False, \
        "a clean model has nothing wrong to explain - the door is shut"
    d, a, b = _two_faults(win)
    win.recompute()
    assert _gear_actions(win)["What's Wrong?"].isEnabled(), \
        "with a fault queued, the explanation is askable"
    a.pitch = 6.0
    b.pitch = 6.0
    _gear_actions(win)["Roll To End"].trigger()
    assert _gear_actions(win)["What's Wrong?"].isEnabled() is False, \
        "the door CLOSES with the wound - healed means nothing to ask"


def test_the_inspection_quotes_the_kernel_and_names_the_next_step(
        win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    told = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda parent, title, text, *a, **k:
                                     told.append((title, text))))
    d, a, b = _two_faults(win)
    win.recompute()
    _gear_actions(win)["What's Wrong?"].trigger()
    assert len(told) == 1
    title, text = told[0]
    assert "What's Wrong" in title
    assert "CoilA" in text, "the STATE names the guilty feature"
    assert a.error in text, "the CAUSE is the kernel's OWN words, quoted"
    assert "Roll To End" in text, \
        "and the NEXT ACTION names the very verb rung 2 minted"
    assert len(_sentences(text)) <= 2, \
        "LAW-67: state+cause+next action in <=2 sentences, no joke"


def test_reasking_at_rest_never_touches_the_build(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(1)))
    told = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda parent, title, text, *a, **k:
                                     told.append(text)))
    d, a, b = _two_faults(win)
    ia = d.features.index(a)
    win.recompute()
    assert d.rollback_to == ia and len(seen) == 1
    before = list(L.entries())
    scar = a.error
    _gear_actions(win)["What's Wrong?"].trigger()
    _gear_actions(win)["What's Wrong?"].trigger()
    assert len(told) == 2, "the answer may be asked TWICE - a door, not an ambush"
    assert len(seen) == 1, "inspecting never re-summons the first-voice modal"
    assert d.rollback_to == ia and a.error == scar, \
        "inspection is PASSIVE: the band, the scar and the build stand still"
    assert list(L.entries()) == before, "and asking never pollutes the log"

# ---- R4: STOP AND REPAIR vs CONTINUE (IGNORE ERROR) - LAW-65 full stop -------
# "SOLIDWORKS can either continue rebuilding (ignoring the error) or
# stop so you can repair" (mechanitec; SW so_messages). R1-R3 cloned
# the STOP half; rung 4 makes it a CHOICE. Continue mode drives the
# rebuild by retry-past-the-fault: every caught fault stamps its scar
# and skips out of the retry, so the pass builds what it CAN - all
# faults scarred, NO modal ambush, a non-modal COUNT speaks (LAW-61(b)
# tier), and errors remain a QUEUE: the pointer aims at the FIRST
# scar. The bar is NOT parked: this pass ran everything it could.


def _toasts():
    return [e for e in L.entries()
            if e.severity == "WARN" and "fail" in e.text.lower()]


def test_stop_and_repair_is_the_default(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(1)))
    assert win.continue_on_error is False, \
        "the vendor default is Stop and Repair - the R1-R3 law stands"
    d, a, b = _two_faults(win)
    ia = d.features.index(a)
    win.recompute()
    assert d.rollback_to == ia and len(seen) == 1, \
        "default mode still parks the bar and summons once"


def test_continue_mode_builds_through_every_fault(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.core.document import PrimitiveFeature as _P
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(1)))
    win.continue_on_error = True
    d, a, b = _two_faults(win)
    tail = d.add(_P(name="Boss", kind="box", op="union",
                    dims={"dx": 3.0, "dy": 3.0, "dz": 2.0}))
    win.recompute()
    assert len(seen) == 0, "Continue mode mounts NO ambush - it IGNORES"
    assert getattr(a, "error", None) and getattr(b, "error", None), \
        "every fault still wears its scar - ignored is not forgiven"
    assert d.failed_feature[1] == "CoilA", \
        "errors remain a QUEUE: the pointer aims at the FIRST, not the "\
        "last catch"
    assert d.rollback_to is None, \
        "continue ran all it could - the bar is NOT parked by law"
    assert d._result is not None and getattr(tail, "error", None) is None, \
        "and the honest tail BUILT: Boss stands on the plate"
    toast = _toasts()
    assert len(toast) == 1 and "2" in toast[0].text, \
        "LAW-61(b): ONE non-modal COUNT speaks the partial failure"
    assert "2" in win.status.currentMessage(), \
        "and the status line echoes the count - no modal, never deaf"


def test_the_continue_walk_clears_the_queue_one_at_a_time(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(1)))
    win.continue_on_error = True
    d, a, b = _two_faults(win)
    win.recompute()
    assert d.failed_feature[1] == "CoilA"
    a.pitch = 6.0
    win.recompute()                            # the healed one RUNS
    assert getattr(a, "error", None) is None, \
        "ran clean - the scar retires (the R1 wipe law rides on)"
    assert d.failed_feature[1] == "CoilB", \
        "the queue advances to the ONE remaining fault"
    toast = _toasts()
    assert len(toast) == 2 and "1" in toast[-1].text \
        and "2" in toast[0].text, \
        "the count spoke twice and the second said 1 - it COUNTS, not "\
        "chants"
    assert len(seen) == 0, "still never a modal across the whole walk"
    b.pitch = 6.0
    win.recompute()
    assert d.failed_feature is None
    assert any("clean again" in e.text for e in L.entries()), \
        "the last fix RAN and only then is recovery news (R1 law, "\
        "shared tail)"


def test_the_gear_toggles_the_choice(win):
    acts = _gear_actions(win)
    assert "Continue rebuilding after errors" in acts, \
        "the CHOICE is NAMED and checkable at the same gear"
    assert acts["Continue rebuilding after errors"].isChecked() is False, \
        "unchecked = Stop and Repair, the law's default"
    acts["Continue rebuilding after errors"].toggle()
    assert win.continue_on_error is True, "the toggle flips the posture"

# ---- R5: THE BADGE IS A BUTTON (LAW-63) ----------------------------------------
# "Clicking any entity in that list ADVANCES YOU DIRECTLY to that
# feature... Never a dead badge." (3dswym/Mechanicitec, fd8 LAW-63).
# The chip BODY keeps selecting in silence (LAW-15 wash); the RED DOT
# is a DOOR: click it and the R3 explanation opens FOR THAT FEATURE -
# select and explain COMPOSE in one click. A badge click never
# touches the marker, and a clean chip has no door to open.


def _dot_x(win, f):
    """The badge dot's live geometry: chips are QRectF(x, 7, 30, h),
    the dot centers at (x + 23, 0) - READ from bar._chips, never
    guessed. grab() forces the paint that fills _chips (the chips are
    PAINT state, not model state)."""
    bar = win.timeline.bar
    bar.grab()
    return next(x for x, w, g in bar._chips if g is f)


def _click(bar, x, y):
    from PySide6.QtCore import QPoint, Qt                      # noqa
    from PySide6.QtTest import QTest                           # noqa
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier,
                     QPoint(int(round(x)), int(round(y))))


def test_the_badge_dot_click_opens_the_explanation(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    told = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda parent, title, text, *a, **k:
                                     told.append(text)))
    d, a, b = _two_faults(win)
    win.recompute()
    bar = win.timeline.bar
    _click(bar, _dot_x(win, a) + 23.0, 3.0)
    qapp.processEvents()
    assert len(told) == 1, "the DOT is a door - clicking it explains"
    assert "CoilA" in told[0] and a.error in told[0], \
        "and the answer is THAT feature, the kernel's words quoted"
    assert bar._sel == d.features.index(a), \
        "the click still SELECTS (LAW-15 wash) - button and selection "\
        "compose"


def test_the_chip_body_still_selects_in_silence(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    told = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda parent, title, text, *a, **k:
                                     told.append(text)))
    d, a, b = _two_faults(win)
    win.recompute()
    bar = win.timeline.bar
    _click(bar, _dot_x(win, a) + 15.0, 20.0)
    qapp.processEvents()
    assert told == [], "the BODY keeps the OLD law - select, never explain"
    assert bar._sel == d.features.index(a)


def test_a_badge_click_never_moves_the_marker(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtCore import QPoint, Qt                      # noqa
    from PySide6.QtTest import QTest                           # noqa
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    d, a, b = _two_faults(win)
    win.recompute()
    rb = d.rollback_to
    bar = win.timeline.bar
    p = QPoint(_dot_x(win, a) + 23, 3)
    QTest.mousePress(bar, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, p)
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, p)
    qapp.processEvents()
    assert d.rollback_to == rb, \
        "the badge is a door, not a handle - the band never moved"
    assert not bar._drag_marker, "the drag arm was never even entered"


def test_a_clean_chip_dot_is_quiet(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.core.document import PrimitiveFeature as _P
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    told = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda parent, title, text, *a, **k:
                                     told.append(text)))
    plate = win.doc.add(_P(name="Quiet", kind="box", op="union",
                           dims={"dx": 2.0, "dy": 2.0, "dz": 2.0}))
    win.recompute()
    bar = win.timeline.bar
    _click(bar, _dot_x(win, plate) + 23.0, 8.0)
    qapp.processEvents()
    assert told == [], "no badge, no door - the dot only exists when "\
        "the chip wears one"
    assert bar._sel == win.doc.features.index(plate), "the click still selects"
