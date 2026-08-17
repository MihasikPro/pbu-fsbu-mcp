"""Compact registry exposed as an MCP resource for one-shot loading."""

from __future__ import annotations

from datetime import date

from mcp.server.fastmcp import FastMCP

from pbu_fsbu_mcp.db import Corpus

_HEADER = (
    "| id | вид | номер | название | приказ | действует с | статус | проекция 1С |\n"
    "|---|---|---|---|---|---|---|---|"
)


def registry_document(corpus: Corpus, on_date: date) -> str:
    lines = [
        f"# Реестр стандартов бухгалтерского учета на {on_date.strftime('%d.%m.%Y')}",
        "",
    ]
    warnings = corpus.warnings()
    if warnings:
        lines.extend(f"> {warning}" for warning in warnings)
        lines.append("")
    lines.append(_HEADER)
    for item in corpus.list_standards(on_date):
        mapping_flag = "да" if item.has_1c_mapping else "нет"
        lines.append(
            f"| {item.id} | {item.kind} | {item.number} | {item.title} "
            f"| от {item.order_date.strftime('%d.%m.%Y')} № {item.order_no} "
            f"| {item.effective_from.strftime('%d.%m.%Y')} | {item.status.value} | {mapping_flag} |"
        )
    return "\n".join(lines)


def register(server: FastMCP, corpus: Corpus) -> None:
    @server.resource(
        "pbu-fsbu://registry",
        name="Реестр ПБУ и ФСБУ",
        description="Компактная таблица всех стандартов с реквизитами приказов и статусом.",
        mime_type="text/markdown",
    )
    def registry() -> str:
        return registry_document(corpus, date.today())
