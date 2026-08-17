from pathlib import Path

import pytest

from pbu_fsbu_mcp.server import build_server

EXPECTED_TOOLS = {"list_standards", "get_standard", "get_clause", "search_clauses"}


@pytest.mark.anyio
async def test_all_tools_are_registered(corpus_db: Path) -> None:
    server = build_server(corpus_db)
    tools = await server.list_tools()
    assert EXPECTED_TOOLS <= {tool.name for tool in tools}


@pytest.mark.anyio
async def test_every_tool_has_a_description(corpus_db: Path) -> None:
    server = build_server(corpus_db)
    for tool in await server.list_tools():
        assert tool.description, f"У инструмента {tool.name} нет описания"


@pytest.mark.anyio
async def test_registry_resource_is_registered(corpus_db: Path) -> None:
    server = build_server(corpus_db)
    resources = await server.list_resources()
    assert any(str(resource.uri) == "pbu-fsbu://registry" for resource in resources)


@pytest.mark.anyio
async def test_get_clause_round_trip(corpus_db: Path) -> None:
    server = build_server(corpus_db)
    result = await server.call_tool(
        "get_clause", {"standard_id": "fsbu-6-2020", "path": "1", "on_date": "2026-08-14"}
    )
    assert result is not None
