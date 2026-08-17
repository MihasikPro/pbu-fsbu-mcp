from datetime import date

from pbu_fsbu_mcp.disclaimers import (
    MAPPING_DISCLAIMER,
    NO_MAPPING_MESSAGE,
    STALE_AFTER_DAYS,
    corpus_warnings,
)


def test_fresh_corpus_produces_no_warnings() -> None:
    assert corpus_warnings(date(2026, 8, 1), date(2026, 8, 14)) == []


def test_boundary_day_produces_no_warnings() -> None:
    assert corpus_warnings(date(2026, 5, 16), date(2026, 8, 14)) == []


def test_stale_corpus_produces_warning_with_build_date() -> None:
    warnings = corpus_warnings(date(2026, 1, 1), date(2026, 8, 14))
    assert len(warnings) == 1
    assert "01.01.2026" in warnings[0]


def test_stale_threshold_is_ninety_days() -> None:
    assert STALE_AFTER_DAYS == 90


def test_mapping_disclaimer_marks_interpretation() -> None:
    assert "интерпретация" in MAPPING_DISCLAIMER.lower()


def test_no_mapping_message_is_explicit() -> None:
    assert "не заполнена" in NO_MAPPING_MESSAGE
