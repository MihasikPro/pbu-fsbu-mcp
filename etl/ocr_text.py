"""Recognise text in a published order PDF.

Official sources publish these acts as scans with no text layer, so plain
extraction returns nothing. `has_text_layer` exists so the cheap path is
taken automatically if that ever changes.
"""

from __future__ import annotations

import io
import os
import re
from collections.abc import Iterable

DEFAULT_DPI = 300
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\n(\w)")
_SINGLE_NEWLINE_RE = re.compile(r"(?<!\n)\n(?!\n)")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def normalise_hyphenation(text: str) -> str:
    """Join words split across lines and collapse soft line breaks."""
    joined = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    joined = _SINGLE_NEWLINE_RE.sub(" ", joined)
    return _MULTI_SPACE_RE.sub(" ", joined).strip()


def has_text_layer(pdf_bytes: bytes) -> bool:
    """True when the PDF already carries extractable text."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return any((page.extract_text() or "").strip() for page in reader.pages)


def extract(
    pdf_bytes: bytes, dpi: int = DEFAULT_DPI, pages: Iterable[int] | None = None
) -> str:
    """Return recognised text, page by page, separated by blank lines."""
    import pymupdf
    import pytesseract
    from PIL import Image

    tesseract_cmd = os.environ.get("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    # pymupdf ships a py.typed marker but its bound methods carry no
    # annotations, so mypy still sees these specific calls as untyped.
    document = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
    indexes = list(pages) if pages is not None else range(document.page_count)

    recognised: list[str] = []
    for index in indexes:
        pixmap = document[index].get_pixmap(dpi=dpi)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))  # type: ignore[no-untyped-call]
        recognised.append(pytesseract.image_to_string(image, lang="rus"))

    return "\n\n".join(recognised)
