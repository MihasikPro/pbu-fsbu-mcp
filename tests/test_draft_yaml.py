from datetime import date
from pathlib import Path

import pytest
import yaml

from etl import draft_yaml
from etl.clause_parser import ParsedClause, parse_clauses, slice_appendix
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
    document_url="https://minfin.gov.ru/ru/document?id_4=133537",
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
    document_url="https://minfin.gov.ru/ru/document?id_4=2260",
)
CLAUSES = [
    ParsedClause(path="1", parent_path=None, heading="Общие положения", text="Текст первого."),
    ParsedClause(path="1.а", parent_path="1", heading=None, text="Подпункт."),
]


def test_render_produces_parsable_yaml() -> None:
    document = yaml.safe_load(render(ROW, CLAUSES, source="ocr"))
    assert document["id"] == "fsbu-6-2020"
    assert document["order_no"] == "204н"


def test_render_creates_single_first_edition() -> None:
    document = yaml.safe_load(render(ROW, CLAUSES, source="ocr"))
    assert len(document["editions"]) == 1
    assert document["editions"][0]["edition_no"] == 1


def test_render_preserves_clause_order_and_paths() -> None:
    document = yaml.safe_load(render(ROW, CLAUSES, source="ocr"))
    paths = [clause["path"] for clause in document["editions"][0]["clauses"]]
    assert paths == ["1", "1.а"]


def test_rendered_draft_loads_through_production_loader(tmp_path: Path) -> None:
    path = tmp_path / "fsbu-6-2020.yaml"
    path.write_text(render(ROW, CLAUSES, source="ocr"), encoding="utf-8")
    standard = load_standard(path)
    assert standard.editions[0].clauses[1].id == "fsbu-6-2020@1#1.а"


def test_draft_carries_review_marker() -> None:
    assert "ЧЕРНОВИК" in render(ROW, CLAUSES, source="ocr")


def test_draft_banner_names_the_html_source() -> None:
    assert "HTML" in render(ROW, CLAUSES, source="html")


def test_draft_banner_names_the_ocr_source() -> None:
    assert "OCR" in render(ROW, CLAUSES, source="ocr")


# --- _fetch_clauses_ocr: wiring between search, OCR, and the clause parser -
# No network and no OCR: `fetch` and `extract` are stubbed at the module level.


def test_fetch_clauses_ocr_raises_when_no_published_act_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(draft_yaml, "fetch", lambda url, cache, *, live: b"{}")
    monkeypatch.setattr(draft_yaml, "parse_search", lambda payload: [])

    with pytest.raises(LookupError):
        draft_yaml._fetch_clauses_ocr(ROW, tmp_path, live=False)


def test_fetch_clauses_ocr_wires_search_result_through_ocr_and_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    act = PublishedAct(eo_number="0001202010160010", title="...", pdf_url="http://example/pdf")
    monkeypatch.setattr(draft_yaml, "fetch", lambda url, cache, *, live: b"{}")
    monkeypatch.setattr(draft_yaml, "parse_search", lambda payload: [act])
    monkeypatch.setattr(draft_yaml, "extract", lambda pdf_bytes: "1. Текст пункта.")

    clauses = draft_yaml._fetch_clauses_ocr(ROW, tmp_path, live=False)

    assert [clause.path for clause in clauses] == ["1"]
    assert clauses[0].text == "Текст пункта."


def test_fetch_clauses_ocr_slices_the_order_to_the_requested_standard_before_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order_text = (
        "ФЕДЕРАЛЬНЫЙ СТАНДАРТ БУХГАЛТЕРСКОГО УЧЕТА\nФСБУ 6/2020 «Основные средства»\n\n"
        "1. Текст первого стандарта.\n\n"
        "ФЕДЕРАЛЬНЫЙ СТАНДАРТ БУХГАЛТЕРСКОГО УЧЕТА\nФСБУ 26/2020 «Капитальные вложения»\n\n"
        "1. Текст второго стандарта.\n"
    )
    act = PublishedAct(eo_number="0001202010160010", title="...", pdf_url="http://example/pdf")
    monkeypatch.setattr(draft_yaml, "fetch", lambda url, cache, *, live: b"{}")
    monkeypatch.setattr(draft_yaml, "parse_search", lambda payload: [act])
    monkeypatch.setattr(draft_yaml, "extract", lambda pdf_bytes: order_text)

    clauses = draft_yaml._fetch_clauses_ocr(ROW, tmp_path, live=False)

    assert [clause.text for clause in clauses] == ["Текст первого стандарта."]


# --- _fetch_clauses_html: the Minfin HTML document-page path ---------------
# No network: `fetch` is stubbed to return a small HTML page in the exact
# shape `etl.minfin_document.extract_clauses_html` expects.


