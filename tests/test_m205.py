"""M201 R17 - the primitive family wears the PAGES' tools and words.

[SLD-CREATE-SOLID-PRIMITIVE, verbatim] "You can use the following
tools to create a solid body from a primitive shape:" - the pages
print ONE TOOL PER SHAPE ("On the toolbar, click Solid > Create >
Box") and ONE DIALOG EACH ("The Box dialog displays.").  The merged
M65 door - one "Primitive" dialog, a Shape combo, every size row of
every shape on screen at once - is not the vendor's shape and is
split here.

[SLD-*-SOLID, verbatim] the family's size voice is DIAMETER: "radius"
counts ZERO hits on every task page.  The doors take the pages'
words - Box "Length"/"Width"/"Height"; Cylinder "Diameter"+"Height";
Sphere "Diameter" (its ONE size row); Torus the page's two handles
"Inner Diameter"+"Torus Diameter".  LAW AT THE MOUTH: a typed
Diameter HALVES into the record's radius - the record voice (saved
files, the lever, the rail) moves not an inch.  Cone is a HOUSE
SHAPE (SLD-CONE-SOLID 404s; the panel's six are Box/Cylinder/Sphere/
Torus/Coil/Pipe) and is DECLARED so at its mouth; Coil and Pipe are
NOT offered - the kernel does not bake them and a door never promises
what cannot land.  The pages print ZERO defaults (grep "default": 0
hits) and no placement rows: every rest and the "place X/Y/Z" rows
are OURS, stamped.  Torus Position {Inside | On Center | Outside} is
not offered: its page glosses are self-referential (vendor DEFECT)
and the two-diameter door never asks the ambiguous single pick.
"""
import contextlib
import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QToolButton             # noqa

from tracer.core.document import PrimitiveFeature                   # noqa
from tracer.ui import cmddialog                                     # noqa
from tracer.ui.mainwindow import MainWindow                         # noqa
from tracer.ui.renderer import SceneRenderer                        # noqa


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
    w.new_document()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


@pytest.fixture(autouse=True)
def _clean_memory():
    yield
    for k in ("box", "cylinder", "sphere", "torus", "cone"):
        cmddialog._REMEMBERED.pop(f"primitive_{k}", None)
    cmddialog._REMEMBERED.pop("primitive", None)


class _Stop(Exception):
    """Raised from the capturing fake so a door that only-inspect
    tests never runs past ask() with a reply that lacks its size rows."""


def _capture_asks(win, monkeypatch, reply):
    calls = []

    def fake_ask(parent, title, fields, remember_key=None):
        calls.append((title, fields))
        raise _Stop                      # inspect the FIELDS, don't build
    monkeypatch.setattr(cmddialog, "ask", fake_ask)
    return calls


def _open(action):
    with contextlib.suppress(_Stop):
        action()


def _script(monkeypatch, reply):
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: dict(reply))


def _box_button(win):
    for i in range(win.ribbon.dl.count()):
        it = win.ribbon.dl.itemAt(i).widget()
        if (isinstance(it, QToolButton)
                and it.toolTip().split(" \u2014 ")[0] == "Box"):
            return it
    return None


# ---- the family's mouths ---------------------------------------------------

def test_the_merged_primitive_button_became_the_pages_flyout(win):
    """"Solid > Create > Box" - the button wears the FIRST tool's name
    and its arrow opens the family in the pages' printed order (Box,
    Cylinder, Sphere, Torus), Cone last as the declared house shape.
    No ribbon mouth still says "Primitive", and no Coil/Pipe entry
    sneaks in: the kernel does not bake them."""
    b = _box_button(win)
    assert b is not None, "the Box tool left the ribbon"
    items = [a.text() for a in b.menu().actions() if a.text()]
    assert items == ["Box…", "Cylinder…", "Sphere…", "Torus…",
                     "Cone… (house tool)"], items
    tips = []
    for i in range(win.ribbon.dl.count()):
        it = win.ribbon.dl.itemAt(i).widget()
        if isinstance(it, QToolButton):
            tips.append(it.toolTip().split(" \u2014 ")[0])
    assert "Primitive" not in tips


def test_each_tool_opens_its_own_dialog_titled_the_tool(win, monkeypatch):
    """ONE dialog per tool, titled the tool's word ("The Cylinder
    dialog displays."), each showing ONLY its own size rows - the
    Shape combo is gone with the merged door."""
    for action, title, size_keys in (
            (win.action_box, "Box", ["length", "width", "height"]),
            (win.action_cylinder, "Cylinder", ["diameter", "height"]),
            (win.action_sphere, "Sphere", ["diameter"]),
            (win.action_torus, "Torus", ["torus_d", "inner_d"]),
            (win.action_cone, "Cone", ["bottom_d", "top_d", "height"])):
        calls = _capture_asks(win, monkeypatch, {})
        _open(action)
        assert len(calls) == 1 and calls[0][0] == title
        keys = [f["key"] for f in calls[0][1]]
        assert keys[:len(size_keys)] == size_keys
        assert "kind" not in keys                    # the picker is dead


