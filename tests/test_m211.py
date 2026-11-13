"""M201 R23 - the fillet half grows the Fillet reference rows.

[SLD-REF-FILLET, verbatim] "The Fillet dialog displays." - the door's
title is the page's word.  Rows in the page's printed order: Type,
Radius, Radius Type, Continuity, Corner Type, Rule, Round/Fillets -
every one resting at the ONLY member this kernel bakes ("Rule Fillet:
Rounds edges based on rules that determine which edges to fillet." -
this door's rule is every sharp edge; "Rounds and Fillets: Creates
convex rounds on all outside corners and concave fillets on all
inside corners." - rim_fillet subtracts at convex rims and unions
beads at concave ones, that sentence in code).  m196's honesty gate
pinned the half at one row UNTIL THIS RUNG; the record's
BodyFilletFeature voice did not move an inch.  "Radius ... in the
units of the current design." rides the document's own unit.  DEFECT
flagged not cloned: the task page double-prints the Variable label
("Variable Variable").  Tangent Chain's "checked by default" (the
family's only printed default) is honoured as OURS stands: the All-
Edges rule fillets the widest chain there is.
"""
import contextlib
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                                # noqa

from tracer.core import step                                              # noqa
from tracer.core.document import BodyFilletFeature, PrimitiveFeature      # noqa
from tracer.ui import cmddialog                                           # noqa
from tracer.ui.mainwindow import MainWindow                               # noqa
from tracer.ui.renderer import SceneRenderer                              # noqa


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


class _Stop(Exception):
    pass


def _rows(win, monkeypatch):
    calls = []

    def fake(parent, title, fields, **k):
        calls.append((title, fields, k))
        return None                                    # cancel: no born
    monkeypatch.setattr(cmddialog, "ask", fake)
    win.new_document()
    win.doc.features.append(PrimitiveFeature(name="B", kind="box",
                                             dims={"dx": 30, "dy": 30,
                                                   "dz": 6}))
    win.doc.dirty = True
    win.doc.recompute()
    with contextlib.suppress(_Stop):
        win._body_fillet(chamfer=False)
    return calls[0]


def _plate(win):
    win.new_document()
    win.doc.add_plate("Plate1", 40, 40, 10, holes=[(20, 20, 5.0)])
    win.doc.dirty = True
    win.doc.recompute()
    return win.doc


# ---- the rows the page prints --------------------------------------------------

def test_the_door_wears_the_pages_rows_in_page_order(win, qapp,
                                                     monkeypatch):
    title, fields, kw = _rows(win, monkeypatch)
    assert title == "Fillet"                       # "The Fillet dialog
    #   displays." - the page's own dialog word (m196's placeholder
    #   title "Fillet body edges" was OURS, not the vendor's)
    assert kw.get("remember_key") == "fillet_body_edges"
    by = {f["key"]: f for f in fields}
    assert list(by) == ["type", "radius", "rtype", "cont", "corner",
                        "rule", "rf"]              # the page's order
    assert by["type"]["label"] == "Type"
    assert list(by["type"]["choices"]) == ["Rule Fillet"]
    assert by["radius"]["label"] == "Radius (mm)"  # the doc's unit
    assert by["rtype"]["label"] == "Radius Type"
    assert list(by["rtype"]["choices"]) == ["Constant"]
    assert by["cont"]["label"] == "Continuity"
    assert list(by["cont"]["choices"]) == ["Tangent (G1)"]
    assert by["corner"]["label"] == "Corner Type"
    assert list(by["corner"]["choices"]) == ["Rolling Ball"]
    assert by["rule"]["label"] == "Rule"
    assert list(by["rule"]["choices"]) == ["All Edges"]
    assert by["rf"]["label"] == "Round/Fillets"
    assert list(by["rf"]["choices"]) == ["Rounds and Fillets"]
    for k in ("type", "rtype", "cont", "corner", "rule", "rf"):
        assert by[k]["default"] == by[k]["choices"][0]
    assert not any(isinstance(f, BodyFilletFeature)
                   for f in win.doc.features)      # cancelled, nothing


def test_the_words_the_kernel_cannot_bake_stay_unoffered(win, qapp,
                                                         monkeypatch):
    """Every family the reference prints but NOTHING here bakes: the
    selection-driven Fillet type, the Center Face type, the chord /
    per-point / per-side radius kinds, G2, Setback, the two-set rule,
    the half topologies, the selection rows."""
    _title, fields, _kw = _rows(win, monkeypatch)
    words = [w for f in fields for w in
             ([f["label"]] + list(f.get("choices", [])))]
    for absent in ("Full Round Fillet", "Chord Length", "Variable",
                   "Asymmetric", "Curvature (G2)", "Setback",
                   "Between Faces/Features", "Rounds Only",
                   "Fillets Only", "Tangent Chain", "Tangency Weight"):
        assert absent not in words, absent
    # the bare selection-driven type word never rides this dialog:
    # the only FILLET-flavoured words it prints are its own title's
    # members - "Rule Fillet" and "Rounds and Fillets"
    assert "Fillet" not in [w for w in words if w != "Rule Fillet"
                            and w != "Rounds and Fillets"]


