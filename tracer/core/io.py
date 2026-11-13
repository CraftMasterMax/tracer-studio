"""File I/O: mesh export/import (trimesh) and JSON documents."""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import trimesh

from .document import Document
from .geometry import Solid

MESH_EXPORT_FORMATS = {".stl": "stl", ".obj": "obj", ".3mf": "3mf", ".ply": "ply"}
MESH_IMPORT_EXTS = {".stl", ".obj", ".ply", ".3mf", ".gltf", ".glb"}

# M201 R16 [MESH-SAVE-AS-MESH, verbatim]: the door's two enums, in the
# page's PRINTED ORDER (steps order - the title orders them
# differently, and the steps row wins; the page itself prints that
# variant as a DEFECT we flag, never clone). Format's "(Binary)" and
# "(ASCII)" ride the word in parentheses, as printed.
MESH_AS_FORMATS = {
    "3MF": ".3mf", "STL (Binary)": ".stl", "STL (ASCII)": ".stl",
    "OBJ": ".obj",
}
# The page's Unit Type words. LAW: CONVERT, never reinterpret (the
# units menu's own law) - a 60 mm boss saved as Centimeter becomes
# SIX units in the file, the SAME boss. The page glosses only
# Centimeter ("One unit from the design equals one centimeter.") -
# the factor table is the house's arithmetic generalisation of that
# ONE printed sentence, and it says so at the door.
MESH_AS_UNITS = {
    "Centimeter": 0.1, "Millimeter": 1.0, "Meter": 0.001,
    "Inch": 1.0 / 25.4, "Foot": 1.0 / 304.8,
}


def write_json_atomic(obj, path: str | Path, *, indent: int | None = None,
                      gz: bool = False) -> Path:
    """Write JSON so a crash can never leave a half-file (M111).

    The bytes go to a sibling ``.tmp``, reach the disk (flush + fsync),
    and only then hop over the target in one ``os.replace`` — atomic
    inside a filesystem.  A power cut therefore leaves either the old
    file or the new one, never a truncated JSON: the promise that even
    cloud CAD prints in its docs ("a save that began is not lost"),
    kept at filesystem level.  Used for the .tracer document AND every
    sidecar (autosave, versions) — the safety net must be safer than
    what it protects.
    """
    path = Path(path)
    data = json.dumps(obj, indent=indent).encode("utf-8")
    if gz:
        data = gzip.compress(data, 1)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)     # the failed attempt leaves no corpse
        raise
    return path


def load_json(path: str | Path):
    """Read JSON written by write_json_atomic; gzip is sniffed, not asked."""
    raw = Path(path).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def export_solids(solids, path: str | Path, *, meta: dict | None = None,
                  appearances: dict | None = None,
                  unit: str | None = None,
                  stl_ascii: bool = False) -> Path:
    """Write each ``(name, Solid)`` as its OWN object (M105 multi-body).

    Two or more bodies become a named scene: 3MF/OBJ keep every body as
    a separate, addressable object (a slicer opens them as "Body 1",
    "Body 2"; a CAD tool reads distinct solids), while single-container
    formats (STL/PLY) get all the shells concatenated.  One body writes
    exactly the mesh it always did — the single-body file is byte-for-byte
    what Tracer produced before per-body export existed.

    M115: ``.3mf`` leaves through Tracer's own spec-exact writer —
    ``meta`` (title/designer/…) and ``appearances`` (body name →
    {"color", "opacity", "material", "name"}) then survive into the
    file: slicer colour slots, part labels and provenance included.
    The other formats keep taking the trimesh road.

    M201 R16 [MESH-SAVE-AS-MESH]: ``unit`` is a door Unit Type word
    (MESH_AS_UNITS) - the CONVERT law runs HERE, at the file's mouth:
    the vertices are scaled into that unit before they leave, and a
    3MF stamps its spec unit attribute to match (what the numbers
    MEAN); ``None`` - every legacy route - stays byte-for-byte
    today's millimetre file. ``stl_ascii`` writes the ASCII voice of
    STL (the page's "STL (ASCII)"; trimesh's plain "stl" has always
    been the "(Binary)" voice the whole house speaks).
    """
    if unit is not None and unit not in MESH_AS_UNITS:
        raise ValueError(f"the Unit Type is one of "
                         f"{', '.join(MESH_AS_UNITS)}, not {unit!r}")
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in MESH_EXPORT_FORMATS:
        raise ValueError(f"unsupported export format {ext!r}; "
                         f"use one of {sorted(MESH_EXPORT_FORMATS)}")
    parts = []
    for name, solid in solids:
        if solid is None:
            continue
        mesh = solid.to_trimesh()
        mesh.process(validate=True)          # watertight in slicers
        if unit is not None:
            mesh.apply_scale(MESH_AS_UNITS[unit])   # the CONVERT law
        parts.append((name or f"Body {len(parts) + 1}", mesh))
    if not parts:
        raise ValueError("nothing to export")
    if ext == ".3mf":
        from . import threemf
        bodies = [dict(name=n, vertices=m.vertices, faces=m.faces,
                       **{k: (appearances or {}).get(n, {}).get(k)
                          for k in ("appearance", "material")})
                  for n, m in parts]
        return threemf.write(path, bodies, meta,
                             unit=(unit or "Millimeter").lower())
    ftype = MESH_EXPORT_FORMATS[ext]
    if ext == ".stl" and stl_ascii:
        ftype = "stl_ascii"                  # the page's ASCII voice
    if len(parts) == 1:
        parts[0][1].export(str(path), file_type=ftype)
        return path
    geoms: dict = {}                         # unique names (no body lost)
    for name, mesh in parts:
        key, k = name, 2
        while key in geoms:
            key = f"{name} ({k})"
            k += 1
        geoms[key] = mesh
    trimesh.Scene(geoms).export(str(path), file_type=ftype)
    return path


