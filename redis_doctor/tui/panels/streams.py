"""Streams panel."""

from __future__ import annotations

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from ...models.finding import Category, Severity
from ...models.report import Report
from . import build_panel


def render(report: Report, severity_filter: Severity | None, expanded: bool) -> RenderableType:
    streams = report.stats.get("streams")
    if streams:
        header: RenderableType = Table(expand=False)
        header.add_column("Stream")
        header.add_column("Length", justify="right")
        header.add_column("Group")
        header.add_column("Pending", justify="right")
        for st in streams:
            if not st["groups"]:
                header.add_row(Text(st["name"]), f"{st['length']:,}", "-", "-")
            for g in st["groups"]:
                header.add_row(
                    Text(st["name"]), f"{st['length']:,}", Text(g["name"]), f"{g['pending']:,}"
                )
    else:
        header = Text("No streams found in the sample.")
    return build_panel(report, "Streams", [Category.STREAMS], severity_filter, expanded, header)
