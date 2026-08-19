import sqlite3
from datetime import date
from pathlib import Path

import pytest
import yaml

from etl.build_db import build
from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.disclaimers import UNVERIFIED_MAPPING_WARNING
from pbu_fsbu_mcp.tools.mapping import get_1c_mapping_payload

TODAY = date(2026, 8, 14)


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


def _build_mapping_corpus(tmp_path: Path, mapping_rows: list[tuple[str, bool]]) -> Corpus:
    """One standard, one clause, `mapping` rows inserted by hand with the given
    `verified` values - purpose-built (like `test_db.py::two_edition_corpus`) so
    the verification-warning wiring can be tested independently of whatever the
    real corpus happens to contain.
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
    for object_ref, verified in mapping_rows:
        connection.execute(
            "INSERT INTO mapping"
            " (standard_id, clause_path, edition_from, config, version_from, kind, object_ref,"
            " note, confidence, verified)"
            " VALUES ('test-std', '1', NULL, 'bp30', NULL, 'счёт', ?, NULL, 90, ?)",
            (object_ref, int(verified)),
        )
    connection.commit()
    connection.close()

    return Corpus(output)


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


def test_unknown_config_says_so_instead_of_not_filled_in_yet(corpus: Corpus) -> None:
    """A typo'd config (e.g. "erp") must not get the same "проекция пока не
    заполнена" wording as a real config with no rows yet - that would silently
    confirm a configuration the server has never heard of."""
    payload = get_1c_mapping_payload(corpus, "fsbu-6-2020", None, "erp")
    assert payload["mappings"] == []
    assert "'erp'" in payload["message"]
    assert "неизвестна" in payload["message"]
    assert "bp30" in payload["message"]


def test_mapping_text_is_separate_from_clause_text(corpus: Corpus) -> None:
    """Проекция не должна подмешиваться в нормативный текст."""
    payload = get_1c_mapping_payload(corpus, "fsbu-6-2020", "4", "bp30")
    assert "clause_text" not in payload
    assert all("text" not in row for row in payload["mappings"])


def test_payload_has_a_top_level_warnings_key(corpus: Corpus) -> None:
    """A standard with no mapping rows at all makes no claim to warn about."""
    payload = get_1c_mapping_payload(corpus, "pbu-13-2000", None, "bp30")
    assert payload["warnings"] == []


def test_mapping_rows_carry_their_own_verified_flag(tmp_path: Path) -> None:
    corpus = _build_mapping_corpus(tmp_path, [("01.01", True)])
    row = get_1c_mapping_payload(corpus, "test-std", None, "bp30")["mappings"][0]
    assert row["verified"] is True


def test_clause_5_maps_onto_a_real_qualified_register(corpus: Corpus) -> None:
    """Regression for the "УчетнаяПолитика.ЛимитСтоимостиОС" pseudo-object: the
    limit lives in a resource of the real РегистрСведений.УчетнаяПолитикаОрганизаций,
    confirmed via config_help against БП 3.0 - not an unaddressable placeholder."""
    payload = get_1c_mapping_payload(corpus, "fsbu-6-2020", "5", "bp30")
    refs = {row["object_ref"] for row in payload["mappings"]}
    assert refs == {"РегистрСведений.УчетнаяПолитикаОрганизаций"}


def test_unverified_row_triggers_the_unverified_warning(tmp_path: Path) -> None:
    """A mapping row with `verified = 0` must raise the warning - regardless of
    what the real corpus's rows happen to be verified as right now.
    """
    corpus = _build_mapping_corpus(tmp_path, [("01.01", False)])
    payload = get_1c_mapping_payload(corpus, "test-std", None, "bp30")
    assert all(row["verified"] is False for row in payload["mappings"])
    assert UNVERIFIED_MAPPING_WARNING in payload["warnings"]


def test_verified_row_does_not_trigger_the_unverified_warning(tmp_path: Path) -> None:
    corpus = _build_mapping_corpus(tmp_path, [("01.01", True)])
    payload = get_1c_mapping_payload(corpus, "test-std", None, "bp30")
    assert UNVERIFIED_MAPPING_WARNING not in payload["warnings"]


def test_one_unverified_row_among_many_verified_ones_still_triggers_the_warning(
    tmp_path: Path,
) -> None:
    """The case most worth pinning: eighteen verified rows plus one still-draft
    row (mirroring the real fsbu-6-2020 mapping's row count) must not let the
    lone unverified row get diluted away by the rest being checked.
    """
    verified_rows = [(f"01.{index:02d}", True) for index in range(1, 19)]
    corpus = _build_mapping_corpus(tmp_path, [*verified_rows, ("01.19", False)])
    payload = get_1c_mapping_payload(corpus, "test-std", None, "bp30")
    assert sum(1 for row in payload["mappings"] if not row["verified"]) == 1
    assert UNVERIFIED_MAPPING_WARNING in payload["warnings"]
