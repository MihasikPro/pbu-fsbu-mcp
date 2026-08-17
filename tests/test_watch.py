from dataclasses import replace
from datetime import date
from pathlib import Path

from etl.registry import REGISTRY_URL, RegistryRow, parse
from etl.watch import diff_registry
from pbu_fsbu_mcp.loader import load_all
from pbu_fsbu_mcp.models import Standard

SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"
FIXTURE = Path(__file__).parent / "fixtures" / "minfin_registry.html"


def _rows() -> list[RegistryRow]:
    return parse(FIXTURE.read_bytes(), REGISTRY_URL)


def _matching_rows(standards: list[Standard]) -> list[RegistryRow]:
    """Rows from the live fixture whose id is actually present in the local corpus.

    `data/sources/standards/` only ever holds a subset of the standards the live
    registry lists - comparing the full parsed fixture against a partial corpus
    would report the missing standards as spurious `added` entries. Filtering to
    the matching slice keeps these tests correct regardless of how many standards
    happen to be committed at any given time.
    """
    ids = {standard.id for standard in standards}
    return [row for row in _rows() if row.id in ids]


def test_matching_registry_produces_empty_diff() -> None:
    standards = load_all(SOURCES)
    assert diff_registry(_matching_rows(standards), standards).is_empty


def test_new_standard_is_reported_as_added() -> None:
    standards = load_all(SOURCES)
    rows = _matching_rows(standards)
    rows.append(
        RegistryRow(
            id="fsbu-11-2027",
            kind="ФСБУ",
            number="11/2027",
            year=2027,
            title="Новый стандарт",
            order_date=date(2027, 1, 1),
            order_no="1н",
            effective_from=date(2028, 1, 1),
            effective_to=None,
            source_url=REGISTRY_URL,
            document_url="https://minfin.gov.ru/ru/document?id_4=999999",
        )
    )
    diff = diff_registry(rows, standards)
    assert "fsbu-11-2027" in diff.added
    assert not diff.is_empty


def test_disappeared_standard_is_reported_as_removed() -> None:
    standards = load_all(SOURCES)
    missing_id = standards[0].id
    rows = [row for row in _matching_rows(standards) if row.id != missing_id]
    assert missing_id in diff_registry(rows, standards).removed


def test_changed_order_number_is_reported() -> None:
    standards = load_all(SOURCES)
    rows = _matching_rows(standards)
    changed_id = rows[0].id
    rows[0] = replace(rows[0], order_no="999н")
    diff = diff_registry(rows, standards)
    assert any(changed_id in item for item in diff.changed)


def test_changed_expiry_is_reported() -> None:
    standards = load_all(SOURCES)
    rows = _matching_rows(standards)
    changed_id = rows[0].id
    rows[0] = replace(rows[0], effective_to=date(2030, 1, 1))
    diff = diff_registry(rows, standards)
    assert any(changed_id in item for item in diff.changed)
