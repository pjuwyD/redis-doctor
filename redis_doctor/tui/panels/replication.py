"""Replication panel."""

from __future__ import annotations

from rich.console import RenderableType
from rich.text import Text

from ...models.finding import Category, Severity
from ...models.report import Report
from . import build_panel


def render(report: Report, severity_filter: Severity | None, expanded: bool) -> RenderableType:
    s = report.server
    header = Text(
        f"role {s.role}  connected_slaves {s.connected_slaves}",
        style="dim",
    )
    return build_panel(
        report, "Replication", [Category.REPLICATION], severity_filter, expanded, header
    )
