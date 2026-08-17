"""Build the SQLite corpus from YAML sources. The only writer to the database."""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from datetime import date
from pathlib import Path

from pbu_fsbu_mcp.loader import load_all
from pbu_fsbu_mcp.models import Standard
from pbu_fsbu_mcp.search.morphology import lemmatize

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "pbu_fsbu_mcp" / "schema.sql"


def build(sources_dir: Path, output: Path, built_at: date) -> None:
    """Rebuild `output` from every YAML file in `sources_dir`."""
    standards = load_all(sources_dir)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)

    connection = sqlite3.connect(output)
    try:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        for standard in standards:
            _insert_standard(connection, standard)
        _insert_meta(connection, standards, built_at)
        connection.commit()
    finally:
        connection.close()


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
    build(args.sources, args.output, built_at=date.today())  # noqa: DTZ011
    return 0


if __name__ == "__main__":
    sys.exit(main())