def _html_page(clause_count: int) -> bytes:
    paragraphs = "".join(f"<p>{n}. Текст пункта {n}.</p>" for n in range(1, clause_count + 1))
    return f"<div class='text_wrapper'>{paragraphs}</div>".encode()


def test_fetch_clauses_html_parses_the_document_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(draft_yaml, "fetch", lambda url, cache, *, live: _html_page(5))

    clauses = draft_yaml._fetch_clauses_html(ROW, tmp_path, live=False)

    assert clauses is not None
    assert [clause.path for clause in clauses] == ["1", "2", "3", "4", "5"]


def test_fetch_clauses_html_returns_none_when_the_page_is_too_thin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(draft_yaml, "fetch", lambda url, cache, *, live: b"<html></html>")

    assert draft_yaml._fetch_clauses_html(ROW, tmp_path, live=False) is None


# --- _fetch_clauses: HTML-first orchestration, OCR only as a fallback ------


def test_fetch_clauses_prefers_html_and_never_calls_ocr_when_it_is_enough(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ocr_calls: list[str] = []
    monkeypatch.setattr(draft_yaml, "fetch", lambda url, cache, *, live: _html_page(5))
    monkeypatch.setattr(
        draft_yaml,
        "_fetch_clauses_ocr",
        lambda row, cache, *, live: ocr_calls.append(row.id) or CLAUSES,
    )

    clauses, source = draft_yaml._fetch_clauses(ROW, tmp_path, live=False)

    assert source == draft_yaml.SOURCE_HTML
    assert len(clauses) == 5
    assert ocr_calls == []


def test_fetch_clauses_falls_back_to_ocr_when_the_html_page_is_too_thin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(draft_yaml, "fetch", lambda url, cache, *, live: b"<html></html>")
    monkeypatch.setattr(draft_yaml, "_fetch_clauses_ocr", lambda row, cache, *, live: CLAUSES)

    clauses, source = draft_yaml._fetch_clauses(ROW, tmp_path, live=False)

    assert source == draft_yaml.SOURCE_OCR
    assert clauses == CLAUSES


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
    monkeypatch.setattr(
        draft_yaml, "_fetch_clauses", lambda row, cache, *, live: (CLAUSES, "html")
    )
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
    ) -> tuple[list[ParsedClause], str]:
        if row.id == ROW.id:
            raise LookupError("акт не найден")
        return CLAUSES, "html"

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
    monkeypatch.setattr(
        draft_yaml, "_fetch_clauses", lambda row, cache, *, live: (CLAUSES, "html")
    )
    out = tmp_path / "drafts"

    draft_yaml.main(["--cache", str(tmp_path / "cache"), "--out", str(out)])

    assert (out / f"{ROW.id}.yaml").read_text(encoding="utf-8") == render(
        ROW, CLAUSES, source="html"
    )


# --- End-to-end: appendix slicing regenerates a clean fsbu-6-2020 draft ----
# Committed OCR fixture (tests/fixtures/prikaz_204n_ocr.txt, see
# test_clause_parser.py for the full rationale); `requires_real_ocr_fixture`
# is a defensive skip, not a hard dependency - see its own comment there.
# No network call and no OCR call - the fixture is already-recognised text.

_REPO_ROOT = Path(__file__).parent.parent
_OCR_FIXTURE = Path(__file__).parent / "fixtures" / "prikaz_204n_ocr.txt"
_GOLD_FSBU_6_2020 = _REPO_ROOT / "data" / "sources" / "standards" / "fsbu-6-2020.yaml"

requires_real_ocr_fixture = pytest.mark.skipif(
    not _OCR_FIXTURE.exists(),
    reason="real OCR fixture (tests/fixtures/prikaz_204n_ocr.txt) is missing",
)


@requires_real_ocr_fixture
def test_regenerated_fsbu_6_2020_draft_has_no_duplicates_and_matches_gold_clause_count() -> None:
    order_text = _OCR_FIXTURE.read_text(encoding="utf-8")
    clauses = parse_clauses(slice_appendix(order_text, ROW.number))
    document = yaml.safe_load(render(ROW, clauses, source="ocr"))
    paths = [clause["path"] for clause in document["editions"][0]["clauses"]]

    gold = yaml.safe_load(_GOLD_FSBU_6_2020.read_text(encoding="utf-8"))
    gold_paths = {clause["path"] for clause in gold["editions"][0]["clauses"]}

    assert len(paths) == len(set(paths)), "duplicate clause paths in the regenerated draft"
    # Including the two ".заключение" splits (13.заключение, 20.заключение):
    # the parser now derives them structurally rather than relying on a
    # manual editorial fix (see test_clause_parser.py).
    assert set(paths) == gold_paths


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
