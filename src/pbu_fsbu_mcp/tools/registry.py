"""Registry tools: `list_standards` and `get_standard`."""

from __future__ import annotations

from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP

from pbu_fsbu_mcp.db import Corpus, CorpusError


def parse_on_date(value: str | None) -> date:
    """Parse an ISO date, defaulting to today."""
    if value is None:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"on_date должен быть датой в формате ГГГГ-ММ-ДД, получено {value!r}") from exc


def list_standards_payload(
    corpus: Corpus, kind: str | None, on_date: str | None
) -> dict[str, Any]:
    as_of = parse_on_date(on_date)
    summaries = corpus.list_standards(as_of, kind=kind)
    return {
        "as_of_date": as_of.isoformat(),
        "warnings": corpus.warnings(),
        "standards": [summary.model_dump(mode="json") for summary in summaries],
    }


def get_standard_payload(
    corpus: Corpus, standard_id: str, on_date: str | None
) -> dict[str, Any]:
    as_of = parse_on_date(on_date)
    try:
        summary = corpus.get_standard(standard_id, as_of)
        outline = corpus.outline(standard_id, as_of)
    except CorpusError as exc:
        raise ValueError(str(exc)) from exc
    return {
        "as_of_date": as_of.isoformat(),
        "warnings": corpus.warnings(),
        "standard": summary.model_dump(mode="json"),
        "outline": [{"path": path, "heading": heading} for path, heading in outline],
    }


def register(server: FastMCP, corpus: Corpus) -> None:
    @server.tool(
        description=(
            "Перечень стандартов бухгалтерского учета (ПБУ и ФСБУ) с реквизитами приказов "
            "и статусом действия на указанную дату."
        )
    )
    def list_standards(kind: str | None = None, on_date: str | None = None) -> dict[str, Any]:
        return list_standards_payload(corpus, kind, on_date)

    @server.tool(
        description=(
            "Метаданные стандарта и его оглавление по пунктам без текстов. "
            "Используйте get_clause, чтобы получить текст конкретного пункта."
        )
    )
    def get_standard(standard_id: str, on_date: str | None = None) -> dict[str, Any]:
        return get_standard_payload(corpus, standard_id, on_date)
