"""Russian lemmatisation shared by the indexer and the query parser.

Both sides MUST call `lemmatize`; using it on one side only silently breaks
recall, because the index and the query would then live in different spaces.
"""

from __future__ import annotations

import re
from functools import lru_cache

import pymorphy3

_TOKEN_RE = re.compile(r"[0-9]+|[а-яёa-z]+", re.IGNORECASE)
_analyzer = pymorphy3.MorphAnalyzer()

# Domain abbreviations that the morphological analyser mangles.
# Verified: pymorphy3 normalises "фсбу" to "фсб" - the security service, not
# the accounting standard. Collapsing the domain's central term into an
# unrelated abbreviation poisons ranking, so these pass through untouched.
PROTECTED_TERMS = frozenset(
    {"фсбу", "пбу", "мсфо", "нма", "мпз", "ппа", "спи", "ос", "нку"}
)


@lru_cache(maxsize=100_000)
def _lemma(token: str) -> str:
    if token in PROTECTED_TERMS:
        return token
    return str(_analyzer.parse(token)[0].normal_form)


def lemmatize(text: str) -> str:
    """Return space-separated lemmas of `text`, lowercased, punctuation dropped."""
    tokens = _TOKEN_RE.findall(text.lower())
    return " ".join(_lemma(token) for token in tokens)
