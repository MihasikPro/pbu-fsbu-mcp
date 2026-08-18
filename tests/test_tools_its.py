from pathlib import Path

import pytest
from pydantic import ValidationError

from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.disclaimers import UNVERIFIED_MAPPING_WARNING
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


def test_links_carry_their_own_verified_flag(corpus: Corpus) -> None:
    link = get_its_references_payload(corpus, "fsbu-6-2020", None)["links"][0]
    assert link["verified"] is False


def test_unverified_link_triggers_the_unverified_warning(corpus: Corpus) -> None:
    payload = get_its_references_payload(corpus, "fsbu-6-2020", None)
    assert all(link["verified"] is False for link in payload["links"])
    assert UNVERIFIED_MAPPING_WARNING in payload["warnings"]


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
