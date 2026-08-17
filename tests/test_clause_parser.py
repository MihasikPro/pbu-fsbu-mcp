from pathlib import Path

import pytest
import yaml

from etl.clause_parser import parse_clauses, slice_appendix

SAMPLE = """
I. Общие положения

1. Настоящий Стандарт устанавливает требования к формированию информации.

2. Настоящий Стандарт не применяется организациями бюджетной сферы.

II. Условия признания

4. Объектом основных средств считается актив, характеризующийся признаками:

а) имеет материально-вещественную форму;

б) предназначен для использования в обычной деятельности.

5. Организация вправе принять решение о неприменении Стандарта.
"""


def test_extracts_top_level_clauses() -> None:
    paths = [clause.path for clause in parse_clauses(SAMPLE)]
    assert "1" in paths
    assert "5" in paths


def test_extracts_lettered_subclauses() -> None:
    paths = [clause.path for clause in parse_clauses(SAMPLE)]
    assert "4.а" in paths
    assert "4.б" in paths


def test_subclause_points_at_its_parent() -> None:
    clause = next(item for item in parse_clauses(SAMPLE) if item.path == "4.а")
    assert clause.parent_path == "4"


def test_top_level_clause_has_no_parent() -> None:
    clause = next(item for item in parse_clauses(SAMPLE) if item.path == "1")
    assert clause.parent_path is None


def test_section_heading_is_attached_to_following_clauses() -> None:
    clause = next(item for item in parse_clauses(SAMPLE) if item.path == "4")
    assert clause.heading == "Условия признания"


def test_clause_text_excludes_its_own_number() -> None:
    clause = next(item for item in parse_clauses(SAMPLE) if item.path == "1")
    assert clause.text.startswith("Настоящий Стандарт устанавливает")


def test_clause_text_excludes_following_clause() -> None:
    clause = next(item for item in parse_clauses(SAMPLE) if item.path == "1")
    assert "бюджетной сферы" not in clause.text


def test_headings_are_not_emitted_as_clauses() -> None:
    paths = [clause.path for clause in parse_clauses(SAMPLE)]
    assert "I" not in paths
    assert "II" not in paths


def test_empty_input_yields_no_clauses() -> None:
    assert parse_clauses("") == []


# --- Decimal-numbered clauses inserted by a later amending order -----------
#
# ПБУ texts amended over many years insert new clauses as "5.1", "7.3",
# "20.2" rather than as lettered subclauses. Both markers found in the wild
# are covered: with the closing dot ("5.1.") and without it ("15.1 ...").

_DECIMAL_SAMPLE = """
5. Организация вправе принять решение о неприменении Стандарта.

5.1. Организация выбирает способ независимо от других организаций.

6. Стандарт не распространяется на капитальные вложения.
"""

_DECIMAL_SAMPLE_NO_DOT = """
15. Изменение учетной политики оформляется в установленном порядке.

15.1 Организации вправе применять упрощенные способы учета.

16. Изменения раскрываются в отчетности.
"""


def test_decimal_clause_gets_its_own_path_with_the_closing_dot() -> None:
    paths = [clause.path for clause in parse_clauses(_DECIMAL_SAMPLE)]
    assert paths == ["5", "5.1", "6"]


def test_decimal_clause_text_excludes_its_own_number() -> None:
    clause = next(item for item in parse_clauses(_DECIMAL_SAMPLE) if item.path == "5.1")
    assert clause.text == "Организация выбирает способ независимо от других организаций."


def test_decimal_clause_does_not_collide_with_the_plain_clause_of_the_same_leading_number() -> (
    None
):
    clauses = {clause.path: clause for clause in parse_clauses(_DECIMAL_SAMPLE)}
    assert clauses["5"].text == "Организация вправе принять решение о неприменении Стандарта."
    assert "5.1" not in clauses["5"].text


def test_decimal_clause_without_a_closing_dot_is_still_recognised() -> None:
    paths = [clause.path for clause in parse_clauses(_DECIMAL_SAMPLE_NO_DOT)]
    assert paths == ["15", "15.1", "16"]


def test_decimal_clause_without_a_closing_dot_has_clean_text() -> None:
    clause = next(item for item in parse_clauses(_DECIMAL_SAMPLE_NO_DOT) if item.path == "15.1")
    assert clause.text == "Организации вправе применять упрощенные способы учета."


# --- slice_appendix: isolating one standard's appendix ---------------------
#
# A single order routinely enacts several standards, each as its own
# appendix. `slice_appendix` anchors on the standard's own header line
# ("ФСБУ N/YYYY «Title»" as the sole content of its paragraph) rather than
# on the "Приложение № N" caption, whose numbering does not say which
# standard it belongs to.

