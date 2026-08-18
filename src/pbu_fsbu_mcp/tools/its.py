"""References to ИТС articles.

Only identifiers, titles and our own one-or-two-sentence summaries are stored.
Full ИТС texts are licensed content and are fetched by the client through the
`1c-code-check-mcp` server under the user's own subscription.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP

from pbu_fsbu_mcp.db import ClauseNotFound, Corpus, CorpusError, NoEditionOnDate
from pbu_fsbu_mcp.disclaimers import ITS_SUMMARY_DISCLAIMER, verification_warning

HINT = (
    "Полный текст статьи получите инструментом fetch_its сервера 1c-code-check-mcp, "
    "передав ему its_id. Здесь хранятся только идентификаторы и краткие выжимки."
)
NO_LINKS_MESSAGE = "Ссылки на ИТС для этого стандарта пока не подобраны."


def get_its_references_payload(
    corpus: Corpus, standard_id: str, clause_path: str | None
) -> dict[str, Any]:
    """Build the `get_its_references` response for `standard_id`.

    Raises `ValueError` for an unknown `standard_id` or `clause_path` - same
    contract as `get_clause`/`get_1c_mapping`. Without this, an unresolvable
    id or path silently looked like "a real standard/clause with no ИТС links
    yet" instead of "this id does not exist".
    """
    try:
        summary = corpus.get_standard(standard_id, corpus.built_at())
        if clause_path is not None:
            _check_clause_path(corpus, standard_id, clause_path, summary.effective_from)
        links = corpus.its_links_for(standard_id, clause_path)
    except CorpusError as exc:
        raise ValueError(str(exc)) from exc

    warnings = [*corpus.warnings(), *verification_warning(bool(link["verified"]) for link in links)]
    return {
        "standard_id": standard_id,
        "hint": HINT,
        "disclaimer": ITS_SUMMARY_DISCLAIMER,
        "warnings": warnings,
        "message": "" if links else NO_LINKS_MESSAGE,
        "links": links,
    }


def _check_clause_path(
    corpus: Corpus, standard_id: str, clause_path: str, first_effective_from: date
) -> None:
    """Raise `ClauseNotFound` if `clause_path` is not a real clause of `standard_id`.

    Resolved as of `built_at()`, falling back to the standard's first edition when
    it is not yet in force as of that date - the same fallback
    `tools.clauses._clause_with_fallback` uses for `get_clause` on a pre-effective date.
    """
    try:
        paths = corpus.clause_paths(standard_id, corpus.built_at())
    except NoEditionOnDate:
        paths = corpus.clause_paths(standard_id, first_effective_from)
    if clause_path not in paths:
        raise ClauseNotFound(standard_id, clause_path, paths)


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
