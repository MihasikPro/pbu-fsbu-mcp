from pathlib import Path

from etl.clause_parser import parse_clauses
from etl.minfin_document import extract_clauses_html, find_standalone_pdf_url, looks_complete

FIXTURE_FSBU_6_2020 = Path(__file__).parent / "fixtures" / "minfin_document_fsbu_6_2020.html"
FIXTURE_PBU_1_2008 = Path(__file__).parent / "fixtures" / "minfin_document_pbu_1_2008.html"
FIXTURE_PBU_10_99 = Path(__file__).parent / "fixtures" / "minfin_document_pbu_10_99.html"
FIXTURE_FSBU_27_2021 = Path(__file__).parent / "fixtures" / "pages" / "fsbu-27-2021.html"
FIXTURE_PBU_8_2010 = Path(__file__).parent / "fixtures" / "pages" / "pbu-8-2010.html"


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
    lettered = {
        clause.path
        for clause in clauses
        if clause.parent_path is not None and "заключение" not in clause.path
    }
    conclusions = {clause.path for clause in clauses if "заключение" in clause.path}
    # Hand-verified against data/sources/standards/fsbu-6-2020.yaml: 52
    # numbered clauses, 50 lettered subclauses, 2 trailing-paragraph
    # conclusions (13.заключение, 20.заключение).
    assert len(top_level) == 52
    assert len(lettered) == 50
    assert len(conclusions) == 2
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


# `minfin_document_pbu_10_99.html` is a byte-for-byte copy of
# https://minfin.gov.ru/ru/document?id_4=2269 - its `text_wrapper` renders the
# entire standard twice, back to back, with no container marking the second
# copy off from the first (see the `extract_clauses_html` module docstring).


def test_pbu_10_99_renders_the_document_exactly_once() -> None:
    # A sentence from clause 1, distinctive enough that it could only appear
    # here (and not, say, as part of a cross-reference elsewhere on the
    # page) - present twice in the raw page, must survive extraction once.
    text = extract_clauses_html(FIXTURE_PBU_10_99.read_bytes())
    sentence = (
        "Настоящее Положение устанавливает правила формирования в "
        "бухгалтерском учете информации о расходах коммерческих организаций"
    )
    assert text.count(sentence) == 1


def test_pbu_10_99_yields_the_hand_verified_clause_count() -> None:
    text = extract_clauses_html(FIXTURE_PBU_10_99.read_bytes())
    clauses = parse_clauses(text)
    top_level = {clause.path for clause in clauses if clause.parent_path is None}
    lettered = {clause.path for clause in clauses if clause.parent_path is not None}
    # Hand-verified against the standard's own numbering: clauses 1..23
    # (clause 12 repealed, so 22 primary clauses) plus 12 decimal insertions
    # ("6.1".."6.6", "14.1".."14.4", "21.1", "21.2") added by later amending
    # orders - 34 numbered clauses total, no lettered (а/б/...) subclauses.
    assert len(top_level) == 34
    assert len(lettered) == 0
    assert looks_complete(text)


def test_pbu_10_99_has_no_duplicate_clause_paths() -> None:
    text = extract_clauses_html(FIXTURE_PBU_10_99.read_bytes())
    paths = [clause.path for clause in parse_clauses(text)]
    assert len(paths) == len(set(paths))


# --- find_standalone_pdf_url: small, handcrafted markup ---------------------


def test_find_standalone_pdf_url_resolves_a_relative_pdf_link() -> None:
    html = (
        "<div class='text_wrapper'></div>"
        '<a href="/common/upload/library/2021/06/main/fsbu_27-2021.pdf">Скачать</a>'
    ).encode()
    assert (
        find_standalone_pdf_url(html)
        == "https://minfin.gov.ru/common/upload/library/2021/06/main/fsbu_27-2021.pdf"
    )


def test_find_standalone_pdf_url_returns_none_without_a_pdf_link() -> None:
    html = "<div class='text_wrapper'><p>1. Текст.</p></div>".encode()
    assert find_standalone_pdf_url(html) is None


def test_find_standalone_pdf_url_matches_a_pdf_link_with_a_query_string() -> None:
    html = '<a href="/common/upload/library/main/std.pdf?v=2">Скачать</a>'.encode()
    assert (
        find_standalone_pdf_url(html)
        == "https://minfin.gov.ru/common/upload/library/main/std.pdf?v=2"
    )


# --- Real ФСБУ 27/2021 page (committed fixture) ------------------------------
# `pages/fsbu-27-2021.html` is a byte-for-byte copy of
# https://minfin.gov.ru/ru/document?id_4=133493 - its `text_wrapper` is
# present but empty (see module docstring); the page embeds the standard
# only via a PDF viewer `<iframe>`, alongside a plain download link to the
# same PDF that `find_standalone_pdf_url` resolves.


def test_fsbu_27_2021_page_has_no_usable_text() -> None:
    text = extract_clauses_html(FIXTURE_FSBU_27_2021.read_bytes())
    assert not looks_complete(text)


def test_fsbu_27_2021_page_links_its_own_pdf_attachment() -> None:
    url = find_standalone_pdf_url(FIXTURE_FSBU_27_2021.read_bytes())
    assert url == "https://minfin.gov.ru/common/upload/library/2021/06/main/fsbu_27-2021.pdf"


# --- Nested appendix without a "№" (handcrafted markup) ---------------------


def test_drops_a_nested_appendix_numbered_without_a_hash_sign() -> None:
    # ПБУ 8/2010's own page spells its appendix caption "Приложение 1 к
    # Положению ..." - no "№" before the number, unlike every other nested
    # appendix caption seen so far.
    html = (
        "<div class='text_wrapper'>"
        "<p>28. Текст последнего пункта Положения.</p>"
        "<p>Приложение 1 к Положению по бухгалтерскому учету «Стандарт» "
        "(ПБУ 8/2010) ПРИМЕРЫ.</p>"
        "<p>Пример 1. Текст примера.</p>"
        "</div>"
    ).encode()
    assert extract_clauses_html(html) == "28. Текст последнего пункта Положения."


# --- Real ПБУ 8/2010 page (committed fixture) --------------------------------
# `pages/pbu-8-2010.html` is a byte-for-byte copy of
# https://minfin.gov.ru/ru/document?id_4=11979 - its п.28 is immediately
# followed by "Приложение 1 к Положению ..." (12 074 of its 12 628 chars
# were the appendix, glued in verbatim before this fix).


def test_pbu_8_2010_clause_28_does_not_swallow_its_appendix() -> None:
    text = extract_clauses_html(FIXTURE_PBU_8_2010.read_bytes())
    clauses = {clause.path: clause for clause in parse_clauses(text)}
    assert "Приложение" not in clauses["28"].text
    assert len(clauses["28"].text) < 1000
