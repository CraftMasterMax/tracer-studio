"""3MF written by hand — spec-correct, metadata-rich, zero new deps (M115).

Tracer already shipped 3MF through trimesh, and the fleet audit against
the Core 1.4.0 spec found its output valid but voiceless: NO document
metadata (who made this? with what? when?), NO colours or materials
(a steel body and a PLA body leave identically), and six namespace
declarations repeated on every build item.

This writer speaks the part. Everything it needs from the spec was
verified against the consortium's own markdown (research
``stl_3mf_print_ready.md``): ZIP/Deflate with the OPC trio, the single
core namespace (``<basematerials>`` is a CORE element — no extensions,
so NO requiredextensions to choke naive consumers), explicit
``unit="millimeter"``, element order metadata → resources → build
(forward-only parsers), ``<base>`` requiring both name and colour,
colours as sRGB ``#RRGGBBAA``, vendor metadata prefixed by convention
(``tracer:Material``), and the classic trap: ``<item transform>`` is
twelve row-major values with the TRANSLATION LAST.

Print-readness follows the spec's SHOULDs the cheap way: the whole
build is grounded so Z sits on the plate and negative X/Y steps onto
the bed (a per-item transform — vertices are never touched), winding
and watertightness come free from the manifold kernel, and every body
keeps its own object + partnumber so slicers list "Bracket, Knob"
instead of "Object 1, Object 2".

Pure stdlib (zipfile + xml.etree + datetime); takes plain arrays so it
is testable without the kernel.
"""
from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
CTYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
MODEL_CT = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    f'<Types xmlns="{CTYPES}">'
    '<Default Extension="rels" ContentType='
    '"application/vnd.openxmlformats-package.relationships+xml"/>'
    f'<Default Extension="model" ContentType="{MODEL_CT}"/>'
    '</Types>')
RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    f'<Relationships xmlns="{RELS}">'
    '<Relationship Id="rel-1" Target="/3D/3dmodel.model" Type='
    '"http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    '</Relationships>')


def _num(v: float) -> str:
    """Compact exact-enough coordinate text: 0.1 µm resolution, no
    trailing zero noise (27.7814 stays 27.7814, 2.0 becomes 2)."""
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def _hex(color, opacity: float = 1.0) -> str:
    """0-1 rgb triplet -> the spec's sRGB '#RRGGBBAA' (8 digits)."""
    r, g, b = (max(0, min(255, round(c * 255))) for c in color[:3])
    a = max(0, min(255, round(float(opacity) * 255)))
    return f"#{r:02X}{g:02X}{b:02X}{a:02X}"


def write(path: str | Path, bodies: list[dict], meta: dict | None = None
          ) -> Path:
    """Write a print-ready 3MF.

    ``bodies``: dicts of ``{name, vertices, faces}`` (+ optional
    ``appearance`` {"name","color","opacity"} and ``material`` str).
    ``meta``: optional ``title`` / ``designer`` / ``description`` /
    ``application``. Returns the path written.
    """
    if not bodies:
        raise ValueError("nothing to export")
    meta = meta or {}

    # ground the build: Z onto the plate, negative XY onto the bed —
    # one rigid translation per item, the model's own coordinates live
    # on untouched in the vertices (the spec's SHOULD, priced at 12
    # numbers per body).
    mins = [min((float(v[i]) for b in bodies for v in b["vertices"]),
                default=0.0) for i in range(3)]
    shift = (max(0.0, -mins[0]), max(0.0, -mins[1]), -mins[2])
    moved = any(abs(s) > 1e-9 for s in shift)

    ET.register_namespace("", CORE)
    core = f"{{{CORE}}}"

    def _el(parent, tag, attrs=None):
        return ET.SubElement(parent, core + tag, attrs or {})

    model = ET.Element(core + "model", {"unit": "millimeter"})
    _el(model, "metadata", {"name": "Application"}
        ).text = str(meta.get("application") or "Tracer Studio")
    if meta.get("title"):
        _el(model, "metadata", {"name": "Title"}).text = str(meta["title"])
    if meta.get("designer"):
        _el(model, "metadata", {"name": "Designer"}
            ).text = str(meta["designer"])
    if meta.get("description"):
        _el(model, "metadata", {"name": "Description"}
            ).text = str(meta["description"])
    _el(model, "metadata", {"name": "CreationDate"}
        ).text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    resources = _el(model, "resources")

    # one core basematerials group; distinct material+colour pairs
    # dedupe into it, and every painted body binds by pid/pindex.
    bases: list[tuple[str, str]] = []
    painted = [b for b in bodies if (b.get("appearance") or {}).get("color")]
    group = None
    if painted:
        group = _el(resources, "basematerials", {"id": "1"})
    for b in painted:
        app = b["appearance"]
        label = str(app.get("name") or b.get("material")
                    or b["name"] or "Material")
        col = _hex(app["color"], app.get("opacity", 1.0))
        pair = (label, col)
        if pair not in bases:
            bases.append(pair)
            _el(group, "base", {"name": label, "displaycolor": col})
        b["_pindex"] = bases.index(pair)

    for i, b in enumerate(bodies, start=1):
        attrs = {"id": str(i), "type": "model"}
        if b.get("name"):
            attrs["name"] = str(b["name"])
        if group is not None and "_pindex" in b:
            attrs["pid"] = "1"
            attrs["pindex"] = str(b["_pindex"])
        obj = _el(resources, "object", attrs)
        mesh = _el(obj, "mesh")
        verts = _el(mesh, "vertices")
        for v in b["vertices"]:
            _el(verts, "vertex", {"x": _num(float(v[0])),
                                  "y": _num(float(v[1])),
                                  "z": _num(float(v[2]))})
        tris = _el(mesh, "triangles")
        for f in b["faces"]:
            _el(tris, "triangle", {"v1": str(int(f[0])),
                                   "v2": str(int(f[1])),
                                   "v3": str(int(f[2]))})
        # vendor metadata (prefixed by convention, no XML namespace —
        # a slicer that never heard of Tracer simply ignores it)
        material = b.get("material") or (b.get("appearance") or {}).get("name")
        colour = (b.get("appearance") or {}).get("color")
        if material or colour:
            mg = _el(obj, "metadatagroup")
            if material:
                _el(mg, "metadata", {"name": "tracer:Material",
                                     "type": "xs:string"}
                    ).text = str(material)
            if colour:
                _el(mg, "metadata", {"name": "tracer:Colour",
                                     "type": "xs:string"}
                    ).text = _hex(colour, (b["appearance"]
                                           or {}).get("opacity", 1.0))

    build = _el(model, "build")
    for i, b in enumerate(bodies, start=1):
        item = _el(build, "item", {"objectid": str(i)})
        if b.get("name"):
            item.set("partnumber", str(b["name"]))
        if moved:
            # row-major, translation LAST — the one detail that puts
            # every part on the bed instead of orbiting the scene
            item.set("transform", "1 0 0 0 1 0 0 0 1 "
                                  + " ".join(_num(s) for s in shift))

    for b in bodies:
        b.pop("_pindex", None)

    xml_bytes = ET.tostring(model, encoding="utf-8",
                            xml_declaration=True)
    path = Path(path)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS_XML)
        z.writestr("3D/3dmodel.model", xml_bytes)
    return path
