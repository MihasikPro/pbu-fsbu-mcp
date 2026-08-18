from pathlib import Path

import pytest

from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.tools.mapping import get_1c_mapping_payload


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


def test_returns_mapping_rows(corpus: Corpus) -> None:
    payload = get_1c_mapping_payload(corpus, "fsbu-6-2020", None, "bp30")
    refs = {row["object_ref"] for row in payload["mappings"]}
    assert "01.01" in refs


def test_mapping_rows_carry_presentation_and_confidence(corpus: Corpus) -> None:
    row = get_1c_mapping_payload(corpus, "fsbu-6-2020", None, "bp30")["mappings"][0]
    assert row["presentation"]
    assert 60 <= row["confidence"] <= 100


def test_disclaimer_is_always_present(corpus: Corpus) -> None:
    payload = get_1c_mapping_payload(corpus, "fsbu-6-2020", None, "bp30")
    assert "интерпретация" in payload["disclaimer"].lower()


def test_filters_by_clause_path(corpus: Corpus) -> None:
    payload = get_1c_mapping_payload(corpus, "fsbu-6-2020", "4", "bp30")
    assert {row["clause_path"] for row in payload["mappings"]} == {"4"}


def test_standard_without_mapping_returns_explicit_message(corpus: Corpus) -> None:
    payload = get_1c_mapping_payload(corpus, "pbu-13-2000", None, "bp30")
    assert payload["mappings"] == []
    assert "не заполнена" in payload["message"]


def test_unknown_standard_raises(corpus: Corpus) -> None:
    with pytest.raises(ValueError, match="отсутствует в корпусе"):
        get_1c_mapping_payload(corpus, "fsbu-999-1999", None, "bp30")


def test_mapping_text_is_separate_from_clause_text(corpus: Corpus) -> None:
    """Проекция не должна подмешиваться в нормативный текст."""
    payload = get_1c_mapping_payload(corpus, "fsbu-6-2020", "4", "bp30")
    assert "clause_text" not in payload
    assert all("text" not in row for row in payload["mappings"])


def test_payload_has_a_top_level_warnings_key(corpus: Corpus) -> None:
    """get_1c_mapping must expose warnings the same way as the other tools."""
    payload = get_1c_mapping_payload(corpus, "fsbu-6-2020", None, "bp30")
    assert payload["warnings"] == []
