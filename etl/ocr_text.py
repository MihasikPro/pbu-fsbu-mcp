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


def extract_text_layer(pdf_bytes: bytes) -> str:
    """Return the PDF's own embedded text, page by page. Cheap alternative to
    `extract` for callers that already checked `has_text_layer` is true."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def extract(
    pdf_bytes: bytes, dpi: int = DEFAULT_DPI, pages: Iterable[int] | None = None
) -> str:
    """Return recognised text, page by page, separated by blank lines.

    Each page's recognised text is prefixed with a `[[PAGE N]]` marker (`N`
    the page's 0-based index) so that `clause_parser._PAGE_FURNITURE_RE` can
    strip it - and an immediately following page-number footer line, when
    Tesseract picks one up as part of the page's own text - before a page
    break is ever allowed to fragment a clause or leak a stray digit into
    one. Without the marker, a footer digit landing between two pages is
    indistinguishable from real body text once blocks are split on blank
    lines.
    """
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
        page_text = pytesseract.image_to_string(image, lang="rus")
        recognised.append(f"[[PAGE {index}]]\n{page_text}")

    return "\n\n".join(recognised)
