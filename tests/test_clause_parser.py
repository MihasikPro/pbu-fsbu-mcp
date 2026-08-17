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
