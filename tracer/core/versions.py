"""Version chain (M111) — durable snapshots beside the file, never inside it.

Undo is RAM and dies with the process; versions are disk and don't.
A folder of gzipped JSON snapshots lives in
``<doc dir>/.tracer_versions/<stem>/`` — split from the document on
purpose (the file_locking doctrine): history stored INSIDE the file it
protects dies with a corrupted file.

One entry is appended per manual Save (an "auto point", rolling at
AUTO_KEEP).  NAMED versions survive the roll forever — the semantic
every CAD user already knows from the cloud ("a save is a version"),
delivered offline where the cloud product itself can't.  "Design
history" stays out of the naming: it means the parametric timeline
now, so this system is just **Versions**.

Restoring is NON-destructive by construction: :func:`read` hands back
a snapshot dict, the app loads it as unsaved work, and the next Save
appends a new head — the chain never truncates, history never lies.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from .io import load_json, write_json_atomic

AUTO_KEEP = 25
_FNAME = re.compile(r"^(\d{4})-(\d{8}T\d{6})-(\d{3})(?:-([^.]+))?\.json\.gz$")


def versions_dir(doc_path: str | Path) -> Path:
    p = Path(doc_path)
    return p.parent / ".tracer_versions" / p.stem


def _slug(name: str) -> str:
    keep = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name.strip())
    return keep[:24].strip("_") or "named"


@dataclass(frozen=True)
class Version:
    n: int
    stamp: str            # UTC "20261007T124103-417"
    name: str | None      # label of a NAMED version; None = auto point
    note: str
    path: Path

    @property
    def when(self) -> str:
        """Human stamp for lists: '2026-10-07 12:41 UTC'."""
        s = self.stamp
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[9:11]}:{s[11:13]} UTC"


def scan(d: Path) -> list[Version]:
    """Every readable version entry in a versions dir, oldest first."""
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.iterdir()):
        m = _FNAME.match(f.name)
        if not m:
            continue
        n = int(m.group(1))
        stamp = f"{m.group(2)}-{m.group(3)}"
        slug = m.group(4)
        name, note = slug, ""
        try:
            meta = load_json(f)
            name = meta.get("name") or slug
            note = meta.get("note", "")
        except Exception:           # unreadable meta still lists; read()
            pass                    # will raise honestly when asked
        out.append(Version(n, stamp, name, note, f))
    out.sort(key=lambda v: (v.n, v.stamp))
    return out


def list_versions(doc_path: str | Path) -> list[Version]:
    return scan(versions_dir(doc_path))


def append(doc_path: str | Path, doc: dict, *, name: str | None = None,
           note: str = "") -> Version:
    """Snapshot a document dict; auto points roll, named survive."""
    d = versions_dir(doc_path)
    d.mkdir(parents=True, exist_ok=True)
    prior = scan(d)
    n = (prior[-1].n + 1) if prior else 1
    t = time.time()
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(t)) \
        + f"-{int(t * 1000) % 1000:03d}"
    vpath = d / (f"{n:04d}-{stamp}" + (f"-{_slug(name)}" if name else "")
                 + ".json.gz")
    write_json_atomic({"n": n, "stamp": stamp, "name": name,
                       "note": note or "", "doc": doc}, vpath, gz=True)
    _roll(d)
    return Version(n, stamp, name, note or "", vpath)


def _roll(d: Path) -> None:
    """Drop the OLDEST auto points past AUTO_KEEP.  Named versions are
    never automatic collateral — the whole point of naming one."""
    autos = [v for v in scan(d) if v.name is None]
    for v in autos[:-AUTO_KEEP]:
        v.path.unlink(missing_ok=True)


def read(v: Version) -> dict:
    """The document dict stored in a version entry."""
    return load_json(v.path)["doc"]


def set_note(v: Version, note: str) -> None:
    data = load_json(v.path)
    data["note"] = note
    write_json_atomic(data, v.path, gz=True)


def name_version(v: Version, label: str) -> Version:
    """Pin an auto point as a NAMED version (it now outruns the roll)."""
    data = load_json(v.path)
    data["name"] = label
    new = v.path.with_name(f"{v.n:04d}-{v.stamp}-{_slug(label)}.json.gz")
    write_json_atomic(data, new, gz=True)
    if new != v.path:
        v.path.unlink(missing_ok=True)
    return Version(v.n, v.stamp, label, data.get("note", ""), new)


def delete(v: Version) -> None:
    v.path.unlink(missing_ok=True)