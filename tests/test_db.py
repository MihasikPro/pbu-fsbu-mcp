import sqlite3
from datetime import date
from pathlib import Path

import pytest
import yaml

from etl.build_db import build
from pbu_fsbu_mcp.db import ClauseNotFound, Corpus, StandardNotFound
from pbu_fsbu_mcp.models import MappingStatus, StandardStatus

TODAY = date(2026, 8, 14)
SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


def test_list_standards_returns_reference_standard(corpus: Corpus) -> None:
    ids = [item.id for item in corpus.list_standards(TODAY)]
    assert "fsbu-6-2020" in ids


def test_list_standards_marks_status(corpus: Corpus) -> None:
    summary = next(item for item in corpus.list_standards(TODAY) if item.id == "fsbu-6-2020")
    assert summary.status is StandardStatus.ACTIVE


def test_list_standards_before_effective_date(corpus: Corpus) -> None:
    summary = next(
        item for item in corpus.list_standards(date(2021, 6, 1)) if item.id == "fsbu-6-2020"
    )
    assert summary.status is StandardStatus.NOT_YET


def test_get_standard_raises_for_unknown_id(corpus: Corpus) -> None:
    with pytest.raises(StandardNotFound):
        corpus.get_standard("fsbu-999-1999", TODAY)


def test_outline_lists_paths_in_document_order(corpus: Corpus) -> None:
    outline = corpus.outline("fsbu-6-2020", TODAY)
    paths = [path for path, _heading in outline]
    assert paths[:2] == ["1", "2"]


def test_get_clause_returns_text_and_provenance(corpus: Corpus) -> None:
    clause = corpus.get_clause("fsbu-6-2020", "1", TODAY)
    assert "устанавливает требования" in clause.text
    assert clause.edition_no == 1
    assert clause.order_ref == "приказ Минфина России от 17.09.2020 № 204н"
    assert clause.as_of_date == TODAY


def test_get_clause_resolves_parent_heading(corpus: Corpus) -> None:
    clause = corpus.get_clause("fsbu-6-2020", "4.а", TODAY)
    assert clause.parent_path == "4"
    assert clause.parent_heading == "Общие положения"


def test_get_clause_raises_with_available_paths(corpus: Corpus) -> None:
    with pytest.raises(ClauseNotFound) as excinfo:
        corpus.get_clause("fsbu-6-2020", "999", TODAY)
    assert "1" in excinfo.value.available_paths


def test_built_at_is_read_from_meta(corpus: Corpus) -> None:
    assert corpus.built_at() == date(2026, 8, 14)


def test_warnings_is_empty_for_a_freshly_built_corpus(corpus: Corpus) -> None:
    assert corpus.warnings() == []


def test_warnings_reports_a_stale_corpus(tmp_path: Path) -> None:
    output = tmp_path / "stale.db"
    build(SOURCES, output, built_at=date(2000, 1, 1))
    stale_corpus = Corpus(output)
    assert any("пересборка корпуса" in warning for warning in stale_corpus.warnings())


def test_corpus_connection_rejects_writes(corpus: Corpus) -> None:
    """The read-only mode is what makes the server safe as an immutable container."""
    with pytest.raises(sqlite3.OperationalError):
        corpus._connection.execute("DELETE FROM clause")


def test_clause_13_text_does_not_contain_the_concluding_sentence(corpus: Corpus) -> None:
    """Clause 13's text must stop at the lead-in; а)/б) sit between it and the conclusion."""
    clause = corpus.get_clause("fsbu-6-2020", "13", TODAY)
    assert "Выбранный способ последующей оценки" not in clause.text


def test_clause_13_conclusion_is_its_own_child_clause(corpus: Corpus) -> None:
    clause = corpus.get_clause("fsbu-6-2020", "13.заключение", TODAY)
    assert clause.parent_path == "13"
    assert "Выбранный способ последующей оценки" in clause.text


def test_clause_13_reports_children_in_document_order(corpus: Corpus) -> None:
    clause = corpus.get_clause("fsbu-6-2020", "13", TODAY)
    assert clause.children == ["13.а", "13.б", "13.заключение"]


