"""Full-text search tool over clause texts."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from pbu_fsbu_mcp.db import Corpus
from pbu_fsbu_mcp.search.backend import SearchBackend
from pbu_fsbu_mcp.tools.registry import parse_on_date

MAX_LIMIT = 50


def search_clauses_payload(
    backend: SearchBackend,
    corpus: Corpus,
    query: str,
    standard_ids: list[str] | None,
    on_date: str | None,
    limit: int,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit должен быть положительным числом")
    effective_limit = min(limit, MAX_LIMIT)
    as_of = parse_on_date(on_date)

    hits = backend.search(query, standard_ids, as_of, effective_limit)
    message = (
        ""
        if hits
        else "По запросу ничего не найдено. Попробуйте переформулировать или снять фильтр по стандартам."
    )
    return {
        "as_of_date": as_of.isoformat(),
        "limit": effective_limit,
        "message": message,
        "warnings": corpus.warnings(),
        "hits": [hit.model_dump(mode="json") for hit in hits],
    }


def register(server: FastMCP, corpus: Corpus, backend: SearchBackend) -> None:
    @server.tool(
        description=(
            "Поиск пунктов стандартов по естественно-языковому запросу. "
            "Возвращает наиболее релевантные пункты со сниппетами; "
            "полный текст получайте через get_clause."
        )
    )
    def search_clauses(
        query: str,
        standard_ids: list[str] | None = None,
        on_date: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        return search_clauses_payload(backend, corpus, query, standard_ids, on_date, limit)
