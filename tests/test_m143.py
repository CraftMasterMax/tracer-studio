"""M143 — Publish PDF: the sheet lands on true paper.

The probe ran this to the bone before a line shipped (contract
research/pdf_publish_export.md §10, spike green): reuse paintPage
against a DEVICE SWAP (shadow width/height/rect + _zoom = dpi/25.4
+ _center at the sheet centre) instead of forking the paint code —
every pen in the path is already mm×zoom, so a zoom swap turns the
screen's ink into physical paper ink for free. What the swap must
NEVER do is trust QPdfWriter defaults: factory is A4 portrait with
10 mm margins and Qt CROPS SILENTLY (the trap was reproduced
pixel-wise) — an explicit QPageLayout(size, Landscape, zero
margins) goes down per sheet, before the first paint. One painter,
newPage() between sheets (FreeCAD's multi-page rule), QPdfWriter
finalises by destruction (no close() in PySide6), and the vendor's
bundle law holds: many sheets → ONE file, order = creation order.
publish_pdf is a canvas method so the gate drives it headless; the
paint page is a VIEW (desk grey + ring + transient ghosts) so print
mode fills paper instead and stashes the ghosts off the sheet —
restoring them after (publish must not eat your in-progress tool).
"""
import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSize, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tracer.core.document import PrimitiveFeature  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


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
    w.doc.add(PrimitiveFeature(name="bracket", kind="box",
                               dims={"dx": 60, "dy": 30, "dz": 12}))
    w.recompute()
    qapp.processEvents()
    yield w
    w._unsaved = False          # m56/m63 house law: close the window
    w.close()
    r.ctx.release()
    qapp.processEvents()


def two_sheets(win):
    """Drawing1 (A3) + Drawing2 (A4) — sheet order IS creation order."""
    win.action_new_drawing()
    win.action_new_drawing()
    win.doc.drawings[1]["page"] = "A4"
    return win.drawing


def open_pdf(path):
    d = QPdfDocument()
    assert d.load(path) == QPdfDocument.Error.None_   # PySide6 spells
    return d                                          # NoError "None_"


def raster(doc, i, w=1200, h=847):
    """Render + composite over white: our paper is #f5f5f2 on an
    ARGB32-transparent render, so raw pixel tests lie (§7 recipe)."""
    img = doc.render(i, QSize(w, h))
    out = QImage(img.size(), QImage.Format_RGB32)
    out.fill(Qt.white)
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.end()
    return out


def ink_fraction(img):
    step = 7
    n = dark = 0
    for x in range(0, img.width(), step):
        for y in range(0, img.height(), step):
            n += 1
            if img.pixelColor(x, y).lightness() < 100:
                dark += 1
    return dark / max(1, n)


def text_of(doc, i):
    # Per-glyph Td advances interleave spaces into extraction runs
    # (contract §7's warning, reproduced page-wise) — flatten.
    return "".join(doc.getAllText(i).text().split())


# ---- the paper itself ------------------------------------------------
def test_pages_are_true_paper_per_sheet(win, qapp, tmp_path):
    cvd = two_sheets(win)
    qapp.processEvents()
    path = str(tmp_path / "bundle.pdf")
    assert cvd.publish_pdf(path) == 2
    doc = open_pdf(path)
    assert doc.pageCount() == 2
    r0, r1 = doc.pagePointSize(0), doc.pagePointSize(1)
    assert abs(r0.width() - 420 / 25.4 * 72) <= 1.5      # A3 landscape
    assert abs(r0.height() - 297 / 25.4 * 72) <= 1.5
    assert abs(r1.width() - 297 / 25.4 * 72) <= 1.5      # A4: per-sheet!
    assert abs(r1.height() - 210 / 25.4 * 72) <= 1.5


def test_layout_is_explicit_not_the_factory_default(win, qapp,
                                                    tmp_path):
    # THE trap: writer defaults are A4 portrait + margins and Qt
    # crops silently. Two runs must agree (the explicit layout is
    # pinned) and neither may land on the default A4 size for A3.
    cvd = two_sheets(win)
    qapp.processEvents()
    a, b = str(tmp_path / "a.pdf"), str(tmp_path / "b.pdf")
    cvd.publish_pdf(a, dpi=150)
    cvd.publish_pdf(b, dpi=300)
    da, db = open_pdf(a), open_pdf(b)
    assert da.pagePointSize(0) == db.pagePointSize(0)
    assert (abs(da.pagePointSize(0).width()
               - 420 / 25.4 * 72) <= 1.5)


