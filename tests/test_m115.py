"""M115: the native 3MF writer — spec traps, materials, provenance.

Every assertion here maps to a [V] line of the Core 1.4.0 spec or the
fleet audit that motivated the writer (research stl_3mf_print_ready.md):
the OPC trio, the transform element order that explodes parts when
wrong, basematerials whose <base> REQUIRES both name and displaycolor,
explicit unit, element order for forward-only parsers, and the metadata
the trimesh writer never spoke.
"""
import re
import zipfile
from xml.etree import ElementTree as ET

import numpy as np
import pytest

from tracer.core import io as fio
from tracer.core import threemf


def _box(x0, y0, z0, dx, dy, dz):
    v = np.array([[x0, y0, z0], [x0 + dx, y0, z0], [x0 + dx, y0 + dy, z0],
                  [x0, y0 + dy, z0], [x0, y0, z0 + dz], [x0 + dx, y0, z0 + dz],
                  [x0 + dx, y0 + dy, z0 + dz], [x0, y0 + dy, z0 + dz]])
    f = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5],
                  [0, 5, 4], [2, 6, 7], [2, 7, 3], [1, 2, 6], [1, 6, 5],
                  [0, 4, 7], [0, 7, 3]])
    return v, f


def _body(name="Part", x0=0.0, y0=0.0, z0=0.0, **app):
    v, f = _box(x0, y0, z0, 10.0, 4.0, 2.0)
    return dict(name=name, vertices=v, faces=f, **app)


STEEL = {"appearance": {"name": "Steel", "color": [.55, .56, .58]},
         "material": "Steel"}


def _write(tmp_path, bodies, meta=None):
    p = tmp_path / "out.3mf"
    return threemf.write(p, bodies, meta), p


def _model(p):
    return zipfile.ZipFile(p).read("3D/3dmodel.model").decode()


# ---- package & root ------------------------------------------------------------
def test_package_is_the_opc_trio(tmp_path):
    _, p = _write(tmp_path, [_body()])
    assert zipfile.ZipFile(p).namelist() == ["[Content_Types].xml",
                                             "_rels/.rels",
                                             "3D/3dmodel.model"]
    rels = zipfile.ZipFile(p).read("_rels/.rels").decode()
    assert "/3D/3dmodel.model" in rels and "2013/01/3dmodel" in rels
    ct = zipfile.ZipFile(p).read("[Content_Types].xml").decode()
    assert "3dmanufacturing-3dmodel+xml" in ct


def test_root_is_core_only_never_requires_extensions(tmp_path):
    _, p = _write(tmp_path, [_body(**STEEL)])
    m = _model(p)
    root = re.search(r"<model[^>]*>", m).group()
    assert 'xmlns="http://schemas.microsoft.com/3dmanufacturing/' \
           'core/2015/02"' in root
    assert "requiredextensions" not in m and "ns0" not in m
    assert 'unit="millimeter"' in root          # explicit kills a bug class


def test_element_order_is_metadata_resources_build(tmp_path):
    _, p = _write(tmp_path, [_body()])
    m = _model(p)
    order = [m.index(x) for x in ("<metadata", "<resources>", "<build>")]
    assert order == sorted(order)


# ---- the transform trap (S2) ----------------------------------------------------
def test_transform_is_row_major_with_translation_last(tmp_path):
    # the materials spec's own example numbers: a part grounded FROM
    # (-27.7814, -52.0603, 0) must land with those as the LAST THREE
    v, f = _box(-27.7814, -52.0603, 0.0, 5, 5, 5)
    _, p = _write(tmp_path, [dict(name="P", vertices=v, faces=f)])
    item = re.search(r"<item[^>]*/>", _model(p)).group()
    assert 'transform="1 0 0 0 1 0 0 0 1 27.7814 52.0603 0"' in item


def test_whole_build_grounds_rigidly(tmp_path):
    a = _body("A")
    b = _body("B", x0=-5.0, z0=-3.0)
    _, p = _write(tmp_path, [a, b])
    items = re.findall(r"<item[^>]*/>", _model(p))
    assert len(items) == 2
    for it in items:                          # one shift, both bodies
        assert 'transform="1 0 0 0 1 0 0 0 1 5 0 3"' in it


def test_positive_octant_build_needs_no_transform(tmp_path):
    _, p = _write(tmp_path, [_body()])
    assert "transform" not in _model(p)       # clean bytes when honest


# ---- part identity, materials, provenance ----------------------------------------
def test_partnumbers_names_and_pairs(tmp_path):
    _, p = _write(tmp_path, [_body("Bracket"), _body("Knob")])
    m = _model(p)
    assert re.findall(r'<object id="\d" type="model" name="(\w+)"', m) \
        == ["Bracket", "Knob"]
    assert re.findall(r'partnumber="(\w+)"', m) == ["Bracket", "Knob"]


