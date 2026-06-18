"""Slowlog panel."""

from __future__ import annotations

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from ...models.finding import Category, Severity
from ...models.report import Report
from . import build_panel


def render(report: Report, severity_filter: Severity | None, expanded: bool) -> RenderableType:
    sl = report.stats.get("slowlog")
    if sl:
        header: RenderableType = Table(expand=False)
        header.add_column("Metric")
        header.add_column("Value", justify="right")
        header.add_row("Slowlog length", str(sl["length"]))
        header.add_row("Sampled entries", str(sl["sampled"]))
        header.add_row("Max duration (us)", f"{sl['max_duration_us']:,}")
        header.add_row("Avg duration (us)", f"{sl['avg_duration_us']:,}")
        if sl.get("command_frequency"):
            top = ", ".join(f"{k} {v}" for k, v in sl["command_frequency"].items())
            header.add_row("Top commands", Text(top))
    else:
        header = Text("No slowlog data.")
    return build_panel(report, "Slowlog", [Category.SLOWLOG], severity_filter, expanded, header)
