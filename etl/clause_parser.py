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
# spelling of each Roman numeral.
_SECTION_RE = re.compile(r"^(?P<marker>[^\s.]{1,6})\.\s+(?P<heading>.+)$")
_HEADING_MAX_WORDS = 6
_SENTENCE_END = (".", ",", ";", ":")

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


def parse_clauses(text: str) -> list[ParsedClause]:
    """Return clauses in document order, attaching the enclosing section heading.

    Clause and subclause bodies routinely wrap across several OCR lines, and are
    sometimes split further by a spurious blank line or a page marker landing
    mid-sentence. Any paragraph that does not open a new clause, subclause, or
    section heading is treated as a continuation of whichever clause is
    currently open and is appended to it, rather than being dropped.
    """
    heading: str | None = None
    last_top_level: str | None = None
    last_subclause_letter: str | None = None
    current: _OpenClause | None = None
    clauses: list[_OpenClause] = []

    for raw_block in _blocks(_PAGE_FURNITURE_RE.sub("", text)):
        section_heading = _match_section_heading(raw_block)
        if section_heading is not None:
            heading = section_heading
            # A heading never appears mid-clause in a well-formed document;
            # closing the open clause here stops unrelated stray text from
            # ever being glued onto it across a section boundary.
            current = None
            continue

        block = normalise_hyphenation(raw_block)
        if not block:
            continue

        subclause_letter, subclause_end = _match_subclause(block, last_subclause_letter)
        if subclause_letter is not None and last_top_level is not None:
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
            last_top_level = clause_match["number"]
            last_subclause_letter = None
            current = _OpenClause(path=last_top_level, parent_path=None, heading=heading)
            current.parts.append(block[clause_match.end() :].strip())
            clauses.append(current)
            continue

        if current is not None:
            current.parts.append(block)

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