_TWO_APPENDIX_SAMPLE = """Преамбула упоминает ФСБУ 9/2021 «Декоративный» и ФСБУ 10/2021 «Другой»
в одном предложении - это не заголовок приложения, а простое перечисление.

ФЕДЕРАЛЬНЫЙ СТАНДАРТ БУХГАЛТЕРСКОГО УЧЕТА
ФСБУ 9/2021 «Декоративный»

1. Текст пункта первого стандарта.

ФЕДЕРАЛЬНЫЙ СТАНДАРТ БУХГАЛТЕРСКОГО УЧЕТА
ФСБУ 10/2021 «Другой»

1. Текст пункта второго стандарта.
"""


def test_slice_appendix_starts_at_the_real_header_not_the_preamble_mention() -> None:
    sliced = slice_appendix(_TWO_APPENDIX_SAMPLE, "9/2021")
    assert sliced.startswith("ФЕДЕРАЛЬНЫЙ СТАНДАРТ")
    assert "Преамбула" not in sliced


def test_slice_appendix_excludes_the_next_appendix() -> None:
    sliced = slice_appendix(_TWO_APPENDIX_SAMPLE, "9/2021")
    assert "Текст пункта первого стандарта" in sliced
    assert "Текст пункта второго стандарта" not in sliced


def test_slice_appendix_for_the_second_standard_is_the_complement() -> None:
    sliced = slice_appendix(_TWO_APPENDIX_SAMPLE, "10/2021")
    assert "Текст пункта второго стандарта" in sliced
    assert "Текст пункта первого стандарта" not in sliced


def test_slice_appendix_on_single_appendix_text_returns_it_unchanged() -> None:
    single = "1. Пункт первый.\n\n2. Пункт второй."
    assert slice_appendix(single, "6/2020") == single


def test_slice_appendix_raises_for_a_standard_absent_from_a_multi_appendix_document() -> None:
    with pytest.raises(ValueError, match="11/2021"):
        slice_appendix(_TWO_APPENDIX_SAMPLE, "11/2021")


def test_slice_appendix_does_not_confuse_a_number_with_its_suffix() -> None:
    # "6/2020" must not match inside "26/2020" - a naive substring check would.
    only_26 = "ФЕДЕРАЛЬНЫЙ СТАНДАРТ БУХГАЛТЕРСКОГО УЧЕТА\nФСБУ 26/2020 «Капитальные вложения»\n\n1. Текст."
    with pytest.raises(ValueError, match="6/2020"):
        slice_appendix(only_26, "6/2020")


# --- Regression against the real OCR of order 204n -------------------------
#
# The fixture is a local `.superpowers` artifact (gitignored, produced ad hoc
# while diagnosing the parser) and is not committed to the repo, so every
# test below skips gracefully when it is absent - e.g. in a fresh checkout or
# in CI. Lines 106-866 (1-indexed) of that dump hold FSBU 6/2020; the
# hand-verified target is `data/sources/standards/fsbu-6-2020.yaml`, which
# *is* committed. The YAML also contains OCR corrections and two editorial
# ".заключение" splits (13.заключение, 20.заключение) that no text-only
# parser can reproduce, so these tests check clause/subclause *coverage*
# against the YAML's paths rather than byte-for-byte text equality.

_REPO_ROOT = Path(__file__).parent.parent
_OCR_FIXTURE = _REPO_ROOT / ".superpowers" / "sdd" / "source" / "prikaz_204n_ocr.txt"
_GOLD_FSBU_6_2020 = _REPO_ROOT / "data" / "sources" / "standards" / "fsbu-6-2020.yaml"

requires_real_ocr_fixture = pytest.mark.skipif(
    not _OCR_FIXTURE.exists(),
    reason="real OCR fixture (.superpowers/sdd/source/prikaz_204n_ocr.txt) is not committed to the repo",
)


def _parse_real_fsbu_6_2020() -> list:
    lines = _OCR_FIXTURE.read_text(encoding="utf-8").splitlines()
    fsbu_6_2020_text = "\n".join(lines[105:866])
    return parse_clauses(fsbu_6_2020_text)


def _gold_clause_paths() -> tuple[set[str], set[str]]:
    gold = yaml.safe_load(_GOLD_FSBU_6_2020.read_text(encoding="utf-8"))
    paths = [clause["path"] for clause in gold["editions"][0]["clauses"]]
    top_level = {path for path in paths if "." not in path}
    lettered = {path for path in paths if "." in path and "заключение" not in path}
    return top_level, lettered


@requires_real_ocr_fixture
def test_finds_every_hand_verified_top_level_clause() -> None:
    parsed_paths = {clause.path for clause in _parse_real_fsbu_6_2020()}
    top_level, _ = _gold_clause_paths()
    assert top_level <= parsed_paths


