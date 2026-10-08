"""M147 — sheet metal SM2: the flat pattern as PAPER, not just
numbers.

The reprobe contract (research/flat_pattern_outline.md) EXECUTED
the outline law against our SM1 kernel and killed the romantic
version: the developed OUTLINE of a straight-fold tree is EXACTLY
ONE RECTANGLE L x W (L = flat_length — stagger collapses because
every leg is full-width), and the bend zones are keyed BA-slots
along it, each marked by one centre line at its middle. The
annulus the mesh hints at is the ORACLE, never the ink:
theta * r_c = BA is an identity (r_c = ri + K*t), tangency is
C1-exact at every offset radius — but the arc BOUNDARIES of a
BA-developed band are ri+(K-1/2)t and ri+(K+1/2)t, equal to the
true ri/ro ONLY at K=0.5. Arcing the plan view would silently
assert K=0.5 while the dialog says 0.44; two wrongs in one stroke.

Goldens here are RE-DERIVED from the formulas, not copied from
the probe's console (which drifted ~1e-5 in the last digit):
BA = theta_rad * (ri + K*t). Tree order rides legkeys: two bands
naming a shared leg AGREE (SM1's key law), and the walk from the
lowest-sorted leaf is deterministic. Refusals ride unfold_flat's
ONE choke (bendless, seam, mixed t); straight-fold (all axes
parallel) is SM2's own named law — a cross-fold is SM3's
seam-and-relief conversation, and a sheet that BRANCHES at a leg
is not one strip.
"""
import math

import numpy as np
import pytest

from tracer.core import sheetmetal
from tracer.core.document import Document
from tracer.core.geometry import Solid

T, RI, RO = 2.0, 3.0, 5.0
K = 0.44
BA = math.pi / 2 * (RI + K * T)          # the LAW, re-derived


def _arc(r, cx, cy, a0, a1, n=15):
    th = np.linspace(a0, a1, n + 1)
    return np.column_stack([cx + r * np.cos(th), cy + r * np.sin(th)])


def bent_plate():
    """SM1's part: legs 60/40 tangent-to-end, t=2 ri=3, width 40."""
    pts = np.vstack([[[RO, -60.0]], _arc(RO, 0, 0, 0, math.pi / 2),
                     [[-40.0, RO]], [[-40.0, RI]],
                     _arc(RI, 0, 0, math.pi / 2, 0),
                     [[RI, -60.0]]])
    return Solid.extrude(pts, height=40.0)


def c_bracket():
    """The contract's 5-fold tree: legs 50/30/40, two 90 deg folds
    (fold2 centre (-30,8): leg2's faces swap inner/outer there),
    sheet width 25. Executed keys: band0
    [(0,1.5,2.5),(1,1.5,2.5)], band1 [(0,-17.5,-16.5),(1,1.5,2.5)]
    — the shared leg names the middle leg from both sides."""
    outer = np.vstack([[[RO, -50.0], [RO, 0.0]],
                       _arc(RO, 0, 0, 0, math.pi / 2),
                       [[-30.0, RO]],
                       _arc(RI, -30.0, 8.0, -math.pi / 2, -math.pi),
                       [[-33.0, 48.0]]])
    back = np.vstack([[[-35.0, 48.0], [-35.0, 8.0]],
                      _arc(RO, -30.0, 8.0, math.pi, 1.5 * math.pi),
                      [[0.0, RI]],
                      _arc(RI, 0, 0, math.pi / 2, 0),
                      [[RI, -50.0]]])
    return Solid.extrude(np.vstack([outer, back]), height=25.0)


def _rounded_square(half, r, n=6):
    c = half - r
    return np.vstack([_arc(r, c, -c, -math.pi / 2, 0, n),
                      _arc(r, c, c, 0, math.pi / 2, n),
                      _arc(r, -c, c, math.pi / 2, math.pi, n),
                      _arc(r, -c, -c, math.pi, 3 * math.pi / 2, n)])


def closed_tube():
    """SM1's own seam part, verbatim: four walls and four corner
    bands around a CYCLE — the same voice that made SM1 demand a
    seam must be SM2's voice too (one choke, one law)."""
    outer = _rounded_square(20.0, RO)
    inner = _rounded_square(18.0, RI)
    return Solid.extrude(outer, holes=[inner], height=30.0)


