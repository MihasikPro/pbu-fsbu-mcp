"""Render a reviewable YAML draft from parsed sources.

Output goes to `data/drafts/`, never straight to `data/sources/`: clause
texts must be proof-read against the official act before they become the
project's source of truth.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from etl.clause_parser import ParsedClause, parse_clauses, slice_appendix
from etl.http_client import fetch
from etl.ocr_text import extract
from etl.pravo import parse_search, search_url
from etl.registry import REGISTRY_URL, RegistryRow, parse

DRAFT_BANNER = (
    "# ЧЕРНОВИК. Тексты пунктов получены автоматически и НЕ вычитаны.\n"
    "# Сверьте каждый пункт с официальным текстом приказа, затем перенесите\n"
    "# файл в data/sources/standards/ и удалите этот баннер.\n"
)


def render(row: RegistryRow, clauses: list[ParsedClause]) -> str:
    document: dict[str, Any] = {
        "id": row.id,
        "kind": row.kind,
        "number": row.number,
        "year": row.year,
        "title": row.title,
        "order_date": row.order_date,
        "order_no": row.order_no,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "superseded_by": None,
        "source_url": row.source_url,
        "editions": [
            {
                "edition_no": 1,
                "amending_order": None,
                "effective_from": row.effective_from,
                "clauses": [
                    {
                        "path": clause.path,
                        "parent_path": clause.parent_path,
                        "heading": clause.heading,
                        "text": clause.text,
                    }
                    for clause in clauses
                ],
            }
        ],
    }
    body = yaml.safe_dump(document, allow_unicode=True, sort_keys=False, width=100)
    return DRAFT_BANNER + body


def _fetch_clauses(row: RegistryRow, cache_dir: Path, *, live: bool) -> list[ParsedClause]:
    """Locate the published order, OCR it, and split the result into clauses."""
    search_payload = fetch(search_url(row.order_date, row.order_no), cache_dir, live=live)
    acts = parse_search(search_payload)
    if not acts:
        raise LookupError(
            f"Не найден опубликованный акт для приказа №{row.order_no} "
            f"от {row.order_date:%d.%m.%Y}"
        )
    pdf_bytes = fetch(acts[0].pdf_url, cache_dir, live=live)
    order_text = extract(pdf_bytes)
    return parse_clauses(slice_appendix(order_text, row.number))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="draft-yaml")
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--out", type=Path, default=Path("data/drafts"))
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--only",
        metavar="STANDARD_ID",
        help="сгенерировать черновик только для одного стандарта, например fsbu-6-2020",
    )
    args = parser.parse_args(argv)

    rows = parse(fetch(REGISTRY_URL, args.cache, live=args.live), REGISTRY_URL)
    if args.only is not None:
        rows = [row for row in rows if row.id == args.only]
        if not rows:
            print(f"Стандарт {args.only!r} не найден в реестре Минфина", file=sys.stderr)
            return 1

    args.out.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for row in rows:
        print(f"[{row.id}] распознавание приказа №{row.order_no}...", flush=True)
        try:
            clauses = _fetch_clauses(row, args.cache, live=args.live)
        except Exception as exc:  # noqa: BLE001 - one standard's failure must not abort the batch
            failures.append(f"{row.id}: {exc}")
            print(f"[{row.id}] ОШИБКА: {exc}", file=sys.stderr)
            continue
        (args.out / f"{row.id}.yaml").write_text(render(row, clauses), encoding="utf-8")
        print(f"[{row.id}] {len(clauses)} пунктов")

    print(f"Черновиков записано: {len(rows) - len(failures)} из {len(rows)} в {args.out}")
    if failures:
        print("Не обработаны:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
