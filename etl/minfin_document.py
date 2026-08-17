"""Extract standard text from a Minfin document page.

Every standard in the registry links to its own document page
(`https://minfin.gov.ru/ru/document?id_4=NNNN`), and - unlike the published
orders on publication.pravo.gov.ru - that page carries the full text of the
standard as server-rendered HTML: no JavaScript, no scan, no OCR. It also
covers standards published before publication.pravo.gov.ru's ~November 2011
archive start, which OCR (`etl/pravo.py` + `etl/ocr_text.py`) cannot reach at
all.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from etl.clause_parser import parse_clauses

# The document's body - and nothing but the body - lives inside this single
# wrapper on Minfin's document-detail template: one `<p>` per paragraph, no
# further nesting, no navigation or site chrome mixed in. It was verified
# byte-for-byte against two document pages from opposite ends of the
# template's lifetime - a 2008 ПБУ and a 2023 ФСБУ - so it is tied to the
# page's content role, not to any wording that changes standard to standard.
# If a future redesign moves the text elsewhere, `looks_complete` below is
# what catches it: this function then simply returns too little text and the
# caller falls back to OCR instead of writing a near-empty draft.
_CONTENT_CLASS = "text_wrapper"
_WHITESPACE_RE = re.compile(r"[ \t\xa0]+")


def extract_clauses_html(html: bytes) -> str:
    """Return the standard's plain text, ready for `clause_parser.parse_clauses`.

    Each `<p>` in the document body becomes its own blank-line-separated
    paragraph - `parse_clauses` splits blocks on blank lines and treats each
    one as a candidate clause/subclause/heading opener, so collapsing
    paragraph breaks here would destroy that structure before parsing even
    starts.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()

    wrapper = soup.find("div", class_=_CONTENT_CLASS)
    if wrapper is None:
        return ""

    # A `<br>` inside a paragraph is a line break, not a paragraph break;
    # left in place it would glue the words on either side of it together
    # once bs4 drops the (text-less) tag during extraction.
    for br in wrapper.find_all("br"):
        br.replace_with(" ")

    paragraphs: list[str] = []
    for p in wrapper.find_all("p"):
        text = _WHITESPACE_RE.sub(" ", p.get_text(" ", strip=True)).strip()
        if text:
            paragraphs.append(text)

    return "\n\n".join(paragraphs)


def looks_complete(text: str, expected_min_clauses: int = 5) -> bool:
    """True when `text` parses into enough top-level clauses to be usable.

    Guards the caller against silently writing a near-empty draft when the
    page did not yield a standard at all (redesigned template, wrong id,
    an interstitial/error page rendered instead of the document).
    """
    top_level = {clause.path for clause in parse_clauses(text) if clause.parent_path is None}
    return len(top_level) >= expected_min_clauses
