"""Clients panel."""

from __future__ import annotations

from rich.console import RenderableType
from rich.text import Text

from ...models.finding import Category, Severity
from ...models.report import Report
from . import build_panel


def render(report: Report, severity_filter: Severity | None, expanded: bool) -> RenderableType:
    c = report.stats.get("clients")
    if c:
        lines = [
            f"{c['total']} connected, {c['blocked']} blocked, {c['idle_over_1h']} idle over 1h"
        ]
        if c["total"]:
            lines.append(f"{c['unnamed'] / c['total']:.0%} unnamed")
        if c.get("top_commands"):
            lines.append("Top: " + ", ".join(f"{k} {v}" for k, v in c["top_commands"].items()))
        header: RenderableType = Text("\n".join(lines))
    else:
        header = Text(f"{report.server.connected_clients} connected (no per-client detail).")
    return build_panel(report, "Clients", [Category.CLIENTS], severity_filter, expanded, header)
