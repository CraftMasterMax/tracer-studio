"""M111 — data safety: atomic save, on-disk versions, rolling autosave,
conflict guard, Revert to Saved.

Contracts pinned here:
* a crash mid-save leaves the OLD file byte-intact and no .tmp corpse;
* Save IS a version (auto point beside the file, rolling at 25);
  named versions survive the roll forever;
* restoring is non-destructive — file and chain wait for the next Save;
* autosave keeps the last five timestamped mirrors, and a saved doc's
  untitled ghosts die with it;
* a file changed on disk can never be silently overwritten.
"""
import json
import os
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings                               # noqa: E402
from PySide6.QtGui import QAction                                  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog,              # noqa: E402
                               QMessageBox)

from tracer.core import io as fio                                  # noqa: E402
from tracer.core import versions                                   # noqa: E402
from tracer.core.document import Document, PrimitiveFeature        # noqa: E402


def _doc(n: int = 1) -> Document:
    d = Document("v")
    for i in range(n):
        d.features.append(PrimitiveFeature(
            name=f"b{i}", kind="box",
            dims={"dx": 10.0, "dy": 10.0, "dz": 10.0}))
    return d


# ---------------- core: atomic JSON ----------------

def test_write_json_atomic_roundtrip_and_replace(tmp_path):
    p = tmp_path / "a.json"
    fio.write_json_atomic({"x": 1}, p)
    assert fio.load_json(p) == {"x": 1}
    fio.write_json_atomic({"x": 2}, p)
    assert fio.load_json(p) == {"x": 2}
    assert not (tmp_path / "a.json.tmp").exists()


def test_write_json_atomic_gz_is_sniffed_not_asked(tmp_path):
    p = tmp_path / "b.json.gz"
    fio.write_json_atomic({"k": [1, 2, 3]}, p, gz=True)
    assert p.read_bytes()[:2] == b"\x1f\x8b"
    assert fio.load_json(p) == {"k": [1, 2, 3]}


def test_crash_mid_save_leaves_the_old_file(tmp_path, monkeypatch):
    p = tmp_path / "doc.tracer"
    d = _doc(1)
    fio.save_document(d, p)
    before = p.read_bytes()

    def die(*a, **k):
        raise OSError("power cut between tmp and target")

    monkeypatch.setattr(os, "replace", die)
    with pytest.raises(OSError):
        fio.save_document(_doc(2), p)
    assert p.read_bytes() == before                       # old file, intact
    assert not (tmp_path / "doc.tracer.tmp").exists()     # no corpse


def test_save_document_stays_plain_readable_json(tmp_path):
    p = tmp_path / "d.tracer"
    fio.save_document(_doc(1), p)
    raw = p.read_bytes()
    assert raw[:2] != b"\x1f\x8b"           # git-diffable text, no gzip
    assert b'\n "features"' in raw          # the indent=1 layout, kept


# ---------------- core: versions ----------------

def test_versions_append_list_read(tmp_path):
    p = tmp_path / "part.tracer"
    v1 = versions.append(p, _doc(1).to_dict())
    versions.append(p, _doc(2).to_dict(), name="release 1")
    entries = versions.list_versions(p)
    assert [(e.n, e.name) for e in entries] == [(1, None), (2, "release 1")]
    assert len(versions.read(entries[1])["features"]) == 2
    assert v1.path.name.startswith("0001-")


def test_auto_points_roll_named_versions_survive(tmp_path, monkeypatch):
    p = tmp_path / "roll.tracer"
    t = [1_700_000_000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])
    keeper = versions.append(p, _doc(1).to_dict(), name="keeper")
    for _ in range(30):
        t[0] += 1.0
        versions.append(p, _doc(1).to_dict())
    entries = versions.list_versions(p)
    autos = [e for e in entries if e.name is None]
    assert len(autos) == versions.AUTO_KEEP
    assert keeper.path.exists()                       # named is never
    assert autos[0].n > 1                             #   automatic bait


def test_note_name_and_delete(tmp_path):
    p = tmp_path / "meta.tracer"
    v = versions.append(p, _doc(1).to_dict())
    versions.set_note(v, "before the big fillet")
    assert versions.list_versions(p)[0].note == "before the big fillet"
    v2 = versions.name_version(v, "v1 shipped")
    assert not v.path.exists() and v2.path.exists()
    assert versions.list_versions(p)[0].name == "v1 shipped"
    versions.delete(v2)
    assert versions.list_versions(p) == []


