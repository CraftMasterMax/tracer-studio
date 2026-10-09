"""M130 — rename is a RELINK (browser polish ladder, rung one).

Fusion can rename anything freely because its references are internal
handles; our M125 datums are resolved BY NAME — mirrors name their
plane, coils their axis, lattice rails and circular patterns name
their pivot. A rename that only edited the string would silently arm
every one of them with part 3's ParamError. So renaming a datum here
rewrites the ledger atomically: the datum store plus every name-bound
field, counted and announced. Collisions are REFUSED, not
auto-suffix'd like Fusion does: one name must mean exactly one datum
for the resolver to mean anything. Duplicate FEATURE names, which
nothing resolves by, do get Fusion's "(1) (2)" browser suffix — as
display only; the model keeps the raw name.
"""
import pytest
from PySide6.QtWidgets import QApplication

from tracer.core import params
from tracer.core.document import Document, PrimitiveFeature


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
    w.resize(1000, 700)
    w.show()
    qapp.processEvents()
    w.new_document()
    qapp.processEvents()
    w._discard_guard = lambda: True
    yield w
    w._unsaved = False
    w.close()
    r.close()


def _bound_doc():
    """Plate + axis + plane, then one mirror (plane) and three axis
    binders (coil, circular, geometric incl. d1 rail; d2 stays a
    vector) — every field class rename_datum must survive."""
    d = Document()
    plate = d.add(PrimitiveFeature(name="plate", kind="box",
                                   dims={"dx": 20, "dy": 20, "dz": 4}))
    d.recompute()
    ax = d.add_axis_2pt((0, 0, 0), (0, 0, 10))
    pl = d.add_plane("XY", 4.0)
    old_ax, old_pl = ax["name"], pl["name"]
    d.add_mirror("mir", plate, plane=pl["name"])
    d.add_coil("coil", axis=ax["name"], base=(30, 0, 0),
               diameter=2, pitch=1, turns=2, size=0.5)
    d.add_circular_pattern("circ", plate, axis=ax["name"], count=3)
    d.add_geometric_pattern("geo", plate, axis=ax["name"], d1=ax["name"],
                            d2=(0, 1, 0), n1=2, n2=2, t1=40.0, t2=40.0)
    d.recompute()
    return d, old_ax, old_pl


# ---- core: the relink ----------------------------------------------------

def test_renaming_an_axis_retargets_every_named_binder():
    d, old_ax, _ = _bound_doc()
    assert d.datum_references(old_ax) == ["coil", "circ", "geo"]
    assert d.rename_datum(old_ax, "SpinLine") == 4   # axis, circ, geo, d1
    assert d.datum_references("SpinLine") == ["coil", "circ", "geo"]
    assert d.datum_references(old_ax) == []
    d.recompute()
    assert d.failed_feature is None                  # green, not armed


def test_vector_rail_survives_a_rename():
    d, old_ax, _ = _bound_doc()
    d.rename_datum(old_ax, "SpinLine")
    geo = d.features[-1]
    assert geo.d1 == "SpinLine"                      # named rail moved
    assert geo.d2 == (0.0, 1.0, 0.0)                 # literal vector: no


def test_the_store_dict_is_the_datum_rename_is_visible_through_it():
    d, old_ax, _ = _bound_doc()
    ax = d.axes[0]
    d.rename_datum(old_ax, "SpinLine")
    assert ax["name"] == "SpinLine"                  # in place, one truth


def test_renaming_a_plane_moves_the_mirror():
    d, _, old_pl = _bound_doc()
    assert d.rename_datum(old_pl, "MountFace") == 1
    assert d.datum_references("MountFace") == ["mir"]
    d.recompute()
    assert d.failed_feature is None


def test_collisions_are_refused_not_suffixed():
    # Fusion's "(1)" courtesy would be a lie for us: resolvers match on
    # name, so a second datum quietly renamed "X (1)" still means TWO
    # places for "X". Refuse, and the message names the cure.
    d, old_ax, old_pl = _bound_doc()
    for bad in ("", "   ", "XY", "X", old_ax):
        with pytest.raises(params.ParamError) as e:
            d.rename_datum(old_pl, bad)
        msg = str(e.value)
        assert "needs a name" in msg if bad.strip() == "" \
            else "already taken" in msg
    assert d.datum_references(old_pl) == ["mir"]     # nothing moved


def test_unknown_datum_and_no_op_rename():
    d, old_ax, _ = _bound_doc()
    with pytest.raises(params.ParamError) as e:
        d.rename_datum("Nope", "Whatever")
    assert "no datum named" in str(e.value)
    assert d.rename_datum(old_ax, old_ax) == 0       # same name: no ripple


