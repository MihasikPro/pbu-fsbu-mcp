from datetime import date
from pathlib import Path

import pytest
import yaml

from etl.build_db import build
from pbu_fsbu_mcp.db import Corpus

SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources" / "standards"
TODAY = date(2026, 8, 14)


@pytest.fixture
def corpus(corpus_db: Path) -> Corpus:
    return Corpus(corpus_db)


def _standard(standard_id: str, kind: str, number: str, year: int) -> dict:
    return {
        "id": standard_id,
        "kind": kind,
        "number": number,
        "year": year,
        "title": f"Тестовый стандарт {standard_id}",
        "order_date": "2020-01-01",
        "order_no": "1н",
        "effective_from": "2020-01-01",
        "source_url": f"https://example.org/{standard_id}",
    }


@pytest.fixture
def two_standard_corpus(tmp_path: Path) -> Corpus:
    """A purpose-built corpus with two standards linked by a crosslink.

    Deliberately independent of whichever standards the ongoing Task 7 has
    populated in `data/sources/standards` so far - these tests must pass
    whether the real corpus holds one standard or all 29.
    """
    sources_dir = tmp_path / "sources"
    standards_dir = sources_dir / "standards"
    standards_dir.mkdir(parents=True)

    (standards_dir / "old.yaml").write_text(
        yaml.safe_dump(_standard("old-standard", "ПБУ", "9/99", 1999)),
        encoding="utf-8",
    )
    (standards_dir / "new.yaml").write_text(
        yaml.safe_dump(_standard("new-standard", "ФСБУ", "9/2025", 2025)),
        encoding="utf-8",
    )
    (sources_dir / "crosslinks.yaml").write_text(
        yaml.safe_dump(
            [{"from_standard": "old-standard", "to_standard": "new-standard", "kind": "заменён"}]
        ),
        encoding="utf-8",
    )

    output = tmp_path / "corpus.db"
    build(standards_dir, output, built_at=TODAY)
    return Corpus(output)


def test_repealed_standard_reports_successor(two_standard_corpus: Corpus) -> None:
    assert "new-standard" in two_standard_corpus.successors("old-standard")


def test_get_standard_exposes_successors(two_standard_corpus: Corpus) -> None:
    summary = two_standard_corpus.get_standard("old-standard", TODAY)
    assert summary.successors == ["new-standard"]


def test_active_standard_has_no_successor(corpus: Corpus) -> None:
    assert corpus.successors("fsbu-6-2020") == []


def test_unknown_standard_returns_empty_list(corpus: Corpus) -> None:
    assert corpus.successors("fsbu-999-1999") == []


def test_crosslink_to_absent_standard_is_skipped(corpus: Corpus) -> None:
    """ПБУ 17/02 отсутствует в реестре; связь на него не должна ломать сборку.

    Uses the real `data/sources/crosslinks.yaml` against the real (partially
    populated) corpus: none of its standards are guaranteed present yet, so
    every link involving them must be silently skipped rather than crash.
    """
    assert corpus.successors("pbu-17-02") == []


def test_build_skips_crosslinks_to_absent_standards_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Of the three real crosslinks, pbu-9-99 -> fsbu-9-2025 and pbu-10-99 -> fsbu-10-2026
    now resolve because both standards in each pair are present in the corpus. Only
    pbu-17-02 -> fsbu-14-2022 is still skipped: ПБУ 17/02 is not in the registry."""
    output = tmp_path / "corpus.db"
    build(SOURCES, output, built_at=TODAY)
    captured = capsys.readouterr()
    assert "pbu-17-02" in captured.out
    assert "fsbu-14-2022" in captured.out
    assert "пропущена" in captured.out
    assert "pbu-9-99" not in captured.out
    assert "pbu-10-99" not in captured.out
