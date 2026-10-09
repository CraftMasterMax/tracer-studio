"""M45 — Sketch ribbon flyouts: the full constraint palette and a
Dimension button live on the Sketch tab (Fusion's Constrain flyout +
dimension panel), not only in the canvas menu and on keys."""
import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (QApplication, QMenu, QToolButton,          # noqa: E402
                               QWidgetAction)

from tracer.ui.mainwindow import MainWindow                              # noqa: E402
from tracer.ui.renderer import SceneRenderer                             # noqa: E402


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
    w.resize(1100, 700)
    w.show()
    qapp.processEvents()
    w.new_document()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _panel_buttons(w):
    return {b.toolTip(): b for b in w.ribbon.sketch_panel.findChildren(QToolButton)}


CONSTRAINTS = ["Horizontal", "Vertical", "Perpendicular", "Equal",
               "Collinear", "Midpoint", "Symmetry", "Concentric",
               "Tangent", "On-curve", "Angle", "Fix"]


# ---- ribbon presence ----------------------------------------------------------

def test_sketch_tab_has_dimension_and_constrain(win):
    tips = _panel_buttons(win)
    dim = [t for t in tips if t.startswith("Dimension")]
    con = [t for t in tips if t.startswith("Geometric constraints")]
    assert dim and con, list(tips)


def test_flyout_is_a_grid_of_all_twelve_constraints(win):
    btn = next(b for b in win.ribbon.sketch_panel.findChildren(QToolButton)
               if b.toolTip().startswith("Geometric constraints"))
    menu = btn.menu()
    assert menu is not None
    panel = next(a.defaultWidget() for a in menu.actions()
                 if isinstance(a, QWidgetAction))
    labels = [b.text() for b in panel.findChildren(QToolButton)]
    assert len(labels) == 12, labels
    for name in CONSTRAINTS:
        assert any(lbl.startswith(name) for lbl in labels), (name, labels)
    # the shortcut hint rides along, Fusion flyout-style
    assert any(lbl.startswith("Horizontal") and "H" in lbl for lbl in labels)


# ---- dispatch ------------------------------------------------------------------

def test_each_flyout_button_dispatches_its_constraint(win, monkeypatch):
    btn = next(b for b in win.ribbon.sketch_panel.findChildren(QToolButton)
               if b.toolTip().startswith("Geometric constraints"))
    panel = next(a.defaultWidget()
                 for a in btn.menu().actions() if isinstance(a, QWidgetAction))
    fired = []
    acts = {"Horizontal": "act_H", "Vertical": "act_V",
            "Perpendicular": "act_perp", "Equal": "act_equal",
            "Collinear": "act_collinear", "Midpoint": "act_midpoint",
            "Symmetry": "act_symmetry", "Concentric": "act_concentric",
            "Tangent": "act_tangent", "On-curve": "act_on",
            "Angle": "act_angle", "Fix": "act_fix"}
    for name, meth in acts.items():
        monkeypatch.setattr(win.sketch, meth,
                            lambda checked=False, n=name: fired.append(n))
    grid = {b.text().split()[0]: b for b in panel.findChildren(QToolButton)}
    for name in CONSTRAINTS:
        grid[name].click()
    assert fired == CONSTRAINTS, fired


def test_dimension_button_fires_act_dim(win, monkeypatch):
    fired = []
    monkeypatch.setattr(win.sketch, "act_dim",
                        lambda checked=False: fired.append(True))
    btn = next(b for b in win.ribbon.sketch_panel.findChildren(QToolButton)
               if b.toolTip().startswith("Dimension"))
    btn.click()
    assert fired


# ---- group order: tools · modify · dimension · constrain · finish --------------

def test_sketch_group_order_matches_fusion(win):
    """Constrain/Dimension sit after the modify ops and before Finish,
    mirroring Fusion's Draw ▸ Modify ▸ Constraint ▸ Format ordering."""
    btns = [b for b in win.ribbon.sketch_panel.findChildren(QToolButton)
            if b.toolTip()]
    order = [b.toolTip().split(" \u2014 ")[0].split(" \u25be")[0]
             for b in btns]

    def idx(prefix):
        return next(i for i, tip in enumerate(order)
                    if tip.startswith(prefix))
    assert idx("Trim") < idx("Dimension") < idx("Geometric constraints")
    assert idx("Geometric constraints") < idx("Finish")


# ---- proof of life ---------------------------------------------------------------

def test_screenshot_proof(win, qapp):
    win._ribbon_tab(1)                      # Sketch tab
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m45_sketch_ribbon.png")
    btn = next(b for b in win.ribbon.sketch_panel.findChildren(QToolButton)
               if b.toolTip().startswith("Geometric constraints"))
    menu = btn.menu()
    menu.popup(win.mapToGlobal(btn.geometry().bottomLeft()))
    qapp.processEvents()
    assert menu.grab().save(f"{out}/m45_constrain_flyout.png")
    menu.hide()
