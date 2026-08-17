from pathlib import Path

import pytest

from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.tools.registry import get_standard_payload, list_standards_payload


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


def test_list_returns_registry_rows(corpus: Corpus) -> None:
    payload = list_standards_payload(corpus, kind=None, on_date="2026-08-14")
    ids = [row["id"] for row in payload["standards"]]
    assert "fsbu-6-2020" in ids


def test_list_filters_by_kind(corpus: Corpus) -> None:
    payload = list_standards_payload(corpus, kind="ПБУ", on_date="2026-08-14")
    assert all(row["kind"] == "ПБУ" for row in payload["standards"])


def test_list_defaults_on_date_to_today(corpus: Corpus) -> None:
    payload = list_standards_payload(corpus, kind=None, on_date=None)
    assert payload["as_of_date"]


def test_list_rejects_malformed_date(corpus: Corpus) -> None:
    with pytest.raises(ValueError, match="on_date"):
        list_standards_payload(corpus, kind=None, on_date="14.08.2026")


def test_get_standard_returns_outline(corpus: Corpus) -> None:
    payload = get_standard_payload(corpus, "fsbu-6-2020", "2026-08-14")
    assert payload["standard"]["title"] == "Основные средства"
    assert payload["outline"][0]["path"] == "1"


def test_get_standard_reports_unknown_id(corpus: Corpus) -> None:
    with pytest.raises(ValueError, match="отсутствует в корпусе"):
        get_standard_payload(corpus, "fsbu-999-1999", "2026-08-14")
