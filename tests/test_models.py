from datetime import date

import pytest
from pydantic import ValidationError

from pbu_fsbu_mcp.models import Clause, Edition, Standard, StandardStatus


def _standard(**overrides: object) -> Standard:
    payload: dict[str, object] = {
        "id": "fsbu-6-2020",
        "kind": "ФСБУ",
        "number": "6/2020",
        "year": 2020,
        "title": "Основные средства",
        "order_date": date(2020, 9, 17),
        "order_no": "204н",
        "effective_from": date(2022, 1, 1),
        "effective_to": None,
        "superseded_by": None,
        "source_url": "https://minfin.gov.ru/",
        "editions": [],
    }
    payload.update(overrides)
    return Standard.model_validate(payload)


def test_standard_accepts_valid_payload() -> None:
    standard = _standard()
    assert standard.id == "fsbu-6-2020"
    assert standard.kind == "ФСБУ"


def test_standard_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        _standard(kind="МСФО")


def test_standard_rejects_effective_to_before_effective_from() -> None:
    with pytest.raises(ValidationError):
        _standard(effective_to=date(2021, 1, 1))


def test_edition_builds_composite_id() -> None:
    edition = Edition(
        standard_id="fsbu-6-2020",
        edition_no=1,
        amending_order=None,
        effective_from=date(2022, 1, 1),
        clauses=[],
    )
    assert edition.id == "fsbu-6-2020@1"


def test_clause_builds_composite_id() -> None:
    clause = Clause(
        edition_id="fsbu-6-2020@1",
        standard_id="fsbu-6-2020",
        path="9",
        parent_path=None,
        heading="Признание",
        text="Объект признается основным средством...",
    )
    assert clause.id == "fsbu-6-2020@1#9"


def test_clause_rejects_empty_text() -> None:
    with pytest.raises(ValidationError):
        Clause(
            edition_id="fsbu-6-2020@1",
            standard_id="fsbu-6-2020",
            path="9",
            parent_path=None,
            heading=None,
            text="   ",
        )


def test_status_values() -> None:
    assert StandardStatus.ACTIVE.value == "действует"
    assert StandardStatus.NOT_YET.value == "не вступил в силу"
    assert StandardStatus.REPEALED.value == "утратил силу"
