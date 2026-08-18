from pathlib import Path

import pytest

from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.disclaimers import UNVERIFIED_MAPPING_WARNING
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
    """A standard with no mapping rows at all makes no claim to warn about."""
    payload = get_1c_mapping_payload(corpus, "pbu-13-2000", None, "bp30")
    assert payload["warnings"] == []


def test_mapping_rows_carry_their_own_verified_flag(corpus: Corpus) -> None:
    row = get_1c_mapping_payload(corpus, "fsbu-6-2020", None, "bp30")["mappings"][0]
    assert row["verified"] is False


def test_clause_5_maps_onto_a_real_qualified_register(corpus: Corpus) -> None:
    """Regression for the "УчетнаяПолитика.ЛимитСтоимостиОС" pseudo-object: the
    limit lives in a resource of the real РегистрСведений.УчетнаяПолитикаОрганизаций,
    confirmed via config_help against БП 3.0 - not an unaddressable placeholder."""
    payload = get_1c_mapping_payload(corpus, "fsbu-6-2020", "5", "bp30")
    refs = {row["object_ref"] for row in payload["mappings"]}
    assert refs == {"РегистрСведений.УчетнаяПолитикаОрганизаций"}


def test_unverified_row_triggers_the_unverified_warning(corpus: Corpus) -> None:
    """Every pilot fsbu-6-2020 mapping row is `verified: false` by construction -
    the warning must appear until a human reviewer flips a row to `verified: true`.
    """
    payload = get_1c_mapping_payload(corpus, "fsbu-6-2020", None, "bp30")
    assert all(row["verified"] is False for row in payload["mappings"])
    assert UNVERIFIED_MAPPING_WARNING in payload["warnings"]
