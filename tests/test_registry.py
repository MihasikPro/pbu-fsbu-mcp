from datetime import date
from pathlib import Path

from etl.registry import REGISTRY_URL, parse

FIXTURE = Path(__file__).parent / "fixtures" / "minfin_registry.html"


def _rows() -> dict[str, object]:
    parsed = parse(FIXTURE.read_bytes(), REGISTRY_URL)
    return {row.id: row for row in parsed}


def test_parses_all_twenty_nine_standards() -> None:
    assert len(parse(FIXTURE.read_bytes(), REGISTRY_URL)) == 29


def test_parses_fsbu_6_2020() -> None:
    row = _rows()["fsbu-6-2020"]
    assert row.kind == "ФСБУ"
    assert row.number == "6/2020"
    assert row.year == 2020
    assert row.title == "Основные средства"
    assert row.order_date == date(2020, 9, 17)
    assert row.order_no == "204н"
    assert row.effective_from == date(2022, 1, 1)


def test_normalises_two_digit_year() -> None:
    row = _rows()["pbu-16-02"]
    assert row.year == 2002


def test_normalises_nineties_year() -> None:
    row = _rows()["pbu-7-98"]
    assert row.year == 1998


def test_captures_expiry_for_repealed_standard() -> None:
    row = _rows()["pbu-9-99"]
    assert row.effective_to == date(2027, 1, 1)


def test_active_standard_has_no_expiry() -> None:
    assert _rows()["fsbu-6-2020"].effective_to is None


def test_parses_day_precise_effective_date() -> None:
    assert _rows()["fsbu-28-2023"].effective_from == date(2025, 4, 1)


def test_all_ids_are_unique() -> None:
    rows = parse(FIXTURE.read_bytes(), REGISTRY_URL)
    assert len({row.id for row in rows}) == len(rows)


def test_every_row_carries_source_url() -> None:
    rows = parse(FIXTURE.read_bytes(), REGISTRY_URL)
    assert all(row.source_url == REGISTRY_URL for row in rows)
