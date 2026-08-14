from pathlib import Path

from pbu_fsbu_mcp.server import build_server


def test_build_server_returns_named_instance(tmp_path: Path) -> None:
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
