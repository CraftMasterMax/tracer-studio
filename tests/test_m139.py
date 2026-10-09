"""M139 — "Bodies to Cut": the section's exclusion picker.

The wave-13 probe's crux, LIVE-VERIFIED before a line of the
milestone shipped: the vendor's "Objects to Cut" tree (uncheck =
GONE from the child) and the ASME standard-parts law (drawn WHOLE,
unhatched) ask for two different things — and our pipeline forces
the choice, because the child projects ONLY the kept half. A naive
filter of the cut source is therefore SILENT DELETION (verified:
the stud's ink vanished). The honest shape is the ADD-BACK: cut a
filtered union, then stand the excluded bodies into the projected
half whole — and since hatch fills ONLY cap loops, the ASME look
of "present but unhatched" costs zero drawing code. Fastener
auto-detection stays deferred loudly: with no fastener library
there is nothing to detect, and thread-metadata heuristics would
exclude our OWN threaded bosses. Exclusion rides the M137 props
dialog as an inclusion picker (all ticked = the untouched,
byte-identical pre-M139 entry); names ride the M130 rename law, so
a stale exclude is inert, never a crash — except the one honest
refusal: excluding EVERYTHING, at the dialog before the capture,
and as a raise for hand-edited files.
"""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from tracer.core.document import (Document, HoleFeature,
                                  PrimitiveFeature)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def area(L):
    P = np.asarray(L, float)
    x, y = P[:, 0], P[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1))
                     - np.dot(y, np.roll(x, -1)))) / 2.0


def cap_area(cv, name):
    return round(sum(area(L) for L in cv.cuts_page()[name]), 1)


def z_max(cv, name):
    P = np.vstack([np.asarray(c, float)
                   for c in cv.views()[name]])
    return float(P[:, 1].max())


def two_body_doc():
    """Plate 40x30x6, a 10x10x20 stud standing at the origin in its
    own body: a cut plane at y=5 breaks BOTH — the discriminator for
    hatched-vs-standing is the cap area (union T 380 vs plate-only
    240), for whole-vs-deleted it is the silhouette (z-max 20)."""
    doc = Document()
    doc.add(PrimitiveFeature(name="plate", kind="box",
                             dims={"dx": 40, "dy": 30, "dz": 6}))
    doc.add(PrimitiveFeature(name="stud", kind="box", body="Stud",
                             dims={"dx": 10, "dy": 10, "dz": 20}))
    return doc


LINE = {"parent": "top", "p0": (0, 5), "p1": (40, 5), "flip": False}


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
    d = w.doc
    d.add(PrimitiveFeature(name="plate", kind="box",
                           dims={"dx": 40, "dy": 30, "dz": 6}))
    d.add(PrimitiveFeature(name="stud", kind="box", body="Stud",
                           dims={"dx": 10, "dy": 10, "dz": 20}))
    w.recompute()
    w.action_new_drawing()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w._discard_guard = lambda: True
    w.close()
    r.close()


def _dialog(qapp, monkeypatch, cut, **over):
    """Answer the M137 props dialog with the picker set to `cut`."""
    from tracer.ui import cmddialog
    vals = dict(mode="Full (everything behind the line)", dist=10.0,
                flip=False, hidden=False, scale="", cut=cut)
    vals.update(over)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: dict(vals))
    return cmddialog


def test_excluded_body_stands_whole_and_unhatched(win, qapp,
                                                  monkeypatch):
    cv = win.drawing
    win._on_section_line(dict(LINE))
    qapp.processEvents()
    assert cap_area(cv, "A-A") == 380.0      # plate 240 + stud 140
    assert z_max(cv, "A-A") == 20.0          # the stud's full height
    _dialog(qapp, monkeypatch, ["Body 1"])   # Stud unticked
    win._on_section_edit("A-A")
    qapp.processEvents()
    assert cv.sections()[0]["exclude"] == ["Stud"]
    assert cap_area(cv, "A-A") == 240.0      # stud contributes NO
    assert z_max(cv, "A-A") == 20.0          # wound but stands WHOLE
    assert "cutting 1 of 2 bodies" in win.status.currentMessage()