def test_each_page_carries_its_own_sheet_number(win, qapp, tmp_path):
    # _block_meta reads the CANVAS sheet_idx — the print context must
    # repoint it per page or every sheet prints "1 / 2" (§8 trap 2).
    cvd = two_sheets(win)
    qapp.processEvents()
    path = str(tmp_path / "meta.pdf")
    cvd.publish_pdf(path)
    doc = open_pdf(path)
    assert "1/2" in text_of(doc, 0)
    assert "2/2" in text_of(doc, 1)


def test_pages_carry_real_ink_and_no_desk_ring(win, qapp, tmp_path):
    cvd = two_sheets(win)
    qapp.processEvents()
    path = str(tmp_path / "ink.pdf")
    cvd.publish_pdf(path)
    doc = open_pdf(path)
    for i in range(2):
        img = raster(doc, i)
        frac = ink_fraction(img)
        assert 0.0005 < frac < 0.5, (i, frac)   # not blank, not black
        corner = img.pixelColor(3, 3)
        assert corner.lightness() > 200, corner  # paper to the edge:
        #                             the desk-grey ring stays on screen


# ---- the swap is a borrow, not a theft --------------------------------
def test_swap_is_fully_reversible(win, qapp, tmp_path):
    cvd = two_sheets(win)
    qapp.processEvents()
    before = (cvd._zoom, (cvd._center.x(), cvd._center.y()),
              cvd.width(), cvd.height(), cvd.sheet_idx, cvd.page,
              cvd._printing)
    cvd.publish_pdf(str(tmp_path / "rev.pdf"))
    qapp.processEvents()
    after = (cvd._zoom, (cvd._center.x(), cvd._center.y()),
             cvd.width(), cvd.height(), cvd.sheet_idx, cvd.page,
             cvd._printing)
    assert after == before
    cvd.update()                       # the live canvas still paints


def test_transient_ghosts_stay_off_the_sheet(win, qapp, tmp_path):
    cvd = two_sheets(win)
    qapp.processEvents()
    cvd._dim_first = ("top", (10.0, 5.0))          # mid-tool publish
    cvd._sec_pts = [(1.0, 2.0), (40.0, 9.0)]
    cvd._sec_view = "top"
    seen = {}
    orig = cvd.paintPage

    def spy(p):
        seen["dim"] = cvd._dim_first
        seen["sec"] = cvd._sec_pts
        return orig(p)

    cvd.paintPage = spy
    try:
        cvd.publish_pdf(str(tmp_path / "ghost.pdf"))
    finally:
        del cvd.paintPage
    assert seen and seen["dim"] is None and seen["sec"] in (None, [])
    assert cvd._dim_first == ("top", (10.0, 5.0))  # yours again after
    assert cvd._sec_pts == [(1.0, 2.0), (40.0, 9.0)]


# ---- the app seam ------------------------------------------------------
def test_action_publish_pdf_writes_the_bundle(win, qapp, tmp_path,
                                              monkeypatch):
    two_sheets(win)
    qapp.processEvents()
    target = str(tmp_path / "whole.pdf")
    monkeypatch.setattr(
        "tracer.ui.mainwindow.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (target, "PDF (*.pdf)")))
    win.action_publish_pdf()
    assert os.path.getsize(target) > 1000
    assert open_pdf(target).pageCount() == 2


def test_action_publish_pdf_refuses_without_sheets(win, qapp,
                                                   tmp_path,
                                                   monkeypatch):
    asked = []
    monkeypatch.setattr(
        "tracer.ui.mainwindow.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: asked.append(1)
                     or (str(tmp_path / "x.pdf"), "")))
    win.action_publish_pdf()               # no drawings yet
    assert not asked                        # the refusal comes first
    assert "sheet" in win.status.currentMessage().lower()