@pytest.fixture
def two_edition_corpus(tmp_path: Path) -> Corpus:
    """One standard, two editions, one unverified `mapping` row gated to the second edition.

    Purpose-built rather than reusing `corpus_db`: the point of this test is that
    `mapping_status` follows `mapping.edition_from` across an amendment, which
    needs a standard with more than one edition and a mapping row inserted by
    hand (Plan 3 has not added a mapping-loading tool yet).
    """
    standards_dir = tmp_path / "sources" / "standards"
    standards_dir.mkdir(parents=True)
    (standards_dir / "test-std.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "test-std",
                "kind": "ФСБУ",
                "number": "99/2099",
                "year": 2020,
                "title": "Тестовый стандарт с двумя редакциями",
                "order_date": "2020-01-01",
                "order_no": "1н",
                "effective_from": "2020-01-01",
                "source_url": "https://example.org/test-std",
                "editions": [
                    {
                        "edition_no": 1,
                        "amending_order": None,
                        "effective_from": "2020-01-01",
                        "clauses": [
                            {
                                "path": "1",
                                "parent_path": None,
                                "heading": None,
                                "text": "Текст пункта 1 первой редакции.",
                            }
                        ],
                    },
                    {
                        "edition_no": 2,
                        "amending_order": "2н",
                        "effective_from": "2022-01-01",
                        "clauses": [
                            {
                                "path": "1",
                                "parent_path": None,
                                "heading": None,
                                "text": "Текст пункта 1 второй редакции.",
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "corpus.db"
    build(standards_dir, output, built_at=TODAY)

    connection = sqlite3.connect(output)
    connection.execute(
        "INSERT INTO mapping"
        " (standard_id, clause_path, edition_from, config, version_from, kind, object_ref,"
        " note, confidence)"
        " VALUES ('test-std', '1', 2, 'bp30', NULL, 'счёт', '01.01', NULL, 90)"
    )
    connection.commit()
    connection.close()

    return Corpus(output)


def test_mapping_status_is_none_before_the_edition_it_applies_from(
    two_edition_corpus: Corpus,
) -> None:
    """The mapping row targets edition 2; on a date when edition 1 is in force
    (edition 2 takes effect 2022-01-01), it must not count."""
    summary = two_edition_corpus.get_standard("test-std", date(2021, 1, 1))
    assert summary.mapping_status is MappingStatus.NONE


def test_mapping_status_is_draft_from_the_edition_it_applies_from(
    two_edition_corpus: Corpus,
) -> None:
    """The row inserted by `two_edition_corpus` carries no `verified` column,
    so it defaults to unverified - the standard must report DRAFT, not VERIFIED."""
    summary = two_edition_corpus.get_standard("test-std", date(2023, 1, 1))
    assert summary.mapping_status is MappingStatus.DRAFT


def test_list_standards_mapping_status_matches_get_standard(
    two_edition_corpus: Corpus,
) -> None:
    """`list_standards` computes `mapping_status` in a single batched query -
    it must agree with `get_standard`'s per-standard answer on both sides of
    the edition boundary."""
    before = {item.id: item for item in two_edition_corpus.list_standards(date(2021, 1, 1))}
    after = {item.id: item for item in two_edition_corpus.list_standards(date(2023, 1, 1))}
    assert before["test-std"].mapping_status is MappingStatus.NONE
    assert after["test-std"].mapping_status is MappingStatus.DRAFT


def test_mapping_status_is_verified_only_when_every_applicable_row_is(
    tmp_path: Path,
) -> None:
    """A standard whose only applicable mapping row has `verified = 1` must report
    VERIFIED, not just "has some mapping" - that distinction is the whole point
    of `MappingStatus` over the old `has_1c_mapping` bool."""
    standards_dir = tmp_path / "sources" / "standards"
    standards_dir.mkdir(parents=True)
    (standards_dir / "test-std.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "test-std",
                "kind": "ФСБУ",
                "number": "99/2099",
                "year": 2020,
                "title": "Тестовый стандарт",
                "order_date": "2020-01-01",
                "order_no": "1н",
                "effective_from": "2020-01-01",
                "source_url": "https://example.org/test-std",
                "editions": [
                    {
                        "edition_no": 1,
                        "amending_order": None,
                        "effective_from": "2020-01-01",
                        "clauses": [
                            {
                                "path": "1",
                                "parent_path": None,
                                "heading": None,
                                "text": "Текст пункта 1.",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "corpus.db"
    build(standards_dir, output, built_at=TODAY)

    connection = sqlite3.connect(output)
    connection.execute(
        "INSERT INTO mapping"
        " (standard_id, clause_path, edition_from, config, version_from, kind, object_ref,"
        " note, confidence, verified)"
        " VALUES ('test-std', '1', NULL, 'bp30', NULL, 'счёт', '01.01', NULL, 90, 1)"
    )
    connection.commit()
    connection.close()

    summary = Corpus(output).get_standard("test-std", TODAY)
    assert summary.mapping_status is MappingStatus.VERIFIED


def test_mappings_for_returns_empty_list_when_standard_not_yet_in_force(tmp_path: Path) -> None:
    """A mapping row on a real, known standard whose first edition has not taken
    effect yet as of `built_at()` must not raise NoEditionOnDate through
    `mappings_for` - it simply has no applicable rows yet."""
    standards_dir = tmp_path / "sources" / "standards"
    standards_dir.mkdir(parents=True)
    (standards_dir / "test-std.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "test-std",
                "kind": "ФСБУ",
                "number": "99/2099",
                "year": 2020,
                "title": "Тестовый стандарт",
                "order_date": "2020-01-01",
                "order_no": "1н",
                "effective_from": "2020-01-01",
                "source_url": "https://example.org/test-std",
                "editions": [
                    {
                        "edition_no": 1,
                        "amending_order": None,
                        "effective_from": "2020-01-01",
                        "clauses": [
                            {
                                "path": "1",
                                "parent_path": None,
                                "heading": None,
                                "text": "Текст пункта.",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "corpus.db"
    # built_at is before the standard's own effective_from: no edition is in
    # force yet as of the date mappings_for anchors itself to.
    build(standards_dir, output, built_at=date(2019, 1, 1))

    connection = sqlite3.connect(output)
    connection.execute(
        "INSERT INTO mapping"
        " (standard_id, clause_path, edition_from, config, version_from, kind, object_ref,"
        " note, confidence)"
        " VALUES ('test-std', '1', NULL, 'bp30', NULL, 'счёт', '01.01', NULL, 90)"
    )
    connection.commit()
    connection.close()

    assert Corpus(output).mappings_for("test-std", None, "bp30") == []


def test_mappings_for_excludes_a_row_whose_clause_was_dropped_by_an_amendment(
    tmp_path: Path,
) -> None:
    """A mapping targets edition 1's clause '1'; edition 2 drops that path
    entirely. Once edition 2 is in force, the row must stop resolving - it is a
    statement about clause '1', which no longer exists - instead of silently
    continuing to answer for wording that is gone. Checked across all three
    edition-aware read paths so they cannot drift apart on this again."""
    standards_dir = tmp_path / "sources" / "standards"
    standards_dir.mkdir(parents=True)
    (standards_dir / "test-std.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "test-std",
                "kind": "ФСБУ",
                "number": "99/2099",
                "year": 2020,
                "title": "Тестовый стандарт с двумя редакциями",
                "order_date": "2020-01-01",
                "order_no": "1н",
                "effective_from": "2020-01-01",
                "source_url": "https://example.org/test-std",
                "editions": [
                    {
                        "edition_no": 1,
                        "amending_order": None,
                        "effective_from": "2020-01-01",
                        "clauses": [
                            {
                                "path": "1",
                                "parent_path": None,
                                "heading": None,
                                "text": "Текст пункта 1 первой редакции.",
                            }
                        ],
                    },
                    {
                        "edition_no": 2,
                        "amending_order": "2н",
                        "effective_from": "2022-01-01",
                        "clauses": [
                            {
                                "path": "2",
                                "parent_path": None,
                                "heading": None,
                                "text": "Пункт 1 исключен; текст пункта 2 второй редакции.",
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "corpus.db"
    build(standards_dir, output, built_at=date(2023, 1, 1))

    connection = sqlite3.connect(output)
    connection.execute(
        "INSERT INTO mapping"
        " (standard_id, clause_path, edition_from, config, version_from, kind, object_ref,"
        " note, confidence)"
        " VALUES ('test-std', '1', NULL, 'bp30', NULL, 'счёт', '01.01', NULL, 90)"
    )
    connection.commit()
    connection.close()

    corpus = Corpus(output)
    assert corpus.mappings_for("test-std", None, "bp30") == []
    assert corpus.get_standard("test-std", date(2023, 1, 1)).mapping_status is MappingStatus.NONE
    assert corpus.clauses_by_object("01.01", "bp30") == []


def test_corpus_opens_under_a_path_containing_a_hash(
    corpus_db: Path, tmp_path: Path
) -> None:
    """`#` in a path silently opened an EMPTY database before the URI was encoded."""
    awkward = tmp_path / "dir#with#hash"
    awkward.mkdir()
    copied = awkward / "corpus.db"
    copied.write_bytes(corpus_db.read_bytes())

    assert Corpus(copied).get_clause("fsbu-6-2020", "1", TODAY).path == "1"
