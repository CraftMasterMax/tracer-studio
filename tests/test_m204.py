"""M201 R16 - Save As Mesh wears the page's three rows.

[MESH-SAVE-AS-MESH, verbatim] "Use the Save As Mesh tool to export a
mesh body from a design in Fusion to a 3MF, OBJ, or STL file." The
dialog carries EXACTLY THREE rows in steps order: Format {3MF | STL
(Binary) | STL (ASCII) | OBJ}, Unit Type {Centimeter | Millimeter |
Meter | Inch | Foot}, Structure {One File | One Body Per File} -
then the file dialog. "default" counts ZERO on the page, so all
three rests (STL (Binary), Millimeter, One File) are OURS, stamped;
the page glosses only Centimeter ("One unit from the design equals
one centimeter.") and the kernel's factor table is the house's
arithmetic GENERALISATION of that one printed sentence - the CONVERT
law: a 60 mm boss saved as Centimeter leaves as SIX, the same boss.

The page's DEFECT - "The Save STL dialog displays." after OK
whatever the Format - is not cloned stale: the file dialog wears the
CHOSEN format's name. The trigger is the Browser right-click and
ONLY that (File > Export appears on NEITHER page of this family);
the page's component half waits for the components rung. Unknown
Format/Unit Type/Structure words refuse by name BEFORE any byte
leaves - a refused door writes nothing, half a file included. The
3MF writer stamps its spec unit attribute to match what the numbers
mean (Core 1.4.0 ST_Unit: micron, millimeter, centimeter, inch,
foot, meter - Meter IS among them).
"""
import pytest

pytest.importorskip("PySide6")

import numpy as np                                                  # noqa
from PySide6.QtCore import QPoint                                   # noqa
from PySide6.QtWidgets import QApplication, QMenu                   # noqa

from conftest import script_cmd                                     # noqa
from tracer.core import io as fio                                   # noqa
from tracer.core import threemf                                     # noqa
from tracer.core.document import PrimitiveFeature                   # noqa
from tracer.ui import cmddialog                                     # noqa
from tracer.ui.mainwindow import MainWindow                         # noqa
from tracer.ui.renderer import SceneRenderer                        # noqa

pytest.importorskip("trimesh")
import trimesh                                                      # noqa


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
    w.doc.add_plate("plate", 60, 10, 2)
    w.recompute()
    qapp.processEvents()
    yield w
    w._unsaved = False
    w.close()
    r.close()


@pytest.fixture(autouse=True)
def _clean_memory():
    yield
    cmddialog._REMEMBERED.pop("save_as_mesh", None)


def _two_bodies(doc):
    """The proven m202 recipe: open a body, feed it a feature."""
    doc.add_body("Body 2")
    doc.add(PrimitiveFeature(name="peg", kind="cylinder",
                             dims={"radius": 2.0, "height": 5.0}))
    doc.recompute()


# ---- the mouths the page licenses ---------------------------------------------

def test_the_body_row_wears_the_page_mouth(win, monkeypatch):
    """"In the Design workspace, right-click a component or body in
    the Browser. Select Save As Mesh." - the Browser body row is the
    ONLY trigger; the captured menu carries the page's words."""
    seen = {}

    def fake_exec(self, *a, **k):
        seen["labels"] = [x.text() for x in self.actions()
                          if x.text()]
        return None
    monkeypatch.setattr(QMenu, "exec_", fake_exec, raising=True)
    win._body_menu("Body 1", QPoint(10, 10))
    assert "Save As Mesh…" in seen["labels"], seen["labels"]


def test_the_door_carries_exactly_the_pages_three_rows(win, monkeypatch):
    """ONE dialog, three rows in steps order, enums verbatim (the
    steps order wins over the title's variant listing - the page's
    own printed inconsistency is flagged, never cloned); the rests
    are OURS (the page prints no defaults)."""
    calls = []

    def spy(parent, title, fields, remember_key=None):
        calls.append((title, [(f["key"], f["label"], f["choices"],
                               f.get("default")) for f in fields]))
        return None
    monkeypatch.setattr(cmddialog, "ask", spy)
    win.action_save_as_mesh("Body 1")
    title, rows = calls[0]
    assert title == "Save As Mesh"
    assert [k for k, *_ in rows] == ["fmt", "unit", "struct"]
    assert [r[1] for r in rows] == ["Format", "Unit Type", "Structure"]
    fmt, unit, struct = (r[2:] for r in rows)
    assert fmt == (["3MF", "STL (Binary)", "STL (ASCII)", "OBJ"],
                   "STL (Binary)")
    assert unit == (["Centimeter", "Millimeter", "Meter", "Inch",
                     "Foot"], "Millimeter")
    assert struct == (["One File", "One Body Per File"], "One File")


