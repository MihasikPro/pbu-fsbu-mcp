"""Extract standard text from a Minfin document page.

Every standard in the registry links to its own document page
(`https://minfin.gov.ru/ru/document?id_4=NNNN`), and - unlike the published
orders on publication.pravo.gov.ru - that page carries the full text of the
standard as server-rendered HTML: no JavaScript, no scan, no OCR. It also
covers standards published before publication.pravo.gov.ru's ~November 2011
archive start, which OCR (`etl/pravo.py` + `etl/ocr_text.py`) cannot reach at
all.

The page's `<p>` stream is not always *only* the standard's own clauses,
though. Investigation against the real markup (see
`data/drafts/*.yaml` duplicate-path audit) turned up three recurring, purely
textual patterns - none of them marked off by a dedicated container, so none
of them can be told apart by `BeautifulSoup` selectors alone:

* Some pages (mostly recent ФСБУ) render the *approving order's own*
  numbered clauses ("1. Утвердить ...", "2. Установить, что ...") before the
  standard's own body, and the body restarts its own numbering at "1." right
  after - `_leading_order_preamble_end` finds where the standard's own text
  begins and drops everything before it.
* At least one page (ПБУ 10/99) renders the entire body twice, back to back,
  with no boundary between the two copies at all - the second copy's own
  "annex begins here" marker is the only signal that a repeat has started;
  `_leading_order_preamble_end` finds *that* occurrence too and the caller
  truncates there instead of concatenating both copies.
* Several pages carry a nested annex *of the standard itself* ("Приложение
  к Положению по бухгалтерскому учету ...", worked examples) whose own
  numbering restarts at "1." and collides with the standard's real clauses -
  `_drop_nested_appendix` cuts it off.
* At least one page (ФСБУ 27/2021) renders no standard text at all: its
  `text_wrapper` is present but empty, and the standard is embedded only as
  a PDF viewer `<iframe>`. `find_standalone_pdf_url` locates that PDF's own
  direct download link (present elsewhere on the same page) so the caller
  can OCR *that* single-standard PDF instead of falling back to OCR of the
  multi-standard published order, which has no comparable per-standard
  anchor to slice on when the order enacts just one standard (see
  `etl.draft_yaml._fetch_clauses`).
* Section headings, and unnumbered subsection titles inside them
  ("Бухгалтерский баланс", "Постоянные разницы"), carry no text shape that
  reliably tells them apart from real clause text once flattened to plain
  text - but Minfin always typesets them as bold and/or centred, unlike any
  body paragraph. `_looks_like_heading_markup` detects that structurally and
  `extract_clauses_html` tags such a paragraph with `clause_parser.
  HTML_HEADING_SENTINEL` before it is joined into the returned text, so
  `parse_clauses` recognises it unconditionally instead of guessing from
  word count or punctuation.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from etl.clause_parser import EDITORIAL_NOTE_RE, HTML_HEADING_SENTINEL, parse_clauses

_MINFIN_BASE_URL = "https://minfin.gov.ru"

# The document's body - and nothing but the body - lives inside this single
# wrapper on Minfin's document-detail template: one `<p>` per paragraph, no
# further nesting, no navigation or site chrome mixed in. It was verified
# byte-for-byte against two document pages from opposite ends of the
# template's lifetime - a 2008 ПБУ and a 2023 ФСБУ - so it is tied to the
# page's content role, not to any wording that changes standard to standard.
# If a future redesign moves the text elsewhere, `looks_complete` below is
# what catches it: this function then simply returns too little text and the
# caller falls back to OCR instead of writing a near-empty draft.
#
# For a handful of standards (see module docstring) that single wrapper is
# not the standard's text alone - `_one_copy_of_the_standard` below trims it
# down to exactly the standard's own body before it is joined into text.
_CONTENT_CLASS = "text_wrapper"
_WHITESPACE_RE = re.compile(r"[ \t\xa0]+")

# The paragraph where the standard's own text begins on the page: either an
# explicit "this is the annex of order N" caption ("УТВЕРЖДЕН(О) приказом
# ...", "Приложение [№ N] к приказу ...") or, for pre-2011 ПБУ pages that
# carry no such caption at all, the parenthetical order-approval note glued
# directly under the title ("(утверждено приказом Минфина России от ...)").
# When this is not the very first paragraph, everything before it is the
# approving order's own preamble (its "Утвердить .../Установить .../
# Признать утратившими силу ..." clauses) - not part of the standard - and
# is dropped. When the marker recurs *again* later in the same page, that
# second occurrence opens a full second copy of the body (ПБУ 10/99) and
# everything from there on is dropped instead.
_ANNEX_START_RE = re.compile(
    r"^\(?\s*(?:утвержд(?:ен|ено|ена)\s+приказом|приложени[ея]\s*(?:№\s*\d+)?\s*к\s+приказ)",
    re.IGNORECASE,
)

# A nested annex *of the standard itself* (as opposed to `_ANNEX_START_RE`'s
# "annex of the order") - e.g. "Приложение к Положению по бухгалтерскому
# учету «Учет расчетов ...» ПБУ 18/02". It carries its own numbering (often
# restarting at "1") that is illustrative, not part of the standard's own
# clauses, and collides with real clause paths if left in. The caption is
# matched either as one paragraph, or - when the page wraps it across two
# `<p>` tags - as a bare "Приложение [№ N]" immediately followed by a
# "к Положению/Стандарту ..." paragraph. The "№" itself is optional even
# when a number is present - ПБУ 8/2010's own page spells it "Приложение 1
# к Положению ..." with no "№" at all.
_NESTED_APPENDIX_RE = re.compile(
    r"^приложени[ея]\s*(?:№\s*)?\d*\s*к\s+(?:положени|стандарт)", re.IGNORECASE
)
_NESTED_APPENDIX_LABEL_RE = re.compile(r"^приложени[ея]\s*(?:№\s*)?\d*\s*$", re.IGNORECASE)
_NESTED_APPENDIX_CONTINUATION_RE = re.compile(r"^к\s+(?:положени|стандарт)", re.IGNORECASE)

# Several pages append the document's footnote apparatus - one paragraph per
# footnote, each opening with its bracketed number ("[1] С изменениями,
# внесенными приказами ...") - as a contiguous run right after the standard's
# real last clause. Not part of the standard's own text. A footnote
# *definition* always opens its own paragraph this way; an inline reference
# mark inside real clause text never does, so this cannot mistake one for
# the other. Verified against the corpus: 28 such paragraphs across 6 pages,
# always a contiguous tail, zero false positives.
_FOOTNOTE_DEFINITION_RE = re.compile(r"^\[\d+\]\s")

# A clause or section number followed by a `<sup>` suffix ("17\N{SUPERSCRIPT
# ONE}." for a clause inserted between 17 and 18 by a later amending order;
# "II\N{SUPERSCRIPT ONE}." for a section inserted the same way) renders, once
# `<p>.get_text(" ", ...)` joins the tag's text nodes with spaces, as
# "17 1 ." / "II 1 .": the digit ends up detached from its base by whitespace
# on both sides. Left alone this breaks both `_CLAUSE_RE`/`_DECIMAL_CLAUSE_RE`
# (which require the digits glued together) and `_SECTION_RE` (whose marker
# excludes whitespace), so the paragraph is silently swallowed as a
# continuation of whatever clause happens to still be open - and every
# lettered subclause that follows it gets misattributed to that clause too.
# Re-gluing the suffix the way each base spells it out in the source fixes
# both: a decimal clause number takes a dot ("17" + "1" -> "17.1", matching
# `_DECIMAL_CLAUSE_RE`'s "N.M" shape); a Roman section numeral takes no
# separator at all ("II" + "1" -> "II1", matching `_SECTION_RE`'s plain
# marker shape - a Roman numeral is never itself followed by a dot before the
# clause-final one).
_SUPERSCRIPT_MARKER_RE = re.compile(r"^(?P<base>[IVXLCDM]+|\d+)\s+(?P<suffix>\d+)\s*\.")


def _reglue_superscript_marker(text: str) -> str:
    match = _SUPERSCRIPT_MARKER_RE.match(text)
    if match is None:
        return text
    base, suffix = match["base"], match["suffix"]
    separator = "." if base.isdigit() else ""
    return f"{base}{separator}{suffix}." + text[match.end() :]


# Every trimming step below slices `paragraphs` down to a contiguous range of
# itself and nothing else - never reorders, never drops an individual item
# out of sequence - so pairing each paragraph's text with its
# `_looks_like_heading_markup` flag and carrying the pair through unchanged
# is enough to keep the two in sync all the way to the final join, with none
# of these `re.match` calls ever needing to know about the pairing.
_Paragraph = tuple[str, bool]


def _drop_trailing_footnote_definitions(paragraphs: list[_Paragraph]) -> list[_Paragraph]:
    """Drop a trailing run of footnote-definition paragraphs, if any (see
    `_FOOTNOTE_DEFINITION_RE`)."""
    end = len(paragraphs)
    while end > 0 and _FOOTNOTE_DEFINITION_RE.match(paragraphs[end - 1][0]):
        end -= 1
    return paragraphs[:end]


def _one_copy_of_the_standard(paragraphs: list[_Paragraph]) -> list[_Paragraph]:
    """Trim `paragraphs` down to exactly one copy of the standard's own body."""
    annex_starts = [i for i, (text, _) in enumerate(paragraphs) if _ANNEX_START_RE.match(text)]
    if annex_starts:
        first_copy_start = annex_starts[0]
        second_copy_start = annex_starts[1] if len(annex_starts) > 1 else None
        paragraphs = paragraphs[first_copy_start:second_copy_start]

    for i, (text, _) in enumerate(paragraphs):
        if _NESTED_APPENDIX_RE.match(text):
            return paragraphs[:i]
        if (
            _NESTED_APPENDIX_LABEL_RE.match(text)
            and i + 1 < len(paragraphs)
            and _NESTED_APPENDIX_CONTINUATION_RE.match(paragraphs[i + 1][0])
        ):
            return paragraphs[:i]

    return _drop_trailing_footnote_definitions(paragraphs)


