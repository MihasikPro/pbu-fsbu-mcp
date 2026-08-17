"""MCP server entry point: builds the server and selects a transport."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "build" / "pbu_fsbu.db"
TRANSPORTS = ("stdio", "http")


def build_server(db_path: Path, host: str = "0.0.0.0", port: int = 18010) -> FastMCP:
    """Create the FastMCP instance with tools registered against `db_path`."""
    server = FastMCP("pbu-fsbu", host=host, port=port)
    server.settings.dependencies = []
    _register_health_route(server, db_path)
    return server


def _register_health_route(server: FastMCP, db_path: Path) -> None:
    @server.custom_route("/healthz", methods=["GET"])  # type: ignore[untyped-decorator]  # FastMCP.custom_route is untyped in mcp==1.29.0
    async def healthz(_request: Request) -> JSONResponse:
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
