"""M118 — Message Log: the bus, the bridge, the badges, the deep link.

Fusion's log has no way back to the guilty feature [ui_message_log
Finding 6]; Tracer's entries carry a feature pointer from the moment
they are written, and a double-click selects the chip. The bus must
stay Qt-free so the document can speak headless — these tests are the
proof, plus the panel polish on top.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                    # noqa: E402

from tracer.core import logservice as L                       # noqa: E402
from tracer.core.document import Document, PrimitiveFeature   # noqa: E402


@pytest.fixture(autouse=True)
def _clean_bus():
    L.clear()
    yield
    L.clear()


def _failing_doc():
    """A document whose first recompute is guaranteed to fail."""
    d = Document("t")
    d.features.append(PrimitiveFeature(name="cut", kind="box",
                                       op="subtract",
                                       dims={"dx": 5.0, "dy": 5.0,
                                             "dz": 5.0}))
    return d


# ---- the bus (headless) ---------------------------------------------------------
def test_bus_append_counts_and_dump():
    L.error("kernel boom", source="kernel", feature="Fillet 1", pos=3)
    L.info("recompute clean again", source="kernel")
    assert len(L.entries()) == 2
    assert L.counts() == (1, 0)
    dump = L.dump_text()
    assert "ERROR" in dump and "Fillet 1" in dump
    assert "clean again" in dump


def test_consecutive_repeat_dedupes_into_a_count():
    for _ in range(3):
        L.error("same complaint", source="kernel")
    assert len(L.entries()) == 1 and L.entries()[0].count == 3
    assert "×3" in L.dump_text()


def test_different_words_never_merge():
    L.error("one", source="kernel")
    L.warn("two", source="file")
    assert len(L.entries()) == 2
    assert L.counts() == (1, 1)


def test_subscribe_hears_every_write():
    heard = []
    L.subscribe(lambda: heard.append(1))
    L.info("a")
    L.info("a")          # dedupe still notifies (the count moved)
    L.clear()            # and so does clearing
    assert heard == [1, 1, 1]


def test_a_dead_listener_is_reaped_not_painted_into():
    # the M118 hang's root cause was windows the bus kept alive: a
    # GUI object's bound method must NOT be a strong reference
    class Panel:
        def __init__(self):
            self.heard = 0

        def changed(self):
            self.heard += 1

    p = Panel()
    L.subscribe(p.changed)
    L.info("one")
    assert p.heard == 1
    before = len(L._listeners)
    del p
    L.info("two")                           # this write reaps the corpse
    assert len(L._listeners) == before - 1
    L.unsubscribe(Panel.changed)             # unsubscribing a ghost: no-op


def test_unsubscribe_stops_the_tap():
    class Panel:
        def changed(self):
            pass

    n = len(L._listeners)
    p = Panel()
    L.subscribe(p.changed)
    assert len(L._listeners) == n + 1
    L.unsubscribe(p.changed)                # bound methods match by ==
    assert len(L._listeners) == n


def test_ring_cap_keeps_the_newest():
    for i in range(L.CAP + 40):
        L.info(f"entry {i}")
    e = L.entries()
    assert len(e) == L.CAP
    assert e[-1].text == f"entry {L.CAP + 39}"
    assert e[0].text == "entry 40"


# ---- the document bridge (headless) ----------------------------------------------
def test_failure_stamps_the_guilty_feature():
    d = _failing_doc()
    with pytest.raises(ValueError):
        d.recompute()
    where = d.record_failure("first feature 'cut' cannot be a subtract")
    assert where == (0, "cut")
    assert d.failed_feature == (0, "cut")
    assert d.features[0].error == "first feature 'cut' cannot be a " \
                                  "subtract"


def test_a_clean_pass_wipes_every_badge():
    d = _failing_doc()
    with pytest.raises(ValueError):
        d.recompute()
    d.record_failure("boom")
    d.features[0].op = "union"
    assert d.recompute() is not None
    assert d.failed_feature is None
    assert getattr(d.features[0], "error", None) is None


def test_error_badges_never_reach_the_file():
    d = _failing_doc()
    with pytest.raises(ValueError):
        d.recompute()
    d.record_failure("boom")
    blob = d.to_dict()
    assert "error" not in str(blob["features"][0])


# ---- the panel and the deep link (Qt) --------------------------------------------
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
        except Exception as e:                 # CI windows runners: no GL
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


def test_recompute_failure_logs_with_a_name(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    win.doc = _failing_doc()
    win.recompute()
    qapp.processEvents()
    errs = [e for e in L.entries() if e.severity == L.ERROR]
    assert errs and errs[-1].feature == "cut" and errs[-1].feature_pos == 0
    assert "⛔ 1" in win._log_chip.text()
    assert getattr(win.doc.features[0], "error", None)


def test_recovery_is_news(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    win.doc = _failing_doc()
    win.recompute()
    win.doc.features[0].op = "union"
    win.recompute()
    qapp.processEvents()
    assert any("clean again" in e.text for e in L.entries())
    # the chip counts the session's events, like Fusion's log badge:
    # the error is history, recovery does not erase it
    assert "⛔ 1" in win._log_chip.text()


def test_double_click_selects_the_feature(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    win.doc = _failing_doc()
    win.recompute()                            # bridges: log + badge
    win._toggle_message_log()
    qapp.processEvents()
    table = win._log_panel._table
    assert table.rowCount() >= 1
    row = table.rowCount() - 1
    assert table.item(row, 3).data(0x0100) == 0    # Qt.UserRole
    win._log_panel._double(table.item(row, 0))
    qapp.processEvents()
    assert win.timeline.bar._sel == 0
    assert "cut" in win.status.currentMessage()


def test_badge_pixels_actually_paint(win, qapp, monkeypatch):
    # grab() forces the real paintEvent — a theme-key KeyError that
    # hides in the badge painter must fail HERE, not silently (M118
    # caught D["error"] exactly this way, one render too late)
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    win.doc = _failing_doc()
    win.recompute()
    qapp.processEvents()
    pix = win.timeline.bar.grab()
    assert not pix.isNull()


def test_panel_filter_copy_and_save(win, qapp, tmp_path, monkeypatch):
    L.error("red", source="kernel")
    L.warn("yellow", source="file")
    L.info("grey", source="app")
    qapp.processEvents()
    panel = win._log_panel
    panel.refresh()
    assert panel._table.rowCount() == 3
    panel._filter.setCurrentText("Errors")
    assert panel._table.rowCount() == 1
    panel._filter.setCurrentText("All")
    panel._copy_all()
    assert "red" in QApplication.clipboard().text()
    from PySide6.QtWidgets import QFileDialog
    target = str(tmp_path / "log.txt")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (target, "")))
    panel._save_as()
    body = open(target, encoding="utf-8").read()
    assert "ERROR" in body and "yellow" in body


def test_log_hidden_by_default_and_menu_synced(win, qapp):
    assert not win._log_panel.isVisible()
    win._toggle_message_log()
    qapp.processEvents()
    assert win._log_panel.isVisible() and win._log_menu.isChecked()
    win._log_menu.trigger()                    # menu is the truth
    qapp.processEvents()
    assert not win._log_panel.isVisible()
