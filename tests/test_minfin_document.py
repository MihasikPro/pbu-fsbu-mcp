from pathlib import Path

from etl.clause_parser import parse_clauses
from etl.minfin_document import extract_clauses_html, find_standalone_pdf_url, looks_complete

FIXTURE_FSBU_6_2020 = Path(__file__).parent / "fixtures" / "minfin_document_fsbu_6_2020.html"
FIXTURE_PBU_1_2008 = Path(__file__).parent / "fixtures" / "minfin_document_pbu_1_2008.html"
FIXTURE_PBU_10_99 = Path(__file__).parent / "fixtures" / "minfin_document_pbu_10_99.html"
FIXTURE_FSBU_27_2021 = Path(__file__).parent / "fixtures" / "pages" / "fsbu-27-2021.html"
FIXTURE_PBU_8_2010 = Path(__file__).parent / "fixtures" / "pages" / "pbu-8-2010.html"
FIXTURE_FSBU_28_2023 = Path(__file__).parent / "fixtures" / "pages" / "fsbu-28-2023.html"
FIXTURE_PBU_3_2006 = Path(__file__).parent / "fixtures" / "pages" / "pbu-3-2006.html"
FIXTURE_PBU_20_03 = Path(__file__).parent / "fixtures" / "pages" / "pbu-20-03.html"
FIXTURE_FSBU_4_2023 = Path(__file__).parent / "fixtures" / "pages" / "fsbu-4-2023.html"
FIXTURE_FSBU_26_2020 = Path(__file__).parent / "fixtures" / "pages" / "fsbu-26-2020.html"


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


# --- Trailing footnote apparatus (handcrafted markup) ------------------------


def test_drops_a_trailing_run_of_footnote_definitions() -> None:
    html = (
        "<div class='text_wrapper'>"
        "<p>1. Текст пункта.</p>"
        "<p>2. Последний пункт стандарта.</p>"
        "<p>[1] С изменениями, внесенными приказом от 01.01.2020 № 1н.</p>"
        "<p>[2] С изменениями, внесенными приказом от 02.02.2021 № 2н.</p>"
        "</div>"
    ).encode()
    text = extract_clauses_html(html)
    assert text == "1. Текст пункта.\n\n2. Последний пункт стандарта."


def test_a_wholly_footnote_document_yields_no_extra_clause() -> None:
    # fsbu-28-2023 п.35.заключение: every trailing paragraph was a footnote
    # definition, so nothing real is left once they are dropped - there must
    # be no clause left standing in their place.
    html = (
        "<div class='text_wrapper'>"
        "<p>1. Единственный настоящий пункт.</p>"
        "<p>[1] Сноска первая.</p>"
        "<p>[2] Сноска вторая.</p>"
        "</div>"
    ).encode()
    clauses = parse_clauses(extract_clauses_html(html))
    assert [clause.path for clause in clauses] == ["1"]


def test_strips_an_inline_footnote_reference_mark() -> None:
    # An inline reference mark ("...требования[1] в соответствии...") never
    # opens its own paragraph, unlike a footnote *definition*, so it is not
    # caught by the trailing-definitions drop - but once the definition
    # itself is gone (see the fixtures below), the mark would point at
    # nothing the corpus still carries, so it is stripped too instead of
    # being left dangling.
    html = "<div class='text_wrapper'><p>1. Текст со ссылкой[1] на сноску.</p></div>".encode()
    assert extract_clauses_html(html) == "1. Текст со ссылкой на сноску."


def test_strips_an_inline_footnote_reference_mark_preceded_by_a_space() -> None:
    html = "<div class='text_wrapper'><p>1. Текст со ссылкой [1], продолжение.</p></div>".encode()
    assert extract_clauses_html(html) == "1. Текст со ссылкой, продолжение."


# --- Real ФСБУ 28/2023 page (committed fixture) ------------------------------
# `pages/fsbu-28-2023.html` is a byte-for-byte copy of the standard's own
# Minfin page - п.35.заключение was entirely footnote text (a wholly
# fabricated clause) before this fix.


def test_fsbu_28_2023_no_longer_has_a_wholly_footnote_clause() -> None:
    text = extract_clauses_html(FIXTURE_FSBU_28_2023.read_bytes())
    paths = {clause.path for clause in parse_clauses(text)}
    assert "35.заключение" not in paths


# --- Markup-driven heading detection (handcrafted markup) -------------------


def test_bold_paragraph_becomes_a_heading_for_the_next_clause() -> None:
    html = (
        "<div class='text_wrapper'>"
        "<p>1. Первый пункт.</p>"
        "<p><strong>II. Оценка</strong></p>"
        "<p>2. Второй пункт.</p>"
        "</div>"
    ).encode()
    clause = next(c for c in parse_clauses(extract_clauses_html(html)) if c.path == "2")
    assert clause.heading == "Оценка"


def test_centred_unnumbered_paragraph_becomes_a_heading() -> None:
    html = (
        "<div class='text_wrapper'>"
        "<p>1. Первый пункт.</p>"
        '<p align="center"><strong>Бухгалтерский баланс</strong></p>'
        "<p>2. Второй пункт.</p>"
        "</div>"
    ).encode()
    clause = next(c for c in parse_clauses(extract_clauses_html(html)) if c.path == "2")
    assert clause.heading == "Бухгалтерский баланс"


