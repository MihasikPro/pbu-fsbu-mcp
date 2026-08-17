from pathlib import Path

import pytest

from etl.http_client import CacheMiss, cache_path_for, fetch


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
