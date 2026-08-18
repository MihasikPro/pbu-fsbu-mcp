"""Read-only access to the corpus. Never opens the database for writing."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from pbu_fsbu_mcp.disclaimers import corpus_warnings
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


def _assert_thread_safe() -> None:
    """Fail loudly if this build cannot share one connection between threads."""
    if sqlite3.threadsafety < 3:
        raise RuntimeError(
            "This sqlite3 build reports threadsafety="
            f"{sqlite3.threadsafety}; the server shares one connection across "
            "requests and needs serialized mode (3)."
        )


def read_only_uri(db_path: Path) -> str:
    """Build a read-only SQLite URI that survives special characters in the path.

    Interpolating the raw path into `file:{path}?mode=ro` looks harmless but is
    not: SQLite's URI parser treats `#` as a fragment separator, so a database
    under a directory containing `#` opens *successfully* against an empty
    database and only fails later with "no such table". `as_uri()` percent-encodes
    the path, which is why this goes through it. Verified against paths containing
    a space, `#` and `%`.
    """
    return f"{db_path.resolve().as_uri()}?mode=ro"


class Corpus:
    """Query facade over the SQLite corpus.

    One connection is opened per instance and shared across requests with
    `check_same_thread=False`. That is safe because CPython's sqlite3 reports
    `threadsafety == 3` (serialized) on supported builds; `_assert_thread_safe`
    turns that assumption into a checked precondition instead of folklore.
    """

    def __init__(self, db_path: Path) -> None:
        _assert_thread_safe()
        self._connection = sqlite3.connect(
            read_only_uri(db_path), uri=True, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row

    def built_at(self) -> date:
        row = self._connection.execute("SELECT built_at FROM corpus_meta").fetchone()
        return date.fromisoformat(row["built_at"])

    def warnings(self) -> list[str]:
        """Standing warnings to attach to every response, e.g. a stale corpus.

        The single source of truth for staleness lookup - every payload function
        and the registry resource call this instead of recomputing it independently.
        """
        return corpus_warnings(self.built_at(), date.today())

    def is_populated(self) -> bool:
        """True if the corpus actually contains a built standard, not just an empty schema.

        A schema-only or literally empty SQLite file opens successfully and answers
        every query with zero rows - it must not be mistaken for a ready corpus.
        """
        (meta_count,) = self._connection.execute("SELECT COUNT(*) FROM corpus_meta").fetchone()
        (standard_count,) = self._connection.execute("SELECT COUNT(*) FROM standard").fetchone()
        return bool(meta_count) and bool(standard_count)

    def list_standards(self, on_date: date, kind: str | None = None) -> list[StandardSummary]:
        query = "SELECT * FROM standard"
        params: tuple[str, ...] = ()
        if kind is not None:
            query += " WHERE kind = ?"
            params = (kind,)
        query += " ORDER BY year, number"
        rows = self._connection.execute(query, params).fetchall()
        mapped_ids = self._mapped_standard_ids([row["id"] for row in rows], on_date)
        return [self._summary(row, on_date, row["id"] in mapped_ids) for row in rows]

    def get_standard(self, standard_id: str, on_date: date) -> StandardSummary:
        row = self._connection.execute(
            "SELECT * FROM standard WHERE id = ?", (standard_id,)
        ).fetchone()
        if row is None:
            raise StandardNotFound(standard_id)
        mapped_ids = self._mapped_standard_ids([standard_id], on_date)
        return self._summary(row, on_date, standard_id in mapped_ids)

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

        children_rows = self._connection.execute(
            "SELECT path FROM clause WHERE edition_id = ? AND parent_path = ? ORDER BY rowid",
            (edition.edition_id, clause_row["path"]),
        ).fetchall()
        children = [row["path"] for row in children_rows]

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
            children=children,
        )

    def successors(self, standard_id: str) -> list[str]:
        """Standards that replace `standard_id`, empty when none."""
        rows = self._connection.execute(
            "SELECT to_standard FROM standard_crosslink"
            " WHERE from_standard = ? AND kind = 'заменён'"
            " ORDER BY to_standard",
            (standard_id,),
        ).fetchall()
        return [row["to_standard"] for row in rows]

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

    def _mapped_standard_ids(self, standard_ids: list[str], on_date: date) -> set[str]:
        """Standards with a `mapping` row applicable to their edition in force on `on_date`.

        One query for however many standards are being summarised - `list_standards`
        used to run this per row, turning a page of standards into a page of queries.
        A mapping applies once its `edition_from` (NULL = the standard's first edition)
        no longer exceeds the edition number in force on `on_date`; a standard with no
        edition yet in force on that date contributes no rows and is simply absent
        from the result.
        """
        if not standard_ids:
            return set()
        placeholders = ",".join("?" for _ in standard_ids)
        rows = self._connection.execute(
            "SELECT DISTINCT mapping.standard_id FROM mapping"
            " JOIN edition ON edition.standard_id = mapping.standard_id"
            " WHERE mapping.standard_id IN (" + placeholders + ")"
            " AND edition.effective_from = ("
            "     SELECT MAX(other.effective_from) FROM edition AS other"
            "     WHERE other.standard_id = mapping.standard_id AND other.effective_from <= ?"
            " )"
            " AND (mapping.edition_from IS NULL OR mapping.edition_from <= edition.edition_no)",
            (*standard_ids, on_date.isoformat()),
        ).fetchall()
        return {row["standard_id"] for row in rows}

    def _summary(self, row: sqlite3.Row, on_date: date, has_mapping: bool) -> StandardSummary:
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
            successors=self.successors(row["id"]),
        )
