"""Guard against non-standard text leaking into - or normative text silently
disappearing from - the committed corpus.

`etl.minfin_document` and `etl.clause_parser` slice a standard's own text out
of pages and scans that also carry the approving order's preamble, an
approval stamp, footnote apparatus, appendix captions, and amendment
attributions. When that slicing fails, the leftover editorial text is
grammatical and confidently formatted - it reads exactly like a real clause
- so nothing downstream notices it is not the standard's own text.

`test_no_order_preamble_imperatives` through `test_clause_length_is_sane`
below all check that direction: *extra* text that should not be there. They
scan `clause.text` only (not `clause.heading`) across the full committed
corpus in `data/sources/standards/*.yaml`, independent of any single
extractor bug.

`test_html_sourced_standard_loses_no_non_heading_paragraph` checks the
opposite, previously unguarded direction: normative text that silently
*disappeared* - a paragraph the extractor pulled out of the page but that
never made it into any clause's `text` or `heading` (see ПБУ 18/02 пп.14-15,
whose worked examples went missing this way once a false-positive heading
closed the clause mid-body). It needs the page fixture as well as the
committed YAML, since "did every paragraph land somewhere" can only be
checked against what the page actually offered.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from etl.clause_parser import (
    EDITORIAL_NOTE_RE,
    HTML_HEADING_SENTINEL,
    _match_section_heading,
    parse_clauses,
)
from etl.minfin_document import extract_clauses_html
from etl.ocr_text import normalise_hyphenation

SOURCES_DIR = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"
_PAGES_DIR = Path(__file__).parent / "fixtures" / "pages"
_STANDALONE_PDF_ID = "fsbu-27-2021"  # no HTML page to check paragraphs against - see module docstring

# --- order-preamble imperatives ---------------------------------------------
# Sentences that belong to the *approving order* itself ("Утвердить
# прилагаемый Стандарт...", "Признать утратившими силу...", "Установить,
# что...") or its closing signature block - never to the standard's own
# clauses.
_ORDER_PREAMBLE_MARKERS = (
    "Утвердить прилагаемый",
    "Признать утратившими силу",
    "Установить, что",
    "Министр А.Г. Силуанов",
)

# --- approval stamp ----------------------------------------------------------
# The "УТВЕРЖДЕН(О) приказом ..." caption that sits between the order and the
# standard's own title page, in both title-case and full-caps spelling
# (including the "ё" variant Minfin's own scans occasionally use).
_APPROVAL_STAMP_MARKERS = (
    "Утвержден приказом",
    "УТВЕРЖДЕН",
    "УТВЕРЖДЁН",
    "УТВЕРЖДЕНЫ",
)

# --- footnote-definition block -----------------------------------------------
# A footnote *definition* ("[1] С изменениями, внесенными приказами...")
# always opens a paragraph - either the very first one (a clause consisting
# of nothing but trailing footnotes) or right after the sentence it
# annotates, which `_OpenClause.finalize()` joins with a single space, so
# the marker is preceded by ". " once clause parts are flattened. An inline
# reference mark ("...рациональности[1] в соответствии...") never starts a
# paragraph this way, so this does not flag genuine inline citations.
_FOOTNOTE_DEFINITION_RE = re.compile(r"(?:^|\.\s)\[\d+\]\s")

# --- appendix caption ---------------------------------------------------------
# "Приложение [N] к Положению/Стандарту ..." or a bare "Приложение N" -
# title-case only, so a lowercase in-sentence mention ("см. приложение к
# настоящему Стандарту") is not flagged.
_APPENDIX_CAPTION_RE = re.compile(
    r"Приложени[ея]\s*(?:№\s*\d+|\d+)?\s*к\s+(?:Положению|Стандарту)"
    r"|Приложени[ея]\s*(?:№\s*\d+|\d+)\b"
)

# --- amendment attribution as the entire clause body -------------------------
# "(п. N в ред. приказа ...)" / "(введен приказом ...)" / "(пп. «X» введен
# ...)" - an editorial note about *when* a clause was amended, not the
# clause's own text. Legitimate when it sits inline next to real clause text
# (see pbu-18-02 п.14); a defect only when it is the clause's *entire* body,
# which is what the anchored `^...$` match below checks for.
_AMENDMENT_ONLY_RE = re.compile(
    r"^\([^()]*(?:в\s+ред\.\s+приказа|введена?ы?\s+приказом)[^()]*\d+н\)$",
    re.IGNORECASE,
)

# --- Roman-numeral section title as the entire clause body -------------------
# A section heading ("III. Расходы, отличные от ...") that `_match_section_
# heading` failed to recognise as a heading and that ended up filed as a
# clause's own (pseudo-subclause) body instead. Real clause text never opens
# with a bare Latin Roman numeral, and headings are short - capped at 10
# words after the marker, matching `_HEADING_MAX_WORDS`'s own ballpark, to
# avoid flagging some future clause that legitimately opens with a Roman
# numeral abbreviation ("IV квартал ...") followed by substantial text.
_ROMAN_SECTION_ONLY_RE = re.compile(r"^[IVXLCDM]+\s*\.\s*(?P<rest>[^\s].*[^\s.,;:])$")
_ROMAN_SECTION_ONLY_MAX_WORDS = 10

# --- clause length --------------------------------------------------------
# 4000 chars: comfortably above the corpus's real p99 (1712 chars) and its
# longest legitimate clause (pbu-18-02 п.14, 3229 chars - a worked numeric
# example genuinely part of the standard's own text, including its own two
# worked examples in full - see the ETL overdeletion fix report), while
# still catching every known appendix/footnote-glue outlier before their fix
# (12628, 4206, 3791, 3697, 3214 chars).
_MAX_SANE_CLAUSE_LENGTH = 4000

# --- missing-paragraph detection (the opposite direction) -------------------
# Mirrors just enough of `clause_parser.parse_clauses`'s own bookkeeping -
# clause/subclause markers and the out-of-sequence "discarding" state - to
# tell which paragraphs the parser is *documented* to drop on purpose (see
# its own docstring) apart from a paragraph that silently vanished for no
# such reason. Deliberately re-derived here rather than imported from
# `clause_parser` (beyond the already-public `EDITORIAL_NOTE_RE`,
# `HTML_HEADING_SENTINEL`, and the one private `_match_section_heading`
# needed to recognise a plain-text heading): a bug that corrupts the real
# state machine and this shadow copy the same way would go undetected
# either way, but a bug that corrupts *only* the real one is exactly what
# this test exists to catch, and sharing the buggy code would defeat that.
_TOP_LEVEL_CLAUSE_RE = re.compile(r"^(?P<number>\d+)\.\s*")
_DECIMAL_CLAUSE_RE = re.compile(r"^(?P<number>\d+\.\d+)\.?\s*")
_SUBCLAUSE_RE = re.compile(r"^(?P<letter>[а-я])\)\s*")
_DIGIT_SUBCLAUSE_RE = re.compile(r"^(?P<digit>[36])\)\s*")


def _clause_number_key(number: str) -> tuple[int, int]:
    major, _, minor = number.partition(".")
    return int(major), int(minor) if minor else 0


def _all_clauses() -> list[tuple[str, str, str]]:
    """Return `(standard_id, clause_path, clause_text)` for the whole corpus."""
    clauses: list[tuple[str, str, str]] = []
    for path in sorted(SOURCES_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for edition in document["editions"]:
            for clause in edition["clauses"]:
                clauses.append((document["id"], clause["path"], clause["text"] or ""))
    return clauses


def _format_violations(violations: list[tuple[str, str, str]]) -> str:
    lines = [f"{standard_id} п.{path}: {detail}" for standard_id, path, detail in violations]
    return f"{len(lines)} violation(s):\n" + "\n".join(lines)


def test_no_order_preamble_imperatives() -> None:
    violations = [
        (standard_id, path, marker)
        for standard_id, path, text in _all_clauses()
        for marker in _ORDER_PREAMBLE_MARKERS
        if marker in text
    ]
    assert not violations, _format_violations(violations)


def test_no_approval_stamp() -> None:
    violations = [
        (standard_id, path, marker)
        for standard_id, path, text in _all_clauses()
        for marker in _APPROVAL_STAMP_MARKERS
        if marker in text
    ]
    assert not violations, _format_violations(violations)


def test_no_footnote_definition_block() -> None:
    violations = [
        (standard_id, path, match.group())
        for standard_id, path, text in _all_clauses()
        if (match := _FOOTNOTE_DEFINITION_RE.search(text)) is not None
    ]
    assert not violations, _format_violations(violations)


def test_no_appendix_caption() -> None:
    violations = [
        (standard_id, path, match.group())
        for standard_id, path, text in _all_clauses()
        if (match := _APPENDIX_CAPTION_RE.search(text)) is not None
    ]
    assert not violations, _format_violations(violations)


def test_no_amendment_attribution_as_entire_body() -> None:
    violations = [
        (standard_id, path, text)
        for standard_id, path, text in _all_clauses()
        if _AMENDMENT_ONLY_RE.match(text.strip())
    ]
    assert not violations, _format_violations(violations)


def test_no_roman_numeral_section_title_as_entire_body() -> None:
    violations = []
    for standard_id, path, text in _all_clauses():
        match = _ROMAN_SECTION_ONLY_RE.match(text.strip())
        if match is not None and len(match["rest"].split()) <= _ROMAN_SECTION_ONLY_MAX_WORDS:
            violations.append((standard_id, path, text))
    assert not violations, _format_violations(violations)


def test_clause_length_is_sane() -> None:
    violations = [
        (standard_id, path, f"{len(text)} chars")
        for standard_id, path, text in _all_clauses()
        if len(text) > _MAX_SANE_CLAUSE_LENGTH
    ]
    assert not violations, _format_violations(violations)


def _missing_paragraphs(standard_id: str) -> list[str]:
    """Every non-heading paragraph `extract_clauses_html` produced for
    `standard_id` that does not turn up in any clause's `text` or `heading`.

    Walks the same paragraph stream `parse_clauses` consumes, tracking just
    enough state (last top-level clause number, the "discarding" run of an
    out-of-sequence numbered collision - see `clause_parser.parse_clauses`'s
    own docstring) to know which paragraphs it is *documented* to exclude:
    front matter before the first clause, a recognised heading (numbered,
    sentinel-tagged, or plain-text), a whole-paragraph editorial/amendment
    note, and a colliding out-of-sequence numbered run (a worked example's
    own internal list restarting at "1." - see ПБУ 15/2008 п.14's own
    "Примечание к примеру: 1. ... 2. ..." list). Every other paragraph must
    show up somewhere in the clauses the same input produced.
    """
    html = (_PAGES_DIR / f"{standard_id}.html").read_bytes()
    text = extract_clauses_html(html)
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    clauses = parse_clauses(text)
    haystack = " ".join(clause.text for clause in clauses) + " ".join(
        clause.heading or "" for clause in clauses
    )

    seen_first_clause = False
    discarding = False
    last_key: tuple[int, int] | None = None
    missing: list[str] = []

    for block in blocks:
        is_sentinel = block.startswith(HTML_HEADING_SENTINEL)
        raw = block[len(HTML_HEADING_SENTINEL) :] if is_sentinel else block

        if is_sentinel:
            discarding = False
            continue
        if _match_section_heading(raw) is not None:
            discarding = False
            continue

        clause_match = _DECIMAL_CLAUSE_RE.match(raw) or _TOP_LEVEL_CLAUSE_RE.match(raw)
        if clause_match:
            key = _clause_number_key(clause_match["number"])
            if last_key is not None and key <= last_key:
                discarding = True
                continue
            discarding = False
            last_key = key
            seen_first_clause = True
            raw = raw[clause_match.end() :]

        if discarding or not seen_first_clause:
            continue

        candidate = normalise_hyphenation(raw)
        if not candidate or EDITORIAL_NOTE_RE.match(candidate):
            continue
        for marker_re in (_SUBCLAUSE_RE, _DIGIT_SUBCLAUSE_RE):
            marker_match = marker_re.match(candidate)
            if marker_match:
                candidate = candidate[marker_match.end() :].strip()
                break
        if candidate and candidate not in haystack:
            missing.append(candidate)

    return missing


_HTML_SOURCED_IDS = sorted(
    path.stem for path in _PAGES_DIR.glob("*.html") if path.stem != _STANDALONE_PDF_ID
)


@pytest.mark.parametrize("standard_id", _HTML_SOURCED_IDS)
def test_html_sourced_standard_loses_no_non_heading_paragraph(standard_id: str) -> None:
    missing = _missing_paragraphs(standard_id)
    assert not missing, f"{len(missing)} paragraph(s) lost:\n" + "\n".join(
        text[:120] for text in missing
    )