def _is_fully_wrapped(p: Tag, tag_names: tuple[str, ...]) -> bool:
    """True when every bit of `p`'s text sits inside a `tag_names` descendant.

    A paragraph that is *partly* bold (a single emphasised word inside an
    otherwise ordinary sentence) must not count - only a paragraph with
    nothing outside the wrapping tag(s) does.
    """
    full_text = p.get_text(" ", strip=True)
    wrapped = p.find_all(tag_names)
    if not wrapped:
        return False
    wrapped_text = " ".join(tag.get_text(" ", strip=True) for tag in wrapped)
    return bool(full_text) and full_text == wrapped_text


def _looks_like_heading_markup(p: Tag, text: str) -> bool:
    """True when `p`'s own markup marks it as a heading, not body text.

    Minfin typesets every heading - numbered section titles and unnumbered
    subsection titles alike - center-aligned, entirely bold, or both; body
    paragraphs use neither. An editorial/amendment note ("(введено приказом
    ...)", "(в ред. приказа ...)") is routinely centred like the heading it
    is glued under, and sometimes also wrapped in `<em>`/`<i>` - but never
    both consistently (see ПБУ 20/03 п.16's own amendment note, plain
    centred text with no `<em>` at all) - so `EDITORIAL_NOTE_RE` excludes it
    by content instead of relying on markup that is not applied
    consistently. It stays a normal (non-heading) paragraph rather than
    being dropped here: whether it is legitimate inline clause content or
    an orphaned trailer that must not become its own pseudo-clause is a
    parsing-level question `clause_parser.parse_clauses` is positioned to
    answer, not an extraction-level one.
    """
    if EDITORIAL_NOTE_RE.match(text):
        return False
    if _is_fully_wrapped(p, ("em", "i")):
        return False
    if _is_fully_wrapped(p, ("strong", "b")):
        return True
    align = str(p.get("align") or "").strip().lower()
    style = str(p.get("style") or "").lower().replace(" ", "")
    return align == "center" or "text-align:center" in style


