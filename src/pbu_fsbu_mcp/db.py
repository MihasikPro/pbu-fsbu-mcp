"""Read-only access to the corpus. Never opens the database for writing."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from pbu_fsbu_mcp.models import ClauseResponse, StandardSummary
from pbu_fsbu_mcp.temporal import EditionRef, resolve_edition, status_on


class CorpusError(Exception):
    """Base class for corpus lookup failures."""


class StandardNotFound(CorpusError):
    def __init__(self, standard_id: str) -> None:
        super().__init__(f"Стандарт {standard_id!r} отсутствует в корпусе")
        self.standard_id = standard_id


class NoEditionOnDate(CorpusError):
    def __init__(self, standard_id: str, on_date: date) -> None:
        super().__init__(
            f"У стандарта {standard_id!r} нет редакции, действующей на {on_date.isoformat()}"
        )
        self.standard_id = standard_id
        self.on_date = on_date


class ClauseNotFound(CorpusError):
    def __init__(self, standard_id: str, path: str, available_paths: list[str]) -> None:
        preview = ", ".join(available_paths[:20])
        super().__init__(
            f"В стандарте {standard_id!r} нет пункта {path!r}. Доступные пункты: {preview}"
        )
        self.standard_id = standard_id
        self.path = path
        self.available_paths = available_paths


def _format_order_ref(order_date: str, order_no: str) -> str:
    parsed = date.fromisoformat(order_date)
    return f"приказ Минфина России от {parsed.day:02d}.{parsed.month:02d}.{parsed.year} № {order_no}"


def _as_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class Corpus:
    """Query facade over the SQLite corpus."""

    def __init__(self, db_path: Path) -> None:
        self._connection = sqlite3.connect(
            f"file:{db_path}?mode=ro", uri=True, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row

    def built_at(self) -> date:
        row = self._connection.execute("SELECT built_at FROM corpus_meta").fetchone()
        return date.fromisoformat(row["built_at"])

    def list_standards(self, on_date: date, kind: str | None = None) -> list[StandardSummary]:
        query = "SELECT * FROM standard"
        params: tuple[str, ...] = ()
        if kind is not None:
            query += " WHERE kind = ?"
            params = (kind,)
        query += " ORDER BY year, number"
        rows = self._connection.execute(query, params).fetchall()
        return [self._summary(row, on_date) for row in rows]

    def get_standard(self, standard_id: str, on_date: date) -> StandardSummary:
        row = self._connection.execute(
            "SELECT * FROM standard WHERE id = ?", (standard_id,)
        ).fetchone()
        if row is None:
            raise StandardNotFound(standard_id)
        return self._summary(row, on_date)

    def outline(self, standard_id: str, on_date: date) -> list[tuple[str, str | None]]:
        edition = self._edition(standard_id, on_date)
        rows = self._connection.execute(
            "SELECT path, heading FROM clause WHERE edition_id = ? ORDER BY rowid",
            (edition.edition_id,),
        ).fetchall()
        return [(row["path"], row["heading"]) for row in rows]

    def clause_paths(self, standard_id: str, on_date: date) -> list[str]:
        return [path for path, _heading in self.outline(standard_id, on_date)]

    def get_clause(self, standard_id: str, path: str, on_date: date) -> ClauseResponse:
        standard_row = self._connection.execute(
            "SELECT * FROM standard WHERE id = ?", (standard_id,)
        ).fetchone()
        if standard_row is None:
            raise StandardNotFound(standard_id)

        edition = self._edition(standard_id, on_date)
        clause_row = self._connection.execute(
            "SELECT * FROM clause WHERE edition_id = ? AND path = ?",
            (edition.edition_id, path),
        ).fetchone()
        if clause_row is None:
            raise ClauseNotFound(standard_id, path, self.clause_paths(standard_id, on_date))

        parent_heading: str | None = None
        if clause_row["parent_path"]:
            parent_row = self._connection.execute(
                "SELECT heading FROM clause WHERE edition_id = ? AND path = ?",
                (edition.edition_id, clause_row["parent_path"]),
            ).fetchone()
            parent_heading = parent_row["heading"] if parent_row else None

        return ClauseResponse(
            standard_id=standard_id,
            standard_title=standard_row["title"],
            path=clause_row["path"],
            heading=clause_row["heading"],
            text=clause_row["text"],
            parent_path=clause_row["parent_path"],
            parent_heading=parent_heading,
            edition_no=edition.edition_no,
            as_of_date=on_date,
            status=status_on(
                date.fromisoformat(standard_row["effective_from"]),
                _as_date(standard_row["effective_to"]),
                on_date,
            ),
            order_ref=_format_order_ref(standard_row["order_date"], standard_row["order_no"]),
            source_url=standard_row["source_url"],
        )

    def _edition(self, standard_id: str, on_date: date) -> EditionRef:
        rows = self._connection.execute(
            "SELECT id, edition_no, effective_from FROM edition WHERE standard_id = ?",
            (standard_id,),
        ).fetchall()
        if not rows:
            raise StandardNotFound(standard_id)
        refs = [
            EditionRef(
                edition_id=row["id"],
                edition_no=row["edition_no"],
                effective_from=date.fromisoformat(row["effective_from"]),
            )
            for row in rows
        ]
        edition = resolve_edition(refs, on_date)
        if edition is None:
            raise NoEditionOnDate(standard_id, on_date)
        return edition

    def _summary(self, row: sqlite3.Row, on_date: date) -> StandardSummary:
        has_mapping = (
            self._connection.execute(
                "SELECT 1 FROM mapping JOIN clause ON clause.id = mapping.clause_id"
                " WHERE clause.standard_id = ? LIMIT 1",
                (row["id"],),
            ).fetchone()
            is not None
        )
        return StandardSummary(
            id=row["id"],
            kind=row["kind"],
            number=row["number"],
            title=row["title"],
            order_date=date.fromisoformat(row["order_date"]),
            order_no=row["order_no"],
            effective_from=date.fromisoformat(row["effective_from"]),
            effective_to=_as_date(row["effective_to"]),
            status=status_on(
                date.fromisoformat(row["effective_from"]),
                _as_date(row["effective_to"]),
                on_date,
            ),
            superseded_by=row["superseded_by"],
            has_1c_mapping=has_mapping,
            source_url=row["source_url"],
        )
