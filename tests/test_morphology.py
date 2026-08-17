import pytest

from pbu_fsbu_mcp.search.morphology import PROTECTED_TERMS, lemmatize


@pytest.mark.parametrize(
    ("source", "expected_lemma"),
    [
        ("амортизационных", "амортизационный"),
        ("основными", "основный"),
        ("средствами", "средство"),
        ("стоимости", "стоимость"),
        ("обязательства", "обязательство"),
        ("признается", "признаваться"),
    ],
)
def test_single_word_is_normalised(source: str, expected_lemma: str) -> None:
    assert lemmatize(source) == expected_lemma


@pytest.mark.parametrize("term", sorted(PROTECTED_TERMS))
def test_domain_abbreviations_survive_lemmatisation(term: str) -> None:
    assert lemmatize(term) == term


def test_fsbu_is_not_collapsed_into_fsb() -> None:
    """Без защиты pymorphy3 превращает «ФСБУ» в «фсб» — чужую аббревиатуру."""
    assert "фсб " not in lemmatize("ФСБУ 6/2020") + " "


def test_phrase_is_normalised_word_by_word() -> None:
    assert lemmatize("ликвидационной стоимости") == "ликвидационный стоимость"


def test_punctuation_and_case_are_dropped() -> None:
    assert lemmatize("Основные средства, (ОС)!") == "основной средство ос"


def test_digits_are_preserved() -> None:
    assert lemmatize("пункт 9 ФСБУ 6/2020") == "пункт 9 фсбу 6 2020"


def test_phrase_case_uses_context_dependent_lemma() -> None:
    """«Основные» и «основными» дают разные леммы - это поведение pymorphy3."""
    assert lemmatize("основными") == "основный"
    assert lemmatize("Основные средства") == "основной средство"


def test_empty_input_returns_empty_string() -> None:
    assert lemmatize("   ") == ""