def test_the_picker_refuses_to_cut_nothing_before_any_capture(
        win, qapp, monkeypatch):
    cv = win.drawing
    win._on_section_line(dict(LINE))
    qapp.processEvents()
    _dialog(qapp, monkeypatch, ["Body 1"])
    win._on_section_edit("A-A")
    entry = dict(cv.sections()[0])
    _dialog(qapp, monkeypatch, [])           # nothing ticked
    win._on_section_edit("A-A")
    assert dict(cv.sections()[0]) == entry   # refusal mutates nothing
    assert "at least one" in win.status.currentMessage()
    win.undo()                               # undo hits the REAL edit
    assert "exclude" not in cv.sections()[0]


def test_all_ticked_is_the_untouched_entry_byte_for_byte(
        win, qapp, monkeypatch):
    cv = win.drawing
    win._on_section_line(dict(LINE))
    qapp.processEvents()
    _dialog(qapp, monkeypatch, ["Body 1", "Stud"])   # all ticked
    win._on_section_edit("A-A")
    assert "exclude" not in cv.sections()[0]         # key never born
    assert cap_area(cv, "A-A") == 380.0              # and the cut is
    assert cv.sections()[0] == {**LINE, "name": "A-A"}


def test_a_stale_exclude_name_is_inert(win, qapp):
    cv = win.drawing
    win._on_section_line(dict(LINE))
    cv.sections()[0]["exclude"] = ["Ghost"]  # a body that never was
    qapp.processEvents()
    assert cap_area(cv, "A-A") == 380.0      # the cut stands, whole
    assert not cv.grab().isNull()            # and so does the paint


def test_excluding_everything_raises_honestly(win, qapp):
    cv = win.drawing
    win._on_section_line(dict(LINE))
    cv.sections()[0]["exclude"] = ["Body 1", "Stud"]
    with pytest.raises(ValueError):          # batch_union([]) guard,
        cv._sec_cut(cv.sections()[0])        # surfaced, not swallowed


def test_modes_compose_with_the_exclusion(win, qapp, monkeypatch):
    cv = win.drawing
    win._on_section_line(dict(LINE))
    _dialog(qapp, monkeypatch, ["Body 1"],
            mode="Slice (the cut face alone)")
    win._on_section_edit("A-A")
    qapp.processEvents()
    res = cv._sec_cut(cv.sections()[0])
    assert res["half"] is None               # a slice has no body to
    assert cap_area(cv, "A-A") == 240.0      #  stand in: wound only
    _dialog(qapp, monkeypatch, ["Body 1"],
            mode="Distance (a slab from the line)", dist=4.0)
    win._on_section_edit("A-A")
    qapp.processEvents()
    assert cap_area(cv, "A-A") == 240.0      # slab cuts plate only…
    assert z_max(cv, "A-A") == 20.0          # …yet the stud towers


def test_jog_and_exclusion_compose(win, qapp, monkeypatch):
    cv = win.drawing
    jog = {"parent": "top", "p0": (0, 3), "p1": (40, 7),
           "pts": [(0, 3), (20, 3), (20, 7), (40, 7)]}
    win._on_section_line(dict(jog))
    qapp.processEvents()
    assert cap_area(cv, "A-A") == 380.0      # T-cap in run 1 + plate
    _dialog(qapp, monkeypatch, ["Body 1"])
    win._on_section_edit("A-A")
    qapp.processEvents()
    assert cap_area(cv, "A-A") == 240.0      # plate bands only: 120…
    assert len(cv.cuts_page()["A-A"]) == 2   # …plus 120 across the jog
    assert z_max(cv, "A-A") == 20.0          # stud whole through both


