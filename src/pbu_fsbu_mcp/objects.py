"""Catalogue of 1C configuration objects that mappings may reference.

Mappings are hand-written, so a typo in an object name would silently
produce a dead reference. Every `object_ref` is validated against this
catalogue at build time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

ObjectKind = Literal[
    "счёт", "регистр", "документ", "настройкаУП", "отчёт", "обработка", "справочник"
]


class ConfigObject(BaseModel):
    ref: str
    kind: ObjectKind
    presentation: str


def load_catalog(path: Path) -> dict[str, ConfigObject]:
    """Load the object catalogue, keyed by `ref`."""
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    catalog: dict[str, ConfigObject] = {}
    for item in raw:
        entry = ConfigObject.model_validate(item)
        if entry.ref in catalog:
            raise ValueError(f"{path}: duplicate object ref {entry.ref!r}")
        catalog[entry.ref] = entry
    return catalog
