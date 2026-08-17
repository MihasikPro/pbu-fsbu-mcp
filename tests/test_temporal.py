from datetime import date

from pbu_fsbu_mcp.models import StandardStatus
from pbu_fsbu_mcp.temporal import EditionRef, resolve_edition, status_on

EDITIONS = [
    EditionRef(edition_id="s@1", edition_no=1, effective_from=date(2022, 1, 1)),
    EditionRef(edition_id="s@2", edition_no=2, effective_from=date(2024, 1, 1)),
]


def test_picks_latest_edition_effective_on_date() -> None:
    assert resolve_edition(EDITIONS, date(2025, 6, 1)).edition_no == 2


def test_picks_earlier_edition_for_earlier_date() -> None:
    assert resolve_edition(EDITIONS, date(2023, 6, 1)).edition_no == 1


def test_boundary_date_selects_new_edition() -> None:
    assert resolve_edition(EDITIONS, date(2024, 1, 1)).edition_no == 2


def test_returns_none_before_first_edition() -> None:
    assert resolve_edition(EDITIONS, date(2021, 12, 31)) is None


def test_unordered_input_is_handled() -> None:
    reversed_editions = list(reversed(EDITIONS))
    assert resolve_edition(reversed_editions, date(2025, 6, 1)).edition_no == 2


def test_status_active() -> None:
    assert status_on(date(2022, 1, 1), None, date(2026, 8, 14)) is StandardStatus.ACTIVE


def test_status_not_yet() -> None:
    assert status_on(date(2027, 1, 1), None, date(2026, 8, 14)) is StandardStatus.NOT_YET


def test_status_repealed_on_expiry_date() -> None:
    assert (
        status_on(date(2000, 1, 1), date(2027, 1, 1), date(2027, 1, 1))
        is StandardStatus.REPEALED
    )


def test_status_active_day_before_expiry() -> None:
    assert (
        status_on(date(2000, 1, 1), date(2027, 1, 1), date(2026, 12, 31))
        is StandardStatus.ACTIVE
    )
