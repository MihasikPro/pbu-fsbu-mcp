"""Split an order's text into a hierarchy of numbered clauses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from etl.ocr_text import normalise_hyphenation

# OCR page furniture: a `[[PAGE N]]` marker inserted between recognised pages,
# sometimes immediately followed by a bare page-number footer line. Neither is
# document content. Left in place it either breaks a clause into unrelated
# fragments (marker glued directly onto the next clause's text) or leaks
# stray digits into a clause body (the footer line) - so both are stripped
# before the text is split into paragraphs.
_PAGE_FURNITURE_RE = re.compile(r"^\[\[PAGE \d+\]\][ \t]*\n(?:\d{1,4}[ \t]*\n)?", re.MULTILINE)

# `\s*`, not `\s+`: OCR occasionally drops the space after the clause-number
# period ("25.В бухгалтерском балансе..."), and the marker is unambiguous
# without it - it only has to be recognised at the very start of a block.
_CLAUSE_RE = re.compile(r"^(?P<number>\d+)\.\s*")

# A clause inserted between two existing ones by a later amending order is
# numbered "5.1", "7.3", "20.2" and so on, rather than with a lettered
# subclause - a common pattern in repeatedly amended ПБУ texts (e.g. ПБУ
# 1/2008). Tried before `_CLAUSE_RE` so it wins on these markers; otherwise
# `_CLAUSE_RE` would stop at the first dot and misread "7.3. В исключительных
# случаях..." as a bare clause "7" - colliding with the real clause 7 that
# appears earlier in the same document and silently merging their text.
# The closing dot is optional (`\.?`, not `\.`): the source is inconsistent
# about it even within the same document - compare "5.1. Организация..."
# (dot present) with "15.1 Организации..." (dot dropped before the next
# word) - so both spellings are accepted once the "N.M" shape itself is
# unambiguous.
_DECIMAL_CLAUSE_RE = re.compile(r"^(?P<number>\d+\.\d+)\.?\s*")
_SUBCLAUSE_RE = re.compile(r"^(?P<letter>[а-я])\)\s*")

# `б)` and `з)` are the two subclause markers Tesseract reliably misreads as
# digits in this document ("б" -> "6", "з" -> "3" - visual confusables). A
# digit is accepted as a subclause marker only when it lands exactly where
# that letter is expected next in the enclosing clause's enumeration - never
# for a digit found elsewhere, and never out of sequence. This keeps the
# normalisation from swallowing an unrelated numbered list.
_DIGIT_SUBCLAUSE_RE = re.compile(r"^(?P<digit>[36])\)\s*")
_DIGIT_LETTER_CONFUSABLES = {"6": "б", "3": "з"}
# Russian legal-drafting enumeration: skips "й", "ъ", "ы", "ь" (never used as
# list markers because they are easily confused with neighbouring letters).
_LETTER_SEQUENCE = "абвгдежзиклмнопрстуфхцчшщэюя"

# A section heading ("I." OCR-corrupted to things like "Ш.", "ГУ.", "\У1.",
# or even a bare "1." that collides with clause numbering) is a short,
# single physical OCR line with no sentence-ending punctuation. Real clause
# text - even a one-line clause - is always a full sentence and ends with
# one, which is what tells the two apart without hardcoding every corrupted
# spelling of each Roman numeral. The marker's dot tolerates a preceding
# space (`\s*\.`, not `\.`): Minfin's HTML sometimes splits a heading's
# numeral and its dot into two adjacent `<strong>` runs ("<strong>V</strong>
# <strong>. Раскрытие...</strong>"), and `get_text(" ", ...)` then inserts a
# space between them ("V . Раскрытие...") that a literal `\.` would reject.
_SECTION_RE = re.compile(r"^(?P<marker>[^\s.]{1,6})\s*\.\s+(?P<heading>.+)$")
# Deliberately still 6, not raised: real section titles run up to 11 words
# ("Пересчет выраженной в иностранной валюте стоимости активов и
# обязательств в рубли"), well past any word limit that would still reject
# every false positive below - but those titles are now recognised through
# `HTML_HEADING_SENTINEL` instead (see the sentinel handling in
# `parse_clauses`), which does not consult this limit at all. Raising it
# here would only widen this heuristic's own blast radius: Russian legal
# abbreviations that end a word in a bare dot ("п." "пп.") make an
# amendment-attribution parenthetical - "(п. 3 в ред. приказа Минфина России
# от 30.05.2022 № 87н)" - structurally indistinguishable from a numbered
# heading once its word count is allowed through, and it is exactly the
# shape `test_no_amendment_attribution_as_entire_body` guards against
# (confirmed: raising this past ~9 words reintroduces that regression on
# fsbu-26-2020's "ж¹)" subclause, verified via `git stash` bisection).
_HEADING_MAX_WORDS = 6
_SENTENCE_END = (".", ",", ";", ":")

# Minfin marks every heading in its HTML - numbered section titles and
# unnumbered subsection titles alike ("Бухгалтерский баланс", "Постоянные
# разницы") - as bold and/or centred; body paragraphs use neither. That
# markup is a much more reliable heading signal than any text shape a
# marker-less title could be guessed from, so `minfin_document.
# extract_clauses_html` detects it structurally and prefixes such a
# paragraph with this sentinel before it ever reaches here - never occurs in
# real clause text or in OCR output, so it cannot collide with anything.
HTML_HEADING_SENTINEL = ""

# An editorial/amendment-attribution note - "(в ред. приказа Минфина России
# от ...)", "(введен приказом ...)", "(введено приказом ...)", "(пп. «X»
# введен приказом ...)" - records *when* a clause or subclause was amended;
# never the standard's own text. Legitimate when it sits inline as part of
# an ordinary clause's own continuation (see pbu-18-02 п.14, several such
# notes woven through one multi-paragraph clause with no lettered list at
# all) - `parse_clauses` never even consults this regex in that case, since
# the paragraph is simply appended to the open clause's own text like any
# other continuation. The defect this guards against is narrower: such a
# note landing in the *trailer* buffer used to close a lettered subclause
# list (see `flush_trailer`) and becoming - alone, or joined with unrelated
# real trailing text - a `.заключение` pseudo-clause whose defining content
# is an editorial note rather than any text of the standard. Recognised by
# content: every instance found in the corpus is a single parenthesised
# clause containing "в ред. приказ..." or "введ<en|eno|ena>... приказ...",
# case-insensitively.
EDITORIAL_NOTE_RE = re.compile(
    r"^\([^()]*(?:в\s+ред\.\s+приказ|введен\w*\s+приказ)[^()]*\)$", re.IGNORECASE
)

# An appendix opens with a standalone line naming the standard it carries -
# e.g. "ФСБУ 6/2020 «Основные средства»", usually directly under its own
# "ФЕДЕРАЛЬНЫЙ СТАНДАРТ БУХГАЛТЕРСКОГО УЧЕТА" caption - and nothing else
# shares that paragraph: the line starts right after a newline (or the start
# of text) and is followed immediately by a blank line or the end of the
# document. That is what separates a genuine appendix header from the same
# standard being *mentioned* in running prose (order preambles routinely
# list every standard the order enacts, e.g. "...ФСБУ 6/2020 «Основные
# средства» и ФСБУ 26/2020 «Капитальные..." wrapped across lines) - a
# mention is always followed by more text in the same paragraph, never by a
# paragraph break. The caption line is matched only when it immediately
# precedes the title with no blank line between them, so that slicing on
# this anchor's start does not glue it onto the *previous* appendix's last
# clause. Quotes are matched tolerantly (OCR flips between «» and straight
# quotes); the standard's number is matched and compared exactly, so two
# different standards can never resolve to the same anchor.
_APPENDIX_ANCHOR_RE = re.compile(
    r"^(?:ФЕДЕРАЛЬНЫЙ\s+СТАНДАРТ\s+БУХГАЛТЕРСКОГО\s+УЧЕТА[ \t]*\n[ \t]*)?"
    r"(?:ФСБУ|ПБУ)[ \t]*(?P<number>\d+[ \t]*/[ \t]*\d+)[ \t]*"
    r"[«\"'][^»\"'\n]*[»\"'][ \t]*"
    r"(?=\n[ \t]*\n|\Z)",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class ParsedClause:
    path: str
    parent_path: str | None
    heading: str | None
    text: str


@dataclass(slots=True)
class _OpenClause:
    """A clause or subclause whose text may still be extended by later blocks."""

    path: str
    parent_path: str | None
    heading: str | None
    parts: list[str] = field(default_factory=list)

    def finalize(self) -> ParsedClause:
        return ParsedClause(
            path=self.path,
            parent_path=self.parent_path,
            heading=self.heading,
            text=" ".join(part for part in self.parts if part).strip(),
        )


def slice_appendix(text: str, standard_number: str) -> str:
    """Return only the appendix of `text` that enacts `standard_number`.

    A single Ministry of Finance order routinely enacts several standards at
    once, each as a separate numbered appendix in one PDF. Passing the whole
    order to `parse_clauses` pulls in every appendix's clauses at once, so
    the caller must slice out the one appendix it wants first.

    The slice runs from the standard's own header line (see
    `_APPENDIX_ANCHOR_RE`) up to the next appendix's header line, or to the
    end of the text if it is the last (or only) appendix.

    An order enacting a single standard carries no such header at all - it
    goes straight from the preamble into "I. Общие положения" - so `text` is
    returned unchanged in that case, never emptied. If the order enacts
    several standards but `standard_number` is not one of them, that is a
    real error: raises `ValueError` naming what was looked for and what was
    actually found.
    """
    anchors = [
        (match.start(), _normalise_appendix_number(match["number"]))
        for match in _APPENDIX_ANCHOR_RE.finditer(text)
    ]
    if not anchors:
        return text

    target = _normalise_appendix_number(standard_number)
    starts = [offset for offset, number in anchors if number == target]
    if not starts:
        found = ", ".join(sorted({number for _, number in anchors}))
        raise ValueError(
            f"В тексте не найдено приложение для стандарта {standard_number!r} "
            f"(в документе найдены приложения для: {found})"
        )

    start = starts[0]
    later_starts = [offset for offset, _ in anchors if offset > start]
    return text[start : min(later_starts)] if later_starts else text[start:]


def _normalise_appendix_number(number: str) -> str:
    """Drop internal whitespace so `"6/2020"` and OCR's `"6 / 2020"` compare equal."""
    return re.sub(r"\s+", "", number)


