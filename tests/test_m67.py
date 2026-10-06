"""M67 — Autosave & crash recovery: a crash loses one edit, not a day.

Every successful recompute mirrors the document into a recovery folder
(QSettings-relocatable — tests never touch the real one); save, open,
new and a clean close clear it.  maybe_recover(), called by the app
entry point (never by the constructor, so headless tests stay silent),
offers the newest autosave: Restore reopens the real document with the
original path and dirty flag; Discard deletes it for good.
"""
import json

import pytest

pytest.importorskip("PySide6")

from pathlib import Path                                                # noqa: E402

from PySide6.QtCore import QSettings                                    # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox                 # noqa: E402

from tracer.core.document import PrimitiveFeature                       # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, tmp_path):
    s = QSettings()
    key = "paths/recovery_dir"
    saved = s.value(key, None)
    d = tmp_path / "recovery"
    s.setValue(key, str(d))
    s.sync()
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
        r.ctx.release()
    finally:
        s2 = QSettings()
        if saved is None:
            s2.remove(key)
        else:
            s2.setValue(key, saved)
        s2.sync()


def _block(win, qapp):
    win.new_document()
    win._clear_autosave()
    win.doc.add(PrimitiveFeature(name="block", kind="box",
                                 dims={"dx": 20, "dy": 20, "dz": 20}))
    win.recompute()
    qapp.processEvents()


def test_recompute_writes_the_autosave(win, qapp):
    _block(win, qapp)
    p = win._autosave_file()
    assert p.exists()
    payload = json.loads(p.read_text())
    feats = payload["doc"]["features"]
    assert len(feats) == 1 and feats[0]["name"] == "block"


def test_save_clears_the_autosave(win, qapp, tmp_path):
    _block(win, qapp)
    assert win._autosave_file().exists()
    target = tmp_path / "saved.tracer"
    from tracer.core import io as fio
    fio.save_document(win.doc, target)
    win.file_path = target
    win._unsaved = False
    win._clear_autosave()                      # what action_save does last
    assert not win._autosave_file().exists()


def test_maybe_recover_restores(win, qapp, monkeypatch):
    _block(win, qapp)
    win.doc.title = "workpiece"
    win._autosave()                              # mirror the new title too
    payload_path = win._autosave_file()
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Open)
    win.new_document()                         # fresh start, like a reboot
    assert win.doc.features == []
    assert win.maybe_recover() is True
    assert win.doc.title == "workpiece"
    assert len(win.doc.features) == 1
    assert win._unsaved is True
    assert "Recovered" in win.status.currentMessage()


def test_maybe_recover_discard_deletes(win, qapp, monkeypatch):
    _block(win, qapp)
    p = win._autosave_file()
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Discard)
    win.new_document()
    assert win.maybe_recover() is False
    assert not p.exists()
    assert win.doc.features == []


def test_no_autosave_means_silence(win, qapp):
    win.new_document()
    win._clear_autosave()
    called = []
    from PySide6.QtWidgets import QMessageBox as MB
    orig = MB.question
    MB.question = staticmethod(lambda *a, **k: called.append(1))
    try:
        assert win.maybe_recover() is False
    finally:
        MB.question = staticmethod(orig)
    assert not called


def test_empty_recents_list_never_crashes_a_restart(win, qapp):
    # PySide6 stores [] as "@Invalid()" and reads it back as None even
    # with a [] default — M58's Clear did exactly that and haunted the
    # next launch.  _recents must shrug it off.
    s = QSettings()
    key = "files/recent"
    saved = s.value(key, None)
    try:
        s.setValue(key, [])           # the exact poison pill
        s.sync()
        assert win._recents() == []
        win._rebuild_recents()                # and the menu survives it
        assert win.m_recent.actions()[0].text() == "(empty)"
    finally:
        if saved:
            s.setValue(key, saved)
        else:
            s.remove(key)
        s.sync()
        win._rebuild_recents()
