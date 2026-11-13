"""M201 R30 - the Section door wears the page that IS its reference.

[SLD-SECTION-ANALYSIS, verbatim; banked insp28 raw, byte-identical
live re-read insp29verify] the REFERENCE page is confirmed-absent
(3x404, insp28 ledger) - this task page prints the whole dialog
architecture: "The Section Analysis dialog displays." - the TITLE is
page-printed (the COM page printed none); "In the canvas, select a
planar object to define the Cut Plane." rides as the combo of named
planar objects this kernel has (canvas picking UNOFFERED, named);
"Adjust the Distance and Angle manipulator handles to orient the
cutting plane, or enter specific values." - Distance rides the normal,
Angle turns about the plane's own u axis, which axis the page prints
NOT AT ALL: the choice and both number rests are OURS ("Default:"
counts 0 on the page).  "Optional: Click Flip to switch which side to
reveal." - and ONLY the side flips.  The family's one page-printed
default: "The Section Color option is set to From Component by
default" - a HOUSE FACT per PAGE LAWS, with the page's two members
and their glosses worn verbatim.  UNOFFERED-BY-NAME (declared,
named): "Show Hatch" - the diagonal hatch pattern on cut faces is
machinery this kernel has no mouth for (caps shade flat; decoration
is forbidden) - and the Analysis-folder browser node with its
visibility, Edit and Delete verbs (R28's stance, same pages).  ' mm'
0, Cancel 0, OK 2, degrees SPOKEN never symbol: the row says
"Angle (degrees)"."""
import inspect
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                          # noqa: E402

import numpy as np                                                   # noqa: E402
from tracer.core.document import Document, PrimitiveFeature          # noqa: E402
from tracer.ui import cmddialog                                      # noqa: E402
from tracer.ui.mainwindow import MainWindow                         # noqa: E402
from tracer.ui.renderer import SceneRenderer                        # noqa: E402


def _box(d):
    d.add(PrimitiveFeature(name="slab", kind="box",
                           dims={"dx": 10, "dy": 10, "dz": 10}))
    d.recompute()


def _mouth(fn):
    return " ".join(inspect.getsource(fn).split())


# ---- the document layer --------------------------------------------------------

def test_distance_and_angle_orient_the_plane_and_flip_carries_them():
    d = Document()
    _box(d)
    # XY's frame: u = +X, n = +Z.  Angle 90 about u: n' = Z cos90 +
    # (X x Z) sin90 = -Y; Distance 4 THEN rides that rotated normal.
    o, n = d.set_section("XY", offset=4.0, angle=90.0)
    assert np.allclose(o, [0.0, -4.0, 0.0]) and np.allclose(n, [0, -1, 0])
    # 'Click Flip to switch which side to reveal.'  WHICH SIDE only:
    assert d.flip_section() is True
    o, n = d.section_frame()
    assert np.allclose(o, [0.0, -4.0, 0.0]) and np.allclose(n, [0, 1, 0])
    assert d._section["angle"] == 90.0          # the numbers SURVIVE the flip
    assert d.flip_section() and d._section["flip"] is False


def test_the_legacy_two_arg_voice_stands():
    d = Document()
    _box(d)
    o, n = d.set_section("YZ")                   # M135 mouths never grew
    assert list(o) == [0.0, 0.0, 0.0]           #   numbers: the frame is
    assert np.allclose(n, [1.0, 0.0, 0.0])      #   exactly the old one
    assert d._section["offset"] == 0.0 and d._section["angle"] == 0.0
    assert d._section["color"] == ""            # no dialog spoke
    fresh = Document()
    assert fresh.flip_section() is False        # nothing to flip


def test_cap_shading_wears_the_section_color_mode():
    d = Document()
    _box(d)
    d.bodies[0]["appearance"] = {"color": [0.2, 0.8, 0.2]}
    d.set_section("XY", offset=5.0)              # cap inside the slab
    # custom: the chosen colour shows up on caps, and skin stays ours
    d.set_section("XY", offset=5.0, color_mode="custom",
                  custom_color=[1.0, 0.0, 0.0])
    st = d.sectioned_display()[0]
    assert st is not None
    cs = st[3]
    reds = np.isclose(cs, np.tile([1.0, 0.0, 0.0], (len(cs), 1))).all(1)
    greens = np.isclose(cs, np.tile([0.2, 0.8, 0.2], (len(cs), 1))).all(1)
    assert reds.any() and greens.any()
    # From Component: caps wear their body's own colour - every face
    # (skin AND cap) carries it, so no red survives:
    d.set_section("XY", offset=5.0, color_mode="component")
    cs2 = d.sectioned_display()[0][3]
    assert np.isclose(cs2, np.tile([0.2, 0.8, 0.2], (len(cs2), 1))).all()
    # the empty (legacy) mode: the M135 accent cap, unchanged
    d.set_section("XY", offset=5.0)
    cs3 = d.sectioned_display()[0][3]
    accent = np.isclose(cs3, np.tile([0.16, 0.55, 0.85],
                                     (len(cs3), 1))).all(1)
    assert accent.any()