def _clause_number_key(number: str) -> tuple[int, int]:
    """Order `"17"` and `"17.3"` as `(17, 0)` and `(17, 3)` for a monotonicity check."""
    major, _, minor = number.partition(".")
    return int(major), int(minor) if minor else 0


def parse_clauses(text: str) -> list[ParsedClause]:
    """Return clauses in document order, attaching the enclosing section heading.

    Clause and subclause bodies routinely wrap across several OCR lines, and are
    sometimes split further by a spurious blank line or a page marker landing
    mid-sentence. Any paragraph that does not open a new clause, subclause, or
    section heading is treated as a continuation of whichever clause is
    currently open and is appended to it, rather than being dropped.

    A document's top-level clause numbers only ever increase (skipping a
    repealed clause is fine; going back down is not). A block that opens a
    lower-or-equal top-level number - a mis-rendered section heading using
    plain Arabic digits instead of a Roman numeral ("2. Понятие событий ..."
    misread as clause "2" when clause "2" already exists), or a nested,
    independently-numbered appendix/worked example the page did not mark off
    clearly enough to be caught before parsing even starts (see
    `etl/minfin_document.py`) - is not a clause of this document and is
    discarded, along with every subclause and continuation paragraph that
    follows it, up to the next block that either resumes the real sequence or
    opens a genuine section heading.

    A paragraph that follows a lettered subclause is ambiguous on its own: it
    might still be that subclause's own text, wrapped across a spurious blank
    line (a source page break routinely splits one sentence into two blocks
    this way - see the "45.ж" -> "45.з" case in the parser tests), or it might
    be the enclosing clause's closing remark that governs the whole lettered
    list rather than any single option in it (see clauses 13 and 20 of ФСБУ
    6/2020: "Выбранный способ ... применяется ко всей группе основных
    средств." is not part of option "б", it is a statement about clause 13 as
    a whole). Which one it is can only be told from what comes *next*, so such
    a paragraph is buffered in `trailer` rather than committed immediately:
    - if another subclause of the same list follows, the enumeration is
      still open, so the buffered text was that subclause's own continuation
      and is merged back into it;
    - if a new clause, a section heading, or the end of the document follows
      instead, the enumeration is over, so the buffered text is emitted as a
      single `<clause>.заключение` pseudo-subclause attached to the clause
      as a whole (several trailing paragraphs are joined into that one entry,
      the same way an ordinary multi-paragraph clause body is joined, rather
      than inventing several numbered conclusions the source has no marker
      for).
    This is a syntactic heuristic, not a semantic one: a subclause whose own
    text is genuinely split across a blank line right before the *last* item
    of its list (no further subclause to resolve it against) would be
    misread as the clause's conclusion. That shape has not been observed in
    the corpus - the last item of a list is consistently either the end of a
    single block or ends the enumeration outright - but it is the failure
    mode to watch for if a future standard's text is laid out that way.
    """
    heading: str | None = None
    last_top_level: str | None = None
    last_top_level_key: tuple[int, int] | None = None
    last_subclause_letter: str | None = None
    current: _OpenClause | None = None
    trailer: list[str] = []
    discarding = False
    clauses: list[_OpenClause] = []

    def flush_trailer() -> None:
        """Emit any buffered trailer as the current subclause's parent's conclusion.

        Only called at a point where a subclause's own continuation has
        definitely ended (a new clause, heading, or end of document), so
        whatever is still open in `current` (if it is a subclause) is exactly
        the last subclause the trailer was tentatively attached to.

        An editorial/amendment-attribution note (`EDITORIAL_NOTE_RE`) buffered
        here is not part of the conclusion's own text - see the regex's own
        docstring for why this is the one place it is stripped rather than
        left alone. Dropped from the buffer before anything else: on its own
        it must not produce a `.заключение` pseudo-clause at all; alongside
        real trailing text (fsbu-26-2020 п.16) only the real text survives.
        """
        nonlocal trailer
        if current is not None and current.parent_path is not None:
            content = [part for part in trailer if not EDITORIAL_NOTE_RE.match(part)]
            if content:
                parent_path = current.parent_path
                conclusion = _OpenClause(
                    path=f"{parent_path}.заключение", parent_path=parent_path, heading=None
                )
                conclusion.parts.extend(content)
                clauses.append(conclusion)
        trailer = []

    def open_heading(new_heading: str) -> None:
        """Start a new section, closing whatever clause is currently open.

        A heading never appears mid-clause in a well-formed document; closing
        the open clause here stops unrelated stray text from ever being glued
        onto it across a section boundary. It also unambiguously ends any run
        of discarded, out-of-sequence blocks.
        """
        nonlocal heading, current, discarding
        flush_trailer()
        heading = new_heading
        current = None
        discarding = False

    for raw_block in _blocks(_PAGE_FURNITURE_RE.sub("", text)):
        if raw_block.startswith(HTML_HEADING_SENTINEL):
            heading_candidate = raw_block[len(HTML_HEADING_SENTINEL) :].strip()
            marker_match = _SECTION_RE.match(heading_candidate)
            if marker_match is not None:
                # A numbered heading - always applies, exactly like the
                # plain-text path below.
                open_heading(marker_match["heading"].strip())
            elif last_top_level is not None:
                # An unnumbered subsection title - only meaningful once the
                # document's own front matter (title page, order references)
                # is behind us. Before the first real clause, a bold/centred
                # paragraph with no numeral marker is title-page furniture,
                # not a heading - e.g. "ПОЛОЖЕНИЕ ПО БУХГАЛТЕРСКОМУ УЧЕТУ
                # «...»" is typeset exactly like "Бухгалтерский баланс" is,
                # and only the document position tells them apart. Dropped
                # silently here, exactly as it already was before this
                # paragraph started carrying the sentinel.
                open_heading(heading_candidate)
            continue

        section_heading = _match_section_heading(raw_block)
        if section_heading is not None:
            open_heading(section_heading)
            continue

        block = normalise_hyphenation(raw_block)
        if not block:
            continue

        subclause_letter, subclause_end = _match_subclause(block, last_subclause_letter)
        if subclause_letter is not None and discarding:
            continue
        if subclause_letter is not None and last_top_level is not None:
            # The enumeration continues, so the buffered trailer was the
            # previous subclause's own text after all - fold it back in
            # before moving on, instead of losing it to the new subclause.
            if trailer and current is not None:
                current.parts.extend(trailer)
            trailer = []
            current = _OpenClause(
                path=f"{last_top_level}.{subclause_letter}",
                parent_path=last_top_level,
                heading=None,
            )
            current.parts.append(block[subclause_end:].strip())
            clauses.append(current)
            last_subclause_letter = subclause_letter
            continue

        clause_match = _DECIMAL_CLAUSE_RE.match(block) or _CLAUSE_RE.match(block)
        if clause_match:
            key = _clause_number_key(clause_match["number"])
            if last_top_level_key is not None and key <= last_top_level_key:
                flush_trailer()
                discarding = True
                current = None
                continue
            flush_trailer()
            last_top_level = clause_match["number"]
            last_top_level_key = key
            last_subclause_letter = None
            discarding = False
            current = _OpenClause(path=last_top_level, parent_path=None, heading=heading)
            current.parts.append(block[clause_match.end() :].strip())
            clauses.append(current)
            continue

        if discarding:
            continue

        if current is not None:
            if current.parent_path is not None:
                # `current` is a lettered subclause: whether this paragraph
                # belongs to it or concludes the enclosing clause is not yet
                # decidable - see `flush_trailer` and the docstring above.
                trailer.append(block)
            else:
                current.parts.append(block)

    flush_trailer()
    return [clause.finalize() for clause in clauses]


