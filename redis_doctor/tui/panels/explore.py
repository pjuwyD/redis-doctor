"""Explore panel: browse the sampled keys' metadata.

The TUI holds a single Report and no live connection, so this is a read-only,
metadata-only view of the largest sampled keys (type, TTL, memory, size). Live
bounded/full value peeking with the unlock is a GUI feature (it needs a
connection) — see the web dashboard's Explore tab.
"""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from ...models.finding import Severity
from ...models.report import Report
from ...output.terminal import human_bytes

MAX_ROWS = 40
MAX_ROWS_EXPANDED = 200


def render(report: Report, severity_filter: Severity | None, expanded: bool) -> RenderableType:
    ks = report.stats.get("keyspace") or {}
    keys = ks.get("sampled_keys") or []
    if not keys:
        return Text("No sampled keys (run with the keyspace module).")

    limit = MAX_ROWS_EXPANDED if expanded else MAX_ROWS
    table = Table(
        title=f"Largest sampled keys (showing {min(limit, len(keys))} of {len(keys)})",
        title_style="bold",
        expand=True,
    )
    table.add_column("Key", overflow="fold")
    table.add_column("Type")
    table.add_column("TTL", justify="right")
    table.add_column("Memory", justify="right")
    table.add_column("Size", justify="right")
    for k in keys[:limit]:
        ttl = k["ttl"]
        ttl_text = "none" if ttl is None or ttl < 0 else f"{ttl}s"
        table.add_row(
            Text(k["key"]),  # plain text: never interpret key data as markup
            k["type"],
            ttl_text,
            human_bytes(k["memory"]) if k.get("memory") else "-",
            str(k["size"]) if k.get("size") is not None else "-",
        )

    hint = Text(
        "metadata only — use the web dashboard (serve) to peek at or unlock values; "
        "press e to show more rows",
        style="dim",
    )
    return Group(table, hint)
