"""M16: Mirror feature — symmetric twin across a datum plane."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QInputDialog                      # noqa: E402

from tracer.core import io as fio                                              # noqa: E402
from tracer.core.document import (CircularPatternFeature,                    # noqa: E402
                                 Document, LinearPatternFeature,
                                 MirrorFeature, PrimitiveFeature)
from tracer.core.geometry import Solid                                        # noqa: E402
from conftest import tree_texts, script_cmd, script_cmd_cancel          # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    from tracer.ui.mainwindow import MainWindow
    from tracer.ui.renderer import SceneRenderer
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    monkeypatch.setattr(QInputDialog, "getDouble",
                        staticmethod(lambda *a, **k: (10.0, True)))
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()


# ---- core --------------------------------------------------------------------
def test_solid_mirror_geometry():
    b = Solid.box(10, 10, 10)                     # x 0..10
    m = b.mirror((1, 0, 0))                       # across x = 0
    assert m.bounding_box[0][0] == pytest.approx(-10.0)
    assert m.bounding_box[1][0] == pytest.approx(0.0)
    assert m.volume == pytest.approx(1000.0)
    with pytest.raises(ValueError):
        b.mirror((0, 0, 0))


def test_mirror_union_twin_exact():
    # 40x40x10 plate, half-protruding boss + its XZ mirror twin
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 40, "dz": 10}))
    boss = d.add(PrimitiveFeature(name="boss", kind="box",
                                  dims={"dx": 6, "dy": 6, "dz": 12},
                                  placement=(2, 5, 5)))
    d.add_mirror("twin", boss, "XZ", 20.0)        # plate mid-plane
    solid = d.recompute()
    above = 6 * 6 * (17 - 10)                     # boss above plate roof
    assert solid.volume == pytest.approx(40 * 40 * 10 + 2 * above, rel=1e-6)
    ys = solid.bounding_box[:, 1]
    assert (ys[0] + ys[1]) == pytest.approx(40.0)  # symmetric about y = 20


def test_mirror_of_a_cut_makes_second_cut():
    d = Document()
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 40, "dz": 10}))
    hole = d.add(PrimitiveFeature(name="hole", kind="cylinder",
                                  dims={"radius": 4, "height": 20},
                                  placement=(10, 20, -5), op="subtract"))
    twin = d.add_mirror("twin-hole", hole, "YZ", 20.0)
    assert twin.op == "subtract"                  # inherited
    solid = d.recompute()
    assert solid.volume == pytest.approx(16000 - 2 * (3.14159265 * 16 * 10),
                                         rel=1e-3)


def test_mirror_noop_when_source_suppressed():
    d = Document()
    base = d.add(PrimitiveFeature(name="plate", kind="box",
                                  dims={"dx": 10, "dy": 10, "dz": 10}))
    lug = d.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2, "dy": 2, "dz": 2},
                                 placement=(11, 4, 4)))
    d.add_mirror("twin", lug, "XY", 5.0)
    with_twin = d.recompute().volume
    assert with_twin == pytest.approx(1000 + 8)
    lug.suppressed = True
    assert d.recompute().volume == pytest.approx(1000.0)


def test_mirror_serialization(tmp_path):
    d = Document()
    base = d.add(PrimitiveFeature(name="plate", kind="box",
                                  dims={"dx": 10, "dy": 10, "dz": 10}))
    d.add_mirror("twin", base, "YZ", 3.5)
    v = d.recompute().volume
    p = tmp_path / "mir.tracer"
    fio.save_document(d, p)
    d2 = fio.load_document(p)
    m = [f for f in d2.features if isinstance(f, MirrorFeature)]
    assert len(m) == 1 and m[0].plane == "YZ" and m[0].offset == 3.5
    assert m[0].source_uid == base.uid            # uid link survived
    assert d2.recompute().volume == pytest.approx(v)


def test_mirror_unknown_plane_raises():
    d = Document()
    base = d.add(PrimitiveFeature(name="plate", kind="box",
                                  dims={"dx": 4, "dy": 4, "dz": 4}))
    d.add(PrimitiveFeature(name="lug", kind="box",
                           dims={"dx": 1, "dy": 1, "dz": 1},
                           placement=(5, 0, 0)))
    d.features[-1] = MirrorFeature(name="bad", op="union",
                                   source_uid=base.uid, plane="QW")
    with pytest.raises(ValueError, match="mirror plane"):
        d.recompute()


# ---- UI ----------------------------------------------------------------------
def test_action_mirror_flow(win, monkeypatch):
    win.new_document()
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 20, "dy": 20, "dz": 5}))
    win.doc.add(PrimitiveFeature(name="lug", kind="box",
                                 dims={"dx": 2, "dy": 8, "dz": 5},
                                 placement=(1, 2, 5)))           # y 2..10
    win.recompute()
    picks = {"src": "lug", "plane": "XZ", "off": 10.0}
    script_cmd(monkeypatch, picks)
    win.action_mirror()
    m = win.doc.features[-1]
    assert isinstance(m, MirrorFeature) and m.plane == "XZ"
    # plate 2000 + lug y2..10 (80) + twin y10..18 (80), both on the plate
    assert win.doc.result.volume == pytest.approx(2000 + 160, rel=1e-6)


def test_context_mirror_handler_cancels(win, monkeypatch):
    win.new_document()
    base = win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                        dims={"dx": 9, "dy": 9, "dz": 9}))
    win._capture = lambda: None                   # no-op undo capture
    script_cmd_cancel(monkeypatch)                # dialog answers Cancel
    n = len(win.doc.features)
    win._mirror_feature(base, "XY")
    assert len(win.doc.features) == n             # nothing added on cancel


def test_mirror_menus_present(win):
    menus = {a.text().replace("&", ""): a.menu()
             for a in win.menuBar().actions()}
    create = menus["Create"]
    labels = [x.text().replace("&", "") for x in create.actions()]
    assert "Mirror…" in labels


def test_properties_panel_pattern_crash_regression(win):
    """show_feature used to read .placement on everything — patterns have
    none. Guarded now; assert the panel renders for each feature type."""
    from tracer.core.document import ExtrudeFeature            # noqa: F401
    win.new_document()
    base = win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                        dims={"dx": 9, "dy": 9, "dz": 9}))
    lin = win.doc.add_linear_pattern("lp", base, (12, 0, 0), 2)
    cir = win.doc.add_circular_pattern("cp", base, (0, 0), 360, 3)
    mir = win.doc.add_mirror("mp", base, "YZ", 5.0)
    props = win.rail.props
    props.show_feature(lin)
    assert "2x" in props._body.text()
    props.show_feature(cir)
    assert "360" in props._body.text()
    props.show_feature(mir)
    assert "YZ" in props._body.text()
    # browser tree carries the mirror + pattern glyphs
    win.recompute()
    rows = tree_texts(win)
    assert any("\u25e7" in r for r in rows)       # ◧ mirror
    assert sum("\u29c9" in r for r in rows) == 2  # ⧉ patterns
