import sqlite3
from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from etl.build_db import build
from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.disclaimers import UNVERIFIED_MAPPING_WARNING
from pbu_fsbu_mcp.models import ItsLinkSource
from pbu_fsbu_mcp.tools.its import get_its_references_payload

SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"
TODAY = date(2026, 8, 14)


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


def _build_its_corpus(tmp_path: Path, its_rows: list[tuple[str, bool]]) -> Corpus:
    """One standard, one clause, `its_link` rows inserted by hand with the given
    `verified` values - purpose-built (like `test_db.py::two_edition_corpus`) so
    `get_its_references`'s verification-warning wiring can be tested
    independently of the real corpus.
    """
    standards_dir = tmp_path / "sources" / "standards"
    standards_dir.mkdir(parents=True)
    (standards_dir / "test-std.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "test-std",
                "kind": "ФСБУ",
                "number": "99/2099",
                "year": 2020,
                "title": "Тестовый стандарт",
                "order_date": "2020-01-01",
                "order_no": "1н",
                "effective_from": "2020-01-01",
                "source_url": "https://example.org/test-std",
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
        ),
        encoding="utf-8",
    )

    output = tmp_path / "corpus.db"
    build(standards_dir, output, built_at=TODAY)

    connection = sqlite3.connect(output)
    for its_id, verified in its_rows:
        connection.execute(
            "INSERT INTO its_link"
            " (standard_id, clause_path, edition_from, its_id, title, summary, verified)"
            " VALUES ('test-std', '1', NULL, ?, 'Заголовок', 'Выжимка своими словами.', ?)",
            (its_id, int(verified)),
        )
    connection.commit()
    connection.close()

    return Corpus(output)


def test_returns_links_for_standard(corpus: Corpus) -> None:
    payload = get_its_references_payload(corpus, "fsbu-6-2020", None)
    assert payload["links"]


def test_links_carry_id_title_and_summary(corpus: Corpus) -> None:
    link = get_its_references_payload(corpus, "fsbu-6-2020", None)["links"][0]
    assert link["its_id"] and link["title"] and link["summary"]


def test_filters_by_clause_path(corpus: Corpus) -> None:
    payload = get_its_references_payload(corpus, "fsbu-6-2020", "4")
    assert {link["clause_path"] for link in payload["links"]} == {"4"}


def test_payload_explains_how_to_read_full_text(corpus: Corpus) -> None:
    payload = get_its_references_payload(corpus, "fsbu-6-2020", None)
    assert "fetch_its" in payload["hint"]


def test_standard_without_links_returns_empty(corpus: Corpus) -> None:
    payload = get_its_references_payload(corpus, "pbu-13-2000", None)
    assert payload["links"] == []
    assert payload["message"]


def test_summary_longer_than_limit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ItsLinkSource(
            clause_path="4",
            its_id="x",
            title="Заголовок",
            summary="а" * 401,
        )


def test_links_carry_their_own_verified_flag(tmp_path: Path) -> None:
    corpus = _build_its_corpus(tmp_path, [("its/1", True)])
    link = get_its_references_payload(corpus, "test-std", None)["links"][0]
    assert link["verified"] is True


def test_unverified_link_triggers_the_unverified_warning(tmp_path: Path) -> None:
    corpus = _build_its_corpus(tmp_path, [("its/1", False)])
    payload = get_its_references_payload(corpus, "test-std", None)
    assert all(link["verified"] is False for link in payload["links"])
    assert UNVERIFIED_MAPPING_WARNING in payload["warnings"]


def test_verified_link_does_not_trigger_the_unverified_warning(tmp_path: Path) -> None:
    corpus = _build_its_corpus(tmp_path, [("its/1", True)])
    payload = get_its_references_payload(corpus, "test-std", None)
    assert UNVERIFIED_MAPPING_WARNING not in payload["warnings"]


def test_standard_without_links_has_no_warning(corpus: Corpus) -> None:
    """No returned rows means no claim to warn about."""
    payload = get_its_references_payload(corpus, "pbu-13-2000", None)
    assert payload["warnings"] == []


def test_unknown_standard_raises(corpus: Corpus) -> None:
    """An unresolvable `standard_id` must be rejected, not answered with 'no links
    yet' as if the standard existed - see `get_1c_mapping`/`get_clause`."""
    with pytest.raises(ValueError, match="отсутствует в корпусе"):
        get_its_references_payload(corpus, "fsbu-999-1999", None)


def test_unknown_clause_path_raises(corpus: Corpus) -> None:
    with pytest.raises(ValueError, match="нет пункта"):
        get_its_references_payload(corpus, "fsbu-6-2020", "999")


def test_clause_path_for_a_standard_not_yet_in_force_is_validated_against_its_first_edition(
    corpus: Corpus,
) -> None:
    """fsbu-9-2025 takes effect 2027-01-01, after `corpus.built_at()` - a real
    clause of its (only) edition must still resolve, falling back the same way
    `get_clause` does for a pre-effective date."""
    payload = get_its_references_payload(corpus, "fsbu-9-2025", "1")
    assert payload["links"] == []
    assert payload["message"]


def test_disclaimer_explains_summary_is_our_own_wording(corpus: Corpus) -> None:
    payload = get_its_references_payload(corpus, "fsbu-6-2020", None)
    assert "ИТС" in payload["disclaimer"]


def test_payload_includes_staleness_warning_for_a_stale_corpus(tmp_path: Path) -> None:
    """The other three tools (get_1c_mapping, list_standards, registry_document)
    already surface a stale corpus via corpus.warnings() - get_its_references
    was the one place that silently dropped it."""
    output = tmp_path / "stale.db"
    build(SOURCES, output, built_at=date(2000, 1, 1))
    stale_corpus = Corpus(output)

    payload = get_its_references_payload(stale_corpus, "fsbu-6-2020", None)
    assert any("пересборка корпуса" in warning for warning in payload["warnings"])
