from pathlib import Path

import pytest

from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.disclaimers import UNVERIFIED_MAPPING_WARNING
from pbu_fsbu_mcp.tools.mapping import find_by_1c_object_payload


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


def test_finds_standards_behind_an_account(corpus: Corpus) -> None:
    payload = find_by_1c_object_payload(corpus, "01.01", "bp30")
    assert any(row["standard_id"] == "fsbu-6-2020" for row in payload["clauses"])


def test_result_carries_clause_path_and_title(corpus: Corpus) -> None:
    row = find_by_1c_object_payload(corpus, "01.01", "bp30")["clauses"][0]
    assert row["clause_path"]
    assert row["standard_title"]


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


def test_clauses_carry_their_own_verified_flag(corpus: Corpus) -> None:
    row = find_by_1c_object_payload(corpus, "01.01", "bp30")["clauses"][0]
    assert row["verified"] is False


def test_unverified_row_triggers_the_unverified_warning(corpus: Corpus) -> None:
    payload = find_by_1c_object_payload(corpus, "01.01", "bp30")
    assert all(row["verified"] is False for row in payload["clauses"])
    assert UNVERIFIED_MAPPING_WARNING in payload["warnings"]
