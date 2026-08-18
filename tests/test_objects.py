from pathlib import Path

import pytest
from pydantic import ValidationError

from pbu_fsbu_mcp.objects import ConfigObject, load_catalog

CATALOG = Path(__file__).resolve().parents[1] / "data" / "sources" / "objects" / "bp30.yaml"


def test_catalog_loads() -> None:
    catalog = load_catalog(CATALOG)
    assert "РегистрСведений.ПараметрыАмортизацииОС" in catalog


def test_catalog_is_keyed_by_ref() -> None:
    catalog = load_catalog(CATALOG)
    assert catalog["01.01"].kind == "счёт"


def test_every_entry_has_presentation() -> None:
    assert all(item.presentation for item in load_catalog(CATALOG).values())


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ConfigObject(ref="X", kind="таблица", presentation="Нечто")


def test_duplicate_ref_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "dup.yaml"
    path.write_text(
        "- ref: '01.01'\n  kind: счёт\n  presentation: Первый\n"
        "- ref: '01.01'\n  kind: счёт\n  presentation: Дубль\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate object ref"):
        load_catalog(path)
