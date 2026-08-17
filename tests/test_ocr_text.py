import os
from pathlib import Path

import pytest

from etl.ocr_text import extract, has_text_layer, normalise_hyphenation

FIXTURE = Path(__file__).parent / "fixtures" / "order_204n.pdf"


def _tesseract_unavailable_reason() -> str | None:
    """Return why Tesseract can't run the OCR tests, or None if it can.

    Probes the actual binary (honouring `TESSERACT_CMD`, same as `ocr_text.extract`)
    instead of assuming a fixed install path, so this works unmodified on any OS.
    """
    import pytesseract

    tesseract_cmd = os.environ.get("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    try:
        languages = pytesseract.get_languages(config="")
    except pytesseract.TesseractNotFoundError:
        return "tesseract binary not found (set TESSERACT_CMD or add it to PATH)"

    if "rus" not in languages:
        return "tesseract 'rus' language model not installed (set TESSDATA_PREFIX)"

    return None


_SKIP_REASON = _tesseract_unavailable_reason()


@pytest.fixture(scope="session")
def first_pages_text() -> str:
    if _SKIP_REASON is not None:
        pytest.skip(_SKIP_REASON)
    return extract(FIXTURE.read_bytes(), pages=range(3, 5))


def test_official_scan_has_no_text_layer() -> None:
    """Задача существует именно потому, что официальный PDF - скан."""
    assert has_text_layer(FIXTURE.read_bytes()) is False


def test_ocr_produces_substantial_text(first_pages_text: str) -> None:
    assert len(first_pages_text) > 1000


def test_ocr_recognises_standard_name(first_pages_text: str) -> None:
    assert "Основные средства" in first_pages_text


def test_ocr_recognises_clause_numbering(first_pages_text: str) -> None:
    assert "1. Настоящий Стандарт устанавливает требования" in first_pages_text


def test_hyphenation_across_lines_is_joined() -> None:
    assert normalise_hyphenation("амортиза-\nционных") == "амортизационных"


def test_single_newlines_become_spaces() -> None:
    assert normalise_hyphenation("первая\nвторая") == "первая вторая"


def test_paragraph_breaks_are_preserved() -> None:
    assert normalise_hyphenation("первый\n\nвторой") == "первый\n\nвторой"