def block():
    return Solid.extrude(np.array([[0.0, 0.0], [30.0, 0.0],
                                   [30.0, 10.0], [0.0, 10.0]]),
                         height=5.0)


# ---- G1: tree order — the legkey fix makes extents addressable --
def test_tree_order_makes_extents_keyed_not_anonymous():
    u = sheetmetal.unfold_flat(bent_plate(), K=K)
    assert {f["key"] for f in u["flanges"]} == set(
        u["bands"][0]["legkeys"])
    f = sheetmetal.flat_outline(bent_plate(), K=K)
    kinds = [r["kind"] for r in f["runs"]]
    assert kinds == ["leg", "band", "leg"]          # sorted-leaf
    assert f["runs"][0]["extent"] == pytest.approx(60.0, abs=1e-3)
    assert f["runs"][2]["extent"] == pytest.approx(40.0, abs=1e-3)
    assert f["runs"][1]["ba"] == pytest.approx(BA, abs=1e-4)  # the
    # kernel's BA rides the MEASURED angle (SM1's own pins: angle
    # 1e-4, totals 1e-3); only the IDENTITIES below are exact.


# ---- G2: closure + the rectangle law ------------------------------
def test_outline_is_one_closed_rectangle_with_shoelace_area():
    f = sheetmetal.flat_outline(bent_plate(), K=K)
    pts = f["outline"]
    assert len(pts) == 5 and pts[0] == pts[-1]
    assert np.hypot(pts[0][0] - pts[-1][0],
                    pts[0][1] - pts[-1][1]) < 1e-12
    L = 100.0 + BA                                   # re-derived
    W = 40.0
    assert f["flat_length"] == pytest.approx(L, abs=1e-3)
    assert f["width"] == pytest.approx(W, abs=1e-3)
    sh = 0.5 * sum(x0 * y1 - x1 * y0
                   for (x0, y0), (x1, y1) in zip(pts, pts[1:]))
    assert abs(sh) == pytest.approx(W * L, abs=1e-2)  # nominal L
    # rides the measured angle; the exact accounting is below
    assert abs(sh) == pytest.approx(
        sum(r["extent"] for r in f["runs"] if r["kind"] == "leg") * W
        + sum(r["ba"] for r in f["runs"]
              if r["kind"] == "band") * W, abs=1e-6)


# ---- G3: bend lines and band slots --------------------------------
def test_bend_lines_sit_at_the_band_middles():
    f = sheetmetal.flat_outline(bent_plate(), K=K)
    assert len(f["bend_lines"]) == 1
    bl = f["bend_lines"][0]
    assert bl["x"] == pytest.approx(60.0 + BA / 2, abs=1e-4)
    assert bl["y0"] == 0.0
    assert bl["y1"] == pytest.approx(f["width"], abs=1e-3)
    assert f["runs"][0]["x0"] == 0.0
    assert f["runs"][1]["x0"] == pytest.approx(60.0, abs=1e-3)
    assert f["runs"][2]["x0"] == pytest.approx(60.0 + BA, abs=1e-4)


# ---- G4: THE ANNULUS ORACLE — identity math, K=0.5 closure --------
def test_annulus_oracle_is_an_identity_and_K_half_closes_on_mesh():
    f = sheetmetal.flat_outline(bent_plate(), K=K)
    b = f["runs"][1]
    # Every identity here rides the KERNEL's own numbers (the
    # measured sheet is t = 1.999995, the measured ri 2.999997) —
    # never the nominal ones it was extruded from.
    tm = f["thickness"]
    theta = math.radians(b["angle"])
    r_c = b["ba"] / theta
    assert r_c == pytest.approx(b["ri"] + K * tm, abs=1e-9)
    assert theta * r_c - b["ba"] == pytest.approx(0.0, abs=1e-12)
    rin, rout = r_c - tm / 2, r_c + tm / 2
    assert rin == pytest.approx(b["ri"] + (K - 0.5) * tm, abs=1e-9)
    assert rout == pytest.approx(b["ri"] + (K + 0.5) * tm, abs=1e-9)
    assert rin != pytest.approx(b["ri"], abs=1e-3)    # the mismatch:
    annulus = theta / 2 * (rout ** 2 - rin ** 2)      # boundaries
    assert annulus == pytest.approx(b["ba"] * tm, abs=1e-9)  # != ri/ro
    g = sheetmetal.flat_outline(bent_plate(), K=0.5)
    assert g["flat_length"] == pytest.approx(
        100.0 + math.pi / 2 * 4, abs=1e-3)           # mesh oracle


