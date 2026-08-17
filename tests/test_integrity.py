import sqlite3
from pathlib import Path

from etl.validate import check


def test_clean_corpus_has_no_violations(corpus_db: Path) -> None:
    assert check(corpus_db) == []


def test_dangling_mapping_is_reported(corpus_db: Path, tmp_path: Path) -> None:
    copy = tmp_path / "dirty.db"
    copy.write_bytes(corpus_db.read_bytes())
    connection = sqlite3.connect(copy)
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(
        "INSERT INTO mapping (clause_id, config, version_from, kind, object_ref, note, confidence)"
        " VALUES ('fsbu-6-2020@1#999', 'bp30', NULL, 'счёт', '01.01', NULL, 90)"
    )
    connection.commit()
    connection.close()

    violations = check(copy)
    assert any("mapping" in violation for violation in violations)


def test_clause_without_edition_is_reported(corpus_db: Path, tmp_path: Path) -> None:
    copy = tmp_path / "orphan.db"
    copy.write_bytes(corpus_db.read_bytes())
    connection = sqlite3.connect(copy)
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(
        "INSERT INTO clause (id, standard_id, edition_id, path, parent_path, heading, text)"
        " VALUES ('x@9#1', 'fsbu-6-2020', 'fsbu-6-2020@9', '1', NULL, NULL, 'Сирота')"
    )
    connection.commit()
    connection.close()

    violations = check(copy)
    assert any("clause" in violation for violation in violations)


def test_missing_fts_row_is_reported(corpus_db: Path, tmp_path: Path) -> None:
    copy = tmp_path / "nofts.db"
    copy.write_bytes(corpus_db.read_bytes())
    connection = sqlite3.connect(copy)
    connection.execute("DELETE FROM clause_fts WHERE clause_id = 'fsbu-6-2020@1#1'")
    connection.commit()
    connection.close()

    violations = check(copy)
    assert any("clause_fts" in violation for violation in violations)


def test_empty_corpus_meta_is_reported(corpus_db: Path, tmp_path: Path) -> None:
    """An empty corpus_meta previously passed validation and then made every
    tool call raise TypeError in Corpus.built_at()."""
    copy = tmp_path / "no_meta.db"
    copy.write_bytes(corpus_db.read_bytes())
    connection = sqlite3.connect(copy)
    connection.execute("DELETE FROM corpus_meta")
    connection.commit()
    connection.close()

    violations = check(copy)
    assert any("corpus_meta" in violation for violation in violations)


def test_dangling_parent_path_is_reported(corpus_db: Path, tmp_path: Path) -> None:
    """A typo'd parent_path must not silently degrade to parent_heading=None."""
    copy = tmp_path / "orphan_parent.db"
    copy.write_bytes(corpus_db.read_bytes())
    connection = sqlite3.connect(copy)
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(
        "INSERT INTO clause (id, standard_id, edition_id, path, parent_path, heading, text)"
        " VALUES ('fsbu-6-2020@1#999', 'fsbu-6-2020', 'fsbu-6-2020@1', '999', '888', NULL,"
        " 'Пункт со ссылкой на несуществующего родителя')"
    )
    connection.commit()
    connection.close()

    violations = check(copy)
    assert any("parent_path" in violation for violation in violations)


def test_empty_but_valid_corpus_is_rejected(tmp_path: Path) -> None:
    """The one failure mode this project already hit: schema fine, corpus empty."""
    empty = tmp_path / "empty.db"
    schema = (
        Path(__file__).resolve().parents[1] / "src" / "pbu_fsbu_mcp" / "schema.sql"
    ).read_text(encoding="utf-8")
    connection = sqlite3.connect(empty)
    connection.executescript(schema)
    connection.commit()
    connection.close()

    violations = check(empty)
    assert any("таблица пуста" in violation for violation in violations)
