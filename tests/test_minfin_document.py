from pathlib import Path

from etl.clause_parser import parse_clauses
from etl.minfin_document import extract_clauses_html, looks_complete

FIXTURE_FSBU_6_2020 = Path(__file__).parent / "fixtures" / "minfin_document_fsbu_6_2020.html"
FIXTURE_PBU_1_2008 = Path(__file__).parent / "fixtures" / "minfin_document_pbu_1_2008.html"


# --- extract_clauses_html: small, handcrafted markup -----------------------


def test_extracts_one_paragraph_per_p_tag() -> None:
    html = "<div class='text_wrapper'><p>1. Первый.</p><p>2. Второй.</p></div>".encode()
    assert extract_clauses_html(html) == "1. Первый.\n\n2. Второй."


def test_output_is_ready_for_parse_clauses() -> None:
    html = "<div class='text_wrapper'><p>1. Первый.</p><p>2. Второй.</p></div>".encode()
    clauses = parse_clauses(extract_clauses_html(html))
    assert [clause.path for clause in clauses] == ["1", "2"]


def test_drops_scripts_and_styles() -> None:
    html = (
        "<html><head><style>.x{color:red}</style></head><body>"
        "<div class='text_wrapper'><p>1. Текст.</p><script>evil()</script></div>"
        "</body></html>"
    ).encode()
    text = extract_clauses_html(html)
    assert "evil" not in text
    assert "color:red" not in text
    assert text == "1. Текст."


def test_ignores_content_outside_the_wrapper() -> None:
    html = (
        "<div class='site_header'><p>Главная</p></div>"
        "<div class='text_wrapper'><p>1. Текст пункта.</p></div>"
        "<div class='site_footer'><p>Контакты</p></div>"
    ).encode()
    assert extract_clauses_html(html) == "1. Текст пункта."


def test_returns_empty_string_when_the_wrapper_is_absent() -> None:
    html = "<html><body><p>Кто-то переделал страницу</p></body></html>".encode()
    assert extract_clauses_html(html) == ""


def test_drops_empty_paragraphs() -> None:
    html = "<div class='text_wrapper'><p>1. Текст.</p><p>&nbsp;</p><p>2. Текст.</p></div>".encode()
    assert extract_clauses_html(html) == "1. Текст.\n\n2. Текст."


def test_collapses_non_breaking_spaces_and_repeated_whitespace() -> None:
    html = "<div class='text_wrapper'><p>1.\xa0Текст   с\xa0пробелами.</p></div>".encode()
    assert extract_clauses_html(html) == "1. Текст с пробелами."


def test_replaces_line_breaks_with_a_space_instead_of_gluing_words() -> None:
    html = "<div class='text_wrapper'><p>1. Первая часть.<br/>Вторая часть.</p></div>".encode()
    assert extract_clauses_html(html) == "1. Первая часть. Вторая часть."


# --- looks_complete ---------------------------------------------------------


def test_looks_complete_is_false_for_too_few_clauses() -> None:
    assert not looks_complete("1. Один пункт.\n\n2. Другой пункт.", expected_min_clauses=5)


def test_looks_complete_is_true_once_the_threshold_is_met() -> None:
    text = "\n\n".join(f"{n}. Текст пункта {n}." for n in range(1, 6))
    assert looks_complete(text, expected_min_clauses=5)


def test_looks_complete_is_false_for_empty_text() -> None:
    assert not looks_complete("")


# --- Real Minfin document pages (committed fixtures) ------------------------
# `minfin_document_fsbu_6_2020.html` and `minfin_document_pbu_1_2008.html` are
# byte-for-byte copies of https://minfin.gov.ru/ru/document?id_4=133537 and
# ?id_4=2260, fetched once and committed so the extractor is tested against
# real markup with no network access at test time.


def test_fsbu_6_2020_yields_the_hand_verified_clause_count() -> None:
    text = extract_clauses_html(FIXTURE_FSBU_6_2020.read_bytes())
    clauses = parse_clauses(text)
    top_level = {clause.path for clause in clauses if clause.parent_path is None}
    lettered = {clause.path for clause in clauses if clause.parent_path is not None}
    # Hand-verified against data/sources/standards/fsbu-6-2020.yaml: 52
    # numbered clauses, 50 lettered subclauses.
    assert len(top_level) == 52
    assert len(lettered) == 50
    assert looks_complete(text)


def test_fsbu_6_2020_has_no_duplicate_clause_paths() -> None:
    text = extract_clauses_html(FIXTURE_FSBU_6_2020.read_bytes())
    paths = [clause.path for clause in parse_clauses(text)]
    assert len(paths) == len(set(paths))


def test_pbu_1_2008_yields_the_expected_primary_clause_count() -> None:
    # ПБУ 1/2008 predates publication.pravo.gov.ru's archive (OCR was never
    # an option for it) and has been amended many times, so its numbering
    # includes clauses inserted later as "5.1", "7.3" etc alongside the 25
    # primary numbered clauses (1..25).
    text = extract_clauses_html(FIXTURE_PBU_1_2008.read_bytes())
    clauses = parse_clauses(text)
    top_level = {clause.path for clause in clauses if clause.parent_path is None}
    primary = {path for path in top_level if "." not in path}
    assert primary == {str(n) for n in range(1, 26)}
    assert looks_complete(text)


def test_pbu_1_2008_has_no_duplicate_clause_paths() -> None:
    text = extract_clauses_html(FIXTURE_PBU_1_2008.read_bytes())
    paths = [clause.path for clause in parse_clauses(text)]
    assert len(paths) == len(set(paths))
