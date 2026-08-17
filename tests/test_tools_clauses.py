from pathlib import Path

import pytest

from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.tools.clauses import get_clause_payload


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


def test_returns_clause_with_provenance(corpus: Corpus) -> None:
    payload = get_clause_payload(corpus, "fsbu-6-2020", "1", "2026-08-14")
    assert "устанавливает требования" in payload["clause"]["text"]
    assert payload["clause"]["order_ref"].startswith("приказ Минфина России")
    assert payload["clause"]["source_url"].startswith("https://")


def test_reports_edition_and_date(corpus: Corpus) -> None:
    payload = get_clause_payload(corpus, "fsbu-6-2020", "1", "2026-08-14")
    assert payload["clause"]["edition_no"] == 1
    assert payload["clause"]["as_of_date"] == "2026-08-14"


def test_missing_clause_lists_available_paths(corpus: Corpus) -> None:
    with pytest.raises(ValueError) as excinfo:
        get_clause_payload(corpus, "fsbu-6-2020", "999", "2026-08-14")
    message = str(excinfo.value)
    assert "нет пункта" in message
    assert "Доступные пункты" in message


def test_date_before_effective_marks_not_yet(corpus: Corpus) -> None:
    payload = get_clause_payload(corpus, "fsbu-6-2020", "1", "2021-06-01")
    assert payload["clause"]["status"] == "не вступил в силу"
    assert any("не действует" in warning for warning in payload["clause"]["warnings"])


def test_unknown_standard_raises(corpus: Corpus) -> None:
    with pytest.raises(ValueError, match="отсутствует в корпусе"):
        get_clause_payload(corpus, "fsbu-999-1999", "1", "2026-08-14")


def test_payload_has_a_top_level_warnings_key(corpus: Corpus) -> None:
    """get_clause must expose warnings the same way as the other three tools -
    a client reading payload["warnings"] must not need special-casing per tool."""
    payload = get_clause_payload(corpus, "fsbu-6-2020", "1", "2026-08-14")
    assert payload["warnings"] == []
