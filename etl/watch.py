"""Compare the live Minfin registry against the committed corpus."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from etl.http_client import fetch
from etl.registry import REGISTRY_URL, RegistryRow, parse
from pbu_fsbu_mcp.loader import load_all
from pbu_fsbu_mcp.models import Standard


@dataclass(frozen=True, slots=True)
class RegistryDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def render(self) -> str:
        lines: list[str] = []
        if self.added:
            lines.append("### Новые стандарты в реестре Минфина")
            lines.extend(f"- `{item}`" for item in self.added)
        if self.removed:
            lines.append("### Стандарты исчезли из реестра")
            lines.extend(f"- `{item}`" for item in self.removed)
        if self.changed:
            lines.append("### Изменились реквизиты")
            lines.extend(f"- {item}" for item in self.changed)
        return "\n".join(lines) if lines else "Расхождений нет."


def diff_registry(rows: list[RegistryRow], standards: list[Standard]) -> RegistryDiff:
    live = {row.id: row for row in rows}
    local = {standard.id: standard for standard in standards}

    changed: list[str] = []
    for standard_id in sorted(live.keys() & local.keys()):
        row, standard = live[standard_id], local[standard_id]
        if row.order_no != standard.order_no:
            changed.append(
                f"`{standard_id}`: приказ {standard.order_no} → {row.order_no}"
            )
        if row.effective_from != standard.effective_from:
            changed.append(
                f"`{standard_id}`: применение с {standard.effective_from} → {row.effective_from}"
            )
        if row.effective_to != standard.effective_to:
            changed.append(
                f"`{standard_id}`: утрата силы {standard.effective_to} → {row.effective_to}"
            )

    return RegistryDiff(
        added=sorted(live.keys() - local.keys()),
        removed=sorted(local.keys() - live.keys()),
        changed=changed,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="etl-watch")
    parser.add_argument("--sources", type=Path, default=Path("data/sources/standards"))
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--report", type=Path, default=Path("registry-diff.md"))
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--save-fixture",
        type=Path,
        default=None,
        help="Also write the fetched registry HTML to this path (e.g. to refresh the test fixture).",
    )
    args = parser.parse_args(argv)

    html = fetch(REGISTRY_URL, args.cache, live=args.live)
    if args.save_fixture is not None:
        args.save_fixture.write_bytes(html)

    rows = parse(html, REGISTRY_URL)
    diff = diff_registry(rows, load_all(args.sources))
    args.report.write_text(diff.render(), encoding="utf-8")

    if diff.is_empty:
        print("Реестр Минфина совпадает с корпусом")
        return 0
    print(diff.render(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
