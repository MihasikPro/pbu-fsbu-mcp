"""Read and validate standard definitions from YAML sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pbu_fsbu_mcp.models import CrosslinkSource, MappingFile, Standard
from pbu_fsbu_mcp.objects import ConfigObject


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

    for edition_index, edition in enumerate(raw.get("editions") or []):
        edition["standard_id"] = standard_id
        if "edition_no" not in edition:
            raise ValueError(
                f"{path}: издание #{edition_index} не содержит обязательное поле 'edition_no'"
            )
        edition_id = f"{standard_id}@{edition['edition_no']}"
        seen: set[str] = set()
        for clause_index, clause in enumerate(edition.get("clauses") or []):
            clause["standard_id"] = standard_id
            clause["edition_id"] = edition_id
            if "path" not in clause:
                raise ValueError(
                    f"{path}: пункт #{clause_index} издания {edition_id!r} не содержит"
                    " обязательное поле 'path'"
                )
            clause_path = clause["path"]
            if clause_path in seen:
                raise ValueError(f"{path}: duplicate clause path {clause_path!r}")
            seen.add(clause_path)

    return Standard.model_validate(raw)


def load_all(directory: Path) -> list[Standard]:
    """Load every `*.yaml` in `directory`, sorted by file name.

    Two files declaring the same standard `id` would otherwise reach the builder
    intact and fail as an opaque `sqlite3.IntegrityError` on the `standard` table's
    primary key - this catches it at load time, with the offending file names.
    """
    standards: list[Standard] = []
    source_by_id: dict[str, Path] = {}
    for source_path in sorted(directory.glob("*.yaml")):
        standard = load_standard(source_path)
        if standard.id in source_by_id:
            raise ValueError(
                f"{source_path}: standard id {standard.id!r} is already declared in "
                f"{source_by_id[standard.id]}"
            )
        source_by_id[standard.id] = source_path
        standards.append(standard)
    return standards


def load_crosslinks(path: Path) -> list[CrosslinkSource]:
    """Load standard-to-standard relations; missing file means no relations."""
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [CrosslinkSource.model_validate(item) for item in raw]


MIN_CONFIDENCE = 60
# A `.заключение` path is the clause parser's pseudo-clause for unstructured
# trailing text (see `etl/clause_parser.py`) - never a stable projection target.
# `etl/validate.py` already rejects it post-build; failing here, at load time,
# gives the offending mapping file a name instead of a bare row id.
_UNSTABLE_PATH_SUFFIX = ".заключение"


def _known_clause_paths(standards: list[Standard]) -> dict[str, set[str]]:
    """Map each standard id to every clause path used across all its editions.

    A mapping row is keyed on `clause_path`, not a specific edition's `clause.id`
    (see `schema.sql`), so "the path resolves" means it exists in *some* edition -
    independent of which edition the row's own `edition_from` names.
    """
    return {
        standard.id: {clause.path for edition in standard.editions for clause in edition.clauses}
        for standard in standards
    }


def load_mappings(
    directory: Path, catalog: dict[str, ConfigObject], standards: list[Standard]
) -> list[MappingFile]:
    """Load mapping files, validating every entry against `catalog` and `standards`.

    Rejects, per entry, with the offending file's path in the message:
    - a `clause_path` ending in `.заключение` (unstable parser artifact);
    - a `clause_path` that does not resolve to a real clause of `standard_id`
      in any edition;
    - an `object_ref` absent from `catalog`;
    - a `kind` that disagrees with the catalogue's `kind` for that object;
    - `confidence` below `MIN_CONFIDENCE`.
    """
    known_clause_paths = _known_clause_paths(standards)
    files: list[MappingFile] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        mapping_file = MappingFile.model_validate(raw)
        clause_paths = known_clause_paths.get(mapping_file.standard_id, set())
        for entry in mapping_file.mappings:
            if entry.clause_path.endswith(_UNSTABLE_PATH_SUFFIX):
                raise ValueError(
                    f"{path}: clause_path {entry.clause_path!r} is invalid - "
                    f"{_UNSTABLE_PATH_SUFFIX!r} is a clause-parser artifact, not a"
                    " real clause"
                )
            if entry.clause_path not in clause_paths:
                raise ValueError(
                    f"{path}: clause_path {entry.clause_path!r} does not resolve to"
                    f" any edition of standard {mapping_file.standard_id!r}"
                )

            known = catalog.get(entry.object_ref)
            if known is None:
                raise ValueError(f"{path}: unknown object_ref {entry.object_ref!r}")
            if known.kind != entry.kind:
                raise ValueError(
                    f"{path}: kind {entry.kind!r} does not match catalogue"
                    f" kind {known.kind!r} for {entry.object_ref!r}"
                )
            if entry.confidence < MIN_CONFIDENCE:
                raise ValueError(
                    f"{path}: confidence {entry.confidence} below the {MIN_CONFIDENCE}"
                    f" floor for {entry.object_ref!r}"
                )
        files.append(mapping_file)
    return files