def test_the_size_rows_wear_the_pages_words_not_radius(win, monkeypatch):
    """Box prints Length/Width/Height (verbatim page words); the
    round doors print Diameter - the word "radius" appears on NO page
    door's rows (Cone is the declared house tool and rides the family
    voice anyway)."""
    def labels_for(action):
        calls = _capture_asks(win, monkeypatch, {})
        _open(action)
        return [f["label"] for f in calls[0][1]]
    labs = labels_for(win.action_box)
    assert labs[:3] == ["Length (mm)", "Width (mm)", "Height (mm)"]
    assert any(l == "Diameter (mm)" for l in labels_for(win.action_cylinder))
    assert any(l == "Diameter (mm)" for l in labels_for(win.action_sphere))
    assert labels_for(win.action_torus)[:2] == ["Torus Diameter (mm)",
                                                "Inner Diameter (mm)"]
    for action in (win.action_box, win.action_cylinder,
                   win.action_sphere, win.action_torus):
        assert not any("radius" in l.lower() for l in labels_for(action))


def test_operation_rides_the_pages_printed_order(win, monkeypatch):
    """The task pages print "Join ... Cut ... Intersect ..." as the
    first three Operations; New Body is the separate house tool and
    New Component is "(Hybrid Design type only)" - not offered."""
    for action in (win.action_box, win.action_cylinder,
                   win.action_sphere, win.action_torus, win.action_cone):
        calls = _capture_asks(win, monkeypatch, {})
        _open(action)
        op = next(f for f in calls[0][1] if f["key"] == "op")
        assert op["label"] == "Operation"
        assert op["choices"] == ["Join", "Cut", "Intersect"]
        assert op["default"] == "Join"      # a STAMPED rest (0 defaults)


# ---- the DIAMETER law at the mouth ------------------------------------------

def test_a_typed_diameter_halves_into_the_records_radius(win, monkeypatch):
    """The door speaks the page, the RECORD keeps its own voice:
    typed 20 lands dims.radius 10 - and the volume proves the half is
    real geometry, not a label swap."""
    win.new_document()
    _script(monkeypatch, {"diameter": 20.0, "height": 30.0,
                          "op": "Join", "x": 0.0, "y": 0.0, "z": 0.0})
    win.action_cylinder()
    f = win.doc.features[-1]
    assert isinstance(f, PrimitiveFeature) and f.kind == "cylinder"
    assert f.dims == {"radius": 10.0, "height": 30.0}
    assert win.doc.result.volume == pytest.approx(math.pi * 100 * 30,
                                                  rel=1e-3)
    assert f.name == "Cylinder 1"          # the naming voice stands


def test_the_torus_pair_lands_the_ring_arithmetic(win, monkeypatch):
    """The page's handles are the OVERALL and the HOLE diameters:
    Torus 50 + Inner 30 -> major=(50+30)/4=20, minor=(50-30)/4=5,
    measured on the record AND by volume (2*pi^2*R*r^2)."""
    win.new_document()
    _script(monkeypatch, {"torus_d": 50.0, "inner_d": 30.0, "op": "Join",
                          "x": 0.0, "y": 0.0, "z": 0.0})
    win.action_torus()
    f = win.doc.features[-1]
    assert f.dims == {"major": 20.0, "minor": 5.0}
    assert win.doc.result.volume == pytest.approx(
        2 * math.pi ** 2 * 20 * 25, rel=2e-3)


def test_an_inner_not_smaller_refuses_before_the_capture(win, monkeypatch):
    """Inner Diameter 50 against Torus Diameter 50 composes NO tube:
    the door refuses by the page's own row words - no record, the
    body untouched, the undo stack never paid for."""
    win.new_document()
    _script(monkeypatch, {"torus_d": 50.0, "inner_d": 50.0, "op": "Join",
                          "x": 0.0, "y": 0.0, "z": 0.0})
    before = list(win.doc.features)
    win.action_torus()
    assert win.doc.features == before
    assert win.status.currentMessage() == \
        ("Torus refused: the Inner Diameter must be smaller "
         "than the Torus Diameter")


# ---- the record voice below the mouth ----------------------------------------

def test_the_rail_still_reads_the_records_own_radius(win, monkeypatch):
    """The lever and the rail are the RECORD's face (files move not
    an inch): a cylinder record still speaks "radius:" there, the
    page's diameter living only at the door's mouth."""
    win.new_document()
    _script(monkeypatch, {"diameter": 20.0, "height": 30.0, "op": "Join",
                          "x": 0.0, "y": 0.0, "z": 0.0})
    win.action_cylinder()
    f = win.doc.features[-1]
    win.rail.props.show_feature(f)
    txt = win.rail.props._body.text()
    assert "radius: 10" in txt and "height: 30" in txt
    assert "diameter" not in txt.lower()


def test_an_unknown_tool_word_refuses_by_name(win):
    """The door knows exactly the five tools; a word outside them is
    a caller bug and says so."""
    with pytest.raises(ValueError, match="no primitive tool"):
        win.action_primitive("Pyramid")


# ---- the declarations, pinned at their mouths ----------------------------------

def test_the_house_declarations_are_stamped_not_hidden():
    """Cone is DECLARED house wholesale (no page prints one; the
    sweep 404s its slug); the Torus Position omission names the
    vendor DEFECT behind it; the rests and placement rows sign the
    zero-defaults page law."""
    cone = " ".join(MainWindow.action_cone.__doc__.split())
    assert "DECLARED HOUSE SHAPE WHOLESALE" in cone
    assert "404s SLD-CONE-SOLID" in cone
    tor = " ".join(MainWindow.action_torus.__doc__.split())
    assert "self-referential" in tor and "DEFECT" in tor
    prim = " ".join(MainWindow.action_primitive.__doc__.split())
    assert "HALVES into the record's radius" in prim
    assert "ZERO printed defaults" in prim
    assert "place X/Y/Z" in prim
