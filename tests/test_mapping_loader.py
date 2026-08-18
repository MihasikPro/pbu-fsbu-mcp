from pathlib import Path

import pytest

from pbu_fsbu_mcp.loader import load_all, load_mappings
from pbu_fsbu_mcp.objects import load_catalog

ROOT = Path(__file__).resolve().parents[1] / "data" / "sources"
MAPPINGS = ROOT / "mappings" / "bp30"
CATALOG = load_catalog(ROOT / "objects" / "bp30.yaml")
STANDARDS = load_all(ROOT / "standards")


def test_loads_pilot_mapping_file() -> None:
    files = load_mappings(MAPPINGS, CATALOG, STANDARDS)
    assert any(item.standard_id == "fsbu-6-2020" for item in files)


def test_mapping_entries_are_parsed() -> None:
    file = next(
        item for item in load_mappings(MAPPINGS, CATALOG, STANDARDS) if item.standard_id == "fsbu-6-2020"
    )
    assert any(entry.object_ref == "01.01" for entry in file.mappings)


def test_unknown_object_ref_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text(
        "standard_id: fsbu-6-2020\nconfig: bp30\nversion_from: null\nmappings:\n"
        "  - clause_path: '4'\n    kind: счёт\n    object_ref: 'Счет.НетТакого'\n"
        "    note: null\n    confidence: 90\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown object_ref"):
        load_mappings(tmp_path, CATALOG, STANDARDS)


def test_low_confidence_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "weak.yaml"
    path.write_text(
        "standard_id: fsbu-6-2020\nconfig: bp30\nversion_from: null\nmappings:\n"
        "  - clause_path: '4'\n    kind: счёт\n    object_ref: '01.01'\n"
        "    note: null\n    confidence: 40\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="confidence"):
        load_mappings(tmp_path, CATALOG, STANDARDS)


def test_kind_must_match_catalog(tmp_path: Path) -> None:
    path = tmp_path / "mismatch.yaml"
    path.write_text(
        "standard_id: fsbu-6-2020\nconfig: bp30\nversion_from: null\nmappings:\n"
        "  - clause_path: '4'\n    kind: документ\n    object_ref: '01.01'\n"
        "    note: null\n    confidence: 90\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="kind"):
        load_mappings(tmp_path, CATALOG, STANDARDS)


def test_unknown_clause_path_is_rejected(tmp_path: Path) -> None:
    """`clause_path` must resolve to a real clause in *some* edition of the standard."""
    path = tmp_path / "no-such-clause.yaml"
    path.write_text(
        "standard_id: fsbu-6-2020\nconfig: bp30\nversion_from: null\nmappings:\n"
        "  - clause_path: '999'\n    kind: счёт\n    object_ref: '01.01'\n"
        "    note: null\n    confidence: 90\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="clause_path"):
        load_mappings(tmp_path, CATALOG, STANDARDS)


def test_zaklyuchenie_clause_path_is_rejected(tmp_path: Path) -> None:
    """A `.заключение` path is a clause-parser artifact, never a legitimate target."""
    path = tmp_path / "unstable-path.yaml"
    path.write_text(
        "standard_id: fsbu-6-2020\nconfig: bp30\nversion_from: null\nmappings:\n"
        "  - clause_path: '4.заключение'\n    kind: счёт\n    object_ref: '01.01'\n"
        "    note: null\n    confidence: 90\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="заключение"):
        load_mappings(tmp_path, CATALOG, STANDARDS)
