"""The only place in the project that performs network access.

Every response is cached on disk so that parsers can be exercised offline
against a byte-identical copy of what the live source returned.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

USER_AGENT = "pbu-fsbu-mcp/0.1 (+https://github.com/OWNER/pbu-fsbu-mcp)"
TIMEOUT_SECONDS = 30.0


class CacheMiss(LookupError):
    def __init__(self, url: str) -> None:
        super().__init__(f"Нет кэшированного ответа для {url}. Запустите ETL с --live.")


def cache_path_for(url: str, cache_dir: Path) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{digest}.bin"


def fetch(url: str, cache_dir: Path, *, live: bool) -> bytes:
    """Return the body of `url`, from cache when `live` is False."""
    path = cache_path_for(url, cache_dir)
    if not live:
        if not path.exists():
            raise CacheMiss(url)
        return path.read_bytes()

    import httpx

    response = httpx.get(
        url,
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    path.write_bytes(response.content)
    return response.content
