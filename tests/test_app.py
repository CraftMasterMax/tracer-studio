"""GUI smoke tests under Qt offscreen platform: the app shell builds,
the tree populates, the viewport (QPainter blit path, no QOpenGLWidget)
paints real pixels, and actions behave."""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from forma.ui.mainwindow import MainWindow, demo_document  # noqa: E402
from forma.ui.renderer import SceneRenderer  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.show()
    qapp.processEvents()
    yield w
    w.close()


def test_shell_builds(win):
    root = win.rail.tree.topLevelItem(0)
    names = [root.child(i).text(0) for i in range(root.childCount())]
    assert len(names) == 3
    assert any("plate" in n for n in names)
    assert "volume" in win.status.currentMessage()


def test_viewport_blits_pixels(win):
    img = win.viewport.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    buf = np.frombuffer(img.constBits(), np.uint8, img.sizeInBytes()
                        ).reshape(img.height(), img.width(), 4)
    g = buf[:, :, 0].astype(int)
    assert g.max() - g.min() > 30, "viewport painted flat — nothing shown"


def test_recompute_after_edit(win):
    v0 = win.doc.result.volume
    win.doc.add_cylinder("extra boss", radius=4, height=5, center=(55, 35))
    win.recompute()
    assert win.doc.result.volume > v0
    root = win.rail.tree.topLevelItem(0)
    assert root.childCount() == 4


def test_properties_panel_updates(win):
    root = win.rail.tree.topLevelItem(0)
    win.rail.tree.setCurrentItem(root.child(1))
    assert "boss" in win.rail.props._body.text()


def test_save_open_roundtrip(win, qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    save_to = tmp_path / "bracket.forma"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(save_to), "")))
    win.action_save()
    assert save_to.exists()
    assert "Saved" in win.status.currentMessage()

    # mutate, then reopen and verify we get the saved state back
    win.doc.add_cylinder("oops", radius=1, height=1, center=(0, 0))
    win.recompute()
    assert win.rail.tree.topLevelItem(0).childCount() == 4
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(save_to), "")))
    win.action_open()
    assert win.rail.tree.topLevelItem(0).childCount() == 3
    assert win.doc.result.volume == pytest.approx(
        demo_document().recompute().volume, rel=1e-9)