# ---- the door ------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(cmddialog, "_REMEMBERED", {})   # process-global
    monkeypatch.setattr(cmddialog, "_REMEMBER_ON", {})
    try:
        r = SceneRenderer()
    except Exception as e:
        pytest.skip(f"no headless GL: {e}")
    w = MainWindow(renderer=r)
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


def test_the_dialog_wears_the_page_name_rows_and_rests(win, monkeypatch):
    calls = []
    monkeypatch.setattr(cmddialog, "ask",
                        lambda p, t, fl, **k: (calls.append(
                            (t, [(f["key"], f["label"], f.get("default"))
                                 for f in fl], fl)), None)[1])
    win.new_document()
    _box(win.doc)
    win.action_section_analysis()
    (title, rows, specs), = calls
    assert title == "Section Analysis"           # PAGE-PRINTED callout
    keys = [k for k, _l, _d in rows]
    assert keys == ["plane", "dist", "ang", "flip", "color", "rgb"]
    # 'Angle (degrees)' rides NO mm suffix - the family spells degrees
    # and the page prints ' mm' zero times; Distance keeps the house
    # numeric voice (declared stamp, same coin as every number row).
    sp = {f["key"]: f for f in specs}
    assert sp["ang"].get("suffix", " mm") == ""
    assert sp["dist"].get("suffix", " mm") == " mm"
    labels = [l for _k, l, _d in rows]
    assert labels[0] == "Cut Plane"              # the page's words
    assert "Show Hatch" not in labels            # UNOFFERED-BY-NAME
    defaults = {k: d for k, _l, d in rows}
    assert defaults["color"] == "From Component"  # THE page-printed
    #   default: 'set to From Component by default' (the family's one)
    assert defaults["dist"] == 0.0 and defaults["ang"] == 0.0
    #   ("Default:" counts 0 -> house rests)
    assert defaults["flip"] is False             # 'Click Flip' = the change
    assert defaults["plane"] == "XY"             # house rest (the page
    #   prints no default plane - the origin planes ride first)


def test_the_empty_design_refuses_with_the_cure_words(win, monkeypatch):
    calls = []
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: (calls.append(1), None)[1])
    win.new_document()
    win.action_section_analysis()
    assert calls == []                            # no dialog to cancel
    assert win.status.currentMessage() == \
        "Nothing to measure yet — add a feature first"
    assert win.doc._section is None


def test_the_door_own_answer_places_and_speaks_the_page(win, monkeypatch):
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "plane": "XY", "dist": 4.0, "ang": 30.0, "flip": False,
        "color": "From Component", "rgb": ""})
    win.new_document()
    _box(win.doc)
    win.action_section_analysis()
    sec = win.doc._section
    assert sec["plane"] == "XY" and sec["offset"] == 4.0
    assert sec["angle"] == 30.0 and sec["color"] == "component"
    msg = win.status.currentMessage()
    assert msg.startswith("Section Analysis on XY (distance 4 mm, "
                          "angle 30 degrees)")
    assert msg.endswith("components it cuts through while it is visible")


def test_custom_color_refuses_before_touching_and_lands_when_honest(
        win, monkeypatch):
    win.new_document()
    _box(win.doc)
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "plane": "XY", "dist": 0.0, "ang": 0.0, "flip": False,
        "color": "Custom", "rgb": "chartreuse hope"})
    win.action_section_analysis()
    assert win.doc._section is None               # refusal BEFORE the state
    assert "r,g,b" in win.status.currentMessage()
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: {
        "plane": "XY", "dist": 0.0, "ang": 0.0, "flip": False,
        "color": "Custom", "rgb": "#ff8000"})
    win.action_section_analysis()
    assert win.doc._section["color"] == "custom"
    assert win.doc._section["custom"] == pytest.approx(
        [1.0, 128 / 255, 0.0])                    # 'enter a specific RGB value'


def test_mouths_and_the_page_quote_and_our_silences(win):
    entries = [a.text() for a in win.menuBar().actions()
               for a in (a.menu().actions() if a.menu() else [])]
    assert "Section Analysis…" in entries         # Tools menu mouth
    mouth = _mouth(MainWindow.action_section_analysis)
    for q in ("The Section Analysis dialog displays.",
              "select a planar object to define the",
              "Distance and Angle manipulator handles",
              "switch which side to reveal",
              'set to From Component by default',
              "Uses the color of each component to shade",
              "UNOFFERED"):
        assert q in mouth, q
    # the two declared absences, NAMED:
    assert "Show Hatch" in mouth and "hatch" in mouth.lower()
    assert "Analysis" in mouth                    # the browser folder
