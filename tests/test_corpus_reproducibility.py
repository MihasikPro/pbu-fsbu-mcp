"""The committed corpus is reproducible by construction from committed inputs.

Every standard in `data/sources/standards/*.yaml` is derived from exactly one
committed snapshot - a Minfin document-page fixture in `tests/fixtures/pages/`
for the 28 HTML-sourced standards, or the human-reviewed OCR transcript in
`tests/fixtures/fsbu_27_2021_ocr.txt` for ФСБУ 27/2021 (see
`etl.draft_yaml._fetch_clauses_minfin_pdf` - its own page renders no text at
all). Re-running the same pure extraction pipeline (`extract_clauses_html` /
`parse_clauses` + `render`) against that snapshot must reproduce the
committed YAML byte for byte - no network access, no OCR software required.

Any extractor change that shifts a standard's output without the source
snapshot changing shows up here as a diff, so drift between the pipeline and
the committed corpus can never go unnoticed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from etl.clause_parser import ParsedClause, parse_clauses
from etl.draft_yaml import SOURCE_HTML, SOURCE_MINFIN_PDF, render
from etl.minfin_document import extract_clauses_html
from etl.registry import REGISTRY_URL, RegistryRow, parse

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SOURCES_DIR = _REPO_ROOT / "data" / "sources" / "standards"
_PAGES_DIR = Path(__file__).parent / "fixtures" / "pages"
_REGISTRY_FIXTURE = Path(__file__).parent / "fixtures" / "minfin_registry.html"
_FSBU_27_2021_OCR_FIXTURE = Path(__file__).parent / "fixtures" / "fsbu_27_2021_ocr.txt"

_STANDALONE_PDF_ID = "fsbu-27-2021"


def _registry_rows() -> dict[str, RegistryRow]:
    return {row.id: row for row in parse(_REGISTRY_FIXTURE.read_bytes(), REGISTRY_URL)}


def _committed_source(standard_id: str) -> str:
    return (_SOURCES_DIR / f"{standard_id}.yaml").read_text(encoding="utf-8")


def _rendered_body(row: RegistryRow, clauses: list[ParsedClause], *, source: str) -> str:
    """`render()`'s output minus its draft banner - what actually gets promoted
    into `data/sources/standards/`."""
    lines = render(row, clauses, source=source).splitlines(keepends=True)
    body_start = next(i for i, line in enumerate(lines) if not line.startswith("#"))
    return "".join(lines[body_start:])


_ROWS = _registry_rows()
_HTML_SOURCED_IDS = sorted(
    path.stem for path in _PAGES_DIR.glob("*.html") if path.stem != _STANDALONE_PDF_ID
)


@pytest.mark.parametrize("standard_id", _HTML_SOURCED_IDS)
def test_html_sourced_standard_reproduces_byte_for_byte(standard_id: str) -> None:
    row = _ROWS[standard_id]
    html = (_PAGES_DIR / f"{standard_id}.html").read_bytes()
    clauses = parse_clauses(extract_clauses_html(html))
    assert _rendered_body(row, clauses, source=SOURCE_HTML) == _committed_source(standard_id)


def test_fsbu_27_2021_reproduces_byte_for_byte_from_the_reviewed_ocr_transcript() -> None:
    # No PDF fetch, no Tesseract: `fsbu_27_2021_ocr.txt` already *is* the
    # human-reviewed transcript (CONTRIBUTING.md) of the standard's own PDF
    # attachment - parsing it directly is exactly what
    # `_fetch_clauses_minfin_pdf` does once OCR has produced that same text.
    row = _ROWS[_STANDALONE_PDF_ID]
    text = _FSBU_27_2021_OCR_FIXTURE.read_text(encoding="utf-8")
    clauses = parse_clauses(text)
    body = _rendered_body(row, clauses, source=SOURCE_MINFIN_PDF)
    assert body == _committed_source(_STANDALONE_PDF_ID)


def test_fsbu_27_2021_clause_5_has_no_stray_preposition_before_abzatsem() -> None:
    """OCR transcript regression: an unreviewed transcription introduced a stray
    "в" ("...пункта и В абзацем первым пункта 6...") that is not grammatical
    Russian and does not appear anywhere else the same exact phrase
    ("абзацем первым пункта 6") occurs later in the same clause. CONTRIBUTING.md
    promises OCR text never enters the corpus without line-by-line proofing
    against the scan - this line had not actually been proofed."""
    assert "и в абзацем" not in _FSBU_27_2021_OCR_FIXTURE.read_text(encoding="utf-8")
    assert "и в абзацем" not in _committed_source(_STANDALONE_PDF_ID)


def test_every_committed_standard_has_a_reproducibility_check() -> None:
    """Guards against a 30th standard landing in the corpus with no snapshot."""
    committed_ids = {path.stem for path in _SOURCES_DIR.glob("*.yaml")}
    covered_ids = set(_HTML_SOURCED_IDS) | {_STANDALONE_PDF_ID}
    assert covered_ids == committed_ids


def test_fsbu_6_2020_keeps_its_hand_verified_clause_count() -> None:
    # The canonical regression target for the whole extraction pipeline
    # (see tests/test_minfin_document.py and tests/test_draft_yaml.py):
    # 52 top-level clauses, 50 lettered subclauses, 2 conclusions.
    row = _ROWS["fsbu-6-2020"]
    html = (_PAGES_DIR / "fsbu-6-2020.html").read_bytes()
    clauses = parse_clauses(extract_clauses_html(html))
    top_level = {clause.path for clause in clauses if clause.parent_path is None}
    lettered = {
        clause.path
        for clause in clauses
        if clause.parent_path is not None and "заключение" not in clause.path
    }
    conclusions = {clause.path for clause in clauses if "заключение" in clause.path}
    assert len(top_level) == 52
    assert len(lettered) == 50
    assert len(conclusions) == 2
    assert _rendered_body(row, clauses, source=SOURCE_HTML) == _committed_source("fsbu-6-2020")
