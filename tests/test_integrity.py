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
        "INSERT INTO mapping"
        " (standard_id, clause_path, edition_from, config, version_from, kind, object_ref,"
        " note, confidence)"
        " VALUES ('fsbu-6-2020', '999', NULL, 'bp30', NULL, 'счёт', '01.01', NULL, 90)"
    )
    connection.commit()
    connection.close()

    violations = check(copy)
    assert any("mapping" in violation for violation in violations)


def test_mapping_with_unknown_edition_from_is_reported(corpus_db: Path, tmp_path: Path) -> None:
    """`edition_from` must name an edition that actually exists for the standard."""
    copy = tmp_path / "bad_edition_from.db"
    copy.write_bytes(corpus_db.read_bytes())
    connection = sqlite3.connect(copy)
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(
        "INSERT INTO mapping"
        " (standard_id, clause_path, edition_from, config, version_from, kind, object_ref,"
        " note, confidence)"
        " VALUES ('fsbu-6-2020', '1', 99, 'bp30', NULL, 'счёт', '01.01', NULL, 90)"
    )
    connection.commit()
    connection.close()

    violations = check(copy)
    assert any("edition_from" in violation for violation in violations)


def test_mapping_onto_a_zakluchenie_path_is_reported(corpus_db: Path, tmp_path: Path) -> None:
    """`.заключение` paths are ETL artefacts, not addressable projection targets."""
    copy = tmp_path / "mapping_zakluchenie.db"
    copy.write_bytes(corpus_db.read_bytes())
    connection = sqlite3.connect(copy)
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(
        "INSERT INTO mapping"
        " (standard_id, clause_path, edition_from, config, version_from, kind, object_ref,"
        " note, confidence)"
        " VALUES ('fsbu-6-2020', '13.заключение', NULL, 'bp30', NULL, 'счёт', '01.01', NULL, 90)"
    )
    connection.commit()
    connection.close()

    violations = check(copy)
    assert any("заключение" in violation for violation in violations)


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


def test_duplicate_effective_from_across_editions_is_reported(tmp_path: Path) -> None:
    """Defense in depth alongside `UNIQUE (standard_id, effective_from)` in
    schema.sql: a corpus built under an older schema, before that constraint
    existed, could still carry two editions of one standard tied on
    `effective_from` - `check()` must flag it even though a *fresh* build can
    no longer produce that state (see `test_db.py` for the constraint itself).
    """
    schema = (
        Path(__file__).resolve().parents[1] / "src" / "pbu_fsbu_mcp" / "schema.sql"
    ).read_text(encoding="utf-8")
    pre_fix_schema = schema.replace(",\n    UNIQUE (standard_id, effective_from)\n)", "\n)")
    assert "UNIQUE (standard_id, effective_from)\n" not in pre_fix_schema

    db_path = tmp_path / "tied_editions.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(pre_fix_schema)
    connection.execute(
        "INSERT INTO standard (id, kind, number, year, title, order_date, order_no,"
        " effective_from, source_url)"
        " VALUES ('test-std', 'ФСБУ', '1/2020', 2020, 'Тест', '2020-01-01', '1н',"
        " '2020-01-01', 'https://example.org')"
    )
    connection.execute(
        "INSERT INTO edition (id, standard_id, edition_no, effective_from)"
        " VALUES ('test-std@1', 'test-std', 1, '2020-01-01')"
    )
    connection.execute(
        "INSERT INTO edition (id, standard_id, edition_no, effective_from)"
        " VALUES ('test-std@2', 'test-std', 2, '2020-01-01')"
    )
    connection.execute(
        "INSERT INTO clause (id, standard_id, edition_id, path, text)"
        " VALUES ('test-std@1#1', 'test-std', 'test-std@1', '1', 'Текст пункта.')"
    )
    connection.execute("INSERT INTO clause_fts (clause_id, lemmas) VALUES ('test-std@1#1', 'текст пункт')")
    connection.execute(
        "INSERT INTO corpus_meta (built_at, registry_hash, source_snapshot_date)"
        " VALUES ('2026-01-01', 'x', '2026-01-01')"
    )
    connection.commit()
    connection.close()

    violations = check(db_path)
    assert any("одинаковой effective_from" in violation for violation in violations)


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