def test_renamed_datums_round_trip_through_save():
    import tempfile
    from pathlib import Path
    from tracer.core.io import save_document, load_document
    d, old_ax, old_pl = _bound_doc()
    d.rename_datum(old_ax, "SpinLine")
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "r.tracer"
        save_document(d, p)
        r = load_document(p)
    assert [a["name"] for a in r.axes] == ["SpinLine"]
    r.recompute()
    assert r.failed_feature is None
    assert r.datum_references("SpinLine") == ["coil", "circ", "geo"]


# ---- UI: the prompt, the ripple message, undo, refusal --------------------

def _datum_win(win, qapp):
    d, old_ax, old_pl = _bound_doc()
    win.doc = d
    win._adopt_doc()
    win.recompute()
    qapp.processEvents()
    return old_ax, old_pl


def test_datum_rename_prompt_announces_the_ripple(win, qapp, monkeypatch):
    from tracer.ui.cmddialog import Shell
    old_ax, _ = _datum_win(win, qapp)
    monkeypatch.setattr(Shell, "getText",
                        staticmethod(lambda p, t, l, text="":
                                     ("SpinLine", True)))
    win._rename_datum("work axis", old_ax)
    qapp.processEvents()
    assert win.doc.datum_references("SpinLine") == ["coil", "circ", "geo"]
    assert "4 references retargeted" in win.status.currentMessage()
    win.undo()                                       # the rename undoes…
    assert win.doc.datum_references(old_ax) == ["coil", "circ", "geo"]
    assert win.doc.datum_references("SpinLine") == []   # …relink and all


def test_datum_rename_refusal_warns_and_changes_nothing(win, qapp,
                                                        monkeypatch):
    from tracer.ui.cmddialog import Shell
    import tracer.ui.mainwindow as mw
    old_ax, old_pl = _datum_win(win, qapp)
    monkeypatch.setattr(Shell, "getText",
                        staticmethod(lambda p, t, l, text="":
                                     (old_ax, True)))   # collide on purpose
    warned = []
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a[2])))
    depth = len(win._undo)
    win._rename_datum("work axis", old_pl)
    assert warned and "already taken" in warned[0]
    assert win.doc.datum_references(old_pl) == ["mir"]   # nothing moved
    assert len(win._undo) == depth            # the refused capture unwound


def test_datum_rows_carry_rename_in_their_menus():
    # the grammar is in the source of the menu builders: both datum
    # roles must offer Rename (before M130 they offered only Delete —
    # a named datum you can never rename is a named datum you fear)
    import inspect
    from tracer.ui.mainwindow import MainWindow
    for fn in (MainWindow._cplane_menu, MainWindow._caxis_menu):
        src = inspect.getsource(fn)
        assert "Rename…" in src and "_rename_datum" in src


# ---- browser display: Fusion's "(1)" disambiguation -----------------------

def test_duplicate_feature_names_show_numbered_but_stay_raw(win, qapp,
                                                            monkeypatch):
    win.doc.add(PrimitiveFeature(name="plate", kind="box",
                                 dims={"dx": 20, "dy": 20, "dz": 4}))
    win.doc.add(PrimitiveFeature(name="stud", kind="box",
                                 dims={"dx": 4, "dy": 4, "dz": 10}))
    win.recompute()
    # CITE-THE-MOVE (M152): this gate used to reach the duplicate state
    # through _rename_feature, which was a raw string write. Rename is
    # now M130's counted relink and a TAKEN name is refused by name
    # (G8) — so the gate mints the duplicate the way messy files arrive
    # (a direct field write, which the browser's disambiguation exists
    # to survive). The LAW below — "stud (1)"/"stud (2)" display over
    # raw names — stands untouched.
    win.doc.features[0].name = "stud"
    win.rail.tree.reload()
    qapp.processEvents()
    assert [f.name for f in win.doc.features] == ["stud", "stud"]

    labels = []

    def walk(it):
        for i in range(it.childCount()):
            ch = it.child(i)
            labels.append(ch.text(0))
            walk(ch)
    root = win.rail.tree.topLevelItem(0)
    assert root is not None
    walk(root)
    assert any(l.endswith("stud (1)") for l in labels)
    assert any(l.endswith("stud (2)") for l in labels)
    assert not any(l.rstrip().endswith("stud") for l in labels)
    assert win.doc.features[0].name == "stud"      # truth stays raw
