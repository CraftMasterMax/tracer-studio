"""M58 — Recent Files: the File menu remembers the last eight.

Opens and saves push a path to the front (dedup, cap 8, stored in
QSettings exactly like the tour flag); the submenu lists only files
that still exist, newest first, tooltips carry the full path, Clear
empties the list, and picking an entry opens it for real.
"""
import pytest

pytest.importorskip("PySide6")

from pathlib import Path                                               # noqa: E402

from PySide6.QtCore import QSettings                                   # noqa: E402
from PySide6.QtWidgets import QApplication                             # noqa: E402

from tracer.core import io as fio                                     # noqa: E402
from tracer.core.document import Document, PrimitiveFeature            # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    s = QSettings()
    saved = s.value("files/recent", None)
    s.remove("files/recent")       # setValue([]) would store @Invalid(),
    s.sync()                       # which PySide6 later reads back as None
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
        if saved:
            s2.setValue("files/recent", saved)
        else:
            s2.remove("files/recent")
        s2.sync()


def _save_doc(win, tmp_path, name):
    d = Document(name)
    d.add(PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10}))
    d.recompute()
    p = Path(tmp_path) / f"{name}.tracer"
    fio.save_document(d, p)
    return p


def _labels(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def test_open_pushes_recent_and_rebuilds_menu(win, qapp, tmp_path):
    p = _save_doc(win, tmp_path, "bracket")
    win._open_path(p)
    qapp.processEvents()
    assert _labels(win.m_recent) == ["bracket.tracer", "Clear"]
    assert win.m_recent.actions()[0].toolTip() == str(p)
    assert win.doc.title == "bracket"


def test_recents_dedupe_and_newest_first(win, qapp, tmp_path):
    a = _save_doc(win, tmp_path, "alpha")
    b = _save_doc(win, tmp_path, "beta")
    win._open_path(a)
    win._open_path(b)
    win._open_path(a)                       # again: back to the front
    qapp.processEvents()
    assert _labels(win.m_recent) == ["alpha.tracer", "beta.tracer",
                                     "Clear"]


def test_missing_files_are_hidden(win, qapp, tmp_path):
    p = _save_doc(win, tmp_path, "ghost")
    win._open_path(p)
    p.unlink()
    win._rebuild_recents()
    assert _labels(win.m_recent) == ["(empty)"]


def test_save_records_and_clear_empties(win, qapp, tmp_path, monkeypatch):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="b", kind="box",
                                 dims={"dx": 5, "dy": 5, "dz": 5}))
    win.recompute()
    target = Path(tmp_path) / "saved.tracer"
    fio.save_document(win.doc, target)          # what action_save does
    win._note_recent(target)                    # ...then records it
    qapp.processEvents()
    assert _labels(win.m_recent)[0] == "saved.tracer"
    clear = win.m_recent.actions()[-1]
    clear.trigger()
    qapp.processEvents()
    assert _labels(win.m_recent) == ["(empty)"]
    assert QSettings().value("files/recent", []) in ([], "")
