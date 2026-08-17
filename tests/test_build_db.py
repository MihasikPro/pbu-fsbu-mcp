import sqlite3
from datetime import date
from pathlib import Path

from etl.build_db import build

SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"


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
