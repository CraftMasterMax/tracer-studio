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


def export_solids(solids, path: str | Path) -> Path:
    """Write each ``(name, Solid)`` as its OWN object (M105 multi-body).

    Two or more bodies become a named scene: 3MF/OBJ keep every body as
    a separate, addressable object (a slicer opens them as "Body 1",
    "Body 2"; a CAD tool reads distinct solids), while single-container
    formats (STL/PLY) get all the shells concatenated.  One body writes
    exactly the mesh it always did — the single-body file is byte-for-byte
    what Tracer produced before per-body export existed.
    """
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
        parts.append((name or f"Body {len(parts) + 1}", mesh))
    if not parts:
        raise ValueError("nothing to export")
    if len(parts) == 1:
        parts[0][1].export(str(path), file_type=MESH_EXPORT_FORMATS[ext])
        return path
    geoms: dict = {}                         # unique names (no body lost)
    for name, mesh in parts:
        key, k = name, 2
        while key in geoms:
            key = f"{name} ({k})"
            k += 1
        geoms[key] = mesh
    trimesh.Scene(geoms).export(str(path), file_type=MESH_EXPORT_FORMATS[ext])
    return path


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
