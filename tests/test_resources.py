import sqlite3
from datetime import date
from pathlib import Path

import pytest
import yaml

from etl.build_db import build
from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.tools.resources import registry_document

SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"
TODAY = date(2026, 8, 14)


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


def _standard_source(standard_id: str) -> dict:
    return {
        "id": standard_id,
        "kind": "ФСБУ",
        "number": "99/2099",
        "year": 2020,
        "title": f"Тестовый стандарт {standard_id}",
        "order_date": "2020-01-01",
        "order_no": "1н",
        "effective_from": "2020-01-01",
        "source_url": f"https://example.org/{standard_id}",
        "editions": [
            {
                "edition_no": 1,
                "amending_order": None,
                "effective_from": "2020-01-01",
                "clauses": [
                    {
                        "path": "1",
                        "parent_path": None,
                        "heading": None,
                        "text": "Текст пункта 1.",
                    }
                ],
            }
        ],
    }


def _build_registry_corpus(tmp_path: Path, mapping_by_standard: dict[str, bool]) -> Corpus:
    """Two standards, one clause each, with a single hand-inserted `mapping`
    row per standard - purpose-built (like `test_db.py::two_edition_corpus`) so
    the registry's черновик/проверено rendering can be tested independently of
    the real corpus's current verification state. `mapping_by_standard` maps
    `standard_id -> verified`.
    """
    standards_dir = tmp_path / "sources" / "standards"
    standards_dir.mkdir(parents=True)
    for standard_id in mapping_by_standard:
        (standards_dir / f"{standard_id}.yaml").write_text(
            yaml.safe_dump(_standard_source(standard_id)), encoding="utf-8"
        )

    output = tmp_path / "corpus.db"
    build(standards_dir, output, built_at=TODAY)

    connection = sqlite3.connect(output)
    for standard_id, verified in mapping_by_standard.items():
        connection.execute(
            "INSERT INTO mapping"
            " (standard_id, clause_path, edition_from, config, version_from, kind, object_ref,"
            " note, confidence, verified)"
            " VALUES (?, '1', NULL, 'bp30', NULL, 'счёт', '01.01', NULL, 90, ?)",
            (standard_id, int(verified)),
        )
    connection.commit()
    connection.close()

    return Corpus(output)


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


def test_registry_marks_draft_mapped_standards(tmp_path: Path) -> None:
    """A standard whose only applicable mapping row is `verified: false` (a
    pilot projection) must be marked `черновик`, not a bare 'да' that a reader
    could mistake for a human-checked mapping - and a standard whose only row
    is `verified: true` must be marked `проверено`, not `черновик`.
    """
    corpus = _build_registry_corpus(
        tmp_path, {"test-draft": False, "test-verified": True}
    )
    document = registry_document(corpus, TODAY)
    draft_line = next(row for row in document.splitlines() if "test-draft" in row)
    verified_line = next(row for row in document.splitlines() if "test-verified" in row)
    assert draft_line.rstrip().endswith("| черновик |")
    assert verified_line.rstrip().endswith("| проверено |")


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
