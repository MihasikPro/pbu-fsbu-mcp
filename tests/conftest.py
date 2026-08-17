from datetime import date
from pathlib import Path

import pytest

from etl.build_db import build

SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"


@pytest.fixture(scope="session")
def corpus_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("corpus") / "pbu_fsbu.db"
    build(SOURCES, output, built_at=date(2026, 8, 14))
    return output


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
