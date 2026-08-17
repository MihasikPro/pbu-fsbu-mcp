from pathlib import Path

import pytest

from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.search.fts import FtsSearchBackend
from pbu_fsbu_mcp.tools.search import search_clauses_payload


@pytest.fixture
def parts(corpus_db: Path) -> tuple[FtsSearchBackend, Corpus]:
    return FtsSearchBackend(corpus_db), Corpus(corpus_db)


def test_returns_hits_for_natural_query(parts: tuple[FtsSearchBackend, Corpus]) -> None:
    backend, corpus = parts
    payload = search_clauses_payload(backend, corpus, "требования", None, "2026-08-14", 5)
    assert payload["hits"]
    assert payload["hits"][0]["standard_id"] == "fsbu-6-2020"


def test_limit_is_clamped_to_fifty(parts: tuple[FtsSearchBackend, Corpus]) -> None:
    backend, corpus = parts
    payload = search_clauses_payload(backend, corpus, "стандарт", None, "2026-08-14", 999)
    assert payload["limit"] == 50


def test_limit_below_one_is_rejected(parts: tuple[FtsSearchBackend, Corpus]) -> None:
    backend, corpus = parts
    with pytest.raises(ValueError, match="limit"):
        search_clauses_payload(backend, corpus, "стандарт", None, "2026-08-14", 0)


def test_no_hits_returns_explicit_message(parts: tuple[FtsSearchBackend, Corpus]) -> None:
    backend, corpus = parts
    payload = search_clauses_payload(backend, corpus, "криптовалюта", None, "2026-08-14", 5)
    assert payload["hits"] == []
    assert "не найдено" in payload["message"]
