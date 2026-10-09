"""M38 — viewport visual identity.

Fusion's corner RGB axis triad (bottom-left, the far axis dimmed), a
left dock wide enough that "6,899.6 mm^3" reads on one line, and
toolbar strokes crisp enough to see at a glance. The triad math is
pure camera (view-basis projection), the ink is pixel-verified offscreen.
"""
import pytest

from tracer.ui.camera import Camera
from tracer.ui.theme import DARK


def _axes(view):
    c = Camera()
    c.set_view(view)
    return {lab: v for lab, v, _ in c.screen_axes()}, \
           {lab: vis for lab, _, vis in c.screen_axes()}


def test_front_view_axes_lie_where_they_should():
    ax, vis = _axes("front")
    assert ax["X"][0] == pytest.approx(1, abs=0.02)      # +X screen-right
    assert ax["X"][1] == pytest.approx(0, abs=0.02)
    assert ax["Z"][1] == pytest.approx(1, abs=0.02)      # +Z screen-up
    assert ax["Y"] == (pytest.approx(0, abs=0.02), pytest.approx(0, abs=0.02))
    assert vis["X"] and vis["Z"]
    assert not vis["Y"]          # +Y leads away from the camera: dimmed


def test_iso_view_spreads_three_axes_and_keeps_z_up():
    ax, vis = _axes("iso")
    assert ax["Z"][1] > 0.8                       # Z mostly up
    assert ax["X"][0] < -0.5 and ax["Y"][0] > 0.5  # X left, Y right
    assert vis["X"] and vis["Y"] and vis["Z"]     # none leads away


def test_axis_pairwise_directions_differ():
    ax, _ = _axes("iso")
    (x0, y0), (y1x, y1y), (z0, z1) = ax["X"], ax["Y"], ax["Z"]
    cross = x0 * y1y - y0 * y1x                   # X vs Y on screen
    assert abs(cross) > 0.3                       # readable spread, no overlap


pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                     # noqa: E402
from PySide6.QtGui import QImage, QPainter                        # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402

from tracer.ui.mainwindow import MainWindow                       # noqa: E402
from tracer.ui.renderer import SceneRenderer                      # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def test_triad_paints_all_three_axis_colors(qapp):
    from tracer.ui.viewport import draw_triad
    img = QImage(420, 320, QImage.Format_RGBA8888)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    draw_triad(p, Camera(), 420, 320, DARK)       # iso camera
    p.end()
    hits = {"red": 0, "green": 0, "blue": 0}
    for x in range(0, 130):
        for y in range(210, 320):
            q = img.pixelColor(x, y)
            if q.alpha() < 60:
                continue
            r, g, b = q.red(), q.green(), q.blue()
            if r > 150 and r > g + 40 and r > b + 40:
                hits["red"] += 1
            elif g > 130 and g > r + 20 and g > b + 20:
                hits["green"] += 1
            elif b > 160 and b > r + 20 and b > g + 20:
                hits["blue"] += 1
    assert all(v > 8 for v in hits.values()), hits


def test_left_dock_stays_readable(win, qapp):
    assert win.rail.minimumWidth() >= 200
    assert win.rail.width() >= 200


def test_toolbar_icons_are_bright():
    from tracer.ui.icons import _COL
    assert _COL.lightness() > 215


def test_screenshot_proof(win, qapp):
    import os
    from tracer.core.document import PrimitiveFeature
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 60, "dy": 40, "dz": 8}))
    win.recompute()
    win._show_page(win.viewport)
    win.action_view("iso")
    win.viewport.refresh(fit=True)
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m38_look.png")