def extract_clauses_html(html: bytes) -> str:
    """Return the standard's plain text, ready for `clause_parser.parse_clauses`.

    Each `<p>` in the document body becomes its own blank-line-separated
    paragraph - `parse_clauses` splits blocks on blank lines and treats each
    one as a candidate clause/subclause/heading opener, so collapsing
    paragraph breaks here would destroy that structure before parsing even
    starts. See the module docstring for the page-furniture (order preamble,
    duplicated body, nested appendix) trimmed out before that happens.
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

    paragraphs: list[_Paragraph] = []
    for p in wrapper.find_all("p"):
        text = _WHITESPACE_RE.sub(" ", p.get_text(" ", strip=True)).strip()
        text = _reglue_superscript_marker(text)
        if text:
            paragraphs.append((text, _looks_like_heading_markup(p, text)))

    return "\n\n".join(
        HTML_HEADING_SENTINEL + text if is_heading else text
        for text, is_heading in _one_copy_of_the_standard(paragraphs)
    )


def looks_complete(text: str, expected_min_clauses: int = 5) -> bool:
    """True when `text` parses into enough top-level clauses to be usable.

    Guards the caller against silently writing a near-empty draft when the
    page did not yield a standard at all (redesigned template, wrong id,
    an interstitial/error page rendered instead of the document).
    """
    top_level = {clause.path for clause in parse_clauses(text) if clause.parent_path is None}
    return len(top_level) >= expected_min_clauses


def find_standalone_pdf_url(html: bytes) -> str | None:
    """Return the URL of the standard's own PDF attachment, or `None` if the page
    carries no such link.

    A page whose `text_wrapper` is empty (see module docstring) still links the same
    PDF the `<iframe>` viewer embeds as a plain `<a href="...pdf">` elsewhere on the
    page - a direct download link is far simpler to resolve reliably than parsing the
    viewer's `file=` query parameter out of the `<iframe src=...>` attribute. Callers
    are expected to check `looks_complete(extract_clauses_html(html))` first and use
    this only once that has failed.
    """
    soup = BeautifulSoup(html, "lxml")
    link = soup.find("a", href=re.compile(r"\.pdf(?:[?#]|$)", re.IGNORECASE))
    if link is None:
        return None
    return urljoin(_MINFIN_BASE_URL, str(link["href"]))
