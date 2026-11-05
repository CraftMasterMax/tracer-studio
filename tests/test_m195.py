"""M195 rung 1 - CREATE COPY GROWS A BODY.

SLD-USE-MOVE-COPY, verbatim: "Optional: Check the box next to Create
Copy to create a copy of the selected object instead of moving the
original." + "The new body is not linked to the original body. When
you modify the original body or the new body, the changes are unique
to that body."  Move/Copy reference (GUID-FFD25CD3): "Create Copy
Check the box to create a copy the selection and move it."

Tracer's copy predates bodies (M53's Ctrl-drag filed a MoveFeature
with copy=True - an in-body UNION). The vendor's sentence speaks a
DIFFERENT shape: the twin is a NEW BODY, the original "instead of
moving" never shifts, and the copy's history is its OWN. M104's
bodies finally make that cloneable:

- The copy door files a snapshot stream: the source body's CURRENT
  solid as a mesh, riding in its own browser row at the offset (the
  ImportedFeature mouth - the same first-class-history carrier STEP
  imports ride).
- The original NEVER MOVES: its solid sits where it sat, byte for
  byte (the vendor's "instead of moving the original").
- The twin is its own stream: M104's own law makes the new body
  ACTIVE (Fusion selects what it just made), and the copy's feature
  carries its own body tag.
- Legacy fidelity: a file that ALREADY carries a copy MoveFeature
  replays the union exactly as M53 shipped it - the kernel's copy
  flag did not move, only the door did.
- Undo walks the row back: the browser shrinks to one body again.
- The plain MOVE branch is untouched: no Ctrl, still a Move feature.
"""
import pytest

pytest.importorskip("PySide6")

import numpy as np                                                # noqa
from PySide6.QtWidgets import QApplication                        # noqa

from tracer.core.document import (Document, ImportedFeature,      # noqa
                                  MoveFeature, PrimitiveFeature)
from tracer.ui.mainwindow import MainWindow                       # noqa
from tracer.ui.renderer import SceneRenderer                      # noqa


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    try:
        r = SceneRenderer()
    except Exception as e:                     # CI windows runners: no GL
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _block(name="copy"):
    d = Document(name)
    d.add(PrimitiveFeature(name="block", kind="box",
                           dims={"dx": 20, "dy": 20, "dz": 20}))
    d.recompute()
    return d


# ---- the door: a NEW browser body, the original unmoved -------------------
def test_copy_door_grows_a_new_body():
    """The vendor's whole sentence at the data mouth: a second body
    appears, the copy rides the offset, and the original never moved
    - "instead of moving the original"."""
    d = _block()
    assert [b["name"] for b in d.body_list()] == ["Body 1"]
    lo0 = d.body_solids()["Body 1"].bounding_box[0].copy()
    b = d.copy_body_moved((50.0, 0.0, 0.0))
    d.recompute()
    assert b["name"] == "Body 2"
    assert [x["name"] for x in d.body_list()] == ["Body 1", "Body 2"]
    bs = d.body_solids()
    assert np.allclose(bs["Body 1"].bounding_box[0], lo0)   # never moved
    assert np.allclose(bs["Body 2"].bounding_box[0], (50.0, 0.0, 0.0))
    assert bs["Body 2"].volume == pytest.approx(bs["Body 1"].volume,
                                                rel=1e-6)   # an equal twin
    assert d.result.volume == pytest.approx(2 * bs["Body 1"].volume,
                                            rel=1e-3)       # the PART shows both


def test_copy_is_its_own_stream():
    """M104's bookkeeping: the snapshot feature rides the NEW body's
    stream, and - Fusion selecting what it made - the copy becomes the
    ACTIVE body for the next gesture."""
    d = _block()
    d.copy_body_moved((0.0, 40.0, 0.0))
    assert d.active_body == "Body 2"
    feat = d.features[-1]
    assert isinstance(feat, ImportedFeature)
    assert feat.name == "Copy"
    assert getattr(feat, "body", None) == "Body 2"          # own stream,
    assert d.features[0].body != "Body 2"                   #  not a graft


def test_the_move_half_still_files_a_move_feature():
    """HONESTY gate: only the COPY branch moved. No Ctrl, same verb:
    the release still files the M53 Move feature and the body slides
    as it always did."""
    d = _block()
    d.add(MoveFeature(name="Move", vec=(10.0, -5.0, 2.0)))
    s = d.recompute()
    assert [b["name"] for b in d.body_list()] == ["Body 1"]  # still one body
    assert np.allclose(s.bounding_box[0], (10.0, -5.0, 2.0))


def test_legacy_copy_feature_still_replays_the_union():
    """File compatibility is the other half of the law: a document
    saved in the M53 era carries a copy MoveFeature and MUST keep
    recomputing the in-body union - the kernel's copy flag never
    moved, only the door did."""
    d = _block("legacy")
    d.add(MoveFeature(name="Copy", vec=(25.0, 0.0, 0.0), copy=True))
    d.recompute()
    d2 = Document.from_dict(d.to_dict())
    s = d2.recompute()
    assert len(d2.body_list()) == 1                          # joined, not born
    assert s.volume == pytest.approx(2 * 8000.0, rel=1e-3)   # the M53 union


# ---- the UI door: the release payload grows (and undo shrinks) the row ----
def _block_win(win, qapp):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="cube", kind="box",
                                 dims={"dx": 20, "dy": 20, "dz": 20}))
    win.recompute()
    win.viewport.refresh(fit=True)
    qapp.processEvents()


def test_copy_release_and_undo_walk_the_body_row(win, qapp):
    """The commit door itself (the payload the triad's release
    answers): copy=True GROWS the browser - and undo takes the row
    back, the whole birth reversible like every other mutation."""
    _block_win(win, qapp)
    v0 = win.doc.result.volume
    win._on_move_drag({"offset": np.array([40.0, 0.0, 0.0]),
                       "copy": True})
    qapp.processEvents()
    assert [b["name"] for b in win.doc.body_list()] == ["Body 1", "Body 2"]
    assert win.doc.result.volume == pytest.approx(2 * v0, rel=1e-3)
    assert "stands on its own" in win.status.currentMessage()
    assert not [f for f in win.doc.features if isinstance(f, MoveFeature)]
    win.undo()
    qapp.processEvents()
    assert [b["name"] for b in win.doc.body_list()] == ["Body 1"]
    assert win.doc.result.volume == pytest.approx(v0, rel=1e-3)
