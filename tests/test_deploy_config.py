"""Structural checks on the container config, not a Docker build.

No Docker is available in the environment these were written and reviewed
in - these tests catch accidental regressions to the text of Dockerfile /
deploy/compose.local.yml, not runtime behaviour. See README.md for the
"never actually built" caveat.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_DOCKERFILE = (_ROOT / "Dockerfile").read_text(encoding="utf-8")
_COMPOSE = (_ROOT / "deploy" / "compose.local.yml").read_text(encoding="utf-8")


def test_build_stage_pins_uv_to_the_build_images_own_python() -> None:
    """Without this, uv could resolve a Python interpreter for the venv that
    does not exist in the (different) runtime image the venv is copied into."""
    assert "UV_PYTHON_DOWNLOADS=never" in _DOCKERFILE
    assert "UV_PYTHON_PREFERENCE=only-system" in _DOCKERFILE


def test_sync_is_no_editable() -> None:
    """An editable install's venv points back at /app/src by path - the
    runtime stage must not depend on that path still existing."""
    assert "--no-editable" in _DOCKERFILE


def test_healthcheck_hits_healthz() -> None:
    """Without a HEALTHCHECK, a container whose corpus failed to build stays
    up looking healthy while build_server registers zero tools."""
    assert "HEALTHCHECK" in _DOCKERFILE
    assert "/healthz" in _DOCKERFILE


def test_compose_mounts_tmpfs_alongside_read_only_root() -> None:
    compose = yaml.safe_load(_COMPOSE)
    service = compose["services"]["pbu-fsbu-mcp"]
    assert service["read_only"] is True
    assert "/tmp" in service["tmpfs"]