def _match_subclause(block: str, last_letter: str | None) -> tuple[str | None, int]:
    """Match a lettered subclause marker, normalising the two digit confusables."""
    letter_match = _SUBCLAUSE_RE.match(block)
    if letter_match:
        return letter_match["letter"], letter_match.end()

    digit_match = _DIGIT_SUBCLAUSE_RE.match(block)
    if digit_match:
        letter = _DIGIT_LETTER_CONFUSABLES[digit_match["digit"]]
        if letter == _next_letter(last_letter):
            return letter, digit_match.end()

    return None, 0


def _next_letter(last_letter: str | None) -> str | None:
    """Return the letter that should follow `last_letter` in the enumeration."""
    if last_letter is None:
        return None
    index = _LETTER_SEQUENCE.find(last_letter)
    if index < 0 or index + 1 >= len(_LETTER_SEQUENCE):
        return None
    return _LETTER_SEQUENCE[index + 1]


def _match_section_heading(raw_block: str) -> str | None:
    """Return the heading text if `raw_block` looks like a section heading."""
    if "\n" in raw_block:
        return None

    match = _SECTION_RE.match(raw_block)
    if not match:
        return None

    # A purely numeric marker is a heading only for "1" - the one documented
    # collision, where Roman "I." (section "Общие положения") is OCR-read as
    # digit "1.". Every other numeric marker ("21.", "29.", ...) is a real
    # clause number whose first line happens to be short and unpunctuated
    # because a spurious blank line split its body early; treating it as a
    # heading would silently drop that clause instead of just truncating it.
    marker = match["marker"]
    if marker.isdigit() and marker != "1":
        return None

    heading_text = match["heading"].strip()
    if heading_text.endswith(_SENTENCE_END) or len(heading_text.split()) > _HEADING_MAX_WORDS:
        return None

    return heading_text


def _blocks(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
