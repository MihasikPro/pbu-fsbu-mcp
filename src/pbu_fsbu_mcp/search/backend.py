"""Search backend protocol.

The FTS implementation is the only one today; a hybrid embedding backend can
be added later without touching the tools, as long as it satisfies this
protocol.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from pbu_fsbu_mcp.models import SearchHit


class SearchBackend(Protocol):
    def search(
        self,
        query: str,
        standard_ids: list[str] | None,
        on_date: date,
        limit: int,
    ) -> list[SearchHit]: ...
