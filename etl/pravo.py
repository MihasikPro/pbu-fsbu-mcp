"""Client for the official publication portal API (publication.pravo.gov.ru).

The API is read-only, needs no key, and is documented at
http://publication.pravo.gov.ru/Help/Index

The documented search endpoint (`/api/Documents`) does not expose free-text
search: there is no `SearchText` parameter. Unrecognised query parameters are
silently ignored rather than rejected, so a client relying on `SearchText`
would appear to work while actually returning an unfiltered, unrelated result
set. The documented and verified way to find a specific ministerial order is
`Number` (exact order number) combined with `NumberSearchType=0` (exact match)
and a `DocumentDateFrom`/`DocumentDateTo` range in `DD.MM.YYYY` format - see
`search_url` below.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

BASE_URL = "http://publication.pravo.gov.ru"
PDF_TEMPLATE = f"{BASE_URL}/file/pdf?eoNumber={{eo_number}}"

# 0 = exact match, per the documented `NumberSearchType` values (1 = starts
# with, 2 = ends with, 3 = contains).
_NUMBER_SEARCH_TYPE_EXACT = 0

# The API accepts only a fixed set of page sizes; anything else is a 400.
_PAGE_SIZE = 30


@dataclass(frozen=True, slots=True)
class PublishedAct:
    eo_number: str
    title: str
    pdf_url: str


def search_url(order_date: date, order_no: str) -> str:
    """Build a search request for a ministerial order by its exact number and date.

    Uses the documented `Number` + `NumberSearchType` + `DocumentDateFrom`/
    `DocumentDateTo` parameters. `DocumentDateFrom`/`DocumentDateTo` must be
    `DD.MM.YYYY` - the ISO form is silently ignored by the API.
    """
    query = urlencode(
        {
            "Number": order_no,
            "NumberSearchType": _NUMBER_SEARCH_TYPE_EXACT,
            "DocumentDateFrom": order_date.strftime("%d.%m.%Y"),
            "DocumentDateTo": order_date.strftime("%d.%m.%Y"),
            "PageSize": _PAGE_SIZE,
            "Index": 1,
        }
    )
    return f"{BASE_URL}/api/Documents?{query}"


def parse_search(payload: bytes) -> list[PublishedAct]:
    """Extract published acts from a search response, tolerating shape drift."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []

    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []

    acts: list[PublishedAct] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        eo_number = item.get("eoNumber") or item.get("EoNumber")
        title = item.get("complexName") or item.get("name") or item.get("Name")
        if not eo_number or not title:
            continue
        acts.append(
            PublishedAct(
                eo_number=str(eo_number),
                title=str(title),
                pdf_url=PDF_TEMPLATE.format(eo_number=eo_number),
            )
        )
    return acts
