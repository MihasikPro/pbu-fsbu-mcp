"""MCP server entry point: builds the server and selects a transport."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from pbu_fsbu_mcp.db import Corpus

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "build" / "pbu_fsbu.db"
TRANSPORTS = ("stdio", "http")


def build_server(db_path: Path, host: str = "0.0.0.0", port: int = 18010) -> FastMCP:
    """Create the FastMCP instance with tools registered against `db_path`.

    Raises `RuntimeError` if `db_path` does not exist - that always means the
    corpus was never built, not a transient runtime condition, so it fails
    loudly with instructions instead of a raw `FileNotFoundError` surfacing
    from inside sqlite3. A file that exists but contains no data (schema-only,
    or literally empty) is not an error: the server still starts with no tools
    registered, and `/healthz` reports the difference from a ready corpus.
    """
    if not db_path.exists():
        raise RuntimeError(
            f"Корпус не найден: {db_path}. Соберите его командой "
            "'python -m etl.build_db'."
        )

    server = FastMCP("pbu-fsbu", host=host, port=port)
    corpus = _open_populated_corpus(db_path)
    _register_health_route(server, db_path, corpus)

    if corpus is not None:
        from pbu_fsbu_mcp.tools import registry

        registry.register(server, corpus)

        from pbu_fsbu_mcp.tools import clauses

        clauses.register(server, corpus)

        from pbu_fsbu_mcp.search.fts import FtsSearchBackend
        from pbu_fsbu_mcp.tools import search as search_tool

        search_tool.register(server, corpus, FtsSearchBackend(db_path))

        from pbu_fsbu_mcp.tools import resources

        resources.register(server, corpus)
    return server


def _open_populated_corpus(db_path: Path) -> Corpus | None:
    """Open `db_path` and return it only if it actually contains a built corpus.

    A schema-only or literally empty SQLite file opens without error but has no
    data - `is_populated()` is what tells the two apart.
    """
    try:
        corpus = Corpus(db_path)
        if not corpus.is_populated():
            return None
    except sqlite3.OperationalError:
        return None
    return corpus


def _register_health_route(server: FastMCP, db_path: Path, corpus: Corpus | None) -> None:
    @server.custom_route("/healthz", methods=["GET"])  # type: ignore[untyped-decorator]  # FastMCP.custom_route is untyped in mcp==1.29.0
    async def healthz(_request: Request) -> JSONResponse:
        if corpus is None:
            return JSONResponse(
                {"status": "unavailable", "db": str(db_path), "reason": "corpus not built"},
                status_code=503,
            )
        return JSONResponse({"status": "ok", "db": str(db_path)})


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pbu-fsbu-mcp")
    parser.add_argument("--transport", choices=TRANSPORTS, default="stdio")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18010)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    server = build_server(args.db, host=args.host, port=args.port)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http")
    return 0


def cli() -> None:
    sys.exit(main())
