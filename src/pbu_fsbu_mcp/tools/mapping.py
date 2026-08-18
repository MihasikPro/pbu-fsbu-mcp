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


def find_by_1c_object_payload(corpus: Corpus, object_ref: str, config: str) -> dict[str, Any]:
    """Build the `find_by_1c_object` response: reverse lookup for `object_ref`.

    `outcome` makes the three possible cases explicit for the caller instead of
    forcing it to infer them from an empty list:
    - "mapped" - at least one clause is projected onto this object;
    - "known_no_mapping" - the object exists in the configuration's catalogue,
      but no clause is projected onto it yet (absence of a projection is not
      evidence the standard is unimplemented - see `NO_MAPPING_MESSAGE`-style wording);
    - "unknown" - the object is not in the catalogue at all, most likely a typo;
      `suggestions` then offers near matches drawn from the whole catalogue.
    """
    clauses = corpus.clauses_by_object(object_ref, config)
    known = bool(clauses) or corpus.is_known_object(object_ref, config)

    suggestions: list[str] = []
    if clauses:
        outcome = "mapped"
        message = ""
    elif known:
        outcome = "known_no_mapping"
        message = (
            "Объект известен в конфигурации, но ни один пункт стандартов ему пока "
            "не сопоставлен. Это может означать, что проекция для соответствующего "
            "стандарта пока не заполнена."
        )
    else:
        outcome = "unknown"
        suggestions = corpus.suggest_objects(object_ref, config)
        message = (
            "Такой объект не найден в каталоге конфигурации. Возможно, вы имели в виду "
            "один из объектов ниже."
            if suggestions
            else "Такой объект не найден в каталоге конфигурации."
        )

    return {
        "object_ref": object_ref,
        "config": config,
        "outcome": outcome,
        "disclaimer": MAPPING_DISCLAIMER,
        "warnings": corpus.warnings(),
        "message": message,
        "suggestions": suggestions,
        "clauses": clauses,
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

    @server.tool(
        description=(
            "Обратный поиск: какие пункты каких стандартов стоят за объектом конфигурации 1С. "
            "Принимает счет (01.01), регистр, документ или настройку учетной политики. "
            "Если объект не найден, возвращает похожие объекты каталога конфигурации."
        )
    )
    def find_by_1c_object(object_ref: str, config: str = DEFAULT_CONFIG) -> dict[str, Any]:
        return find_by_1c_object_payload(corpus, object_ref, config)