def test_sidecar_lives_beside_the_file(tmp_path):
    p = tmp_path / "sub" / "x.tracer"
    p.parent.mkdir()
    versions.append(p, _doc(1).to_dict())
    assert versions.versions_dir(p) == p.parent / ".tracer_versions" / "x"
    assert (p.parent / ".tracer_versions" / "x").is_dir()


# ---------------- UI ----------------

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, tmp_path):
    s = QSettings()
    key = "paths/recovery_dir"
    saved = s.value(key, None)
    s.setValue(key, str(tmp_path / "recovery"))
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
        r.close()
    finally:
        s2 = QSettings()
        if saved is None:
            s2.remove(key)
        else:
            s2.setValue(key, saved)
        s2.sync()


def _brick(win, qapp, name="brick"):
    win.doc.add(PrimitiveFeature(name=name, kind="box",
                                 dims={"dx": 20, "dy": 20, "dz": 20}))
    win.recompute()
    qapp.processEvents()


def test_menu_carries_the_new_verbs(win, qapp):
    texts = [a.text() for a in win.findChildren(QAction)]
    assert "Saved &Versions…" in texts
    assert "Revert to &Saved" in texts


def test_save_records_a_version(win, qapp, tmp_path):
    win.new_document()
    target = tmp_path / "chain.tracer"
    win.file_path = target
    _brick(win, qapp)
    win.action_save()
    assert len(versions.list_versions(target)) == 1
    _brick(win, qapp, name="second")
    win.action_save()
    entries = versions.list_versions(target)
    assert [e.n for e in entries] == [1, 2]
    assert len(versions.read(entries[1])["features"]) == 2


def test_save_failure_keeps_the_unsaved_flag(win, qapp, tmp_path, monkeypatch):
    win.new_document()
    win.file_path = tmp_path / "nowhere" / "x.tracer"      # dir absent
    _brick(win, qapp)
    win._unsaved = True                                    # what edit paths do
    monkeypatch.setattr(QMessageBox, "critical",
                        lambda *a, **k: None)
    win.action_save()
    assert win._unsaved is True           # a failed save never lies (M111)


def test_restore_is_nondestructive(win, qapp, tmp_path):
    win.new_document()
    target = tmp_path / "keep.tracer"
    win.file_path = target
    _brick(win, qapp)
    win.action_save()                                  # v1: one feature
    _brick(win, qapp, name="more")
    win.action_save()                                  # v2: two
    v1 = versions.list_versions(target)[0]
    assert win._load_version(versions.read(v1), False) is True
    assert len(win.doc.features) == 1                  # in memory: v1
    assert win._unsaved is True
    assert win.file_path == target
    assert len(fio.load_document(target).features) == 2     # disk: v2, intact
    assert len(versions.list_versions(target)) == 2         # chain grew never cut


def test_open_as_copy_detaches(win, qapp, tmp_path):
    win.new_document()
    target = tmp_path / "copy.tracer"
    win.file_path = target
    _brick(win, qapp)
    win.action_save()
    _brick(win, qapp, name="later")
    win.action_save()
    v1 = versions.list_versions(target)[0]
    assert win._load_version(versions.read(v1), detach=True) is True
    assert win.file_path is None                 # next Save must pick a path
    assert win._unsaved is True


def test_revert_reopens_the_saved_file(win, qapp, tmp_path, monkeypatch):
    win.new_document()
    target = tmp_path / "rev.tracer"
    win.file_path = target
    _brick(win, qapp)
    win.action_save()
    _brick(win, qapp, name="unsaved addition")
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    win.action_revert_saved()
    assert len(win.doc.features) == 1
    assert win._unsaved is False          # the memory matches the disk again


def test_mtime_guard_never_silent_overwrite(win, qapp, tmp_path, monkeypatch):
    win.new_document()
    target = tmp_path / "theirs.tracer"
    win.file_path = target
    _brick(win, qapp)
    win.action_save()
    target.write_text('{"tampered": true}')           # someone else wrote
    ft = target.stat().st_mtime + 2.0
    os.utime(target, (ft, ft))
    monkeypatch.setattr(win, "_changed_on_disk_prompt", lambda: "cancel")
    win.doc.title = "mine"
    win.action_save()
    assert target.read_text().startswith('{"tampered"')      # untouched
    monkeypatch.setattr(win, "_changed_on_disk_prompt", lambda: "go")
    win.action_save()
    assert "mine" in target.read_text()                      # after consent


