"""Sentinel panel (populated only when connected via Sentinel)."""

from __future__ import annotations

from rich.console import RenderableType
from rich.text import Text

from ...models.finding import Category, Severity
from ...models.report import Report
from . import build_panel


def render(report: Report, severity_filter: Severity | None, expanded: bool) -> RenderableType:
    s = report.stats.get("sentinel")
    if s:
        header: RenderableType = Text(
            f"master {s['master_name']}  "
            f"sentinels {s['reachable_sentinels']}/{s['configured_sentinels']}  "
            f"quorum {s['quorum']}  replicas {len(s.get('replicas', []))}"
        )
    else:
        header = Text("Not connected via Sentinel.", style="dim")
    return build_panel(report, "Sentinel", [Category.SENTINEL], severity_filter, expanded, header)
