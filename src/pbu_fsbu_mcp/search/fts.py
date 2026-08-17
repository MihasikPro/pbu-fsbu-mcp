"""FTS5 + BM25 search over the lemmatised clause index."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from pbu_fsbu_mcp.db import read_only_uri
from pbu_fsbu_mcp.models import SearchHit
from pbu_fsbu_mcp.search.morphology import lemmatize
from pbu_fsbu_mcp.temporal import EditionRef, resolve_edition

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
        match_expression = self._to_match_expression(lemmas)
        params = [match_expression, *active_editions, limit]
        rows = self._connection.execute(sql, params).fetchall()
        return [
            SearchHit(
                standard_id=row["standard_id"],
                standard_title=row["standard_title"],
                path=row["path"],
                heading=row["heading"],
                snippet=row["text"][:_SNIPPET_CHARS],
                score=-float(row["score"]),
            )
            for row in rows
        ]

    @staticmethod
    def _to_match_expression(lemmas: str) -> str:
        """Quote every lemma so FTS5 operators in user input are treated literally."""
        return " OR ".join(f'"{lemma}"' for lemma in lemmas.split())

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
