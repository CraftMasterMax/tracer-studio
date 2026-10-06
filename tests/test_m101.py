"""M101 — true hidden-line removal: depth decides, not vibes.

M97's rule was orientation-only: dash edges whose both faces flee the
viewer, clipped against the silhouette's 2D region. Fine for convex
blocks — hopeless for anything concave, because "facing the viewer"
is not the same as "the viewer can see it": a milled pocket's back
wall faces the camera through the plate's intact front wall, and the
orientation rule happily drew it SOLID (over-drawing the cavity)
while a bore's far rim, legitimately seen THROUGH an open hole, had
no rule that could call it visible.

Now there is one classifier (project_edges) and a real depth test:
every candidate edge — turn, crease, back crease, grazing-and-back
creases like a pocket floor meeting a fleeing wall — is sampled at
its midpoint and asked: does any FRONT-FACING triangle strictly
cover this point with nearer depth? Covered, it dashes (a bore wall
behind solid metal, a pocket's back wall); uncovered, it draws solid
(a far rim through a hole). Boundary-touching cover is decided by
DEPTH, not by strictness: a surface's own edge interpolates to the
edge's own depth and loses the comparison, while a genuinely nearer
silhouette crossing wins — the symmetric iso case (a far corner's ray
grazing a near crease) that strict tests missed. Coincident segments
merge, visible winning, so rims that repeat rims draw one line.

The pocket is the proof: 20×8×6 milled into a 40×20×10 plate from
the top, front wall intact. From the front the back wall dashes
whole — floor line at z=4, two corner lines, and the rim riding the
top outline; from above, everything is visible and nothing dashes.
And a through bore's walls now dash in elevation exactly as any
drawing standard demands (M93's pin migrated to the truth).
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402

from tracer.core import drawing                              # noqa: E402
from tracer.core.document import PrimitiveFeature            # noqa: E402


def _pocket():
    plate = PrimitiveFeature(name="p", kind="box",
                             dims={"dx": 40.0, "dy": 20.0, "dz": 10.0})
    cut = PrimitiveFeature(name="c", kind="box",
                           dims={"dx": 20.0, "dy": 8.0, "dz": 6.0},
                           placement=(10.0, 6.0, 4.0))
    return plate.build().subtract(cut.build())


def _plate():
    box = PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 40.0, "dy": 20.0, "dz": 5.0})
    cyl = PrimitiveFeature(name="c", kind="cylinder",
                           dims={"radius": 4.0, "height": 5.0},
                           placement=(20.0, 10.0, 0.0))
    return box.build().subtract(cyl.build())


# ---------------------------------------------------------------- core

def test_pocket_hides_its_back_wall_in_front():
    hidden = drawing.project_hidden(_pocket(), view="front")
    segs = [(c[i], c[i + 1]) for c in hidden for i in range(len(c) - 1)]
    assert len(segs) == 4         # the occluded back wall, dashed whole
    interior = [s for s in segs
                if not all(abs(p[1] - 10.0) < 1e-6 for p in s)]
    # strip the rim segment that rides the plate's top outline: what
    # remains is the classic hidden trio — floor line + two corners
    assert len(interior) == 3
    horiz = [(a, b) for a, b in interior if abs(a[1] - b[1]) < 1e-6]
    vert = [(a, b) for a, b in interior if abs(a[0] - b[0]) < 1e-6]
    assert len(horiz) == 1 and len(vert) == 2
    (a, b) = horiz[0]
    assert a[1] == pytest.approx(4.0)     # the FLOOR's level
    assert sorted((a[0], b[0])) == pytest.approx((10.0, 30.0))
    assert {round(a[0]) for a, _ in vert} == {10.0, 30.0}


def test_pocket_top_view_stays_clean():
    # seen from above the pocket is OPEN — nothing there hides
    assert drawing.project_hidden(_pocket(), view="top") == []


def test_through_bore_front_view_dashes_its_walls():
    # the wall faces the camera but the front face is intact metal:
    # a real drawing dashes the bore, it does not draw it solid
    assert drawing.project_hidden(_plate(), view="front")


def test_bore_view_from_above_still_hides_nothing():
    # looking straight down an open hole: nothing is occluded
    assert drawing.project_hidden(_plate(), view="top") == []


def test_sphere_still_refuses_the_wireframe():
    sph = PrimitiveFeature(name="s", kind="sphere",
                           dims={"radius": 10.0},
                           placement=(0.0, 0.0, 10.0)).build()
    for v in ("front", "iso", "top"):
        hidden = drawing.project_hidden(sph, view=v)
        assert sum(len(c) - 1 for c in hidden) <= 1


def test_iso_box_still_exactly_three():
    box = PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 40.0, "dy": 20.0,
                                 "dz": 10.0}).build()
    hidden = drawing.project_hidden(box, view="iso")
    assert sum(len(c) - 1 for c in hidden) == 3


# ------------------------------------------------------------------ UI

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
        w._discard_guard = lambda: True
        w.close()
        r.ctx.release()
    except Exception:
        raise


def _pocket_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Plate", kind="box",
        dims={"dx": 40.0, "dy": 20.0, "dz": 10.0}))
    win.doc.features.append(PrimitiveFeature(
        name="Pocket", kind="box",
        dims={"dx": 20.0, "dy": 8.0, "dz": 6.0},
        placement=(10.0, 6.0, 4.0), op="subtract"))
    win.recompute()
    win.action_new_drawing()
    qapp.processEvents()
    return win.drawing


def test_canvas_dashes_the_pocket_floor(win, qapp):
    cv = _pocket_sheet(win, qapp)
    hid = cv.hidden_views()
    # the occluded back-wall rectangle dashes in BOTH elevations
    assert sum(len(c) - 1 for c in hid["front"]) == 4
    assert sum(len(c) - 1 for c in hid["right"]) == 4
    assert hid["top"] == []              # open from above: nothing hides


def test_dxf_carries_the_pocket_hidden_ink(win, qapp, tmp_path):
    cv = _pocket_sheet(win, qapp)
    n_vis = sum(len(cs) for cs in cv.layout().values())
    n_hid = sum(len(cs) for cs in cv.hidden_views().values())
    assert n_hid >= 1
    out = str(tmp_path / "pocket.dxf")
    win.export_drawing(out)
    from tracer.core import import2d
    ops = import2d.read(out)
    polys = [o for o in ops if o[0] in ("poly", "line")]
    # every visible chain AND every hidden chain reaches the paper —
    # not one more, not one less
    assert len(polys) == n_vis + n_hid
