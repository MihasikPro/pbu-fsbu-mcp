from dataclasses import replace
from datetime import date
from pathlib import Path

from etl import watch
from etl.http_client import cache_path_for
from etl.registry import REGISTRY_URL, RegistryRow, parse
from etl.watch import diff_registry
from pbu_fsbu_mcp.loader import load_all
from pbu_fsbu_mcp.models import Standard

SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"
FIXTURE = Path(__file__).parent / "fixtures" / "minfin_registry.html"


def _rows() -> list[RegistryRow]:
    return parse(FIXTURE.read_bytes(), REGISTRY_URL)


def _matching_rows(standards: list[Standard]) -> list[RegistryRow]:
    """Rows from the live fixture whose id is actually present in the local corpus.

    `data/sources/standards/` only ever holds a subset of the standards the live
    registry lists - comparing the full parsed fixture against a partial corpus
    would report the missing standards as spurious `added` entries. Filtering to
    the matching slice keeps these tests correct regardless of how many standards
    happen to be committed at any given time.
    """
    ids = {standard.id for standard in standards}
    return [row for row in _rows() if row.id in ids]


def test_matching_registry_produces_empty_diff() -> None:
    standards = load_all(SOURCES)
    assert diff_registry(_matching_rows(standards), standards).is_empty


def test_new_standard_is_reported_as_added() -> None:
    standards = load_all(SOURCES)
    rows = _matching_rows(standards)
    rows.append(
        RegistryRow(
            id="fsbu-11-2027",
            kind="ФСБУ",
            number="11/2027",
            year=2027,
            title="Новый стандарт",
            order_date=date(2027, 1, 1),
            order_no="1н",
            effective_from=date(2028, 1, 1),
            effective_to=None,
            source_url=REGISTRY_URL,
            document_url="https://minfin.gov.ru/ru/document?id_4=999999",
        )
    )
    diff = diff_registry(rows, standards)
    assert "fsbu-11-2027" in diff.added
    assert not diff.is_empty


def test_disappeared_standard_is_reported_as_removed() -> None:
    standards = load_all(SOURCES)
    missing_id = standards[0].id
    rows = [row for row in _matching_rows(standards) if row.id != missing_id]
    assert missing_id in diff_registry(rows, standards).removed


def test_changed_order_number_is_reported() -> None:
    standards = load_all(SOURCES)
    rows = _matching_rows(standards)
    changed_id = rows[0].id
    rows[0] = replace(rows[0], order_no="999н")
    diff = diff_registry(rows, standards)
    assert any(changed_id in item for item in diff.changed)


def test_changed_expiry_is_reported() -> None:
    standards = load_all(SOURCES)
    rows = _matching_rows(standards)
    changed_id = rows[0].id
    rows[0] = replace(rows[0], effective_to=date(2030, 1, 1))
    diff = diff_registry(rows, standards)
    assert any(changed_id in item for item in diff.changed)


def _seeded_cache(tmp_path: Path) -> Path:
    """A cache directory holding the committed registry fixture as `REGISTRY_URL`."""
    cache = tmp_path / "cache"
    cache.mkdir()
    cache_path_for(REGISTRY_URL, cache).write_bytes(FIXTURE.read_bytes())
    return cache


def test_matching_registry_exits_in_sync(tmp_path: Path) -> None:
    code = watch.main(
        ["--cache", str(_seeded_cache(tmp_path)), "--report", str(tmp_path / "diff.md")]
    )
    assert code == watch.EXIT_IN_SYNC


def test_drift_exits_with_its_own_code(tmp_path: Path) -> None:
    sources = tmp_path / "standards"
    sources.mkdir()
    for path in sorted(SOURCES.glob("*.yaml"))[1:]:
        (sources / path.name).write_bytes(path.read_bytes())

    code = watch.main(
        [
            "--cache",
            str(_seeded_cache(tmp_path)),
            "--sources",
            str(sources),
            "--report",
            str(tmp_path / "diff.md"),
        ]
    )
    assert code == watch.EXIT_DRIFT


def test_unreachable_registry_exits_with_its_own_code(tmp_path: Path) -> None:
    """A source that cannot be fetched is not a drift.

    The workflow opens a pull request on EXIT_DRIFT; conflating the two made a
    503 from minfin.gov.ru look like a new order from the ministry.
    """
    report = tmp_path / "diff.md"
    code = watch.main(["--cache", str(tmp_path / "empty-cache"), "--report", str(report)])

    assert code == watch.EXIT_UNREACHABLE
    assert not report.exists(), "Недоступный источник не должен оставлять отчёт для PR"
