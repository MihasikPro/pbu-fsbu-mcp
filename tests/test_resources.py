from datetime import date
from pathlib import Path

import pytest

from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.tools.resources import registry_document


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
