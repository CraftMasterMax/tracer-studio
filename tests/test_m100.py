"""M100 — per-view scale: the draughtsman's 1:2.

Fusion's view properties open with a scale picker, and every maker
who has ever squeezed a part onto A4 knows why: one sheet, one part,
but the detail view must be HALF size and the assembly icon can stay
small. Double-click a view on the sheet and the Scale dialog offers
Fit (the layout assistant's auto-scale, today's behavior) plus the
standard ratios. The override rides ON the drawing entry
({view: factor}) exactly like moves do: views still re-derive live,
bubbles still measure the MODEL (the number never changes because
the paper does), hidden lines and DXF export follow the frame, and
undo takes the view back to auto.

Honest scope: scale only (no rotation), the auto-fit still balances
the NON-overridden views, and an explicit scale is the draughtsman's
responsibility — like Fusion, a 5:1 detail may hang off the sheet.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402

from tracer.core import drawing                              # noqa: E402
from tracer.core.document import Document, PrimitiveFeature  # noqa: E402


def _views():
    box = PrimitiveFeature(name="b", kind="box",
                           dims={"dx": 40.0, "dy": 20.0, "dz": 5.0})
    s = box.build()
    return {v: drawing.project_view(s, view=v)
            for v in drawing.STANDARD}


# ---------------------------------------------------------------- core

def test_place_scales_one_view_without_touching_the_rest():
    views = _views()
    base = drawing.place(views)
    half = drawing.place(views, scales={"top": 0.5})
    assert half["top"]["sc"] == pytest.approx(0.5)
    assert half["front"]["sc"] == pytest.approx(base["front"]["sc"])
    # a 40-wide box at 1:2 spans 20 page mm
    span = half["top"]["max"][0] - half["top"]["min"][0]
    assert span == pytest.approx(20.0, abs=0.3)


def test_frames_and_anchors_round_trip_under_a_scale():
    views = _views()
    p = drawing.place(views, scales={"top": 2.0})["top"]
    page = (40.0 * p["sc"] + p["off"][0], 20.0 * p["sc"] + p["off"][1])
    model = ((page[0] - p["off"][0]) / p["sc"],
             (page[1] - p["off"][1]) / p["sc"])
    assert model == pytest.approx((40.0, 20.0))


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
        r.close()
    except Exception:
        raise


def _box_sheet(win, qapp):
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="Block", kind="box",
        dims={"dx": 40.0, "dy": 20.0, "dz": 10.0}))
    win.recompute()
    win.action_new_drawing()
    qapp.processEvents()
    return win.drawing


def test_double_click_a_view_offers_the_scale_dialog(win, qapp,
                                                     monkeypatch):
    from tracer.ui import cmddialog
    cv = _box_sheet(win, qapp)
    cv.resize(800, 600)
    qapp.processEvents()
    asked = {}

    def fake_ask(parent, title, fields):
        asked["title"] = title
        asked["choices"] = fields[0]["choices"]
        return {"scale": "1:2"}
    monkeypatch.setattr(cmddialog, "ask", fake_ask)
    sc, off = cv.frames()["top"]
    ctr = cv.s2p(off[0] + 20.0 * sc, off[1] + 10.0 * sc).toPoint()
    QTest.mouseDClick(cv, Qt.LeftButton, Qt.KeyboardModifier.NoModifier,
                      ctr, 10)
    qapp.processEvents()
    assert "scale" in asked["title"].lower()
    assert asked["choices"][0].lower().startswith("fit")
    assert cv.sheet()["vscale"]["top"] == pytest.approx(0.5)
    assert cv.frames()["top"][0] == pytest.approx(0.5)


def test_fit_clears_the_override(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    cv = _box_sheet(win, qapp)
    cv.resize(800, 600)
    qapp.processEvents()
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"scale": "1:5"})
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert cv.frames()["top"][0] == pytest.approx(0.2)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"scale": "Fit (auto)"})
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert cv.sheet().get("vscale", {}).get("top") is None
    assert cv.frames()["top"][0] == pytest.approx(1.0)   # box fits at 1


def test_nonsense_scale_changes_nothing(win, qapp, monkeypatch):
    cv = _box_sheet(win, qapp)
    before = cv.frames()["top"][0]
    monkeypatch.setattr(cv, "_scale_dialog",
                        lambda cur: "half-and-half")
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert cv.frames()["top"][0] == pytest.approx(before)
    assert "Scale" in win.status.currentMessage() or "scale" in \
        win.status.currentMessage().lower()


def test_scale_survives_the_file_and_the_undo(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    cv = _box_sheet(win, qapp)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"scale": "1:2"})
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    back = Document.from_dict(win.doc.to_dict())
    assert back.drawings[-1]["vscale"]["top"] == pytest.approx(0.5)
    win.undo()
    qapp.processEvents()
    assert "vscale" not in cv.sheet() or not cv.sheet()["vscale"]


def test_bubbles_measure_the_model_not_the_paper(win, qapp,
                                                 monkeypatch):
    cv = _box_sheet(win, qapp)
    cv.resize(800, 600)
    qapp.processEvents()
    cv.set_dim_mode(True)
    sc, off = cv.frames()["top"]
    for x, y in [(off[0], off[1]), (off[0] + 40.0 * sc, off[1])]:
        QTest.mouseClick(cv, Qt.LeftButton,
                         Qt.KeyboardModifier.NoModifier,
                         cv.s2p(x, y).toPoint())
        qapp.processEvents()
    cv.set_dim_mode(False)
    d = cv.sheet()["dims"][0]
    assert d["text"] == "40.00"
    monkeypatch.setattr(cv, "_scale_dialog", lambda cur: "1:2")
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    assert d["text"] == "40.00"                 # the model did not shrink
    a_page = cv.model_to_page("top", d["a"])
    sc2, off2 = cv.frames()["top"]
    assert a_page[0] == pytest.approx(
        d["a"][0] * sc2 + off2[0], abs=0.01)    # but the ink did


def test_dxf_export_uses_the_scaled_geometry(win, qapp, monkeypatch,
                                             tmp_path):
    cv = _box_sheet(win, qapp)
    monkeypatch.setattr(cv, "_scale_dialog", lambda cur: "1:2")
    cv.view_scale_requested.emit("top")
    qapp.processEvents()
    out = str(tmp_path / "half.dxf")
    win.export_drawing(out)
    from tracer.core import import2d
    pts = [p for op in import2d.read(out) if op[0] == "poly"
           for p in op[1]]
    xs = [p[0] for p in pts]
    # the top view at 1:2 spans 20 mm; the whole sheet's ink must
    # reflect a 20-wide run somewhere (auto-fit would give 40)
    assert max(xs) - min(xs) < 420
    hit = False
    for op in import2d.read(out):
        if op[0] != "poly":
            continue
        w = max(p[0] for p in op[1]) - min(p[0] for p in op[1])
        if abs(w - 20.0) < 0.5:
            hit = True
    assert hit, "no 20 mm-wide run found (scale did not reach the paper)"


def test_scale_label_reads_like_a_drawing():
    from tracer.ui.drawingview import scale_label
    assert scale_label(1.0) == "1:1"
    assert scale_label(0.5) == "1:2"
    assert scale_label(2.0) == "2:1"
    assert scale_label(0.2) == "1:5"
