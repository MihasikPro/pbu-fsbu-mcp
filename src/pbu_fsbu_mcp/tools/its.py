"""References to ИТС articles.

Only identifiers, titles and our own one-or-two-sentence summaries are stored.
Full ИТС texts are licensed content and are fetched by the client through the
`1c-code-check-mcp` server under the user's own subscription.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from pbu_fsbu_mcp.db import Corpus

HINT = (
    "Полный текст статьи получите инструментом fetch_its сервера 1c-code-check-mcp, "
    "передав ему its_id. Здесь хранятся только идентификаторы и краткие выжимки."
)
NO_LINKS_MESSAGE = "Ссылки на ИТС для этого стандарта пока не подобраны."


def get_its_references_payload(
    corpus: Corpus, standard_id: str, clause_path: str | None
) -> dict[str, Any]:
    links = corpus.its_links_for(standard_id, clause_path)
    return {
        "standard_id": standard_id,
        "hint": HINT,
        "message": "" if links else NO_LINKS_MESSAGE,
        "links": links,
    }


def register(server: FastMCP, corpus: Corpus) -> None:
    @server.tool(
        description=(
            "Идентификаторы статей ИТС по теме пункта стандарта с краткими выжимками. "
            "Полный текст статьи читайте через fetch_its сервера 1c-code-check-mcp."
        )
    )
    def get_its_references(
        standard_id: str, clause_path: str | None = None
    ) -> dict[str, Any]:
        return get_its_references_payload(corpus, standard_id, clause_path)
