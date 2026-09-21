from pathlib import Path

import pytest

from etl.http_client import USER_AGENT, CacheMiss, FetchError, cache_path_for, fetch


def test_cache_path_is_deterministic(tmp_path: Path) -> None:
    first = cache_path_for("https://example.org/a", tmp_path)
    second = cache_path_for("https://example.org/a", tmp_path)
    assert first == second


def test_cache_paths_differ_per_url(tmp_path: Path) -> None:
    assert cache_path_for("https://example.org/a", tmp_path) != cache_path_for(
        "https://example.org/b", tmp_path
    )


def test_offline_read_returns_cached_bytes(tmp_path: Path) -> None:
    url = "https://example.org/a"
    cache_path_for(url, tmp_path).write_bytes(b"cached payload")
    assert fetch(url, tmp_path, live=False) == b"cached payload"


def test_offline_read_without_cache_raises(tmp_path: Path) -> None:
    with pytest.raises(CacheMiss, match="https://example.org/missing"):
        fetch("https://example.org/missing", tmp_path, live=False)


def test_http_error_is_wrapped_as_fetch_error(tmp_path: Path, monkeypatch) -> None:
    """A 503 must reach the caller as FetchError, not as an httpx type.

    etl.watch decides between "реестр разошёлся" and "источник недоступен" by
    catching FetchError; an unwrapped httpx exception would escape that branch.
    """
    import httpx

    url = "https://example.org/down"
    request = httpx.Request("GET", url)
    monkeypatch.setattr(
        httpx, "get", lambda *args, **kwargs: httpx.Response(503, request=request)
    )

    with pytest.raises(FetchError, match="503"):
        fetch(url, tmp_path, live=True)

    assert not cache_path_for(url, tmp_path).exists(), "Ошибочный ответ не кэшируется"


def test_transport_error_is_wrapped_as_fetch_error(tmp_path: Path, monkeypatch) -> None:
    import httpx

    def _boom(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("name resolution failed")

    monkeypatch.setattr(httpx, "get", _boom)

    with pytest.raises(FetchError, match="name resolution failed"):
        fetch("https://example.org/gone", tmp_path, live=True)


def test_cache_miss_is_a_fetch_error(tmp_path: Path) -> None:
    with pytest.raises(FetchError):
        fetch("https://example.org/missing", tmp_path, live=False)


def test_user_agent_avoids_the_token_minfin_refuses() -> None:
    """Minfin's WAF answers 503 to any User-Agent mentioning github.com.

    Measured against the live registry on 2026-09-21: identical request, 200 for
    "pbu-fsbu-mcp/0.1" and 503 once the repository URL is appended. The link is
    the obvious thing for a future reader to re-add, so it is pinned here.
    """
    assert "github.com" not in USER_AGENT.lower()
    assert USER_AGENT.startswith("pbu-fsbu-mcp/")