def save_mesh_as(solids, path: str | Path, fmt: str, *,
                 unit: str = "Millimeter", structure: str = "One File",
                 meta: dict | None = None,
                 appearances: dict | None = None) -> list:
    """The Save As Mesh door's write step [MESH-SAVE-AS-MESH, verbatim]:
    the dialog carries EXACTLY three rows - Format {3MF | STL (Binary)
    | STL (ASCII) | OBJ}, Unit Type {Centimeter | Millimeter | Meter |
    Inch | Foot}, Structure {"One File: Saves all bodies in the
    component to a single file." | "One Body Per File: Saves each body
    in the component as separate files."} - then the file dialog.
    Returns every path written, in body order.

    The page prints NO defaults (word "default": zero hits) and NO
    naming scheme for the per-body files: where each body lands is
    OURS - the chosen path stands for One File, and One Body Per File
    rides "<stem> <body name><suffix>" (the browser name is the only
    name the house has). Unknown Format/Unit Type/Structure words
    refuse by name BEFORE any byte leaves: a refused door writes
    nothing, half a file included.
    """
    if fmt not in MESH_AS_FORMATS:
        raise ValueError(f"the Format is one of "
                         f"{', '.join(MESH_AS_FORMATS)}, not {fmt!r}")
    if unit not in MESH_AS_UNITS:
        raise ValueError(f"the Unit Type is one of "
                         f"{', '.join(MESH_AS_UNITS)}, not {unit!r}")
    if structure not in ("One File", "One Body Per File"):
        raise ValueError(f"the Structure is 'One File' or 'One Body Per "
                         f"File', not {structure!r}")
    path = Path(path)
    if not path.suffix:
        path = path.with_suffix(MESH_AS_FORMATS[fmt])
    ascii_voice = fmt == "STL (ASCII)"
    if structure == "One File":
        return [export_solids(list(solids), path, meta=meta,
                              appearances=appearances, unit=unit,
                              stl_ascii=ascii_voice)]
    out = []
    for name, solid in solids:
        p = path.with_name(f"{path.stem} {name}{path.suffix}")
        out.append(export_solids([(name, solid)], p, meta=meta,
                                 appearances=appearances, unit=unit,
                                 stl_ascii=ascii_voice))
    return out


def export_mesh(solid: Solid, path: str | Path) -> Path:
    return export_solids([("", solid)], path)


def import_mesh(path: str | Path) -> Solid:
    path = Path(path)
    loaded = trimesh.load(str(path), process=True, force="mesh")
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"could not load a mesh from {path.name!r}")
    if not loaded.is_watertight:
        loaded.fill_holes()
    return Solid.from_mesh(loaded.vertices, loaded.faces)


def save_document(doc: Document, path: str | Path) -> Path:
    path = Path(path)
    write_json_atomic(doc.to_dict(), path, indent=1)
    return path


def load_document(path: str | Path) -> Document:
    return Document.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