def test_prompt_branches_on_the_three_answers(win, qapp, tmp_path,
                                              monkeypatch):
    win.new_document()
    target = tmp_path / "p.tracer"
    win.file_path = target
    _brick(win, qapp)
    win.action_save()
    assert win._changed_on_disk_prompt() == "go"      # fresh save, silent
    ft = target.stat().st_mtime + 2.0
    os.utime(target, (ft, ft))                        # now it moved
    monkeypatch.setattr(QMessageBox, "exec_", lambda self: None)

    def pick(label):
        monkeypatch.setattr(
            QMessageBox, "clickedButton",
            lambda self: next(b for b in self.buttons()
                              if b.text().startswith(label)))

    pick("Cancel")
    assert win._changed_on_disk_prompt() == "cancel"
    pick("Overwrite")
    assert win._changed_on_disk_prompt() == "go"
    pick("Save to a new")
    assert win._changed_on_disk_prompt() == "new"


def test_autosave_rolls_to_the_last_five(win, qapp, monkeypatch):
    win.new_document()
    t = [1_760_000_000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])
    for _ in range(6):
        t[0] += 1.0
        win._autosave()
    files = sorted(win._recovery_dir().glob("untitled.*.autosave.tracer"))
    assert len(files) == 5
    assert win._autosave_file() == files[-1]
    assert json.loads(files[-1].read_text())["doc"]["features"] is not None


def test_save_clears_untitled_ghosts(win, qapp, tmp_path):
    win.new_document()
    _brick(win, qapp)                                 # autosaved as untitled
    assert list(win._recovery_dir().glob("untitled.*.autosave.tracer"))
    win.file_path = tmp_path / "saved.tracer"
    win.action_save()
    assert not list(win._recovery_dir().glob("*.autosave.tracer"))


def test_versions_dialog_lists_and_restores(win, qapp, tmp_path):
    from tracer.ui.versionsdlg import VersionsDialog
    win.new_document()
    target = tmp_path / "dlg.tracer"
    win.file_path = target
    _brick(win, qapp)
    win.action_save()
    _brick(win, qapp, name="second")
    win.action_save()
    dlg = VersionsDialog(target, parent=win, on_restore=win._load_version)
    assert dlg.table.rowCount() == 2
    assert dlg.table.item(0, 0).text() == ""           # elder: no marker
    assert dlg.table.item(1, 0).text() == "\u25cf"     # newest wears the dot
    assert dlg.table.item(0, 2).text().endswith("UTC")
    dlg.table.setCurrentCell(0, 0)
    dlg._load_current()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert len(win.doc.features) == 1                  # the elder, restored


def test_ghost_autosave_older_than_file_is_eaten(win, qapp, tmp_path,
                                                 monkeypatch):
    win.new_document()
    target = tmp_path / "g.tracer"
    win.file_path = target
    _brick(win, qapp)
    win.action_save()
    # an autosave that predates the saved file: not a rescue, a ghost
    old = win._recovery_dir() / "g.20200101T000000-000.autosave.tracer"
    fio.write_json_atomic(dict(path=str(target), saved="2020-01-01T00:00",
                               doc=win.doc.to_dict()), old)
    ts = target.stat().st_mtime
    os.utime(old, (ts - 50, ts - 50))
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or
                        QMessageBox.StandardButton.Discard)
    assert win.maybe_recover() is False
    assert not asked                                   # never even asked
    assert not old.exists()                            # and it's gone


def test_corrupted_file_falls_back_to_its_autosave(win, qapp, tmp_path,
                                                   monkeypatch):
    win.new_document()
    target = tmp_path / "c.tracer"
    win.file_path = target
    _brick(win, qapp)
    win.action_save()
    _brick(win, qapp, name="after-save")               # autosaved under stem
    target.write_text("{ this file is now Toast")
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    assert win._open_path(target) is True
    assert len(win.doc.features) == 2                  # the autosave had both
    assert win._unsaved is True                        # rescue lands unsaved