# ---- the rests land today's exact feature --------------------------------------

def test_the_rests_land_m196s_exact_feature(win, qapp, monkeypatch):
    monkeypatch.setattr(step, "available", lambda: False)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"radius": 2.0})
    d = _plate(win)
    base = d.result.volume
    win._body_fillet(chamfer=False)
    qapp.processEvents()
    f = d.features[-1]
    assert isinstance(f, BodyFilletFeature) and not f.chamfer
    assert f.radius == 2.0 and f.angle_deg is None and f.dist2 is None
    assert f.n_rims == 2                    # convex AND concave rims:
    assert d.result.volume != base          # the page's one sentence


# ---- the guards, from the outside ------------------------------------------------

def test_a_scripted_selection_type_refuses_before_the_capture(
        win, qapp, monkeypatch):
    monkeypatch.setattr(step, "available", lambda: False)
    d = _plate(win)
    n = len(d.features)
    depth = len(win._undo)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"type": "Fillet",
                                         "radius": 2.0})
    win._body_fillet(chamfer=False)
    assert len(d.features) == n
    assert len(win._undo) == depth, "a refused Type paid an undo step"
    msg = win.status.currentMessage()
    assert "'Rule Fillet'" in msg and "Full Round Fillet" in msg, msg


def test_a_scripted_half_topology_refuses(win, qapp, monkeypatch):
    monkeypatch.setattr(step, "available", lambda: False)
    d = _plate(win)
    n = len(d.features)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"rf": "Rounds Only",
                                         "radius": 2.0})
    win._body_fillet(chamfer=False)
    assert len(d.features) == n
    msg = win.status.currentMessage()
    assert "half the body" in msg and "Rounds Only" in msg, msg


def test_a_scripted_g2_or_setback_refuses(win, qapp, monkeypatch):
    monkeypatch.setattr(step, "available", lambda: False)
    d = _plate(win)
    n = len(d.features)
    for key, word, needle in (("cont", "Curvature (G2)",
                               "Tangent (G1)"),
                              ("corner", "Setback", "Rolling Ball")):
        monkeypatch.setattr(cmddialog, "ask",
                            lambda *a, kw=key, **k: {"radius": 2.0,
                                                     kw: word})
        win._body_fillet(chamfer=False)
        assert len(d.features) == n, key
        assert needle in win.status.currentMessage(), key
    assert n == len(d.features)


def test_a_scripted_between_features_rule_refuses(win, qapp,
                                                  monkeypatch):
    monkeypatch.setattr(step, "available", lambda: False)
    d = _plate(win)
    n = len(d.features)
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: {"rule": "Between Faces/Features",
                                         "radius": 2.0})
    win._body_fillet(chamfer=False)
    assert len(d.features) == n
    assert "two" in win.status.currentMessage() and \
        "All Edges" in win.status.currentMessage()


# ---- the source itself cites its pages (codec-pinned, the LAW) ------------------

def test_the_door_cites_its_pages_in_the_source():
    src = (Path(__file__).resolve().parent.parent / "tracer" / "ui" /
           "mainwindow.py").read_text(encoding="utf-8")
    i = src.index("def _body_fillet")
    j = src.index("\n    def ", i)          # exactly this one method:
    #   the next def at method indent ends the window, so the gate can
    #   never spill into a sibling lever's getDouble (the edit door is
    #   a future rung's own job)
    seg = "\n".join(l.split("#", 1)[1] if l.lstrip().startswith("#")
                    else l for l in src[i:j].splitlines())
    body = " ".join(seg.split())            # comment wraps are layout,
    #   not content - the sigils shed, the page quotes read as printed
    assert "The Fillet dialog displays." in body
    assert "Rounds edges based on rules that determine which edges " \
           "to fillet." in body
    assert "Creates convex rounds on all outside corners and concave " \
           "fillets on all inside corners." in body
    assert "Specify the radius value for the fillet in the units of " \
           "the current design." in body
    assert "Variable Variable" in body             # DEFECT, flagged
    assert "checked by" in body                    # the family's one
    #   printed default, honoured as our rule already stands
    # and the EDIT lever stays the honest single number: THIS method's
    # own body no longer touches getDouble at all
    assert "getDouble" not in body
