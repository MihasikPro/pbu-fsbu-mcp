"""Referential integrity checks for a built corpus."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from pbu_fsbu_mcp.db import read_only_uri

_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "clause: пункт ссылается на несуществующую редакцию",
        (
            "SELECT clause.id FROM clause"
            " LEFT JOIN edition ON edition.id = clause.edition_id"
            " WHERE edition.id IS NULL"
        ),
    ),
    (
        "clause: пункт ссылается на несуществующий стандарт",
        (
            "SELECT clause.id FROM clause"
            " LEFT JOIN standard ON standard.id = clause.standard_id"
            " WHERE standard.id IS NULL"
        ),
    ),
    (
        "edition: редакция ссылается на несуществующий стандарт",
        (
            "SELECT edition.id FROM edition"
            " LEFT JOIN standard ON standard.id = edition.standard_id"
            " WHERE standard.id IS NULL"
        ),
    ),
    (
        "mapping: маппинг ссылается на несуществующий пункт",
        (
            "SELECT mapping.id FROM mapping"
            " LEFT JOIN clause ON clause.id = mapping.clause_id"
            " WHERE clause.id IS NULL"
        ),
    ),
    (
        "its_link: ссылка ИТС указывает на несуществующий пункт",
        (
            "SELECT its_link.id FROM its_link"
            " LEFT JOIN clause ON clause.id = its_link.clause_id"
            " WHERE clause.id IS NULL"
        ),
    ),
    (
        "crosslink: связь указывает на несуществующий пункт",
        (
            "SELECT crosslink.id FROM crosslink"
            " LEFT JOIN clause AS src ON src.id = crosslink.from_clause"
            " LEFT JOIN clause AS dst ON dst.id = crosslink.to_clause"
            " WHERE src.id IS NULL OR dst.id IS NULL"
        ),
    ),
    (
        "clause_fts: пункт отсутствует в поисковом индексе",
        (
            "SELECT clause.id FROM clause"
            " LEFT JOIN clause_fts ON clause_fts.clause_id = clause.id"
            " WHERE clause_fts.clause_id IS NULL"
        ),
    ),
    (
        "standard: superseded_by указывает на несуществующий стандарт",
        (
            "SELECT s.id FROM standard AS s"
            " LEFT JOIN standard AS target ON target.id = s.superseded_by"
            " WHERE s.superseded_by IS NOT NULL AND target.id IS NULL"
        ),
    ),
)


def _check_not_empty(connection: sqlite3.Connection) -> list[str]:
    """Reject a corpus that is structurally perfect and contains nothing.

    Every referential check below passes trivially on an empty database, so
    without this the validator would wave through exactly the failure this
    project already hit once: a build that died midway and left a valid but
    empty corpus, indistinguishable from a good one to anything downstream.
    """
    violations: list[str] = []
    for table in ("standard", "edition", "clause", "clause_fts"):
        (count,) = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if count == 0:
            violations.append(f"{table}: таблица пуста - корпус собран некорректно")
    return violations


def check(db_path: Path) -> list[str]:
    """Return a list of human-readable integrity violations."""
    connection = sqlite3.connect(read_only_uri(db_path), uri=True)
    try:
        violations: list[str] = _check_not_empty(connection)
        for label, sql in _CHECKS:
            offenders = [str(row[0]) for row in connection.execute(sql).fetchall()]
            if offenders:
                preview = ", ".join(offenders[:10])
                violations.append(f"{label} ({len(offenders)}): {preview}")
        return violations
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="validate-corpus")
    parser.add_argument("--db", type=Path, default=Path("data/build/pbu_fsbu.db"))
    args = parser.parse_args(argv)

    violations = check(args.db)
    if not violations:
        print("Целостность корпуса: нарушений нет")
        return 0
    for violation in violations:
        print(violation, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
