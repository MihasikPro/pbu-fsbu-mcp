"""Read-only access to the corpus. Never opens the database for writing."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from pbu_fsbu_mcp.disclaimers import corpus_warnings
from pbu_fsbu_mcp.models import ClauseResponse, MappingEntry, MappingStatus, StandardSummary
from pbu_fsbu_mcp.temporal import EditionRef, resolve_edition, status_on

# Shared by every read path that needs "the edition in force as of a given
# date": `_mapping_status_by_standard` and `clauses_by_object` inline it
# directly; `mappings_for` reaches the same edition through `_edition`
# (Python-side `temporal.resolve_edition` over the same rows) instead of a
# second copy of this SQL, because it needs the edition's `id` to join
# against `clause` and its `edition_no` to gate `mapping.edition_from`, not
# just a filter predicate. The two used to be hand-duplicated with slightly
# different text and could drift; `UNIQUE (standard_id, effective_from)` on
# `edition` (see `schema.sql`) means there is never more than one row for
# `MAX(effective_from)` to break a tie between, so this fragment and
# `resolve_edition` are provably the same rule, not just written to look
# the same. Takes a single `?` parameter: `on_date.isoformat()`.
_EDITION_IN_FORCE_SQL = (
    "edition.effective_from = ("
    "    SELECT MAX(other.effective_from) FROM edition AS other"
    "    WHERE other.standard_id = mapping.standard_id AND other.effective_from <= ?"
    ")"
)

# A projection must not outlive the clause it targets: if an amendment drops
# a clause path, a `mapping`/lookup row still naming it must stop resolving
# instead of quietly continuing to answer for a clause that no longer exists
# in the edition now in force. Correlated on `edition.id`, no bind parameters
# of its own - always used alongside `_EDITION_IN_FORCE_SQL`.
_CLAUSE_LIVES_IN_EDITION_SQL = (
    "EXISTS ("
    "    SELECT 1 FROM clause"
    "    WHERE clause.edition_id = edition.id AND clause.path = mapping.clause_path"
    ")"
)


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


def _py_lower(value: str | None) -> str | None:
    """Unicode-aware lowercasing exposed to SQLite as `py_lower()` - see `Corpus.__init__`."""
    return value.lower() if value is not None else None


def _escape_like_fragment(fragment: str) -> str:
    """Escape `%`, `_` and `\\` in a user-supplied fragment before it reaches
    SQL `LIKE ... ESCAPE '\\'`, so the fragment is matched as a literal
    substring instead of `%`/`_` acting as LIKE wildcards - see `suggest_objects`.
    """
    return fragment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
        # SQLite's built-in LOWER() only folds ASCII; a 1C object ref is typically
        # Cyrillic (`РегистрСведений...`), so a case-insensitive lookup needs Python's
        # Unicode-aware str.lower() registered as a SQL function instead.
        self._connection.create_function("py_lower", 1, _py_lower, deterministic=True)

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
        status_by_id = self._mapping_status_by_standard([row["id"] for row in rows], on_date)
        return [
            self._summary(row, on_date, status_by_id.get(row["id"], MappingStatus.NONE))
            for row in rows
        ]

    def get_standard(self, standard_id: str, on_date: date) -> StandardSummary:
        row = self._connection.execute(
            "SELECT * FROM standard WHERE id = ?", (standard_id,)
        ).fetchone()
        if row is None:
            raise StandardNotFound(standard_id)
        status_by_id = self._mapping_status_by_standard([standard_id], on_date)
        return self._summary(row, on_date, status_by_id.get(standard_id, MappingStatus.NONE))

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

    def mappings_for(
        self, standard_id: str, clause_path: str | None, config: str
    ) -> list[MappingEntry]:
        """Projection rows for a standard, optionally narrowed to one clause.

        Resolved as of `built_at()`, not "today": a projection is maintained
        together with the corpus and is meant to reflect the edition the
        corpus considers current, not whatever the caller's clock says. Rows
        whose `edition_from` is NULL apply from the standard's first edition;
        rows naming a later edition are excluded until that edition is the
        one in force as of `built_at()`. A standard with no edition in force
        yet as of `built_at()` (e.g. a ФСБУ whose `effective_from` is still in
        the future) simply has no applicable rows - `[]`, not an error; the
        standard itself is still a real, known standard.

        A row whose `clause_path` no longer exists in the edition in force -
        because an amendment dropped that clause - is excluded too: a
        projection is a statement about a specific clause, and it must stop
        answering once that clause is gone, not keep citing wording that no
        longer exists.
        """
        edition = self._edition_or_none(standard_id, self.built_at())
        if edition is None:
            return []

        sql = (
            "SELECT mapping.clause_path AS clause_path, mapping.kind AS kind,"
            "       mapping.object_ref AS object_ref, mapping.note AS note,"
            "       mapping.confidence AS confidence, mapping.verified AS verified"
            " FROM mapping"
            " JOIN clause ON clause.edition_id = ? AND clause.path = mapping.clause_path"
            " WHERE mapping.standard_id = ? AND mapping.config = ?"
            "   AND (mapping.edition_from IS NULL OR mapping.edition_from <= ?)"
        )
        params: list[str | int] = [edition.edition_id, standard_id, config, edition.edition_no]
        if clause_path is not None:
            sql += " AND mapping.clause_path = ?"
            params.append(clause_path)
        sql += " ORDER BY mapping.confidence DESC, mapping.object_ref"

        rows = self._connection.execute(sql, params).fetchall()
        return [
            MappingEntry(
                clause_path=row["clause_path"],
                kind=row["kind"],
                object_ref=row["object_ref"],
                presentation=self._presentation(row["object_ref"], config),
                note=row["note"],
                confidence=row["confidence"],
                verified=bool(row["verified"]),
            )
            for row in rows
        ]

    def its_links_for(
        self, standard_id: str, clause_path: str | None
    ) -> list[dict[str, str | bool]]:
        """ИТС reference rows for a standard, optionally narrowed to one clause.

        Keyed on `standard_id` + `clause_path`, not `clause.id` - same reasoning
        as `mappings_for`: a reference is a statement about the norm, not about
        one edition's clause row.
        """
        sql = (
            "SELECT clause_path, its_id, title, summary, verified"
            " FROM its_link"
            " WHERE standard_id = ?"
        )
        params: list[str] = [standard_id]
        if clause_path is not None:
            sql += " AND clause_path = ?"
            params.append(clause_path)
        sql += " ORDER BY clause_path, its_id"
        return [
            {**dict(row), "verified": bool(row["verified"])}
            for row in self._connection.execute(sql, params).fetchall()
        ]

    def clauses_by_object(
        self, object_ref: str, config: str
    ) -> list[dict[str, str | int | bool]]:
        """Reverse lookup: which clauses of which standards are implemented by this object.

        Keyed on `standard_id` + `clause_path` like `mappings_for`, not on a
        `clause.id` join - the `mapping` table stores `clause_path` directly (see
        `schema.sql`). Resolved as of `built_at()` for the same reason `mappings_for`
        does it, through the identical `_EDITION_IN_FORCE_SQL` fragment so the two
        cannot silently disagree about which edition is "current" - and, like
        `mappings_for`, excludes a row whose `clause_path` no longer exists in that
        edition (`_CLAUSE_LIVES_IN_EDITION_SQL`). `DISTINCT` because a standard can
        in principle have more than one `edition` row satisfying the join before
        `_EDITION_IN_FORCE_SQL` narrows it to one - see that fragment's docstring
        for why the schema now makes that impossible, kept here as a second line of
        defense against a duplicated result row rather than a duplicated fact.
        Lookup is case-insensitive - `object_ref` is normally typed by hand while
        looking at a live configuration, casing of 1C names is not reliable. Each
        row carries its own (canonically cased) `object_ref` and a `presentation`
        resolved from it via `_presentation` - `mappings_for` gives the object a
        human-readable name the same way, and this reverse lookup must not answer
        with only a bare identifier when the forward lookup does not.
        """
        sql = (
            "SELECT DISTINCT mapping.standard_id AS standard_id,"
            "       standard.title AS standard_title,"
            "       mapping.clause_path AS clause_path,"
            "       mapping.kind AS kind,"
            "       mapping.object_ref AS object_ref,"
            "       mapping.note AS note,"
            "       mapping.confidence AS confidence,"
            "       mapping.verified AS verified"
            " FROM mapping"
            " JOIN standard ON standard.id = mapping.standard_id"
            " JOIN edition ON edition.standard_id = mapping.standard_id"
            " WHERE mapping.config = ? AND py_lower(mapping.object_ref) = py_lower(?)"
            "   AND " + _EDITION_IN_FORCE_SQL + ""
            "   AND (mapping.edition_from IS NULL OR mapping.edition_from <= edition.edition_no)"
            "   AND " + _CLAUSE_LIVES_IN_EDITION_SQL + ""
            " ORDER BY mapping.confidence DESC, mapping.standard_id, mapping.clause_path"
        )
        rows = self._connection.execute(
            sql, (config, object_ref, self.built_at().isoformat())
        ).fetchall()
        return [
            {
                **dict(row),
                "verified": bool(row["verified"]),
                # Looked up from the row's own (canonically cased) object_ref,
                # not the caller's `object_ref` argument - the lookup above is
                # case-insensitive, so the two can differ in casing.
                "presentation": self._presentation(row["object_ref"], config),
            }
            for row in rows
        ]

    def known_configs(self) -> list[str]:
        """Every configuration name that has an object catalogue, sorted.

        Lets a caller distinguish "this config has no projection for this
        object" from "this config isn't one the server knows about at all" -
        see `is_known_config`.
        """
        rows = self._connection.execute(
            "SELECT DISTINCT config FROM config_object ORDER BY config"
        ).fetchall()
        return [row["config"] for row in rows]

    def is_known_config(self, config: str) -> bool:
        """True if `config` has an object catalogue at all (e.g. "bp30")."""
        row = self._connection.execute(
            "SELECT 1 FROM config_object WHERE config = ? LIMIT 1", (config,)
        ).fetchone()
        return row is not None

    def is_known_object(self, object_ref: str, config: str) -> bool:
        """True if `object_ref` is listed in the configuration's object catalogue.

        Distinguishes "known object, no projection yet" from "no such object" -
        both look identical if you only look at `clauses_by_object` being empty.
        """
        row = self._connection.execute(
            "SELECT 1 FROM config_object WHERE config = ? AND py_lower(ref) = py_lower(?)",
            (config, object_ref),
        ).fetchone()
        return row is not None

    def suggest_objects(self, fragment: str, config: str, limit: int = 10) -> list[str]:
        """Object refs from the catalogue whose ref or presentation contains `fragment`.

        Draws from the full object catalogue (`config_object`), not only objects
        that already have a mapping row - an object that exists in the configuration
        but has no projection yet is a far more useful suggestion than nothing.
        `fragment` is escaped before it reaches `LIKE` so a caller-supplied `%`
        or `_` is matched literally instead of acting as a wildcard - without
        this, a bare `"%"` fragment silently matched every object in the catalogue.
        """
        escaped = _escape_like_fragment(fragment)
        rows = self._connection.execute(
            "SELECT ref FROM config_object"
            " WHERE config = ?"
            "   AND (py_lower(ref) LIKE py_lower(?) ESCAPE '\\'"
            "        OR py_lower(presentation) LIKE py_lower(?) ESCAPE '\\')"
            " ORDER BY ref LIMIT ?",
            (config, f"%{escaped}%", f"%{escaped}%", limit),
        ).fetchall()
        return [row["ref"] for row in rows]

    def _presentation(self, object_ref: str, config: str) -> str:
        row = self._connection.execute(
            "SELECT presentation FROM config_object WHERE config = ? AND ref = ?",
            (config, object_ref),
        ).fetchone()
        return row["presentation"] if row else object_ref

    def _edition(self, standard_id: str, on_date: date) -> EditionRef:
        edition = self._edition_or_none(standard_id, on_date)
        if edition is None:
            raise NoEditionOnDate(standard_id, on_date)
        return edition

    def _edition_or_none(self, standard_id: str, on_date: date) -> EditionRef | None:
        """Same resolution as `_edition`, but `None` instead of raising
        `NoEditionOnDate` when the standard exists but has no edition in force
        yet on `on_date` - the caller decides whether that is an error (`_edition`)
        or simply "nothing applies yet" (`mappings_for`). Still raises
        `StandardNotFound` for a `standard_id` with no editions at all, since
        that is never a valid "nothing applies yet" case - see `mappings_for`,
        which validates `standard_id` through `Corpus.get_standard` before
        this is reached and therefore never hits that branch itself.
        """
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
        return resolve_edition(refs, on_date)

    def _mapping_status_by_standard(
        self, standard_ids: list[str], on_date: date
    ) -> dict[str, MappingStatus]:
        """`MappingStatus` for each of `standard_ids` that has an applicable `mapping`
        row as of `on_date`; a standard absent from the result has none (`NONE`).

        One query for however many standards are being summarised - `list_standards`
        used to run this per row, turning a page of standards into a page of queries.
        A mapping applies once its `edition_from` (NULL = the standard's first edition)
        no longer exceeds the edition number in force on `on_date`; a standard with no
        edition yet in force on that date contributes no rows and is simply absent
        from the result.

        Resolved through the identical `_EDITION_IN_FORCE_SQL` fragment `clauses_by_object`
        uses, and excludes a row whose `clause_path` no longer exists in that edition
        (`_CLAUSE_LIVES_IN_EDITION_SQL`) for the same reason `mappings_for` does -
        a standard whose only applicable row targets a clause an amendment dropped
        must not keep reporting a mapping for it.

        `MIN(mapping.verified)` folds a standard's applicable rows to `0` (SQLite's
        integer for `verified = 0`) the moment any one of them is unverified, and to
        `1` only when every applicable row is verified - `DRAFT` vs. `VERIFIED`,
        decided by SQLite instead of pulling every row into Python to check.
        """
        if not standard_ids:
            return {}
        placeholders = ",".join("?" for _ in standard_ids)
        sql = (
            "SELECT mapping.standard_id AS standard_id,"
            "       MIN(mapping.verified) AS all_verified"
            " FROM mapping"
            " JOIN edition ON edition.standard_id = mapping.standard_id"
            " WHERE mapping.standard_id IN (" + placeholders + ")"
            " AND " + _EDITION_IN_FORCE_SQL + ""
            " AND (mapping.edition_from IS NULL OR mapping.edition_from <= edition.edition_no)"
            " AND " + _CLAUSE_LIVES_IN_EDITION_SQL + ""
            " GROUP BY mapping.standard_id"
        )
        rows = self._connection.execute(sql, (*standard_ids, on_date.isoformat())).fetchall()
        return {
            row["standard_id"]: (
                MappingStatus.VERIFIED if row["all_verified"] else MappingStatus.DRAFT
            )
            for row in rows
        }

    def _summary(
        self, row: sqlite3.Row, on_date: date, mapping_status: MappingStatus
    ) -> StandardSummary:
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
            mapping_status=mapping_status,
            source_url=row["source_url"],
            successors=self.successors(row["id"]),
        )
