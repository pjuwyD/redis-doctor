"""Keys panel: prefix table, type distribution, sampling metadata + key findings."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from ...models.finding import Category, Severity
from ...models.report import Report
from . import build_panel


def render(report: Report, severity_filter: Severity | None, expanded: bool) -> RenderableType:
    ks = report.stats.get("keyspace")
    parts: list[RenderableType] = []
    if ks:
        parts.append(
            Text(
                f"Sampled {ks['scanned']:,} of {ks['estimated_total']:,} keys "
                f"(confidence {ks['confidence']}, {ks['duration_seconds']}s)",
                style="dim",
            )
        )
        by_count = ks.get("top_prefixes_by_count") or []
        if by_count:
            table = Table(title="Top prefixes", expand=False)
            table.add_column("Prefix")
            table.add_column("Keys", justify="right")
            for p in by_count:
                table.add_row(Text(f"{p['prefix']}:*"), f"{p['count']:,}")
            parts.append(table)
        dist = ks.get("type_distribution") or {}
        if dist:
            total = sum(dist.values()) or 1
            parts.append(
                Text(
                    "Types: "
                    + ", ".join(
                        f"{t} {100 * c / total:.0f}%"
                        for t, c in sorted(dist.items(), key=lambda x: -x[1])
                    )
                )
            )
    header = Group(*parts) if parts else Text("No keyspace data (run with the keyspace module).")
    cats = [Category.KEYSPACE, Category.TTL, Category.BIGKEY, Category.TYPES]
    return build_panel(report, "Keys", cats, severity_filter, expanded, header=header)
