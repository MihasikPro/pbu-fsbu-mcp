from datetime import date
from pathlib import Path

import pytest

from pbu_fsbu_mcp.db import ClauseNotFound, Corpus, StandardNotFound
from pbu_fsbu_mcp.models import StandardStatus

TODAY = date(2026, 8, 14)


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
