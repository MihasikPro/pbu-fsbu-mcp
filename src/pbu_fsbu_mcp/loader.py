"""Read and validate standard definitions from YAML sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pbu_fsbu_mcp.models import Standard


def load_standard(path: Path) -> Standard:
    """Load one standard from a YAML file, filling derived identifiers."""
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    # ValueError, not TypeError, is deliberate here and below: the caller passed a
    # perfectly good Path — it is the *file's content* that is malformed. Every
    # failure of this function means "this source file is bad", and callers should
    # not have to catch two exception types to express that.
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at the document root")  # noqa: TRY004

    standard_id = raw.get("id")
    if not isinstance(standard_id, str):
        raise ValueError(f"{path}: missing string field 'id'")  # noqa: TRY004

    for edition in raw.get("editions") or []:
        edition["standard_id"] = standard_id
        edition_id = f"{standard_id}@{edition['edition_no']}"
        seen: set[str] = set()
        for clause in edition.get("clauses") or []:
            clause["standard_id"] = standard_id
            clause["edition_id"] = edition_id
            clause_path = clause["path"]
            if clause_path in seen:
                raise ValueError(f"{path}: duplicate clause path {clause_path!r}")
            seen.add(clause_path)

    return Standard.model_validate(raw)


def load_all(directory: Path) -> list[Standard]:
    """Load every `*.yaml` in `directory`, sorted by file name."""
    return [load_standard(path) for path in sorted(directory.glob("*.yaml"))]