# ---- G5: multi-band tree — shared legs, two BA-slots ---------------
def test_c_bracket_walks_the_tree_with_shared_legs():
    f = sheetmetal.flat_outline(c_bracket(), K=K)
    kinds = [r["kind"] for r in f["runs"]]
    assert kinds == ["leg", "band", "leg", "band", "leg"]
    keys0 = set(f["bands"][0]["legkeys"])
    keys1 = set(f["bands"][1]["legkeys"])
    assert len(keys0 & keys1) == 1                   # shared middle
    assert f["flat_length"] == pytest.approx(120.0 + 2 * BA,
                                             abs=1e-3)
    assert f["width"] == pytest.approx(25.0, abs=1e-3)
    xs = [r["x0"] for r in f["runs"] if r["kind"] == "band"]
    assert xs == pytest.approx([40.0, 40.0 + BA + 30.0], abs=1e-3)


# ---- G6: refusals ride SM1's one choke, in its voices --------------
def test_flat_outline_refusals_share_the_unfold_voices():
    with pytest.raises(sheetmetal.SheetMetalError) as e:
        sheetmetal.flat_outline(closed_tube(), K=K)
    assert "seam" in str(e.value).lower()
    with pytest.raises(sheetmetal.SheetMetalError) as e:
        sheetmetal.flat_outline(block(), K=K)
    assert "bend" in str(e.value).lower()


def test_cross_folds_and_branching_refuse_by_name():
    with pytest.raises(sheetmetal.SheetMetalError) as e:
        sheetmetal._straight_fold([{"axis": (0.0, 0.0, 1.0)},
                                   {"axis": (1.0, 0.0, 0.0)}])
    assert "straight" in str(e.value).lower()
    assert sheetmetal._straight_fold([{"axis": (0.0, 0.0, 1.0)},
                                      {"axis": (0.0, 0.0, -1.0)}]
                                     ) is None      # antiparallel
    #  axes ARE parallel (|dot| rules, not sign)


# ---- G7: the rail law — the slab projects to EXACTLY one chain ----
def test_flat_slab_projects_to_exactly_one_closed_chain():
    from tracer.core.drawing import project_edges
    f = sheetmetal.flat_outline(bent_plate(), K=K)
    slab = Solid.extrude(np.asarray(f["outline"]), height=0.01)
    chains = project_edges(slab, view="top")
    vis = [c for c in chains["visible"] if len(c) > 2
           and np.allclose(c[0], c[-1])]
    assert len(vis) == 1 and len(vis[0]) == 5
    assert chains["hidden"] == []


# ---- UI: the rails (contract §4): hidden body, Flat view, ink ------
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def win(qapp):
    from tracer.ui.renderer import SceneRenderer
    from tracer.ui.mainwindow import MainWindow
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL available: {e}")
    w = MainWindow(renderer=r)
    w.resize(1200, 800)
    w.show()
    qapp.processEvents()
    w.new_document()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    qapp.processEvents()


def _sheet_in(win):
    """The sheet as a BODY through the document's own import rail —
    not a test-only channel."""
    from tracer.core.document import ImportedFeature
    t = bent_plate().to_trimesh()
    d = win.doc
    d.add_body("Sheet")
    d.add(ImportedFeature(name="sheet", verts=t.vertices.tolist(),
                          faces=t.faces.astype(int).tolist()))
    d.recompute()
    return d


