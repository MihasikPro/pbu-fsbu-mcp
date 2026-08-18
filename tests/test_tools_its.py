from pathlib import Path

import pytest
from pydantic import ValidationError

from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.models import ItsLinkSource
from pbu_fsbu_mcp.tools.its import get_its_references_payload


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


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
