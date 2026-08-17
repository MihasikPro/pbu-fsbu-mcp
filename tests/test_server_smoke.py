from pathlib import Path

import pytest

from pbu_fsbu_mcp.server import build_server


def test_build_server_returns_named_instance(tmp_path: Path) -> None:
    """An existing-but-empty corpus file is not an error: the server still starts,
    just with no tools registered - see test_build_server_registers_no_tools_for_empty_corpus."""
    db_path = tmp_path / "empty.db"
    db_path.touch()
    server = build_server(db_path)
    assert server.name == "pbu-fsbu"


def test_main_rejects_unknown_transport(tmp_path: Path) -> None:
    from pbu_fsbu_mcp.server import main

    db_path = tmp_path / "empty.db"
    db_path.touch()
    exit_code = main(["--transport", "carrier-pigeon", "--db", str(db_path)])
    assert exit_code == 2


def test_build_server_raises_a_clear_error_for_a_missing_db_file(tmp_path: Path) -> None:
    """A missing corpus previously surfaced as a raw FileNotFoundError from Path.stat()."""
    missing = tmp_path / "does-not-exist.db"
    with pytest.raises(RuntimeError, match="etl.build_db"):
        build_server(missing)


@pytest.mark.anyio
async def test_build_server_registers_no_tools_for_empty_corpus(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    db_path.touch()
    server = build_server(db_path)
    assert await server.list_tools() == []


@pytest.mark.anyio
async def test_healthz_reports_unavailable_for_empty_corpus(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    db_path.touch()
    server = build_server(db_path)
    route = server._custom_starlette_routes[0]
    response = await route.endpoint(None)
    assert response.status_code == 503


@pytest.mark.anyio
async def test_healthz_reports_ok_for_a_populated_corpus(corpus_db: Path) -> None:
    server = build_server(corpus_db)
    route = server._custom_starlette_routes[0]
    response = await route.endpoint(None)
    assert response.status_code == 200
