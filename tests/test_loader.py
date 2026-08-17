from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from pbu_fsbu_mcp.loader import load_all, load_standard

SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"


def test_loads_reference_standard() -> None:
    standard = load_standard(SOURCES / "fsbu-6-2020.yaml")
    assert standard.id == "fsbu-6-2020"
    assert standard.effective_from == date(2022, 1, 1)
    assert len(standard.editions) == 1


def test_reference_standard_has_clauses() -> None:
    standard = load_standard(SOURCES / "fsbu-6-2020.yaml")
    paths = {clause.path for clause in standard.editions[0].clauses}
    assert "1" in paths
    assert "4.а" in paths


def test_clause_ids_are_unique_within_edition() -> None:
    standard = load_standard(SOURCES / "fsbu-6-2020.yaml")
    clauses = standard.editions[0].clauses
    assert len({clause.id for clause in clauses}) == len(clauses)


def test_load_all_reads_directory() -> None:
    standards = load_all(SOURCES)
    assert any(standard.id == "fsbu-6-2020" for standard in standards)


def test_duplicate_clause_path_is_rejected(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text(
        dedent(
            """\
            id: broken-1-2020
            kind: ФСБУ
            number: "1/2020"
            year: 2020
            title: Тест
            order_date: 2020-01-01
            order_no: 1н
            effective_from: 2021-01-01
            effective_to: null
            superseded_by: null
            source_url: https://example.org/
            editions:
              - edition_no: 1
                amending_order: null
                effective_from: 2021-01-01
                clauses:
                  - path: "1"
                    parent_path: null
                    heading: null
                    text: Первый
                  - path: "1"
                    parent_path: null
                    heading: null
                    text: Дубль
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate clause path"):
        load_standard(broken)


def test_missing_edition_no_raises_value_error_with_path(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text(
        dedent(
            """\
            id: broken-1-2020
            kind: ФСБУ
            number: "1/2020"
            year: 2020
            title: Тест
            order_date: 2020-01-01
            order_no: 1н
            effective_from: 2021-01-01
            effective_to: null
            superseded_by: null
            source_url: https://example.org/
            editions:
              - amending_order: null
                effective_from: 2021-01-01
                clauses: []
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"broken\.yaml.*edition_no") as excinfo:
        load_standard(broken)
    assert str(broken) in str(excinfo.value)


def test_missing_clause_path_raises_value_error_with_path(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text(
        dedent(
            """\
            id: broken-1-2020
            kind: ФСБУ
            number: "1/2020"
            year: 2020
            title: Тест
            order_date: 2020-01-01
            order_no: 1н
            effective_from: 2021-01-01
            effective_to: null
            superseded_by: null
            source_url: https://example.org/
            editions:
              - edition_no: 1
                amending_order: null
                effective_from: 2021-01-01
                clauses:
                  - parent_path: null
                    heading: null
                    text: Пункт без пути.
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"broken\.yaml.*path") as excinfo:
        load_standard(broken)
    assert str(broken) in str(excinfo.value)


def test_load_all_rejects_duplicate_standard_id_across_files(tmp_path: Path) -> None:
    directory = tmp_path / "sources"
    directory.mkdir()
    duplicate = dedent(
        """\
        id: broken-1-2020
        kind: ФСБУ
        number: "1/2020"
        year: 2020
        title: Тест
        order_date: 2020-01-01
        order_no: 1н
        effective_from: 2021-01-01
        effective_to: null
        superseded_by: null
        source_url: https://example.org/
        editions: []
        """
    )
    (directory / "a.yaml").write_text(duplicate, encoding="utf-8")
    (directory / "b.yaml").write_text(duplicate, encoding="utf-8")

    with pytest.raises(ValueError, match="already declared"):
        load_all(directory)
