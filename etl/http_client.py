"""The only place in the project that performs network access.

Every response is cached on disk so that parsers can be exercised offline
against a byte-identical copy of what the live source returned.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Deliberately without the repository URL. Measured 2026-09-21 against the live
# registry: the same request returns 200 with "pbu-fsbu-mcp/0.1" and 503 as soon
# as the User-Agent contains "github.com" (in any shape - with or without a
# scheme, with or without the "+" convention); "curl/…" and "wget/…" are refused
# the same way. The ministry's WAF started doing this between 2026-09-14 and
# 2026-09-21 and it is what broke the etl-watch run. The project name alone
# identifies the client and is accepted - do not put the repo link back.
USER_AGENT = "pbu-fsbu-mcp/0.1"
TIMEOUT_SECONDS = 30.0


class FetchError(RuntimeError):
    """Every way `fetch` can fail to obtain a body, under one type.

    Callers decide what a failed fetch means (retry, skip, abort) without
    importing `httpx` - transport and HTTP-status errors are wrapped here so
    that network access stays contained in this module.
    """


class CacheMiss(FetchError):
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

    try:
        response = httpx.get(
            url,
            timeout=TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise FetchError(f"Не удалось загрузить {url}: {error}") from error

    path.write_bytes(response.content)
    return response.content
