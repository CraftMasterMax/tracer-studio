"""M114: Limits & Fits — the ISO 286 callout contract.

The data module must reproduce published limit tables to the micron;
the sheet must attach, paint, and remove class callouts over nominal
geometry; the drawing keys must answer D/B/F/Esc.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                           # noqa: E402

from tracer.core import fits                                                # noqa: E402


# ---- the tables (published anchors) -------------------------------------------
def test_it_grades_and_band_edges():
    assert fits.it(10, 7) == 15          # µm
    assert fits.it(30, 7) == 21
    assert fits.it(110, 9) == 87         # [V] roymech sanity anchor
    assert fits.it(3, 7) == 10           # band edge: <= 3
    assert fits.it(3.2, 7) == 12         # next band up
    with pytest.raises(ValueError):
        fits.it(150, 7)                  # beyond the v1 table
    with pytest.raises(ValueError):
        fits.it(10, 12)                  # grade out of scope


def test_fine_bands_make_25_differ_from_30():
    # the classic trap: deviations use 24-30, ITs use 18-30
    assert fits.deviation(25, "g6") == (-21, -8)
    assert fits.deviation(30, "g6") == (-21, -8)
    assert fits.deviation(40, "g6") == (-25, -9)
    assert fits.deviation(10, "H7") == (0, 15)
    assert fits.deviation(10, "h6") == (-9, 0)
    assert fits.deviation(30, "n6") == (8, 21)
    assert fits.deviation(30, "p6") == (22, 35)
    assert fits.deviation(10, "p6") == (15, 24)
    assert fits.deviation(10, "k6") == (0, 9)


def test_limits_match_published_mm():
    assert fits.limits(10, "H7") == (10.000, 10.015)
    assert fits.limits(10, "g6") == (9.985, 9.994)
    assert fits.limits(10, "h6") == (9.991, 10.000)
    assert fits.limits(10, "n6") == (10.006, 10.015)
    assert fits.limits(30, "H7") == (30.000, 30.021)


def test_fit_pair_taxonomy():
    f = fits.fit(10, "H7/g6")
    assert (f["xmin_um"], f["xmax_um"], f["kind"]) == (6, 30, "clearance")
    assert fits.fit(30, "H7/g6")["xmax_um"] == 42
    assert fits.fit(10, "H7/k6")["kind"] == "transition"
    f = fits.fit(10, "H7/p6")
    assert (f["xmin_um"], f["xmax_um"], f["kind"]) == (-24, 0,
                                                       "interference")
    with pytest.raises(ValueError):
        fits.fit(10, "H7")
    with pytest.raises(ValueError):
        fits.fit(10, "g6/H7")            # hole first, CAPS


def test_only_the_verified_classes():
    for bad in ("e9", "K7", "j6", "s7", "H12", "H4", "hh", ""):
        with pytest.raises(ValueError):
            fits.limits(10, bad)


def test_callout_formatting():
    assert fits.fmt_um(21) == "+0.021"
    assert fits.fmt_um(0) == "0"
    assert fits.fmt_um(-15) == "-0.015"
    assert fits.callout(30, "H7") == "H7 (+0.021/0)"
    assert fits.callout(10, "g6") == "g6 (-0.006/-0.015)"
    assert fits.callout(30, "H7/g6") == "H7/g6"     # pairs: class alone


# ---- the sheet --------------------------------------------------------------------
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
        w.close()
    except ImportError:
        pytest.skip("no PySide6")


def _box_sheet(win, qapp):
    from tracer.core.document import PrimitiveFeature
    win.new_document()
    win.doc.features.append(PrimitiveFeature(
        name="b", kind="box", dims={"dx": 40.0, "dy": 20.0, "dz": 5.0}))
    win.doc.recompute()
    win.action_new_drawing()
    qapp.processEvents()
    return win.drawing


def _flat_dim(cv):
    """Inject one honest 40 mm linear dim on the top view."""
    g = cv.sheet()
    g.setdefault("dims", []).append(
        {"view": "top", "a": [0.0, 0.0], "b": [40.0, 0.0],
         "text": "40.00"})
    return g["dims"][0]


def test_annotate_attaches_callout(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    cv = _box_sheet(win, qapp)
    d = _flat_dim(cv)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"cls": "H7"})
    win._annotate_fit("top", 0)
    qapp.processEvents()
    assert d["fit"] == "H7"
    assert d["fit_nom"] == pytest.approx(40.0)
    disp = cv._dim_disp(d)
    assert disp == "40.00 H7 (+0.025/0)"        # IT7(30-50) = 25 µm
    assert d["text"] == "40.00"                 # geometry stays nominal


def test_annotate_removes_and_refuses_radius(win, qapp, monkeypatch):
    from tracer.ui import cmddialog
    cv = _box_sheet(win, qapp)
    d = _flat_dim(cv)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {"cls": "g6"})
    win._annotate_fit("top", 0)
    assert d["fit"] == "g6"
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"cls": "(none — plain dim)"})
    win._annotate_fit("top", 0)
    assert "fit" not in d and "fit_nom" not in d
    assert cv._dim_disp(d) == "40.00"
    r = {"view": "top", "a": [0, 0], "b": [1, 1], "text": "R 5.00",
         "radius": True, "center": [0, 0], "dir": [1, 0], "r": 5.0}
    cv.sheet().setdefault("dims", []).append(r)
    win._annotate_fit("top", 1)
    assert "fit" not in r                       # R bubbles stay plain


def test_rejected_class_changes_nothing(win, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tracer.ui import cmddialog
    cv = _box_sheet(win, qapp)
    d = _flat_dim(cv)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"cls": "Custom…"})
    asked = {"n": 0}

    def ask2(parent, title, fields, *a, **k):
        asked["n"] += 1
        return {"cls": "e9"}                    # outside the v1 tables

    monkeypatch.setattr(cmddialog, "ask", ask2)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a[2])))
    win._annotate_fit("top", 0)
    assert asked["n"] == 1 and warned
    assert "fit" not in d
    assert cv.sheet()["dims"][0] is d


def test_dim_at_finds_the_bubble_and_misses_the_paper(win, qapp):
    cv = _box_sheet(win, qapp)
    _flat_dim(cv)
    cv.resize(800, 600)
    qapp.processEvents()
    placed = cv.placed()
    fr = placed["top"]
    mid = cv.s2p(*cv._m2p(fr, (20.0, 0.0)))
    hit = cv._dim_at((mid.x(), mid.y()), placed)
    assert hit == ("top", 0)
    assert cv._dim_at((10.0, 10.0), placed) is None


def test_drawing_keys_answer(win, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    cv = _box_sheet(win, qapp)
    win.stack.setCurrentWidget(win._drawing_page)
    cv.setFocus()
    qapp.processEvents()
    QTest.keyClick(cv, Qt.Key_D)
    qapp.processEvents()
    assert win._dim_btn.isChecked() and cv._dim_mode
    QTest.keyClick(cv, Qt.Key_F)                # exclusive: fit in, dim out
    qapp.processEvents()
    assert win._fit_btn.isChecked() and not win._dim_btn.isChecked()
    QTest.keyClick(cv, Qt.Key_Escape)
    qapp.processEvents()
    assert not win._fit_btn.isChecked() and not cv._fit_mode
