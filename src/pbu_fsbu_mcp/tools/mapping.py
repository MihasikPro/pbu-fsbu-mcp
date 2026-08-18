"""Projection of standard clauses onto 1C:Bukhgalteriya 3.0 objects."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from pbu_fsbu_mcp.db import Corpus, CorpusError
from pbu_fsbu_mcp.disclaimers import MAPPING_DISCLAIMER, NO_MAPPING_MESSAGE

DEFAULT_CONFIG = "bp30"


def get_1c_mapping_payload(
    corpus: Corpus, standard_id: str, clause_path: str | None, config: str
) -> dict[str, Any]:
    """Build the `get_1c_mapping` response for `standard_id`.

    Raises `ValueError` when `standard_id` is unknown to the corpus. Never
    puts a clause's own text next to the projection - only `note` (a
    description of the implementation mechanism) and `presentation` (an
    object's catalogue name) travel alongside the standing disclaimer.
    """
    try:
        summary = corpus.get_standard(standard_id, corpus.built_at())
        entries = corpus.mappings_for(standard_id, clause_path, config)
    except CorpusError as exc:
        raise ValueError(str(exc)) from exc

    return {
        "standard_id": standard_id,
        "standard_title": summary.title,
        "config": config,
        "disclaimer": MAPPING_DISCLAIMER,
        "warnings": corpus.warnings(),
        "message": "" if entries else NO_MAPPING_MESSAGE,
        "mappings": [entry.model_dump(mode="json") for entry in entries],
    }


def register(server: FastMCP, corpus: Corpus) -> None:
    @server.tool(
        description=(
            "Как пункты стандарта реализованы в конфигурации 1С:Бухгалтерия предприятия 3.0: "
            "счета, регистры, документы, настройки учетной политики. "
            "Это экспертная интерпретация разработчиков сервера, а не текст нормы - "
            "текст пункта берите через get_clause."
        )
    )
    def get_1c_mapping(
        standard_id: str,
        clause_path: str | None = None,
        config: str = DEFAULT_CONFIG,
    ) -> dict[str, Any]:
        return get_1c_mapping_payload(corpus, standard_id, clause_path, config)