def _say_yes(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.ui import cmddialog
    monkeypatch.setattr(
        cmddialog, "ask",
        lambda parent, title, fields, remember_key=None: {
            f["key"]: (0.44 if f["key"] == "K" else None)
            for f in fields})
    monkeypatch.setattr(QMessageBox, "question",
                        classmethod(lambda cls, *a, **k: cls.Yes))
    monkeypatch.setattr(QMessageBox, "information",
                        classmethod(lambda cls, *a, **k: cls.Ok))


def _walk_texts(win):
    texts = []

    def walk(it):
        for i in range(it.childCount()):
            ch = it.child(i)
            texts.append(ch.text(0))
            walk(ch)
    walk(win.rail.tree.invisibleRootItem())
    return texts


def test_flat_pattern_action_adds_a_hidden_body_not_a_new_toolbar(
        win, qapp, monkeypatch):
    from tracer.core.document import FlatPatternFeature
    d = _sheet_in(win)
    r0 = d.result
    _say_yes(qapp, monkeypatch)
    win.action_flat_pattern()
    qapp.processEvents()
    fb = next((b for b in d.body_list() if b["name"] == "_flat"),
              None)
    assert fb is not None and fb["visible"] is False
    bs = d.body_solids()
    assert "_flat" in bs and "Sheet" in bs
    # the PART is still only the sheet: a hidden body is not ink
    assert d.result.bounding_box[0][0] == pytest.approx(
        r0.bounding_box[0][0])
    assert any(isinstance(f, FlatPatternFeature) for f in d.features)
    # rides the file: reload puts the paper back
    e = Document.from_dict(d.to_dict())
    e.recompute()
    assert "_flat" in e.body_solids()
    bb = e.body_solids()["_flat"].bounding_box
    assert float(bb[1][0]) == pytest.approx(100.0 + BA, abs=1e-3)
    assert "□ _flat" in " ".join(_walk_texts(win)) or any(
        "_flat" in t for t in _walk_texts(win))


def test_drawing_gets_a_flat_view_and_the_bends_travel_to_dxf(
        win, qapp, monkeypatch, tmp_path):
    from tracer.core import import2d
    d = _sheet_in(win)
    win.action_new_drawing()
    qapp.processEvents()
    _say_yes(qapp, monkeypatch)
    win.action_flat_pattern()
    qapp.processEvents()
    win.recompute()
    qapp.processEvents()
    views = win.drawing.views()
    assert "Flat" in views
    chains = views["Flat"]
    assert len(chains) == 1 and len(chains[0]) == 5
    assert np.allclose(chains[0][0], chains[0][-1])
    # the bend centre-lines ride the analytic channel, never re-fit
    bl = win.drawing.bends_page("Flat")
    assert len(bl) == 1 and len(bl[0]) == 2
    assert win.drawing.bends_page("top") == []   # scoped ink
    dxf = str(tmp_path / "flat.dxf")
    win.export_drawing(dxf)
    qapp.processEvents()
    ops = [o for o in import2d.read(dxf) if o[0] in ("line", "poly")]
    sc = win.drawing.frames()["Flat"][0]
    # The paper's OWN measured values ride here, and the honesty
    # margin is the DXF writer's 6-decimal rounding, not the law.
    fp = d.flat_feature()
    L = fp.flat_length * sc
    W = fp.width * sc
    # the outline: one closed op the size of the developed sheet
    assert any(o[2] and len(o[1]) == 5 and
               abs((max(p[0] for p in o[1]) -
                    min(p[0] for p in o[1])) - L) < 1e-5
               for o in ops)
    # and one open 2-pt op as long as the sheet is wide: the bend
    assert any(not o[2] and len(o[1]) == 2 and
               abs(math.hypot(o[1][0][0] - o[1][1][0],
                              o[1][0][1] - o[1][1][1]) - W) < 1e-5
               for o in ops)


def test_publish_pdf_paints_the_flat_view_with_zero_new_code(
        win, qapp, monkeypatch, tmp_path):
    d = _sheet_in(win)
    win.action_new_drawing()
    qapp.processEvents()
    _say_yes(qapp, monkeypatch)
    win.action_flat_pattern()
    qapp.processEvents()
    win.recompute()
    qapp.processEvents()
    assert "Flat" in win.drawing.views()
    n = win.drawing.publish_pdf(str(tmp_path / "flat.pdf"))
    assert n >= 1                              # M143 device-swap paint
