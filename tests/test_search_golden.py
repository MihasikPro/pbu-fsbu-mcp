"""Regression suite for search relevance.

Pairs marked `lexical_limitation: true` are queries whose correct answer shares
no wording with the clause that answers them. The lexical BM25 backend cannot
reach those by construction - it was chosen over a hybrid embedding backend
deliberately, and this is the documented cost. They are kept, excluded from the
hit rate, and asserted to STILL fail: when a semantic backend lands they will
start passing, and this test will demand the marker be removed rather than
letting the gap quietly disappear.
"""

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from pbu_fsbu_mcp.search.fts import FtsSearchBackend

GOLDEN = Path(__file__).parent / "golden_queries.yaml"
TODAY = date(2026, 8, 14)
MIN_HIT_RATE = 0.9


def _load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    return cases


def _finds_expected(backend: FtsSearchBackend, case: dict[str, Any]) -> tuple[bool, str]:
    hits = backend.search(case["query"], None, TODAY, limit=3)
    found = any(
        hit.standard_id == case["expect_standard"] and hit.path == case["expect_path"]
        for hit in hits
    )
    got = ", ".join(f"{hit.standard_id}#{hit.path}" for hit in hits) or "ничего"
    return found, got


def test_golden_queries_hit_rate(corpus_db: Path) -> None:
    backend = FtsSearchBackend(corpus_db)
    cases = [case for case in _load_cases() if not case.get("lexical_limitation")]
    assert cases, "Golden-набор не должен состоять из одних известных ограничений"

    misses: list[str] = []
    for case in cases:
        found, got = _finds_expected(backend, case)
        if not found:
            misses.append(
                f"{case['query']!r}: ожидался "
                f"{case['expect_standard']}#{case['expect_path']}, получено {got}"
            )

    hit_rate = 1 - len(misses) / len(cases)
    assert hit_rate >= MIN_HIT_RATE, "Промахи:\n" + "\n".join(misses)


def test_known_lexical_limitations_still_fail(corpus_db: Path) -> None:
    """A limitation that started working must be promoted, not left mislabelled."""
    backend = FtsSearchBackend(corpus_db)
    cases = [case for case in _load_cases() if case.get("lexical_limitation")]

    unexpectedly_passing = [
        case["query"] for case in cases if _finds_expected(backend, case)[0]
    ]
    assert not unexpectedly_passing, (
        "Эти запросы помечены как недостижимые для лексического поиска, но проходят. "
        "Снимите пометку lexical_limitation и верните их в основной набор: "
        + ", ".join(repr(query) for query in unexpectedly_passing)
    )
