import sqlite3
from datetime import date
from pathlib import Path

import pytest

from etl.build_db import build

SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"

# Two YAML files that each pass the loader individually but collide on insert.
# Both declare the same top-level `id`, so the second file's `standard` row
# hits the table's PRIMARY KEY constraint. Colliding directly on the `clause`
# table's UNIQUE(edition_id, path) is unreachable: the loader always derives
# `edition.standard_id` from the top-level `id`, so two files whose clauses
# would collide on `edition_id` necessarily collide on `standard.id` first -
# and that fails before a single clause of the second file is inserted. This
# still exercises a genuine insert-phase failure (past the loader, mid-build).
_COLLIDING_STANDARD_A = """\
id: exp-std-collision
kind: ФСБУ
number: "1/2099"
year: 2099
title: Экспериментальный стандарт А
order_date: 2020-01-01
order_no: 1н
effective_from: 2020-01-01
effective_to: null
superseded_by: null
source_url: https://example.org/a
editions:
  - edition_no: 1
    amending_order: null
    effective_from: 2020-01-01
    clauses:
      - path: "1"
        parent_path: null
        heading: Раздел А
        text: Текст пункта из первого файла.
"""

_COLLIDING_STANDARD_B = """\
id: exp-std-collision
kind: ФСБУ
number: "1/2099"
year: 2099
title: Экспериментальный стандарт Б
order_date: 2020-01-01
order_no: 1н
effective_from: 2020-01-01
effective_to: null
superseded_by: null
source_url: https://example.org/b
editions:
  - edition_no: 1
    amending_order: null
    effective_from: 2020-01-01
    clauses:
      - path: "1"
        parent_path: null
        heading: Раздел Б
        text: Текст пункта из второго файла с тем же путем.
"""


def _write_colliding_sources(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "a.yaml").write_text(_COLLIDING_STANDARD_A, encoding="utf-8")
    (directory / "b.yaml").write_text(_COLLIDING_STANDARD_B, encoding="utf-8")


def _build(tmp_path: Path) -> Path:
    output = tmp_path / "corpus.db"
    build(SOURCES, output, built_at=date(2026, 8, 14))
    return output


def test_build_creates_database_file(tmp_path: Path) -> None:
    assert _build(tmp_path).exists()


def test_standard_row_is_written(tmp_path: Path) -> None:
    connection = sqlite3.connect(_build(tmp_path))
    row = connection.execute(
        "SELECT kind, title, order_no FROM standard WHERE id = ?", ("fsbu-6-2020",)
    ).fetchone()
    assert row == ("ФСБУ", "Основные средства", "204н")


def test_clause_text_round_trips(tmp_path: Path) -> None:
    connection = sqlite3.connect(_build(tmp_path))
    (text,) = connection.execute(
        "SELECT text FROM clause WHERE id = ?", ("fsbu-6-2020@1#1",)
    ).fetchone()
    assert "устанавливает требования" in text


def test_fts_index_is_lemmatised(tmp_path: Path) -> None:
    connection = sqlite3.connect(_build(tmp_path))
    rows = connection.execute(
        "SELECT clause_id FROM clause_fts WHERE clause_fts MATCH ?", ("требование",)
    ).fetchall()
    assert ("fsbu-6-2020@1#1",) in rows


def test_corpus_meta_is_written(tmp_path: Path) -> None:
    connection = sqlite3.connect(_build(tmp_path))
    (built_at,) = connection.execute("SELECT built_at FROM corpus_meta").fetchone()
    assert built_at == "2026-08-14"


def test_rebuild_replaces_previous_database(tmp_path: Path) -> None:
    output = _build(tmp_path)
    build(SOURCES, output, built_at=date(2026, 8, 15))
    connection = sqlite3.connect(output)
    rows = connection.execute("SELECT COUNT(*) FROM corpus_meta").fetchone()
    assert rows == (1,)


def test_failed_rebuild_leaves_existing_database_untouched(tmp_path: Path) -> None:
    output = tmp_path / "db" / "corpus.db"
    build(SOURCES, output, built_at=date(2026, 8, 14))

    connection = sqlite3.connect(output)
    (clause_count_before,) = connection.execute("SELECT COUNT(*) FROM clause").fetchone()
    connection.close()
    assert clause_count_before > 0

    bad_sources = tmp_path / "bad_sources"
    _write_colliding_sources(bad_sources)

    with pytest.raises(sqlite3.IntegrityError):
        build(bad_sources, output, built_at=date(2026, 8, 16))

    connection = sqlite3.connect(output)
    (clause_count_after,) = connection.execute("SELECT COUNT(*) FROM clause").fetchone()
    connection.close()
    assert clause_count_after == clause_count_before


def test_failed_rebuild_leaves_no_temporary_file(tmp_path: Path) -> None:
    output = tmp_path / "db" / "corpus.db"
    build(SOURCES, output, built_at=date(2026, 8, 14))

    bad_sources = tmp_path / "bad_sources"
    _write_colliding_sources(bad_sources)

    with pytest.raises(sqlite3.IntegrityError):
        build(bad_sources, output, built_at=date(2026, 8, 16))

    assert sorted(p.name for p in output.parent.iterdir()) == [output.name]