def test_no_dialog_no_file_dialog_no_bytes(win, monkeypatch, tmp_path):
    """A door CANCELLED at the dialog never reaches the file dialog,
    and a file dialog CANCELLED never writes: neither cancel leaves
    the folder as it was (nothing is ever born)."""
    from PySide6.QtWidgets import QFileDialog
    target = tmp_path / "never.stl"
    monkeypatch.setattr(cmddialog, "ask", lambda *a, **k: None)
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("file dialog reached after cancel"))))
    win.action_save_as_mesh("Body 1")
    script_cmd(monkeypatch, {"fmt": "STL (Binary)", "unit": "Millimeter",
                             "struct": "One File"})
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    win.action_save_as_mesh("Body 1")
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_the_file_dialog_wears_the_CHOSEN_format(win, monkeypatch,
                                                 tmp_path):
    """The page prints "The Save STL dialog displays." after OK for
    EVERY format - a stale DEFECT, NOT cloned: choose 3MF, the file
    dialog says Save 3MF file."""
    asked = {}
    target = tmp_path / "model.3mf"

    def grab_title(parent, title, *a, **k):
        asked["title"] = title
        return str(target), ""
    from PySide6.QtWidgets import QFileDialog
    script_cmd(monkeypatch, {"fmt": "3MF", "unit": "Millimeter",
                             "struct": "One File"})
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(grab_title))
    win.action_save_as_mesh("Body 1")
    assert asked["title"] == "Save 3MF file", asked
    assert target.exists()
    assert win.status.currentMessage() == \
        f"Saved Body 1 as 3MF to {target}"


# ---- the CONVERT law at the file's mouth ---------------------------------------

def _parts(win):
    return win.doc.export_solids()


def test_a_centimeter_file_holds_centimeters(win, tmp_path):
    """60 mm x 10 mm x 2 mm: the page's ONE glossed sentence says
    one unit equals one centimeter - so the file's numbers are
    6 x 1 x 0.2, THE SAME BOSS, counted at the bounds."""
    p = fio.save_mesh_as(_parts(win), tmp_path / "cm.stl",
                         "STL (Binary)", unit="Centimeter")[0]
    m = trimesh.load(str(p))
    assert np.allclose(m.extents, [6.0, 1.0, 0.2], atol=1e-6)


def test_inch_and_meter_ride_the_same_arithmetic(win, tmp_path):
    p = fio.save_mesh_as(_parts(win), tmp_path / "in.stl",
                         "STL (Binary)", unit="Inch")[0]
    m = trimesh.load(str(p))
    assert np.allclose(m.extents, [60 / 25.4, 10 / 25.4, 2 / 25.4],
                       atol=1e-6)
    p = fio.save_mesh_as(_parts(win), tmp_path / "m.stl",
                         "STL (Binary)", unit="Meter")[0]
    m = trimesh.load(str(p))
    assert np.allclose(m.extents, [0.06, 0.01, 0.002], atol=1e-9)


def test_millimeter_rests_where_the_house_always_stood(win, tmp_path):
    """The stamped rest is the legacy route: Millimeter and the
    silent None agree to the last face."""
    a = fio.export_solids(_parts(win), tmp_path / "a.stl")
    b = fio.save_mesh_as(_parts(win), tmp_path / "b.stl",
                         "STL (Binary)")[0]
    ma, mb = trimesh.load(str(a)), trimesh.load(str(b))
    assert np.allclose(ma.extents, [60.0, 10.0, 2.0], atol=1e-9)
    assert np.array_equal(mb.extents, ma.extents)
    assert len(mb.faces) == len(ma.faces)


