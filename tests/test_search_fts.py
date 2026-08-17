from datetime import date
from pathlib import Path

import pytest

from pbu_fsbu_mcp.search.fts import FtsSearchBackend

TODAY = date(2026, 8, 14)


@pytest.fixture
def backend(corpus_db: Path) -> FtsSearchBackend:
    return FtsSearchBackend(corpus_db)


def test_finds_clause_by_inflected_query(backend: FtsSearchBackend) -> None:
    hits = backend.search("требований", None, TODAY, limit=5)
    assert any(hit.path == "1" for hit in hits)


def test_respects_limit(backend: FtsSearchBackend) -> None:
    hits = backend.search("стандарт", None, TODAY, limit=1)
    assert len(hits) <= 1


def test_filters_by_standard_ids(backend: FtsSearchBackend) -> None:
    hits = backend.search("стандарт", ["fsbu-999-1999"], TODAY, limit=5)
    assert hits == []


def test_empty_query_returns_empty_list(backend: FtsSearchBackend) -> None:
    assert backend.search("   ", None, TODAY, limit=5) == []


def test_query_with_no_matches_returns_empty_list(backend: FtsSearchBackend) -> None:
    assert backend.search("криптовалюта", None, TODAY, limit=5) == []


def test_special_characters_do_not_break_fts(backend: FtsSearchBackend) -> None:
    """FTS5 operators in user input must be literals, not syntax - and never raise."""
    hits = backend.search('пункт "9" AND OR *', None, TODAY, limit=5)
    assert all(hit.standard_id == "fsbu-6-2020" for hit in hits)


def test_hits_carry_snippet_and_score(backend: FtsSearchBackend) -> None:
    hits = backend.search("требований", None, TODAY, limit=5)
    assert hits[0].snippet
    assert hits[0].standard_title == "Основные средства"


def test_score_is_higher_is_better(backend: FtsSearchBackend) -> None:
    """Pins the bm25 sign convention: dropping the negation must fail a test."""
    hits = backend.search("основных средств", None, TODAY, limit=10)
    assert len(hits) > 1
    assert hits[0].score >= hits[-1].score
