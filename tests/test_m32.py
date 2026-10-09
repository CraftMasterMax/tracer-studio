"""M32 — Shell: hollow a solid, opening one face (enclosures, cases).

Kernel recipe (tracer/core/shell.py): the cavity is the body eroded by the
wall thickness (Minkowski difference with a ball — an exact inner inset for
prismatic parts, softly rounded corners for organic ones).  Material removed
is that cavity PLUS a window punched through the opened face: copies of the
cavity lifted along the face normal in t/2 steps, stopping just past THAT
face so a taller feature standing on the deck is never perforated.  A body
op (replaces the accumulated solid), so it saves, suppresses and undoes
exactly like the rest of the timeline.
"""
import json
import math

import numpy as np
import pytest

from tracer.core.document import Document, ShellFeature, PrimitiveFeature
from tracer.core.geometry import Solid
from tracer.core.shell import shell_open


def _plate():
    d = Document("t")
    d.add(PrimitiveFeature(name="base", kind="box",
                           dims={"dx": 40, "dy": 40, "dz": 10}))
    return d


# ---- kernel -----------------------------------------------------------------

def test_open_box_is_exactly_a_walled_tray():
    box = Solid.box(40, 40, 10)
    sh = shell_open(box, 2.0, [((20, 20, 10), (0, 0, 1))])
    # outer 40x40x10 minus an open-top 36x36x8 interior (floor 2 thick)
    assert sh.volume == pytest.approx(16000 - 36 * 36 * 8, abs=1.5)
    assert sh.to_trimesh().is_watertight


def test_open_box_has_floor_walls_and_no_roof():
    box = Solid.box(40, 40, 10)
    sh = shell_open(box, 2.0, [((20, 20, 10), (0, 0, 1))])
    tm = sh.to_trimesh()
    pts = np.array([(1, 20, 5), (39, 20, 5),      # side walls
                    (20, 20, 1),                  # floor
                    (20, 20, 5),                  # interior air
                    (20, 20, 9.9)])               # where the roof was
    inside = tm.contains(pts)
    assert list(inside[[0, 1, 2]]) == [True, True, True]
    assert list(inside[[3, 4]]) == [False, False]


def test_deeper_feature_on_the_deck_survives_the_window():
    # tower standing on the deck: opening the base must not drill the tower
    L = Solid.box(40, 40, 10).union(Solid.box(20, 20, 8).translated((10, 20, 10)))
    sh = shell_open(L, 2.0, [((2, 2, 10), (0, 0, 1))])
    assert sh.to_trimesh().is_watertight
    pts = np.array([(20, 30, 17),   # tower ceiling stays solid
                    (11, 21, 15),   # tower wall stays solid
                    (20, 30, 12.5), # tower interior hollowed
                    (20, 10, 5)])   # base interior hollowed
    assert list(sh.to_trimesh().contains(pts)) == [True, True, False, False]


def test_shell_rejects_impossible_thickness():
    box = Solid.box(40, 40, 10)
    for t in (0.0, -1.0, 6.0):
        with pytest.raises(ValueError):
            shell_open(box, t, [((20, 20, 10), (0, 0, 1))])


def test_cylindrical_cup_rounds_like_a_moulding():
    cup = shell_open(Solid.cylinder(10, 20), 2.0, [((0, 0, 20), (0, 0, 1))])
    want = math.pi * 100 * 20 - math.pi * 64 * 18
    assert cup.volume == pytest.approx(want, rel=0.02)   # corner rounding
    assert cup.to_trimesh().is_watertight


# ---- document feature -------------------------------------------------------

def test_shell_is_a_suppressible_body_op_feature():
    d = _plate()
    f = ShellFeature(name="Shell", thickness=2.0,
                     openings=[((20, 20, 10), (0, 0, 1))])
    d.add(f)
    hollow = d.recompute().volume
    assert hollow == pytest.approx(16000 - 36 * 36 * 8, abs=1.5)
    f.suppressed = True
    assert d.recompute().volume == pytest.approx(16000, abs=1e-6)


def test_shell_as_first_feature_is_rejected():
    d = Document()
    d.features.append(ShellFeature(name="S1"))
    with pytest.raises(ValueError, match="no body to shell"):
        d.recompute()


def test_shell_serialize_roundtrip():
    d = _plate()
    d.add(ShellFeature(name="Shell", thickness=2.5,
                       openings=[((20, 20, 10), (0, 0, 1)),
                                 ((0, 20, 5), (-1, 0, 0))]))
    v = d.recompute().volume
    d2 = Document.from_dict(json.loads(json.dumps(d.to_dict())))
    f = d2.features[1]
    assert isinstance(f, ShellFeature) and f.thickness == 2.5
    assert len(f.openings) == 2
    assert abs(d2.recompute().volume - v) < 1e-6


