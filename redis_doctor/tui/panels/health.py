"""Health panel: score, severity counts, top findings."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.text import Text

from ...models.finding import Severity
from ...models.report import Report
from . import build_panel


def render(report: Report, severity_filter: Severity | None, expanded: bool) -> RenderableType:
    score = report.health_score
    style = "green" if score >= 80 else "yellow" if score >= 50 else "red"
    header = Group(
        Text.assemble(("Health score: ", "bold"), (f"{score}/100", f"bold {style}")),
        Text(
            f"{report.summary.critical} critical   "
            f"{report.summary.warning} warning   "
            f"{report.summary.info} info"
        ),
        Text(
            f"Redis {report.server.redis_version}  role {report.server.role}  "
            f"target {report.target}",
            style="dim",
        ),
    )
    return build_panel(report, "Health", None, severity_filter, expanded, header=header)
