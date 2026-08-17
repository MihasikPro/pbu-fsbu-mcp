from pathlib import Path

import pytest
import yaml

from etl.clause_parser import parse_clauses

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
