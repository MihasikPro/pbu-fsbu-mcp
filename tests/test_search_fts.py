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
    assert backend.search('пункт "9" AND OR *', None, TODAY, limit=5) is not None


def test_hits_carry_snippet_and_score(backend: FtsSearchBackend) -> None:
    hits = backend.search("требований", None, TODAY, limit=5)
    assert hits[0].snippet
    assert hits[0].standard_title == "Основные средства"
