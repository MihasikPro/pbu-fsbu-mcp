"""Parse the Ministry of Finance registry of accounting standards."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

REGISTRY_URL = (
    "https://minfin.gov.ru/ru/perfomance/accounting/accounting/standart/positions/"
)

_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

_TITLE_RE = re.compile(
    r"(?P<kind>ФСБУ|ПБУ)\s*(?P<number>\d+/\d+)\s*[«\"'](?P<title>[^»\"']+)[»\"']"
)
_ORDER_RE = re.compile(r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4}).*?№\s*(?P<no>\S+)")
_FULL_DATE_RE = re.compile(r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})")
_WORD_DATE_RE = re.compile(
    r"(?P<day>\d{1,2})\s+(?P<month>" + "|".join(_MONTHS) + r")\s+(?P<year>\d{4})",
    re.IGNORECASE,
)
# The registry writes applicability as "С отчетности за <год> г." - the year follows
# the word "за", not "с", so the marker word is "за" rather than "с".
_YEAR_ONLY_RE = re.compile(r"за\s*(?P<year>\d{4})\s*г", re.IGNORECASE)
# "Утрачивает силу с <дата>" - the word "с" separates the phrase from the date.
_EXPIRY_RE = re.compile(
    r"утрачивает силу(?:\s*с)?\s*(?P<date>\d{2}\.\d{2}\.\d{4})", re.IGNORECASE
)
# Applicability cells for repealed standards embed the expiry clause in the same
# string as the effective-from date, e.g. "С отчетности за 2009 г. Утрачивает силу
# с 01.01.2027 г." - strip it before parsing effective_from so its date is not
# mistaken for the effective-from date.
_EXPIRY_CLAUSE_RE = re.compile(r"утрачивает силу.*$", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True, slots=True)
class RegistryRow:
    id: str
    kind: str
    number: str
    year: int
    title: str
    order_date: date
    order_no: str
    effective_from: date
    effective_to: date | None
    source_url: str


def _normalise_year(number: str) -> int:
    """`6/2020` -> 2020, `16/02` -> 2002, `7/98` -> 1998."""
    suffix = number.split("/", 1)[1]
    value = int(suffix)
    if len(suffix) == 4:
        return value
    return 1900 + value if value >= 90 else 2000 + value


def _make_id(kind: str, number: str) -> str:
    prefix = "fsbu" if kind == "ФСБУ" else "pbu"
    return f"{prefix}-{number.replace('/', '-')}"


def _parse_effective_from(text: str) -> date:
    full = _FULL_DATE_RE.search(text)
    if full:
        return date(int(full["year"]), int(full["month"]), int(full["day"]))
    word = _WORD_DATE_RE.search(text)
    if word:
        month = _MONTHS[word["month"].lower()]
        return date(int(word["year"]), month, int(word["day"]))
    year_only = _YEAR_ONLY_RE.search(text)
    if year_only:
        return date(int(year_only["year"]), 1, 1)
    raise ValueError(f"Не удалось разобрать дату применения из {text!r}")


def _parse_effective_to(text: str) -> date | None:
    match = _EXPIRY_RE.search(text)
    if not match:
        return None
    parsed = _FULL_DATE_RE.search(match["date"])
    assert parsed is not None
    return date(int(parsed["year"]), int(parsed["month"]), int(parsed["day"]))


def parse(html: bytes, source_url: str) -> list[RegistryRow]:
    """Extract every standard from the registry page."""
    soup = BeautifulSoup(html, "lxml")
    rows: list[RegistryRow] = []

    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 3:
            continue

        joined = " ".join(cells)
        title_match = _TITLE_RE.search(joined)
        if title_match is None:
            continue

        kind = title_match["kind"]
        number = title_match["number"]

        order_cell = next((cell for cell in cells if _ORDER_RE.search(cell)), None)
        if order_cell is None:
            continue
        order_match = _ORDER_RE.search(order_cell)
        assert order_match is not None

        applicability = cells[-1]
        effective_from_text = _EXPIRY_CLAUSE_RE.sub("", applicability)
        rows.append(
            RegistryRow(
                id=_make_id(kind, number),
                kind=kind,
                number=number,
                year=_normalise_year(number),
                title=title_match["title"].strip(),
                order_date=date(
                    int(order_match["year"]), int(order_match["month"]), int(order_match["day"])
                ),
                order_no=order_match["no"].strip(".,;"),
                effective_from=_parse_effective_from(effective_from_text),
                effective_to=_parse_effective_to(joined),
                source_url=source_url,
            )
        )

    return rows