def test_basematerials_dedupe_and_binding(tmp_path):
    _, p = _write(tmp_path, [_body("A", **STEEL), _body("B", **STEEL),
                             _body("C", appearance={"name": "PLA",
                                                    "color": [.13, .733,
                                                              .298]})])
    root = ET.fromstring(_model(p))
    ns = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
    bases = root.findall(f"{ns}resources/{ns}basematerials/{ns}base")
    assert len(bases) == 2                    # identical paints share one
    assert all(b.get("name") and b.get("displaycolor") for b in bases)
    assert bases[0].get("displaycolor") == "#8C8F94FF"   # sRGB 8-digit
    objs = root.findall(f"{ns}resources/{ns}object")
    assert [o.get("pid") for o in objs] == ["1", "1", "1"]
    assert [o.get("pindex") for o in objs] == ["0", "0", "1"]


def test_unpainted_file_has_no_material_noise(tmp_path):
    _, p = _write(tmp_path, [_body()])
    m = _model(p)
    assert "basematerials" not in m and "pid=" not in m


def test_vendor_metadata_is_prefixed_not_forcing(tmp_path):
    _, p = _write(tmp_path, [_body("A", **STEEL)])
    m = _model(p)
    assert '<metadata name="tracer:Material" type="xs:string">Steel' \
        in m
    assert "requiredextensions" not in m      # naive parsers ignore,
    assert "xmlns:tracer" not in m            # never reject


def test_provenance_metadata(tmp_path):
    _, p = _write(tmp_path, [_body()],
                  {"title": "Bracket set", "designer": "Max",
                   "application": "Tracer Studio 0.0.1"})
    m = _model(p)
    for name, value in (("Title", "Bracket set"), ("Designer", "Max"),
                        ("Application", "Tracer Studio 0.0.1")):
        assert f'<metadata name="{name}">{value}</metadata>' in m
    assert re.search(r'<metadata name="CreationDate">'
                     r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", m)


# ---- the consumer oracle ----------------------------------------------------------
def test_trimesh_reads_what_we_wrote(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    _, p = _write(tmp_path, [_body("Bracket", **STEEL), _body("Knob")])
    scene = trimesh.load(str(p))
    assert sorted(scene.geometry) == ["Bracket", "Knob"]
    for g in scene.geometry.values():
        assert len(g.faces) == 12 and g.volume > 0


# ---- routed through io.export_solids ------------------------------------------
def _two_body_doc():
    from tracer.core.appearance import appearance
    from tracer.core.document import Document, PrimitiveFeature
    doc = Document("mb")
    doc.add(PrimitiveFeature(name="b", kind="box",
                             dims={"dx": 10.0, "dy": 10.0, "dz": 10.0},
                             placement=(0.0, 0.0, 0.0)))
    doc.add_body()
    doc.add(PrimitiveFeature(name="c", kind="box",
                             dims={"dx": 6.0, "dy": 6.0, "dz": 6.0},
                             placement=(30.0, 0.0, 0.0)))
    doc.set_body_appearance("Body 1", appearance("Anodized red"))
    doc.body_list()[1]["material"] = "Brass"
    return doc


def test_document_export_carries_its_voice(tmp_path):
    doc = _two_body_doc()
    out = fio.export_solids(doc.export_solids(), tmp_path / "two.3mf",
                            meta={"title": "Two", "designer": "Max"},
                            appearances=doc.export_appearances())
    m = _model(out)
    assert '<metadata name="Title">Two</metadata>' in m   # trimesh never
    assert '<metadata name="Application">Tracer Studio' in m
    assert ">Brass</metadata>" in m                 # tracer:Material
    assert 'displaycolor="#C72E29FF"' in m
    assert 'partnumber="Body 1"' in m and 'partnumber="Body 2"' in m
    scene = pytest.importorskip("trimesh").load(str(out))
    assert sorted(scene.geometry) == ["Body 1", "Body 2"]


def test_appearance_chain_resolves_default_too(tmp_path):
    from tracer.core.appearance import appearance
    doc = _two_body_doc()
    doc.appearance = appearance("Plastic white")
    recs = doc.export_appearances()
    assert recs["Body 1"]["appearance"]["name"] == "Anodized red"
    assert recs["Body 2"]["appearance"]["name"] == "Plastic white"
    assert recs["Body 2"]["material"] == "Brass"


def test_other_formats_take_the_trimesh_road(tmp_path):
    doc = _two_body_doc()
    stl = doc.export_solids()
    fio.export_solids(stl, tmp_path / "a.stl")
    fio.export_solids(stl, tmp_path / "a.obj")
    trimesh = pytest.importorskip("trimesh")
    for ext in ("stl", "obj"):
        got = trimesh.load(str(tmp_path / f"a.{ext}"), force="mesh")
        assert len(got.faces) > 20 and got.is_watertight
