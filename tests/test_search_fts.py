from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from etl.build_db import build
from pbu_fsbu_mcp.models import StandardStatus
from pbu_fsbu_mcp.search.fts import FtsSearchBackend

TODAY = date(2026, 8, 14)

_ACTIVE_STANDARD = dedent(
    """\
    id: exp-std-active
    kind: ФСБУ
    number: "77/2099"
    year: 2099
    title: Экспериментальный действующий стандарт
    order_date: 2020-01-01
    order_no: 1н
    effective_from: 2020-01-01
    effective_to: null
    superseded_by: null
    source_url: https://example.org/active
    editions:
      - edition_no: 1
        amending_order: null
        effective_from: 2020-01-01
        clauses:
          - path: "1"
            parent_path: null
            heading: null
            text: Основные средства учитываются по первоначальной стоимости.
    """
)

_REPEALED_STANDARD = dedent(
    """\
    id: exp-std-repealed
    kind: ФСБУ
    number: "88/2099"
    year: 2099
    title: Экспериментальный утративший силу стандарт
    order_date: 2018-01-01
    order_no: 2н
    effective_from: 2018-01-01
    effective_to: 2025-01-01
    superseded_by: exp-std-active
    source_url: https://example.org/repealed
    editions:
      - edition_no: 1
        amending_order: null
        effective_from: 2018-01-01
        clauses:
          - path: "1"
            parent_path: null
            heading: null
            text: Основные средства учитываются по восстановительной стоимости.
    """
)


@pytest.fixture
def backend(corpus_db: Path) -> FtsSearchBackend:
    return FtsSearchBackend(corpus_db)


def test_finds_clause_by_inflected_query(backend: FtsSearchBackend) -> None:
    """Genitive plural "требований" must resolve to the same clauses as the nominative
    plural "требования" - proving the lemmatiser normalises inflected forms rather than
    doing a literal substring match. Pinning to one standard's path would be arbitrary
    across a 29-standard corpus; equivalence to the base form is what inflection means."""
    inflected = backend.search("требований", None, TODAY, limit=5)
    base_form = backend.search("требования", None, TODAY, limit=5)
    assert inflected
    assert [(hit.standard_id, hit.path) for hit in inflected] == [
        (hit.standard_id, hit.path) for hit in base_form
    ]


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
    """FTS5 operators in user input must be literals, not syntax - and never raise.

    `lemmatize()` strips the quotes/`AND`/`OR`/`*` punctuation before tokenising, so a
    query built from the same words without any FTS5-special characters must produce
    the byte-for-byte identical lemma expression and therefore identical hits. If the
    special characters leaked into FTS5 syntax instead of being treated as literals,
    this equality would break (or the call would raise) well before this assertion.
    """
    hits = backend.search('пункт "9" AND OR *', None, TODAY, limit=5)
    plain_hits = backend.search("пункт 9 and or", None, TODAY, limit=5)
    assert hits
    assert [(hit.standard_id, hit.path) for hit in hits] == [
        (hit.standard_id, hit.path) for hit in plain_hits
    ]


def test_hits_carry_snippet_and_score(backend: FtsSearchBackend) -> None:
    """Every hit must carry a non-empty snippet, a standard title, and a numeric score -
    which standard happens to rank first across a 29-standard corpus is not the point."""
    hits = backend.search("требований", None, TODAY, limit=5)
    assert hits[0].snippet
    assert hits[0].standard_title
    assert isinstance(hits[0].score, float)


def test_score_is_higher_is_better(backend: FtsSearchBackend) -> None:
    """Pins the bm25 sign convention: dropping the negation must fail a test."""
    hits = backend.search("основных средств", None, TODAY, limit=10)
    assert len(hits) > 1
    assert hits[0].score >= hits[-1].score


def test_active_hits_carry_status(backend: FtsSearchBackend) -> None:
    hits = backend.search("требований", None, TODAY, limit=5)
    assert hits[0].status is StandardStatus.ACTIVE


def test_search_marks_repealed_standard_status(tmp_path: Path) -> None:
    """A repealed standard's editions still resolve by date; the hit must say so."""
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "active.yaml").write_text(_ACTIVE_STANDARD, encoding="utf-8")
    (sources / "repealed.yaml").write_text(_REPEALED_STANDARD, encoding="utf-8")
    db_path = tmp_path / "corpus.db"
    build(sources, db_path, built_at=TODAY)

    backend = FtsSearchBackend(db_path)
    hits = backend.search("основные средства", None, TODAY, limit=10)

    hits_by_standard = {hit.standard_id: hit for hit in hits}
    assert hits_by_standard["exp-std-active"].status is StandardStatus.ACTIVE
    assert hits_by_standard["exp-std-repealed"].status is StandardStatus.REPEALED
