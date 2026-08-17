"""Split an order's text into a hierarchy of numbered clauses."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SECTION_RE = re.compile(r"^\s*(?:[IVXLC]+)\.\s+(?P<heading>[^\n]+?)\s*$")
_CLAUSE_RE = re.compile(r"^\s*(?P<number>\d+)\.\s+(?P<body>.+)$")
_SUBCLAUSE_RE = re.compile(r"^\s*(?P<letter>[а-я])\)\s+(?P<body>.+)$")


@dataclass(frozen=True, slots=True)
class ParsedClause:
    path: str
    parent_path: str | None
    heading: str | None
    text: str


def parse_clauses(text: str) -> list[ParsedClause]:
    """Return clauses in document order, attaching the enclosing section heading."""
    clauses: list[ParsedClause] = []
    heading: str | None = None
    last_top_level: str | None = None

    for block in _blocks(text):
        section = _SECTION_RE.match(block)
        if section:
            heading = section["heading"].strip()
            continue

        subclause = _SUBCLAUSE_RE.match(block)
        if subclause and last_top_level is not None:
            clauses.append(
                ParsedClause(
                    path=f"{last_top_level}.{subclause['letter']}",
                    parent_path=last_top_level,
                    heading=None,
                    text=subclause["body"].strip(),
                )
            )
            continue

        clause = _CLAUSE_RE.match(block)
        if clause:
            last_top_level = clause["number"]
            clauses.append(
                ParsedClause(
                    path=clause["number"],
                    parent_path=None,
                    heading=heading,
                    text=clause["body"].strip(),
                )
            )

    return clauses


def _blocks(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
