import sqlite3
from datetime import date
from pathlib import Path

import pytest

from etl.build_db import build
from pbu_fsbu_mcp.db import ClauseNotFound, Corpus, StandardNotFound
from pbu_fsbu_mcp.models import StandardStatus

TODAY = date(2026, 8, 14)
SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"


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


def test_warnings_is_empty_for_a_freshly_built_corpus(corpus: Corpus) -> None:
    assert corpus.warnings() == []


def test_warnings_reports_a_stale_corpus(tmp_path: Path) -> None:
    output = tmp_path / "stale.db"
    build(SOURCES, output, built_at=date(2000, 1, 1))
    stale_corpus = Corpus(output)
    assert any("пересборка корпуса" in warning for warning in stale_corpus.warnings())


def test_corpus_connection_rejects_writes(corpus: Corpus) -> None:
    """The read-only mode is what makes the server safe as an immutable container."""
    with pytest.raises(sqlite3.OperationalError):
        corpus._connection.execute("DELETE FROM clause")


def test_clause_13_text_does_not_contain_the_concluding_sentence(corpus: Corpus) -> None:
    """Clause 13's text must stop at the lead-in; а)/б) sit between it and the conclusion."""
    clause = corpus.get_clause("fsbu-6-2020", "13", TODAY)
    assert "Выбранный способ последующей оценки" not in clause.text


def test_clause_13_conclusion_is_its_own_child_clause(corpus: Corpus) -> None:
    clause = corpus.get_clause("fsbu-6-2020", "13.заключение", TODAY)
    assert clause.parent_path == "13"
    assert "Выбранный способ последующей оценки" in clause.text


def test_clause_13_reports_children_in_document_order(corpus: Corpus) -> None:
    clause = corpus.get_clause("fsbu-6-2020", "13", TODAY)
    assert clause.children == ["13.а", "13.б", "13.заключение"]


def test_corpus_opens_under_a_path_containing_a_hash(
    corpus_db: Path, tmp_path: Path
) -> None:
    """`#` in a path silently opened an EMPTY database before the URI was encoded."""
    awkward = tmp_path / "dir#with#hash"
    awkward.mkdir()
    copied = awkward / "corpus.db"
    copied.write_bytes(corpus_db.read_bytes())

    assert Corpus(copied).get_clause("fsbu-6-2020", "1", TODAY).path == "1"
