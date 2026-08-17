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