@requires_real_ocr_fixture
def test_finds_every_hand_verified_subclause() -> None:
    parsed_paths = {clause.path for clause in _parse_real_fsbu_6_2020()}
    _, lettered = _gold_clause_paths()
    assert lettered <= parsed_paths


@requires_real_ocr_fixture
def test_does_not_invent_paths_outside_the_hand_verified_set() -> None:
    parsed_paths = {clause.path for clause in _parse_real_fsbu_6_2020()}
    top_level, lettered = _gold_clause_paths()
    assert parsed_paths == top_level | lettered


@requires_real_ocr_fixture
def test_multiline_clause_body_is_captured_past_the_first_ocr_line() -> None:
    clauses = {clause.path: clause for clause in _parse_real_fsbu_6_2020()}
    # Clause 37's body wraps across many raw OCR lines with no punctuation
    # until its very end - the original defect truncated it to the first line.
    assert clauses["37"].text.endswith("как изменения оценочных значений.")


@requires_real_ocr_fixture
def test_clause_split_by_a_page_marker_keeps_its_full_text() -> None:
    clauses = {clause.path: clause for clause in _parse_real_fsbu_6_2020()}
    # Clause 49's sentence is interrupted mid-way by a "[[PAGE 20]]" marker
    # plus its page-number footer line; both must be stripped, not glued in.
    assert (
        "полезного использования, определенного в соответствии с настоящим Стандартом."
        in clauses["49"].text
    )


@requires_real_ocr_fixture
def test_digit_six_is_recovered_as_letter_b_in_sequence() -> None:
    clauses = {clause.path: clause for clause in _parse_real_fsbu_6_2020()}
    # Raw OCR misreads "б) предназначен..." as "6) предназначен...".
    assert clauses["4.б"].text.startswith("предназначен для использования")


@requires_real_ocr_fixture
def test_digit_three_is_recovered_as_letter_z_in_sequence() -> None:
    clauses = {clause.path: clause for clause in _parse_real_fsbu_6_2020()}
    # Raw OCR misreads "з) сумма обесценения..." as "3) сумма обесценения...",
    # itself split across a page break from the preceding "ж)".
    assert clauses["45.з"].text.startswith("сумма обесценения")


@requires_real_ocr_fixture
def test_section_headings_survive_ocr_corruption_of_roman_numerals() -> None:
    clauses = {clause.path: clause for clause in _parse_real_fsbu_6_2020()}
    assert clauses["1"].heading == "Общие положения"  # "I." collides with clause "1."
    assert clauses["12"].heading == "Оценка"  # "II." OCR-corrupted to "НП."
    assert clauses["27"].heading == "Амортизация"  # "III." OCR-corrupted to "Ш."
    assert clauses["40"].heading == "Списание"  # "IV." OCR-corrupted to "ГУ."
    assert clauses["45"].heading == "Раскрытие информации в отчетности"  # "V." -> "У."
    assert clauses["48"].heading == "Изменение учетной политики"  # "VI." -> "\У1."


@requires_real_ocr_fixture
def test_section_heading_colliding_with_clause_1_is_not_emitted_as_a_clause() -> None:
    parsed = _parse_real_fsbu_6_2020()
    # "1. Общие положения" is the section-I heading; it must not also surface
    # as a garbage duplicate of clause "1".
    assert sum(1 for clause in parsed if clause.path == "1") == 1


# --- slice_appendix against the real order 204n (two standards, one PDF) ---


def _real_order_text() -> str:
    return _OCR_FIXTURE.read_text(encoding="utf-8")


@requires_real_ocr_fixture
def test_slice_appendix_fsbu_6_2020_contains_clause_52_and_not_fsbu_26_2020() -> None:
    clauses = {c.path: c for c in parse_clauses(slice_appendix(_real_order_text(), "6/2020"))}
    assert "52" in clauses
    # "Капитальные вложения" is FSBU 26/2020's own title; it appears nowhere
    # inside FSBU 6/2020's appendix once the neighbouring one is sliced out.
    assert all("Капитальные вложения" not in c.text for c in clauses.values())


@requires_real_ocr_fixture
def test_slice_appendix_fsbu_26_2020_is_the_complement_of_fsbu_6_2020() -> None:
    clauses = {c.path: c for c in parse_clauses(slice_appendix(_real_order_text(), "26/2020"))}
    # "Основные средства" is FSBU 6/2020's own title; absent once its
    # appendix has been sliced away from FSBU 26/2020's.
    assert all("Основные средства" not in c.text for c in clauses.values())


@requires_real_ocr_fixture
def test_slice_appendix_fsbu_6_2020_matches_the_hand_verified_clause_set() -> None:
    parsed_paths = {c.path for c in parse_clauses(slice_appendix(_real_order_text(), "6/2020"))}
    top_level, lettered = _gold_clause_paths()
    assert parsed_paths == top_level | lettered
