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
