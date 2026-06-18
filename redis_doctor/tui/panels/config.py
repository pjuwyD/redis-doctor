"""Config panel: config + persistence risk findings."""

from __future__ import annotations

from rich.console import RenderableType
from rich.text import Text

from ...models.finding import Category, Severity
from ...models.report import Report
from . import build_panel


def render(report: Report, severity_filter: Severity | None, expanded: bool) -> RenderableType:
    s = report.server
    header = Text(
        f"policy {s.maxmemory_policy}  AOF {'on' if s.aof_enabled else 'off'}  "
        f"rdb_status {s.rdb_last_bgsave_status}",
        style="dim",
    )
    cats = [Category.CONFIG, Category.PERSISTENCE]
    return build_panel(report, "Config", cats, severity_filter, expanded, header)
