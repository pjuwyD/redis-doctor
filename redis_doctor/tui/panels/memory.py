"""Memory panel."""

from __future__ import annotations

from rich.console import RenderableType
from rich.text import Text

from ...models.finding import Category, Severity
from ...models.report import Report
from ...output.terminal import human_bytes
from . import build_panel


def render(report: Report, severity_filter: Severity | None, expanded: bool) -> RenderableType:
    s = report.server
    if s.maxmemory_bytes:
        pct = 100 * s.used_memory_bytes / s.maxmemory_bytes
        line = (
            f"Used {human_bytes(s.used_memory_bytes)} / {human_bytes(s.maxmemory_bytes)} "
            f"({pct:.0f}%)"
        )
    else:
        line = f"Used {human_bytes(s.used_memory_bytes)} / unbounded"
    header = Text.assemble(
        (line + "\n", "bold"),
        (f"policy {s.maxmemory_policy}  fragmentation {s.mem_fragmentation_ratio:.2f}", "dim"),
    )
    return build_panel(
        report, "Memory", [Category.MEMORY], severity_filter, expanded, header=header
    )
