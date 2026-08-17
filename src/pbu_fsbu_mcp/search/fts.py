"""FTS5 + BM25 search over the lemmatised clause index."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from pbu_fsbu_mcp.db import read_only_uri
from pbu_fsbu_mcp.models import SearchHit, StandardStatus
from pbu_fsbu_mcp.search.morphology import lemmatize
from pbu_fsbu_mcp.temporal import EditionRef, resolve_edition, status_on

_SNIPPET_CHARS = 300


class FtsSearchBackend:
    def __init__(self, db_path: Path) -> None:
        # Same URI encoding as Corpus: a raw f-string breaks on paths containing `#`.
        self._connection = sqlite3.connect(
            read_only_uri(db_path), uri=True, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row

    def search(
        self,
        query: str,
        standard_ids: list[str] | None,
        on_date: date,
        limit: int,
    ) -> list[SearchHit]:
        lemmas = lemmatize(query)
        if not lemmas:
            return []

        active_editions = self._active_edition_ids(standard_ids, on_date)
        if not active_editions:
            return []
        statuses = self._standard_statuses(standard_ids, on_date)

        placeholders = ",".join("?" for _ in active_editions)
        sql = (
            "SELECT clause.standard_id AS standard_id,"
            "       standard.title AS standard_title,"
            "       clause.path AS path,"
            "       clause.heading AS heading,"
            "       clause.text AS text,"
            "       bm25(clause_fts) AS score"
            " FROM clause_fts"
            " JOIN clause ON clause.id = clause_fts.clause_id"
            " JOIN standard ON standard.id = clause.standard_id"
            f" WHERE clause_fts MATCH ? AND clause.edition_id IN ({placeholders})"
            " ORDER BY score"
            " LIMIT ?"
        )

        # Conjunctive match first: a clause matching every query lemma is a
        # far stronger signal than one matching just any single lemma, and
        # keeps common domain terms (present in nearly every clause) from
        # drowning out the actually relevant one. Only widen to disjunctive
        # matching when the strict match finds nothing, so multi-word
        # queries still degrade gracefully instead of returning zero hits.
        params = [self._to_match_expression(lemmas, operator="AND"), *active_editions, limit]
        rows = self._connection.execute(sql, params).fetchall()
        if not rows:
            params = [self._to_match_expression(lemmas, operator="OR"), *active_editions, limit]
            rows = self._connection.execute(sql, params).fetchall()

        return [
            SearchHit(
                standard_id=row["standard_id"],
                standard_title=row["standard_title"],
                path=row["path"],
                heading=row["heading"],
                snippet=row["text"][:_SNIPPET_CHARS],
                score=-float(row["score"]),
                status=statuses[row["standard_id"]],
            )
            for row in rows
        ]

    @staticmethod
    def _to_match_expression(lemmas: str, *, operator: str) -> str:
        """Quote every lemma so FTS5 operators in user input are treated literally."""
        separator = f" {operator} "
        return separator.join(f'"{lemma}"' for lemma in lemmas.split())

    def _active_edition_ids(
        self, standard_ids: list[str] | None, on_date: date
    ) -> list[str]:
        sql = "SELECT id, standard_id, edition_no, effective_from FROM edition"
        params: list[str] = []
        if standard_ids:
            placeholders = ",".join("?" for _ in standard_ids)
            sql += f" WHERE standard_id IN ({placeholders})"
            params = list(standard_ids)
        rows = self._connection.execute(sql, params).fetchall()

        grouped: dict[str, list[EditionRef]] = {}
        for row in rows:
            grouped.setdefault(row["standard_id"], []).append(
                EditionRef(
                    edition_id=row["id"],
                    edition_no=row["edition_no"],
                    effective_from=date.fromisoformat(row["effective_from"]),
                )
            )

        resolved: list[str] = []
        for refs in grouped.values():
            edition = resolve_edition(refs, on_date)
            if edition is not None:
                resolved.append(edition.edition_id)
        return resolved

    def _standard_statuses(
        self, standard_ids: list[str] | None, on_date: date
    ) -> dict[str, StandardStatus]:
        """Force status of every standard a hit can come from, keyed by standard id.

        Resolving an edition (`_active_edition_ids`) only tells us a clause's
        *text* is applicable on `on_date` - it does not check `standard.effective_to`,
        so a repealed standard's still-resolvable edition would otherwise be
        indistinguishable from an active one. This is what makes that check explicit.
        """
        sql = "SELECT id, effective_from, effective_to FROM standard"
        params: list[str] = []
        if standard_ids:
            placeholders = ",".join("?" for _ in standard_ids)
            sql += f" WHERE id IN ({placeholders})"
            params = list(standard_ids)
        rows = self._connection.execute(sql, params).fetchall()
        return {
            row["id"]: status_on(
                date.fromisoformat(row["effective_from"]),
                date.fromisoformat(row["effective_to"]) if row["effective_to"] else None,
                on_date,
            )
            for row in rows
        }
