from datetime import date
from pathlib import Path

from etl.pravo import parse_search, search_url

FIXTURE = Path(__file__).parent / "fixtures" / "pravo_search_204n.json"


def test_search_url_contains_order_number() -> None:
    url = search_url(date(2020, 9, 17), "204н")
    assert "204" in url
    assert url.startswith("http://publication.pravo.gov.ru/")


def test_parse_search_returns_acts() -> None:
    acts = parse_search(FIXTURE.read_bytes())
    assert acts, "Фикстура не содержит ни одного документа"


def test_acts_carry_eo_number_and_title() -> None:
    act = parse_search(FIXTURE.read_bytes())[0]
    assert act.eo_number
    assert act.title


def test_act_matches_order_204n() -> None:
    act = parse_search(FIXTURE.read_bytes())[0]
    assert act.eo_number == "0001202010160010"
    assert "204н" in act.title
    assert "17.09.2020" in act.title


def test_pdf_url_is_absolute() -> None:
    act = parse_search(FIXTURE.read_bytes())[0]
    assert act.pdf_url.startswith("http")


def test_malformed_payload_returns_empty_list() -> None:
    assert parse_search(b'{"unexpected": true}') == []
