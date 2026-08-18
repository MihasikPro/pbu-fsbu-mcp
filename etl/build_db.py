"""Build the SQLite corpus from YAML sources. The only writer to the database."""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

from pbu_fsbu_mcp.loader import load_all, load_crosslinks, load_its_links, load_mappings
from pbu_fsbu_mcp.models import Standard
from pbu_fsbu_mcp.objects import load_catalog
from pbu_fsbu_mcp.search.morphology import lemmatize

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "pbu_fsbu_mcp" / "schema.sql"


def build(sources_dir: Path, output: Path, built_at: date) -> None:
    """Rebuild `output` from every YAML file in `sources_dir`.

    Builds into a temporary file next to `output` and only swaps it into
    place with `os.replace()` (atomic on both Windows and POSIX) after every
    row is committed. If anything fails - a bad source file, a constraint
    violation - the temporary file is removed and `output` is left exactly
    as it was, so a failed rebuild can never ship a half-written or empty
    corpus in place of a good one.
    """
    standards = load_all(sources_dir)

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_output = output.with_name(f"{output.name}.tmp")
    tmp_output.unlink(missing_ok=True)

    try:
        connection = sqlite3.connect(tmp_output)
        try:
            connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            for standard in standards:
                _insert_standard(connection, standard)

            known = {standard.id for standard in standards}
            crosslinks = load_crosslinks(sources_dir.parent / "crosslinks.yaml")
            for link in crosslinks:
                if link.from_standard not in known or link.to_standard not in known:
                    print(
                        f"Связь {link.from_standard} -> {link.to_standard} пропущена:"
                        " один из стандартов отсутствует в корпусе"
                    )
                    continue
                connection.execute(
                    "INSERT INTO standard_crosslink (from_standard, to_standard, kind)"
                    " VALUES (?, ?, ?)",
                    (link.from_standard, link.to_standard, link.kind),
                )

            _insert_mappings(connection, sources_dir.parent, standards)
            _insert_its_links(connection, sources_dir.parent, standards)

            _insert_meta(connection, standards, built_at)
            connection.commit()
        finally:
            connection.close()
    except BaseException:
        tmp_output.unlink(missing_ok=True)
        raise

    os.replace(tmp_output, output)


def _insert_standard(connection: sqlite3.Connection, standard: Standard) -> None:
    connection.execute(
        "INSERT INTO standard (id, kind, number, year, title, order_date, order_no,"
        " effective_from, effective_to, superseded_by, source_url)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            standard.id,
            standard.kind,
            standard.number,
            standard.year,
            standard.title,
            standard.order_date.isoformat(),
            standard.order_no,
            standard.effective_from.isoformat(),
            standard.effective_to.isoformat() if standard.effective_to else None,
            standard.superseded_by,
            standard.source_url,
        ),
    )
    for edition in standard.editions:
        connection.execute(
            "INSERT INTO edition (id, standard_id, edition_no, amending_order, effective_from)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                edition.id,
                edition.standard_id,
                edition.edition_no,
                edition.amending_order,
                edition.effective_from.isoformat(),
            ),
        )
        for clause in edition.clauses:
            connection.execute(
                "INSERT INTO clause (id, standard_id, edition_id, path, parent_path, heading, text)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    clause.id,
                    clause.standard_id,
                    clause.edition_id,
                    clause.path,
                    clause.parent_path,
                    clause.heading,
                    clause.text,
                ),
            )
            indexed = lemmatize(f"{clause.heading or ''} {clause.text}")
            connection.execute(
                "INSERT INTO clause_fts (clause_id, lemmas) VALUES (?, ?)",
                (clause.id, indexed),
            )


def _insert_mappings(
    connection: sqlite3.Connection, sources_dir: Path, standards: list[Standard]
) -> None:
    """Load and insert projection rows for every `<config>` under `mappings/`.

    Silently does nothing when a configuration has no catalogue or no mapping
    files yet - mappings are hand-authored per config and are not expected to
    exist for every config from day one.
    """
    objects_dir = sources_dir / "objects"
    mappings_root = sources_dir / "mappings"
    if not mappings_root.exists():
        return

    for config_dir in sorted(p for p in mappings_root.iterdir() if p.is_dir()):
        catalog_path = objects_dir / f"{config_dir.name}.yaml"
        if not catalog_path.exists():
            continue
        catalog = load_catalog(catalog_path)
        for config_object in catalog.values():
            connection.execute(
                "INSERT INTO config_object (config, ref, kind, presentation) VALUES (?, ?, ?, ?)",
                (config_dir.name, config_object.ref, config_object.kind, config_object.presentation),
            )
        for mapping_file in load_mappings(config_dir, catalog, standards):
            for entry in mapping_file.mappings:
                connection.execute(
                    "INSERT INTO mapping (standard_id, clause_path, edition_from,"
                    " config, version_from, kind, object_ref, note, confidence)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        mapping_file.standard_id,
                        entry.clause_path,
                        entry.edition_from,
                        mapping_file.config,
                        mapping_file.version_from,
                        entry.kind,
                        entry.object_ref,
                        entry.note,
                        entry.confidence,
                    ),
                )


def _insert_its_links(
    connection: sqlite3.Connection, sources_dir: Path, standards: list[Standard]
) -> None:
    """Load and insert ИТС reference rows for every `data/sources/its/*.yaml` file.

    Missing directory means no ИТС references have been authored yet - silently
    does nothing, same as `_insert_mappings` does for a missing `mappings/` root.
    """
    its_dir = sources_dir / "its"
    for its_file in load_its_links(its_dir, standards):
        for link in its_file.links:
            connection.execute(
                "INSERT INTO its_link (standard_id, clause_path, edition_from,"
                " its_id, title, summary)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    its_file.standard_id,
                    link.clause_path,
                    None,
                    link.its_id,
                    link.title,
                    link.summary,
                ),
            )


def _insert_meta(
    connection: sqlite3.Connection, standards: list[Standard], built_at: date
) -> None:
    digest = hashlib.sha256()
    for standard in sorted(standards, key=lambda item: item.id):
        digest.update(f"{standard.id}|{standard.order_no}|{standard.effective_from}".encode())
    connection.execute(
        "INSERT INTO corpus_meta (built_at, registry_hash, source_snapshot_date)"
        " VALUES (?, ?, ?)",
        (built_at.isoformat(), digest.hexdigest(), built_at.isoformat()),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build-db")
    parser.add_argument("--sources", type=Path, default=Path("data/sources/standards"))
    parser.add_argument("--output", type=Path, default=Path("data/build/pbu_fsbu.db"))
    args = parser.parse_args(argv)
    build(args.sources, args.output, built_at=date.today())
    return 0


if __name__ == "__main__":
    sys.exit(main())