def test_shell_after_a_hole_keeps_the_hole_in_the_wall():
    from tracer.core.document import HoleFeature
    d = _plate()                          # 40x40x10 plate
    d.add(HoleFeature(name="h", op="subtract", center=(2, 20, 10),
                      normal=(0, 0, -1), radius=1.0, depth=10.0,
                      through=True, cut_length=20.0))   # in the near wall line
    drilled = d.recompute().volume
    d.add(ShellFeature(name="Shell", thickness=2.0,
                       openings=[((20, 20, 10), (0, 0, 1))]))
    shelled = d.recompute()
    assert drilled > shelled.volume
    assert shelled.to_trimesh().is_watertight


# ---- UI ---------------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                      # noqa: E402
from PySide6.QtCore import Qt                                   # noqa: E402

from tracer.ui.mainwindow import MainWindow                     # noqa: E402
from tracer.ui.panels import PropertiesPanel                    # noqa: E402
from tracer.ui.renderer import SceneRenderer                    # noqa: E402


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


def _box(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 40, "dy": 40, "dz": 10}))
    win.recompute()
    qapp.processEvents()


def test_action_shell_needs_a_solid_and_a_face(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: seen.append(a[2])))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(a[2])))
    win.new_document()
    win.action_shell()                       # no solid yet
    assert any("extrude" in s.lower() or "solid" in s.lower() for s in seen)
    _box(win, qapp)
    monkeypatch.setattr(win.viewport, "selected_face", lambda: None)
    seen.clear()
    win.action_shell()                       # no face picked
    assert any("face" in s.lower() for s in seen)
    assert not any(isinstance(f, ShellFeature) for f in win.doc.features)


def test_action_shell_hollows_with_the_dialog(win, qapp, monkeypatch):
    _box(win, qapp)
    monkeypatch.setattr(win.viewport, "selected_face",
                        lambda: dict(point=np.array([20, 20, 10.0]),
                                     normal=np.array([0, 0, 1.0])))
    monkeypatch.setattr("tracer.ui.cmddialog.Shell.getDouble",
                        staticmethod(lambda *a, **k: (2.0, True)))
    win.action_shell()
    qapp.processEvents()
    shells = [f for f in win.doc.features if isinstance(f, ShellFeature)]
    assert len(shells) == 1 and shells[0].thickness == 2.0
    assert win.doc.result.volume == pytest.approx(16000 - 36 * 36 * 8, abs=1.5)
    assert "2 mm walls" in win.status.currentMessage()


def test_action_shell_refuses_impossible_wall_without_adding(
        win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a[2])))
    _box(win, qapp)
    monkeypatch.setattr(win.viewport, "selected_face",
                        lambda: dict(point=np.array([20, 20, 10.0]),
                                     normal=np.array([0, 0, 1.0])))
    monkeypatch.setattr("tracer.ui.cmddialog.Shell.getDouble",
                        staticmethod(lambda *a, **k: (6.0, True)))
    win.action_shell()
    assert warned and not any(isinstance(f, ShellFeature)
                              for f in win.doc.features)


def test_action_shell_twice_is_refused(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    _box(win, qapp)
    monkeypatch.setattr(win.viewport, "selected_face",
                        lambda: dict(point=np.array([20, 20, 10.0]),
                                     normal=np.array([0, 0, 1.0])))
    monkeypatch.setattr("tracer.ui.cmddialog.Shell.getDouble",
                        staticmethod(lambda *a, **k: (2.0, True)))
    win.action_shell()
    win.action_shell()                       # already shelled
    assert len([f for f in win.doc.features
                if isinstance(f, ShellFeature)]) == 1


def test_shell_undo_restores_the_solid(win, qapp, monkeypatch):
    _box(win, qapp)
    before = win.doc.result.volume
    monkeypatch.setattr(win.viewport, "selected_face",
                        lambda: dict(point=np.array([20, 20, 10.0]),
                                     normal=np.array([0, 0, 1.0])))
    monkeypatch.setattr("tracer.ui.cmddialog.Shell.getDouble",
                        staticmethod(lambda *a, **k: (2.0, True)))
    win.action_shell()
    assert win.doc.result.volume < before
    win.undo()
    assert win.doc.result.volume == pytest.approx(before, abs=1e-6)


def test_properties_panel_describes_shell(qapp):
    p = PropertiesPanel()
    p.show_feature(ShellFeature(name="s", thickness=3.0,
                                openings=[((0, 0, 0), (0, 0, 1))]))
    text = p._body.text()
    assert "3 mm" in text and "faces removed: 1" in text


def test_screenshot_proof(win, qapp, monkeypatch):
    import os
    _box(win, qapp)
    monkeypatch.setattr(win.viewport, "selected_face",
                        lambda: dict(point=np.array([20, 20, 10.0]),
                                     normal=np.array([0, 0, 1.0])))
    monkeypatch.setattr("tracer.ui.cmddialog.Shell.getDouble",
                        staticmethod(lambda *a, **k: (2.0, True)))
    win.action_shell()
    qapp.processEvents()
    win.action_view("iso")
    win.viewport.refresh(fit=True)
    qapp.processEvents()
    out = "/tmp/opencode/shots"
    os.makedirs(out, exist_ok=True)
    assert win.grab().save(f"{out}/m32_shell.png")
