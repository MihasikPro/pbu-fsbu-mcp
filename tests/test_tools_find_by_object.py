import sqlite3
from datetime import date
from pathlib import Path

import pytest
import yaml

from etl.build_db import build
from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.disclaimers import UNVERIFIED_MAPPING_WARNING
from pbu_fsbu_mcp.tools.mapping import find_by_1c_object_payload

TODAY = date(2026, 8, 14)


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


def _build_object_corpus(tmp_path: Path, mapping_rows: list[tuple[str, bool]]) -> Corpus:
    """One standard, one clause, `config_object` + `mapping` rows inserted by
    hand with the given `verified` values - purpose-built (like
    `test_db.py::two_edition_corpus`) so `find_by_1c_object`'s verification-
    warning wiring can be tested independently of the real corpus.
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
    for object_ref, verified in mapping_rows:
        connection.execute(
            "INSERT INTO config_object (config, ref, kind, presentation) VALUES (?, ?, ?, ?)",
            ("bp30", object_ref, "счёт", f"Представление {object_ref}"),
        )
        connection.execute(
            "INSERT INTO mapping"
            " (standard_id, clause_path, edition_from, config, version_from, kind, object_ref,"
            " note, confidence, verified)"
            " VALUES ('test-std', '1', NULL, 'bp30', NULL, 'счёт', ?, NULL, 90, ?)",
            (object_ref, int(verified)),
        )
    connection.commit()
    connection.close()

    return Corpus(output)


def test_finds_standards_behind_an_account(corpus: Corpus) -> None:
    payload = find_by_1c_object_payload(corpus, "01.01", "bp30")
    assert any(row["standard_id"] == "fsbu-6-2020" for row in payload["clauses"])


def test_result_carries_clause_path_and_title(corpus: Corpus) -> None:
    row = find_by_1c_object_payload(corpus, "01.01", "bp30")["clauses"][0]
    assert row["clause_path"]
    assert row["standard_title"]


def test_result_carries_a_human_readable_presentation(corpus: Corpus) -> None:
    """get_1c_mapping already resolves a presentation for every row (mappings_for);
    the reverse lookup must not answer with a bare object_ref where the forward
    lookup gives a catalogue name."""
    row = find_by_1c_object_payload(corpus, "01.01", "bp30")["clauses"][0]
    assert row["presentation"] == "Основные средства в организации"


def test_disclaimer_is_present(corpus: Corpus) -> None:
    payload = find_by_1c_object_payload(corpus, "01.01", "bp30")
    assert "интерпретация" in payload["disclaimer"].lower()


def test_mapped_object_outcome_is_mapped(corpus: Corpus) -> None:
    """An object with at least one projection row is unambiguously 'mapped'."""
    payload = find_by_1c_object_payload(corpus, "01.01", "bp30")
    assert payload["outcome"] == "mapped"
    assert payload["clauses"]


def test_unknown_object_returns_suggestions(corpus: Corpus) -> None:
    payload = find_by_1c_object_payload(corpus, "01.0", "bp30")
    assert payload["clauses"] == []
    assert payload["outcome"] == "unknown"
    assert payload["suggestions"], "Должны предлагаться похожие объекты"


def test_object_without_mapping_reports_empty_result(corpus: Corpus) -> None:
    """The object exists in the catalogue but has no projection row yet.

    This must be distinguishable from an unrecognised object: `outcome` says
    'known_no_mapping', not 'unknown', even though `clauses` is empty in both cases.
    """
    payload = find_by_1c_object_payload(corpus, "01.09", "bp30")
    assert isinstance(payload["clauses"], list)
    assert payload["clauses"] == []
    assert payload["outcome"] == "known_no_mapping"


def test_known_object_without_mapping_is_not_offered_as_a_suggestion_of_itself(
    corpus: Corpus,
) -> None:
    payload = find_by_1c_object_payload(corpus, "01.09", "bp30")
    assert payload["suggestions"] == []


def test_lookup_is_case_insensitive(corpus: Corpus) -> None:
    lower = find_by_1c_object_payload(corpus, "регистрсведений.параметрыамортизацииос", "bp30")
    upper = find_by_1c_object_payload(corpus, "РегистрСведений.ПараметрыАмортизацииОС", "bp30")
    assert len(lower["clauses"]) == len(upper["clauses"])
    assert lower["outcome"] == upper["outcome"] == "mapped"


def test_percent_sign_fragment_is_matched_literally_not_as_a_wildcard(corpus: Corpus) -> None:
    """`suggest_objects` used an unescaped `LIKE '%<fragment>%'` - a bare "%"
    fragment matched every row in the catalogue instead of the literal
    character. No catalogue entry contains a literal "%", so this must come
    back empty, not "everything"."""
    payload = find_by_1c_object_payload(corpus, "%", "bp30")
    assert payload["suggestions"] == []


def test_suggestions_come_from_the_object_catalogue_not_only_mapped_objects(
    corpus: Corpus,
) -> None:
    """01.09 has no mapping row but is a real catalogue object - it must still surface
    as a suggestion for a near-miss fragment, not just objects that already have
    a projection.
    """
    payload = find_by_1c_object_payload(corpus, "01.0", "bp30")
    assert "01.09" in payload["suggestions"]


def test_payload_has_a_top_level_warnings_key(corpus: Corpus) -> None:
    """An object with no returned rows makes no claim to warn about."""
    payload = find_by_1c_object_payload(corpus, "01.09", "bp30")
    assert payload["warnings"] == []


def test_clauses_carry_their_own_verified_flag(tmp_path: Path) -> None:
    corpus = _build_object_corpus(tmp_path, [("01.01", True)])
    row = find_by_1c_object_payload(corpus, "01.01", "bp30")["clauses"][0]
    assert row["verified"] is True


def test_unverified_row_triggers_the_unverified_warning(tmp_path: Path) -> None:
    corpus = _build_object_corpus(tmp_path, [("01.01", False)])
    payload = find_by_1c_object_payload(corpus, "01.01", "bp30")
    assert all(row["verified"] is False for row in payload["clauses"])
    assert UNVERIFIED_MAPPING_WARNING in payload["warnings"]


def test_verified_row_does_not_trigger_the_unverified_warning(tmp_path: Path) -> None:
    corpus = _build_object_corpus(tmp_path, [("01.01", True)])
    payload = find_by_1c_object_payload(corpus, "01.01", "bp30")
    assert UNVERIFIED_MAPPING_WARNING not in payload["warnings"]


def test_unknown_config_is_reported_as_such_not_as_an_unknown_object(corpus: Corpus) -> None:
    """A typo'd config must not fall through to "object not found in catalogue" -
    the object was never even looked up against a real catalogue."""
    payload = find_by_1c_object_payload(corpus, "01.01", "erp")
    assert payload["outcome"] == "unknown_config"
    assert payload["clauses"] == []
    assert payload["suggestions"] == []
    assert "'erp'" in payload["message"]
