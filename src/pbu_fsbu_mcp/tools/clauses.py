"""Clause retrieval tool."""

from __future__ import annotations

from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP

from pbu_fsbu_mcp.db import Corpus, CorpusError, NoEditionOnDate
from pbu_fsbu_mcp.disclaimers import corpus_warnings
from pbu_fsbu_mcp.models import ClauseResponse, StandardStatus
from pbu_fsbu_mcp.tools.registry import parse_on_date


def get_clause_payload(
    corpus: Corpus, standard_id: str, path: str, on_date: str | None
) -> dict[str, Any]:
    as_of = parse_on_date(on_date)
    try:
        clause = _clause_with_fallback(corpus, standard_id, path, as_of)
    except CorpusError as exc:
        raise ValueError(str(exc)) from exc

    if clause.status is not StandardStatus.ACTIVE:
        clause.warnings.append(
            f"На {as_of.strftime('%d.%m.%Y')} стандарт не действует: {clause.status.value}."
        )
    clause.warnings.extend(corpus_warnings(corpus.built_at(), date.today()))

    return {
        "as_of_date": as_of.isoformat(),
        "clause": clause.model_dump(mode="json"),
    }


def _clause_with_fallback(
    corpus: Corpus, standard_id: str, path: str, as_of: date
) -> ClauseResponse:
    """Return the clause, falling back to the earliest edition for pre-effective dates."""
    try:
        return corpus.get_clause(standard_id, path, as_of)
    except NoEditionOnDate:
        summary = corpus.get_standard(standard_id, as_of)
        clause = corpus.get_clause(standard_id, path, summary.effective_from)
        clause.as_of_date = as_of
        clause.status = StandardStatus.NOT_YET
        return clause


def register(server: FastMCP, corpus: Corpus) -> None:
    @server.tool(
        description=(
            "Точный текст пункта стандарта с указанием редакции, реквизитов приказа "
            "и даты, на которую дан ответ. Пути пунктов берите из get_standard."
        )
    )
    def get_clause(
        standard_id: str, path: str, on_date: str | None = None
    ) -> dict[str, Any]:
        return get_clause_payload(corpus, standard_id, path, on_date)
