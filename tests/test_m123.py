"""M123 — the fastener library's provenance law: no value ships uncited.

The tables moved from Python literals into data/*.json, each carrying
its standard, edition, sources and verification date. This file is the
CI enforcer: it validates every registered table's schema AND checks
the numbers against each OTHER — standards corroborate one another, so
a typo or a folklore regression in one table trips on a neighbour's
agreement (e.g. an ISO 7089 washer ID IS the ISO 273 medium hole).
"""
import json
import re
from pathlib import Path

import pytest

from tracer.core import fasteners as F

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SIZE_RE = re.compile(r"^M\d+(\.\d+)?$")
REQUIRED = ("$schema", "key", "standard", "edition", "title", "unit",
            "columns", "verified", "provenance", "notes", "license",
            "data")


def _raw(key):
    return json.loads((Path(F.__file__).parent / "data" / F.TABLES[key])
                      .read_text(encoding="utf-8"))


def test_every_data_file_is_registered():
    files = {p.name for p in (Path(F.__file__).parent / "data").glob("*.json")}
    assert files == set(F.TABLES.values())        # no orphan, no ghost


def test_every_table_carries_full_provenance():
    for key in F.TABLES:
        raw = _raw(key)
        missing = [f for f in REQUIRED if f not in raw or raw[f] in ("", None, [])]
        assert not missing, f"{key}: {missing}"
        assert raw["key"] == key
        assert DATE_RE.match(raw["verified"]), f"{key}: bad verified date"
        assert isinstance(raw["provenance"], list) and raw["provenance"]
        assert all(isinstance(s, str) and len(s) > 10 for s in raw["provenance"])


def test_cells_are_sane_numbers_on_known_sizes():
    for key in F.TABLES:
        raw = _raw(key)
        ncols = len(raw["columns"])
        assert raw["unit"] == "mm"
        assert raw["data"], key
        for size, row in raw["data"].items():
            assert SIZE_RE.match(size), f"{key}: odd size label {size!r}"
            assert len(row) == ncols, f"{key}/{size}: arity"
            for v in row:
                assert 0 < float(v) < 100, f"{key}/{size}: {v} mm?"


def test_module_constants_are_the_files_not_stale_literals():
    """The bug that motivated M123: values living twice drift. Python
    must now be a pure view of the JSON."""
    for key, view in (("clearance", F.CLEARANCE), ("shcs_head", F.SHCS_HEAD)):
        raw = _raw(key)
        for size, row in raw["data"].items():
            assert tuple(map(float, row)) == tuple(view[size])
    raw_ins = _raw("insert")
    assert {s: float(v[0]) for s, v in raw_ins["data"].items()} == F.INSERT


# ---- cross-standard invariants (they corroborate each other) ----------

def test_clearance_rows_increase_and_cover_the_nominal():
    for size, (close, med, coarse) in F.CLEARANCE.items():
        assert F.nominal(size) <= close < med < coarse, size


def test_washer_ids_are_the_iso_273_close_holes():
    """Physical agreement between two standards: a normal washer's bore
    IS the ISO 273 close (H12) clearance for the same thread — all seven
    sizes agree cell-for-cell. If either table is mistyped this trips."""
    for size, (wid, od, th) in F.WASHERS["normal"].items():
        assert wid == pytest.approx(F.clearance(size, "close")), size
        assert wid < od and th > 0, size


def test_small_washers_are_smaller_than_normal():
    for size in F.WASHERS["small"]:
        _, small_od, _ = F.WASHERS["small"][size]
        _, norm_od, _ = F.WASHERS["normal"][size]
        assert small_od < norm_od, size          # the point of the series


def test_shcs_head_covers_every_clearance_and_insert_bore():
    for size, (head, height) in F.SHCS_HEAD.items():
        assert head > F.clearance(size, "coarse"), size
        assert height > 0, size
        dia, dep = F.cbore(size)
        assert dia == pytest.approx(round(head + 0.5, 2))
        assert dep == pytest.approx(round(height + 0.2, 2))


def test_insert_bore_outgrows_the_biggest_hole_it_replaces():
    for size, bore in F.INSERT.items():
        assert bore > F.clearance(size, "coarse"), size


# ---- API surface -------------------------------------------------------

def test_washer_accessor_round_and_errors():
    assert F.washer("M6") == (6.4, 12.0, 1.6)
    assert F.washer("M6", "small") == (6.4, 11.0, 1.6)
    with pytest.raises(KeyError):
        F.washer("M6", "jumbo")
    with pytest.raises(KeyError):
        F.washer("M27")


def test_provenance_api_feeds_the_ui():
    p = F.provenance("clearance")
    assert p["standard"] == "ISO 273" and p["verified"]
    with pytest.raises(KeyError):
        F.provenance("nope")


def test_hole_dialog_names_the_standard_it_used():
    """The point of M123: a preset is never an unsourced magic Ø."""
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])     # offscreen-safe singleton
    from tracer.ui.hole import HoleDialog
    d = HoleDialog(None, [6.0])
    d.std.setCurrentText("Clearance")
    assert "ISO 273" in d._prov.text()
    assert d._head0 not in d.head.text()          # preset filled the dialog
    d.std.setCurrentText("Socket head (cbore)")
    assert "DIN 912" in d._prov.text()
    d.std.setCurrentText("Custom (Ø from sketch)")
    assert d._prov.text() == ""                   # nothing sourced, nothing claimed
