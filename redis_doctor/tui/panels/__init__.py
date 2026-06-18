"""Shared helpers for TUI panels.

Each panel module exposes `render(report, severity_filter, expanded) -> RenderableType`.
Panels never recompute analysis; they render a slice of the single Report.
"""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from ...models.finding import Category, Finding, Severity
from ...models.report import Report

_SEVERITY_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.WARNING: "yellow",
    Severity.INFO: "dim",
}


def filter_findings(
    report: Report,
    categories: list[Category] | None,
    severity_filter: Severity | None,
) -> list[Finding]:
    out = report.findings
    if categories is not None:
        cats = set(categories)
        out = [f for f in out if f.category in cats]
    if severity_filter is not None:
        out = [f for f in out if f.severity == severity_filter]
    order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
    return sorted(out, key=lambda f: order[f.severity])


def finding_line(f: Finding, expanded: bool) -> RenderableType:
    head = Text()
    head.append(f"[{f.category.value.upper()}] {f.id}", style=_SEVERITY_STYLE[f.severity])
    head.append(" — ")
    head.append(f.title)
    if not expanded:
        return head
    parts: list[RenderableType] = [head]
    if f.evidence:
        ev = Text("    Evidence: ", style="dim")
        ev.append(", ".join(f"{k}={v}" for k, v in f.evidence.items()))
        parts.append(ev)
    if f.explanation:
        parts.append(Text(f"    Impact: {f.explanation}", style="dim"))
    for label, items, sep in (
        ("Checks", f.suggested_checks, " | "),
        ("Fixes", f.suggested_fixes, "; "),
    ):
        if items:
            t = Text(f"    {label}: ", style="dim")
            t.append(sep.join(items))
            parts.append(t)
    return Group(*parts)


def findings_block(findings: list[Finding], expanded: bool) -> RenderableType:
    if not findings:
        return Text("No findings in this view.", style="green")
    return Group(*[finding_line(f, expanded) for f in findings])


def build_panel(
    report: Report,
    title: str,
    categories: list[Category] | None,
    severity_filter: Severity | None,
    expanded: bool,
    header: RenderableType | None = None,
) -> RenderableType:
    findings = filter_findings(report, categories, severity_filter)
    parts: list[RenderableType] = []
    if header is not None:
        parts.append(header)
        parts.append(Rule(style="dim"))
    parts.append(findings_block(findings, expanded))
    return Panel(Group(*parts), title=title, border_style="cyan")