def test_heading_split_across_two_strong_runs_is_still_recognised() -> None:
    # Minfin sometimes renders a heading's numeral and its text as two
    # adjacent <strong> tags ("<strong>V</strong><strong>. Раскрытие
    # информации</strong>"); get_text(" ", ...) then inserts a space between
    # them ("V . Раскрытие информации") that must not defeat recognition.
    html = (
        "<div class='text_wrapper'>"
        "<p>1. Первый пункт.</p>"
        "<p><strong>V</strong><strong>. Раскрытие информации</strong></p>"
        "<p>2. Второй пункт.</p>"
        "</div>"
    ).encode()
    clause = next(c for c in parse_clauses(extract_clauses_html(html)) if c.path == "2")
    assert clause.heading == "Раскрытие информации"


def test_partly_bold_paragraph_is_not_a_heading() -> None:
    # Only a paragraph with *nothing* outside the bold tag counts - a
    # single emphasised word inside an ordinary sentence must not.
    html = (
        "<div class='text_wrapper'>"
        "<p>1. Текст с <strong>выделенным</strong> словом внутри предложения.</p>"
        "<p>2. Второй пункт.</p>"
        "</div>"
    ).encode()
    clauses = {c.path: c for c in parse_clauses(extract_clauses_html(html))}
    assert "выделенным" in clauses["1"].text
    assert clauses["2"].heading is None


def test_title_page_paragraph_before_the_first_clause_is_not_a_heading() -> None:
    html = (
        "<div class='text_wrapper'>"
        '<p align="center"><strong>ПОЛОЖЕНИЕ ПО БУХГАЛТЕРСКОМУ УЧЕТУ «СТАНДАРТ»</strong></p>'
        "<p>1. Первый пункт.</p>"
        "</div>"
    ).encode()
    clause = next(c for c in parse_clauses(extract_clauses_html(html)) if c.path == "1")
    assert clause.heading is None


def test_centred_amendment_note_is_not_a_heading_even_without_em_wrapping() -> None:
    # ПБУ 20/03 п.16: Minfin does not consistently wrap these in <em> - some
    # are plain, centre-aligned text, indistinguishable from a heading by
    # markup alone; only the content check catches them.
    html = (
        "<div class='text_wrapper'>"
        "<p>16. Текст пункта шестнадцать.</p>"
        '<p align="center">(в ред. Приказа Минфина РФ от 18.09.2006 N 116н)</p>'
        "<p>Продолжение пункта шестнадцать.</p>"
        "<p>17. Второй пункт.</p>"
        "</div>"
    ).encode()
    clauses = {c.path: c for c in parse_clauses(extract_clauses_html(html))}
    assert "Продолжение пункта шестнадцать" in clauses["16"].text
    assert clauses["17"].heading is None


def test_em_wrapped_amendment_note_is_not_a_heading() -> None:
    html = (
        "<div class='text_wrapper'>"
        "<p>1. Первый пункт.</p>"
        '<p align="center"><em>(введено приказом Минфина России от 30.05.2022 № 87н)</em></p>'
        "<p>2. Второй пункт.</p>"
        "</div>"
    ).encode()
    clause = next(c for c in parse_clauses(extract_clauses_html(html)) if c.path == "2")
    assert clause.heading is None


# --- Real pages exercising the markup-driven heading fix (committed fixtures)


def test_pbu_3_2006_heading_propagates_past_a_long_numbered_title() -> None:
    # п.3's real 11-word section title used to be rejected by the word-count
    # heuristic and glued onto п.3's own text instead.
    text = extract_clauses_html(FIXTURE_PBU_3_2006.read_bytes())
    clauses = {c.path: c for c in parse_clauses(text)}
    assert clauses["3"].text.endswith("отчетного периода.")
    assert clauses["4"].heading == (
        "Пересчет выраженной в иностранной валюте стоимости активов и обязательств в рубли"
    )


def test_fsbu_4_2023_unnumbered_subsection_headings_do_not_become_clauses() -> None:
    text = extract_clauses_html(FIXTURE_FSBU_4_2023.read_bytes())
    clauses = {c.path: c for c in parse_clauses(text)}
    assert "Бухгалтерский баланс" not in clauses
    assert clauses["8"].heading == "Бухгалтерский баланс"


def test_pbu_20_03_centred_amendment_note_does_not_overwrite_the_heading() -> None:
    text = extract_clauses_html(FIXTURE_PBU_20_03.read_bytes())
    clauses = {c.path: c for c in parse_clauses(text)}
    assert clauses["17"].heading == "Совместная деятельность"


def test_fsbu_26_2020_superscript_section_heading_applies_cleanly() -> None:
    # "II<sup>1</sup>." (a section inserted between II and III) reglues to
    # "II1." and must still be recognised as a numbered heading, with its
    # own centred amendment note excluded from becoming one.
    text = extract_clauses_html(FIXTURE_FSBU_26_2020.read_bytes())
    clauses = {c.path: c for c in parse_clauses(text)}
    assert clauses["17.3"].heading == (
        "Научно-исследовательские, опытно-конструкторские и технологические работы"
    )
