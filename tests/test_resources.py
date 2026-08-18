from datetime import date
from pathlib import Path

import pytest

from etl.build_db import build
from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.tools.resources import registry_document

SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


def test_document_is_markdown_table(corpus: Corpus) -> None:
    document = registry_document(corpus, date(2026, 8, 14))
    assert document.startswith("# Реестр стандартов")
    assert "| id |" in document


def test_document_lists_reference_standard(corpus: Corpus) -> None:
    document = registry_document(corpus, date(2026, 8, 14))
    assert "fsbu-6-2020" in document
    assert "Основные средства" in document


def test_document_reports_status(corpus: Corpus) -> None:
    document = registry_document(corpus, date(2021, 6, 1))
    assert "не вступил в силу" in document


def test_document_omits_staleness_warning_for_a_fresh_corpus(corpus: Corpus) -> None:
    document = registry_document(corpus, date(2026, 8, 14))
    assert "пересборка корпуса" not in document


def test_registry_marks_draft_mapped_standards(corpus: Corpus) -> None:
    """Every fsbu-6-2020 mapping row is `verified: false` by construction (a pilot
    projection) - the registry must say so, not a bare 'да' that a reader could
    mistake for a human-checked mapping."""
    document = registry_document(corpus, date(2026, 8, 14))
    line = next(row for row in document.splitlines() if "fsbu-6-2020" in row)
    assert line.rstrip().endswith("| черновик |")


def test_registry_marks_unmapped_standards(corpus: Corpus) -> None:
    document = registry_document(corpus, date(2026, 8, 14))
    line = next(row for row in document.splitlines() if "pbu-13-2000" in row)
    assert line.rstrip().endswith("| нет |")


def test_document_includes_staleness_warning_for_a_stale_corpus(tmp_path: Path) -> None:
    """The registry resource is the artifact most likely to be cached in an LLM
    context for a whole session, so it must not be the one place with no warning."""
    output = tmp_path / "stale.db"
    build(SOURCES, output, built_at=date(2000, 1, 1))
    stale_corpus = Corpus(output)

    document = registry_document(stale_corpus, date(2026, 8, 14))
    assert "пересборка корпуса" in document
