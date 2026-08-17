from datetime import date
from pathlib import Path

import pytest
import yaml

from etl import draft_yaml
from etl.clause_parser import ParsedClause
from etl.draft_yaml import render
from etl.pravo import PublishedAct
from etl.registry import RegistryRow
from pbu_fsbu_mcp.loader import load_standard

ROW = RegistryRow(
    id="fsbu-6-2020",
    kind="ФСБУ",
    number="6/2020",
    year=2020,
    title="Основные средства",
    order_date=date(2020, 9, 17),
    order_no="204н",
    effective_from=date(2022, 1, 1),
    effective_to=None,
    source_url="https://minfin.gov.ru/",
)
OTHER_ROW = RegistryRow(
    id="pbu-1-2008",
    kind="ПБУ",
    number="1/2008",
    year=2008,
    title="Учетная политика организации",
    order_date=date(2008, 10, 6),
    order_no="106н",
    effective_from=date(2009, 1, 1),
    effective_to=None,
    source_url="https://minfin.gov.ru/",
)
CLAUSES = [
    ParsedClause(path="1", parent_path=None, heading="Общие положения", text="Текст первого."),
    ParsedClause(path="1.а", parent_path="1", heading=None, text="Подпункт."),
]


def test_render_produces_parsable_yaml() -> None:
    document = yaml.safe_load(render(ROW, CLAUSES))
    assert document["id"] == "fsbu-6-2020"
    assert document["order_no"] == "204н"


def test_render_creates_single_first_edition() -> None:
    document = yaml.safe_load(render(ROW, CLAUSES))
    assert len(document["editions"]) == 1
    assert document["editions"][0]["edition_no"] == 1


def test_render_preserves_clause_order_and_paths() -> None:
    document = yaml.safe_load(render(ROW, CLAUSES))
    paths = [clause["path"] for clause in document["editions"][0]["clauses"]]
    assert paths == ["1", "1.а"]


def test_rendered_draft_loads_through_production_loader(tmp_path: Path) -> None:
    path = tmp_path / "fsbu-6-2020.yaml"
    path.write_text(render(ROW, CLAUSES), encoding="utf-8")
    standard = load_standard(path)
    assert standard.editions[0].clauses[1].id == "fsbu-6-2020@1#1.а"


def test_draft_carries_review_marker() -> None:
    assert "ЧЕРНОВИК" in render(ROW, CLAUSES)


# --- _fetch_clauses: wiring between search, OCR, and the clause parser -----
# No network and no OCR: `fetch` and `extract` are stubbed at the module level.


def test_fetch_clauses_raises_when_no_published_act_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(draft_yaml, "fetch", lambda url, cache, *, live: b"{}")
    monkeypatch.setattr(draft_yaml, "parse_search", lambda payload: [])

    with pytest.raises(LookupError):
        draft_yaml._fetch_clauses(ROW, tmp_path, live=False)


def test_fetch_clauses_wires_search_result_through_ocr_and_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    act = PublishedAct(eo_number="0001202010160010", title="...", pdf_url="http://example/pdf")
    monkeypatch.setattr(draft_yaml, "fetch", lambda url, cache, *, live: b"{}")
    monkeypatch.setattr(draft_yaml, "parse_search", lambda payload: [act])
    monkeypatch.setattr(draft_yaml, "extract", lambda pdf_bytes: "1. Текст пункта.")

    clauses = draft_yaml._fetch_clauses(ROW, tmp_path, live=False)

    assert [clause.path for clause in clauses] == ["1"]
    assert clauses[0].text == "Текст пункта."


# --- main(): orchestration, stubbed end to end -----------------------------
# No network and no OCR: `fetch`, `parse` (registry) and `_fetch_clauses` are
# stubbed so these tests exercise only main()'s own logic - filtering,
# per-standard failure isolation, file output, and the exit code.


def _stub_registry(monkeypatch: pytest.MonkeyPatch, rows: list[RegistryRow]) -> None:
    monkeypatch.setattr(draft_yaml, "fetch", lambda url, cache, *, live: b"")
    monkeypatch.setattr(draft_yaml, "parse", lambda html, source_url: rows)


def test_main_only_filters_to_a_single_standard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_registry(monkeypatch, [ROW, OTHER_ROW])
    monkeypatch.setattr(draft_yaml, "_fetch_clauses", lambda row, cache, *, live: CLAUSES)
    out = tmp_path / "drafts"

    exit_code = draft_yaml.main(
        ["--cache", str(tmp_path / "cache"), "--out", str(out), "--only", ROW.id]
    )

    assert exit_code == 0
    assert (out / f"{ROW.id}.yaml").exists()
    assert not (out / f"{OTHER_ROW.id}.yaml").exists()


def test_main_reports_unknown_only_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_registry(monkeypatch, [ROW])

    exit_code = draft_yaml.main(
        [
            "--cache",
            str(tmp_path / "cache"),
            "--out",
            str(tmp_path / "drafts"),
            "--only",
            "does-not-exist",
        ]
    )

    assert exit_code == 1


def test_main_continues_after_one_standard_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_registry(monkeypatch, [ROW, OTHER_ROW])

    def fake_fetch_clauses(
        row: RegistryRow, cache_dir: Path, *, live: bool
    ) -> list[ParsedClause]:
        if row.id == ROW.id:
            raise LookupError("акт не найден")
        return CLAUSES

    monkeypatch.setattr(draft_yaml, "_fetch_clauses", fake_fetch_clauses)
    out = tmp_path / "drafts"

    exit_code = draft_yaml.main(["--cache", str(tmp_path / "cache"), "--out", str(out)])

    assert exit_code == 1
    assert not (out / f"{ROW.id}.yaml").exists()
    assert (out / f"{OTHER_ROW.id}.yaml").exists()


def test_main_writes_a_draft_that_round_trips_through_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_registry(monkeypatch, [ROW])
    monkeypatch.setattr(draft_yaml, "_fetch_clauses", lambda row, cache, *, live: CLAUSES)
    out = tmp_path / "drafts"

    draft_yaml.main(["--cache", str(tmp_path / "cache"), "--out", str(out)])

    assert (out / f"{ROW.id}.yaml").read_text(encoding="utf-8") == render(ROW, CLAUSES)


def test_main_threads_the_live_flag_into_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_live: list[bool] = []

    def fake_fetch(url: str, cache_dir: Path, *, live: bool) -> bytes:
        captured_live.append(live)
        return b""

    monkeypatch.setattr(draft_yaml, "fetch", fake_fetch)
    monkeypatch.setattr(draft_yaml, "parse", lambda html, source_url: [])
    args = ["--cache", str(tmp_path / "cache"), "--out", str(tmp_path / "drafts")]

    draft_yaml.main(args)
    draft_yaml.main([*args, "--live"])

    assert captured_live == [False, True]