def test_the_exclusion_rides_the_file(win, qapp, monkeypatch):
    cv = win.drawing
    win._on_section_line(dict(LINE))
    _dialog(qapp, monkeypatch, ["Body 1"])
    win._on_section_edit("A-A")
    blob = win.doc.to_dict()
    s = blob["drawings"][-1]["sections"][0]
    assert [str(n) for n in s["exclude"]] == ["Stud"]
    from tracer.core.document import Document as D
    rt = D.from_dict(blob)
    assert rt.drawings[-1]["sections"][0]["exclude"] == ["Stud"]


def test_the_picker_only_shows_when_there_is_a_choice(
        win, qapp, monkeypatch):
    captured = []
    from tracer.ui import cmddialog

    def spy(parent, title, fields):
        captured.append(fields)
        names = sorted(win.doc.body_solids())
        return dict(mode="Full (everything behind the line)",
                    dist=10.0, flip=False, hidden=False, scale="",
                    cut=names)
    monkeypatch.setattr(cmddialog, "ask", spy)
    win._on_section_line(dict(LINE))
    win._on_section_edit("A-A")              # two bodies: a picker
    assert any(f["kind"] == "checks" for f in captured[0])
    win.undo()                               # drop the section
    win._on_section_line(dict(LINE))
    win.doc.features = [f for f in win.doc.features
                        if getattr(f, "name", "") != "stud"]
    win.recompute()
    captured.clear()
    win._on_section_edit("A-A")              # one body: no picker —
    assert not any(f["kind"] == "checks"     # nothing to decline
                   for f in captured[0])


def test_the_picker_opens_pre_ticked_from_the_entry(win, qapp,
                                                    monkeypatch):
    cv = win.drawing
    win._on_section_line(dict(LINE))
    _dialog(qapp, monkeypatch, ["Body 1"])
    win._on_section_edit("A-A")
    seen = []
    from tracer.ui import cmddialog

    def spy(parent, title, fields):
        seen.append(fields)
        return None                          # cancel
    monkeypatch.setattr(cmddialog, "ask", spy)
    win._on_section_edit("A-A")
    f = next(f for f in seen[0] if f["kind"] == "checks")
    assert f["choices"] == ["Body 1", "Stud"]
    assert f["checked"] == ["Body 1"]        # Stud shows unticked


def test_hlr_occlusion_binning_keeps_the_answer_exact():
    # M139a: the suite gate caught the HLR occlusion test interrogating
    # EVERY front triangle about EVERY edge midpoint — a plate with two
    # modelled M8 taps (41,766 triangles) took 91 s to draw, borderline
    # enough that a routine reboot flipped it into a timeout. The fix
    # binned triangles by 2D bbox into a grid so a midpoint asks only
    # its own cell: WHICH triangles were asked changed, WHAT they answer
    # did not. These chain counts are the pre-fix baseline, verified
    # byte-identical across the whole implementation (visible/hidden).
    from tracer.core import drawing as dr
    doc = Document()
    doc.add(PrimitiveFeature(name="plate", kind="box",
                             dims={"dx": 40, "dy": 24, "dz": 8}))
    for x in (12.0, 28.0):
        doc.add(HoleFeature(name=f"tap{x}", op="subtract",
                            center=(x, 12, 8), normal=(0, 0, -1),
                            radius=3.4, depth=8, cut_length=8,
                            through=True, thread_pitch=1.25,
                            thread_len=8, thread_size="M8",
                            thread_class="6H"))
    doc.add(HoleFeature(name="plain", op="subtract", center=(8, 6, 8),
                        normal=(0, 0, -1), radius=2.5, depth=4,
                        cut_length=4))
    doc.add(HoleFeature(name="cb", op="subtract", center=(30, 6, 8),
                        normal=(0, 0, -1), radius=2.5, depth=4,
                        cut_length=4, cb_radius=4.5, cb_depth=3))
    golds = {"top": (460, 641), "front": (1, 122), "right": (1, 77),
             "iso": (75, 170)}
    for view, want in golds.items():
        out = dr.project_edges(doc.result, view)
        assert (len(out["visible"]), len(out["hidden"])) == want, view
