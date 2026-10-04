"""File I/O: mesh export/import (trimesh) and JSON documents."""
from __future__ import annotations

import json
from pathlib import Path

import trimesh

from .document import Document
from .geometry import Solid

MESH_EXPORT_FORMATS = {".stl": "stl", ".obj": "obj", ".3mf": "3mf", ".ply": "ply"}
MESH_IMPORT_EXTS = {".stl", ".obj", ".ply", ".3mf", ".gltf", ".glb"}


def export_mesh(solid: Solid, path: str | Path) -> Path:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in MESH_EXPORT_FORMATS:
        raise ValueError(f"unsupported export format {ext!r}; "
                         f"use one of {sorted(MESH_EXPORT_FORMATS)}")
    mesh = solid.to_trimesh()
    # merge_duplicate_vertices keeps exported files watertight in slicers
    mesh.process(validate=True)
    mesh.export(str(path), file_type=MESH_EXPORT_FORMATS[ext])
    return path


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
    path.write_text(json.dumps(doc.to_dict(), indent=1), encoding="utf-8")
    return path


def load_document(path: str | Path) -> Document:
    return Document.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
