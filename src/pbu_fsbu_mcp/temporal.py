"""Resolve which edition of a standard applies on a given date."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pbu_fsbu_mcp.models import StandardStatus


@dataclass(frozen=True, slots=True)
class EditionRef:
    edition_id: str
    edition_no: int
    effective_from: date


def resolve_edition(editions: list[EditionRef], on_date: date) -> EditionRef | None:
    """Return the newest edition that had already taken effect on `on_date`."""
    applicable = [item for item in editions if item.effective_from <= on_date]
    if not applicable:
        return None
    return max(applicable, key=lambda item: item.effective_from)


def status_on(
    effective_from: date, effective_to: date | None, on_date: date
) -> StandardStatus:
    """Classify a standard's force on `on_date`.

    `effective_to` is the first day the standard is no longer in force.
    """
    if on_date < effective_from:
        return StandardStatus.NOT_YET
    if effective_to is not None and on_date >= effective_to:
        return StandardStatus.REPEALED
    return StandardStatus.ACTIVE