def test_the_two_stl_voices_are_two_voices(win, tmp_path):
    """The page's "(Binary)" and "(ASCII)" are the SAME format in
    two printed voices - the files show it: ASCII opens with the
    "solid" keyword, binary opens with an 80-byte header."""
    pa = fio.save_mesh_as(_parts(win), tmp_path / "a.stl",
                          "STL (ASCII)")[0]
    pb = fio.save_mesh_as(_parts(win), tmp_path / "b.stl",
                          "STL (Binary)")[0]
    head_a = open(pa, "rb").read(64)
    head_b = open(pb, "rb").read(64)
    assert head_a.startswith(b"solid") and b"facet" in head_a
    assert not head_b.startswith(b"solid")
    m = trimesh.load(str(pa))
    assert np.allclose(m.extents, [60.0, 10.0, 2.0], atol=1e-6)


def test_the_3mf_stamps_what_the_numbers_mean(win, tmp_path):
    """Core 1.4.0 ST_Unit prints six words - meter among them - so
    a meter file DECLARES meter (the attribute says what the
    numbers mean; the vertices already moved). An unknown word
    refuses by name at the writer too."""
    import zipfile
    p = fio.save_mesh_as(_parts(win), tmp_path / "m.3mf", "3MF",
                         unit="Meter")[0]
    x = zipfile.ZipFile(p).read("3D/3dmodel.model").decode()
    assert 'unit="meter"' in x
    assert np.allclose(trimesh.load(str(p)).extents,
                       [0.06, 0.01, 0.002], atol=1e-9)
    from tracer.core.document import Document
    with pytest.raises(ValueError, match="micron, millimeter"):
        threemf.write(tmp_path / "bad.3mf",
                      [dict(name="b", vertices=[[0, 0, 0], [1, 0, 0],
                                                 [0, 1, 0]],
                            faces=[[0, 1, 2]])], {}, unit="furlong")


def test_refusals_name_the_voice_and_write_nothing(win, tmp_path):
    """Unknown Format/Unit Type/Structure words refuse BEFORE any
    byte leaves (the door law, at the kernel mouth too): the
    sentence names the voices the caller failed."""
    ghost = tmp_path / "ghost.stl"
    for bad, needle in (
            (dict(fmt="GLTF"), "the Format is one of"),
            (dict(fmt="STL (Binary)", unit="Furlong"), "the Unit Type"),
            (dict(fmt="STL (Binary)", structure="Two Files"),
             "the Structure is")):
        with pytest.raises(ValueError, match=needle):
            fio.save_mesh_as(_parts(win), ghost, bad["fmt"],
                             unit=bad.get("unit", "Millimeter"),
                             structure=bad.get("structure", "One File"))
        assert not ghost.exists()


def test_one_body_per_file_lands_one_file_per_body(win, tmp_path):
    """Structure's per-body branch at the kernel mouth (the door
    saves ONE body, so the branches collapse there - proven here):
    two bodies, two files, named "<stem> <body name>" - OURS, the
    page prints no naming scheme."""
    _two_bodies(win.doc)
    qapp = QApplication.instance()
    qapp.processEvents()
    paths = fio.save_mesh_as(win.doc.export_solids(),
                             tmp_path / "two.obj", "OBJ",
                             structure="One Body Per File")
    names = sorted(p.name for p in paths)
    assert names == ["two Body 1.obj", "two Body 2.obj"], names
    assert all(p.exists() for p in paths)
    one = fio.save_mesh_as(win.doc.export_solids(),
                           tmp_path / "all.obj", "OBJ",
                           structure="One File")
    assert len(one) == 1 and one[0].exists()


def test_the_door_refuses_a_body_without_a_solid(win, monkeypatch):
    """A scripted body name the browser no longer knows refuses with
    the M197 door law whole: no dialog, no file, the sentence names
    it."""
    monkeypatch.setattr(cmddialog, "ask",
                        lambda *a, **k: pytest.fail("door opened"))
    assert win.status is not None
    win.action_save_as_mesh("Ghost body")
    assert "has no solid to save" in win.status.currentMessage()


def test_the_declarations_are_pinned_at_the_door():
    """The stamped rests, the not-cloned defect and the CONVERT law
    all SIGN at the door docstring."""
    d = " ".join(MainWindow.action_save_as_mesh.__doc__.split())
    assert '"default" counts ZERO on the page' in d
    assert "not cloned stale" in d
    assert "leaves as SIX, the same boss" in d
