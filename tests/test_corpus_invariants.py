"""Guard against non-standard text leaking into the committed corpus.

`etl.minfin_document` and `etl.clause_parser` slice a standard's own text out
of pages and scans that also carry the approving order's preamble, an
approval stamp, footnote apparatus, appendix captions, and amendment
attributions. When that slicing fails, the leftover editorial text is
grammatical and confidently formatted - it reads exactly like a real clause
- so nothing downstream notices it is not the standard's own text. These
tests exist to catch that class of defect directly in the committed YAML,
independent of any single extractor bug.

Every check here operates on `clause.text` only (not `clause.heading`) and
scans the full committed corpus in `data/sources/standards/*.yaml`.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

SOURCES_DIR = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"

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
# 4000 chars: comfortably above the corpus's real p99 (1799 chars) and its
# longest legitimate clause (pbu-18-02 п.14, ~3229 chars - a worked numeric
# example genuinely part of the standard's own text), while still catching
# every known appendix/footnote-glue outlier before their fix (12628, 4206,
# 3791, 3697, 3214 chars).
_MAX_SANE_CLAUSE_LENGTH = 4000


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
